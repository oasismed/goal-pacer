"""goalpacer/periodos.py: drill-down ano > semestre > trimestre > mês > semana > dia com a convenção do plano."""

from __future__ import annotations

from datetime import date

import pytest

from goalpacer import demanda, periodos as p

HOJE = date(2026, 9, 28)  # segunda da semana 40, que é de outubro (quinta 01/10)


def test_cadeia_do_dia_segue_a_semana_do_plano():
    assert [p.do_dia(n, HOJE) for n in p.NIVEIS] == ["2026-09-28", "2026-W40", "2026-10", "2026-T4", "2026-S2", "2026"]
    assert p.trilha("dia", "2026-09-28") == [
        ("ano", "2026"),
        ("semestre", "2026-S2"),
        ("trimestre", "2026-T4"),
        ("mes", "2026-10"),
        ("semana", "2026-W40"),
        ("dia", "2026-09-28"),
    ]
    assert p.intervalo("mes", "2026-10") == (date(2026, 9, 28), date(2026, 11, 1))
    assert p.intervalo("ano", "2026") == (date(2025, 12, 29), date(2027, 1, 3))
    assert p.filhos("semestre", "2026-S2") == [("trimestre", "2026-T3"), ("trimestre", "2026-T4")]
    assert [f[1] for f in p.filhos("mes", "2026-10")] == ["2026-W40", "2026-W41", "2026-W42", "2026-W43", "2026-W44"]
    assert len(p.filhos("semana", "2026-W40")) == 7 and p.filhos("dia", "2026-09-28") == []


@pytest.mark.parametrize("ano", [2020, 2026, 2027])
def test_todo_filho_cabe_no_pai_e_os_filhos_cobrem_o_pai(ano):
    for mes in ["%d-%02d" % (ano, m) for m in range(1, 13)]:
        assert p.semanas_do_mes(mes) == demanda.semanas_do_mes(mes)
    pendentes = [("ano", str(ano))]
    while pendentes:
        nivel, pid = pendentes.pop()
        filhos = p.filhos(nivel, pid)
        if not filhos:
            continue
        inicio, fim = p.intervalo(nivel, pid)
        assert p.intervalo(*filhos[0])[0] == inicio and p.intervalo(*filhos[-1])[1] == fim, (nivel, pid)
        for anterior, seguinte in zip(filhos, filhos[1:]):
            assert (p.intervalo(*seguinte)[0] - p.intervalo(*anterior)[1]).days == 1
        for filho in filhos:
            assert p.pai(*filho) == (nivel, pid), filho
        if nivel != "semana":
            pendentes += filhos


def test_vizinhos_fase_decorrido_e_validacao():
    assert p.vizinho("mes", "2026-12", 1) == "2027-01" and p.vizinho("trimestre", "2026-T1", -1) == "2025-T4"
    assert p.vizinho("semestre", "2026-S2", 1) == "2027-S1" and p.vizinho("semana", "2026-W53", 1) == "2027-W01"
    assert p.vizinho("dia", "2026-02-28", 1) == "2026-03-01" and p.vizinho("ano", "2026", -1) == "2025"
    assert [p.fase("trimestre", t, HOJE) for t in ("2026-T3", "2026-T4", "2027-T1")] == ["passado", "atual", "futuro"]
    assert (
        p.decorrido("semana", "2026-W40", HOJE) == 1 / 7
        and p.decorrido("ano", "2025", HOJE) == 1.0
        and p.decorrido("ano", "2027", HOJE) == 0.0
    )
    assert (
        p.validar("trimestre", "2026-T4")
        and not p.validar("trimestre", "2026-T5")
        and not p.validar("semana", "2026-W60")
    )
    assert (
        not p.validar("dia", "2026-02-30")
        and not p.validar("mes", "2026-13")
        and not p.validar("ano", "../x")
        and not p.validar("hora", "1")
    )
    assert p.sobrepoe(date(2026, 9, 1), date(2026, 12, 15), *p.intervalo("mes", "2026-10"))
    assert not p.sobrepoe(date(2026, 9, 1), date(2026, 9, 20), *p.intervalo("mes", "2026-10"))
