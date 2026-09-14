"""Golden master do balanço do mês antes da refatoração: um mês com metas em todos os estados, agenda ocupada,
blocos de hoje já gerados, feitas confirmadas e perfil, em dois instantes (antes e depois do horário útil).

O esperado mora em tests/fixtures/caracterizacao/balanco-calcular.json (sintético). Para regravar depois de uma
mudança intencional nos números: GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_balanco_caracterizacao.py
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import balanco, registro as reg

TZ = ZoneInfo("America/Sao_Paulo")
ESPERADO = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "balanco-calcular.json"
METAS_CAL = "metas-fixture@group.calendar.google.com"
CONTEXTO = {
    "timezone": "America/Sao_Paulo",
    "instalacao_id": "inst-fixture-01",
    "calendar_id_metas": METAS_CAL,
    "calendar_id_primario": "pessoa@exemplo.test",
    "horario_util_seg_sex": "07:00-10:00",
    "horario_util_sab": "09:00-12:00",
    "horario_util_dom": "",
    "buffer_min": 10,
    "restricoes_horario": [],
}


def _meta(meta_id, h, semanas, prazo, **extra):
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
        "criado_em": datetime(2026, 8, 3, 10, tzinfo=TZ),
    }
    m.update(extra)
    return m


def _bloco(meta, inicio, horas, estado, origem="inferido", dia=None):
    comeco = datetime(*inicio, tzinfo=TZ)
    return {
        "meta": meta,
        "inicio": comeco,
        "fim": comeco + (datetime(2000, 1, 1, 1) - datetime(2000, 1, 1)) * horas,
        "duracao_h": horas,
        "estado": estado,
        "origem": origem,
        "_dia": dia or comeco.date().isoformat(),
    }


def _evento(ev_id, inicio, fim, **extra):
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


def _cenario(agora):
    metas = {
        "M01": _meta("M01", 4, 12, date(2026, 12, 15)),
        "M02": _meta("M02", 6, 10, date(2026, 11, 20), prazo_externo=True),
        "M03": _meta("M03", 2, 8, date(2026, 10, 2)),  # vence no meio do mês
        "M04": _meta("M04", 3, 10, date(2027, 1, 30), estado="pausada"),
    }
    registro = reg.vazio()
    for task, meta, horas in (("D-2026-09-29-01", "M01", 1.5), ("D-2026-09-30-01", "M02", 2.0)):
        reg.registrar_feita(registro, meta, task, horas, "confirmado", ts=datetime(2026, 9, 30, 12, tzinfo=TZ))
    blocos = {
        "D-2026-09-29-01": _bloco("M01", (2026, 9, 29, 7, 0), 1.5, "feita", "confirmado"),
        "D-2026-09-30-01": _bloco("M02", (2026, 9, 30, 7, 0), 2.0, "feita", "confirmado"),
        "D-2026-10-05-01": _bloco("M01", (2026, 10, 5, 7, 0), 1.0, "planejada"),
        "D-2026-10-05-02": _bloco("M02", (2026, 10, 5, 8, 10), 1.0, "planejada"),
        "D-2026-10-01-01": _bloco("M02", (2026, 10, 6, 9, 0), 0.5, "reagendada", dia="2026-10-01"),
    }
    eventos = [
        _evento("reuniao", "2026-10-06T07:30:00-03:00", "2026-10-06T08:30:00-03:00"),
        _evento("feriado", "2026-10-12", "2026-10-13", event_type="outOfOffice"),
        _evento("livre", "2026-10-07T07:00:00-03:00", "2026-10-07T10:00:00-03:00", transparency="transparent"),
    ]
    perfil = {"metas": {"M01": {"progresso_pct": 12.5, "progresso_presumido_pct": 3.0, "ritmo_esperado_pct": 20.0}}}
    return balanco.calcular(
        mes="2026-10",
        contexto=CONTEXTO,
        metas=metas,
        registro=registro,
        perfil=perfil,
        blocos=blocos,
        eventos=eventos,
        agora=agora,
    )


INSTANTES = {
    "manha": datetime(2026, 10, 5, 8, 0, tzinfo=TZ),
    "noite": datetime(2026, 10, 5, 21, 0, tzinfo=TZ),
}


def test_balanco_do_mes_igual_ao_golden_master():
    obtido = {nome: _cenario(agora) for nome, agora in INSTANTES.items()}
    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO.read_text(encoding="utf-8"))
