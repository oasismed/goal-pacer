"""Golden master do keep+diff no calendário Metas antes da refatoração: todos os casos de uma vez (bloco novo,
mantido, janela mudada, chave velha, casado só pela gp_key, cancelado com e sem evento, feito, duplicata, órfão de
hoje e de outro dia, evento cancelado, evento de outra instalação e ops inválidas).

Esperado em tests/fixtures/caracterizacao/calendar-ops-planejar.json. Regravar depois de mudança intencional:
GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_calendar_ops_caracterizacao.py
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import calendar_ops as co
from goalpacer.base import GpErro

TZ = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 9, 28)
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
METAS = "metas-fixture@group.calendar.google.com"
CONTEXTO = {
    "calendar_id_metas": METAS,
    "calendar_id_primario": "pessoa@exemplo.test",
    "instalacao_id": "inst-fixture-01",
    "timezone": "America/Sao_Paulo",
    "lembretes": "nao",
}
ESPERADO = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "calendar-ops-planejar.json"


def _bloco(sufixo, hora, estado="planejada", **extra):
    inicio = datetime(2026, 9, 28, hora, 0, tzinfo=TZ)
    b = {
        "id": "D-2026-09-28-" + sufixo,
        "titulo": "Bloco " + sufixo,
        "meta": "M01",
        "semana": "2026-W40",
        "inicio": inicio,
        "fim": inicio + timedelta(hours=1),
        "duracao_h": 1.0,
        "porque": "porquê",
        "efeito": "",
        "estado": estado,
        "origem": "inferido",
    }
    b.update(extra)
    return b


def _evento(ev_id, chave, hora, dia="2026-09-28", created="2026-09-27T07:00:00Z", **extra):
    inicio = datetime.fromisoformat("%sT%02d:00:00-03:00" % (dia, hora))
    e = {
        "id": ev_id,
        "calendar_id": METAS,
        "start": inicio.isoformat(),
        "end": (inicio + timedelta(hours=1)).isoformat(),
        "all_day": False,
        "status": "confirmed",
        "gp_key": chave,
        "created": created,
        "summary": "[GP] x",
        "description": "x",
    }
    e.update(extra)
    return e


def _chave(task, inst="inst-fixture-01"):
    return "gp:%s/%s" % (task, inst)


def _cenario():
    blocos = [
        _bloco("01", 7),  # novo: create
        _bloco("02", 8, calendar_event_id="ev-02"),  # mantido
        _bloco("03", 9, calendar_event_id="ev-03"),  # janela mudou: update
        _bloco("04", 10, calendar_event_id="ev-04"),  # chave velha: update só da descrição
        _bloco("05", 11),  # sem id, casado pela chave (a mais antiga das duplicatas)
        _bloco("06", 12, "cancelada", calendar_event_id="ev-06"),  # delete
        _bloco("07", 13, "cancelada"),  # cancelado sem evento: nada
        _bloco("08", 14, "feita", calendar_event_id="ev-08"),  # fixo: nada
    ]
    eventos = [
        _evento("ev-02", _chave("D-2026-09-28-02"), 8),
        _evento("ev-03", _chave("D-2026-09-28-03"), 15),
        _evento("ev-04", "gp:D-2026-09-28-99/inst-fixture-01", 10),
        _evento("ev-05b", _chave("D-2026-09-28-05"), 11, created="2026-09-27T09:00:00Z"),
        _evento("ev-05a", _chave("D-2026-09-28-05"), 11, created="2026-09-27T08:00:00Z"),
        _evento("ev-06", _chave("D-2026-09-28-06"), 12),
        _evento("ev-08", _chave("D-2026-09-28-08"), 14),
        _evento("ev-orfao-hoje", _chave("D-2026-09-28-20"), 16),
        _evento("ev-orfao-ontem", _chave("D-2026-09-27-01"), 16, dia="2026-09-27"),
        _evento("ev-orfao-ontem-dup", _chave("D-2026-09-27-01"), 17, dia="2026-09-27", created="2026-09-27T10:00:00Z"),
        _evento("ev-cancelado", _chave("D-2026-09-28-21"), 18, status="cancelled"),
        _evento("ev-outra", _chave("D-2026-09-28-22", "outra-inst"), 19),
        "lixo",
    ]
    doc = co.planejar_ops(blocos, eventos, CONTEXTO, run_id="r-car", agora=AGORA, dia=DIA)
    ids = {b["id"]: (b.get("calendar_event_id"), b.get("calendar_id")) for b in blocos}
    return {"ops": doc["ops"], "ids": ids}


def test_keep_diff_igual_ao_golden_master():
    obtido = _cenario()
    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO.read_text(encoding="utf-8"))


def test_ops_invalidas_param_o_planejamento():
    ruim = dict(CONTEXTO, calendar_id_metas="")
    with pytest.raises(GpErro, match="ops planejadas inválidas"):
        co.planejar_ops([_bloco("01", 7)], [], ruim, run_id="r", agora=AGORA, dia=DIA)


def test_lista_de_calendarios_ilegivel_ou_sem_metas_e_refeita(tmp_path, monkeypatch):
    from goalpacer import proxy

    chamadas = []

    def lista(tool, args, **_k):
        chamadas.append(tool)
        return {"calendars": [{"id": METAS, "summary": "Metas", "timeZone": "America/Sao_Paulo", "extra": 1}, "x"]}

    monkeypatch.setattr(proxy, "chamar", lista)
    cache = tmp_path / "cache" / ("%s2026-09-28.json" % co.PREFIXO_LISTA)
    cache.parent.mkdir()
    cache.write_text("{quebrado", encoding="utf-8")
    assert co.listar_calendarios(tmp_path, modo_offline=False, agora=AGORA, calendar_id_metas=METAS) == [
        {"id": METAS, "summary": "Metas", "timeZone": "America/Sao_Paulo"}
    ]
    assert json.loads(cache.read_text(encoding="utf-8")) == {
        "calendars": [{"id": METAS, "summary": "Metas", "timeZone": "America/Sao_Paulo"}]
    }
    assert co.listar_calendarios(tmp_path, modo_offline=False, agora=AGORA, calendar_id_metas=METAS)[0]["id"] == METAS
    assert co.listar_calendarios(tmp_path, modo_offline=False, agora=AGORA, calendar_id_metas="outro-metas")
    assert chamadas == [co.TOOL_LIST_CALENDARS, co.TOOL_LIST_CALENDARS]


def test_evento_usado_por_um_bloco_nunca_e_apagado_como_orfao_ou_duplicata():
    blocos = [
        # casado pelo id com um evento cuja gp_key é de outro bloco (descrição antiga): atualiza, não apaga
        _bloco("04", 10, calendar_event_id="ev-04"),
        # casado pelo id com a duplicata mais nova: fica essa, sai a mais antiga
        _bloco("05", 11, calendar_event_id="ev-05b"),
    ]
    eventos = [
        _evento("ev-04", "gp:D-2026-09-28-99/inst-fixture-01", 10),
        _evento("ev-05a", _chave("D-2026-09-28-05"), 11, created="2026-09-27T08:00:00Z"),
        _evento("ev-05b", _chave("D-2026-09-28-05"), 11, created="2026-09-27T09:00:00Z"),
    ]
    ops = co.planejar_ops(blocos, eventos, CONTEXTO, run_id="r", agora=AGORA, dia=DIA)["ops"]
    apagados = {op["calendar_event_id"] for op in ops if op["op"] == "delete"}
    assert apagados == {"ev-05a"}
    assert [(op["op"], op["task_id"]) for op in ops if op["op"] != "delete"] == [("update", "D-2026-09-28-04")]
