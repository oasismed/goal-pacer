"""Testes de goalpacer.clock: ISO, semanas ISO, fusos, DST, --agora/--tz.

Datas âncora: 2026-09-28 (segunda, ISO 2026-W40; a quinta dessa semana é
2026-10-01) e a virada 2026-12-31/2027-01-01 (2026 tem 53 semanas ISO).
"""

from __future__ import annotations

import argparse
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from goalpacer import clock
from goalpacer.base import EXIT_VALIDACAO, GpErro

SP = ZoneInfo("America/Sao_Paulo")
LISBOA = ZoneInfo("Europe/Lisbon")


@pytest.fixture
def relogio_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem GP_AGORA/GP_TZ e sem estado fixado (restaurado ao fim)."""
    monkeypatch.delenv("GP_AGORA", raising=False)
    monkeypatch.delenv("GP_TZ", raising=False)
    monkeypatch.setattr(clock, "_AGORA_FIXADO", None)
    monkeypatch.setattr(clock, "_TZ_FIXADO", None)


def _codigo_validacao(excinfo: pytest.ExceptionInfo) -> None:
    assert excinfo.value.codigo == EXIT_VALIDACAO


# ---------------------------------------------------------------- normalizar_iso


def test_normalizar_iso_z_para_offset():
    assert clock.normalizar_iso("2026-09-28T07:00:00Z") == "2026-09-28T07:00:00+00:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00z") == "2026-09-28T07:00:00+00:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00.123Z") == "2026-09-28T07:00:00.123+00:00"


def test_normalizar_iso_fracao_truncada_a_6():
    assert clock.normalizar_iso("2026-09-28T07:00:00.1234567890Z") == "2026-09-28T07:00:00.123456+00:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00.123456-03:00") == ("2026-09-28T07:00:00.123456-03:00")
    # o fromisoformat do 3.9 só aceita 3 ou 6 dígitos: completa com zeros
    assert clock.normalizar_iso("2026-09-28T07:00:00.1Z") == "2026-09-28T07:00:00.100000+00:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00.1234") == "2026-09-28T07:00:00.123400"
    assert clock.normalizar_iso("2026-09-28T07:00:00.123") == "2026-09-28T07:00:00.123"


def test_normalizar_iso_offset_sem_dois_pontos():
    assert clock.normalizar_iso("2026-09-28T07:00:00+0000") == "2026-09-28T07:00:00+00:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00-0300") == "2026-09-28T07:00:00-03:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00-03") == "2026-09-28T07:00:00-03:00"
    assert clock.normalizar_iso("2026-09-28T07:00:00+05:30") == "2026-09-28T07:00:00+05:30"
    assert clock.normalizar_iso("2026-09-28T07:00-03:00") == "2026-09-28T07:00-03:00"


def test_normalizar_iso_formato_basico_erro():
    for texto in ("20260928T070000Z", "2026-09-28T0700", "20260928", "2026/09/28", "", "ontem"):
        with pytest.raises(GpErro) as excinfo:
            clock.normalizar_iso(texto)
        _codigo_validacao(excinfo)
    with pytest.raises(GpErro):
        clock.normalizar_iso(None)  # type: ignore[arg-type]


def test_normalizar_iso_data_pura_espacos_e_separador():
    assert clock.normalizar_iso("2026-09-28") == "2026-09-28"
    assert clock.normalizar_iso("  2026-09-28 \n") == "2026-09-28"
    assert clock.normalizar_iso("2026-09-28 07:00:00") == "2026-09-28T07:00:00"
    assert clock.normalizar_iso("2026-09-28t07:00:00z") == "2026-09-28T07:00:00+00:00"


# ---------------------------------------------------------------- parse_iso


def test_parse_iso_data_pura_meia_noite(agora_fixo):
    dt = clock.parse_iso("2026-09-28")
    assert dt == datetime(2026, 9, 28, 0, 0, tzinfo=SP)
    assert dt.tzinfo.key == "America/Sao_Paulo"
    assert dt.utcoffset() == timedelta(hours=-3)
    dt2 = clock.parse_iso("2026-09-28", LISBOA)
    assert (dt2.hour, dt2.minute) == (0, 0)
    assert dt2.utcoffset() == timedelta(hours=1)


def test_parse_iso_naive_recebe_tz_padrao(agora_fixo):
    dt = clock.parse_iso("2026-09-28T07:00:00", LISBOA)
    assert dt.tzinfo is LISBOA
    assert dt.hour == 7 and dt.utcoffset() == timedelta(hours=1)
    # sem tz_padrao usa fuso() (GP_TZ=America/Sao_Paulo pela fixture)
    dt = clock.parse_iso("2026-09-28T07:00:00")
    assert dt.tzinfo.key == "America/Sao_Paulo"
    assert dt.utcoffset() == timedelta(hours=-3)


def test_parse_iso_consciente_preserva_offset():
    dt = clock.parse_iso("2026-09-28T07:00:00+05:30", LISBOA)
    assert dt.utcoffset() == timedelta(hours=5, minutes=30)
    assert dt.hour == 7
    dt = clock.parse_iso("2026-09-28T07:00:00Z")
    assert dt.utcoffset() == timedelta(0)
    dt = clock.parse_iso("2026-09-28T07:00:00.1234567-03:00")
    assert dt.microsecond == 123456 and dt.utcoffset() == timedelta(hours=-3)
    dt = clock.parse_iso("2026-09-28T07:00:00.5Z")
    assert dt.microsecond == 500000


def test_parse_iso_invalido_erro():
    for texto in ("2026-13-45", "2026-09-28T25:00:00", "2026-09-28T07:61:00Z", "2026-09-28T07:00:00-030"):
        with pytest.raises(GpErro) as excinfo:
            clock.parse_iso(texto, timezone.utc)
        _codigo_validacao(excinfo)


# ---------------------------------------------------------------- para_utc


def test_para_utc():
    dt = datetime(2026, 9, 28, 7, 0, tzinfo=SP)
    utc = clock.para_utc(dt)
    assert utc.tzinfo is timezone.utc
    assert utc == datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    assert utc.hour == 10
    assert clock.para_utc(utc) == utc


def test_para_utc_naive_erro():
    with pytest.raises(GpErro) as excinfo:
        clock.para_utc(datetime(2026, 9, 28, 7, 0))
    _codigo_validacao(excinfo)
    with pytest.raises(GpErro):
        clock.para_utc("2026-09-28T07:00:00Z")  # type: ignore[arg-type]


# ---------------------------------------------------------------- semanas ISO


def test_semana_iso_w40_de_2026():
    assert clock.semana_iso(date(2026, 9, 28)) == "2026-W40"
    assert clock.semana_iso(date(2026, 10, 4)) == "2026-W40"
    assert clock.semana_iso(date(2026, 10, 5)) == "2026-W41"
    assert clock.semana_iso(datetime(2026, 9, 28, 7, 0, tzinfo=SP)) == "2026-W40"


def test_semana_iso_virada_2026_12_31():
    # 2026-01-01 é quinta: o ano ISO 2026 tem 53 semanas
    assert clock.semana_iso(date(2026, 12, 31)) == "2026-W53"
    assert clock.semana_iso(date(2026, 12, 28)) == "2026-W53"


def test_semana_iso_virada_2027_01_01():
    assert clock.semana_iso(date(2027, 1, 1)) == "2026-W53"
    assert clock.semana_iso(date(2027, 1, 3)) == "2026-W53"
    assert clock.semana_iso(date(2027, 1, 4)) == "2027-W01"


def test_semana_iso_ano_iso_diferente_do_civil():
    assert clock.semana_iso(date(2025, 12, 29)) == "2026-W01"
    assert clock.semana_iso(date(2026, 1, 1)) == "2026-W01"
    assert clock.semana_iso(date(2026, 1, 5)) == "2026-W02"


def test_mes_da_semana_pela_quinta_feira():
    # W40 começa em 28/09, mas a quinta é 01/10: a semana é de outubro
    assert clock.mes_da_semana("2026-W40") == "2026-10"
    assert clock.mes_da_semana("2026-W39") == "2026-09"
    assert clock.mes_da_semana("2026-W53") == "2026-12"
    assert clock.mes_da_semana("2027-W01") == "2027-01"
    assert clock.mes_da_semana("2026-W01") == "2026-01"
    for ruim in ("2026-40", "2026-W0", "2026-W54", "2025-W53", "2026-W00", "", None):
        with pytest.raises(GpErro) as excinfo:
            clock.mes_da_semana(ruim)  # type: ignore[arg-type]
        _codigo_validacao(excinfo)


def test_dias_da_semana_sete_dias():
    dias = clock.dias_da_semana("2026-W40")
    assert len(dias) == 7
    assert dias[0] == date(2026, 9, 28) and dias[-1] == date(2026, 10, 4)
    assert [d.isoweekday() for d in dias] == [1, 2, 3, 4, 5, 6, 7]
    assert all(clock.semana_iso(d) == "2026-W40" for d in dias)
    assert all((b - a).days == 1 for a, b in zip(dias, dias[1:]))
    virada = clock.dias_da_semana("2026-W53")
    assert virada[0] == date(2026, 12, 28) and virada[-1] == date(2027, 1, 3)
    with pytest.raises(GpErro):
        clock.dias_da_semana("2026-W99")


def test_mes_id_semanas_do_mes_iso_e_instante():
    assert clock.mes_id(date(2026, 9, 28)) == "2026-09"
    dt = datetime(2026, 1, 5, 23, 59, tzinfo=SP)
    assert clock.mes_id(dt) == "2026-01"
    assert clock.semanas_do_mes("2026-10") == ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]
    assert clock.iso(dt) == "2026-01-05T23:59:00-03:00"
    assert clock.instante("2026-01-05T23:59:00", SP) == dt and clock.instante(dt) is dt
    assert clock.instante("ontem") is None and clock.instante(None) is None and clock.instante(5) is None


# ---------------------------------------------------------------- fuso


def test_fuso_valido_e_invalido(relogio_limpo):
    tz = clock.fuso("America/Sao_Paulo")
    assert isinstance(tz, ZoneInfo) and tz.key == "America/Sao_Paulo"
    assert clock.fuso("UTC").key == "UTC"
    for ruim in ("Marte/Olympus", "america/sao_paulo", "BRT", "-03:00"):
        with pytest.raises(GpErro) as excinfo:
            clock.fuso(ruim)
        _codigo_validacao(excinfo)


def test_fuso_precedencia_argumento_fixado_env(relogio_limpo, monkeypatch):
    monkeypatch.setenv("GP_TZ", "America/Sao_Paulo")
    assert clock.fuso().key == "America/Sao_Paulo"
    monkeypatch.setattr(clock, "_TZ_FIXADO", "Europe/Lisbon")
    assert clock.fuso().key == "Europe/Lisbon"
    assert clock.fuso("UTC").key == "UTC"
    monkeypatch.setenv("GP_TZ", "Marte/Olympus")
    assert clock.fuso().key == "Europe/Lisbon"  # o fixado vence o env inválido
    monkeypatch.setattr(clock, "_TZ_FIXADO", None)
    with pytest.raises(GpErro):
        clock.fuso()


def test_fuso_sistema_sem_env(relogio_limpo):
    tz = clock.fuso()
    assert tz is not None
    assert datetime(2026, 9, 28, 7, 0, tzinfo=tz).utcoffset() is not None


def test_fuso_dst_europe_lisbon():
    tz = clock.fuso("Europe/Lisbon")
    inverno = clock.parse_iso("2026-01-15T12:00:00", tz)
    verao = clock.parse_iso("2026-07-01T12:00:00", tz)
    assert inverno.utcoffset() == timedelta(0)
    assert verao.utcoffset() == timedelta(hours=1)
    assert clock.para_utc(verao).hour == 11
    # fim do horário de verão (25/10/2026 01:00 UTC): 01:30 local acontece duas vezes
    antes = clock.parse_iso("2026-10-25T00:30:00Z").astimezone(tz)
    depois = clock.parse_iso("2026-10-25T01:30:00Z").astimezone(tz)
    assert (antes.hour, antes.minute) == (1, 30) and antes.utcoffset() == timedelta(hours=1)
    assert (depois.hour, depois.minute) == (1, 30) and depois.utcoffset() == timedelta(0)
    # mesmo tzinfo: a subtração direta ignora o fold (dá 0); compare em UTC
    assert clock.para_utc(depois) - clock.para_utc(antes) == timedelta(hours=1)
    assert depois.fold == 1


# ---------------------------------------------------------------- agora


def test_agora_do_env(agora_fixo):
    ag = clock.agora()
    assert ag == datetime(2026, 9, 28, 7, 0, tzinfo=SP)
    assert ag.tzinfo.key == "America/Sao_Paulo"
    assert (ag.hour, ag.utcoffset()) == (7, timedelta(hours=-3))
    assert clock.semana_iso(ag) == "2026-W40" and ag.date().isoformat() == "2026-09-28"
    em_utc = clock.agora(timezone.utc)
    assert em_utc.tzinfo is timezone.utc and em_utc.hour == 10
    assert clock.agora(LISBOA).hour == 11


def test_fixar_agora_e_desfixar(agora_fixo):
    clock.fixar_agora("2026-10-01T12:00:00Z")
    ag = clock.agora()
    assert ag == datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    assert ag.hour == 9 and ag.tzinfo.key == "America/Sao_Paulo"
    clock.fixar_agora("2026-10-01")  # data pura: meia-noite no fuso()
    assert clock.agora() == datetime(2026, 10, 1, 0, 0, tzinfo=SP)
    clock.fixar_agora(None)
    assert clock.agora() == datetime(2026, 9, 28, 7, 0, tzinfo=SP)
    with pytest.raises(GpErro) as excinfo:
        clock.fixar_agora("20261001T120000Z")
    _codigo_validacao(excinfo)
    assert clock.agora() == datetime(2026, 9, 28, 7, 0, tzinfo=SP)


def test_agora_sem_env_e_consciente(monkeypatch, relogio_limpo):
    ag = clock.agora()
    assert ag.tzinfo is not None and ag.utcoffset() is not None
    assert abs(ag.timestamp() - time.time()) < 5
    em_utc = clock.agora(timezone.utc)
    assert em_utc.tzinfo is timezone.utc
    assert abs((em_utc - ag).total_seconds()) < 5
    monkeypatch.setenv("GP_AGORA", "2026-09-28T07:00:00-03:00")
    assert clock.agora(timezone.utc).hour == 10
    monkeypatch.setenv("GP_AGORA", "nao-e-data")
    with pytest.raises(GpErro):
        clock.agora()


# ---------------------------------------------------------------- --agora/--tz


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teste")
    clock.adicionar_args_relogio(parser)
    return parser


def test_args_agora_tz_via_parser(dados_tmp, relogio_limpo):
    args = _parser().parse_args(["--agora", "2026-09-28T07:00:00", "--tz", "Europe/Lisbon"])
    assert args.agora == "2026-09-28T07:00:00" and args.tz == "Europe/Lisbon"
    clock.aplicar_args_relogio(args)
    ag = clock.agora()
    assert ag.tzinfo.key == "Europe/Lisbon"
    assert (ag.hour, ag.utcoffset()) == (7, timedelta(hours=1))
    assert clock.agora(timezone.utc).hour == 6  # o --agora naive usou o --tz
    assert clock.fuso().key == "Europe/Lisbon"
    assert clock.semana_iso(ag) == "2026-W40"

    args = _parser().parse_args(["--agora", "2026-09-28T07:00:00-03:00"])
    clock.aplicar_args_relogio(args)
    assert clock.agora(timezone.utc).hour == 10
    assert clock._TZ_FIXADO is None


def test_args_tz_invalido_erro(dados_tmp, relogio_limpo):
    args = _parser().parse_args(["--tz", "Marte/Olympus"])
    with pytest.raises(GpErro) as excinfo:
        clock.aplicar_args_relogio(args)
    _codigo_validacao(excinfo)
    args = _parser().parse_args(["--agora", "ontem"])
    with pytest.raises(GpErro) as excinfo:
        clock.aplicar_args_relogio(args)
    _codigo_validacao(excinfo)


def test_aplicar_args_sem_flags_usa_env(agora_fixo):
    clock.fixar_agora("2020-01-01T00:00:00Z")  # resto de execução anterior
    args = _parser().parse_args([])
    clock.aplicar_args_relogio(args)
    assert clock._AGORA_FIXADO is None and clock._TZ_FIXADO is None
    assert clock.agora() == datetime(2026, 9, 28, 7, 0, tzinfo=SP)
    assert clock.fuso().key == "America/Sao_Paulo"


def test_aplicar_args_env_invalido_falha_cedo(agora_fixo, monkeypatch):
    monkeypatch.setenv("GP_TZ", "Marte/Olympus")
    with pytest.raises(GpErro) as excinfo:
        clock.aplicar_args_relogio(_parser().parse_args([]))
    _codigo_validacao(excinfo)
    monkeypatch.setenv("GP_TZ", "America/Sao_Paulo")
    monkeypatch.setenv("GP_AGORA", "20260928T070000")
    with pytest.raises(GpErro) as excinfo:
        clock.aplicar_args_relogio(_parser().parse_args([]))
    _codigo_validacao(excinfo)
