"""Painel web (direção A + F): modelo da tela Hoje, servidor local e suas proteções, ações e textos."""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import checkin
import diario
import mensal
import painel
import web
from goalpacer import copy, frontmatter, metas as gpmetas, registro as reg, schema, tom
from goalpacer.base import GpErro

RAIZ_REPO = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA_JOB = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
AGORA = datetime(2026, 9, 28, 9, 0, tzinfo=TZ)


@pytest.fixture
def dados(tmp_path, agora_fixo, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "mensal" / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "mensal" / "offline"))
    mensal.gerar(destino, modo_offline=True, agora=AGORA_JOB, run_id="mensal-1")
    diario.gerar(
        destino, dia=AGORA_JOB.date(), modo_offline=True, sem_inferir=False, agora=AGORA_JOB, run_id="diario-1"
    )
    monkeypatch.setenv("GP_AGORA", AGORA.isoformat())
    return destino


def visiveis(modelo) -> list:
    """Textos de interface que o modelo já entrega prontos (o resto sai de textos no front)."""
    saida = []
    for chave, valor in modelo.items():
        if chave == "textos":
            continue
        if isinstance(valor, str):
            saida.append(valor)
        elif isinstance(valor, dict):
            saida += visiveis(valor)
        elif isinstance(valor, list):
            for item in valor:
                saida += visiveis(item) if isinstance(item, dict) else [item] if isinstance(item, str) else []
    return saida


def test_modelo_da_tela_hoje_fala_em_leituras(dados):
    m = painel.modelo(dados, AGORA)
    assert (
        m["tela"] == "hoje"
        and m["data"] == "2026-09-28"
        and m["titulo_dia"] == "Segunda, 28/09"
        and m["sub"] == "3 blocos hoje."
    )
    assert [(p["nivel"], p["rotulo"]) for p in m["trilha"]] == [
        ("ano", "2026"),
        ("semestre", "S2"),
        ("trimestre", "T4"),
        ("mes", "Out"),
        ("semana", "Semana 40"),
    ]
    assert (m["anterior"], m["proximo"], m["e_hoje"]) == ("2026-09-27", "2026-09-29", True)
    assert [b["inicio"] for b in m["blocos"]] == ["08:00", "08:45", "09:15"] and all(
        b["pode_confirmar"] for b in m["blocos"]
    )
    assert [b["passou"] for b in m["blocos"]] == [True, False, False] and m["blocos"][0][
        "cor"
    ] == painel.CORES_OBJETIVO[0]
    # anéis: palavras, não horas; o número 0..1 só desenha
    assert [h["nome"] for h in m["horizontes"]] == ["hoje", "semana", "mes"]
    assert [h["leitura"] for h in m["horizontes"]][0::2] == ["coach.presenca_por_comecar", "coach.direcao_foco"]
    # só M1 tem bloco vencido na semana (confirmado na sexta e o das 8h, intocado, vale como "feita?"): o ritmo é o dela
    assert m["horizontes"][1]["leitura"] == "coach.ritmo_florescendo"
    assert all(h["leitura"] in m["textos"] for h in m["horizontes"]) and not any(
        "pct" in h or "plano_h" in h for h in m["horizontes"]
    )
    # sem objetivos cadastrados, cada meta é o próprio objetivo; a alavanca é a de maior impacto vezes o que falta de tração
    assert [(o["id"], o["implicito"]) for o in m["objetivos"]] == [("M01", True), ("M02", True)]
    assert m["alavanca"]["id"] == "M02" and m["manchete"] == copy.texto("coach.manchete_florescendo")
    assert [(x["id"], x["estado"]) for x in m["metas"]] == [("M02", "atencao"), ("M01", "florescendo")]
    assert m["espaco"]["faixa"] == "apertado" and [s["faixa"] for s in m["espaco"]["semanas"]] == [
        "apertado",
        "justo",
        "apertado",
        "justo",
        "justo",
    ]
    assert [d["meta"] for d in m["decisoes"]] == ["M01", "M02"] and m["decisoes"][1]["prazo_externo"] is True
    assert m["decisoes"][1]["texto"] == "Com as janelas até 31/10 dá para cobrir 62% do que falta de M2 neste mês."
    assert re.match(r"^[0-9a-f]{16}-M02-[0-9a-f]{8}$", m["decisoes"][1]["chave"])
    assert not any("decisão aberta" in a for a in m["avisos"])
    assert all(tom.violacoes(texto) == [] for texto in visiveis(m)), [
        texto for texto in visiveis(m) if tom.violacoes(texto)
    ]
    assert not any(re.search(r"\d+%", texto) for texto in (m["manchete"], m["sub"]))
    # confirmar o primeiro bloco move o anel de hoje e a linha de baixo da manchete
    checkin.confirmar(dados, {"feitas": [{"task_id": m["blocos"][0]["id"]}]}, agora=AGORA)
    m = painel.modelo(dados, AGORA)
    assert m["blocos"][0]["confirmada"] and not m["blocos"][0]["pode_confirmar"]
    assert (
        m["horizontes"][0]["leitura"] == "coach.presenca_andamento" and m["sub"] == "3 blocos hoje. Um já confirmado."
    )
    assert painel.horas_texto(5.75) == "5 h 45" and painel.horas_texto(0) == "0 h" and painel.horas_texto(2) == "2 h"


def test_modelo_sem_dia_e_sem_plano(dados):
    m = painel.modelo(dados, datetime(2026, 11, 3, 9, 0, tzinfo=TZ))
    assert m["blocos"] == [] and m["sub"] == copy.texto("painel.manchete_zero") and m["espaco"] is None
    assert m["horizontes"][0]["leitura"] == "coach.presenca_sem_blocos"
    mes = painel.modelo_periodo(dados, datetime(2026, 11, 3, 9, 0, tzinfo=TZ), "mes")
    assert mes["id"] == "2026-11" and mes["espaco"] is None and "Sem plano de novembro/2026" in mes["sem_plano"]


