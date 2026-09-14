#!/usr/bin/env python3
"""diario.py: inferir + gerar o dia + email (T6, T30; design "As cadências: diario" e "Email das 7h").

Em série, com o lock da pasta de dados::

    validar grafo -> calendário Metas existe? -> inferência (checkin.inferir; --sem-inferir pula)
    -> cache diário (list_events de cada calendário lido, compacto, validado)
    -> demanda do dia por meta -> janelas livres -> alocação (agenda)
    -> ids preservados (render.atribuir_ids) -> porquê (prosa viva ou template) e efeito
    -> ops keep+diff no Metas -> executa -> reparo único -> dias/<data>.md
    -> (--email) email das 7h pelo Gmail, uma vez por dia -> registro.geracoes[run_id]

``--offline``: proxies viram fixtures (``GP_OFFLINE_DIR``), ops são
simuladas, o email vai para ``cache/email-<run_id>.json`` e o porquê vem do
template (zero tokens); ``--prosa-viva`` liga a prosa real mesmo offline
(golden run). ``--reenviar-email``: nova tentativa do email do dia já gerado (o job usa quando o
envio falhou). ``--email-falha CLASSE``: só manda o email mínimo de falha
(o job usa quando o dia não foi gerado). ``--desinstalar [--confirmar]``:
blocos desta instalação no Metas. ``--data`` gera outro dia.

Exit: 0 ok · 2 sem onboarding/meta ativa · 3 inválido ou Metas ausente ·
4 IO/lock · 5 timeout (proxy).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import monotonic
from typing import Any, NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checkin
import validar
from goalpacer import (
    agenda,
    balanco,
    base,
    calendar_ops,
    cli,
    clock,
    conexoes,
    copy,
    correio,
    demanda,
    execucao,
    frontmatter,
    ia,
    io as gpio,
    leitura as gpleitura,
    offline,
    perfil as prf,
    prompts,
    proxy,
    registro as reg,
    render,
    respostas_email,
    saude,
    schema,
    telemetria,
    tom,
)
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro

TOOL_LIST_CALENDARS = "mcp__claude_ai_Google_Calendar__list_calendars"
MODO = "diario"
MODO_REENVIO = "diario-email"
TETO_AVISOS_SAUDE = 2  # alertas perto do limite no email (o resto fica no status)
CACHE_PREFIXO = "calendar-diario-"
ESTADOS_ABERTOS = ("planejada", "sem_sinal")
RE_LINHA_PORQUE = re.compile(r"^(D-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}):\s*(.+)$")
RE_DECISAO_PLANO = re.compile(r"^- (M[0-9]{2}): (.+)$")
FIXTURE_PORQUE = "prosa_porque.txt"


_contexto = frontmatter.ler_contexto


def _calendarios(
    dados: Path, contexto: dict[str, Any], *, modo_offline: bool, agora: datetime, registro_proxies: list
) -> list[dict[str, Any]]:
    return calendar_ops.listar_calendarios(
        dados,
        modo_offline=modo_offline,
        agora=agora,
        calendar_id_metas=contexto.get("calendar_id_metas"),
        registro=registro_proxies,
    )


def _run_id(agora: datetime) -> str:
    return os.environ.get(base.ENV_RUN_ID) or "%s-%s" % (MODO, agora.strftime("%Y%m%d-%H%M%S"))


# --- porquê --------------------------------------------------------------------------


def _porque_template(meta: dict[str, Any], demanda_semana_h: float, inicio: datetime) -> str:
    texto = copy.texto(
        "diario.porque_template",
        meta=render.rotulo_meta(meta["id"]),
        horas=balanco.horas(demanda_semana_h),
        hora=render.hora_curta(inicio),
    )
    return texto[: schema.TETO_PORQUE_CHARS]


def porques(
    blocos: list[dict[str, Any]],
    metas: dict[str, dict[str, Any]],
    registro: dict[str, Any],
    semana: str,
    *,
    dia: date,
    viva: bool,
    modo_offline: bool,
    run_id: str,
    registro_proxies: list,
    avisos: list[str],
) -> None:
    """Preenche ``porque`` de cada bloco aberto: prosa viva (uma chamada) com fallback por bloco para o template."""
    demandas = {b["id"]: demanda.demanda_semana(metas[b["meta"]], registro, semana) for b in blocos}
    gerados: dict[str, str] = {}
    if viva and blocos:
        try:
            gerados = _porques_vivos(
                blocos,
                metas,
                demandas,
                dia=dia,
                modo_offline=modo_offline,
                run_id=run_id,
                registro_proxies=registro_proxies,
            )
        except proxy.RateLimited:
            raise
        except GpErro as erro:
            avisos.append(copy.texto("mensal.prosa_template", classe=execucao.classe_de(erro)))
    for bloco in blocos:
        texto = gerados.get(bloco["id"], "")
        if texto and len(texto) <= schema.TETO_PORQUE_CHARS and tom.ok(texto):
            bloco["porque"] = texto
            continue
        if texto:
            telemetria.log("porquê de %s trocado pelo template" % bloco["id"], nivel="aviso")
        bloco["porque"] = _porque_template(metas[bloco["meta"]], demandas[bloco["id"]], bloco["inicio"])


def _porques_vivos(
    blocos: list[dict[str, Any]],
    metas: dict[str, dict[str, Any]],
    demandas: dict[str, float],
    *,
    dia: date,
    modo_offline: bool,
    run_id: str,
    registro_proxies: list,
) -> dict[str, str]:
    """Uma chamada de prosa para todos os blocos; devolve ``{task_id: porquê normalizado}`` das linhas no formato."""
    linhas = [
        "%s · %s · %s · %s · %s h na semana"
        % (
            b["id"],
            render.rotulo_meta(b["meta"]),
            metas[b["meta"]]["titulo"],
            render.hora_curta(b["inicio"]),
            ("%.1f" % demandas[b["id"]]).rstrip("0").rstrip("."),
        )
        for b in blocos
    ]
    texto_prompt = prompts.renderizar("porque", {"DATA": dia.isoformat(), "BLOCOS": "\n".join(linhas)})
    prompts.salvar(run_id, "porque", texto_prompt)
    if modo_offline and offline.texto(FIXTURE_PORQUE):
        resposta = offline.texto(FIXTURE_PORQUE)
    else:
        resposta = ia.prosa(texto_prompt, modelo="haiku", curta=True, registro=registro_proxies)
    gerados = {}
    for linha in resposta.split("\n"):
        m = RE_LINHA_PORQUE.match(linha.strip())
        if m:
            gerados[m.group(1)] = tom.normalizar(" ".join(m.group(2).split()))
    return gerados


# --- desde, decisão, avisos do plano ------------------------------------------------------


def ultima_geracao_antes(registro: dict[str, Any], dia: date) -> Optional[dict[str, Any]]:
    anteriores = [
        g
        for g in registro.get("geracoes", {}).values()
        if g.get("modo") == MODO and str(g.get("data")) < dia.isoformat()
    ]
    return max(anteriores, key=lambda g: (str(g.get("data")), str(g.get("ts")))) if anteriores else None


DIAS_FEITA_PRESUMIDA_NO_EMAIL = 2


def desde(
    aplicadas: list[dict[str, Any]],
    registro: dict[str, Any],
    todos: dict[str, dict[str, Any]],
    ultima: Optional[dict[str, Any]],
    tz,
    agora: Optional[datetime] = None,
) -> tuple[Optional[str], str, list[str], dict[str, int]]:
    """``(dia_curto, contagem, linhas, contagens)`` do que aconteceu desde o último diário.

    Presumidas ("feita?") ficam na lista por ``DIAS_FEITA_PRESUMIDA_NO_EMAIL`` dias
    (design 3.2) para o usuário corrigir; depois saem (continuam no registro)."""
    if ultima is None:
        return None, "", [], {"confirmadas": 0, "presumidas": 0, "movidas": 0}
    linhas: list[str] = []
    contagens = {"confirmadas": 0, "presumidas": 0, "movidas": 0, "fora": 0}
    vistos = _confirmadas_desde(registro, todos, str(ultima.get("ts") or ""), contagens, linhas)
    for item in aplicadas:
        if item["task_id"] in vistos or item["estado"] == "sem_sinal" or item["task_id"] not in todos:
            continue
        linha = _linha_inferida(item, todos[item["task_id"]], tz, contagens)
        if linha is not None:
            linhas.append(linha)
    if agora is not None:
        excluidos = vistos | {item["task_id"] for item in aplicadas}
        _presumidas_recentes(registro, todos, excluidos, agora, contagens, linhas)
    partes = [
        copy.texto("desde.contagem_%s" % chave, n=contagens[chave])
        for chave in ("confirmadas", "presumidas", "movidas", "fora")
        if contagens[chave]
    ]
    dia_ultimo = date.fromisoformat(str(ultima["data"]))
    return copy.dia_curto(dia_ultimo), " · ".join(partes), linhas, contagens


CHAVES_CONFIRMADAS = {"feita": "desde.confirmada", "nao_feita": "desde.nao_feita"}


def _linha_do_bloco(chave: str, bloco: dict[str, Any], **extra: str) -> str:
    return copy.texto(chave, titulo=bloco.get("titulo", ""), meta=render.rotulo_meta(bloco["meta"]), **extra)


def _confirmadas_desde(
    registro: dict[str, Any], todos: dict[str, dict[str, Any]], corte: str, contagens: dict[str, int], linhas: list[str]
) -> set[str]:
    """Linhas das confirmações feitas depois do último diário; devolve os blocos vistos (não se repetem abaixo)."""
    vistos = set()
    for task_id, item in sorted(registro.get("checkins", {}).items()):
        if item.get("origem") != "confirmado" or str(item.get("ts")) <= corte or not todos.get(task_id):
            continue
        vistos.add(task_id)
        chave = CHAVES_CONFIRMADAS.get(item.get("estado"))
        if chave:
            contagens["confirmadas"] += 1 if item.get("estado") == "feita" else 0
            linhas.append(_linha_do_bloco(chave, todos[task_id]))
    return vistos


def _linha_inferida(item: dict[str, Any], bloco: dict[str, Any], tz, contagens: dict[str, int]) -> Optional[str]:
    estado = item["estado"]
    if estado == "feita":
        contagens["presumidas"] += 1
        return _linha_do_bloco("desde.feita_presumida", bloco)
    if estado in ("movida", "reagendada"):
        contagens["movidas"] += 1
        novo = clock.parse_iso(item["inicio"]).astimezone(tz) if item.get("inicio") else bloco["inicio"]
        if estado == "movida":
            return _linha_do_bloco("desde.movida", bloco, hora=render.hora_curta(novo))
        return _linha_do_bloco("desde.reagendada", bloco, dia=copy.dia_curto(novo.date()), hora=render.hora_curta(novo))
    if estado == "apagada":
        contagens["fora"] += 1
        return _linha_do_bloco("desde.apagada", bloco)
    return None


def _presumidas_recentes(
    registro: dict[str, Any],
    todos: dict[str, dict[str, Any]],
    excluidos: set[str],
    agora: datetime,
    contagens: dict[str, int],
    linhas: list[str],
) -> None:
    limite = (agora - timedelta(days=DIAS_FEITA_PRESUMIDA_NO_EMAIL)).isoformat(timespec="seconds")
    for task_id, item in sorted(registro.get("checkins", {}).items()):
        if task_id in excluidos or task_id not in todos:
            continue
        if item.get("origem") == "presumido" and item.get("estado") == "feita" and str(item.get("ts")) >= limite:
            contagens["presumidas"] += 1
            linhas.append(_linha_do_bloco("desde.feita_presumida", todos[task_id]))


def plano_do_dia(dados: Path, dia: date) -> tuple[Optional[dict[str, Any]], list[tuple[str, str]]]:
    """``(front-matter, [(meta, texto da decisão)])`` do plano do mês da semana de ``dia``."""
    mes = clock.mes_da_semana(clock.semana_iso(dia))
    path = dados / "planos" / ("%s.md" % mes)
    if not path.exists():
        return None, []
    try:
        fm, corpo = frontmatter.ler_arquivo(path)
    except GpErro:
        return None, []
    decisoes = []
    secao = False
    for linha in corpo.split("\n"):
        if linha.startswith("## "):
            secao = linha.strip() == "## Decisões"
            continue
        m = RE_DECISAO_PLANO.match(linha.strip()) if secao else None
        if m:
            decisoes.append((m.group(1), m.group(2)))
    return fm, decisoes


def decisao_do_email(
    fm_plano: Optional[dict[str, Any]], decisoes: list[tuple[str, str]], dia: date, tz
) -> tuple[bool, Optional[tuple[str, str]]]:
    """``(plano_novo, decisão em caixa)``: a caixa de decisão sai no dia em que o plano foi gerado e às segundas (design 1.3)."""
    plano_novo = (
        bool(fm_plano)
        and isinstance(fm_plano.get("gerado_em"), datetime)
        and fm_plano["gerado_em"].astimezone(tz).date() == dia
    )
    if decisoes and (plano_novo or dia.weekday() == 0):
        return plano_novo, (render.rotulo_meta(decisoes[0][0]), decisoes[0][1])
    return plano_novo, None


def montar_email(dados: Path, dia: date) -> tuple[str, str, str]:
    """``(assunto, texto, html)`` do email de ``dias/<dia>.md`` sem enviar nada (``--email-texto``/``--email-html``, T30)."""
    path = dados / "dias" / ("%s.md" % dia.isoformat())
    if not path.exists():
        raise GpErro(
            EXIT_ESTADO, "dias/%s.md não existe; rode diario.py --data %s" % (dia.isoformat(), dia.isoformat())
        )
    contexto = _contexto(dados)
    tz = clock.fuso(contexto["timezone"])
    registro = reg.carregar(dados)
    fm_plano, decisoes = plano_do_dia(dados, dia)
    _, decisao = decisao_do_email(fm_plano, decisoes, dia, tz)
    modelo = render.modelo_email(
        render.ler_dia(path.read_text(encoding="utf-8")),
        primeiro_dia=ultima_geracao_antes(registro, dia) is None,
        decisao=decisao,
    )
    assunto, corpo = render.email_texto(modelo)
    return assunto, corpo, render.email_html(modelo)


def custos_pendentes(dados: Path, metas: dict[str, dict[str, Any]]) -> list[str]:
    avisos = []
    for meta_id in sorted(metas):
        path = dados / "fontes" / ("%s.md" % meta_id)
        if not path.exists() or metas[meta_id].get("estado", "ativa") != "ativa":
            continue
        try:
            fm, _ = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        if fm.get("estado") == "pendente":
            avisos.append(copy.texto("mensal.custo_pendente", meta=render.rotulo_meta(meta_id)))
    return avisos


# --- cache e geração ------------------------------------------------------------------------


def cache_do_dia(
    contexto: dict[str, Any],
    calendarios: list[dict[str, Any]],
    dia: date,
    tz,
    *,
    modo_offline: bool,
    run_id: str,
    agora: datetime,
    registro_proxies: list,
) -> dict[str, Any]:
    inicio = datetime.combine(dia, time.min, tzinfo=tz)
    fim = inicio + timedelta(days=1)
    lidos = set(contexto.get("calendarios_lidos") or [c["id"] for c in calendarios])
    lidos |= {contexto["calendar_id_primario"], contexto["calendar_id_metas"]}
    eventos: list[dict[str, Any]] = []
    for cal_id in sorted(lidos):
        eventos += calendar_ops.ler_eventos(
            cal_id,
            inicio,
            fim,
            calendar_id_metas=contexto["calendar_id_metas"],
            modo_offline=modo_offline,
            registro=registro_proxies,
        )
    cache = {
        "calendar_id_metas": contexto["calendar_id_metas"],
        "janela_inicio": inicio.isoformat(timespec="seconds"),
        "janela_fim": fim.isoformat(timespec="seconds"),
        "gerado_em": agora.isoformat(timespec="seconds"),
        "run_id": run_id,
        "calendarios": [
            {"id": str(c["id"]), "summary": str(c.get("summary") or ""), "time_zone": str(c.get("timeZone") or "")}
            for c in calendarios
            if c["id"] in lidos
        ],
        "eventos": eventos,
    }
    erros = schema.validar_registro("cache_calendar", cache)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "cache do Calendar inválido (CacheInvalid): " + "; ".join(erros[:5]))
    return cache


class _Rodada(NamedTuple):
    """O que todo passo do diário lê: pasta, dia, relógio, execução, contexto e as chamadas de conector feitas."""

    dados: Path
    dia: date
    agora: datetime
    run_id: str
    modo_offline: bool
    contexto: dict[str, Any]
    tz: Any
    registro_proxies: list


def gerar(
    dados: Path,
    *,
    dia: date,
    modo_offline: bool,
    sem_inferir: bool,
    agora: Optional[datetime] = None,
    run_id: Optional[str] = None,
    enviar_email: bool = False,
    prosa_viva: bool = False,
) -> dict[str, Any]:
    agora = agora or clock.agora()
    contexto = validar.contexto_valido(dados)
    r = _Rodada(
        dados, dia, agora, run_id or _run_id(agora), modo_offline, contexto, clock.fuso(contexto["timezone"]), []
    )
    avisos = _aviso_de_fuso(contexto)
    calendarios = _calendarios_com_metas(r)
    aplicadas = [] if sem_inferir else _inferir(r, avisos)
    registro = reg.carregar(dados)
    ultima = ultima_geracao_antes(registro, dia)
    metas = prf._ler_metas(dados)
    perfil = prf.calcular(dados, agora)
    prf.gravar(dados, perfil)
    cache = _agenda_do_dia(r, calendarios)
    todos = prf.blocos_com_registro(dados, registro)
    fixos, abertos_anteriores = _fixos_e_abertos(todos, dia, r.tz)
    semana = clock.semana_iso(dia)
    janelas = _janelas(r, cache, fixos, abertos_anteriores)
    blocos_abertos = _alocar(r, janelas, metas, registro, perfil, todos, fixos, abertos_anteriores)
    porques(
        blocos_abertos,
        metas,
        registro,
        semana,
        dia=dia,
        viva=(not modo_offline) or prosa_viva,
        modo_offline=modo_offline,
        run_id=r.run_id,
        registro_proxies=r.registro_proxies,
        avisos=avisos,
    )
    coach_do_dia = gpleitura.leitura(dados, agora)
    for bloco in blocos_abertos:
        bloco["efeito"] = gpleitura.efeito_do_bloco(coach_do_dia, bloco["meta"])
    fixos += _cancelar_vencidos(r, abertos_anteriores, blocos_abertos, metas, registro)
    blocos = fixos + blocos_abertos
    for bloco in blocos:
        bloco.pop("_dia", None)
    doc_ops, com_erro = _sincronizar_agenda(r, blocos, cache)
    avisos.extend(copy.texto("diario.op_parcial", bloco=task_id) for task_id in com_erro)
    fm_plano, decisoes = plano_do_dia(dados, dia)
    plano_novo, decisao = decisao_do_email(fm_plano, decisoes, dia, r.tz)
    _avisos_do_plano(avisos, decisoes, decisao, plano_novo, metas, semana)
    avisos += custos_pendentes(dados, metas)
    avisos += [a["texto"] for a in saude.alertas(dados, agora, registro, so_do_job=True)][:TETO_AVISOS_SAUDE]
    motivo = "sem_janela" if not (blocos_abertos or janelas) else None
    if motivo:
        avisos.insert(0, copy.texto("diario.sem_janela"))
    resumo = _linha_resumo(blocos_abertos, janelas)
    secao_desde, contagens = _secao_desde(aplicadas, registro, todos, ultima, r)
    texto = render.render_dia(
        dia,
        r.run_id,
        blocos,
        resumo_linha=resumo,
        progresso=gpleitura.resumo_coach(coach_do_dia),
        desde=secao_desde,
        avisos=avisos,
        motivo=motivo,
        decisao_pendente=next((meta_id for meta_id, _ in decisoes), None),
        contagens=contagens,
    )
    gpio.escrever_atomico(base.caminho_dados("dias", dia.isoformat() + ".md"), texto)
    email_status, email_info = ("nao_enviado", {})
    if enviar_email:
        email_status, email_info = _email_do_dia(r, registro, texto, primeiro_dia=ultima is None, decisao=decisao)
    _registrar_geracao(r, registro, metas, email_status)
    return {
        "data": dia.isoformat(),
        "run_id": r.run_id,
        "arquivo": "dias/%s.md" % dia.isoformat(),
        "blocos": [b["id"] for b in blocos_abertos],
        "fixos": [b["id"] for b in fixos],
        "janelas": len(janelas),
        "ops": _contar_ops(doc_ops),
        "motivo": motivo,
        "avisos": avisos,
        "resumo": resumo,
        "email": email_info or {"status": "nao_enviado"},
        "primeiro_dia": ultima is None,
        "decisao": decisao[0] if decisao else None,
    }


def _agenda_do_dia(r: _Rodada, calendarios: list[dict[str, Any]]) -> dict[str, Any]:
    """O cache da agenda do dia; sem Google Calendar, nenhum evento (as janelas são o horário útil)."""
    if not conexoes.usa_agenda(r.contexto):
        return {"eventos": []}
    cache = cache_do_dia(
        r.contexto,
        calendarios,
        r.dia,
        r.tz,
        modo_offline=r.modo_offline,
        run_id=r.run_id,
        agora=r.agora,
        registro_proxies=r.registro_proxies,
    )
    gpio.escrever_json(base.caminho_dados("cache", CACHE_PREFIXO + r.dia.isoformat() + ".json"), cache)
    return cache


def _aviso_de_fuso(contexto: dict[str, Any]) -> list[str]:
    """Fuso do sistema diferente do contexto (viagem): as janelas seguem o contexto e o email avisa (achado 4.3)."""
    fuso_sistema = getattr(clock.fuso(), "key", "")
    if fuso_sistema and fuso_sistema != contexto["timezone"] and not clock._AGORA_FIXADO:
        return [copy.texto("diario.fuso_divergente", fuso=fuso_sistema)]
    return []


def _calendarios_com_metas(r: _Rodada) -> list[dict[str, Any]]:
    if not conexoes.usa_agenda(r.contexto):
        return []  # sem Google Calendar: nada a listar, as janelas são o horário útil
    calendarios = _calendarios(
        r.dados, r.contexto, modo_offline=r.modo_offline, agora=r.agora, registro_proxies=r.registro_proxies
    )
    if calendarios and r.contexto["calendar_id_metas"] not in {c["id"] for c in calendarios}:
        raise GpErro(EXIT_VALIDACAO, copy.texto("diario.metas_nao_encontrado"), classe="MetasNaoEncontrado")
    return calendarios


def _secao_desde(
    aplicadas: list[dict[str, Any]],
    registro: dict[str, Any],
    todos: dict[str, dict[str, Any]],
    ultima: Optional[dict[str, Any]],
    r: _Rodada,
) -> tuple[Optional[tuple[str, str, list[str]]], dict[str, int]]:
    """``((dia, contagem, linhas) ou None sem diário anterior, contagens)`` para o render do dia."""
    dia_desde, contagem, linhas, contagens = desde(aplicadas, registro, todos, ultima, r.tz, r.agora)
    return ((dia_desde, contagem, linhas) if dia_desde else None), contagens


def _registrar_geracao(r: _Rodada, registro: dict[str, Any], metas: dict[str, dict[str, Any]], email: str) -> None:
    conexoes.registrar_uso(r.registro_proxies, r.agora, simulado=r.modo_offline)
    reg.registrar_geracao(
        registro,
        {
            "run_id": r.run_id,
            "modo": MODO,
            "data": r.dia.isoformat(),
            "ts": clock.agora().isoformat(timespec="seconds"),
            "exit_code": 0,
            "duracao_s": 0.0,
            "tokens": somar_tokens(r.registro_proxies),
            "sessoes": [x["session_id"] for x in r.registro_proxies if x.get("session_id")],
            "email": email,
            "hash_metas": schema.hash_metas(metas.values()),
        },
    )
    reg.salvar(registro, r.dados)


def _inferir(r: _Rodada, avisos: list[str]) -> list[dict[str, Any]]:
    """Respostas ao email das 7h primeiro (confirmação vence inferência), depois a inferência pelo Calendar; sem
    Gmail ou sem Calendar, o passo correspondente não existe (o check-in fica com a pessoa, no painel)."""
    if conexoes.usa_email(r.contexto):
        _respostas_ao_email(r, avisos)
    if not conexoes.usa_agenda(r.contexto):
        return []
    return checkin.inferir(r.dados, modo_offline=r.modo_offline, agora=r.agora)["aplicadas"]


def _respostas_ao_email(r: _Rodada, avisos: list[str]) -> None:
    try:
        por_email = respostas_email.aplicar(
            r.dados,
            modo_offline=r.modo_offline,
            agora=r.agora,
            registro_proxies=r.registro_proxies,
            confirmar=checkin.confirmar,
        )
        if por_email["confirmados"] or por_email["nao_feitos"]:
            avisos.append(
                copy.texto(
                    "diario.respostas_email", confirmados=por_email["confirmados"], nao_feitos=por_email["nao_feitos"]
                )
            )
    except proxy.RateLimited:
        raise
    except GpErro as erro:
        telemetria.log("respostas ao email não lidas: %s" % execucao.classe_de(erro), nivel="aviso")


def _fixos_e_abertos(
    todos: dict[str, dict[str, Any]], dia: date, tz
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Blocos de hoje e reagendados para hoje: os com estado final ficam fixos; os abertos serão realocados."""
    de_hoje = {tid: b for tid, b in todos.items() if b.get("_dia") == dia.isoformat()}
    importados = [
        b
        for tid, b in todos.items()
        if b.get("_dia") != dia.isoformat()
        and b.get("estado") == "reagendada"
        and b["inicio"].astimezone(tz).date() == dia
        and tid not in de_hoje
    ]
    fixos = [b for b in [*de_hoje.values(), *importados] if b.get("estado") not in ESTADOS_ABERTOS]
    abertos = [b for b in de_hoje.values() if b.get("estado") in ESTADOS_ABERTOS]
    return fixos, abertos


