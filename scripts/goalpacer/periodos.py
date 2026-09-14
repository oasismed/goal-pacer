"""Períodos do drill-down do painel: ano > semestre > trimestre > mês > semana > dia. Só cálculo de datas.

Ano, semestre e trimestre são os horizontes das metas do onboarding; mês, semana e dia são
derivados deles (o plano do mês, as semanas do balanço, os blocos do dia). A contenção segue a
convenção do plano: a semana ISO pertence ao mês da sua quinta-feira (``clock.mes_da_semana``),
o mês ao trimestre e ao semestre pelo número, e cada período vai da segunda-feira da sua primeira
semana ao domingo da última, para que todo filho caiba inteiro no pai::

    2026 -> 2026-S2 -> 2026-T4 -> 2026-10 -> 2026-W40 -> 2026-09-28
    ano     semestre   trimestre  mês        semana      dia (segunda da semana 40, que é de outubro)
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from goalpacer import clock
from goalpacer.base import GpErro

NIVEIS = ("dia", "semana", "mes", "trimestre", "semestre", "ano")
DERIVADOS = ("dia", "semana", "mes")
FORMATOS = {
    "dia": re.compile(r"^\d{4}-\d{2}-\d{2}\Z"),
    "semana": re.compile(r"^\d{4}-W\d{2}\Z"),
    "mes": re.compile(r"^\d{4}-(0[1-9]|1[0-2])\Z"),
    "trimestre": re.compile(r"^\d{4}-T[1-4]\Z"),
    "semestre": re.compile(r"^\d{4}-S[12]\Z"),
    "ano": re.compile(r"^\d{4}\Z"),
}


def validar(nivel: str, pid: str) -> bool:
    if nivel not in FORMATOS or not isinstance(pid, str) or not FORMATOS[nivel].match(pid):
        return False
    try:
        if nivel == "dia":
            date.fromisoformat(pid)
        elif nivel == "semana":
            clock.dias_da_semana(pid)
    except (ValueError, GpErro):
        return False
    return True


def _mes(ano: int, numero: int) -> str:
    return "%04d-%02d" % (ano, numero)


def meses(nivel: str, pid: str) -> list[str]:
    """Meses de um mês, trimestre, semestre ou ano."""
    ano = int(pid[:4])
    if nivel == "mes":
        return [pid]
    if nivel == "trimestre":
        primeiro = 3 * (int(pid[-1]) - 1) + 1
        return [_mes(ano, m) for m in range(primeiro, primeiro + 3)]
    if nivel == "semestre":
        primeiro = 1 if pid[-1] == "1" else 7
        return [_mes(ano, m) for m in range(primeiro, primeiro + 6)]
    if nivel == "ano":
        return [_mes(ano, m) for m in range(1, 13)]
    raise ValueError("nível sem meses: %s" % nivel)


semanas_do_mes = clock.semanas_do_mes  # regra única em clock (a mesma do plano)


def filhos(nivel: str, pid: str) -> list[tuple[str, str]]:
    ano = pid[:4]
    if nivel == "ano":
        return [("semestre", ano + "-S1"), ("semestre", ano + "-S2")]
    if nivel == "semestre":
        base = 1 if pid[-1] == "1" else 3
        return [("trimestre", "%s-T%d" % (ano, base)), ("trimestre", "%s-T%d" % (ano, base + 1))]
    if nivel == "trimestre":
        return [("mes", m) for m in meses(nivel, pid)]
    if nivel == "mes":
        return [("semana", s) for s in semanas_do_mes(pid)]
    if nivel == "semana":
        return [("dia", d.isoformat()) for d in clock.dias_da_semana(pid)]
    return []


def do_dia(nivel: str, dia: date) -> str:
    """Id do período de ``nivel`` que contém ``dia``, pela cadeia dia -> semana -> mês."""
    if nivel == "dia":
        return dia.isoformat()
    semana = clock.semana_iso(dia)
    if nivel == "semana":
        return semana
    mes = clock.mes_da_semana(semana)
    ano, numero = mes[:4], int(mes[5:7])
    return {
        "mes": mes,
        "trimestre": "%s-T%d" % (ano, (numero - 1) // 3 + 1),
        "semestre": "%s-S%d" % (ano, 1 if numero <= 6 else 2),
        "ano": ano,
    }[nivel]


def intervalo(nivel: str, pid: str) -> tuple[date, date]:
    """Primeiro e último dia (inclusive)."""
    if nivel == "dia":
        dia = date.fromisoformat(pid)
        return dia, dia
    if nivel == "semana":
        dias = clock.dias_da_semana(pid)
        return dias[0], dias[-1]
    lista = meses(nivel, pid)
    return clock.dias_da_semana(semanas_do_mes(lista[0])[0])[0], clock.dias_da_semana(semanas_do_mes(lista[-1])[-1])[-1]


def pai(nivel: str, pid: str) -> Optional[tuple[str, str]]:
    if nivel == "ano":
        return None
    acima = NIVEIS[NIVEIS.index(nivel) + 1]
    if nivel in ("dia", "semana"):
        return acima, do_dia(acima, intervalo(nivel, pid)[0])
    # mês, trimestre e semestre: o dia 15 do primeiro mês cai numa semana que é desse mês
    return acima, do_dia(acima, date.fromisoformat(meses(nivel, pid)[0] + "-15"))


def trilha(nivel: str, pid: str) -> list[tuple[str, str]]:
    """Do ano até o próprio período."""
    saida = [(nivel, pid)]
    while True:
        acima = pai(*saida[0])
        if acima is None:
            return saida
        saida.insert(0, acima)


def vizinho(nivel: str, pid: str, passo: int) -> str:
    ano = int(pid[:4])
    if nivel == "dia":
        return (date.fromisoformat(pid) + timedelta(days=passo)).isoformat()
    if nivel == "semana":
        return clock.semana_iso(clock.dias_da_semana(pid)[0] + timedelta(days=7 * passo))
    if nivel == "mes":
        total = ano * 12 + int(pid[5:7]) - 1 + passo
        return _mes(total // 12, total % 12 + 1)
    if nivel == "trimestre":
        total = ano * 4 + int(pid[-1]) - 1 + passo
        return "%04d-T%d" % (total // 4, total % 4 + 1)
    if nivel == "semestre":
        total = ano * 2 + int(pid[-1]) - 1 + passo
        return "%04d-S%d" % (total // 2, total % 2 + 1)
    return "%04d" % (ano + passo)


def fase(nivel: str, pid: str, hoje: date) -> str:
    inicio, fim = intervalo(nivel, pid)
    return "passado" if fim < hoje else "futuro" if inicio > hoje else "atual"


def decorrido(nivel: str, pid: str, hoje: date) -> float:
    """Fração do período que já passou (0 antes de começar, 1 depois de acabar), contando o dia de hoje."""
    inicio, fim = intervalo(nivel, pid)
    total = (fim - inicio).days + 1
    return max(0.0, min(1.0, ((hoje - inicio).days + 1) / total))


def sobrepoe(inicio: date, fim: date, de: date, ate: date) -> bool:
    return inicio <= ate and de <= fim
