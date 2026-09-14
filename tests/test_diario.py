"""E2E offline do diário: gerar duas vezes = zero ops na segunda e dias/ idêntico (critério 12)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import diario
import validar
from goalpacer import frontmatter, registro as reg, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "diario"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "diario.py"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
DIA = date(2026, 9, 28)
AGORA_ARGS = ["--agora", "2026-09-28T07:00:00-03:00", "--tz", "America/Sao_Paulo"]
METAS = "metas-fixture@group.calendar.google.com"


def pasta(tmp_path: Path) -> Path:
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    return destino


def sem_run_id(texto: str) -> str:
    return re.sub(r"^run_id: .*$", "run_id: X", texto, flags=re.MULTILINE)


def test_gerar_duas_vezes_zero_ops(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    saida = diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="run-1")
    assert saida["arquivo"] == "dias/2026-09-28.md" and saida["motivo"] is None
    # 2 blocos novos (M01 e M02); o bloco da meta arquivada virou cancelada e seu evento é apagado;
    # o órfão de ontem e a duplicata são apagados; o evento de outra instalação fica.
    assert saida["blocos"] == ["D-2026-09-28-02", "D-2026-09-28-03"]
    assert saida["fixos"] == ["D-2026-09-28-01"]
    assert saida["ops"] == {"create": 2, "update": 0, "delete": 3, "erro": 0}
    assert saida["janelas"] >= 1
    texto = (dados / "dias" / "2026-09-28.md").read_text(encoding="utf-8")
    fm, corpo = frontmatter.separar(texto)
    assert frontmatter.parse(fm)["run_id"] == "run-1"
    blocos = {b["id"]: b for b in frontmatter.parse_blocos(corpo)}
    assert blocos["D-2026-09-28-01"]["estado"] == "cancelada" and blocos["D-2026-09-28-01"]["origem"] == "prazo"
    m01 = blocos["D-2026-09-28-02"]
    assert m01["meta"] == "M01" and m01["titulo"] == "Terminar o curso de estatística" and m01["estado"] == "planejada"
    assert m01["inicio"].isoformat() == "2026-09-28T08:00:00-03:00" and m01["duracao_h"] == 0.75
    assert m01["calendar_event_id"] == "off-D-2026-09-28-02" and m01["calendar_id"] == METAS
    assert m01["porque"] == "M1 pede 4h nesta semana; janela livre das 08h" and len(m01["porque"]) <= 90
    assert "efeito" not in m01  # sem objetivo cadastrado não há objetivo para mover
    m02 = blocos["D-2026-09-28-03"]
    assert m02["meta"] == "M02" and m02["inicio"].isoformat() == "2026-09-28T08:45:00-03:00" and m02["duracao_h"] == 0.5
    assert (
        "## Progresso" in corpo
        and "- M1 Terminar o curso de estatística: " in corpo
        and "%" not in corpo.split("## Progresso")[1].split("##")[0]
    )
    assert "pauta de terceiro" not in texto and "Reunião" not in texto
    assert validar.validar_grafo(dados).codigo == EXIT_OK
    cache = json.loads((dados / "cache" / "calendar-diario-2026-09-28.json").read_text(encoding="utf-8"))
    assert schema.validar_registro("cache_calendar", cache) == []
    assert all(e["summary"] is None for e in cache["eventos"] if e["calendar_id"] != METAS)
    ops = json.loads((dados / "cache" / "ops-run-1.json").read_text(encoding="utf-8"))
    assert schema.validar_registro("ops", ops) == [] and all(op["status"] == "ok" for op in ops["ops"])
    assert validar.validar_ops(dados / "cache" / "ops-run-1.json", False, dados).codigo == EXIT_OK
    registro = reg.carregar(dados)
    assert registro["geracoes"]["run-1"]["modo"] == "diario" and registro["geracoes"]["run-1"]["email"] == "nao_enviado"
    assert (
        registro["checkins"]["D-2026-09-28-01"]
        == {
            "estado": "cancelada",
            "origem": "prazo",
            "ts": "2026-09-28T07:00:00-03:00",
            "calendar_id": METAS,
            "calendar_event_id": "evt-28-01",
        }
        or registro["checkins"]["D-2026-09-28-01"]["estado"] == "cancelada"
    )
    # Segunda execução: mesmos ids, zero ops, arquivo idêntico salvo run_id.
    saida2 = diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="run-2")
    assert saida2["blocos"] == saida["blocos"]
    assert saida2["ops"] == {"create": 0, "update": 0, "delete": 0, "erro": 0}
    texto2 = (dados / "dias" / "2026-09-28.md").read_text(encoding="utf-8")
    assert sem_run_id(texto2) == sem_run_id(texto)
    assert validar.validar_grafo(dados).codigo == EXIT_OK


def test_sem_janela_e_sem_inferir(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    # domingo sem horário útil: sem janela, sem blocos, motivo no front-matter, aviso no corpo
    domingo = date(2026, 10, 4)
    saida = diario.gerar(dados, dia=domingo, modo_offline=True, sem_inferir=True, agora=AGORA, run_id="run-dom")
    assert saida["blocos"] == [] and saida["motivo"] == "sem_janela" and saida["ops"]["create"] == 0
    texto = (dados / "dias" / "2026-10-04.md").read_text(encoding="utf-8")
    assert "motivo: sem_janela" in texto and "Hoje sem janela livre" in texto and "(sem blocos)" in texto
    assert validar.validar_grafo(dados).codigo == EXIT_OK


def test_gerar_recusa_sem_metas_e_sem_calendario_metas(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(tmp_path / "off"))
    (tmp_path / "off").mkdir()
    (tmp_path / "off" / "list_calendars.json").write_text(
        json.dumps({"calendars": [{"id": "pessoa@exemplo.test", "summary": "x"}]}), encoding="utf-8"
    )
    with pytest.raises(GpErro) as info:
        diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=True, agora=AGORA)
    assert info.value.codigo == EXIT_VALIDACAO and "Metas" in info.value.mensagem
    shutil.rmtree(dados / "metas")
    with pytest.raises(GpErro) as info:
        diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=True, agora=AGORA)
    assert info.value.codigo == EXIT_ESTADO and "onboarding" in info.value.mensagem


def test_desinstalar(tmp_path, agora_fixo, monkeypatch):
    dados = pasta(tmp_path)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    saida = diario.desinstalar(dados, modo_offline=True, confirmar=False, agora=AGORA)
    assert (
        sorted(saida["blocos"]) == ["D-2026-09-27-05", "D-2026-09-27-05", "D-2026-09-28-01"]
        and saida["apagados"] is False
    )
    assert not list((dados / "cache").glob("ops-desinstalar-*.json")) if (dados / "cache").exists() else True
    saida = diario.desinstalar(dados, modo_offline=True, confirmar=True, agora=AGORA)
    assert saida["apagados"] is True and saida["erros"] == []
    assert list((dados / "cache").glob("ops-desinstalar-*.json"))


def executar(*args: str, env: dict) -> subprocess.CompletedProcess:
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    ambiente.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=ambiente
    )


def test_cli(tmp_path):
    dados = pasta(tmp_path)
    env = {"GP_OFFLINE_DIR": str(FIXTURES / "offline")}
    proc = executar(
        "--json",
        "--dados",
        str(dados),
        *AGORA_ARGS,
        "--offline",
        "--data",
        "2026-09-28",
        "diario" if False else "--sem-inferir",
        env=env,
    )
    assert proc.returncode == EXIT_OK, proc.stderr
    saida = json.loads(proc.stdout)
    assert saida["arquivo"] == "dias/2026-09-28.md" and saida["ops"]["create"] == 2
    assert not (dados / ".lock").exists()
    proc = executar("--dados", str(dados), *AGORA_ARGS, "--offline", "--data", "2026-09-28", env=env)
    assert proc.returncode == EXIT_OK and proc.stdout.startswith("dias/2026-09-28.md: 2 blocos hoje, para M1, M2.")
    proc = executar("--dados", str(dados), *AGORA_ARGS, "--offline", "--desinstalar", env=env)
    assert proc.returncode == EXIT_OK and "encontrados" in proc.stdout
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    proc = executar("--json", "--dados", str(vazio), *AGORA_ARGS, "--offline", env=env)
    assert proc.returncode == EXIT_ESTADO and "onboarding" in proc.stderr


def _sem_conectores(dados: Path, *, email: str = "") -> None:
    """O contexto de quem não conectou nada: sem calendário Metas, sem primário e, sem ``email``, sem Gmail."""
    path = dados / "contexto.md"
    texto = path.read_text(encoding="utf-8")
    for chave in ("calendar_id_metas", "calendar_id_primario", "calendarios_lidos", "email_proprio", "fontes_ativas"):
        texto = re.sub(r"^%s: .*\n" % chave, "", texto, flags=re.MULTILINE)
    if email:
        texto = texto.replace("---\n", "---\nemail_proprio: %s\n" % email, 1)
    path.write_text(texto, encoding="utf-8")


def test_sem_conectores_o_dia_sai_do_horario_util_sem_agenda_nem_email(tmp_path, agora_fixo, monkeypatch):
    """Pedido do usuário (14/09): o app funciona sem conector nenhum. Os blocos saem do horário útil, ficam só no
    app (sem op no Calendar, sem cache da agenda) e nenhum email sai, nem com --email."""
    dados = pasta(tmp_path)
    _sem_conectores(dados)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(tmp_path / "sem-respostas"))  # qualquer chamada de conector falharia
    assert validar.validar_grafo(dados).codigo == EXIT_OK
    saida = diario.gerar(
        dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="run-sc", enviar_email=True
    )
    assert saida["blocos"] and saida["ops"] == {"create": 0, "update": 0, "delete": 0, "erro": 0}
    assert saida["email"] == {"status": "nao_enviado"}
    assert not list((dados / "cache").glob("calendar-*.json")) and not list((dados / "cache").glob("ops-*.json"))
    texto = (dados / "dias" / "2026-09-28.md").read_text(encoding="utf-8")
    blocos = frontmatter.parse_blocos(frontmatter.separar(texto)[1])
    novos = [b for b in blocos if b["id"] in saida["blocos"]]
    assert novos[0]["inicio"].isoformat() == "2026-09-28T08:00:00-03:00" and "calendar_event_id" not in novos[0]
    assert validar.validar_grafo(dados).codigo == EXIT_OK


def test_conectores_coerentes_no_contexto(tmp_path):
    dados = pasta(tmp_path)
    path = dados / "contexto.md"
    original = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"^calendar_id_primario: .*\n", "", original, flags=re.MULTILINE), encoding="utf-8")
    assert any("calendar_id_primario: vazio" in p for p in validar.validar_grafo(dados).erros)
    path.write_text(re.sub(r"^email_proprio: .*\n", "", original, flags=re.MULTILINE), encoding="utf-8")
    assert any("email_proprio: vazio (a fonte gmail precisa dele)" in p for p in validar.validar_grafo(dados).erros)
