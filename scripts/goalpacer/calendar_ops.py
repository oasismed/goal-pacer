"""Leitura e escrita do Google Calendar pelos proxies (CEO 1.2, 2.3, 4.4; design "Blocos").

Leitura: ``ler_eventos`` faz um ``list_events`` paginado (``pageSize`` 25,
spike §4.6) de um calendário numa janela e devolve os eventos já
projetados (``proxy.projetar_eventos``). Em ``--offline`` a resposta crua
vem de ``offline`` e passa pela mesma projeção.

Escrita, keep+diff (só no calendário Metas)::

    bloco aberto (planejada/sem_sinal) sem evento         -> create
    bloco aberto com evento, janela diferente            -> update (start/end/description)
    bloco aberto com evento sem gp_key na descrição      -> update (só description)
    bloco cancelada com evento                           -> delete
    evento nosso (gp_key desta instalação) de hoje sem   -> delete
      bloco correspondente no .md
    duplicata (mesma gp_key em mais de um evento)        -> delete dos extras (fica o de created menor)
    bloco movida/reagendada/apagada/feita                -> nada (o usuário decidiu)

``executar_ops`` roda cada op num proxy (``modo_leitura=False``), grava
``status`` ok/erro e ``event_id_resultado``; nunca retenta uma op com erro
(``--verificar`` reaplica uma vez). ``--offline`` simula ``ok`` com ids
``off-<task_id>``. Os argumentos das tools de escrita seguem o schema do
conector visto no spike (``timeZone`` de topo, ``overrideReminders``,
``notificationLevel``); a escrita real ainda não foi exercitada (escopo),
por isso ficam concentrados em ``args_create``/``args_update``.
"""

from __future__ import annotations

import functools
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from goalpacer import clock, io as gpio, offline, proxy, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

TOOL_LIST_EVENTS = "mcp__claude_ai_Google_Calendar__list_events"
TOOL_CREATE = "mcp__claude_ai_Google_Calendar__create_event"
TOOL_UPDATE = "mcp__claude_ai_Google_Calendar__update_event"
TOOL_DELETE = "mcp__claude_ai_Google_Calendar__delete_event"
FULLTEXT_GC = "[GP]"
PREFIXO_TITULO = "[GP] "
TETO_TITULO = 60
NOTIFICACAO_NENHUMA = "NONE"
ESTADOS_ABERTOS = ("planejada", "sem_sinal")


_iso = clock.iso


# --- leitura ---------------------------------------------------------------


def ler_eventos(
    calendar_id: str,
    inicio: datetime,
    fim: datetime,
    *,
    calendar_id_metas: str,
    modo_offline: bool = False,
    full_text: Optional[str] = None,
    chamar: Optional[Callable[..., dict[str, Any]]] = None,
    registro: Any = None,
) -> list[dict[str, Any]]:
    """Eventos compactos de ``calendar_id`` entre ``inicio`` e ``fim``.

    ``full_text`` restringe por termo (``[GP]`` para achar blocos movidos
    para o primário); ``chamar`` substitui o proxy (testes). Resposta sem
    ``events`` é lista vazia.
    """
    args: dict[str, Any] = {"calendarId": calendar_id, "timeMin": _iso(inicio), "timeMax": _iso(fim)}
    if full_text:
        args["fullText"] = full_text
    projecao = functools.partial(proxy.projetar_eventos, calendar_id=calendar_id, calendar_id_metas=calendar_id_metas)
    if modo_offline:
        resposta = projecao(offline.chamar(TOOL_LIST_EVENTS, args))
        eventos = [e for e in (resposta.get("events") or []) if isinstance(e, dict)]
        return _fundir_sombra(eventos, calendar_id, inicio, fim, full_text)
    if chamar is not None:
        resposta = projecao(chamar(TOOL_LIST_EVENTS, args))
        return [e for e in (resposta.get("events") or []) if isinstance(e, dict)]
    return proxy.chamar_paginado(TOOL_LIST_EVENTS, args, chave_lista="events", projecao=projecao, registro=registro)


# --- lista de calendários do dia ----------------------------------------------------

TOOL_LIST_CALENDARS = "mcp__claude_ai_Google_Calendar__list_calendars"
PREFIXO_LISTA = "calendar-lista-"  # entra na retenção de 7 dias do cache (calendar-*.json)


