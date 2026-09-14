"""Tela Conexões: estado gravado pelo doctor e pelos jobs, fontes dos sinais, modelo do painel e rota de gravação."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import diario
import mensal
import painel
import status
from goalpacer import base, conexoes, frontmatter, registro as reg, tom
from goalpacer.base import GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
MCP_OK = {"Google_Calendar": "Connected", "Gmail": "Connected", "Notion": "Needs authentication"}


@pytest.fixture
def instalado(tmp_path, monkeypatch):
    """Raiz com jobs/ (o que existe numa instalação) e a pasta de dados do mensal."""
    dados = tmp_path / "dados"
    shutil.copytree(FIXTURES / "mensal" / "dados", dados)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "mensal" / "offline"))
    (tmp_path / "raiz" / "jobs").mkdir(parents=True)
    return dados


def test_sem_instalacao_nada_e_gravado(tmp_path, monkeypatch):
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "sem-raiz"))
    conexoes.registrar_doctor(MCP_OK, AGORA)
    assert not conexoes.caminho().exists() and conexoes.ler() == conexoes.vazio()


def test_doctor_e_jobs_gravam_o_estado(instalado):
    conexoes.registrar_doctor(MCP_OK, AGORA, simulado=True)
    assert not conexoes.caminho().exists()  # --offline nunca grava
    conexoes.registrar_doctor(MCP_OK, AGORA, metas_encontrado=True)
    estado = conexoes.ler()
    assert {n: s["estado"] for n, s in estado["servidores"].items()} == {
        "Google_Calendar": "conectado",
        "Gmail": "conectado",
        "Notion": "reconectar",
        "Google_Drive": "desconectado",
    }
    assert estado["metas_encontrado"] is True and estado["escrita_testada_em"] is None
    assert os.name == "nt" or oct(os.stat(conexoes.caminho()).st_mode & 0o777) == "0o600"
    depois = AGORA.replace(hour=9)
    conexoes.registrar_doctor(MCP_OK, depois, escrita_ok=True)
    assert conexoes.ler()["escrita_testada_em"] == depois.isoformat() and conexoes.ler()["metas_encontrado"] is True
    registro = [
        {"tool": "mcp__claude_ai_Notion__notion-search", "codigo": 0},
        {"tool": "prosa", "codigo": 0},
        {"tool": "mcp__claude_ai_Google_Calendar__list_events", "codigo": 0},
        {"tool": "mcp__claude_ai_Notion__notion-fetch", "codigo": 0},
        {"tool": "mcp__outro__x", "codigo": 0},
    ]
    assert conexoes.servidores_usados(registro) == ["Notion", "Google_Calendar"]
    conexoes.registrar_uso(registro, depois)
    notion = conexoes.ler()["servidores"]["Notion"]
    assert notion["estado"] == "conectado" and notion["uso_ok_em"] == depois.isoformat()
    conexoes.registrar_uso([{"tool": "prosa"}], depois)  # nenhum servidor: nada muda
    conexoes.caminho().write_text("[1]", encoding="utf-8")
    assert conexoes.ler() == conexoes.vazio()
    conexoes.caminho().write_text('{"servidores": [1], "outro": 2}', encoding="utf-8")
    assert conexoes.ler() == conexoes.vazio()
    assert conexoes.estado_do_mcp(" connected ") == "conectado" and conexoes.estado_do_mcp("Failed") == "reconectar"


def test_ajustar_fonte_em_contexto(instalado):
    assert conexoes.ajustar_fonte(instalado, "notion", True) is True
    contexto = frontmatter.ler_contexto(instalado)
    assert contexto["fontes_ativas"] == ["gmail", "whatsapp", "notion"]
    assert conexoes.ajustar_fonte(instalado, "notion", True) is False
    assert conexoes.ajustar_fonte(instalado, "gmail", False) is True
    assert frontmatter.ler_contexto(instalado)["fontes_ativas"] == ["whatsapp", "notion"]
    with pytest.raises(GpErro, match="fonte desconhecida 'slack'"):
        conexoes.ajustar_fonte(instalado, "slack", True)
    caminho = instalado / "contexto.md"
    caminho.write_text(
        caminho.read_text(encoding="utf-8").replace("schema_version: 1", "schema_version: um"), encoding="utf-8"
    )
    with pytest.raises(GpErro, match="inválido antes do ajuste"):
        conexoes.ajustar_fonte(instalado, "drive", True)


def test_jobs_do_dia_e_do_mes_marcam_o_uso(instalado):
    mensal.gerar(instalado, modo_offline=True, agora=AGORA, run_id="mensal-1")
    assert not conexoes.caminho().exists()  # offline: fixture não vira estado
    registro = [{"tool": "mcp__claude_ai_Gmail__search_threads", "codigo": 0}]
    r = diario._Rodada(instalado, AGORA.date(), AGORA, "d-1", False, {}, TZ, registro)
    diario._registrar_geracao(r, reg.carregar(instalado), {}, "nao_enviado")
    assert conexoes.ler()["servidores"]["Gmail"]["uso_ok_em"] == AGORA.isoformat()


def test_doctor_grava_o_que_viu(instalado, tmp_path, monkeypatch):
    offline = tmp_path / "offline-doctor"
    offline.mkdir()
    shutil.copy(FIXTURES / "offline" / "mcp_list.txt", offline / "mcp_list.txt")
    shutil.copy(FIXTURES / "mensal" / "offline" / "list_calendars.json", offline / "list_calendars.json")
    monkeypatch.setenv("GP_OFFLINE_DIR", str(offline))
    contexto = frontmatter.ler_contexto(instalado)
    vistos = []
    monkeypatch.setattr(status.conexoes, "registrar_doctor", lambda *a, **k: vistos.append(k))
    item = status.item_conectores(contexto, AGORA, modo_offline=True, sondar=True)
    assert item.ok
    assert [k.get("metas_encontrado") for k in vistos] == [None, True, True] and vistos[-1]["escrita_ok"] is True
    assert all(k["simulado"] is True for k in vistos)


def test_modelo_da_tela_conexoes(instalado, monkeypatch):
    mensal.gerar(instalado, modo_offline=True, agora=AGORA, run_id="mensal-1")
    m = painel.modelo_conexoes(instalado, AGORA)
    assert m["tela"] == "conexoes" and m["provedor"] == "Claude Code, pelo login que você já tem."
    assert [(c["id"], c["estado"], c["fonte"], c["ativa"]) for c in m["conexoes"]] == [
        ("calendar", "sem_verificacao", None, None),
        ("gmail", "sem_verificacao", "gmail", True),
        ("notion", "sem_verificacao", "notion", False),
        ("drive", "sem_verificacao", "drive", False),
        ("whatsapp", "com_export", "whatsapp", True),
    ]
    assert m["verificado"].startswith("Rode o doctor") and m["problema"] is None
    gmail = m["conexoes"][1]
    assert gmail["papel"] == "usada todo dia e fonte de sinais" and gmail["linhas"] == ["lida no mensal de 28/09"]
    assert m["conexoes"][4]["linhas"][0].startswith("último export em ")
    conexoes.registrar_doctor(MCP_OK, AGORA, metas_encontrado=False, escrita_ok=True)
    m = painel.modelo_conexoes(instalado, AGORA)
    calendar = m["conexoes"][0]
    assert calendar["estado"] == "conectado" and calendar["estado_texto"] == "conectado"
    assert calendar["linhas"] == [
        "visto pelo doctor em 28/09",
        "calendário Metas fora da lista: crie o calendário ou refaça o onboarding",
        "escrita testada em 28/09",
    ]
    assert m["conexoes"][2]["estado"] == "reconectar" and m["verificado"] == "Última verificação pelo doctor em 28/09."
    texto = "\n".join(painel_textos(m))
    assert tom.violacoes(texto) == []


def painel_textos(m) -> list:
    saida = [m["provedor"], m["onde"], m["verificado"], m["problema"] or ""]
    for c in m["conexoes"]:
        saida += [c["nome"], c["papel"], c["estado_texto"], *c["linhas"]]
    return saida


def test_ultimo_job_que_pediu_reconexao_aparece(instalado):
    registro = reg.carregar(instalado)
    for run_id, ts, codigo, classe in (
        ("job-diario-1", "2026-09-26T07:05:00-03:00", 0, None),
        ("job-diario-2", "2026-09-27T07:05:00-03:00", 3, "EscopoInsuficiente"),
    ):
        reg.registrar_geracao(
            registro,
            {"run_id": run_id, "modo": "job:diario", "data": ts[:10], "ts": ts, "exit_code": codigo, "classe": classe},
        )
    reg.salvar(registro, instalado)
    m = painel.modelo_conexoes(instalado, AGORA)
    assert m["problema"].startswith("O job de 27/09 parou em EscopoInsuficiente: ")
    registro = reg.carregar(instalado)
    reg.registrar_geracao(
        registro,
        {
            "run_id": "job-diario-3",
            "modo": "job:diario",
            "data": "2026-09-28",
            "ts": "2026-09-28T07:05:00-03:00",
            "exit_code": 5,
            "classe": "SessionTimeout",
        },
    )
    reg.salvar(registro, instalado)
    assert painel.modelo_conexoes(instalado, AGORA)["problema"] is None  # a última parada não é de conexão


def test_provedor_sem_conectores_na_tela(instalado, monkeypatch):
    monkeypatch.setenv("GP_PROVEDOR", "openai")
    m = painel.modelo_conexoes(instalado, AGORA)
    assert m["provedor"].startswith("Codex") and "apps do ChatGPT" in m["onde"]
    assert [c["estado"] for c in m["conexoes"][:4]] == ["provedor"] * 4
    assert "depois do spike" in m["conexoes"][0]["linhas"][0]


def test_sinais_quebrados_e_sem_export(instalado):
    (instalado / "sinais").mkdir(exist_ok=True)
    (instalado / "sinais" / "2026-09-20.md").write_text("---\nsem fechar", encoding="utf-8")
    (instalado / "sinais" / "rascunho.md").write_text("x", encoding="utf-8")
    shutil.rmtree(instalado / "inbox" / "whatsapp")
    m = painel.modelo_conexoes(instalado, AGORA)
    assert m["conexoes"][4]["estado"] == "sem_export" and m["conexoes"][1]["linhas"] == [
        "nenhuma leitura registrada nos sinais"
    ]


def test_rota_de_fontes_no_servidor(instalado, monkeypatch):
    import threading

    import web
    from test_web import pedir

    monkeypatch.setenv("GP_AGORA", AGORA.isoformat())
    srv = web.servir(0, instalado)
    fio = threading.Thread(target=srv.serve_forever, daemon=True)
    fio.start()
    try:
        status_http, corpo, _ = pedir(srv, "GET", "/api/conexoes")
        assert (
            status_http == 200 and corpo["modelo"]["tela"] == "conexoes" and "nav_conexoes" in corpo["modelo"]["textos"]
        )
        status_http, corpo, _ = pedir(srv, "POST", "/api/fonte", {"fonte": "drive", "ativa": True})
        assert status_http == 200 and corpo["mensagem"] == "Google Drive entra na próxima leitura mensal."
        assert "drive" in frontmatter.ler_contexto(instalado)["fontes_ativas"]
        assert (
            pedir(srv, "POST", "/api/fonte", {"fonte": "drive", "ativa": True})[1]["mensagem"]
            == "Google Drive já estava assim."
        )
        assert pedir(srv, "POST", "/api/fonte", {"fonte": "drive", "ativa": False})[1]["mensagem"].endswith(
            "sai da próxima leitura mensal."
        )
        for ruim in ({"fonte": "slack", "ativa": True}, {"fonte": "drive", "ativa": "sim"}, {}):
            assert pedir(srv, "POST", "/api/fonte", ruim)[0] == 400, ruim
        assert pedir(srv, "POST", "/api/fonte", {"fonte": "drive", "ativa": True}, token=False)[0] == 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_demo_tem_conexoes_sinteticas(tmp_path, monkeypatch):
    import demo_painel

    destino = tmp_path / "demo"
    destino.mkdir()
    demo_painel._conexoes(destino / "raiz" / base.NOME_JOBS)
    monkeypatch.setenv("GP_RAIZ", str(destino / "raiz"))
    estado = json.loads((destino / "raiz" / "jobs" / "conexoes.json").read_text(encoding="utf-8"))
    assert conexoes.ler() == estado and estado["servidores"]["Notion"]["estado"] == "reconectar"