def test_modelos_das_outras_telas(dados):
    objetivos = painel.modelo_objetivos(dados, AGORA)
    assert objetivos["tem_implicitos"] and [o["metas"][0]["fatia"] for o in objetivos["objetivos"]] == [1.0, 1.0]
    metas = painel.modelo_metas(dados, AGORA)
    assert {x["quadrante"] for x in metas["metas"]} <= {"proteger", "destravar", "manter_leve", "repensar"}
    meta = painel.modelo_meta(dados, AGORA, "M02")
    assert (
        meta["meta"]["estado"] == "atencao"
        and meta["numeros"]["cobertura"] == "62%"
        and meta["numeros"]["decisao"] == "renegociar"
    )
    assert meta["leitura"]["atrito"] == copy.texto("coach.atrito", frase=copy.texto("coach.espaco_baixo"))
    assert meta["leitura"]["passo"] == copy.texto("coach.passo_atencao") and len(meta["meta"]["trilha_semanas"]) == 6
    assert [s["nome"] for s in meta["sinais"]] == ["presenca", "fluidez", "energia", "evidencia", "espaco"]
    with pytest.raises(GpErro):
        painel.modelo_meta(dados, AGORA, "../M01")
    with pytest.raises(GpErro):
        painel.modelo_meta(dados, AGORA, "M09")
    mes = painel.modelo_periodo(dados, AGORA, "mes", "2026-10")
    assert (
        mes["espaco"]["faixa"] == "apertado"
        and mes["resumo"]
        and len(mes["decisoes"]) == 2
        and [x["id"] for x in mes["metas_acima"]] == ["M02", "M01"]
    )
    ck = painel.modelo_checkin(dados, AGORA)
    assert (
        [b["inicio"] for b in ck["pendentes"]] == ["08:00"]
        and len(ck["decisoes"]) == 2
        and {x["id"] for x in ck["metas"]} == {"M01", "M02"}
    )
    status = painel.modelo_status(dados, AGORA)
    assert [e["run_id"] for e in status["execucoes"]] == ["diario-1", "mensal-1"] and status[
        "fuso"
    ] == "America/Sao_Paulo"
    for modelo in (objetivos, metas, meta, mes, ck, status):
        assert all(tom.violacoes(texto) == [] for texto in visiveis(modelo))


def test_objetivos_cadastrados_pesam_as_metas_pelo_impacto(dados):
    (dados / "objetivos").mkdir()
    frontmatter.escrever_arquivo(
        dados / "objetivos" / "O01.md",
        {"id": "O01", "titulo": "Mudar de carreira", "estado": "ativo"},
        "\n## Por que\n\nTrabalho com dados.\n\n## Como vou saber\n\nUma proposta.\n",
    )
    for meta_id, impacto in (("M01", "essencial"), ("M02", "apoio")):
        gpmetas.ajustar(dados, meta_id, {"objetivo": "O01", "impacto": impacto})
    objetivos = painel.modelo_objetivos(dados, AGORA)
    (o,) = objetivos["objetivos"]
    assert (
        o["id"] == "O01"
        and not o["implicito"]
        and o["por_que"] == "Trabalho com dados."
        and o["como_vou_saber"] == "Uma proposta."
    )
    assert {x["id"]: x["fatia"] for x in o["metas"]} == {"M01": 0.75, "M02": 0.25}
    assert o["alavanca"]["id"] in ("M01", "M02") and o["estado"] in ("firme", "construcao", "foco")
    gpmetas.ajustar(dados, "M02", {"estado": "pausada"})
    (o,) = painel.modelo_objetivos(dados, AGORA)["objetivos"]
    assert {x["id"]: x["fatia"] for x in o["metas"]} == {"M01": 1.0, "M02": 0.0}
    assert painel.modelo_meta(dados, AGORA, "M02")["meta"]["estado"] == "pausada"
    assert [d["meta"] for d in checkin.decisoes_pendentes(dados, AGORA)] == ["M01"]


def test_drill_down_do_ano_ao_dia(dados):
    """M1 é meta de trimestre (prazo 15/12), M2 de semestre (prazo 01/03/2027); mês, semana e dia saem delas."""
    ano = painel.modelo_periodo(dados, AGORA)
    assert (ano["nivel"], ano["id"], ano["titulo"], ano["intervalo"], ano["fase"]) == (
        "ano",
        "2026",
        "2026",
        "janeiro a dezembro",
        "atual",
    )
    assert (
        ano["metas_nivel"] == []
        and [x["id"] for x in ano["metas_abaixo"]] == ["M02", "M01"]
        and ano["alavanca"]["id"] == "M02"
    )
    assert [(f["id"], f["fase"], f["prazos"]) for f in ano["filhos"]] == [
        ("2026-S1", "passado", 0),
        ("2026-S2", "atual", 1),
    ]
    assert [n["id"] for n in ano["niveis"]] == ["2026", "2026-S2", "2026-T4", "2026-10", "2026-W40", "2026-09-28"]
    semestre = painel.modelo_periodo(dados, AGORA, "semestre", "2026-S2")
    assert (
        semestre["titulo"] == "2º semestre de 2026"
        and [x["id"] for x in semestre["metas_nivel"]] == ["M02"]
        and semestre["trilha"][0]["id"] == "2026"
    )
    trimestre = painel.modelo_periodo(dados, AGORA, "trimestre", "2026-T4")
    assert [x["id"] for x in trimestre["metas_nivel"]] == ["M01"] and trimestre["metas_nivel"][0]["prazo_aqui"] is True
    assert trimestre["metas_nivel"][0]["compasso"] == "folego" and [x["id"] for x in trimestre["metas_acima"]] == [
        "M02"
    ]
    assert trimestre["leitura"]["chave"].startswith("coach.direcao_") and trimestre["leitura"]["frase"] == copy.texto(
        "coach.periodo_alavanca_trimestre", meta="Terminar o curso de estatística (M1)"
    )
    assert [(f["id"], f["fase"], f["leitura"]) for f in trimestre["filhos"]][1:] == [
        ("2026-11", "futuro", "fase_futuro"),
        ("2026-12", "futuro", "fase_futuro"),
    ]
    assert trimestre["filhos"][2]["prazos"] == 1 and (trimestre["anterior"], trimestre["proximo"]) == (
        "2026-T3",
        "2027-T1",
    )
    semana = painel.modelo_periodo(dados, AGORA, "semana", "2026-W40")
    assert (
        semana["titulo"] == "Semana 40 · 2026"
        and semana["intervalo"] == "28/09 a 04/10"
        and semana["leitura"]["chave"].startswith("coach.ritmo_")
    )
    assert [len(f["blocos"]) for f in semana["filhos"]] == [3, 0, 0, 0, 0, 0, 0] and semana["filhos"][0]["hoje"] is True
    passada = painel.modelo_periodo(dados, AGORA, "semana", "2026-W39")
    assert (
        passada["fase"] == "passado"
        and passada["leitura"]["frase"] == copy.texto("coach.periodo_passado")
        and passada["alavanca"] is None
    )
    futuro = painel.modelo_periodo(dados, AGORA, "trimestre", "2027-T1")
    assert (
        futuro["fase"] == "futuro"
        and futuro["leitura"]["valor"] is None
        and futuro["leitura"]["frase"] == copy.texto("coach.periodo_futuro_um")
    )
    textos_painel = painel.textos()
    for modelo in (ano, semestre, trimestre, semana, passada, futuro):
        assert modelo["leitura"]["chave"] in textos_painel and all(
            f["leitura"] in textos_painel for f in modelo["filhos"]
        )
        assert all(tom.violacoes(texto) == [] for texto in visiveis(modelo))
    for nivel, pid in (("dia", "2026-09-28"), ("hora", None), ("trimestre", "2026-T9"), ("mes", "../x")):
        with pytest.raises(GpErro):
            painel.modelo_periodo(dados, AGORA, nivel, pid)
    # o dia é a tela Hoje com data: trilha e vizinhos do dia pedido
    dia = painel.modelo(dados, AGORA, datetime(2026, 9, 25).date())
    assert dia["e_hoje"] is False and dia["trilha"][-1]["id"] == "2026-W39" and dia["trilha"][-2]["id"] == "2026-09"


