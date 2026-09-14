"""goalpacer/saude.py, telemetria e logs.py: métricas locais, alertas perto do limite e a leitura por CLI (análise de 13/09)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import logs as logs_cli
import status
from goalpacer import registro as reg, saude, telemetria

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 29, 9, 0, tzinfo=TZ)


def job(n, *, duracao=150.0, teto=1200.0, lock=0.0, classe=None, tokens=7000):
    ts = AGORA - timedelta(days=n)
    geracao = {
        "run_id": "job-diario-%s" % ts.strftime("%Y%m%d-%H%M%S"),
        "modo": "job:diario",
        "data": ts.date().isoformat(),
        "ts": ts.isoformat(),
        "exit_code": 3 if classe else 0,
        "duracao_s": duracao,
        "teto_s": teto,
        "espera_lock_s": lock,
        "tokens": {"input": tokens, "output": 0},
    }
    if classe:
        geracao["classe"] = classe
    return geracao


@pytest.fixture
def dados(tmp_path, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "diario" / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_AGORA", AGORA.isoformat())
    monkeypatch.setattr("goalpacer.clock._AGORA_FIXADO", None)
    return destino


def test_sem_nada_perto_do_limite_nao_ha_alerta(dados):
    registro = reg.carregar(dados)
    for n in range(8, 0, -1):
        reg.registrar_geracao(registro, job(n))
    assert saude.alertas(dados, AGORA, registro) == []
    medidas = saude.metricas(dados)
    assert medidas["registro_kb"] > 0 and medidas["dias"] >= 1 and medidas["painel_p95_ms"] is None


def test_cada_limite_vira_um_alerta_com_texto_para_frente(dados, monkeypatch):
    from goalpacer import tom

    registro = reg.carregar(dados)
    for n in range(12, 2, -1):
        reg.registrar_geracao(registro, job(n))
    reg.registrar_geracao(registro, job(2, classe="RateLimited", duracao=1900.0, teto=3000.0))
    reg.registrar_geracao(registro, job(1, classe="RateLimited", lock=420.0))
    reg.registrar_geracao(registro, job(0, duracao=900.0, tokens=16000))
    for i in range(12):
        telemetria.registrar_span(
            "conector", 95000.0 if i == 0 else 8000.0, ferramenta="list_events", tentativa=2 if i < 5 else 1
        )
    for i in range(25):
        telemetria.evento("painel", metodo="GET", rota="/api/painel", status=200, ms=350.0 if i > 20 else 20.0)
    telemetria.evento("erro_front", mensagem="x", tela="hoje")
    monkeypatch.setattr(saude, "REGISTRO_GRANDE_KB", 0.001)
    alertas = saude.alertas(dados, AGORA, registro)
    assert [a["chave"] for a in alertas] == [
        "job_perto_do_teto",
        "espera_lock",
        "limite_de_uso",
        "tokens_acima",
        "chamada_lenta",
        "retries_startup",
        "registro_grande",
        "painel_lento",
        "erros_tela",
    ]
    assert all(tom.violacoes(a["texto"]) == [] for a in alertas)
    assert [a["chave"] for a in saude.alertas(dados, AGORA, registro, so_do_job=True)] == list(saude.ALERTAS_DO_JOB)
    # o status mostra a seção logo depois das pendências
    reg.salvar(registro, dados)
    modelo = status.coletar(dados, AGORA)
    texto = status.render_status(modelo)
    assert "Perto do limite" in texto and texto.index("Perto do limite") < texto.index("Como vão as metas")
    assert modelo["saude"]["chaves"][:1] == ["job_perto_do_teto"] and modelo["saude"]["metricas"]["erros_front_7d"] == 1


def test_notificacao_so_na_terceira_vez_e_uma_por_sequencia():
    registro = reg.vazio()
    for n, chaves in ((3, ["tokens_acima"]), (2, ["tokens_acima"])):
        geracao = job(n)
        geracao.update({"alertas": chaves})
        reg.registrar_geracao(registro, geracao)
    atual = job(1)
    reg.registrar_geracao(registro, atual)
    assert saude.notificacao_repetida(registro, ["tokens_acima"], run_id_atual=atual["run_id"]) == "tokens_acima"
    registro["geracoes"][atual["run_id"]].update({"alertas": ["tokens_acima"], "alerta_notificado": "tokens_acima"})
    seguinte = job(0)
    reg.registrar_geracao(registro, seguinte)
    assert saude.notificacao_repetida(registro, ["tokens_acima"], run_id_atual=seguinte["run_id"]) is None
    assert saude.notificacao_repetida(registro, ["espera_lock"], run_id_atual=seguinte["run_id"]) is None


def test_logs_cli_resumo_eventos_e_trace(dados, capsys, monkeypatch):
    monkeypatch.setenv("GP_TRACE_ID", "job-diario-20260929-070000")
    raiz = telemetria.registrar_span("job", 150000.0, pai="", modo="diario", codigo=0)
    monkeypatch.setenv("GP_TRACE_PAI", raiz)
    with telemetria.span("passo", passo="diario", codigo=0):
        telemetria.registrar_span("conector", 8200.0, ferramenta="list_events", tentativa=1)
        telemetria.registrar_span("conector", 12100.0, ferramenta="list_events", tentativa=2)
    telemetria.evento("painel", metodo="GET", rota="/api/painel", status=200, ms=18.0)
    assert logs_cli.main(["trace", "ultimo"]) == 0
    arvore = capsys.readouterr().out
    assert (
        "job diario  150.0 s" in arvore
        and "\n  passo diario" in arvore
        and "\n    conector list_events  12.1 s tentativa 2" in arvore
    )
    assert logs_cli.main(["resumo", "--json"]) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert (
        resumo["resumo"]["conectores"]["list_events"]["n"] == 2
        and resumo["resumo"]["painel"]["GET /api/painel"]["p50_ms"] == 18.0
    )
    assert resumo["resumo"]["chamadas"] == {"total": 2, "repetidas": 1} and resumo["metricas"]["dias"] >= 1
    assert logs_cli.main(["eventos", "--tipo", "painel", "--json"]) == 0
    assert [e["rota"] for e in json.loads(capsys.readouterr().out)["eventos"]] == ["/api/painel"]
    monkeypatch.setenv("GP_TELEMETRIA", "0")
    assert logs_cli.main(["resumo"]) == 2
