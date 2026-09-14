"""Inferência do check-in a partir do Calendar (CEO 4.3, 4.4; D4.11; design "Intocado / movido / apagado").

Entrada: os blocos abertos de ``dias/*.md`` (esquema ``task``, coagido) e
os eventos compactos (``proxy.projetar_eventos``) de um único
``list_events`` do calendário Metas cobrindo a janela dos blocos, mais os
eventos ``[GP]`` do primário (``fullText='[GP]'``). Saída: uma
``Inferencia`` por bloco em que o Calendar prova algo; o script grava via
``registro.registrar_checkin`` (que recusa sobrescrever confirmado).

Regras (instantes comparados em UTC; "mesmo dia" no fuso do bloco)::

    evento do bloco em Metas (por calendar_event_id, senão por gp_key):
        |start - inicio| <= 15 min e mesmo dia  -> intocado:
            fim <= agora  -> feita, origem presumido ("feita?")
            senão         -> sem_sinal, origem inferido (transitório)
        mesmo dia, outro horário                 -> movida, inferido (nova janela)
        outro dia                                -> reagendada, inferido (nova data)
    ausente (ou cancelled) em Metas:
        evento no primário com a mesma gp_key    -> movida/reagendada, calendar_id do primário
        senão, bloco tinha calendar_event_id     -> apagada, inferido
        senão (nunca foi criado)                 -> sem inferência

Só ``gp_key`` (regex estrita) e ids são usados para reconhecer blocos;
nunca texto livre. Bloco duplicado à mão não é detectável.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, NamedTuple, Optional

from goalpacer import clock, schema

TOLERANCIA_MIN = 15
STATUS_CANCELADO = "cancelled"


class Inferencia(NamedTuple):
    task_id: str
    estado: str
    origem: str
    motivo: str
    calendar_event_id: Optional[str] = None
    calendar_id: Optional[str] = None
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None


gp_key = schema.gp_key


def _instante(texto: Any, tz: Any) -> Optional[datetime]:
    """``start``/``end`` compactos → datetime consciente; dia inteiro vira 00:00 no fuso do bloco."""
    return clock.instante(texto, tz) if isinstance(texto, str) else None


def _indexar(eventos: Iterable[dict[str, Any]]) -> tuple[dict[tuple[str, str], dict], dict[tuple[str, str], dict]]:
    """``(calendar_id, id) → evento`` e ``(calendar_id, gp_key) → evento``."""
    por_id: dict[tuple[str, str], dict[str, Any]] = {}
    por_chave: dict[tuple[str, str], dict[str, Any]] = {}
    for evento in eventos:
        if not isinstance(evento, dict):
            continue
        cal = str(evento.get("calendar_id") or "")
        if evento.get("id"):
            por_id[(cal, str(evento["id"]))] = evento
        chave = evento.get("gp_key")
        if isinstance(chave, str) and schema.RE_GP_KEY.match(chave) and (cal, chave) not in por_chave:
            por_chave[(cal, chave)] = evento
    return por_id, por_chave


def _ativo(evento: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if evento is None or evento.get("status") == STATUS_CANCELADO:
        return None
    return evento


def _comparar(bloco: dict[str, Any], evento: dict[str, Any], agora: datetime, tolerancia: timedelta) -> Inferencia:
    task_id = bloco["id"]
    inicio_bloco: datetime = bloco["inicio"]
    fim_bloco: datetime = bloco["fim"]
    tz = inicio_bloco.tzinfo
    inicio_ev = _instante(evento.get("start"), tz)
    fim_ev = _instante(evento.get("end"), tz)
    cal = str(evento.get("calendar_id") or "")
    ev_id = str(evento.get("id") or "") or None
    if inicio_ev is None:
        return Inferencia(task_id, "sem_sinal", "inferido", "evento sem início legível", ev_id, cal)
    mesmo_dia = inicio_ev.astimezone(tz).date() == inicio_bloco.astimezone(tz).date()
    delta = abs(clock.para_utc(inicio_ev) - clock.para_utc(inicio_bloco))
    if not evento.get("all_day") and mesmo_dia and delta <= tolerancia:
        if clock.para_utc(fim_bloco) <= clock.para_utc(agora):
            return Inferencia(task_id, "feita", "presumido", "intocado e vencido", ev_id, cal, inicio_bloco, fim_bloco)
        return Inferencia(
            task_id, "sem_sinal", "inferido", "intocado, janela não venceu", ev_id, cal, inicio_bloco, fim_bloco
        )
    estado = "movida" if mesmo_dia else "reagendada"
    if fim_ev is None or clock.para_utc(fim_ev) <= clock.para_utc(inicio_ev):
        fim_ev = inicio_ev + (fim_bloco - inicio_bloco)
    motivo = "%s para %s" % (
        "movido" if mesmo_dia else "reagendado",
        inicio_ev.astimezone(tz).isoformat(timespec="minutes"),
    )
    if evento.get("all_day"):
        motivo += " (dia inteiro)"
    return Inferencia(task_id, estado, "inferido", motivo, ev_id, cal, inicio_ev, fim_ev)


def inferir(
    blocos: Iterable[dict[str, Any]],
    eventos: Iterable[dict[str, Any]],
    *,
    calendar_id_metas: str,
    calendar_id_primario: str,
    instalacao_id: str,
    agora: Optional[datetime] = None,
    tolerancia_min: int = TOLERANCIA_MIN,
) -> list[Inferencia]:
    """Uma ``Inferencia`` por bloco aberto sobre o qual o Calendar diz algo.

    ``blocos`` já coagidos (``inicio``/``fim`` datetime conscientes); blocos
    com estado final, ``origem: confirmado`` ou sem evento e sem
    ``calendar_event_id`` são pulados.
    """
    contexto = _Contexto(
        *_indexar(eventos),
        calendar_id_metas,
        calendar_id_primario,
        instalacao_id,
        agora or clock.agora(),
        timedelta(minutes=tolerancia_min),
    )
    abertos = (
        b
        for b in blocos
        if b.get("estado") in ("planejada", "sem_sinal", "movida", "reagendada") and b.get("origem") != "confirmado"
    )
    return [i for i in (_inferir_bloco(b, contexto) for b in abertos) if i is not None]


class _Contexto(NamedTuple):
    por_id: dict[tuple[str, str], dict[str, Any]]
    por_chave: dict[tuple[str, str], dict[str, Any]]
    metas: str
    primario: str
    instalacao_id: str
    agora: datetime
    tolerancia: timedelta


def _inferir_bloco(bloco: dict[str, Any], c: _Contexto) -> Optional[Inferencia]:
    """Evento no Metas (id, senão gp_key) > evento no primário (gp_key) > apagada, se o bloco tinha evento."""
    task_id = bloco["id"]
    chave = gp_key(task_id, c.instalacao_id)
    ev_id = bloco.get("calendar_event_id") or None
    ja_movido = bloco.get("estado") in ("movida", "reagendada")
    evento = (_ativo(c.por_id.get((c.metas, ev_id))) if ev_id else None) or _ativo(c.por_chave.get((c.metas, chave)))
    if evento is not None:
        inferencia = _comparar(bloco, evento, c.agora, c.tolerancia)
        return None if ja_movido and inferencia.estado == "sem_sinal" else inferencia  # movido até a janela vencer
    no_primario = _ativo(c.por_chave.get((c.primario, chave)))
    if no_primario is not None:
        return _no_primario(bloco, no_primario, c, ja_movido=ja_movido)
    if ev_id:
        return Inferencia(task_id, "apagada", "inferido", "evento ausente do Metas", ev_id, c.metas)
    return None


def _no_primario(
    bloco: dict[str, Any], evento: dict[str, Any], c: _Contexto, *, ja_movido: bool
) -> Optional[Inferencia]:
    inferencia = _comparar(bloco, evento, c.agora, c.tolerancia)
    if bloco.get("calendar_id") != c.primario and inferencia.estado in ("feita", "sem_sinal"):
        # Mesmo horário, mas em outro calendário: o usuário moveu o bloco de calendário.
        inferencia = inferencia._replace(estado="movida", origem="inferido", motivo="movido para o calendário primário")
    elif ja_movido and inferencia.estado == "sem_sinal":
        return None
    return inferencia._replace(calendar_id=c.primario)


def janela_dos_blocos(
    blocos: Iterable[dict[str, Any]], agora: datetime, folga_dias: int = 7
) -> tuple[datetime, datetime]:
    """``(inicio, fim)`` do ``list_events`` que cobre os blocos abertos, com folga
    para blocos reagendados; sem blocos, a semana em volta de ``agora``."""
    inicios = [b["inicio"] for b in blocos if isinstance(b.get("inicio"), datetime)]
    fins = [b["fim"] for b in blocos if isinstance(b.get("fim"), datetime)]
    folga = timedelta(days=folga_dias)
    inicio = min(inicios) - folga if inicios else agora - folga
    fim = max(fins) + folga if fins else agora + folga
    return inicio, fim