def test_textos_usados_no_front_existem_e_seguem_o_tom():
    chaves = set(painel.textos())
    arquivos_js = [RAIZ_REPO / "web" / "app.js", *sorted((RAIZ_REPO / "web" / "js").rglob("*.js"))]
    js = "\n".join(p.read_text(encoding="utf-8") for p in arquivos_js)
    html = (RAIZ_REPO / "web" / "index.html").read_text(encoding="utf-8")
    literais = set(re.findall(r'\bt\("([a-z_.]+)"\s*[,)]', js)) | set(
        re.findall(r'data-t(?:-rotulo)?="([a-z_.]+)"', html)
    )
    assert literais and literais <= chaves, literais - chaves
    prefixos = set(re.findall(r'\bt\("([a-z_.]+)"\s*\+', js))
    assert prefixos and all(any(c.startswith(p) for c in chaves) for p in prefixos), prefixos
    assert all(tom.violacoes(v) == [] for v in painel.textos().values())
    assert re.sub(r"<[^>]+>|\{\{TOKEN\}\}", "", html).strip() == "Goal Pacer"  # nenhum texto de interface solto no HTML
    assert "innerHTML" not in js and "eval(" not in js and 'setAttribute("style"' not in js  # CSP style-src 'self'
    for arquivo in [RAIZ_REPO / "web" / "index.html", RAIZ_REPO / "web" / "app.css", *arquivos_js]:
        assert chr(0x2014) not in arquivo.read_text(encoding="utf-8")


def test_front_em_modulos_nativos_sem_build_e_sem_origem_externa():
    web_dir = RAIZ_REPO / "web"
    html = (web_dir / "index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="/app.js"></script>' in html
    modulos = [web_dir / "app.js", *sorted((web_dir / "js").rglob("*.js"))]
    assert len(modulos) >= 9 and all(("/" + p.relative_to(web_dir).as_posix()) in web.ESTATICOS for p in modulos)
    for arquivo in modulos:
        texto = arquivo.read_text(encoding="utf-8")
        for nomes, origem in re.findall(r'^import \{ ([^}]*) \} from "([^"]+)";', texto, flags=re.MULTILINE):
            assert origem.startswith(("./", "../")), (arquivo.name, origem)  # nada de CDN nem pacote
            alvo = (arquivo.parent / origem).resolve()
            exportados = set(
                re.findall(
                    r"^export (?:function|var) ([A-Za-z_$][\w$]*)", alvo.read_text(encoding="utf-8"), flags=re.MULTILINE
                )
            )
            assert {n.strip() for n in nomes.split(",")} <= exportados, (arquivo.name, origem)
    telas = sorted(p.stem for p in (web_dir / "js" / "telas").glob("*.js"))
    app = (web_dir / "app.js").read_text(encoding="utf-8")
    assert all('from "./js/telas/%s.js"' % tela in app for tela in telas)


# --- servidor ----------------------------------------------------------------------------


@pytest.fixture
def servidor(dados):
    srv = web.servir(0, dados)
    fio = threading.Thread(target=srv.serve_forever, daemon=True)
    fio.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def pedir(srv, metodo, caminho, corpo=None, *, token=True, host=None, cabecalhos=None):
    conexao = http.client.HTTPConnection("127.0.0.1", srv.porta, timeout=10)
    headers = {"Host": host or "127.0.0.1:%d" % srv.porta}
    if token:
        headers["X-GP-Token"] = srv.token
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    headers.update(cabecalhos or {})
    conexao.request(metodo, caminho, body=dados, headers=headers)
    resposta = conexao.getresponse()
    bruto = resposta.read()
    conexao.close()
    tipo = resposta.getheader("Content-Type") or ""
    return (
        resposta.status,
        (json.loads(bruto) if tipo.startswith("application/json") else bruto.decode("utf-8", "replace")),
        resposta,
    )


def test_servidor_serve_a_pagina_com_token_e_protecoes(servidor):
    status, html, resposta = pedir(servidor, "GET", "/", token=False)
    assert status == 200 and servidor.token in html and "{{TOKEN}}" not in html
    assert (
        "default-src 'self'" in resposta.getheader("Content-Security-Policy")
        and resposta.getheader("X-Content-Type-Options") == "nosniff"
    )
    assert pedir(servidor, "GET", "/app.js", token=False)[0] == 200
    assert (
        pedir(servidor, "GET", "/js/telas/hoje.js", token=False)[0] == 200
        and pedir(servidor, "GET", "/js/../scripts/web.py", token=False)[0] == 404
    )
    assert pedir(servidor, "GET", "/fonts/plus-jakarta-sans-latin.woff2", token=False)[0] == 200
    assert pedir(servidor, "GET", "/../scripts/web.py", token=False)[0] == 404
    assert pedir(servidor, "GET", "/api/painel", token=False)[0] == 403
    assert pedir(servidor, "GET", "/", token=False, host="evil.test:%d" % servidor.porta)[0] == 403
    status, corpo, _ = pedir(servidor, "GET", "/api/painel")
    assert (
        status == 200
        and corpo["ok"]
        and corpo["modelo"]["sub"] == "3 blocos hoje."
        and corpo["endereco"].startswith("http://127.0.0.1:")
        and corpo["demo"] is False
    )
    assert pedir(servidor, "GET", "/api/painel?data=ontem")[0] == 400


def test_servidor_confirma_bloco_e_recusa_pedidos_estranhos(servidor, dados):
    bloco = painel.modelo(dados, AGORA)["blocos"][1]["id"]
    assert (
        pedir(servidor, "POST", "/api/confirmar", {"task_id": bloco}, cabecalhos={"Origin": "http://evil.test"})[0]
        == 403
    )
    assert pedir(servidor, "POST", "/api/confirmar", {"task_id": bloco}, token=False)[0] == 403
    conexao = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=10)
    conexao.request(
        "POST",
        "/api/confirmar",
        body=b"task_id=x",
        headers={"Host": "127.0.0.1:%d" % servidor.porta, "X-GP-Token": servidor.token, "Content-Type": "text/plain"},
    )
    assert conexao.getresponse().status == 415
    conexao.close()
    assert pedir(servidor, "POST", "/api/confirmar", {"task_id": "../x"})[0] == 400
    status, corpo, _ = pedir(servidor, "POST", "/api/confirmar", {"task_id": "D-2026-09-28-09"})
    assert status == 400 and "não existe" in corpo["erro"]
    status, corpo, _ = pedir(
        servidor,
        "POST",
        "/api/confirmar",
        {"task_id": bloco},
        cabecalhos={"Origin": "http://127.0.0.1:%d" % servidor.porta},
    )
    assert status == 200 and corpo["modelo"]["blocos"][1]["confirmada"] is True
    assert reg.carregar(dados)["checkins"][bloco]["origem"] == "confirmado"
    assert not (dados / ".lock").exists()
    # job segurando a pasta de dados: 409 com o texto do painel
    (dados / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "criado_em": "2026-09-28T12:00:00+00:00"}), encoding="utf-8"
    )
    status, corpo, _ = pedir(
        servidor, "POST", "/api/confirmar", {"task_id": painel.modelo(dados, AGORA)["blocos"][2]["id"]}
    )
    assert status == 409 and corpo["erro"] == copy.texto("painel.job_em_andamento")


