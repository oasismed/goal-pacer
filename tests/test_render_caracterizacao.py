"""Caracterização do render antes da refatoração (D-04): email em texto e HTML nos dois idiomas e em cada estado
(decisão, primeiro dia, dia sem bloco, acima dos tetos), ids dos blocos e a leitura do dia.

Mudança intencional numa superfície: GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_render_caracterizacao.py
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import copy, render
from goalpacer.base import GpErro

ESPERADO = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "render.json"
FIXTURE_DIA = Path(__file__).resolve().parent / "fixtures" / "mensal" / "dados" / "dias" / "2026-09-25.md"
TZ = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 9, 28)


def _bloco(n: int, estado: str = "planejada", **extra):
    inicio = datetime(2026, 9, 28, 7, 0, tzinfo=TZ) + timedelta(minutes=45 * n)
    bloco = {
        "id": "D-2026-09-28-%02d" % n,
        "meta": "M0%d" % (1 + n % 3),
        "titulo": "Bloco <%d> & cia" % n,
        "inicio": inicio,
        "fim": inicio + timedelta(minutes=40),
        "estado": estado,
        "porque": "porque %d" % n if n % 2 else "",
        "efeito": "M1 40% → 42%" if n % 3 == 0 else "",
    }
    bloco.update(extra)
    return bloco


def _dia(**mudancas):
    dia = {
        "data": DIA,
        "fm": {},
        "titulo": "Segunda, 28/09",
        "resumo": "8 blocos · 1 confirmada",
        "blocos": [_bloco(n) for n in range(1, 9)] + [_bloco(9, "feita"), _bloco(10, "sem_sinal")],
        "desde_dia": "sáb",
        "desde_contagem": "1 confirmada · 2 feita?",
        "desde": ["linha %d" % i for i in range(8)],
        "progresso": [copy.texto("email.comecando")] + ["M%d segue firme" % i for i in range(1, 11)],
        "progresso_manchete": "Semana em ritmo.",
        "avisos": ["aviso %d" % i for i in range(5)],
    }
    dia.update(mudancas)
    return dia


CASOS = {
    "cheio": ({}, {}),
    "decisao_e_primeiro_dia": (
        {},
        {"primeiro_dia": True, "decisao": ("M3", "Com as janelas até 30/10 dá para cobrir 62%.")},
    ),
    "vazio": (
        {
            "blocos": [],
            "desde": [],
            "desde_contagem": "",
            "progresso": [],
            "avisos": [],
            "titulo": "",
            "progresso_manchete": "",
        },
        {},
    ),
    "so_contagem_e_comecando": ({"desde": [], "progresso": [copy.texto("email.comecando")]}, {}),
}


def _emails():
    saida = {}
    for idioma in ("pt-BR", "en"):
        copy.usar(idioma)
        try:
            for nome, (dia, opcoes) in CASOS.items():
                modelo = render.modelo_email(_dia(**dia), **opcoes)
                assunto, corpo = render.email_texto(modelo)
                saida["%s/%s" % (idioma, nome)] = {
                    "modelo": json.loads(json.dumps(modelo, default=str)),
                    "assunto": assunto,
                    "corpo": corpo.split("\n"),
                    "html": render.email_html(modelo),
                }
        finally:
            copy.usar(None)
    return saida


def _ids():
    anteriores = [
        {"id": "D-2026-09-28-01", "meta": "M01", "titulo": "Ler", "calendar_event_id": "ev1", "calendar_id": "metas"},
        {"id": "D-2026-09-28-03", "meta": "M02", "titulo": "Correr"},
        {"id": None, "meta": "M03", "titulo": "sem id"},
    ]
    novos = [
        {"meta": "M02", "titulo": "Correr", "inicio": "08:00"},
        {"meta": "M01", "titulo": "Ler", "inicio": "07:00", "calendar_event_id": "ja-tinha"},
        {"meta": "M01", "titulo": "Ler", "inicio": "09:00"},
        {"meta": "M03", "titulo": "Novo", "inicio": "07:00"},
    ]
    return render.atribuir_ids(novos, anteriores, DIA, reservados=["D-2026-09-28-02"])


def test_render_igual_ao_golden_master():
    obtido = {
        "emails": _emails(),
        "ids": _ids(),
        "ler_dia": json.loads(json.dumps(render.ler_dia(FIXTURE_DIA.read_text(encoding="utf-8")), default=str)),
    }
    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO.read_text(encoding="utf-8"))


def test_ids_acima_de_99_e_bloco_invalido():
    ocupados = ["D-2026-09-28-%02d" % n for n in range(1, 100)]
    with pytest.raises(GpErro, match="mais de 99 blocos"):
        render.atribuir_ids([{"meta": "M01", "titulo": "x", "inicio": "07:00"}], [], DIA, reservados=ocupados)
    texto = FIXTURE_DIA.read_text(encoding="utf-8").replace("- estado: ", "- estado: inventado_", 1)
    with pytest.raises(GpErro, match="bloco D-"):
        render.ler_dia(texto)
