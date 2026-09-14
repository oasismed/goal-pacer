"""status.py (T12/T32): painel em 80 colunas com snapshot, estados de silêncio e nunca rodou, e --doctor com stubs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import diario
import mensal
import status
from goalpacer import registro as reg, tom
from goalpacer.base import GpErro

RAIZ_REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = RAIZ_REPO / "scripts" / "status.py"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA_JOB = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
AGORA = datetime(2026, 9, 29, 9, 0, tzinfo=TZ)
SNAPSHOT = FIXTURES / "status" / "esperado.txt"


@pytest.fixture
def dados(tmp_path, agora_fixo, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "mensal" / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "mensal" / "offline"))
    return destino


def gerar_mes_e_dia(dados: Path) -> None:
    mensal.gerar(dados, modo_offline=True, agora=AGORA_JOB, run_id="mensal-1")
    diario.gerar(dados, dia=AGORA_JOB.date(), modo_offline=True, sem_inferir=False, agora=AGORA_JOB, run_id="diario-1")


def test_snapshot_do_status(dados):
    gerar_mes_e_dia(dados)
    texto = status.render_status(status.coletar(dados, AGORA))
    if os.environ.get("GP_ATUALIZAR_SNAPSHOT") == "1":
        SNAPSHOT.write_text(texto, encoding="utf-8")
    assert texto == SNAPSHOT.read_text(encoding="utf-8")
    assert all(len(linha) <= 80 for linha in texto.split("\n"))
    assert tom.violacoes(texto) == []
    ordem = [
        texto.index(t)
        for t in (
            "Pendências",
            "Como vão as metas",
            "Cobertura de outubro/2026",
            "Perfil",
            "Evidências",
            "Últimas execuções",
        )
    ]
    assert ordem == sorted(ordem)


def test_status_nunca_rodou_e_silencio(dados):
    modelo = status.coletar(dados, AGORA)
    assert modelo["aviso"] == "Nenhum diário por aqui. Próximo: qua 30/09 07:00. Para ver agora: /goal-pacer diario"
    assert modelo["cobertura"]["linhas"] == ["Sem plano de outubro/2026. Para gerar: /goal-pacer mensal"]
    gerar_mes_e_dia(dados)
    sabado = datetime(2026, 10, 3, 10, 0, tzinfo=TZ)
    modelo = status.coletar(dados, sabado)
    assert modelo["aviso"].startswith("O último diário rodou há 5 dias (seg 28/09 07:00).")
    assert tom.violacoes(status.render_status(modelo)) == []
    assert status.proximo_job(datetime(2026, 10, 3, 8, 0, tzinfo=TZ)) == datetime(2026, 10, 5, 7, 0, tzinfo=TZ)
    assert status.proximo_job(datetime(2026, 10, 5, 6, 59, tzinfo=TZ)) == datetime(2026, 10, 5, 7, 0, tzinfo=TZ)


def test_aviso_de_silencio_para_modos_interativos(dados):
    assert status.aviso_de_silencio(dados, AGORA) is None  # nenhum diário: sem aviso
    gerar_mes_e_dia(dados)
    assert status.aviso_de_silencio(dados, AGORA) is None
    aviso = status.aviso_de_silencio(dados, datetime(2026, 10, 1, 9, 0, tzinfo=TZ))
    assert aviso.startswith("O último diário rodou há 3 dias") and tom.violacoes(aviso) == []


def test_pendencias_presumidas_e_job_com_erro(dados):
    gerar_mes_e_dia(dados)
    registro = reg.carregar(dados)
    reg.registrar_checkin(registro, "D-2026-09-28-01", "feita", "presumido", ts=AGORA)
    reg.registrar_geracao(
        registro,
        {
            "run_id": "job-diario-20260929-070000",
            "modo": "job:diario",
            "data": "2026-09-29",
            "ts": "2026-09-29T07:05:00-03:00",
            "exit_code": 3,
            "classe": "EscopoInsuficiente",
            "chave_runbook": "escopo-insuficiente",
        },
    )
    reg.salvar(registro, dados)
    modelo = status.coletar(dados, AGORA)
    assert any(p.startswith('1 bloco(s) "feita?"') and "D-2026-09-28-01" in p for p in modelo["pendencias"])
    assert any(p.startswith("Último job:") for p in modelo["pendencias"])
    assert any("EscopoInsuficiente" in e for e in modelo["execucoes"])
    assert tom.violacoes(status.render_status(modelo)) == []


def test_status_neutraliza_escapes_de_terminal():
    linhas = status.embrulhar("resumo \x1b[2J\x1b]0;titulo\x07 limpo")
    assert all("\x1b" not in l and "\x07" not in l for l in linhas) and "limpo" in linhas[0]


def test_declarar_progresso(dados):
    gerar_mes_e_dia(dados)
    assert status.declarar(dados, ["M01=40"], AGORA) == ["M1: progresso declarado 40%"]
    assert reg.ultimo_progresso_declarado(reg.carregar(dados), "M01") == 40.0
    assert any(linha.startswith("M1 ") and "%" not in linha for linha in status.coletar(dados, AGORA)["progresso"])
    with pytest.raises(GpErro):
        status.declarar(dados, ["M01=140", "M09=10"], AGORA)


def test_decisoes_pendentes_do_checkin(dados):
    import checkin
    from goalpacer import balanco, metas

    gerar_mes_e_dia(dados)
    pendentes = checkin.decisoes_pendentes(dados, AGORA)
    assert [(d["meta"], d["sugerida"], d["prazo"]) for d in pendentes] == [
        ("M01", "reduzir", "2026-12-15"),
        ("M02", "renegociar", "2027-03-01"),
    ]
    assert pendentes[1]["prazo_externo"] is True and pendentes[0]["texto"].startswith("Com as janelas até 31/10")
    plano = balanco.ler_plano((dados / "planos" / "2026-10.md").read_text(encoding="utf-8"))
    assert plano["mes"] == {"oferta": "46,8", "demanda": "70", "cobertura": "67%"}
    assert plano["metas"]["M01"] == {"cobertura": "80%", "decisao": "reduzir"}
    assert balanco.ler_plano("sem front-matter") == {
        "frontmatter": {},
        "mes": None,
        "metas": {},
        "decisoes": [],
        "semanas": [],
    }
    assert [(s["semana"], s["cobertura_pct"]) for s in plano["semanas"]] == [
        ("2026-W40", 62),
        ("2026-W41", 71),
        ("2026-W42", 57),
        ("2026-W43", 71),
        ("2026-W44", 71),
    ]
    metas.aplicar_decisao(dados, "M02", {"saida": "renegociar", "prazo": "2027-05-01"})
    assert checkin.decisoes_pendentes(dados, AGORA) == []


# --- doctor --------------------------------------------------------------------------------


def stub(pasta: Path, nome: str, corpo: str) -> Path:
    path = pasta / nome
    path.write_text("#!/bin/sh\n" + corpo + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    pasta = tmp_path / "stubs"
    pasta.mkdir()
    monkeypatch.setenv(
        "GP_LAUNCHCTL",
        str(
            stub(
                pasta,
                "launchctl",
                'printf -- "-\\t0\\tcom.goal-pacer.diario\\n-\\t0\\tcom.goal-pacer.mensal\\n123\\t0\\tcom.apple.x\\n"',
            )
        ),
    )
    monkeypatch.setenv("GP_XCODE_SELECT", str(stub(pasta, "xcode-select", "echo /Library/Developer/CommandLineTools")))
    monkeypatch.setenv("GP_CLAUDE_BIN", str(stub(pasta, "claude", 'echo "2.1.270 (Claude Code)"')))
    offline_dir = tmp_path / "offline-doctor"
    offline_dir.mkdir()
    shutil.copy(FIXTURES / "offline" / "mcp_list.txt", offline_dir / "mcp_list.txt")
    shutil.copy(FIXTURES / "mensal" / "offline" / "list_calendars.json", offline_dir / "list_calendars.json")
    monkeypatch.setenv("GP_OFFLINE_DIR", str(offline_dir))
    return pasta


def job_ok(dados: Path, ts: str = "2026-09-29T07:04:00-03:00") -> None:
    registro = reg.carregar(dados)
    reg.registrar_geracao(
        registro,
        {"run_id": "job-diario-20260929-070000", "modo": "job:diario", "data": ts[:10], "ts": ts, "exit_code": 0},
    )
    reg.salvar(registro, dados)


def lint_doctor(texto: str) -> list[str]:
    return tom.violacoes(texto.replace("FALHOU", ""))


def test_doctor_tudo_ok(dados, stubs):
    job_ok(dados)
    dados.chmod(0o700)
    itens = status.doctor(dados, AGORA, modo_offline=True, sondar=True)
    assert [i.ok for i in itens] == [True] * 8, itens
    texto = status.render_doctor(itens, AGORA)
    assert texto.count("\nOK ") == 8 and "Tudo certo nos 8 itens." in texto
    detalhes = {i.nome: i.detalhe for i in itens}
    assert detalhes["conectores"].endswith("escrita testada no Metas e no Gmail") and "2.1.270" in detalhes["claude"]
    assert all(len(linha) <= 80 for linha in texto.split("\n")) and lint_doctor(texto) == []


def test_doctor_falhas_com_o_que_fazer(dados, stubs, tmp_path, monkeypatch):
    offline_dir = tmp_path / "offline"
    offline_dir.mkdir()
    (offline_dir / "mcp_list.txt").write_text(
        "claude.ai Google Calendar: https://x.test/c - ✔ Connected\nclaude.ai Gmail: https://x.test/g - ✘ Needs authentication\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GP_OFFLINE_DIR", str(offline_dir))
    monkeypatch.setenv("GP_LAUNCHCTL", str(stub(stubs, "launchctl2", 'printf -- "-\\t0\\tcom.goal-pacer.diario\\n"')))
    monkeypatch.setenv("GP_XCODE_SELECT", str(stub(stubs, "xcode2", "exit 2")))
    monkeypatch.setenv("GP_CLAUDE_BIN", str(tmp_path / "nao-existe" / "claude"))
    morto = subprocess.Popen(["true"])
    morto.wait()
    (dados / ".lock").write_text(
        json.dumps({"pid": morto.pid, "criado_em": "2026-09-28T10:00:00+00:00"}), encoding="utf-8"
    )
    registro = reg.carregar(dados)
    reg.registrar_geracao(
        registro,
        {
            "run_id": "job-diario-20260926-070000",
            "modo": "job:diario",
            "data": "2026-09-26",
            "ts": "2026-09-26T07:10:00-03:00",
            "exit_code": 5,
            "classe": "SessionTimeout",
        },
    )
    reg.salvar(registro, dados)
    itens = {i.nome: i for i in status.doctor(dados, AGORA, modo_offline=True, sondar=False)}
    assert itens["pasta de dados"].ok
    assert not itens["lock da pasta de dados"].ok and "apague" in itens["lock da pasta de dados"].detalhe
    assert (
        not itens["jobs agendados"].ok
        and "com.goal-pacer.mensal fora do launchd: rode ./install.sh" in itens["jobs agendados"].detalhe
    )
    assert not itens["claude"].ok and "GP_CLAUDE_BIN" in itens["claude"].detalhe
    assert not itens["python3"].ok and "xcode-select --install" in itens["python3"].detalhe
    assert not itens["conectores"].ok and "Gmail fora de Connected" in itens["conectores"].detalhe
    assert not itens["último job"].ok and "SessionTimeout" in itens["último job"].detalhe
    assert (
        not itens["permissões"].ok
        and "aberta para outros usuários (0755): rode chmod 700" in itens["permissões"].detalhe
    )
    texto = status.render_doctor(list(itens.values()), AGORA)
    assert texto.count("\nFALHOU ") == 7 and lint_doctor(texto) == []
    assert all(len(linha) <= 80 for linha in texto.split("\n"))


def test_doctor_schema_e_metas_ausente(dados, stubs, monkeypatch):
    contexto = dados / "contexto.md"
    contexto.write_text(
        contexto.read_text(encoding="utf-8").replace(
            "calendar_id_metas: metas-fixture@group.calendar.google.com",
            "calendar_id_metas: sumiu@group.calendar.google.com",
        ),
        encoding="utf-8",
    )
    itens = {i.nome: i for i in status.doctor(dados, AGORA, modo_offline=True, sondar=False)}
    assert not itens["conectores"].ok and "sumiu@group.calendar.google.com" in itens["conectores"].detalhe
    contexto.write_text(
        contexto.read_text(encoding="utf-8").replace("schema_version: 1", "schema_version: 9"), encoding="utf-8"
    )
    item, _ = status.item_dados(dados)
    assert not item.ok and "install.sh --update" in item.detalhe
    item, _ = status.item_dados(dados.parent / "outra")
    assert not item.ok and "install.sh" in item.detalhe


def test_sonda_de_escrita_sem_escopo(dados, monkeypatch):
    contexto = diario._contexto(dados)
    chamadas = []

    def falso(tool, args, **_):
        chamadas.append(tool.rsplit("__", 1)[-1])
        if tool.endswith("create_draft"):
            from goalpacer import proxy

            raise proxy.ErroConector("Insufficient scope")
        return {"id": "evt-sonda"}

    monkeypatch.setattr(status, "_chamar", falso)
    problema = status.sondar_escrita(contexto, AGORA, modo_offline=False, servidores=None)
    assert chamadas == ["create_event", "delete_event", "create_draft"]
    assert problema.startswith("Gmail sem permissão de escrita")


def test_cli(dados, stubs, monkeypatch):
    offline_doctor = os.environ["GP_OFFLINE_DIR"]
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "mensal" / "offline"))
    gerar_mes_e_dia(dados)
    monkeypatch.setenv("GP_OFFLINE_DIR", offline_doctor)
    env = {k: v for k, v in os.environ.items() if k != "GP_AGORA"}
    env["GP_AGORA"] = "2026-09-29T09:00:00-03:00"
    env["NO_COLOR"] = "1"
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == SNAPSHOT.read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--doctor", "--offline", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    saida = json.loads(proc.stdout)
    assert proc.returncode == (0 if saida["ok"] else 3) and len(saida["itens"]) == 8
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--progresso", "M02=15"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert (
        proc.returncode == 0
        and proc.stdout.startswith("M2: progresso declarado 15%")
        and not (dados / ".lock").exists()
    )


def test_doctor_com_o_provedor_openai(dados, stubs, tmp_path, monkeypatch):
    monkeypatch.setenv("GP_PROVEDOR", "openai")
    monkeypatch.setenv("GP_CODEX_BIN", str(stub(stubs, "codex", 'echo "codex-cli 0.130.0"')))
    itens = {i.nome: i for i in status.doctor(dados, AGORA, modo_offline=True, sondar=False)}
    assert "claude" not in itens and itens["codex"].ok and "codex-cli 0.130.0" in itens["codex"].detalhe
    assert (
        not itens["conectores"].ok
        and "Calendar e Gmail pelo Codex entram depois do spike" in itens["conectores"].detalhe
    )
    monkeypatch.setenv("GP_CODEX_BIN", str(tmp_path / "nao-existe" / "codex"))
    item = status.item_provedor()
    assert not item.ok and "instale o Codex CLI e rode codex login" in item.detalhe
    texto = status.render_doctor(list(itens.values()), AGORA)
    assert lint_doctor(texto) == [] and all(len(linha) <= 80 for linha in texto.split("\n"))


def test_doctor_sem_conectores_nao_e_falha(dados, stubs, tmp_path, monkeypatch):
    """Conectores são opcionais: sem calendário nem e-mail no contexto, Calendar e Gmail desconectados não falham; com o
    e-mail escolhido, o Gmail desconectado falha (é o que a instalação usa)."""
    offline_dir = tmp_path / "offline-sem"
    offline_dir.mkdir()
    (offline_dir / "mcp_list.txt").write_text(
        "claude.ai Google Calendar: https://x.test/c - ✘ Needs authentication\n"
        "claude.ai Gmail: https://x.test/g - ✘ Needs authentication\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GP_OFFLINE_DIR", str(offline_dir))
    contexto = dados / "contexto.md"
    texto = contexto.read_text(encoding="utf-8")
    for chave in ("calendar_id_metas", "calendar_id_primario", "calendarios_lidos", "email_proprio", "fontes_ativas"):
        texto = "\n".join(linha for linha in texto.split("\n") if not linha.startswith(chave + ":"))
    contexto.write_text(texto, encoding="utf-8")
    item = status.item_conectores(status.item_dados(dados)[1], AGORA, modo_offline=True, sondar=True)
    assert item.ok and "sem conectores" in item.detalhe
    assert status.item_conectores(None, AGORA, modo_offline=True, sondar=False).ok
    contexto.write_text(texto.replace("---\n", "---\nemail_proprio: pessoa@exemplo.test\n", 1), encoding="utf-8")
    item = status.item_conectores(status.item_dados(dados)[1], AGORA, modo_offline=True, sondar=False)
    assert not item.ok and "Gmail" in item.detalhe and "Calendar" not in item.detalhe