def test_servidor_aplica_decisao(servidor, dados):
    status, corpo, _ = pedir(
        servidor, "POST", "/api/decisao", {"meta": "M02", "saida": "renegociar", "prazo": "2027-05-01"}
    )
    assert status == 200 and corpo["mensagem"] == "M2 ajustada. O próximo diário refaz o plano com o novo número."
    bruto, _ = frontmatter.ler_arquivo(dados / "metas" / "M02.md")
    assert frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])[0]["prazo"].isoformat() == "2027-05-01"
    assert corpo["modelo"]["decisoes"] == []  # metas mudaram: o plano deixa de oferecer decisão até o próximo diário
    status, corpo, _ = pedir(servidor, "POST", "/api/decisao", {"meta": "M01", "saida": "reduzir", "custo": "muito"})
    assert status == 400
    assert pedir(servidor, "POST", "/api/decisao", {"meta": "M01", "saida": "sumir"})[0] == 400


def test_servidor_serve_todas_as_telas(servidor, dados):
    for rota, tela in (
        ("/api/objetivos", "objetivos"),
        ("/api/metas", "metas"),
        ("/api/meta?id=M01", "meta"),
        ("/api/periodo?nivel=mes", "periodo"),
        ("/api/checkin", "checkin"),
        ("/api/status", "status"),
    ):
        assert pedir(servidor, "GET", rota, token=False)[0] == 403
        status, corpo, _ = pedir(servidor, "GET", rota)
        assert (
            status == 200 and corpo["modelo"]["tela"] == tela and "coach.estado_travada" in corpo["modelo"]["textos"]
        ), rota
    status, corpo, _ = pedir(servidor, "GET", "/api/status")
    assert corpo["modelo"]["rede"] is False and corpo["modelo"]["local"] is True and corpo["modelo"]["aparelhos"] == 0
    assert pedir(servidor, "GET", "/api/meta?id=../M01")[0] == 400 and pedir(servidor, "GET", "/api/meta")[0] == 400
    assert pedir(servidor, "GET", "/api/meta?id=M09")[0] == 400
    status, corpo, _ = pedir(servidor, "GET", "/api/periodo")
    assert status == 200 and corpo["modelo"]["nivel"] == "ano" and corpo["modelo"]["id"] == "2026"
    assert (
        pedir(servidor, "GET", "/api/periodo?nivel=trimestre&id=2026-T4")[1]["modelo"]["titulo"]
        == "4º trimestre de 2026"
    )
    for ruim in ("?nivel=dia", "?nivel=hora", "?nivel=semana&id=2026-W99", "?nivel=mes&id=../../x"):
        assert pedir(servidor, "GET", "/api/periodo" + ruim)[0] == 400, ruim