def listar_calendarios(
    dados: Path, *, modo_offline: bool, agora: datetime, calendar_id_metas: Optional[str] = None, registro: Any = None
) -> list[dict[str, Any]]:
    """``list_calendars`` uma vez por dia: o mensal e o diário do mesmo job reaproveitam a lista (P2, análise de 13/09).

    Só no modo vivo (o offline lê sempre a fixture). Lista do dia sem o calendário Metas é refeita, porque a
    pessoa pode ter acabado de criá-lo. Guarda só id, nome e fuso de cada calendário."""
    if modo_offline:
        resposta = offline.chamar(TOOL_LIST_CALENDARS, {})
        return [c for c in (resposta.get("calendars") or []) if isinstance(c, dict) and c.get("id")]
    path = dados / "cache" / ("%s%s.json" % (PREFIXO_LISTA, agora.date().isoformat()))
    guardada = _lista_guardada(path, calendar_id_metas)
    if guardada:
        return guardada
    resposta = proxy.chamar(TOOL_LIST_CALENDARS, {}, registro=registro)
    calendarios = [
        {"id": str(c["id"]), "summary": str(c.get("summary") or ""), "timeZone": str(c.get("timeZone") or "")}
        for c in (resposta.get("calendars") or [])
        if isinstance(c, dict) and c.get("id")
    ]
    if calendarios:
        path.parent.mkdir(parents=True, exist_ok=True)
        gpio.escrever_json(path, {"calendars": calendarios})
    return calendarios


def _lista_guardada(path: Path, calendar_id_metas: Optional[str]) -> list[dict[str, Any]]:
    """A lista de hoje já gravada, se existe, é legível e tem o Metas; senão vazia (a chamada é refeita)."""
    if not path.exists():
        return []
    try:
        guardada = gpio.ler_json(path).get("calendars") or []
    except GpErro:
        return []
    if not guardada or (calendar_id_metas is not None and calendar_id_metas not in {c.get("id") for c in guardada}):
        return []
    return [c for c in guardada if isinstance(c, dict) and c.get("id")]


# --- sombra do modo offline -------------------------------------------------------

NOME_SOMBRA = "offline-eventos.json"


def _caminho_sombra() -> Path:
    from goalpacer import base

    return base.caminho_dados("cache", NOME_SOMBRA)


def _ler_sombra() -> dict[str, dict[str, Any]]:
    """Eventos criados/alterados/apagados pelas ops simuladas do ``--offline``
    (``id → evento compacto``; apagado = ``status: cancelled``). Assim
    ``diario --offline`` duas vezes vê os próprios blocos e gera zero ops."""
    from goalpacer import io as gpio

    path = _caminho_sombra()
    if not path.exists():
        return {}
    dados = gpio.ler_json(path)
    return dados if isinstance(dados, dict) else {}


def _gravar_sombra(sombra: dict[str, dict[str, Any]]) -> None:
    from goalpacer import io as gpio

    gpio.escrever_json(_caminho_sombra(), sombra)


def _fundir_sombra(
    eventos: list[dict[str, Any]], calendar_id: str, inicio: datetime, fim: datetime, full_text: Optional[str]
) -> list[dict[str, Any]]:
    from goalpacer import clock

    sombra = _ler_sombra()
    if not sombra:
        return eventos
    ids_sombra = set(sombra)
    saida = [e for e in eventos if str(e.get("id")) not in ids_sombra]
    for evento in sombra.values():
        if evento.get("calendar_id") != calendar_id:
            continue
        try:
            comeca = clock.parse_iso(str(evento.get("start")), tz_padrao=inicio.tzinfo)
        except GpErro:
            continue
        if not (inicio <= comeca < fim):
            continue
        if full_text and full_text not in str(evento.get("summary") or ""):
            continue
        saida.append(dict(evento))
    return saida


def _simular_op(op: dict[str, Any], sombra: dict[str, dict[str, Any]]) -> None:
    corpo = op.get("corpo") or {}
    if op["op"] == "create":
        novo_id = "off-" + op["task_id"]
        op["event_id_resultado"] = novo_id
        sombra[novo_id] = {
            "id": novo_id,
            "calendar_id": op["calendar_id"],
            "start": corpo.get("start", ""),
            "end": corpo.get("end", ""),
            "all_day": False,
            "status": "confirmed",
            "transparency": "opaque",
            "self_response": "",
            "event_type": "default",
            "recurring_event_id": "",
            "summary": corpo.get("summary"),
            "description": corpo.get("description"),
            "gp_key": proxy.gp_key_de(corpo.get("description")),
            "created": corpo.get("start", ""),
        }
    elif op["op"] == "update":
        evento = sombra.get(str(op.get("calendar_event_id")))
        if evento is not None:
            for chave in ("start", "end", "summary", "description"):
                if chave in corpo:
                    evento[chave] = corpo[chave]
            evento["gp_key"] = proxy.gp_key_de(evento.get("description"))
    elif op["op"] == "delete":
        ev_id = str(op.get("calendar_event_id"))
        sombra[ev_id] = dict(
            sombra.get(ev_id) or {"id": ev_id, "calendar_id": op["calendar_id"], "start": "", "end": ""},
            status="cancelled",
        )
    op["status"] = "ok"


