"""Email das 7h (references/email.md): ordem, tetos, colunas, tom, HTML, primeiro dia, reenvio, falha."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import diario
from goalpacer import copy, correio, estilo, execucao, proxy, render, tom
from goalpacer.base import GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "diario"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "diario.py"
TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def dados(tmp_path, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    for var in [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    monkeypatch.setenv("GP_TZ", "America/Sao_Paulo")
    monkeypatch.setattr("goalpacer.clock._AGORA_FIXADO", None)
    return destino


def rodar(dados, monkeypatch, dia: date, run_id: str, **kw):
    agora = datetime(dia.year, dia.month, dia.day, 7, 0, tzinfo=TZ)
    monkeypatch.setenv("GP_AGORA", agora.isoformat())
    return diario.gerar(
        dados, dia=dia, modo_offline=True, sem_inferir=False, agora=agora, run_id=run_id, enviar_email=True, **kw
    )


def email_de(dados, run_id):
    return json.loads((dados / "cache" / ("email-%s.json" % run_id)).read_text(encoding="utf-8"))


def conferir_superficie(args):
    colunas = estilo.inteiro("colunas_email_texto")
    assert args["subject"].startswith("[goal-pacer] ")
    assert all(len(l) <= colunas for l in args["body"].split("\n")), [
        l for l in args["body"].split("\n") if len(l) > colunas
    ]
    for texto in (args["subject"], args["body"], args["htmlBody"]):
        assert tom.violacoes(texto) == [], tom.violacoes(texto)
        assert chr(0x2014) not in texto
    assert render.lint_html(args["htmlBody"]) == []
    assert args["body"].count("https://") == 1


def test_primeiro_dia_e_segunda_com_desde(dados, monkeypatch):
    sabado = rodar(dados, monkeypatch, date(2026, 9, 26), "d-sab")
    assert sabado["primeiro_dia"] is True and sabado["email"]["status"] == "enviado"
    args = email_de(dados, "d-sab")
    conferir_superficie(args)
    assert args["to"] == ["pessoa@exemplo.test"]
    assert args["subject"].startswith("[goal-pacer] Sáb 26/09 · ")
    corpo = args["body"]
    assert "DESDE" not in corpo and "COMO FUNCIONA" in corpo and copy.texto("email.gestos") in corpo.replace("\n", " ")
    ordem = [
        corpo.index(t)
        for t in ("Sábado, 26/09", "HOJE", "COMO VÃO AS METAS", "COMO FUNCIONA", "Ver o dia no Google Calendar")
    ]
    assert ordem == sorted(ordem)
    assert "https://calendar.google.com/calendar/r/day/2026/09/26" in corpo
    # mesmo dia de novo: não reenvia
    de_novo = rodar(dados, monkeypatch, date(2026, 9, 26), "d-sab-2")
    assert de_novo["email"]["status"] == "ja_enviado" and not (dados / "cache" / "email-d-sab-2.json").exists()
    # confirmação no domingo, depois a segunda
    registro = json.loads((dados / "registro.json").read_text(encoding="utf-8"))
    registro["checkins"]["D-2026-09-26-01"]["ts"] = "2026-09-27T20:00:00-03:00"
    (dados / "registro.json").write_text(json.dumps(registro), encoding="utf-8")
    segunda = rodar(dados, monkeypatch, date(2026, 9, 28), "d-seg")
    assert segunda["primeiro_dia"] is False
    args = email_de(dados, "d-seg")
    conferir_superficie(args)
    corpo = args["body"]
    assert (
        "DESDE SÁB" in corpo
        and "1 confirmada(s)" in corpo
        and "Terminar o curso de estatística (M1): confirmada" in corpo
    )
    assert "COMO FUNCIONA" not in corpo
    ordem = [
        corpo.index(t)
        for t in ("Segunda, 28/09", "HOJE", "DESDE SÁB", "COMO VÃO AS METAS", "Ver o dia no Google Calendar")
    ]
    assert ordem == sorted(ordem)
    assert "8/10" not in args["subject"] and " de " not in args["subject"]


def test_modelo_tetos_decisao_e_html():
    blocos = []
    for i in range(8):
        inicio = datetime(2026, 9, 28, 8 + i, 0, tzinfo=TZ)
        blocos.append(
            {
                "id": "D-2026-09-28-%02d" % (i + 1),
                "titulo": "Bloco %d" % i,
                "meta": "M01",
                "inicio": inicio,
                "fim": inicio + timedelta(minutes=45),
                "estado": "planejada",
                "origem": "inferido",
                "porque": "porquê %d" % i,
                "efeito": "move: Mudar de carreira para dados (essencial)",
            }
        )
    dia = {
        "data": date(2026, 9, 28),
        "titulo": "Segunda, 28/09",
        "resumo": "8 blocos hoje, para M1.",
        "blocos": blocos,
        "desde_dia": "sáb",
        "desde_contagem": "2 feita?",
        "desde": ["linha %d" % i for i in range(9)],
        "progresso": ["M%d Meta %d: florescendo, no compasso do prazo" % (i, i) for i in range(1, 10)],
        "progresso_manchete": "O que mais move esta semana: Meta 3 (M3).",
        "avisos": ["aviso %d" % i for i in range(5)],
        "fm": {},
    }
    modelo = render.modelo_email(
        dia,
        decisao=(
            "M3",
            "Com as janelas até 31/10 dá para cobrir 62% do que falta de M3 neste mês. Saídas: reduzir · adiar para 15/11 · manter.",
        ),
    )
    assert len(modelo["hoje"]) == 6 and modelo["hoje_mais"] == 2
    assert len(modelo["desde"]["linhas"]) == 6 and len(modelo["progresso"]) == 8 and len(modelo["avisos"]) == 3
    assert modelo["assunto"] == "[goal-pacer] Seg 28/09 · 8 blocos · M3 precisa de decisão"
    _assunto, corpo = render.email_texto(modelo)
    assert all(len(l) <= 60 for l in corpo.split("\n"))
    ordem = [
        corpo.index(t)
        for t in (
            "PRECISA DE DECISÃO (M3)",
            "HOJE",
            "e mais 2 na agenda",
            "DESDE SÁB",
            "COMO VÃO AS METAS",
            "O que mais move esta semana",
            "AVISOS",
            "Ver o dia",
        )
    ]
    assert ordem == sorted(ordem)
    assert "08h-08h45" in corpo and "- M1 Meta 1: florescendo, no compasso do prazo" in corpo and "█" not in corpo
    html = render.email_html(modelo)
    assert render.lint_html(html) == [] and html.count("<a ") == 1 and "&lt;" not in html
    assert "M1 Meta 1: florescendo" in html and "max-width:560px" in html
    assert render.lint_html(html.replace("</div>", '<img src="x"></div>', 1)) == ["proibido: <img"]
    assert "cor fora dos tokens: #ff0000" in render.lint_html(html.replace("#111", "#ff0000", 1))
    assert render.lint_html(html.replace("font-size:13px", "font-size:11px", 1))[0].startswith("fonte abaixo de 13px")
    vazio = render.modelo_email(
        dict(dia, blocos=[], progresso=[], desde=[], desde_contagem="", avisos=[]), primeiro_dia=True
    )
    _, corpo = render.email_texto(vazio)
    assert (
        vazio["assunto"] == "[goal-pacer] Seg 28/09 · sem blocos" and "começando" in corpo and "COMO FUNCIONA" in corpo
    )


def test_email_falha_e_correio(dados, monkeypatch):
    assunto, texto, html = render.email_falha(
        date(2026, 9, 28), execucao.motivo("RateLimited"), execucao.acao("RateLimited")
    )
    assert assunto == "[goal-pacer] Seg 28/09 · hoje não gerei o seu dia"
    assert texto.startswith(
        "Motivo: a janela de uso da assinatura esgotou. O que fazer:"
    ) and "Seus blocos de ontem" in texto.replace("\n", " ")
    assert render.lint_html(html) == [] and tom.violacoes(texto) == []
    for classe in execucao.CLASSES:
        assert tom.violacoes(execucao.motivo(classe) + " " + execucao.acao(classe)) == [], classe
    saida = diario.enviar_email_falha(
        dados, "SessionTimeout", dia=date(2026, 9, 28), modo_offline=True, run_id="falha-1"
    )
    args = email_de(dados, "falha-1")
    assert (
        saida["offline"]
        and args["subject"].endswith("hoje não gerei o seu dia")
        and "passou do tempo máximo" in args["body"]
    )
    with pytest.raises(GpErro):
        correio.argumentos({"email_proprio": "p@e.test"}, "sem prefixo", "x", "y")
    with pytest.raises(GpErro):
        correio.argumentos({}, "[goal-pacer] x", "x", "y")
    chamadas = []
    resposta = correio.enviar(
        {"email_proprio": "p@e.test"},
        "[goal-pacer] x",
        "t",
        "<p>h</p>",
        run_id="r",
        modo_offline=False,
        chamar=lambda tool, args: chamadas.append((tool, args)) or {"id": "msg-1"},
    )
    assert (
        resposta == {"id": "msg-1", "offline": False}
        and chamadas[0][0] == correio.TOOL_SEND
        and chamadas[0][1]["htmlBody"] == "<p>h</p>"
    )


def test_email_falhou_nao_derruba_o_dia(dados, monkeypatch):
    def quebra(*a, **k):
        raise proxy.ErroConector("Insufficient scope: required gmail.send")

    monkeypatch.setattr(correio, "enviar", quebra)
    saida = rodar(dados, monkeypatch, date(2026, 9, 28), "d-x")
    assert saida["email"] == {"status": "falhou", "classe": "EscopoInsuficiente"}
    registro = json.loads((dados / "registro.json").read_text(encoding="utf-8"))
    assert registro["geracoes"]["d-x"]["email"] == "falhou"


def test_classe_de():
    assert execucao.classe_de(proxy.RateLimited("x")) == "RateLimited"
    assert execucao.classe_de(proxy.ErroConector("Insufficient scope")) == "EscopoInsuficiente"
    assert execucao.classe_de(proxy.ErroConector("outro")) == "ErroConector"
    assert execucao.classe_de(proxy.McpNaoCarregado("x")) == "McpNaoCarregado"
    assert execucao.classe_de(GpErro(2, "sem_meta_ativa: rode")) == "SemMetaAtiva"
    assert execucao.classe_de(GpErro(2, "sem_onboarding: rode")) == "SemOnboarding"
    assert execucao.classe_de(GpErro(3, copy.texto("diario.metas_nao_encontrado"))) == "MetasNaoEncontrado"
    assert (
        execucao.classe_de(GpErro(3, "registro.json: schema_version 0 (esperado 1); rode install.sh --update"))
        == "SchemaMismatch"
    )
    assert execucao.classe_de(GpErro(5, "timeout")) == "SessionTimeout"
    assert execucao.classe_de(GpErro(4, "lock preso há 50 min (pid 1)")) == "LockTimeout"
    assert execucao.classe_de(ValueError("x")) == "Desconhecida"
    assert execucao.erro_json(proxy.RateLimited("x"))["runbook"] == "rate-limited"
    assert execucao.classe_do_json('lixo\n{"ok": false, "classe": "RateLimited"}\n') == "RateLimited"
    assert execucao.classe_do_json("nada") is None
    assert execucao.info("RateLimited").retentar and not execucao.info("Inexistente").retentar


def test_cli_email_falha(tmp_path):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    ambiente.update(
        {"GP_OFFLINE_DIR": str(FIXTURES / "offline"), "GP_RAIZ": str(tmp_path / "raiz"), "GP_RUN_ID": "cli-falha"}
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dados",
            str(destino),
            "--agora",
            "2026-09-28T07:00:00-03:00",
            "--tz",
            "America/Sao_Paulo",
            "--offline",
            "--email-falha",
            "LockTimeout",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ambiente,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads((destino / "cache" / "email-cli-falha.json").read_text(encoding="utf-8"))["subject"].endswith(
        "hoje não gerei o seu dia"
    )


def test_email_texto_e_html_pelo_terminal_batem_com_o_enviado(dados, monkeypatch):
    """T30: --email-texto/--email-html reconstroem de dias/ o mesmo email que o diário mandou."""
    rodar(dados, monkeypatch, date(2026, 9, 26), "d-sab")
    rodar(dados, monkeypatch, date(2026, 9, 28), "d-seg")
    enviado = email_de(dados, "d-seg")
    assunto, corpo, html = diario.montar_email(dados, date(2026, 9, 28))
    assert (assunto, corpo, html) == (enviado["subject"], enviado["body"], enviado["htmlBody"])
    assert diario.montar_email(dados, date(2026, 9, 26))[1] == email_de(dados, "d-sab")["body"]
    env = dict(os.environ.items())
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--email-texto", "--data", "2026-09-28"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "Assunto: %s\n\n%s\n" % (enviado["subject"], enviado["body"].rstrip("\n"))
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--email-html", "--data", "2026-09-28"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 0 and proc.stdout.rstrip("\n") == enviado["htmlBody"].rstrip("\n")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--email-texto", "--data", "2026-10-02"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 2 and "rode diario.py --data 2026-10-02" in proc.stderr


def test_reenviar_email_do_dia_uma_vez(dados, monkeypatch):
    dia = date(2026, 9, 28)
    agora = datetime(2026, 9, 28, 7, 30, tzinfo=TZ)
    monkeypatch.setenv("GP_AGORA", agora.isoformat())
    with pytest.raises(GpErro, match="não existe"):
        diario.reenviar_email(dados, dia=date(2026, 10, 5), modo_offline=True, agora=agora, run_id="r-antes")
    original = correio.enviar
    monkeypatch.setattr(correio, "enviar", lambda *a, **k: (_ for _ in ()).throw(GpErro(3, "Insufficient scope")))
    saida = rodar(dados, monkeypatch, dia, "d-seg")
    assert saida["email"]["status"] == "falhou"
    monkeypatch.setattr(correio, "enviar", original)
    monkeypatch.setenv("GP_AGORA", agora.isoformat())
    reenvio = diario.reenviar_email(dados, dia=dia, modo_offline=True, agora=agora, run_id="r-1")
    assert reenvio["email"]["status"] == "enviado"
    args = email_de(dados, "r-1")
    conferir_superficie(args)
    assert args["body"] == diario.montar_email(dados, dia)[1]
    registro = json.loads((dados / "registro.json").read_text(encoding="utf-8"))
    assert registro["geracoes"]["r-1"]["modo"] == "diario-email" and registro["geracoes"]["r-1"]["email"] == "enviado"
    assert (
        diario.reenviar_email(dados, dia=dia, modo_offline=True, agora=agora, run_id="r-2")["email"]["status"]
        == "ja_enviado"
    )
    assert not (dados / "cache" / "email-r-2.json").exists()