def test_servidor_grava_checkin_sentimento_marcos_e_ajustes(servidor, dados):
    bruto, corpo_meta = frontmatter.ler_arquivo(dados / "metas" / "M01.md")
    frontmatter.escrever_arquivo(
        dados / "metas" / "M01.md", bruto, corpo_meta.rstrip("\n") + "\n\n## Marcos\n\n- [x] Módulo 1\n- [ ] Módulo 2\n"
    )
    blocos = painel.modelo(dados, AGORA)["blocos"]
    # rotas novas passam pelas mesmas guardas
    assert pedir(servidor, "POST", "/api/checkin", {"feitas": [blocos[0]["id"]]}, token=False)[0] == 403
    assert (
        pedir(
            servidor,
            "POST",
            "/api/sentimento",
            {"meta": "M01", "valor": "energia"},
            cabecalhos={"Origin": "http://evil.test"},
        )[0]
        == 403
    )
    assert pedir(servidor, "POST", "/api/rota-que-nao-existe", {})[0] == 404
    # não fiz
    status, corpo, _ = pedir(servidor, "POST", "/api/nao-feita", {"task_id": blocos[2]["id"]})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.nao_feita_ok")
    assert reg.carregar(dados)["checkins"][blocos[2]["id"]]["estado"] == "nao_feita"
    # check-in completo: blocos, sentimentos e nota no perfil
    status, corpo, _ = pedir(
        servidor,
        "POST",
        "/api/checkin",
        {"feitas": [blocos[0]["id"]], "sentimentos": {"M02": "pesada"}, "nota": "Cedo rende mais."},
    )
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.checkin_ok")
    registro = reg.carregar(dados)
    assert (
        registro["checkins"][blocos[0]["id"]]["origem"] == "confirmado"
        and registro["sentimentos"]["M02"][-1]["valor"] == "pesada"
    )
    assert "Cedo rende mais." in (dados / "perfil.md").read_text(encoding="utf-8")
    status, corpo, _ = pedir(servidor, "POST", "/api/checkin", {})
    assert status == 400 and corpo["erro"] == copy.texto("painel.checkin_vazio")
    assert pedir(servidor, "POST", "/api/checkin", {"feitas": ["../x"]})[0] == 400
    assert pedir(servidor, "POST", "/api/checkin", {"sentimentos": {"M01": "furiosa"}})[0] == 400
    assert pedir(servidor, "POST", "/api/checkin", {"nota": "x" * 400})[0] == 400
    # sentimento avulso aparece na leitura da meta
    assert (
        pedir(servidor, "POST", "/api/sentimento", {"meta": "M01", "valor": "energia"})[1]["mensagem"]
        == "Anotado para M1."
    )
    assert painel.modelo_meta(dados, AGORA, "M01")["meta"]["sentimento"] == "energia"
    assert pedir(servidor, "POST", "/api/sentimento", {"meta": "M01", "valor": "cansada"})[0] == 400
    # marcos
    status, corpo, _ = pedir(servidor, "POST", "/api/meta/marco", {"meta": "M01", "indice": 1, "feito": True})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.marco_feito")
    assert [m["feito"] for m in painel.modelo_meta(dados, AGORA, "M01")["meta"]["marcos"]] == [True, True]
    assert painel.modelo_meta(dados, AGORA, "M01")["meta"]["estado"] == "conquistada"
    assert pedir(servidor, "POST", "/api/meta/marco", {"meta": "M01", "indice": 7, "feito": True})[0] == 400
    assert pedir(servidor, "POST", "/api/meta/marco", {"meta": "M01", "indice": "1", "feito": True})[0] == 400
    # ajustes: impacto, horas, prazo e pausa; o que não é permitido volta 400 sem gravar
    status, corpo, _ = pedir(
        servidor,
        "POST",
        "/api/meta/ajustar",
        {"meta": "M02", "impacto": "essencial", "custo": 6, "prazo": "2027-04-01"},
    )
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.ajuste_ok", meta="M2")
    meta = frontmatter.coagir(frontmatter.ler_arquivo(dados / "metas" / "M02.md")[0], schema.ESQUEMAS["metas"])[0]
    assert (meta["impacto"], meta["custo_h_semana_escolhido"], meta["prazo"].isoformat(), meta["confianca"]) == (
        "essencial",
        6.0,
        "2027-04-01",
        "usuario",
    )
    assert pedir(servidor, "POST", "/api/meta/ajustar", {"meta": "M02", "impacto": "essencial"})[1][
        "mensagem"
    ] == copy.texto("painel.ajuste_igual", meta="M2")
    for ruim in (
        {"meta": "M02", "custo": 0},
        {"meta": "M02", "custo": True},
        {"meta": "M02", "prazo": "amanhã"},
        {"meta": "M02", "impacto": "máximo"},
        {"meta": "M02", "estado": "arquivada"},
        {"meta": "M02", "objetivo": "../O01"},
        {"meta": "M02", "objetivo": "O07"},
        {"meta": "M02"},
        {"meta": "M02", "titulo": "outro"},
    ):
        assert pedir(servidor, "POST", "/api/meta/ajustar", ruim)[0] == 400, ruim
    assert pedir(servidor, "POST", "/api/meta/ajustar", {"meta": "M02", "estado": "pausada"})[0] == 200
    assert painel.modelo_meta(dados, AGORA, "M02")["meta"]["estado"] == "pausada"
    assert not (dados / ".lock").exists()


def test_demo_monta_dados_de_exemplo(tmp_path, monkeypatch):
    for var in [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]:
        monkeypatch.delenv(var, raising=False)
    import validar
    from goalpacer import clock

    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    import demo_painel

    dados = web.preparar_demo(tmp_path)
    assert not str(dados).startswith(str(RAIZ_REPO))
    assert not [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]  # gerar não vaza ambiente
    for var, valor in demo_painel.ambiente(tmp_path).items():
        monkeypatch.setenv(var, valor)
    assert os.environ["GP_DATA_DIR"] == str(dados)
    agora = clock.agora()
    m = painel.modelo(dados, agora)
    assert m["silencio"] is None and [d["meta"] for d in m["decisoes"]] == ["M01"] and m["alavanca"]["id"] == "M03"
    assert [o["titulo"] for o in m["objetivos"]] == [
        "Mudar de carreira para dados",
        "Ter energia para a família",
        "Ser lido pelo que escrevo",
    ]
    assert [(x["id"], x["estado"]) for x in m["metas"]] == [
        ("M03", "travada"),
        ("M02", "atencao"),
        ("M05", "ritmo"),
        ("M01", "florescendo"),
        ("M06", "florescendo"),
        ("M04", "florescendo"),
    ]
    assert {x["horizonte"] for x in m["metas"]} == {"trimestre", "semestre", "ano"}
    assert [x["id"] for x in painel.modelo_periodo(dados, agora, "ano")["metas_nivel"]] == ["M06"]
    assert sum(1 for b in m["blocos"] if b["confirmada"]) == 2 and m["espaco"]["faixa"] == "justo"
    status = painel.modelo_status(dados, agora)
    assert [e["ok"] for e in status["execucoes"]].count(False) == 1 and status["execucoes"][0]["modo"] == "job:diario"
    assert validar.main(["grafo"]) == 0


