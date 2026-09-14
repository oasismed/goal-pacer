"""Demanda de horas por meta (design "Custo e demanda"; CEO 2.5; D3.3).

::

    custo_total_h        = custo_h_semana_escolhido * semanas_pesquisa
    horas_confirmadas    = soma das feitas com origem confirmado (duracao_real_h ou duracao_h)
    restante_h           = max(0, custo_total_h - horas_confirmadas)      (presumidas NÃO abatem)
    semanas_ate_prazo    = max(1, semanas entre a segunda da semana e o prazo)
    demanda_h(semana_k)  = 0 se restante <= 0 ou prazo < segunda da semana, senão
                           min(max(custo_h_semana_escolhido, (restante - distribuido) / semanas_ate_prazo),
                               restante - distribuido)
                           onde distribuido = soma das demandas das semanas anteriores do mês
                           (sem descontar, o restante fixo dividido por menos semanas faria a
                           demanda crescer a cada semana do mesmo mês)
    demanda_dia(meta)    = (demanda_h(semana) - horas alocadas ou confirmadas na semana,
                            excluída a alocação de hoje) / dias úteis restantes na semana (hoje incluso)

Só ``registro.feitas`` com ``origem: confirmado`` abate; ``estado`` da meta
fora de ``ativa`` (ou prazo vencido) tira a meta da alocação.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Optional

from goalpacer import clock


def custo_total_h(meta: dict[str, Any]) -> float:
    return float(meta["custo_h_semana_escolhido"]) * int(meta["semanas_pesquisa"])


def horas_confirmadas(registro: dict[str, Any], meta_id: str) -> float:
    total = 0.0
    for item in registro.get("feitas", {}).get(meta_id, []):
        if item.get("origem") != "confirmado":
            continue
        valor = item.get("duracao_real_h")
        if valor is None:
            valor = item.get("duracao_h", 0.0)
        total += float(valor or 0.0)
    return total


def restante_h(meta: dict[str, Any], registro: dict[str, Any]) -> float:
    return max(0.0, custo_total_h(meta) - horas_confirmadas(registro, meta["id"]))


def ativa_em(meta: dict[str, Any], data: date) -> bool:
    """Entra na alocação: ``estado: ativa`` e prazo não vencido."""
    return meta.get("estado", "ativa") == "ativa" and meta["prazo"] >= data


def semanas_ate_prazo(meta: dict[str, Any], segunda: date) -> int:
    dias = (meta["prazo"] - segunda).days
    return max(1, math.ceil(dias / 7.0))


semanas_do_mes = clock.semanas_do_mes  # regra única em clock (plano e painel usam a mesma)


def demandas_do_mes(meta: dict[str, Any], registro: dict[str, Any], mes: str) -> dict[str, float]:
    """``semana → demanda_h`` para as semanas do mês, com o clamp acumulado."""
    restante = restante_h(meta, registro)
    escolhido = float(meta["custo_h_semana_escolhido"])
    saida: dict[str, float] = {}
    acumulado = 0.0
    for semana in semanas_do_mes(mes):
        segunda = clock.dias_da_semana(semana)[0]
        if restante <= 0 or meta["prazo"] < segunda or meta.get("estado", "ativa") != "ativa":
            saida[semana] = 0.0
            continue
        falta = restante - acumulado
        base = max(escolhido, falta / semanas_ate_prazo(meta, segunda))
        valor = max(0.0, min(base, falta))
        saida[semana] = round(valor, 2)
        acumulado += valor
    return saida


def demanda_semana(meta: dict[str, Any], registro: dict[str, Any], semana: str) -> float:
    return demandas_do_mes(meta, registro, clock.mes_da_semana(semana)).get(semana, 0.0)


def dias_uteis_restantes(data: date, tem_horario_util) -> int:
    """Dias da semana ISO de ``data`` (hoje incluso) até domingo com horário útil; mínimo 1."""
    total = 0
    dia = data
    while dia.isocalendar()[:2] == data.isocalendar()[:2]:
        if tem_horario_util(dia):
            total += 1
        dia += timedelta(days=1)
    return max(1, total)


def demanda_dia(
    meta: dict[str, Any],
    registro: dict[str, Any],
    data: date,
    horas_na_semana_fora_de_hoje: float,
    tem_horario_util,
) -> float:
    """Horas que a meta pede hoje (``>= 0``)."""
    if not ativa_em(meta, data):
        return 0.0
    semana = clock.semana_iso(data)
    falta = demanda_semana(meta, registro, semana) - horas_na_semana_fora_de_hoje
    if falta <= 0:
        return 0.0
    return round(falta / dias_uteis_restantes(data, tem_horario_util), 2)


def horas_na_semana(
    blocos: dict[str, dict[str, Any]], meta_id: str, semana: str, excluir_data: Optional[date] = None
) -> float:
    """Horas alocadas ou confirmadas da meta na semana (estados que contam como
    alocadas: planejada, sem_sinal, movida, reagendada; feita confirmada ou
    presumida conta pela duração real quando houver), fora de ``excluir_data``."""
    total = 0.0
    for bloco in blocos.values():
        if bloco.get("meta") != meta_id:
            continue
        inicio = bloco.get("inicio")
        if not isinstance(inicio, datetime) or clock.semana_iso(inicio.date()) != semana:
            continue
        if excluir_data is not None and inicio.date() == excluir_data:
            continue
        estado = bloco.get("estado")
        if estado in ("planejada", "sem_sinal", "movida", "reagendada"):
            total += float(bloco.get("duracao_h", 0.0))
        elif estado == "feita":
            total += float(bloco.get("duracao_real_h") or bloco.get("duracao_h", 0.0))
    return total