# --- corpo dos eventos ------------------------------------------------------


gp_key = schema.gp_key


def titulo_evento(titulo: str) -> str:
    texto = " ".join(str(titulo).split())
    limite = TETO_TITULO - len(PREFIXO_TITULO)
    if len(texto) > limite:
        texto = texto[: limite - 1].rstrip() + "…"
    return PREFIXO_TITULO + texto


def descricao_evento(bloco: dict[str, Any], instalacao_id: str) -> str:
    """Porquê + efeito + ``gp:<task_id>/<instalacao_id>`` na ÚLTIMA linha."""
    linhas = [str(bloco.get("porque") or "").strip(), str(bloco.get("efeito") or "").strip()]
    linhas = [l for l in linhas if l]
    linhas.append(gp_key(bloco["id"], instalacao_id))
    return "\n".join(linhas)


def args_create(bloco: dict[str, Any], contexto: dict[str, Any]) -> dict[str, Any]:
    args = {
        "calendarId": contexto["calendar_id_metas"],
        "summary": titulo_evento(bloco.get("titulo") or ""),
        "description": descricao_evento(bloco, contexto["instalacao_id"]),
        "start": _iso(bloco["inicio"]),
        "end": _iso(bloco["fim"]),
        "timeZone": contexto["timezone"],
    }
    if contexto.get("lembretes", "nao") != "sim":
        args["overrideReminders"] = []
        args["notificationLevel"] = NOTIFICACAO_NENHUMA
    return args


def args_update(bloco: dict[str, Any], contexto: dict[str, Any], *, janela: bool) -> dict[str, Any]:
    args = {
        "calendarId": contexto["calendar_id_metas"],
        "eventId": bloco["calendar_event_id"],
        "description": descricao_evento(bloco, contexto["instalacao_id"]),
    }
    if janela:
        args["start"] = _iso(bloco["inicio"])
        args["end"] = _iso(bloco["fim"])
        args["timeZone"] = contexto["timezone"]
    return args


def args_delete(calendar_id: str, event_id: str) -> dict[str, Any]:
    return {"calendarId": calendar_id, "eventId": event_id}


# --- keep+diff ------------------------------------------------------------------


def _op(
    op: str, task_id: str, calendar_id: str, corpo: dict[str, Any], event_id: Optional[str] = None
) -> dict[str, Any]:
    item: dict[str, Any] = {"op": op, "task_id": task_id, "calendar_id": calendar_id, "corpo": corpo}
    if event_id:
        item["calendar_event_id"] = event_id
    return item


def _mesma_janela(bloco: dict[str, Any], evento: dict[str, Any]) -> bool:
    from goalpacer import clock

    try:
        inicio = clock.parse_iso(str(evento.get("start")), tz_padrao=bloco["inicio"].tzinfo)
        fim = clock.parse_iso(str(evento.get("end")), tz_padrao=bloco["inicio"].tzinfo)
    except GpErro:
        return False
    return clock.para_utc(inicio) == clock.para_utc(bloco["inicio"]) and clock.para_utc(fim) == clock.para_utc(
        bloco["fim"]
    )


def planejar_ops(
    blocos: Iterable[dict[str, Any]],
    eventos_metas: Iterable[dict[str, Any]],
    contexto: dict[str, Any],
    *,
    run_id: str,
    agora: datetime,
    dia: date,
) -> dict[str, Any]:
    """Documento ``ops`` (esquema ``ops``) com as ops planejadas, sem status."""
    metas_cal = contexto["calendar_id_metas"]
    por_id, por_chave = _indexar_eventos(eventos_metas, contexto["instalacao_id"])
    blocos = list(blocos)
    ops: list[dict[str, Any]] = []
    for bloco in sorted(blocos, key=lambda b: (b["inicio"], b["id"])):
        op = _op_do_bloco(bloco, por_id, por_chave, contexto)
        if op is not None:
            ops.append(op)
    usados = {str(b["calendar_event_id"]) for b in blocos if b.get("calendar_event_id")}
    ops.extend(_ops_de_orfaos_e_duplicatas(por_chave, {b["id"] for b in blocos}, usados, metas_cal, dia))
    doc = {"run_id": run_id, "calendar_id_metas": metas_cal, "gerado_em": _iso(agora), "ops": ops}
    erros = schema.validar_registro("ops", doc)
    if erros:
        raise GpErro(3, "ops planejadas inválidas: " + "; ".join(erros))
    return doc