def _janelas(
    r: _Rodada, cache: dict[str, Any], fixos: list[dict[str, Any]], abertos_anteriores: list[dict[str, Any]]
) -> list:
    ocupado = agenda.ocupacoes(
        cache["eventos"],
        r.dia,
        r.tz,
        calendar_id_metas=r.contexto.get("calendar_id_metas") or "",
        instalacao_id=r.contexto["instalacao_id"],
        blocos_livres=[b["id"] for b in abertos_anteriores],
    )
    ocupado += [
        agenda.Janela(b["inicio"].astimezone(r.tz), b["fim"].astimezone(r.tz))
        for b in fixos
        if b.get("estado") in ("movida", "reagendada") and b["inicio"].astimezone(r.tz).date() == r.dia
    ]
    horario = agenda.horario_util(r.contexto, r.dia, r.tz)
    return agenda.janelas_livres(horario, sorted(ocupado), int(r.contexto.get("buffer_min", 10)))


def _alocar(
    r: _Rodada,
    janelas: list,
    metas: dict[str, dict[str, Any]],
    registro: dict[str, Any],
    perfil: dict[str, Any],
    todos: dict[str, dict[str, Any]],
    fixos: list[dict[str, Any]],
    abertos_anteriores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Demanda do dia por meta -> alocação nas janelas -> ids preservados dos blocos abertos que continuam."""
    semana = clock.semana_iso(r.dia)
    tem_util = agenda.tem_horario_util(r.contexto)
    demandas: dict[str, float] = {}
    cobertura: dict[str, float] = {}
    for meta_id, meta in metas.items():
        fora_de_hoje = demanda.horas_na_semana(todos, meta_id, semana, excluir_data=r.dia)
        fixos_hoje = sum(
            float(b.get("duracao_real_h") or b.get("duracao_h", 0.0))
            for b in fixos
            if b.get("meta") == meta_id and b.get("estado") in ("feita", "movida", "reagendada")
        )
        demandas[meta_id] = demanda.demanda_dia(meta, registro, r.dia, fora_de_hoje + fixos_hoje, tem_util)
        semana_h = demanda.demanda_semana(meta, registro, semana)
        cobertura[meta_id] = (fora_de_hoje + fixos_hoje) / semana_h if semana_h > 0 else 0.0
    alocados = agenda.alocar(
        janelas,
        {m: metas[m] for m in metas if demanda.ativa_em(metas[m], r.dia)},
        demandas,
        dia=r.dia,
        tz=r.tz,
        cobertura=cobertura,
        perfil=perfil,
        restricoes=r.contexto.get("restricoes_horario") or [],
    )
    novos = [
        {
            "titulo": render.titulo_bloco(metas[a.meta]["titulo"]),
            "meta": a.meta,
            "semana": semana,
            "inicio": a.inicio,
            "fim": a.fim,
            "duracao_h": a.duracao_h,
            "estado": "planejada",
            "origem": "inferido",
        }
        for a in alocados
    ]
    ids_anteriores = {b["id"] for b in abertos_anteriores}
    reservados = [tid for tid in todos if tid.startswith("D-%s-" % r.dia.isoformat()) and tid not in ids_anteriores]
    return render.atribuir_ids(novos, abertos_anteriores, r.dia, reservados=reservados)


def _cancelar_vencidos(
    r: _Rodada,
    abertos_anteriores: list[dict[str, Any]],
    blocos_abertos: list[dict[str, Any]],
    metas: dict[str, dict[str, Any]],
    registro: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bloco aberto que não voltou e cuja meta saiu do prazo (ou foi arquivada) vira ``cancelada`` por prazo."""
    ids_abertos = {b["id"] for b in blocos_abertos}
    cancelados = []
    for bloco in abertos_anteriores:
        meta = metas.get(bloco["meta"], {"estado": "arquivada", "prazo": r.dia})
        if bloco["id"] in ids_abertos or demanda.ativa_em(meta, r.dia):
            continue
        bloco["estado"], bloco["origem"] = "cancelada", "prazo"
        reg.registrar_checkin(registro, bloco["id"], "cancelada", "prazo", ts=r.agora)
        cancelados.append(bloco)
    return cancelados


def _sincronizar_agenda(
    r: _Rodada, blocos: list[dict[str, Any]], cache: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Ops keep+diff no Metas -> executa -> um reparo para as que falharam; grava ``cache/ops-<run_id>.json``. Sem
    Google Calendar, nenhuma op: os blocos ficam só no app."""
    if not conexoes.usa_agenda(r.contexto):
        return {"ops": []}, []
    metas_id = r.contexto["calendar_id_metas"]
    eventos_metas = [e for e in cache["eventos"] if e.get("calendar_id") == metas_id]
    doc_ops = calendar_ops.planejar_ops(blocos, eventos_metas, r.contexto, run_id=r.run_id, agora=r.agora, dia=r.dia)
    calendar_ops.executar_ops(
        doc_ops, calendar_id_metas=metas_id, modo_offline=r.modo_offline, registro=r.registro_proxies
    )
    com_erro = calendar_ops.aplicar_resultados(blocos, doc_ops, metas_id)
    if com_erro:
        reparo = calendar_ops.ops_de_reparo(doc_ops, r.run_id, r.agora)
        calendar_ops.executar_ops(
            reparo, calendar_id_metas=metas_id, modo_offline=r.modo_offline, registro=r.registro_proxies
        )
        com_erro = calendar_ops.aplicar_resultados(blocos, reparo, metas_id)
        doc_ops["ops"] += reparo["ops"]
    gpio.escrever_json(base.caminho_dados("cache", "ops-%s.json" % r.run_id), doc_ops)
    return doc_ops, com_erro


def _avisos_do_plano(
    avisos: list[str],
    decisoes: list[tuple[str, str]],
    decisao: Optional[tuple[str, str]],
    plano_novo: bool,
    metas: dict[str, dict[str, Any]],
    semana: str,
) -> None:
    """Decisões que não couberam na caixa viram aviso; no dia do plano novo, o resumo do mês abre a lista."""
    avisos.extend(
        copy.texto("email.decisao_pendente_aviso", meta=render.rotulo_meta(meta_id))
        for meta_id, _ in decisoes[1 if decisao else 0 :]
    )
    if not plano_novo:
        return
    com_decisao = {d[0] for d in decisoes}
    coberta = [
        render.rotulo_meta(m)
        for m in sorted(metas)
        if m not in com_decisao and metas[m].get("estado", "ativa") == "ativa"
    ]
    avisos.insert(
        0,
        copy.texto(
            "mensal.resumo",
            mes=balanco.mes_e_ano(clock.mes_da_semana(semana)),
            coberta=", ".join(coberta) or "nenhuma",
            outras=", ".join(render.rotulo_meta(d[0]) for d in decisoes) or "nenhuma",
        ),
    )


def _email_do_dia(
    r: _Rodada, registro: dict[str, Any], texto: str, *, primeiro_dia: bool, decisao: Optional[tuple[str, str]]
) -> tuple[str, dict[str, Any]]:
    """``(status para o registro, detalhe para a saída)``; uma vez por dia, falha do envio não derruba o diário. Sem
    Gmail, nenhum email: o dia fica no app."""
    if not conexoes.usa_email(r.contexto):
        return "nao_enviado", {}
    if email_ja_enviado(registro, r.dia):
        return "nao_enviado", {"status": "ja_enviado"}
    modelo = render.modelo_email(render.ler_dia(texto), primeiro_dia=primeiro_dia, decisao=decisao)
    assunto, corpo = render.email_texto(modelo)
    html = render.email_html(modelo)
    try:
        info = correio.enviar(
            r.contexto, assunto, corpo, html, run_id=r.run_id, modo_offline=r.modo_offline, registro=r.registro_proxies
        )
    except proxy.RateLimited:
        raise
    except GpErro as erro:
        telemetria.log("email das 7h falhou: %s" % execucao.classe_de(erro), nivel="erro")
        return "falhou", {"status": "falhou", "classe": execucao.classe_de(erro)}
    info["status"] = "enviado"
    return "enviado", info


def _contar_ops(doc_ops: dict[str, Any]) -> dict[str, int]:
    contagem = {"create": 0, "update": 0, "delete": 0, "erro": 0}
    for op in doc_ops["ops"]:
        contagem["erro" if op.get("status") != "ok" else op["op"]] += 1
    return contagem


def _linha_resumo(abertos: list[dict[str, Any]], janelas: list) -> str:
    n = len(abertos)
    if n == 0:
        return copy.texto("diario.resumo_sem_blocos") if not janelas else copy.texto("diario.resumo_sem_demanda")
    return copy.texto(
        "diario.resumo",
        n=n,
        s="" if n == 1 else "s",
        metas=", ".join(sorted({render.rotulo_meta(b["meta"]) for b in abertos})),
    )


somar_tokens = proxy.somar_tokens


def email_ja_enviado(registro: dict[str, Any], dia: date) -> bool:
    return any(
        g.get("modo") in (MODO, MODO_REENVIO) and str(g.get("data")) == dia.isoformat() and g.get("email") == "enviado"
        for g in registro.get("geracoes", {}).values()
    )


def reenviar_email(dados: Path, *, dia: date, modo_offline: bool, agora: datetime, run_id: str) -> dict[str, Any]:
    """Nova tentativa do email das 7h a partir de ``dias/<dia>.md`` (sem refazer o dia nem chamar o Calendar).

    Uma vez por dia: com o email do dia já enviado, não manda de novo. Erro do conector propaga
    (o job decide se tenta outra vez); sucesso fica em ``geracoes`` com modo ``diario-email``."""
    registro = reg.carregar(dados)
    if email_ja_enviado(registro, dia):
        return {"email": {"status": "ja_enviado"}}
    if not (dados / "dias" / ("%s.md" % dia.isoformat())).exists():
        raise GpErro(EXIT_ESTADO, "dias/%s.md não existe: o dia não foi gerado" % dia.isoformat())
    comeco = monotonic()
    assunto, corpo, html = montar_email(dados, dia)
    registro_proxies: list = []
    info = correio.enviar(
        _contexto(dados), assunto, corpo, html, run_id=run_id, modo_offline=modo_offline, registro=registro_proxies
    )
    registro = reg.carregar(dados)
    reg.registrar_geracao(
        registro,
        {
            "run_id": run_id,
            "modo": MODO_REENVIO,
            "data": dia.isoformat(),
            "ts": agora.isoformat(timespec="seconds"),
            "exit_code": 0,
            "duracao_s": round(monotonic() - comeco, 1),
            "tokens": somar_tokens(registro_proxies),
            "sessoes": [r["session_id"] for r in registro_proxies if r.get("session_id")],
            "email": "enviado",
        },
    )
    reg.salvar(registro, dados)
    return {"email": dict(info, status="enviado")}


def enviar_email_falha(dados: Path, classe: str, *, dia: date, modo_offline: bool, run_id: str) -> dict[str, Any]:
    """Email mínimo de falha: lê só ``email_proprio`` do contexto (sem validar o resto)."""
    bruto, _ = frontmatter.ler_arquivo(dados / schema.CAMINHOS["contexto"])
    assunto, texto, html = render.email_falha(dia, execucao.motivo(classe), execucao.acao(classe))
    return correio.enviar(
        {"email_proprio": bruto.get("email_proprio")}, assunto, texto, html, run_id=run_id, modo_offline=modo_offline
    )


def desinstalar(
    dados: Path, *, modo_offline: bool, confirmar: bool, agora: Optional[datetime] = None
) -> dict[str, Any]:
    agora = agora or clock.agora()
    contexto = _contexto(dados)
    tz = clock.fuso(contexto["timezone"])
    inicio, fim = agora.astimezone(tz) - timedelta(days=60), agora.astimezone(tz) + timedelta(days=120)
    eventos = calendar_ops.ler_eventos(
        contexto["calendar_id_metas"],
        inicio,
        fim,
        calendar_id_metas=contexto["calendar_id_metas"],
        modo_offline=modo_offline,
    )
    doc = calendar_ops.ops_desinstalar(
        eventos, contexto, run_id="desinstalar-" + agora.strftime("%Y%m%d-%H%M%S"), agora=agora
    )
    if confirmar:
        calendar_ops.executar_ops(doc, calendar_id_metas=contexto["calendar_id_metas"], modo_offline=modo_offline)
        gpio.escrever_json(base.caminho_dados("cache", "ops-%s.json" % doc["run_id"]), doc)
    return {
        "blocos": [op["task_id"] for op in doc["ops"]],
        "apagados": confirmar,
        "erros": [op["task_id"] for op in doc["ops"] if confirmar and op.get("status") != "ok"],
    }


def _parser() -> argparse.ArgumentParser:
    parser = cli.parser_base(
        "gera o dia: inferência, cache do Calendar, alocação, blocos no Metas, dias/<data>.md e email"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="dia a gerar (padrão: hoje)")
    parser.add_argument(
        "--sem-inferir", dest="sem_inferir", action="store_true", help="pula a inferência (usado pelo checkin)"
    )
    parser.add_argument("--email", action="store_true", help="manda o email das 7h (uma vez por dia)")
    parser.add_argument(
        "--email-falha", dest="email_falha", default=None, metavar="CLASSE", help="só manda o email mínimo de falha"
    )
    parser.add_argument(
        "--reenviar-email",
        dest="reenviar",
        action="store_true",
        help="nova tentativa do email do dia já gerado (uma vez por dia)",
    )
    parser.add_argument(
        "--prosa-viva",
        dest="prosa_viva",
        action="store_true",
        help="porquê por claude -p mesmo com --offline (golden run)",
    )
    parser.add_argument(
        "--email-texto",
        dest="email_texto",
        action="store_true",
        help="imprime o email do dia em texto (assunto e corpo) sem enviar",
    )
    parser.add_argument(
        "--email-html", dest="email_html", action="store_true", help="imprime o HTML do email do dia sem enviar"
    )
    parser.add_argument("--desinstalar", action="store_true", help="lista os blocos desta instalação no Metas")
    parser.add_argument("--confirmar", action="store_true", help="com --desinstalar: apaga de verdade")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    trava = None
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        agora = clock.agora()
        if args.email_texto or args.email_html:
            return _cli_mostrar_email(args, dados, agora)
        if args.email_falha:
            saida = enviar_email_falha(
                dados, args.email_falha, dia=args.data or agora.date(), modo_offline=args.offline, run_id=_run_id(agora)
            )
            texto = "email de falha: %s" % saida.get("id")
        else:
            trava = reg.lock(dados)
            saida, texto = _cli_sob_lock(args, dados, agora)
        if args.json:
            sys.stdout.write(json.dumps(saida, ensure_ascii=False, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(texto.rstrip("\n") + "\n")
        return EXIT_OK
    except GpErro as erro:
        if args.json:
            sys.stdout.write(json.dumps(execucao.erro_json(erro), ensure_ascii=False) + "\n")
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    finally:
        if trava is not None:
            trava.liberar()


def _cli_mostrar_email(args: argparse.Namespace, dados: Path, agora: datetime) -> int:
    assunto, corpo, html = montar_email(dados, args.data or agora.date())
    if args.json:
        sys.stdout.write(json.dumps({"subject": assunto, "body": corpo, "htmlBody": html}, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write((html if args.email_html else "Assunto: %s\n\n%s" % (assunto, corpo)).rstrip("\n") + "\n")
    return EXIT_OK


def _cli_sob_lock(args: argparse.Namespace, dados: Path, agora: datetime) -> tuple[dict[str, Any], str]:
    """Reenviar o email do dia, desinstalar os blocos ou gerar o dia; devolve ``(saída, texto)``."""
    if args.reenviar:
        saida = reenviar_email(
            dados, dia=args.data or agora.date(), modo_offline=args.offline, agora=agora, run_id=_run_id(agora)
        )
        return saida, "email do dia: %s" % saida["email"]["status"]
    if args.desinstalar:
        saida = desinstalar(dados, modo_offline=args.offline, confirmar=args.confirmar, agora=agora)
        acao = "apagados" if args.confirmar else "encontrados (use --confirmar para apagar)"
        return saida, copy.texto("diario.desinstalar", n=len(saida["blocos"]), acao=acao)
    saida = gerar(
        dados,
        dia=args.data or agora.date(),
        modo_offline=args.offline,
        sem_inferir=args.sem_inferir,
        agora=agora,
        enviar_email=args.email,
        prosa_viva=args.prosa_viva,
    )
    return saida, "%s: %s\n%s" % (saida["arquivo"], saida["resumo"], "\n".join("- " + a for a in saida["avisos"]))


if __name__ == "__main__":
    raise SystemExit(main())
