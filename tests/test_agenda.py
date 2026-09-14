"""Testes de goalpacer.agenda: horário útil, ocupações, janelas livres, alocação determinística."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from goalpacer import agenda
from goalpacer.agenda import Janela
from goalpacer.base import GpErro

TZ = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 9, 28)  # segunda
METAS_CAL = "metas-fixture@group.calendar.google.com"
PRIMARIO = "pessoa@exemplo.test"
INST = "inst-fixture-01"
CONTEXTO = {
    "horario_util_seg_sex": "08:00-19:00",
    "horario_util_sab": "09:00-13:00",
    "horario_util_dom": "",
    "buffer_min": 10,
}


def dt(h: int, m: int = 0, dia: date = DIA) -> datetime:
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=TZ)


def ev(inicio: str, fim: str, cal: str = PRIMARIO, **extra) -> dict:
    e = {
        "id": "e",
        "calendar_id": cal,
        "start": inicio,
        "end": fim,
        "all_day": False,
        "status": "confirmed",
        "transparency": "opaque",
        "self_response": "",
        "event_type": "default",
        "gp_key": None,
    }
    e.update(extra)
    return e


def test_horario_util():
    assert agenda.horario_util(CONTEXTO, DIA, TZ) == Janela(dt(8), dt(19))
    assert agenda.horario_util(CONTEXTO, date(2026, 10, 3), TZ) == Janela(
        dt(9, dia=date(2026, 10, 3)), dt(13, dia=date(2026, 10, 3))
    )
    assert agenda.horario_util(CONTEXTO, date(2026, 10, 4), TZ) is None
    assert agenda.tem_horario_util(CONTEXTO)(date(2026, 10, 4)) is False
    with pytest.raises(GpErro):
        agenda.horario_util({"horario_util_seg_sex": "8-19"}, DIA, TZ)


def test_ocupacoes_regras():
    eventos = [
        ev("2026-09-28T09:00:00-03:00", "2026-09-28T10:00:00-03:00"),  # ocupa
        ev("2026-09-28T10:00:00-03:00", "2026-09-28T11:00:00-03:00", transparency="transparent"),  # livre
        ev("2026-09-28T11:00:00-03:00", "2026-09-28T12:00:00-03:00", self_response="declined"),  # livre
        ev("2026-09-28T12:00:00-03:00", "2026-09-28T13:00:00-03:00", status="cancelled"),  # livre
        ev("2026-09-28", "2026-09-29", all_day=True),  # dia inteiro comum: livre
        ev("2026-09-28", "2026-09-29", all_day=True, event_type="outOfOffice", id="ooo"),  # ocupa o dia
        ev(
            "2026-09-28T14:00:00-03:00", "2026-09-28T15:00:00-03:00", cal=METAS_CAL, gp_key="gp:D-2026-09-28-01/" + INST
        ),  # nosso, planejado: livre
        ev(
            "2026-09-28T15:00:00-03:00", "2026-09-28T16:00:00-03:00", cal=METAS_CAL, gp_key="gp:D-2026-09-26-02/" + INST
        ),  # nosso, movido: ocupa
        ev(
            "2026-09-28T16:00:00-03:00", "2026-09-28T17:00:00-03:00", cal=METAS_CAL, gp_key="gp:D-2026-09-28-09/outra"
        ),  # de outra instalação: ocupa
        ev("2026-09-27T23:00:00-03:00", "2026-09-28T01:00:00-03:00"),  # cruza a meia-noite: recorta
        ev("2026-09-29T09:00:00-03:00", "2026-09-29T10:00:00-03:00"),  # outro dia: fora
        ev("2026-09-28T18:00:00-03:00", "2026-09-28T17:00:00-03:00"),  # fim antes do início: ignora
        "lixo",
    ]
    oc = agenda.ocupacoes(
        eventos, DIA, TZ, calendar_id_metas=METAS_CAL, instalacao_id=INST, blocos_livres=["D-2026-09-28-01"]
    )
    assert oc == [
        Janela(dt(0), dt(1)),
        Janela(dt(0), dt(0) + timedelta(days=1)),
        Janela(dt(9), dt(10)),
        Janela(dt(15), dt(16)),
        Janela(dt(16), dt(17)),
    ]
    # instantes em outro fuso são convertidos
    oc = agenda.ocupacoes(
        [ev("2026-09-28T12:00:00Z", "2026-09-28T13:00:00Z")], DIA, TZ, calendar_id_metas=METAS_CAL, instalacao_id=INST
    )
    assert oc == [Janela(dt(9), dt(10))]


def test_janelas_livres_com_buffer():
    horario = Janela(dt(8), dt(19))
    assert agenda.janelas_livres(horario, [], 10) == [horario]
    assert agenda.janelas_livres(None, [], 10) == []
    ocupado = [
        Janela(dt(9), dt(10)),
        Janela(dt(9, 30), dt(11)),
        Janela(dt(12, 30), dt(12, 45)),
        Janela(dt(18, 45), dt(20)),
    ]
    livres = agenda.janelas_livres(horario, ocupado, 10)
    # 08:00-08:50 (50 min), 11:10-12:20 (70 min), 12:55-18:35; 18:35-19:00 tem 25 min < 30: fora
    assert livres == [Janela(dt(8), dt(8, 50)), Janela(dt(11, 10), dt(12, 20)), Janela(dt(12, 55), dt(18, 35))]
    # gap - 2*buffer >= 30: 50 min entre eventos com buffer 10 → 30 min (entra); com buffer 15 → 20 (não)
    ocupado = [Janela(dt(9), dt(10)), Janela(dt(10, 50), dt(12))]
    assert Janela(dt(10, 10), dt(10, 40)) in agenda.janelas_livres(horario, ocupado, 10)
    assert Janela(dt(10, 15), dt(10, 35)) not in agenda.janelas_livres(horario, ocupado, 15)
    # ocupação cobrindo o dia inteiro
    assert agenda.janelas_livres(horario, [Janela(dt(0), dt(0) + timedelta(days=1))], 10) == []


def test_duracao_bloco():
    assert agenda.duracao_bloco(0.1) == 0.5
    assert agenda.duracao_bloco(0.58) == 0.5
    assert agenda.duracao_bloco(1.3) == 1.25
    assert agenda.duracao_bloco(5.0) == 2.0
    assert agenda.duracao_bloco(1.0, fator_duracao=1.5) == 1.5
    assert agenda.duracao_bloco(1.0, bloco_medio_h=2.0) == 1.5
    assert agenda.duracao_bloco(0.0) == 0.5


def metas_base():
    return {
        "M01": {"id": "M01", "prazo": date(2026, 12, 15)},
        "M02": {"id": "M02", "prazo": date(2027, 3, 1)},
        "M03": {"id": "M03", "prazo": date(2026, 10, 1)},
    }


def test_ordenar_metas():
    metas = metas_base()
    demandas = {"M01": 1.0, "M02": 1.0, "M03": 1.0}
    # sem cobertura: empate na razão (0) → prazo mais cedo primeiro
    assert agenda.ordenar_metas(metas, demandas, {}) == ["M03", "M01", "M02"]
    # cobertura maior cai para o fim; demanda zero sai
    assert agenda.ordenar_metas(metas, {"M01": 1.0, "M02": 1.0, "M03": 0.0}, {"M01": 0.9, "M02": 0.1}) == ["M02", "M01"]


def test_alocar_deterministico_com_tetos_e_preferencias():
    metas = metas_base()
    janelas = [Janela(dt(8), dt(9, 30)), Janela(dt(11), dt(13)), Janela(dt(14), dt(19))]
    demandas = {"M01": 2.5, "M02": 0.58, "M03": 5.0}
    blocos = agenda.alocar(janelas, metas, demandas, dia=DIA, tz=TZ)
    assert blocos == agenda.alocar(janelas, metas, demandas, dia=DIA, tz=TZ)  # determinístico
    por_meta = {}
    for b in blocos:
        por_meta.setdefault(b.meta, []).append(b)
    # M03 (prazo mais cedo) pega as duas primeiras janelas grandes em blocos de 2 h; teto 2 blocos por meta
    assert [(b.inicio.hour, b.inicio.minute, b.duracao_h) for b in por_meta["M03"]] == [(11, 0, 2.0), (14, 0, 2.0)]
    # M01: 2,5 h → 2 h + 0,5 h
    assert sum(b.duracao_h for b in por_meta["M01"]) == 2.5 and len(por_meta["M01"]) == 2
    assert por_meta["M02"][0].duracao_h == 0.5
    # nada se sobrepõe e tudo cabe nas janelas
    ordenados = sorted(blocos, key=lambda b: b.inicio)
    for a, b in zip(ordenados, ordenados[1:]):
        assert a.fim <= b.inicio
    for b in blocos:
        assert any(j.inicio <= b.inicio and b.fim <= j.fim for j in janelas)
    # restrição por meta: M01 só à tarde
    blocos = agenda.alocar(
        janelas, {"M01": metas["M01"]}, {"M01": 1.0}, dia=DIA, tz=TZ, restricoes=["M01 14:00-19:00", "M09 x"]
    )
    assert blocos[0].inicio == dt(14) and blocos[0].duracao_h == 1.0
    # preferência do perfil: janela da tarde com taxa alta e n >= 5 vence a manhã
    perfil = {
        "janelas": {"seg-tarde": {"taxa_conclusao": 0.9, "n": 6}, "seg-manha": {"taxa_conclusao": 0.2, "n": 6}},
        "metas": {"M01": {"fator_duracao": 1.5}},
        "preferencias": {},
    }
    blocos = agenda.alocar(janelas, {"M01": metas["M01"]}, {"M01": 1.0}, dia=DIA, tz=TZ, perfil=perfil)
    assert blocos[0].inicio == dt(14) and blocos[0].duracao_h == 1.5
    # com n < 5 a preferência não vale
    perfil["janelas"]["seg-tarde"]["n"] = 3
    perfil["janelas"]["seg-manha"]["n"] = 3
    assert agenda.alocar(janelas, {"M01": metas["M01"]}, {"M01": 1.0}, dia=DIA, tz=TZ, perfil=perfil)[0].inicio == dt(8)
    # sem janela: nada
    assert agenda.alocar([], metas, demandas, dia=DIA, tz=TZ) == []
    # janela menor que o bloco pedido: encurta o bloco para caber (>= 30 min)
    assert (
        agenda.alocar([Janela(dt(8), dt(8, 30))], {"M01": metas["M01"]}, {"M01": 2.0}, dia=DIA, tz=TZ)[0].duracao_h
        == 0.5
    )
    assert (
        agenda.alocar([Janela(dt(8), dt(9, 20))], {"M01": metas["M01"]}, {"M01": 2.0}, dia=DIA, tz=TZ)[0].duracao_h
        == 1.25
    )
    assert agenda.alocar([Janela(dt(8), dt(8, 20))], {"M01": metas["M01"]}, {"M01": 2.0}, dia=DIA, tz=TZ) == []