def _indexar_eventos(
    eventos_metas: Iterable[dict[str, Any]], inst: str
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """``(por id, por gp_key desta instalação)``; eventos cancelados não entram."""
    por_id: dict[str, dict[str, Any]] = {}
    por_chave: dict[str, list[dict[str, Any]]] = {}
    for evento in eventos_metas:
        if not isinstance(evento, dict) or evento.get("status") == "cancelled":
            continue
        if evento.get("id"):
            por_id[str(evento["id"])] = evento
        chave = evento.get("gp_key")
        if isinstance(chave, str) and chave.endswith("/" + inst):
            por_chave.setdefault(chave, []).append(evento)
    return por_id, por_chave


def _op_do_bloco(
    bloco: dict[str, Any],
    por_id: dict[str, dict[str, Any]],
    por_chave: dict[str, list[dict[str, Any]]],
    contexto: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Casa o bloco com o evento (id guardado primeiro, depois a gp_key mais antiga) e decide create, update ou
    delete; estados finais que não são cancelados não mexem no Calendar."""
    metas_cal = contexto["calendar_id_metas"]
    chave = gp_key(bloco["id"], contexto["instalacao_id"])
    evento = por_id.get(str(bloco.get("calendar_event_id") or "")) if bloco.get("calendar_event_id") else None
    if evento is None and por_chave.get(chave):
        evento = min(por_chave[chave], key=lambda e: str(e.get("created") or ""))
        bloco["calendar_event_id"] = evento.get("id")
    estado = bloco.get("estado")
    if estado == "cancelada":
        if evento is None:
            return None
        return _op("delete", bloco["id"], metas_cal, args_delete(metas_cal, str(evento["id"])), str(evento["id"]))
    if estado not in ESTADOS_ABERTOS:
        return None
    if evento is None:
        return _op("create", bloco["id"], metas_cal, args_create(bloco, contexto))
    bloco["calendar_event_id"] = str(evento["id"])
    bloco["calendar_id"] = metas_cal
    janela_mudou = not _mesma_janela(bloco, evento)
    if not janela_mudou and evento.get("gp_key") == chave:
        return None
    return _op("update", bloco["id"], metas_cal, args_update(bloco, contexto, janela=janela_mudou), str(evento["id"]))


def _ops_de_orfaos_e_duplicatas(
    por_chave: dict[str, list[dict[str, Any]]], ids_no_md: set[str], usados: set[str], metas_cal: str, dia: date
) -> list[dict[str, Any]]:
    """Eventos nossos de hoje sem bloco no .md, e duplicatas. Evento que um bloco usa (``usados``, casado pelo id ou
    pela chave) nunca sai: na duplicata fica ele, ou o criado primeiro quando nenhum bloco usa nenhum."""
    ops = []
    for chave, eventos in sorted(por_chave.items()):
        task_id = chave[3:].split("/", 1)[0]
        extras = _sobras(eventos, usados, orfao_de=None if task_id in ids_no_md else dia)
        ops.extend(
            _op("delete", task_id, metas_cal, args_delete(metas_cal, str(evento["id"])), str(evento["id"]))
            for evento in extras
        )
    return ops


def _sobras(eventos: list[dict[str, Any]], usados: set[str], *, orfao_de: Optional[date]) -> list[dict[str, Any]]:
    """Eventos de uma mesma chave que saem: os não usados além do primeiro; se a chave não tem bloco no .md
    (``orfao_de`` = hoje), também os que começam hoje."""
    ordenados = sorted(eventos, key=lambda e: (str(e.get("created") or ""), str(e.get("id"))))
    livres = [e for e in ordenados if str(e.get("id")) not in usados]
    extras = livres[1:] if len(livres) == len(ordenados) else livres
    if orfao_de is None:
        return extras
    return [e for e in livres if str(e.get("start") or "")[:10] == orfao_de.isoformat() or e in extras]


TOOL_POR_OP = {"create": TOOL_CREATE, "update": TOOL_UPDATE, "delete": TOOL_DELETE}


def executar_ops(
    doc: dict[str, Any],
    *,
    calendar_id_metas: str,
    modo_offline: bool = False,
    chamar: Optional[Callable[..., dict[str, Any]]] = None,
    registro: Any = None,
) -> dict[str, Any]:
    """Executa cada op em série e preenche ``status``/``mensagem``/``event_id_resultado``.

    Erro do conector numa op não interrompe as demais e não é retentado
    aqui. ``--offline`` simula sucesso (``off-<task_id>``). Última barreira
    da regra "escrita só no Metas": op cujo ``calendarId`` não é
    ``calendar_id_metas`` nunca chega ao conector (``status: erro``)."""
    if not calendar_id_metas:
        raise GpErro(EXIT_VALIDACAO, "executar_ops sem calendar_id_metas")
    sombra = _ler_sombra() if modo_offline else {}
    chamada = chamar or functools.partial(proxy.chamar, modo_leitura=False, registro=registro)
    for op in doc.get("ops", []):
        if op.get("status") == "ok":
            continue
        if (op.get("corpo") or {}).get("calendarId") != calendar_id_metas or op.get("op") not in TOOL_POR_OP:
            op["status"] = "erro"
            op["mensagem"] = "op recusada: escrita fora do calendário Metas"
        elif modo_offline:
            _simular_op(op, sombra)
        else:
            _executar_op(op, chamada)
    if modo_offline and doc.get("ops"):
        _gravar_sombra(sombra)
    return doc


def _executar_op(op: dict[str, Any], chamada: Callable[..., dict[str, Any]]) -> None:
    try:
        resposta = chamada(TOOL_POR_OP[op["op"]], op["corpo"])
    except GpErro as erro:
        if op["op"] == "delete" and isinstance(erro, proxy.ErroConector) and erro.nao_encontrado:
            op["status"] = "ok"  # o evento já não existe: o delete chegou ao estado pedido (como no --offline)
            return
        op["status"] = "erro"
        op["mensagem"] = erro.mensagem[:200]
        return
    op["status"] = "ok"
    if op["op"] != "create":
        return
    novo_id = resposta.get("id") if isinstance(resposta, dict) else None
    if novo_id:
        op["event_id_resultado"] = str(novo_id)
    else:
        op["status"] = "erro"
        op["mensagem"] = "create_event sem id na resposta"


def aplicar_resultados(blocos: Iterable[dict[str, Any]], doc: dict[str, Any], calendar_id_metas: str) -> list[str]:
    """Grava ``calendar_event_id``/``calendar_id`` nos blocos criados com sucesso; devolve os ids com erro."""
    por_task = {b["id"]: b for b in blocos}
    com_erro: list[str] = []
    for op in doc.get("ops", []):
        bloco = por_task.get(op["task_id"])
        if op.get("status") != "ok":
            com_erro.append(op["task_id"])
            continue
        if op["op"] == "create" and bloco is not None:
            bloco["calendar_event_id"] = op.get("event_id_resultado")
            bloco["calendar_id"] = calendar_id_metas
    return com_erro


def ops_de_reparo(doc: dict[str, Any], run_id: str, agora: datetime) -> dict[str, Any]:
    """Segunda chance única para as ops com erro (CEO 2.3): mesmo corpo, novo documento."""
    ops = [dict(op, status=None, mensagem=None) for op in doc.get("ops", []) if op.get("status") != "ok"]
    for op in ops:
        op.pop("status", None)
        op.pop("mensagem", None)
    return {"run_id": run_id, "calendar_id_metas": doc["calendar_id_metas"], "gerado_em": _iso(agora), "ops": ops}


def ops_desinstalar(
    eventos_metas: Iterable[dict[str, Any]], contexto: dict[str, Any], *, run_id: str, agora: datetime
) -> dict[str, Any]:
    """Delete de todos os eventos com ``gp_key`` desta instalação no Metas (só do próprio ``instalacao_id``)."""
    inst = contexto["instalacao_id"]
    metas_cal = contexto["calendar_id_metas"]
    ops = []
    for evento in eventos_metas:
        chave = evento.get("gp_key") if isinstance(evento, dict) else None
        if isinstance(chave, str) and chave.endswith("/" + inst) and evento.get("id"):
            task_id = chave[3:].split("/", 1)[0]
            ops.append(_op("delete", task_id, metas_cal, args_delete(metas_cal, str(evento["id"])), str(evento["id"])))
    return {"run_id": run_id, "calendar_id_metas": metas_cal, "gerado_em": _iso(agora), "ops": ops}
