"""Testes de goalpacer.demanda: custo, restante, demanda por semana com clamp, demanda do dia."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from goalpacer import clock, demanda, registro as reg

TZ = ZoneInfo("America/Sao_Paulo")


def meta(**extra) -> dict:
    m = {
        "id": "M01",
        "titulo": "Meta",
        "horizonte": "trimestre",
        "prazo": date(2026, 12, 15),
        "estado": "ativa",
        "custo_h_semana_escolhido": 4.0,
        "semanas_pesquisa": 12,
        "confianca": "media",
        "criado_em": datetime(2026, 9, 1, 10, 0, tzinfo=TZ),
    }
    m.update(extra)
    return m


def test_custo_confirmadas_e_restante():
    r = reg.vazio()
    m = meta()
    assert demanda.custo_total_h(m) == 48.0
    reg.registrar_feita(r, "M01", "D-2026-09-21-01", 1.0, "confirmado", duracao_real_h=1.5)
    reg.registrar_feita(r, "M01", "D-2026-09-21-02", 2.0, "confirmado")
    reg.registrar_feita(r, "M01", "D-2026-09-21-03", 9.0, "presumido")  # não abate
    assert demanda.horas_confirmadas(r, "M01") == 3.5
    assert demanda.restante_h(m, r) == 44.5
    assert demanda.ativa_em(m, date(2026, 12, 15)) and not demanda.ativa_em(m, date(2026, 12, 16))
    assert not demanda.ativa_em(meta(estado="arquivada"), date(2026, 9, 28))


def test_semanas_do_mes_pela_quinta():
    # setembro/2026: quintas 3, 10, 17, 24 → W36..W39; 1/10 é quinta → W40 é de outubro
    assert demanda.semanas_do_mes("2026-09") == ["2026-W36", "2026-W37", "2026-W38", "2026-W39"]
    assert demanda.semanas_do_mes("2026-10")[0] == "2026-W40" and demanda.semanas_do_mes("2026-10")[-1] == "2026-W44"
    assert demanda.semanas_do_mes("2026-12")[-1] == "2026-W53"  # 31/12/2026 é quinta
    assert demanda.semanas_do_mes("2027-01")[0] == "2027-W01"


def test_demandas_do_mes_com_clamp():
    r = reg.vazio()
    m = meta()
    # 48 h restantes, prazo 15/12: da segunda 7/9 faltam 15 semanas → 48/15 = 3,2 < 4 → 4 h por semana
    assert demanda.demandas_do_mes(m, r, "2026-09") == {
        "2026-W36": 4.0,
        "2026-W37": 4.0,
        "2026-W38": 4.0,
        "2026-W39": 4.0,
    }
    # pouco restante: o clamp acumulado zera as últimas semanas
    for i in range(1, 44):
        reg.registrar_feita(r, "M01", "D-2026-09-%02d-%02d" % (1 + i % 28, i), 1.0, "confirmado")
    assert demanda.restante_h(m, r) == 5.0
    assert demanda.demandas_do_mes(m, r, "2026-09") == {
        "2026-W36": 4.0,
        "2026-W37": 1.0,
        "2026-W38": 0.0,
        "2026-W39": 0.0,
    }
    # prazo perto (27/9): o que falta dividido pelas semanas até o prazo sobe acima do escolhido
    # W36 (seg 31/8): 48/4 = 12; W37: 36/3 = 12; W38: 24/2 = 12; W39 (seg 21/9): 12/1 = 12
    r2 = reg.vazio()
    m2 = meta(prazo=date(2026, 9, 27))
    d = demanda.demandas_do_mes(m2, r2, "2026-09")
    assert d == {"2026-W36": 12.0, "2026-W37": 12.0, "2026-W38": 12.0, "2026-W39": 12.0}
    # demanda estável ao longo do mês quando o ritmo escolhido cobre o prazo (nada de crescer semana a semana)
    assert set(demanda.demandas_do_mes(meta(), reg.vazio(), "2026-10").values()) == {4.0}
    # meta vencida ou arquivada: zero
    assert set(demanda.demandas_do_mes(meta(prazo=date(2026, 8, 1)), r2, "2026-09").values()) == {0.0}
    assert set(demanda.demandas_do_mes(meta(estado="arquivada"), r2, "2026-09").values()) == {0.0}
    assert demanda.demanda_semana(m, reg.vazio(), "2026-W40") == 4.0


def test_demanda_dia_e_horas_na_semana():
    contexto = {"horario_util_seg_sex": "08:00-19:00", "horario_util_sab": "09:00-13:00", "horario_util_dom": ""}
    from goalpacer import agenda

    tem = agenda.tem_horario_util(contexto)
    assert demanda.dias_uteis_restantes(date(2026, 9, 28), tem) == 6  # seg..sáb
    assert demanda.dias_uteis_restantes(date(2026, 10, 3), tem) == 1  # sábado
    assert demanda.dias_uteis_restantes(date(2026, 10, 4), tem) == 1  # domingo sem horário: mínimo 1
    m = meta()
    r = reg.vazio()
    blocos = {
        "D-2026-09-28-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 28, 9, 0, tzinfo=TZ),
            "duracao_h": 1.5,
            "estado": "planejada",
        },
        "D-2026-09-29-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 29, 9, 0, tzinfo=TZ),
            "duracao_h": 1.0,
            "estado": "feita",
            "duracao_real_h": 0.5,
        },
        "D-2026-09-30-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 30, 9, 0, tzinfo=TZ),
            "duracao_h": 1.0,
            "estado": "apagada",
        },
        "D-2026-09-21-01": {
            "meta": "M01",
            "inicio": datetime(2026, 9, 21, 9, 0, tzinfo=TZ),
            "duracao_h": 3.0,
            "estado": "planejada",
        },
        "D-2026-09-28-02": {
            "meta": "M02",
            "inicio": datetime(2026, 9, 28, 9, 0, tzinfo=TZ),
            "duracao_h": 3.0,
            "estado": "planejada",
        },
    }
    assert demanda.horas_na_semana(blocos, "M01", "2026-W40") == 2.0
    assert demanda.horas_na_semana(blocos, "M01", "2026-W40", excluir_data=date(2026, 9, 28)) == 0.5
    # W40: demanda 4 h; 0,5 h fora de hoje; 6 dias úteis restantes na segunda → 0,58
    assert demanda.demanda_dia(m, r, date(2026, 9, 28), 0.5, tem) == 0.58
    assert demanda.demanda_dia(m, r, date(2026, 10, 3), 3.5, tem) == 0.5
    assert demanda.demanda_dia(m, r, date(2026, 10, 3), 4.0, tem) == 0.0
    assert demanda.demanda_dia(meta(estado="concluida"), r, date(2026, 9, 28), 0.0, tem) == 0.0
    from goalpacer import periodos

    assert (
        demanda.semanas_do_mes is periodos.semanas_do_mes is clock.semanas_do_mes
    )  # uma regra só (D1, análise de 13/09)
