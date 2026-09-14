"""Testes de goalpacer.perfil: progresso, ritmo, fator de duração, janelas e o que NÃO entra."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import perfil as prf, registro as reg, schema

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "checkin" / "dados"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)


def pasta(tmp_path: Path) -> Path:
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES, destino)
    return destino


def escrever_dia(dados: Path, data: str, blocos: list[tuple[str, str, float]]) -> None:
    """blocos: (sufixo, inicio ISO, horas)."""
    linhas = ["---", "data: %s" % data, "run_id: fx", "---", "", "## Hoje", ""]
    for sufixo, inicio, horas in blocos:
        ini = datetime.fromisoformat(inicio)
        linhas += [
            "### D-%s-%s Bloco" % (data, sufixo),
            "- meta: M01",
            "- semana: 2026-W40",
            "- inicio: %s" % ini.isoformat(),
            "- fim: %s" % (ini + timedelta(hours=horas)).isoformat(),
            "- duracao_h: %s" % horas,
            "- estado: planejada",
            "- origem: inferido",
            "",
        ]
    (dados / "dias" / (data + ".md")).write_text("\n".join(linhas) + "\n", encoding="utf-8")


def test_faixas_e_buckets():
    assert prf.faixa_de(datetime(2026, 9, 28, 8, 0, tzinfo=TZ)) == "seg-manha"
    assert prf.faixa_de(datetime(2026, 9, 29, 12, 0, tzinfo=TZ)) == "ter-tarde"
    assert prf.faixa_de(datetime(2026, 10, 3, 19, 0, tzinfo=TZ)) == "sab-noite"
    assert prf.faixa_de(datetime(2026, 10, 4, 23, 59, tzinfo=TZ)) == "dom-noite"
    assert prf.bucket_duracao(0.5) == "ate_1h" and prf.bucket_duracao(1.0) == "ate_1h"
    assert prf.bucket_duracao(1.5) == "1h_2h" and prf.bucket_duracao(3) == "mais_2h"


def test_perfil_vazio_e_valido(tmp_path, agora_fixo):
    dados = pasta(tmp_path)
    perfil = prf.calcular(dados, AGORA)
    assert schema.validar_registro("perfil", perfil) == []
    assert perfil["n_confirmadas"] == 0 and perfil["janelas"] == {}
    m1 = perfil["metas"]["M01"]
    assert m1["progresso_pct"] == 0.0 and m1["fator_duracao"] == 1.0 and m1["horas_confirmadas"] == 0.0
    # ritmo: criada em 01/09, prazo 15/12 (15 semanas); 27 dias decorridos ≈ 3,86 sem → 25,7%
    assert m1["ritmo_esperado_pct"] == pytest.approx(25.7, abs=0.1)
    assert m1["delta"] == pytest.approx(-25.7, abs=0.1)
    assert prf.gravar(dados, perfil) == dados / "perfil.json"
    assert prf.carregar(dados) == perfil
    assert prf.janelas_confiaveis(perfil) == {}


def test_progresso_confirmadas_presumidas_e_declarado(tmp_path, agora_fixo):
    dados = pasta(tmp_path)
    r = reg.vazio()
    # M01: custo total 4 × 12 = 48 h. 6 h confirmadas (12,5%), 2 h presumidas recentes, 4 h presumidas antigas.
    reg.registrar_feita(
        r, "M01", "D-2026-09-26-01", 1.0, "confirmado", duracao_real_h=2.0, ts=AGORA - timedelta(days=2)
    )
    reg.registrar_feita(r, "M01", "D-2026-09-26-02", 4.0, "confirmado", ts=AGORA - timedelta(days=10))
    reg.registrar_feita(r, "M01", "D-2026-09-26-03", 2.0, "presumido", ts=AGORA - timedelta(days=3))
    reg.registrar_feita(r, "M01", "D-2026-09-26-04", 4.0, "presumido", ts=AGORA - timedelta(days=20))
    reg.salvar(r, dados)
    m1 = prf.calcular(dados, AGORA)["metas"]["M01"]
    assert m1["horas_confirmadas"] == 6.0 and m1["progresso_pct"] == 12.5
    assert m1["progresso_presumido_pct"] == pytest.approx(4.2, abs=0.05)  # 2/48
    assert m1["horas_presumidas_nao_contadas"] == 4.0
    assert m1["h_semana_real"] == 1.5  # 6 h nas últimas 4 semanas
    # declarado prevalece sobre esforço menor; esforço maior prevalece sobre declarado antigo
    reg.declarar_progresso(r, "M01", 50, ts=AGORA - timedelta(days=1))
    reg.salvar(r, dados)
    assert prf.calcular(dados, AGORA)["metas"]["M01"]["progresso_pct"] == 50.0
    reg.declarar_progresso(r, "M01", 5, ts=AGORA)
    reg.salvar(r, dados)
    assert prf.calcular(dados, AGORA)["metas"]["M01"]["progresso_pct"] == 12.5
    # meta vencida: ritmo travado em 100
    (dados / "metas" / "M02.md").write_text(
        (dados / "metas" / "M02.md").read_text(encoding="utf-8").replace("prazo: 2027-03-01", "prazo: 2026-09-10"),
        encoding="utf-8",
    )
    assert prf.calcular(dados, AGORA)["metas"]["M02"]["ritmo_esperado_pct"] == 100.0


def test_janelas_fator_duracao_e_presumidas_nao_pesam(tmp_path, agora_fixo):
    dados = pasta(tmp_path)
    escrever_dia(dados, "2026-09-21", [("%02d" % i, "2026-09-21T%02d:00:00-03:00" % (8 + i), 1.0) for i in range(1, 8)])
    escrever_dia(dados, "2026-09-22", [("%02d" % i, "2026-09-22T09:00:00-03:00", 1.5) for i in range(1, 11)])
    r = reg.vazio()
    # seg-manha: 08h..11h → 4 blocos (i=1..3 manhã: 9,10,11h; i=4 12h tarde). Confirmadas 2 feitas + 2 não feitas.
    for i, (estado, origem) in enumerate(
        [
            ("feita", "confirmado"),
            ("feita", "confirmado"),
            ("apagada", "inferido"),
            ("nao_feita", "confirmado"),
            ("feita", "confirmado"),
            ("movida", "inferido"),
            ("feita", "presumido"),
        ],
        start=1,
    ):
        task = "D-2026-09-21-%02d" % i
        reg.registrar_checkin(
            r,
            task,
            estado,
            origem,
            ts=AGORA,
            duracao_real_h=1.25 if estado == "feita" and origem == "confirmado" else None,
        )
        if estado == "feita":
            reg.registrar_feita(
                r, "M01", task, 1.0, origem, duracao_real_h=1.25 if origem == "confirmado" else None, ts=AGORA
            )
    # 10 presumidas na terça de manhã: não criam célula nem mudam pesos
    for i in range(1, 11):
        task = "D-2026-09-22-%02d" % i
        reg.registrar_checkin(r, task, "feita", "presumido", ts=AGORA)
        reg.registrar_feita(r, "M01", task, 1.5, "presumido", ts=AGORA)
    reg.salvar(r, dados)
    perfil = prf.calcular(dados, AGORA)
    assert perfil["n_confirmadas"] == 3
    assert perfil["janelas"] == {
        "seg-manha": {"taxa_conclusao": 0.67, "n": 3},  # 9h feita, 10h feita, 11h apagada
        "seg-tarde": {"taxa_conclusao": 0.33, "n": 3},  # 12h nao_feita, 13h feita, 14h movida
    }
    assert "ter-manha" not in perfil["janelas"]
    assert prf.janelas_confiaveis(perfil) == {}  # n < 5
    m1 = perfil["metas"]["M01"]
    assert m1["fator_duracao"] == 1.0  # só 3 durações reais: abaixo do mínimo de 5
    assert m1["progresso_presumido_pct"] == pytest.approx(100 * 16 / 48, abs=0.1)
    assert perfil["preferencias"]["bloco_medio_h"] == 1.0
    assert perfil["preferencias"]["taxa_por_duracao"] == {"ate_1h": 0.5}
    # com 5 durações reais o fator entra (mediana)
    for i in range(1, 6):
        task = "D-2026-09-21-%02d" % i
        reg.registrar_checkin(
            r, task, "feita", "confirmado", ts=AGORA, duracao_real_h=[0.5, 1.0, 1.5, 2.0, 0.75][i - 1]
        )
        reg.registrar_feita(
            r, "M01", task, 1.0, "confirmado", duracao_real_h=[0.5, 1.0, 1.5, 2.0, 0.75][i - 1], ts=AGORA
        )
    reg.salvar(r, dados)
    perfil = prf.calcular(dados, AGORA)
    assert perfil["metas"]["M01"]["fator_duracao"] == 1.0  # mediana de 0.5,1,1.5,2,0.75
    assert perfil["janelas"]["seg-manha"] == {"taxa_conclusao": 1.0, "n": 3}
    assert perfil["janelas"]["seg-tarde"] == {"taxa_conclusao": 0.67, "n": 3}
    assert perfil["n_confirmadas"] == 5
    assert schema.validar_registro("perfil", perfil) == []
    assert json.loads(json.dumps(perfil)) == perfil


def test_cache_de_blocos_por_conteudo_nao_serve_versao_velha(tmp_path):
    """P3 (análise de 13/09): o cache poupa o parse, nunca a leitura; mesma data e mesmo tamanho não enganam."""
    import os
    import shutil
    from pathlib import Path

    from goalpacer import perfil

    destino = tmp_path / "dados"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "diario" / "dados", destino)
    arquivo = destino / "dias" / "2026-09-26.md"
    antes = perfil.ler_blocos(destino)
    assert antes["D-2026-09-26-01"]["duracao_h"] == 1.0
    texto = arquivo.read_text(encoding="utf-8")
    estado = arquivo.stat()
    arquivo.write_text(texto.replace("- duracao_h: 1\n", "- duracao_h: 2\n", 1), encoding="utf-8")  # mesmo tamanho
    os.utime(arquivo, ns=(estado.st_atime_ns, estado.st_mtime_ns))  # e mesma data
    depois = perfil.ler_blocos(destino)
    assert depois["D-2026-09-26-01"]["duracao_h"] == 2.0
    depois["D-2026-09-26-01"]["estado"] = "mexido"
    assert perfil.ler_blocos(destino)["D-2026-09-26-01"].get("estado") != "mexido"  # cada chamada recebe cópias
