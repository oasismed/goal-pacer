"""Fonte única de "agora", fusos e ids de calendário (achado 6.2 do plano).

Nenhum outro módulo chama ``datetime.now()``. Os CLIs aceitam ``--agora`` e
``--tz`` (ou ``GP_AGORA``/``GP_TZ``); ``run_job`` nunca passa ``--agora``.

Precedência de ``agora()``: valor fixado por ``fixar_agora`` > ``GP_AGORA`` >
relógio do sistema. Precedência de ``fuso()``: argumento > valor fixado por
``--tz`` > ``GP_TZ`` > fuso do sistema.

Semana ISO: ``AAAA-Www``; o mês de uma semana é o mês da sua quinta-feira.

Estado do módulo: ``_AGORA_FIXADO`` e ``_TZ_FIXADO`` (o conftest os zera
com ``monkeypatch.setattr``; use esses nomes).

Compatível com Python 3.9: ``datetime.fromisoformat`` daquela versão só
aceita fração de segundo com 3 ou 6 dígitos, offset com ``:`` e nada de
``Z``; ``normalizar_iso`` cobre essas diferenças (spike §4.4).
"""

from __future__ import annotations

import argparse
import functools
import os
import re
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

from goalpacer.base import EXIT_VALIDACAO, GpErro

ENV_AGORA = "GP_AGORA"
ENV_TZ = "GP_TZ"

_AGORA_FIXADO: Optional[datetime] = None
_TZ_FIXADO: Optional[str] = None

_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_HORA_INICIO = re.compile(r"^\d{2}:\d{2}")
_RE_OFFSET = re.compile(r"([+-])(\d{2})(?::?(\d{2}))?$")
_RE_FRACAO = re.compile(r"^(\d{2}:\d{2}:\d{2})\.(\d+)$")
_RE_SEMANA = re.compile(r"^(\d{4})-W(\d{2})$")

_DIGITOS_FRACAO = 6
_ARQUIVO_LOCALTIME = Path("/etc/localtime")


# ---------------------------------------------------------------- fusos


@functools.cache
def _zonas() -> frozenset[str]:
    """Nomes IANA conhecidos pelo zoneinfo (varredura cara; feita uma vez)."""
    return frozenset(available_timezones())


def _zona(nome: str) -> ZoneInfo:
    """``ZoneInfo`` de um nome IANA validado; inválido é ``GpErro``."""
    if not isinstance(nome, str) or nome not in _zonas():
        raise GpErro(
            EXIT_VALIDACAO,
            "fuso inválido: %r (use um nome IANA, ex.: America/Sao_Paulo)" % (nome,),
        )
    return ZoneInfo(nome)


def _nome_fuso_do_sistema() -> Optional[str]:
    """Nome IANA do fuso do sistema, se descobrível.

    Tenta ``TZ`` e depois o alvo do symlink ``/etc/localtime`` (no macOS,
    ``.../zoneinfo/America/Sao_Paulo``), casando os últimos segmentos do
    caminho com a lista do zoneinfo. ``None`` quando nada casa.
    """
    nome = os.environ.get("TZ")
    if nome and nome in _zonas():
        return nome
    if os.name == "nt":
        nome = _nome_fuso_windows()
        return nome if nome in _zonas() else None
    try:
        partes = _ARQUIVO_LOCALTIME.resolve().parts
    except OSError:
        return None
    for n in (1, 2, 3):
        candidato = "/".join(partes[-n:])
        if candidato in _zonas():
            return candidato
    return None


def _nome_fuso_windows() -> Optional[str]:  # pragma: no cover - só no Windows
    """Nome IANA do fuso do Windows pelo ICU que vem com o sistema (Windows 10 1903 em diante): o ``icu.dll`` traduz o
    fuso do Windows ("E. South America Standard Time") para o IANA ("America/Sao_Paulo")."""
    import ctypes

    try:
        icu = ctypes.CDLL("icu.dll")
        texto = ctypes.create_unicode_buffer(128)
        erro = ctypes.c_int(0)
        tamanho = icu.ucal_getDefaultTimeZone(texto, 128, ctypes.byref(erro))
    except (OSError, AttributeError):
        return None
    return texto.value[:tamanho] if erro.value <= 0 and tamanho > 0 else None


def _fuso_do_sistema() -> tzinfo:
    """Fuso do sistema: ``ZoneInfo`` quando o nome é descobrível; senão o
    offset fixo do relógio local (sem regra de horário de verão)."""
    nome = _nome_fuso_do_sistema()
    if nome is not None:
        return ZoneInfo(nome)
    local = datetime.now(timezone.utc).astimezone().tzinfo
    return local if local is not None else timezone.utc


