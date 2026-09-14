"""Janelas livres e alocação determinística dos blocos do dia (design "Janela livre" e "Balanço"; eng 2A).

Pipeline::

    cache compacto (eventos do dia)         horário útil do dia (contexto)
              |                                        |
              v                                        v
    ocupacoes(): regras de ocupação  ---------->  janelas_livres(): horário útil
      transparent = livre                           menos (ocupação + buffer dos
      cancelled = livre                             dois lados), gaps >= 30 min
      self_response declined = livre
      dia inteiro só ocupa se outOfOffice
      bloco nosso planejado/sem_sinal hoje = livre (o sync o mantém ou move)
      bloco nosso movido/reagendado = ocupa
              |
              v
    alocar(): metas em ordem (menor cobertura/demanda, prazo mais cedo, id),
      até 2 blocos por meta por dia, bloco entre 30 min e 2 h (múltiplos de
      15 min), duração = demanda_dia * fator_duracao tendendo a bloco_medio_h,
      restrições por meta (restricoes_horario), preferência por janelas de
      maior taxa de conclusão (perfil, só células com n >= 5), senão a mais cedo.

Tudo em hora local do bloco (fuso do contexto); a comparação de instantes
usa UTC. Determinístico: mesma entrada, mesma saída.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, NamedTuple, Optional

from goalpacer import clock, perfil as prf, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

MINIMO_MIN = 30
MAXIMO_H = 2.0
PASSO_MIN = 15
BLOCOS_POR_META_DIA = 2
EVENT_TYPE_FORA = "outOfOffice"
DIAS_CONTEXTO = ("seg_sex", "seg_sex", "seg_sex", "seg_sex", "seg_sex", "sab", "dom")


class Janela(NamedTuple):
    inicio: datetime
    fim: datetime

    @property
    def horas(self) -> float:
        return (self.fim - self.inicio).total_seconds() / 3600.0


class BlocoAlocado(NamedTuple):
    meta: str
    inicio: datetime
    fim: datetime

    @property
    def duracao_h(self) -> float:
        return round((self.fim - self.inicio).total_seconds() / 3600.0, 2)


def _hora(texto: str) -> time:
    horas, minutos = texto.split(":")
    return time(int(horas), int(minutos))


def horario_util(contexto: dict[str, Any], dia: date, tz) -> Optional[Janela]:
    """Janela do horário útil do dia (``None`` = dia sem blocos)."""
    chave = "horario_util_" + DIAS_CONTEXTO[dia.weekday()]
    valor = contexto.get(chave) or ""
    if not valor:
        return None
    if schema.RE_HORARIO_UTIL.fullmatch(valor) is None:
        raise GpErro(EXIT_VALIDACAO, "%s inválido: %r" % (chave, valor))
    inicio, fim = valor.split("-")
    return Janela(datetime.combine(dia, _hora(inicio), tzinfo=tz), datetime.combine(dia, _hora(fim), tzinfo=tz))


def tem_horario_util(contexto: dict[str, Any]):
    def _tem(dia: date) -> bool:
        return bool(contexto.get("horario_util_" + DIAS_CONTEXTO[dia.weekday()]) or "")

    return _tem


def _instante(texto: Any, tz) -> Optional[datetime]:
    lido = clock.instante(texto, tz) if isinstance(texto, str) else None
    return lido.astimezone(tz) if lido is not None else None


def ocupacoes(
    eventos: Iterable[dict[str, Any]],
    dia: date,
    tz,
    *,
    calendar_id_metas: str,
    instalacao_id: str,
    blocos_livres: Iterable[str] = (),
) -> list[Janela]:
    """Intervalos ocupados do dia, pelas regras do design.

    ``blocos_livres``: task_ids dos nossos blocos de hoje ``planejada``/``sem_sinal``
    cujos eventos não contam como ocupação (o sync os mantém ou move).
    """
    livres = set(blocos_livres)
    dia_inicio = datetime.combine(dia, time.min, tzinfo=tz)
    dia_fim = dia_inicio + timedelta(days=1)
    saida: list[Janela] = []
    for evento in eventos:
        if not isinstance(evento, dict) or not _ocupa(evento, livres, calendar_id_metas, instalacao_id):
            continue
        intervalo = _intervalo_dia_inteiro(evento, tz) if evento.get("all_day") else _intervalo_com_hora(evento, tz)
        if intervalo is None:
            continue
        inicio, fim = max(intervalo[0], dia_inicio), min(intervalo[1], dia_fim)
        if fim > inicio:
            saida.append(Janela(inicio, fim))
    saida.sort()
    return saida


def _ocupa(evento: dict[str, Any], livres: set[str], calendar_id_metas: str, instalacao_id: str) -> bool:
    """Cancelado, livre (transparente), recusado e o nosso bloco que ainda vai ser realocado não ocupam."""
    if evento.get("status") == "cancelled" or evento.get("transparency") == "transparent":
        return False
    if evento.get("self_response") == "declined":
        return False
    chave = evento.get("gp_key")
    if isinstance(chave, str) and chave.endswith("/" + instalacao_id):
        task_id = chave[3:].split("/", 1)[0]
        if task_id in livres and evento.get("calendar_id") == calendar_id_metas:
            return False
    return True


def _intervalo_dia_inteiro(evento: dict[str, Any], tz) -> Optional[tuple[datetime, datetime]]:
    """Dia inteiro só ocupa quando é ausência (fora do escritório); fim ausente ou invertido vira um dia."""
    if evento.get("event_type") != EVENT_TYPE_FORA:
        return None
    inicio, fim = _instante(evento.get("start"), tz), _instante(evento.get("end"), tz)
    if inicio is None:
        return None
    if fim is None or fim <= inicio:
        fim = inicio + timedelta(days=1)
    return inicio, fim


def _intervalo_com_hora(evento: dict[str, Any], tz) -> Optional[tuple[datetime, datetime]]:
    inicio, fim = _instante(evento.get("start"), tz), _instante(evento.get("end"), tz)
    if inicio is None or fim is None or fim <= inicio:
        return None
    return inicio, fim


def _fundir(intervalos: list[Janela]) -> list[Janela]:
    fundidos: list[Janela] = []
    for janela in sorted(intervalos):
        if fundidos and janela.inicio <= fundidos[-1].fim:
            fundidos[-1] = Janela(fundidos[-1].inicio, max(fundidos[-1].fim, janela.fim))
        else:
            fundidos.append(janela)
    return fundidos


def janelas_livres(
    horario: Optional[Janela], ocupado: list[Janela], buffer_min: int, minimo_min: int = MINIMO_MIN
) -> list[Janela]:
    """Gaps do horário útil fora das ocupações expandidas pelo buffer, com
    pelo menos ``minimo_min`` (``gap - 2 * buffer >= 30 min``)."""
    if horario is None:
        return []
    folga = timedelta(minutes=buffer_min)
    expandidos = _fundir([Janela(j.inicio - folga, j.fim + folga) for j in ocupado])
    livres: list[Janela] = []
    cursor = horario.inicio
    for janela in expandidos:
        if janela.fim <= cursor:
            continue
        if janela.inicio >= horario.fim:
            break
        if janela.inicio > cursor:
            livres.append(Janela(cursor, min(janela.inicio, horario.fim)))
        cursor = max(cursor, janela.fim)
    if cursor < horario.fim:
        livres.append(Janela(cursor, horario.fim))
    minimo = timedelta(minutes=minimo_min)
    return [j for j in livres if j.fim - j.inicio >= minimo]


def _arredondar_h(horas: float) -> float:
    passo = PASSO_MIN / 60.0
    return round(round(horas / passo) * passo, 2)


def duracao_bloco(demanda_h: float, fator_duracao: float = 1.0, bloco_medio_h: Optional[float] = None) -> float:
    """Duração planejada: demanda do dia × fator, puxada para o bloco médio do
    perfil, entre 30 min e 2 h, em múltiplos de 15 min."""
    alvo = max(0.0, demanda_h) * max(fator_duracao, 0.1)
    if bloco_medio_h:
        alvo = (alvo + bloco_medio_h) / 2.0
    return min(MAXIMO_H, max(MINIMO_MIN / 60.0, _arredondar_h(alvo)))


def _restricao(restricoes: Iterable[str], meta_id: str) -> Optional[tuple[time, time]]:
    for item in restricoes:
        partes = item.split()
        if len(partes) == 2 and partes[0] == meta_id and schema.RE_HORARIO_UTIL.fullmatch(partes[1]):
            inicio, fim = partes[1].split("-")
            return _hora(inicio), _hora(fim)
    return None


def _recortar(janelas: list[Janela], restricao: Optional[tuple[time, time]], dia: date, tz) -> list[Janela]:
    if restricao is None:
        return janelas
    inicio = datetime.combine(dia, restricao[0], tzinfo=tz)
    fim = datetime.combine(dia, restricao[1], tzinfo=tz)
    saida = []
    for j in janelas:
        a, b = max(j.inicio, inicio), min(j.fim, fim)
        if b > a:
            saida.append(Janela(a, b))
    return saida


def ordenar_metas(
    metas: dict[str, dict[str, Any]], demandas: dict[str, float], cobertura: dict[str, float]
) -> list[str]:
    """Ordem de alocação: menor cobertura/demanda, prazo mais cedo, id."""

    def chave(meta_id: str):
        demanda = demandas.get(meta_id, 0.0)
        razao = cobertura.get(meta_id, 0.0) / demanda if demanda > 0 else float("inf")
        return (razao, metas[meta_id]["prazo"], meta_id)

    return sorted((m for m in metas if demandas.get(m, 0.0) > 0), key=chave)


def alocar(
    janelas: list[Janela],
    metas: dict[str, dict[str, Any]],
    demandas: dict[str, float],
    *,
    dia: date,
    tz,
    cobertura: Optional[dict[str, float]] = None,
    perfil: Optional[dict[str, Any]] = None,
    restricoes: Iterable[str] = (),
) -> list[BlocoAlocado]:
    """Blocos do dia, determinísticos. ``demandas``: horas que cada meta pede hoje."""
    perfil = perfil or {}
    taxas = prf.janelas_confiaveis(perfil)
    bloco_medio = _bloco_medio(perfil)
    livres = sorted(janelas)
    saida: list[BlocoAlocado] = []
    for meta_id in ordenar_metas(metas, demandas, cobertura or {}):
        restante = demandas[meta_id]
        fator = float(perfil.get("metas", {}).get(meta_id, {}).get("fator_duracao", 1.0) or 1.0)
        restricao = _restricao(restricoes, meta_id)
        for _ in range(BLOCOS_POR_META_DIA):
            if restante <= 0.01:
                break
            recortadas = _recortar(livres, restricao, dia, tz)
            escolha = _escolher_janela(recortadas, duracao_bloco(restante, fator, bloco_medio), taxas)
            if escolha is None:
                break
            inicio, duracao = escolha
            fim = inicio + timedelta(hours=duracao)
            saida.append(BlocoAlocado(meta_id, inicio, fim))
            restante -= duracao
            livres = _sem_o_trecho(livres, inicio, fim)
    saida.sort(key=lambda b: (b.inicio, b.meta))
    return saida


def _bloco_medio(perfil: dict[str, Any]) -> Optional[float]:
    """O bloco médio só pesa com o mesmo mínimo de observações das janelas (eng 1.3)."""
    if int(perfil.get("n_confirmadas", 0) or 0) < prf.MINIMO_OBSERVACOES:
        return None
    return (perfil.get("preferencias") or {}).get("bloco_medio_h")


def _escolher_janela(
    recortadas: list[Janela], duracao: float, taxas: dict[str, float]
) -> Optional[tuple[datetime, float]]:
    """``(início, duração)`` na janela de faixa mais confiável que comporta o bloco; sem nenhuma, a maior que existe
    (>= 30 min) com o bloco encurtado para caber (múltiplo de 15 min); ``None`` sem janela útil."""
    candidatas = [j for j in recortadas if j.horas >= duracao]
    if candidatas:
        candidatas.sort(key=lambda j: (-taxas.get(prf.faixa_de(j.inicio), 0.0), j.inicio))
        return candidatas[0].inicio, duracao
    candidatas = [j for j in recortadas if j.horas >= MINIMO_MIN / 60.0]
    if not candidatas:
        return None
    candidatas.sort(key=lambda j: (-taxas.get(prf.faixa_de(j.inicio), 0.0), -j.horas, j.inicio))
    return candidatas[0].inicio, max(MINIMO_MIN / 60.0, _arredondar_h(candidatas[0].horas - 0.124))


def _sem_o_trecho(livres: list[Janela], inicio: datetime, fim: datetime) -> list[Janela]:
    """Tira o trecho usado da janela original (a candidata pode ser um recorte); pedaços menores que o mínimo somem."""
    novas: list[Janela] = []
    for j in livres:
        if not j.inicio <= inicio < j.fim:
            novas.append(j)
            continue
        if inicio > j.inicio:
            novas.append(Janela(j.inicio, inicio))
        if fim < j.fim:
            novas.append(Janela(fim, j.fim))
    return sorted(j for j in novas if j.fim - j.inicio >= timedelta(minutes=MINIMO_MIN))
