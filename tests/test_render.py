"""Testes de goalpacer.render: ids preservados, blocos, seções, roundtrip pelo parser."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from goalpacer import copy, frontmatter, render, schema
from goalpacer.base import GpErro

TZ = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 9, 28)


def novo(meta: str, titulo: str, hora: int, horas: float = 1.0, **extra) -> dict:
    inicio = datetime(2026, 9, 28, hora, 0, tzinfo=TZ)
    b = {
        "meta": meta,
        "titulo": titulo,
        "semana": "2026-W40",
        "inicio": inicio,
        "fim": inicio + timedelta(hours=horas),
        "duracao_h": horas,
        "estado": "planejada",
        "origem": "inferido",
        "porque": "porquê",
        "efeito": "se feita: M1 41% → 44%",
    }
    b.update(extra)
    return b


def test_titulo_e_rotulo():
    assert render.titulo_bloco("  Título   com   espaços ") == "Título com espaços"
    assert len(render.titulo_bloco("x" * 80)) == 60 and render.titulo_bloco("x" * 80).endswith("…")
    assert render.rotulo_meta("M01") == "M1" and render.rotulo_meta("M12") == "M12" and render.rotulo_meta("x") == "x"
    assert copy.dia_curto(DIA) == "seg" and copy.dia_curto(date(2026, 10, 3)) == "sáb"
    assert (
        render.hora_curta(datetime(2026, 9, 28, 9, 0, tzinfo=TZ)) == "9h"
        if False
        else render.hora_curta(datetime(2026, 9, 28, 9, 0, tzinfo=TZ)) == "09h"
    )
    assert render.hora_curta(datetime(2026, 9, 28, 14, 30, tzinfo=TZ)) == "14h30"


def test_atribuir_ids_preserva_por_meta_e_titulo():
    anteriores = [
        {
            "id": "D-2026-09-28-01",
            "meta": "M01",
            "titulo": "Estatística",
            "calendar_event_id": "evt-a",
            "calendar_id": "metas",
        },
        {"id": "D-2026-09-28-03", "meta": "M02", "titulo": "Corrida", "calendar_event_id": "evt-b"},
        {"id": "D-2026-09-28-04", "meta": "M01", "titulo": "Estatística"},
    ]
    novos = [
        novo("M02", "Corrida", 8),
        novo("M01", "Estatística", 9),
        novo("M01", "Estatística", 11),
        novo("M01", "Estatística", 15),
        novo("M03", "Outra", 16),
    ]
    saida = render.atribuir_ids(novos, anteriores, DIA)
    assert [b["id"] for b in saida] == [
        "D-2026-09-28-03",
        "D-2026-09-28-01",
        "D-2026-09-28-04",
        "D-2026-09-28-02",
        "D-2026-09-28-05",
    ]
    assert (
        saida[0]["calendar_event_id"] == "evt-b"
        and saida[1]["calendar_event_id"] == "evt-a"
        and saida[1]["calendar_id"] == "metas"
    )
    assert "calendar_event_id" not in saida[3]
    # determinístico e sem anteriores
    assert [b["id"] for b in render.atribuir_ids(novos, [], DIA)] == [
        "D-2026-09-28-01",
        "D-2026-09-28-02",
        "D-2026-09-28-03",
        "D-2026-09-28-04",
        "D-2026-09-28-05",
    ]
    assert render.atribuir_ids([], anteriores, DIA) == []
    # ids reservados (blocos feitos ou movidos que ficam no dia) nunca são reutilizados
    reservado = render.atribuir_ids(
        [novo("M03", "Outra", 16)], [], DIA, reservados=["D-2026-09-28-01", "D-2026-09-28-02"]
    )
    assert reservado[0]["id"] == "D-2026-09-28-03"


def test_render_dia_roundtrip_e_secoes():
    blocos = render.atribuir_ids([novo("M01", "Estatística", 9, 1.5), novo("M02", "Corrida", 18, 0.75)], [], DIA)
    blocos[0]["calendar_event_id"] = "evt-1"
    blocos[0]["calendar_id"] = "metas-fixture@group.calendar.google.com"
    fixo = novo(
        "M01", "Feito de manhã", 7, 0.5, estado="feita", origem="confirmado", duracao_real_h=0.75, id="D-2026-09-28-09"
    )
    progresso = {
        "manchete": "O que mais move esta semana: Corrida (M2).",
        "linhas": ["M1 Estatística: florescendo, com folga para o prazo", "M2 Corrida: pede atenção"],
    }
    texto = render.render_dia(
        DIA,
        "run-1",
        [*blocos, fixo],
        resumo_linha="2 blocos hoje.",
        progresso=progresso,
        desde=("sáb", "1 feita?", ["Curso (M1): feita?"]),
        avisos=["um aviso", ""],
        decisao_pendente="M01",
    )
    fm, corpo = frontmatter.separar(texto)
    dados = frontmatter.parse(fm)
    assert dados == {
        "data": DIA,
        "run_id": "run-1",
        "resumo_confirmadas": 1,
        "resumo_presumidas": 0,
        "resumo_movidas": 0,
        "decisao_pendente": "M01",
    }
    assert schema.validar_registro("dia", dados) == []
    secoes = [l for l in corpo.split("\n") if l.startswith("## ")]
    assert secoes == ["## Hoje", "## Desde sáb", "## Progresso", "## Avisos"]
    assert "# Segunda, 28/09" in corpo and "2 blocos hoje." in corpo
    lidos = frontmatter.parse_blocos(corpo)
    assert [b["id"] for b in lidos] == ["D-2026-09-28-09", "D-2026-09-28-01", "D-2026-09-28-02"]  # ordem por início
    for bloco in lidos:
        bloco.pop("_linha")
        coagido, erros = frontmatter.coagir(bloco, schema.ESQUEMAS["task"])
        assert erros == [] and schema.validar_registro("task", coagido) == []
    assert lidos[1]["calendar_event_id"] == "evt-1" and lidos[1]["efeito"] == "se feita: M1 41% → 44%"
    assert lidos[0]["duracao_real_h"] == 0.75 and lidos[0]["estado"] == "feita"
    assert (
        "O que mais move esta semana: Corrida (M2).\n\n- M1 Estatística: florescendo, com folga para o prazo\n- M2 Corrida: pede atenção"
        in corpo
    )
    assert "- um aviso" in corpo and "- \n" not in corpo
    # sem blocos, sem desde/avisos: seções condicionais somem; motivo no front-matter
    texto = render.render_dia(
        DIA, "run-2", [], resumo_linha="Hoje sem janela livre.", progresso={}, motivo="sem_janela"
    )
    fm, corpo = frontmatter.separar(texto)
    assert frontmatter.parse(fm)["motivo"] == "sem_janela"
    assert [l for l in corpo.split("\n") if l.startswith("## ")] == ["## Hoje", "## Progresso"]
    assert "(sem blocos)" in corpo and "- começando" in corpo
    assert chr(0x2014) not in texto
    with pytest.raises(GpErro):
        render.render_dia(DIA, "run-3", [dict(blocos[0], estado="feita?")], resumo_linha="x", progresso={})