# --- rede local e pareamento ----------------------------------------------------------------

IP_TESTE = "192.168.50.7"
NOME_TESTE = "mac-teste.local"


@pytest.fixture
def rede(dados, monkeypatch):
    monkeypatch.setenv("GP_IP_REDE", IP_TESTE)
    monkeypatch.setenv("GP_NOME_LOCAL", NOME_TESTE)
    monkeypatch.setenv("GP_ENDERECO_ESCUTA", "127.0.0.1")
    monkeypatch.setattr(web, "ESPERA_ERRO_S", 0)
    servidores = []

    def abrir(https=False):
        srv = web.servir(0, dados, rede=True, https=https)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servidores.append(srv)
        return srv

    yield abrir
    for srv in servidores:
        srv.shutdown()
        srv.server_close()


def na_rede(srv, metodo, caminho, corpo=None, *, cookie=None, token=False, host=None):
    host = host or "%s:%d" % (IP_TESTE, srv.porta)
    cabecalhos = {"Origin": "http://" + host}
    if cookie:
        cabecalhos["Cookie"] = "gp_aparelho=" + cookie
    return pedir(srv, metodo, caminho, corpo, token=token, host=host, cabecalhos=cabecalhos)


def test_rede_pede_pareamento_e_lembra_o_aparelho(rede, dados):
    srv = rede()
    assert srv.endereco_rede == "http://%s:%d/" % (IP_TESTE, srv.porta)
    status, html, _ = na_rede(srv, "GET", "/")
    assert status == 200 and "Parear este aparelho" in html and srv.token not in html and "{{" not in html
    assert na_rede(srv, "GET", "/api/painel", token=True)[0] == 403
    assert na_rede(srv, "GET", "/api/pareamento", token=True)[0] == 403
    status, corpo, _ = na_rede(srv, "POST", "/api/parear", {"codigo": "000000" if srv.codigo != "000000" else "111111"})
    assert status == 403 and corpo["erro"] == copy.texto("painel.parear_errado")
    status, corpo, resposta = na_rede(srv, "POST", "/api/parear", {"codigo": srv.codigo})
    biscoito = resposta.getheader("Set-Cookie")
    assert status == 200 and "HttpOnly" in biscoito and "SameSite=Strict" in biscoito and "Max-Age=7776000" in biscoito
    token_aparelho = biscoito.split(";")[0].split("=", 1)[1]
    status, html, _ = na_rede(srv, "GET", "/", cookie=token_aparelho)
    assert status == 200 and srv.token in html and 'rel="apple-touch-icon"' in html
    status, corpo, _ = pedir(
        srv,
        "GET",
        "/api/painel",
        host="%s:%d" % (IP_TESTE, srv.porta),
        cabecalhos={"Cookie": "gp_aparelho=" + token_aparelho},
    )
    assert status == 200 and corpo["modelo"]["sub"] == "3 blocos hoje."
    status, corpo, _ = pedir(
        srv,
        "POST",
        "/api/confirmar",
        {"task_id": corpo["modelo"]["blocos"][0]["id"]},
        host=NOME_TESTE + ":%d" % srv.porta,
        cabecalhos={"Cookie": "gp_aparelho=" + token_aparelho, "Origin": "http://%s:%d" % (NOME_TESTE, srv.porta)},
    )
    assert status == 200 and corpo["modelo"]["blocos"][0]["confirmada"]
    arquivo = Path(os.environ["GP_RAIZ"]) / "jobs" / "painel-aparelhos.json"
    assert (os.name == "nt" or (arquivo.stat().st_mode & 0o777) == 0o600) and token_aparelho not in arquivo.read_text(
        encoding="utf-8"
    )
    # no Mac, o cartão mostra código, endereço e aparelhos
    status, corpo, _ = pedir(srv, "GET", "/api/pareamento")
    assert status == 200 and corpo["rede"] and corpo["codigo"] == srv.codigo and corpo["aparelhos"] == 1
    # reiniciar o painel mantém o aparelho e troca o código
    srv2 = rede()
    assert srv2.codigo is not None and na_rede(srv2, "GET", "/", cookie=token_aparelho)[1].count(srv2.token) == 1
    # esquecer aparelhos só pelo Mac; depois o cookie volta a pedir pareamento
    assert na_rede(srv2, "POST", "/api/esquecer-aparelhos", {}, cookie=token_aparelho, token=True)[0] == 403
    status, corpo, _ = pedir(srv2, "POST", "/api/esquecer-aparelhos", {})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.rede_esquecidos")
    assert "Parear este aparelho" in na_rede(srv2, "GET", "/", cookie=token_aparelho)[1]


def test_rede_trava_pareamento_depois_de_erros_e_recusa_hosts(rede):
    srv = rede()
    errado = "123456" if srv.codigo != "123456" else "654321"
    for _ in range(web.TETO_ERROS_PAREAMENTO - 1):
        assert na_rede(srv, "POST", "/api/parear", {"codigo": errado})[0] == 403
    status, corpo, _ = na_rede(srv, "POST", "/api/parear", {"codigo": errado})
    assert status == 429 and corpo["erro"] == copy.texto("painel.parear_bloqueado")
    assert na_rede(srv, "POST", "/api/parear", {"codigo": srv.codigo})[0] == 429
    assert pedir(srv, "GET", "/", token=False, host="evil.test:%d" % srv.porta)[0] == 403
    status, _, _ = pedir(
        srv,
        "POST",
        "/api/parear",
        {"codigo": srv.codigo},
        host="%s:%d" % (IP_TESTE, srv.porta),
        cabecalhos={"Origin": "http://evil.test"},
    )
    assert status == 403
    assert pedir(srv, "POST", "/api/parear", {"codigo": srv.codigo})[0] == 404  # do próprio Mac não há o que parear