def fuso(nome: Optional[str] = None) -> tzinfo:
    """``zoneinfo.ZoneInfo`` para ``nome`` (ou ``--tz``/``GP_TZ``/sistema).

    Valida contra ``zoneinfo.available_timezones()``; nome inválido é
    ``GpErro(EXIT_VALIDACAO)``. Sem nenhum nome, devolve o fuso do sistema.
    """
    if not nome:
        nome = _TZ_FIXADO or os.environ.get(ENV_TZ) or None
    if not nome:
        return _fuso_do_sistema()
    return _zona(nome)


# ---------------------------------------------------------------- ISO


def _erro_iso(texto: object, motivo: str) -> GpErro:
    resumo = repr(texto)
    if len(resumo) > 48:
        resumo = resumo[:45] + "..."
    return GpErro(EXIT_VALIDACAO, "data/hora inválida %s: %s" % (resumo, motivo))


def normalizar_iso(texto: str) -> str:
    """Prepara RFC 3339 para ``datetime.fromisoformat`` do 3.9.

    ``Z``/``z`` → ``+00:00``; fração de segundo truncada a 6 dígitos (e
    completada com zeros quando não tem 3 ou 6, exigência do 3.9);
    ``+0000`` → ``+00:00`` e ``+00`` → ``+00:00``; separador ``t``/espaço
    → ``T``. Data pura ``AAAA-MM-DD`` volta como está. O formato básico
    (data sem ``-`` ou hora sem ``:``) é ``GpErro(EXIT_VALIDACAO)``.
    """
    if not isinstance(texto, str):
        raise _erro_iso(texto, "esperado texto ISO 8601")
    texto = texto.strip()
    data, resto = texto[:10], texto[10:]
    if not _RE_DATA.match(data):
        raise _erro_iso(texto, "esperado AAAA-MM-DD (formato básico não é aceito)")
    if not resto:
        return data
    if resto[0] not in ("T", "t", " "):
        raise _erro_iso(texto, "esperado 'T' entre data e hora")
    hora = resto[1:]
    if not _RE_HORA_INICIO.match(hora):
        raise _erro_iso(texto, "esperado HH:MM na hora (formato básico não é aceito)")

    offset = ""
    if hora[-1] in ("Z", "z"):
        hora, offset = hora[:-1], "+00:00"
    else:
        m = _RE_OFFSET.search(hora)
        if m:
            hora = hora[: m.start()]
            offset = "%s%s:%s" % (m.group(1), m.group(2), m.group(3) or "00")

    m = _RE_FRACAO.match(hora)
    if m:
        fracao = m.group(2)[:_DIGITOS_FRACAO]
        if len(fracao) not in (3, _DIGITOS_FRACAO):
            fracao = fracao.ljust(_DIGITOS_FRACAO, "0")
        hora = "%s.%s" % (m.group(1), fracao)

    return "%sT%s%s" % (data, hora, offset)


def parse_iso(texto: str, tz_padrao: Optional[tzinfo] = None) -> datetime:
    """Texto ISO → datetime consciente.

    Data pura ``AAAA-MM-DD`` vira meia-noite em ``tz_padrao``; datetime sem
    offset recebe ``tz_padrao``; ``tz_padrao`` ausente = ``fuso()``.
    Texto inválido é ``GpErro(EXIT_VALIDACAO)``.
    """
    normalizado = normalizar_iso(texto)
    try:
        if len(normalizado) == 10:
            dt = datetime.combine(date.fromisoformat(normalizado), datetime.min.time())
        else:
            dt = datetime.fromisoformat(normalizado)
    except ValueError as exc:
        raise _erro_iso(texto, str(exc)) from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz_padrao if tz_padrao is not None else fuso())
    return dt


def para_utc(dt: datetime) -> datetime:
    """Converte para UTC (``timezone.utc``); naive é ``GpErro(EXIT_VALIDACAO)``."""
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise GpErro(EXIT_VALIDACAO, "datetime sem fuso: %r" % (dt,))
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------- agora


def fixar_agora(iso_ou_none: Optional[str]) -> None:
    """Fixa o instante devolvido por ``agora()`` (``None`` volta ao relógio).

    ``iso`` passa por ``parse_iso``; erro de formato é ``GpErro(EXIT_VALIDACAO)``.
    """
    global _AGORA_FIXADO
    _AGORA_FIXADO = None if iso_ou_none is None else parse_iso(iso_ou_none)


def agora(tz: Optional[tzinfo] = None) -> datetime:
    """Instante atual, sempre consciente de fuso.

    Devolve o valor fixado, senão ``GP_AGORA``, senão o relógio do sistema;
    convertido para ``tz`` (padrão: ``fuso()``).
    """
    if _AGORA_FIXADO is not None:
        instante = _AGORA_FIXADO
    else:
        env = os.environ.get(ENV_AGORA)
        instante = parse_iso(env) if env else datetime.now(timezone.utc)
    return instante.astimezone(tz if tz is not None else fuso())


