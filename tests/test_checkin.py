"""E2E offline do check-in: inferir (fixtures de Calendar cruas → projeção → inferência → registro) e confirmar."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import checkin
import validar
from goalpacer import calendar_ops, perfil as prf, registro as reg
from goalpacer.base import EXIT_IO, EXIT_OK, EXIT_VALIDACAO

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "checkin"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "checkin.py"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
AGORA_ARGS = ["--agora", "2026-09-28T07:00:00-03:00", "--tz", "America/Sao_Paulo"]
METAS = "metas-fixture@group.calendar.google.com"
PRIMARIO = "pessoa@exemplo.test"


def pasta(tmp_path: Path) -> Path:
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    return destino


def test_ler_eventos_offline_por_calendario(monkeypatch):
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    inicio, fim = datetime(2026, 9, 20, tzinfo=TZ), datetime(2026, 10, 5, tzinfo=TZ)
    metas = calendar_ops.ler_eventos(METAS, inicio, fim, calendar_id_metas=METAS, modo_offline=True)
    assert [e["id"] for e in metas] == ["evt-01", "evt-02", "evt-03", "evt-07", "evt-terceiro-no-metas"]
    assert (
        metas[0]["summary"] == "[GP] Intocado e vencido" and metas[0]["gp_key"] == "gp:D-2026-09-26-01/inst-fixture-01"
    )
    primario = calendar_ops.ler_eventos(
        PRIMARIO, inicio, fim, calendar_id_metas=METAS, modo_offline=True, full_text="[GP]"
    )
    assert [e["id"] for e in primario] == ["evt-05-no-primario", "evt-gp-de-terceiro"]
    assert primario[0]["summary"] is None and primario[0]["gp_key"] == "gp:D-2026-09-26-05/inst-fixture-01"
    assert primario[1]["gp_key"] == "gp:D-2026-09-26-04/outra-instalacao" and primario[1]["description"] is None
    assert "Ignore" not in json.dumps(primario)
    assert (
        calendar_ops.ler_eventos(
            "outro@group.calendar.google.com", inicio, fim, calendar_id_metas=METAS, modo_offline=True
        )
        == []
    )


def test_inferir_e2e(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    saida = checkin.inferir(dados, modo_offline=True, agora=AGORA)
    estados = {a["task_id"]: (a["estado"], a["origem"]) for a in saida["aplicadas"]}
    assert estados == {
        "D-2026-09-26-01": ("feita", "presumido"),
        "D-2026-09-26-02": ("movida", "inferido"),
        "D-2026-09-26-03": ("reagendada", "inferido"),
        "D-2026-09-26-04": ("apagada", "inferido"),
        "D-2026-09-26-05": ("movida", "inferido"),
        "D-2026-09-28-01": ("sem_sinal", "inferido"),
    }
    movido = next(a for a in saida["aplicadas"] if a["task_id"] == "D-2026-09-26-05")
    assert movido["calendar_id"] == PRIMARIO and movido["calendar_event_id"] == "evt-05-no-primario"
    assert saida["resumo"] == "1 confirmada · 1 feita? · 2 movidas · 1 reagendada · 1 apagada"
    assert [p["task_id"] for p in saida["presumidas"]] == ["D-2026-09-26-01"]
    assert saida["presumidas"][0]["inicio"] == "2026-09-26T09:00-03:00"
    assert sorted(i["task_id"] for i in saida["inferidas"]) == [
        "D-2026-09-26-02",
        "D-2026-09-26-03",
        "D-2026-09-26-04",
        "D-2026-09-26-05",
    ]
    assert [s["task_id"] for s in saida["sem_sinal"]] == ["D-2026-09-28-01"]
    assert saida["segunda"] is True and saida["nota_sugerida"] is None
    # registro gravado; o confirmado da fixture (06) não aparece nas inferências
    registro = reg.carregar(dados)
    assert "D-2026-09-26-06" not in registro["checkins"]
    assert registro["checkins"]["D-2026-09-26-01"]["origem"] == "presumido"
    assert [f["task_id"] for f in registro["feitas"]["M01"]] == ["D-2026-09-26-01"]
    assert (dados / "perfil.json").exists()
    assert prf.carregar(dados)["metas"]["M01"]["progresso_presumido_pct"] > 0
    assert validar.validar_grafo(dados).codigo == EXIT_OK
    # segunda execução: os blocos movidos ganharam a janela nova; intocados e vencidos viram feita?
    # (02 às 15h de sábado, 05 no primário às 16h); o reagendado para terça continua reagendado.
    saida2 = checkin.inferir(dados, modo_offline=True, agora=AGORA)
    assert saida2["resumo"] == "1 confirmada · 3 feita? · 1 reagendada · 1 apagada"
    registro2 = reg.carregar(dados)
    assert registro2["checkins"]["D-2026-09-26-02"]["origem"] == "presumido"
    assert registro2["checkins"]["D-2026-09-26-02"]["inicio"] == "2026-09-26T15:00:00-03:00"  # janela nova preservada
    assert registro2["checkins"]["D-2026-09-26-03"]["estado"] == "reagendada"
    assert registro2["checkins"]["D-2026-09-26-05"]["calendar_id"] == PRIMARIO
    # terceira execução: estável
    checkin.inferir(dados, modo_offline=True, agora=AGORA)
    assert reg.carregar(dados)["checkins"] == registro2["checkins"]


def test_confirmar_e2e(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    checkin.inferir(dados, modo_offline=True, agora=AGORA)
    respostas = {
        "feitas": [{"task_id": "D-2026-09-26-01", "duracao_real_h": "1,5"}, {"task_id": "D-2026-09-26-02"}],
        "nao_feitas": ["D-2026-09-26-05"],
        "progresso": {"M01": 30},
        "nota": {"texto": "sem blocos sábado à tarde", "aceita": True},
    }
    saida = checkin.confirmar(dados, respostas, agora=AGORA)
    assert saida["mudancas"] == [
        "D-2026-09-26-01: feita confirmada (1.5 h)",
        "D-2026-09-26-02: feita confirmada",
        "D-2026-09-26-05: não feita",
        "M01: progresso declarado 30%",
        "perfil.md: nota registrada",
    ]
    registro = reg.carregar(dados)
    assert registro["checkins"]["D-2026-09-26-01"] == {
        "estado": "feita",
        "origem": "confirmado",
        "ts": "2026-09-28T07:00:00-03:00",
        "duracao_real_h": 1.5,
        "calendar_id": METAS,
        "calendar_event_id": "evt-01",
    }
    assert registro["checkins"]["D-2026-09-26-05"]["estado"] == "nao_feita"
    feitas = {f["task_id"]: f for f in registro["feitas"]["M01"]}
    assert feitas["D-2026-09-26-01"]["origem"] == "confirmado" and feitas["D-2026-09-26-01"]["duracao_real_h"] == 1.5
    assert "D-2026-09-26-05" not in feitas
    assert registro["progresso"]["M01"][0]["declarado_pct"] == 30.0
    assert "- 2026-09-28: sem blocos sábado à tarde" in (dados / "perfil.md").read_text(encoding="utf-8")
    assert (
        saida["n_confirmadas"] == 2 and saida["perfil"]["M01"]["progresso_pct"] == 30.0
    )  # o bloco 06 confirmado só em dias/ não está no registro
    # inferir de novo não desfaz o confirmado
    checkin.inferir(dados, modo_offline=True, agora=AGORA)
    assert reg.carregar(dados)["checkins"]["D-2026-09-26-01"]["origem"] == "confirmado"
    # nota recusada
    saida = checkin.confirmar(dados, {"nota": {"texto": "sem blocos antes das 9h", "aceita": False}}, agora=AGORA)
    assert saida["mudancas"] == ["nota recusada (não volta por 30 dias)"]
    assert reg.nota_recusada_recente(reg.carregar(dados), "sem blocos antes das 9h", AGORA)
    # respostas inválidas não gravam nada
    antes = (dados / "registro.json").read_text(encoding="utf-8")
    import pytest

    with pytest.raises(Exception) as info:
        checkin.confirmar(dados, {"feitas": [{"task_id": "D-2026-09-26-99"}], "progresso": {"M01": 150}}, agora=AGORA)
    assert "não existe" in str(info.value) and "0 a 100" in str(info.value)
    assert (dados / "registro.json").read_text(encoding="utf-8") == antes


def test_nota_sugerida_pela_pior_celula(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(tmp_path / "sem-fixtures"))
    perfil = {
        "janelas": {
            "seg-manha": {"taxa_conclusao": 0.2, "n": 6},
            "ter-tarde": {"taxa_conclusao": 0.1, "n": 2},
            "qua-noite": {"taxa_conclusao": 0.3, "n": 5},
        }
    }
    nota = checkin._nota_sugerida(perfil, reg.vazio(), AGORA)
    assert nota["celula"] == "seg-manha" and nota["texto"] == "sem blocos segunda de manhã"
    assert "taxa 20%" in nota["pergunta"] and "6 observações" in nota["pergunta"]
    r = reg.vazio()
    reg.recusar_nota(r, "sem blocos segunda de manhã", ts=AGORA)
    assert checkin._nota_sugerida(perfil, r, AGORA)["celula"] == "qua-noite"
    assert checkin._nota_sugerida(None, r, AGORA) is None


def executar(*args: str, env: dict) -> subprocess.CompletedProcess:
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    ambiente.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=ambiente
    )


def test_cli(tmp_path):
    dados = pasta(tmp_path)
    env = {"GP_OFFLINE_DIR": str(FIXTURES / "offline")}
    proc = executar("--json", "--dados", str(dados), *AGORA_ARGS, "--offline", "inferir", env=env)
    assert proc.returncode == EXIT_OK, proc.stderr
    saida = json.loads(proc.stdout)
    assert saida["resumo"] == "1 confirmada · 1 feita? · 2 movidas · 1 reagendada · 1 apagada"
    assert not (dados / ".lock").exists()
    proc = executar("--dados", str(dados), *AGORA_ARGS, "--offline", "inferir", env=env)
    assert proc.returncode == EXIT_OK and proc.stdout.startswith(
        "Check-in rápido. Desde a última vez: 1 confirmada · 3 feita?"
    )
    respostas = tmp_path / "r.json"
    respostas.write_text(json.dumps({"feitas": [{"task_id": "D-2026-09-26-01"}]}), encoding="utf-8")
    proc = executar("--dados", str(dados), *AGORA_ARGS, "confirmar", "--respostas", str(respostas), env=env)
    assert (
        proc.returncode == EXIT_OK
        and "D-2026-09-26-01: feita confirmada" in proc.stdout
        and "O dia é refeito" in proc.stdout
    )
    # lock preso: exit 4 com a mensagem do copy
    trava = reg.lock(dados)
    proc = executar("--json", "--dados", str(dados), *AGORA_ARGS, "--offline", "inferir", env=env)
    assert proc.returncode == EXIT_IO and "job rodando" in proc.stderr
    trava.liberar()
    # sem onboarding
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    proc = executar("--dados", str(vazio), *AGORA_ARGS, "--offline", "inferir", env=env)
    assert proc.returncode == 2 and "onboarding" in proc.stderr
    proc = executar(*AGORA_ARGS, env=env)
    assert proc.returncode == EXIT_VALIDACAO


def test_confirmar_decisoes(tmp_path, agora_fixo, monkeypatch):
    """Decisão pendente respondida no check-in muda a meta por metas.aplicar_decisao; inválida não grava nada."""
    import pytest

    from goalpacer import frontmatter, schema
    from goalpacer.base import GpErro

    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    saida = checkin.confirmar(
        dados, {"decisoes": {"M02": {"saida": "adiar", "prazo": "2027-04-12"}, "M01": {"saida": "manter"}}}, agora=AGORA
    )
    bruto, _ = frontmatter.ler_arquivo(dados / "metas" / "M02.md")
    assert frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])[0]["prazo"].isoformat() == "2027-04-12"
    assert any("M02" in m and "2027-04-12" in m for m in saida["mudancas"])
    metas_antes = (dados / "metas" / "M01.md").read_text(encoding="utf-8")
    registro_antes = (
        (dados / "registro.json").read_text(encoding="utf-8") if (dados / "registro.json").exists() else None
    )
    perfil_md = dados / "perfil.md"
    perfil_antes = perfil_md.read_text(encoding="utf-8") if perfil_md.exists() else None
    with pytest.raises(GpErro) as info:
        checkin.confirmar(
            dados,
            {
                "decisoes": {"M01": {"saida": "sumir"}, "M07": {"saida": "manter"}},
                "nota": {"texto": "x", "aceita": True},
            },
            agora=AGORA,
        )
    assert "M01" in info.value.mensagem and "M07" in info.value.mensagem
    assert (dados / "metas" / "M01.md").read_text(encoding="utf-8") == metas_antes
    assert (
        (dados / "registro.json").read_text(encoding="utf-8") if (dados / "registro.json").exists() else None
    ) == registro_antes
    assert (perfil_md.read_text(encoding="utf-8") if perfil_md.exists() else None) == perfil_antes