def test_rede_com_https_na_mesma_porta(rede):
    """Com openssl: HTTPS para a rede (certificado autoassinado, impressão no cartão, cookie Secure), HTTP da rede
    mandado para o HTTPS, e o próprio computador segue em HTTP."""
    import socket
    import ssl

    from goalpacer import tls

    if not tls.openssl():
        pytest.skip("sem openssl nesta máquina")
    srv = rede(https=True)
    certificado = Path(os.environ["GP_RAIZ"]) / "jobs" / tls.NOME_PASTA / tls.NOME_CERTIFICADO
    assert srv.tls is not None and srv.endereco_rede == "https://%s:%d/" % (IP_TESTE, srv.porta)
    assert os.name == "nt" or ((certificado.parent / tls.NOME_CHAVE).stat().st_mode & 0o777) == 0o600
    status, _, resposta = na_rede(srv, "GET", "/checkin?x=1")
    assert status == 308 and resposta.getheader("Location") == "https://%s:%d/checkin?x=1" % (IP_TESTE, srv.porta)
    status, corpo, _ = pedir(srv, "GET", "/api/pareamento")  # o computador, em HTTP
    assert status == 200 and corpo["impressao"] == tls.impressao(certificado) and len(corpo["impressao"]) == 95

    cliente = ssl.create_default_context()
    cliente.check_hostname, cliente.verify_mode = False, ssl.CERT_NONE

    def em_https(metodo, caminho, corpo=None):
        host = "%s:%d" % (IP_TESTE, srv.porta)
        conexao = http.client.HTTPSConnection("127.0.0.1", srv.porta, timeout=10, context=cliente)
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        cabecalhos = {"Host": host, "Origin": "https://" + host, "Content-Type": "application/json"}
        conexao.request(metodo, caminho, body=dados, headers=cabecalhos)
        der = conexao.sock.getpeercert(binary_form=True)
        resposta = conexao.getresponse()
        bruto = resposta.read()
        conexao.close()
        return resposta, bruto, der

    resposta, bruto, der = em_https("GET", "/")
    assert resposta.status == 200 and "Parear este aparelho" in bruto.decode("utf-8")
    assert ssl.DER_cert_to_PEM_cert(der).strip() == certificado.read_text(encoding="utf-8").strip()
    resposta, _, _ = em_https("POST", "/api/parear", {"codigo": srv.codigo})
    assert resposta.status == 200 and "; Secure" in resposta.getheader("Set-Cookie")
    # handshake que o celular abandona (certificado não aceito) não derruba o painel
    with socket.create_connection(("127.0.0.1", srv.porta), timeout=5) as bruto_tls:
        bruto_tls.sendall(b"\x16\x03\x01\x00\x05lixo!")
    assert pedir(srv, "GET", "/api/pareamento")[0] == 200
    # reabrir o painel usa o mesmo certificado
    assert rede(https=True).tls.impressao == srv.tls.impressao


def test_tls_sem_openssl_fica_em_http(rede, monkeypatch, tmp_path):
    from goalpacer import tls

    monkeypatch.setenv("GP_OPENSSL", str(tmp_path / "nao-existe"))
    assert tls.do_painel(tmp_path / "jobs") is None
    srv = rede(https=True)
    assert srv.tls is None and srv.endereco_rede.startswith("http://")
    assert na_rede(srv, "GET", "/")[0] == 200
    falso = tmp_path / "openssl"
    falso.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    falso.chmod(0o755)
    monkeypatch.setenv("GP_OPENSSL", str(falso))
    assert tls.do_painel(tmp_path / "jobs2") is None and not list((tmp_path / "jobs2" / tls.NOME_PASTA).iterdir())


def test_sem_rede_recusa_host_da_rede(servidor, monkeypatch):
    assert pedir(servidor, "GET", "/", token=False, host="%s:%d" % (IP_TESTE, servidor.porta))[0] == 403
    status, corpo, _ = pedir(servidor, "GET", "/api/pareamento")
    assert status == 200 and corpo["rede"] is False and corpo["codigo"] is None


def test_arquivos_da_tela_inicial_e_icones_reproduziveis(servidor):
    import icones_painel

    status, manifesto, resposta = pedir(servidor, "GET", "/manifest.webmanifest", token=False)
    dados = json.loads(manifesto) if isinstance(manifesto, str) else manifesto
    assert (
        status == 200
        and dados["display"] == "standalone"
        and {i["sizes"] for i in dados["icons"]} == {"192x192", "512x512"}
    )
    for tamanho in icones_painel.TAMANHOS:
        status, _, resposta = pedir(servidor, "GET", "/icone-%d.png" % tamanho, token=False)
        assert status == 200 and resposta.getheader("Content-Type") == "image/png"
        assert (RAIZ_REPO / "web" / ("icone-%d.png" % tamanho)).read_bytes() == icones_painel.png(tamanho), (
            "regenere com scripts/icones_painel.py"
        )
    parear = (RAIZ_REPO / "web" / "parear.html").read_text(encoding="utf-8")
    chaves = set(re.findall(r"\{\{T:([a-z_]+)\}\}", parear))
    assert chaves and chaves <= set(painel.textos())
    assert "<script>" not in parear and "<script>" not in (RAIZ_REPO / "web" / "index.html").read_text(encoding="utf-8")