def instante_real() -> datetime:
    """Relógio do sistema em UTC, ignorando ``GP_AGORA``: telemetria (quando algo aconteceu de fato) e validade de
    credenciais (aparelhos pareados do painel), que não podem seguir um relógio fixado."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- ids


def _como_date(data: date) -> date:
    if isinstance(data, datetime):
        return data.date()
    if not isinstance(data, date):
        raise GpErro(EXIT_VALIDACAO, "esperado date ou datetime, veio %r" % (data,))
    return data


def _semana_partes(semana: str) -> tuple:
    """``(ano, numero)`` de ``AAAA-Www``; inválido é ``GpErro``."""
    m = _RE_SEMANA.match(semana) if isinstance(semana, str) else None
    if not m:
        raise GpErro(EXIT_VALIDACAO, "semana inválida: %r (esperado AAAA-Www)" % (semana,))
    ano, numero = int(m.group(1)), int(m.group(2))
    try:
        date.fromisocalendar(ano, numero, 1)
    except ValueError:
        raise GpErro(EXIT_VALIDACAO, "semana inexistente: %s" % semana) from None
    return ano, numero


def semana_iso(data: date) -> str:
    """``AAAA-Www`` da semana ISO de ``data`` (ano ISO, não civil)."""
    iso = _como_date(data).isocalendar()
    return "%04d-W%02d" % (iso[0], iso[1])


def mes_da_semana(semana: str) -> str:
    """``AAAA-MM`` do mês da quinta-feira da semana ``AAAA-Www``."""
    ano, numero = _semana_partes(semana)
    return mes_id(date.fromisocalendar(ano, numero, 4))


def dias_da_semana(semana: str) -> list[date]:
    """Os 7 dias (segunda a domingo) da semana ``AAAA-Www``."""
    ano, numero = _semana_partes(semana)
    return [date.fromisocalendar(ano, numero, dia) for dia in range(1, 8)]


def mes_id(data: date) -> str:
    """``AAAA-MM``."""
    return _como_date(data).strftime("%Y-%m")


def semanas_do_mes(mes: str) -> list[str]:
    """Semanas ISO cuja quinta-feira cai no mês ``AAAA-MM``: a regra única do plano e do painel."""
    ano, numero = int(mes[:4]), int(mes[5:7])
    saida: list[str] = []
    dia = date(ano, numero, 1)
    while dia.month == numero:
        semana = semana_iso(dia)
        if semana not in saida and mes_da_semana(semana) == mes:
            saida.append(semana)
        dia += timedelta(days=1)
    return saida


def iso(instante: datetime) -> str:
    """Instante com offset, em segundos (formato gravado no registro e nas ops)."""
    return instante.isoformat(timespec="seconds")


def instante(valor: object, tz_padrao: Optional[tzinfo] = None) -> Optional[datetime]:
    """``datetime`` como veio, texto ISO lido com ``tz_padrao`` (sem offset), qualquer outra coisa ou texto ruim = ``None``."""
    if isinstance(valor, datetime):
        return (
            valor if valor.tzinfo is not None else valor.replace(tzinfo=tz_padrao if tz_padrao is not None else fuso())
        )
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return parse_iso(valor, tz_padrao=tz_padrao)
    except GpErro:
        return None


# ---------------------------------------------------------------- CLI


def adicionar_args_relogio(parser: argparse.ArgumentParser) -> None:
    """Adiciona ``--agora`` (ISO) e ``--tz`` (nome IANA) ao parser."""
    parser.add_argument(
        "--agora",
        metavar="ISO",
        default=None,
        help="instante a tratar como agora (ISO 8601, ex.: 2026-09-28T07:00:00-03:00); "
        "padrão: GP_AGORA ou o relógio do sistema",
    )
    parser.add_argument(
        "--tz",
        metavar="FUSO",
        default=None,
        help="fuso IANA (ex.: America/Sao_Paulo); padrão: GP_TZ ou o fuso do sistema",
    )


def aplicar_args_relogio(args: argparse.Namespace) -> None:
    """Fixa agora e fuso a partir de ``args.agora``/``args.tz`` ou do ambiente.

    Chamar logo depois de ``parse_args``. O fuso é aplicado antes do instante
    (um ``--agora`` sem offset usa o ``--tz``). Termina chamando ``agora()``
    para que ``GP_TZ``/``GP_AGORA`` inválidos falhem aqui, cedo. Fuso
    inválido é ``GpErro(EXIT_VALIDACAO)``.
    """
    global _TZ_FIXADO
    nome_tz = getattr(args, "tz", None) or None
    if nome_tz is not None:
        _zona(nome_tz)
    _TZ_FIXADO = nome_tz
    fixar_agora(getattr(args, "agora", None) or None)
    agora()
