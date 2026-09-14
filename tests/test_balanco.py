"""Testes de goalpacer.balanco: formatação, datas do mês, oferta, simulação, decisões, recalibração, render e hash."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from goalpacer import balanco, frontmatter, registro as reg, schema, tom

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
METAS_CAL = "metas-fixture@group.calendar.google.com"
CONTEXTO = {
    "timezone": "America/Sao_Paulo",
    "instalacao_id": "inst-fixture-01",
    "calendar_id_metas": METAS_CAL,
    "calendar_id_primario": "pessoa@exemplo.test",
    "horario_util_seg_sex": "08:00-10:00",
    "horario_util_sab": "",
    "horario_util_dom": "",
    "buffer_min": 10,
}


def meta(meta_id: str, h: float, semanas: int, prazo: date, **extra) -> dict:
    m = {
        "id": meta_id,
        "titulo": "Meta " + meta_id,
        "horizonte": "trimestre",
        "prazo": prazo,
        "estado": "ativa",
        "prazo_externo": False,
        "custo_h_semana_escolhido": float(h),
        "semanas_pesquisa": semanas,
        "confianca": "media",
        "criado_em": datetime(2026, 9, 1, 10, tzinfo=TZ),
    }
    m.update(extra)
    return m


def ev(ev_id: str, inicio: str, fim: str, **extra) -> dict:
    e = {
        "id": ev_id,
        "calendar_id": "pessoa@exemplo.test",
        "start": inicio,
        "end": fim,
        "all_day": len(inicio) == 10,
        "status": "confirmed",
        "transparency": "opaque",
        "self_response": "",
        "event_type": "default",
        "gp_key": None,
        "summary": None,
        "description": None,
    }
    e.update(extra)
    return e


def test_formatacao_e_datas():
    assert (
        balanco.horas(12.5) == "12,5"
        and balanco.horas(4.0) == "4"
        and balanco.horas(0) == "0"
        and balanco.horas(8.833) == "8,8"
    )
    assert balanco.pct(47.5) == "48%" and balanco.pct(100) == "100%"
    assert balanco.mes_e_ano("2026-10") == "outubro/2026"
    assert balanco.ultimo_dia_do_mes("2026-02") == date(2026, 2, 28) and balanco.ultimo_dia_do_mes("2026-12") == date(
        2026, 12, 31
    )
    assert balanco.semanas("2026-10") == ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]
    inicio, fim = balanco.janela_leitura("2026-10", AGORA, TZ)
    assert inicio == datetime(2026, 9, 28, tzinfo=TZ) and fim == datetime(2026, 11, 2, tzinfo=TZ)
    inicio, fim = balanco.janela_leitura("2026-09", AGORA, TZ)  # mês que já acabou para a leitura
    assert fim == inicio
    assert balanco.decidir(100, False) == "manter" and balanco.decidir(70, False) == "reduzir"
    assert balanco.decidir(69.9, False) == "adiar" and balanco.decidir(10, True) == "renegociar"


def calcular(metas, eventos=(), blocos=None, registro=None, perfil=None, agora=AGORA, mes="2026-10"):
    return balanco.calcular(
        mes=mes,
        contexto=CONTEXTO,
        metas=metas,
        registro=registro or reg.vazio(),
        perfil=perfil or {},
        blocos=blocos or {},
        eventos=list(eventos),
        agora=agora,
    )


def test_oferta_por_semana_com_regras_de_ocupacao():
    eventos = [
        ev("ter", "2026-09-29T08:30:00-03:00", "2026-09-29T09:00:00-03:00"),
        ev("livre", "2026-09-30T08:00:00-03:00", "2026-09-30T09:00:00-03:00", transparency="transparent"),
        ev("ooo", "2026-10-12", "2026-10-13", event_type="outOfOffice"),
        ev("recusado", "2026-10-13T08:00:00-03:00", "2026-10-13T10:00:00-03:00", self_response="declined"),
        ev(
            "nosso",
            "2026-10-14T08:00:00-03:00",
            "2026-10-14T10:00:00-03:00",
            calendar_id=METAS_CAL,
            gp_key="gp:D-2026-10-14-01/inst-fixture-01",
        ),
    ]
    res = calcular({"M01": meta("M01", 1, 10, date(2026, 12, 15))}, eventos)
    ofertas = {s["semana"]: s["oferta_h"] for s in res["semanas"]}
    assert ofertas == {"2026-W40": 8.83, "2026-W41": 10.0, "2026-W42": 8.0, "2026-W43": 10.0, "2026-W44": 10.0}
    assert res["oferta_mes_h"] == 46.83
    # hoje depois do fim do horário útil: hoje não oferece nada
    tarde = calcular({"M01": meta("M01", 1, 10, date(2026, 12, 15))}, agora=datetime(2026, 9, 28, 11, 0, tzinfo=TZ))
    assert tarde["semanas"][0]["oferta_h"] == 8.0
    # no meio do horário útil: só o que resta
    meio = calcular({"M01": meta("M01", 1, 10, date(2026, 12, 15))}, agora=datetime(2026, 9, 28, 9, 0, tzinfo=TZ))
    assert meio["semanas"][0]["oferta_h"] == 9.0


def test_decisoes_e_cobertura():
    metas = {
        "M01": meta("M01", 4, 12, date(2026, 12, 15)),
        "M02": meta("M02", 10, 20, date(2027, 3, 1), prazo_externo=True),
        "M03": meta("M03", 1, 30, date(2027, 6, 30), estado="arquivada"),
        "M04": meta("M04", 6, 20, date(2027, 3, 1)),
    }
    res = calcular(metas)
    m = res["metas"]
    # 20 h pedidas por semana para 10 h de oferta: a falta é dividida (ordem por cobertura/demanda), ninguém fica coberto
    assert m["M02"]["decisao"] == "renegociar" and m["M02"]["cobertura_pct"] < 70
    assert m["M01"]["decisao"] in ("adiar", "reduzir") and m["M04"]["decisao"] in ("adiar", "reduzir")
    assert m["M04"]["adiar_para"] > "2027-03-01"
    assert m["M03"]["decisao"] is None and m["M03"]["demanda_mes_h"] == 0.0
    assert res["apertado"] is True
    assert all(s["metas"]["M01"]["demanda_h"] == 4.0 for s in res["semanas"])
    alocado_semana = [sum(v["alocado_h"] for v in s["metas"].values()) for s in res["semanas"]]
    assert all(a <= s["oferta_h"] + 1e-9 for a, s in zip(alocado_semana, res["semanas"]))
    # sem as metas grandes, M01 cabe
    res = calcular({"M01": metas["M01"]})
    assert res["metas"]["M01"]["decisao"] == "manter" and res["metas"]["M01"]["cobertura_pct"] == 100.0
    for semana in res["semanas"]:
        for valores in semana["metas"].values():
            assert 0 <= valores["cobertura_pct"] <= 100
    # uma meta só, pequena: folgado
    res = calcular({"M01": meta("M01", 2, 12, date(2026, 12, 15))})
    assert res["apertado"] is False and res["metas"]["M01"]["decisao"] == "manter"
    assert res["metas"]["M01"]["alocado_mes_h"] >= res["metas"]["M01"]["demanda_mes_h"]


def test_blocos_existentes_contam_e_ocupam():
    metas = {"M01": meta("M01", 4, 12, date(2026, 12, 15))}
    blocos = {
        "D-2026-09-28-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 28, 8, 0, tzinfo=TZ),
            "fim": datetime(2026, 9, 28, 10, 0, tzinfo=TZ),
            "duracao_h": 2.0,
            "estado": "planejada",
            "origem": "inferido",
            "_dia": "2026-09-28",
        },
        "D-2026-09-22-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 29, 8, 0, tzinfo=TZ),
            "fim": datetime(2026, 9, 29, 9, 0, tzinfo=TZ),
            "duracao_h": 1.0,
            "estado": "reagendada",
            "origem": "inferido",
            "_dia": "2026-09-22",
        },
    }
    res = calcular(metas, blocos=blocos)
    w40 = res["semanas"][0]["metas"]["M01"]
    assert w40["alocado_h"] == 4.0  # 2 (hoje, do diário) + 1 (reagendado) + 1 simulado no resto da semana
    assert res["semanas"][0]["oferta_h"] == 10.0  # nossos blocos não reduzem a oferta


def test_recalibracao():
    m = meta("M01", 4, 12, date(2026, 12, 15))
    r = reg.vazio()
    assert balanco.recalibracao(m, r, date(2026, 9, 28)) is None
    for task, horas in (("D-2026-09-15-01", 1.0), ("D-2026-09-17-01", 0.5), ("D-2026-09-22-01", 1.5)):
        reg.registrar_feita(r, "M01", task, horas, "confirmado")
    assert balanco.recalibracao(m, r, date(2026, 9, 28)) == 1.5  # W38 1,5 h e W39 1,5 h, as duas longe de 4
    reg.registrar_feita(r, "M01", "D-2026-09-23-01", 2.5, "confirmado")
    assert balanco.recalibracao(m, r, date(2026, 9, 28)) is None  # W39 com 4 h: dentro dos 30%
    assert (
        balanco.recalibracao(
            meta("M01", 4, 12, date(2026, 12, 15), criado_em=datetime(2026, 9, 20, tzinfo=TZ)), r, date(2026, 9, 28)
        )
        is None
    )


def test_render_plano_hash_e_prosa():
    metas = {
        "M01": meta("M01", 4, 12, date(2026, 12, 15)),
        "M02": meta("M02", 10, 20, date(2027, 3, 1), prazo_externo=True),
    }
    res = calcular(metas)
    prosa = balanco.prosa_template(res)
    assert set(prosa) == {"resumo", "m01", "m02"} and all(tom.ok(t) for t in prosa.values())
    assert "renegociar o prazo" in prosa["m02"] and "31/10" in prosa["m02"]
    evidencias = [("2026-09-20", "gmail", "M01", "matrícula confirmada")]
    texto = balanco.render_plano(
        res,
        prosa,
        evidencias,
        hash_metas=schema.hash_metas(metas.values()),
        fontes=["whatsapp", "gmail"],
        run_id="r1",
        notas=["whatsapp: export lido"],
    )
    fm, corpo = frontmatter.separar(texto)
    dados = frontmatter.parse(fm)
    assert dados["fontes"] == ["gmail", "whatsapp"] and schema.validar_registro("plano", dados) == []
    assert dados["hash_numeros"] == balanco.hash_numeros(corpo)
    secoes = [l for l in corpo.split("\n") if l.startswith("## ")]
    assert secoes == ["## Balanço", "## Metas", "## Semanas", "## Evidências", "## Decisões"]
    assert (
        "### M01 Meta M01" in corpo
        and "### 2026-W44" in corpo
        and "- evidencia: 2026-09-20 gmail M01: matrícula confirmada" in corpo
    )
    assert "- nota: whatsapp: export lido" in corpo and "- M02: Com as janelas até 31/10" in corpo
    assert balanco.extrair_prosa(texto) == prosa
    # trocar a prosa não muda o hash; trocar um número muda
    outra = texto.replace("<!-- prosa:m01 -->\n%s\n" % prosa["m01"], "<!-- prosa:m01 -->\nTexto novo à mão.\n")
    assert outra != texto
    assert balanco.hash_numeros(frontmatter.separar(outra)[1]) == dados["hash_numeros"]
    alterado = corpo.replace("| mês |", "| mes |")
    assert balanco.hash_numeros(alterado) != dados["hash_numeros"]
    assert tom.violacoes(schema.RE_BLOCO_PROSA.sub("", texto)) == []
    assert chr(0x2014) not in texto
    semana = balanco.render_semana(res, res["semanas"][0], "r1")
    fm_s, corpo_s = frontmatter.separar(semana)
    assert schema.validar_registro("semana", frontmatter.parse(fm_s)) == []
    assert "# Semana 2026-W40 (28/09 a 04/10)" in corpo_s and "| M1 |" in corpo_s
    assert balanco.secao_semana_existe(texto, "2026-W40") and not balanco.secao_semana_existe(texto, "2026-W45")
    assert (
        balanco.precisa_regerar(None)
        and balanco.precisa_regerar("  ")
        and balanco.precisa_regerar("x <!-- prosa:atualizar -->")
    )
    assert not balanco.precisa_regerar("texto")