def test_cli_esquecer_aparelhos(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    env["GP_RAIZ"] = str(tmp_path / "raiz")
    proc = subprocess.run(
        [sys.executable, str(RAIZ_REPO / "scripts" / "web.py"), "--esquecer-aparelhos"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == copy.texto("painel.rede_esquecidos")
    assert json.loads((tmp_path / "raiz" / "jobs" / "painel-aparelhos.json").read_text(encoding="utf-8")) == {
        "aparelhos": []
    }


# --- observabilidade e limites do servidor (análise de 13/09: O1, O4, R1, R3, R4) ------------------


@pytest.fixture
def logs(tmp_path, monkeypatch):
    pasta = tmp_path / "logs"
    monkeypatch.setenv("GP_LOGS_DIR", str(pasta))
    return pasta


def eventos(pasta, tipo=None):
    linhas = []
    for arquivo in sorted(pasta.glob("eventos-*.jsonl")):
        linhas += [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [l for l in linhas if tipo is None or l["tipo"] == tipo]


def test_cada_pedido_vira_uma_linha_sem_query_nem_token(servidor, logs):
    assert pedir(servidor, "GET", "/api/painel?data=2026-09-28")[0] == 200
    assert pedir(servidor, "GET", "/api/meta?id=M01")[0] == 200
    assert pedir(servidor, "GET", "/nada/%s" % servidor.token, token=False)[0] == 404
    assert pedir(servidor, "POST", "/api/sentimento", {"meta": "M01", "valor": "firme"})[0] == 200
    for _ in range(
        100
    ):  # a linha do pedido é gravada depois da resposta: em máquina lenta ela chega um instante depois
        linhas = eventos(logs, "painel")
        if len(linhas) >= 4:
            break
        time.sleep(0.05)
    assert [(l["metodo"], l["rota"], l["status"]) for l in linhas] == [
        ("GET", "/api/painel", 200),
        ("GET", "/api/meta", 200),
        ("GET", "outra", 404),
        ("POST", "/api/sentimento", 200),
    ]
    assert all(isinstance(l["ms"], float) and l["origem"] == "local" and l["bytes"] > 0 for l in linhas)
    bruto = "".join(p.read_text(encoding="utf-8") for p in logs.glob("*.jsonl"))
    assert servidor.token not in bruto and "data=" not in bruto and "M01" not in bruto and "firme" not in bruto
    assert os.name == "nt" or (logs.stat().st_mode & 0o777) == 0o700


def test_erro_inesperado_responde_json_e_fica_registrado(servidor, logs, monkeypatch):
    def quebra(*_, **__):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(painel, "modelo_metas", quebra)
    monkeypatch.setitem(web.TELAS_GET, "/api/metas", quebra)
    status, corpo, _ = pedir(servidor, "GET", "/api/metas")
    assert status == 500 and corpo["ok"] is False and corpo["classe"] == "Desconhecida"
    for _ in range(60):  # o registro do erro sai depois da resposta: no Windows, às vezes um instante depois
        if eventos(logs, "painel_erro") and eventos(logs, "painel"):
            break
        time.sleep(0.05)
    erro = eventos(logs, "painel_erro")
    assert erro and erro[0]["erro"] == "RuntimeError" and erro[0]["rota"] == "/api/metas"
    assert eventos(logs, "painel")[-1]["status"] == 500
    assert pedir(servidor, "GET", "/api/objetivos")[0] == 200  # o servidor segue de pé


def test_erro_do_front_registrado_com_forma_e_teto(servidor, logs):
    corpo = {
        "mensagem": "x is not a function",
        "arquivo": "/js/telas/meta.js",
        "linha": 12,
        "coluna": 7,
        "tela": "meta",
    }
    assert pedir(servidor, "POST", "/api/erro-front", corpo, token=False)[0] == 403
    assert pedir(servidor, "POST", "/api/erro-front", dict(corpo, tela="<script>"))[0] == 200
    registro = eventos(logs, "erro_front")
    assert registro == [
        dict(registro[0], mensagem="x is not a function", arquivo="/js/telas/meta.js", linha=12, coluna=7, tela="outra")
    ]
    for _ in range(web.TETO_ERROS_FRONT_MIN):
        pedir(servidor, "POST", "/api/erro-front", corpo)
    assert pedir(servidor, "POST", "/api/erro-front", corpo)[0] == 429
    status, _, _ = pedir(
        servidor, "POST", "/api/confirmar", {"task_id": "D-2026-09-28-01", "sobra": "x" * (web.TETO_CORPO + 10)}
    )
    assert status == 413


def test_conexao_parada_cai_e_teto_de_conexoes(servidor, logs):
    assert web.Tratador.timeout == web.TIMEOUT_CONEXAO_S
    servidor.vagas = threading.BoundedSemaphore(1)
    servidor.vagas.acquire()  # como se 32 conexões estivessem abertas
    conexao = http.client.HTTPConnection("127.0.0.1", servidor.porta, timeout=5)
    with pytest.raises((http.client.RemoteDisconnected, ConnectionError)):  # Windows: ConnectionAbortedError
        conexao.request("GET", "/", headers={"Host": "127.0.0.1:%d" % servidor.porta})
        conexao.getresponse()
    conexao.close()
    servidor.vagas.release()
    assert pedir(servidor, "GET", "/", token=False)[0] == 200
    assert eventos(logs, "painel_recusa")


def test_rajada_de_codigos_errados_nao_passa_do_teto(rede):
    srv = rede()
    errado = "123456" if srv.codigo != "123456" else "654321"
    resultados = []
    fios = [
        threading.Thread(target=lambda: resultados.append(na_rede(srv, "POST", "/api/parear", {"codigo": errado})[0]))
        for _ in range(30)
    ]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()
    assert srv.erros_pareamento == web.TETO_ERROS_PAREAMENTO
    assert sorted(set(resultados)) == [403, 429] and resultados.count(403) == web.TETO_ERROS_PAREAMENTO - 1


def test_manifest_segue_o_idioma_da_instalacao(servidor, monkeypatch):
    """R6 (análise de 13/09)."""
    status, corpo, resposta = pedir(servidor, "GET", "/manifest.webmanifest", token=False)
    assert (
        status == 200
        and json.loads(corpo)["lang"] == "pt-BR"
        and resposta.getheader("Content-Type").startswith("application/manifest+json")
    )
    monkeypatch.setenv("GP_IDIOMA", "en")
    assert json.loads(pedir(servidor, "GET", "/manifest.webmanifest", token=False)[1])["lang"] == "en"


def test_anuncio_da_rede_com_e_sem_https(capsys):
    from types import SimpleNamespace

    from goalpacer import tls

    falso = SimpleNamespace(endereco="http://127.0.0.1:1/", rede=True, endereco_rede=None, codigo="123456", tls=None)
    web._anunciar(falso)
    saida = capsys.readouterr().out
    assert copy.texto("painel.rede_sem_endereco") in saida and copy.texto("painel.rede_aviso") in saida
    falso.endereco_rede, falso.tls = "https://10.0.0.2:1/", tls.Tls(None, "AB:CD")
    web._anunciar(falso)
    saida = capsys.readouterr().out
    assert "https://10.0.0.2:1/" in saida and copy.texto("painel.rede_impressao", impressao="AB:CD") in saida


def test_conexao_parada_antes_do_primeiro_byte_e_descartada():
    from types import SimpleNamespace

    class Parada:
        def settimeout(self, _s):
            return None

        def recv(self, *_a):
            raise OSError("timed out")

    class Fechada(Parada):
        def recv(self, *_a):
            return b""

    falso = SimpleNamespace(tls=SimpleNamespace(contexto=None))
    assert web.Painel._conexao(falso, Parada()) is None
    fechada = Fechada()
    assert web.Painel._conexao(falso, fechada) is fechada
