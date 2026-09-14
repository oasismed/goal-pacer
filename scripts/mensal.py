#!/usr/bin/env python3
"""mensal.py: evidências + balanço do mês + prosa → planos/AAAA-MM.md e semanas/*.md (T7, T10).

Em série, com o lock da pasta de dados::

    validar grafo -> perfil
    -> evidências (se ativas): parse_whatsapp -> sessão mensal-ler (só-leitura) -> sinais/<data>.md
       -> apaga cache/whatsapp-*.json e o prompt renderizado (critério 13)
    -> list_calendars -> list_events de hoje ao fim da última semana (compacto) -> cache/calendar-mensal-AAAA-MM.json
    -> balanco.calcular -> prosa: keep+diff (bloco vazio ou com <!-- prosa:atualizar --> é refeito;
       prosa viva só fora do --offline ou com --prosa-viva; viola o tom -> template)
    -> planos/AAAA-MM.md (hash_numeros) + espelhos semanas/AAAA-Www.md
    -> fontes/M<nn>.md com título/horizonte/prazo mudados viram estado pendente (aviso)
    -> registro.geracoes[run_id]

``--sem-evidencias`` pula a leitura das fontes (semanal e balanco.py --render
usam assim, com ``--manter-prosa``). Exit: 0 ok · 2 sem onboarding/meta ativa ·
3 inválido · 4 IO/lock · 5 timeout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parse_whatsapp
import validar
from goalpacer import (
    balanco,
    base,
    calendar_ops,
    cli,
    clock,
    conexoes,
    copy,
    execucao,
    frontmatter,
    ia,
    io as gpio,
    leitor,
    offline,
    perfil as prf,
    prompts,
    proxy,
    registro as reg,
    render,
    schema,
    telemetria,
    tom,
)
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro

TOOL_LIST_CALENDARS = "mcp__claude_ai_Google_Calendar__list_calendars"
MODO = "mensal"
MODELO_PROSA = "sonnet"
TETO_PROSA_META = 400
TETO_PROSA_RESUMO = 500
FIXTURE_LEITURA = "mensal_ler"
FIXTURE_PROSA = "prosa_plano.txt"


_contexto = frontmatter.ler_contexto


def _run_id(agora: datetime, modo: str = MODO) -> str:
    import os

    return os.environ.get(base.ENV_RUN_ID) or "%s-%s" % (modo, agora.strftime("%Y%m%d-%H%M%S"))


# --- evidências ---------------------------------------------------------------------


def _bloco_metas_leitura(metas: dict[str, dict[str, Any]], contexto: dict[str, Any], fontes: list[str]) -> str:
    linhas = []
    for meta_id in sorted(metas):
        meta = metas[meta_id]
        palavras = meta.get("palavras_chave") or []
        linha = "- %s · %s · palavras-chave: %s" % (meta_id, meta["titulo"], ", ".join(palavras) or "(nenhuma)")
        if "gmail" in fontes and palavras:
            linha += "\n  busca Gmail: %s" % leitor.query_gmail(
                palavras, contexto.get("email_proprio") or "", contexto.get("email_alias") or []
            )
        linhas.append(linha)
    return "\n".join(linhas)


def _bloco_whatsapp(wa: Optional[dict[str, Any]]) -> str:
    if not wa or not any(wa.get("trechos", {}).values()):
        return prompts.envelope("whatsapp", "(nenhum trecho)")
    partes = [
        "%s | %s | %s" % (meta_id, t["ts"], t["texto"])
        for meta_id, trechos in sorted(wa["trechos"].items())
        for t in trechos
    ]
    return prompts.envelope("whatsapp", "\n".join(partes))


def evidencias(
    dados: Path,
    contexto: dict[str, Any],
    metas: dict[str, dict[str, Any]],
    *,
    modo_offline: bool,
    agora: datetime,
    run_id: str,
    registro_proxies: list,
) -> dict[str, Any]:
    fontes = [f for f in schema.FONTES if f in set(contexto.get("fontes_ativas") or [])]
    ativas = {m: meta for m, meta in metas.items() if meta.get("estado", "ativa") == "ativa"}
    avisos: list[str] = []
    wa = parse_whatsapp.processar(dados, clock.mes_id(agora.date()), agora) if "whatsapp" in fontes else None
    if wa is not None and wa["status"] in AVISOS_WHATSAPP:
        avisos.append(copy.texto(AVISOS_WHATSAPP[wa["status"]]))
    mcp = leitor.fontes_mcp(fontes)
    dados_lidos: dict[str, Any] = {}
    if ativas and (mcp or (wa and any(wa["trechos"].values()))):
        dados_lidos = _ler_fontes(
            contexto,
            ativas,
            fontes,
            mcp,
            wa,
            modo_offline=modo_offline,
            agora=agora,
            run_id=run_id,
            registro_proxies=registro_proxies,
            avisos=avisos,
        )
    sinais, descartes = leitor.validar_resultado(
        dados_lidos, metas=ativas, fontes_ativas=fontes, agora=agora, whatsapp=wa
    )
    for d in descartes:
        telemetria.log("mensal-ler: " + d, nivel="aviso")
    texto = leitor.render_sinais(sinais, metas=ativas, fontes=fontes, agora=agora, run_id=run_id, whatsapp=wa)
    path = base.caminho_dados("sinais", agora.date().isoformat() + ".md")
    gpio.escrever_atomico(path, texto)
    _apagar_cache_do_whatsapp(dados)
    return {
        "arquivo": "sinais/%s" % path.name,
        "evidencias": sum(len(v) for v in sinais["evidencias"].values()),
        "descartadas": len(descartes),
        "avisos": avisos,
        "whatsapp": (wa or {}).get("status"),
    }


AVISOS_WHATSAPP = {
    "nao_reconhecido": "mensal.whatsapp_nao_reconhecido",
    "stale": "mensal.whatsapp_stale",
    "truncado": "mensal.whatsapp_truncado",
}


def _ler_fontes(
    contexto: dict[str, Any],
    ativas: dict[str, dict[str, Any]],
    fontes: list[str],
    mcp: list[str],
    wa: Optional[dict[str, Any]],
    *,
    modo_offline: bool,
    agora: datetime,
    run_id: str,
    registro_proxies: list,
    avisos: list[str],
) -> dict[str, Any]:
    """A sessão só-leitura (``mensal-ler``) com as fontes ativas e os trechos do WhatsApp envelopados; a auditoria
    das chamadas descarta tudo quando alguma tool saiu da lista. O prompt renderizado nunca fica no disco."""
    caminho_prompt = None
    try:
        texto_prompt = prompts.renderizar("mensal-ler", _variaveis_da_leitura(contexto, ativas, fontes, wa, agora))
        caminho_prompt = prompts.salvar(run_id, "mensal-ler", texto_prompt)
        chamadas: list = []
        dados_lidos: dict[str, Any] = {}
        if modo_offline:
            dados_lidos = offline.resposta(FIXTURE_LEITURA)
            chamadas = list(offline.resposta(FIXTURE_LEITURA + "_chamadas").get("chamadas") or [])
        elif mcp:
            dados_lidos = leitor.ler(
                texto_prompt, mcp, n_metas=len(ativas), registro=registro_proxies, chamadas=chamadas
            )
        if mcp and not _auditoria_ok(chamadas, mcp, ativas, contexto, run_id, avisos):
            return {}
        return dados_lidos
    except proxy.RateLimited:
        raise
    except GpErro as erro:
        avisos.append(copy.texto("mensal.leitura_sem_fontes", classe=type(erro).__name__))
        return {}
    finally:
        if caminho_prompt is not None and caminho_prompt.exists():
            caminho_prompt.unlink()


def _variaveis_da_leitura(
    contexto: dict[str, Any],
    ativas: dict[str, dict[str, Any]],
    fontes: list[str],
    wa: Optional[dict[str, Any]],
    agora: datetime,
) -> dict[str, Any]:
    return {
        "DATA": agora.date().isoformat(),
        "FONTES": ", ".join(fontes) or "(nenhuma)",
        "METAS": _bloco_metas_leitura(ativas, contexto, fontes),
        "WHATSAPP": _bloco_whatsapp(wa),
        "TETO_GMAIL": contexto.get("tetos_gmail_threads", 15),
        "TETO_GMAIL_INTEIRAS": contexto.get("tetos_gmail_threads_inteiras", 3),
        "TETO_NOTION": contexto.get("tetos_notion_paginas", 5),
        "TETO_DRIVE": contexto.get("tetos_drive_arquivos", 5),
        "TETO_DRIVE_CHARS": contexto.get("tetos_drive_caracteres", 4000),
    }


def _auditoria_ok(
    chamadas: list,
    mcp: list[str],
    ativas: dict[str, dict[str, Any]],
    contexto: dict[str, Any],
    run_id: str,
    avisos: list[str],
) -> bool:
    """Grava ``cache/auditoria-<run_id>.jsonl``; ``False`` quando alguma tool saiu da lista (a leitura é descartada).
    Fora dos tetos só avisa."""
    auditoria = leitor.auditar(chamadas, mcp, n_metas=len(ativas), contexto=contexto)
    gpio.escrever_atomico(
        base.caminho_dados("cache", "auditoria-%s.jsonl" % run_id),
        leitor.auditoria_jsonl(chamadas, auditoria, run_id=run_id),
        bak=False,
    )
    if auditoria["fora_da_lista"]:
        avisos.append(copy.texto("mensal.leitura_fora_da_lista", tools=", ".join(auditoria["fora_da_lista"])))
        return False
    if not auditoria["ok"]:
        avisos.append(copy.texto("mensal.leitura_fora_dos_tetos"))
    return True


def _apagar_cache_do_whatsapp(dados: Path) -> None:
    """Os trechos do export saem do cache logo depois da leitura (achado 3.3); o .bak também."""
    for cache_wa in (dados / "cache").glob("whatsapp-*.json") if (dados / "cache").is_dir() else []:
        cache_wa.unlink()
        bak = gpio.caminho_bak(cache_wa)
        if bak.exists():
            bak.unlink()


# --- prosa ------------------------------------------------------------------------------


def _numeros_para_prompt(res: dict[str, Any]) -> str:
    linhas = [
        "mês %s: oferta %s h, demanda das semanas abertas %s h, %s"
        % (
            res["mes"],
            balanco.horas(res["oferta_mes_h"]),
            balanco.horas(res["demanda_aberta_h"]),
            "apertado" if res["apertado"] else "folgado",
        )
    ]
    for meta_id, item in sorted(res["metas"].items()):
        linhas.append(
            "%s (%s): demanda do mês %s h, alocado %s h, cobertura %s, decisão %s, progresso %s, ritmo esperado %s, prazo %s%s"
            % (
                meta_id.lower(),
                item["titulo"],
                balanco.horas(item["demanda_mes_h"]),
                balanco.horas(item["alocado_mes_h"]),
                balanco.pct(item["cobertura_pct"]),
                item["decisao"] or item["estado"],
                balanco.pct(item["progresso_pct"]),
                balanco.pct(item["ritmo_esperado_pct"]),
                item["prazo"],
                ", adiar para %s" % item["adiar_para"] if item.get("adiar_para") else "",
            )
        )
    return "\n".join(linhas)


def prosa_viva(
    res: dict[str, Any],
    nomes: list[str],
    evidencias_lista: list[tuple[str, str, str, str]],
    *,
    run_id: str,
    modo_offline: bool,
    registro_proxies: list,
) -> dict[str, str]:
    sinais = "\n".join("%s %s %s: %s" % e for e in evidencias_lista) or "(nenhum sinal)"
    texto_prompt = prompts.renderizar(
        "plano",
        {
            "MES": balanco.mes_e_ano(res["mes"]),
            "NUMEROS": _numeros_para_prompt(res),
            "SINAIS": prompts.envelope("sinais", sinais),
            "BLOCOS": ", ".join(nomes),
        },
    )
    prompts.salvar(run_id, "plano", texto_prompt)
    if modo_offline and offline.texto(FIXTURE_PROSA):
        resposta = offline.texto(FIXTURE_PROSA)
    else:
        resposta = ia.prosa(texto_prompt, modelo=MODELO_PROSA, curta=False, registro=registro_proxies)
    return balanco.extrair_prosa(resposta)


def compor_prosa(
    res: dict[str, Any],
    existente: dict[str, str],
    *,
    regenerar: bool,
    viva: bool,
    evidencias_lista,
    run_id: str,
    modo_offline: bool,
    registro_proxies: list,
) -> tuple[dict[str, str], list[str]]:
    """Prosa de cada bloco: a guardada fica; a que precisa ser refeita vem do modelo, se passar no teto e no tom,
    senão do template. Limite de uso sobe; outro erro da prosa viva vira aviso e template."""
    template = balanco.prosa_template(res)
    final, refazer = _prosa_guardada(balanco.nomes_blocos_prosa(res), existente, regenerar=regenerar)
    gerado: dict[str, str] = {}
    avisos: list[str] = []
    if refazer and viva:
        try:
            gerado = prosa_viva(
                res,
                refazer,
                evidencias_lista,
                run_id=run_id,
                modo_offline=modo_offline,
                registro_proxies=registro_proxies,
            )
        except proxy.RateLimited:
            raise
        except GpErro as erro:
            avisos.append(copy.texto("mensal.prosa_template", classe=type(erro).__name__))
    for nome in refazer:
        final[nome] = _prosa_aceita(nome, gerado.get(nome), template[nome])
    return final, avisos


def _prosa_guardada(
    nomes: list[str], existente: dict[str, str], *, regenerar: bool
) -> tuple[dict[str, str], list[str]]:
    """``(prosa que fica, blocos a refazer)``: refaz o bloco vazio e, com ``regenerar``, o marcado para atualizar."""
    final: dict[str, str] = {}
    refazer = []
    for nome in nomes:
        atual = existente.get(nome)
        if balanco.precisa_regerar(atual) and (regenerar or not (atual or "").strip()):
            refazer.append(nome)
        else:
            final[nome] = atual or ""
    return final, refazer


def _prosa_aceita(nome: str, gerado: Optional[str], template: str) -> str:
    texto = tom.normalizar(" ".join((gerado or "").split()))
    teto = TETO_PROSA_RESUMO if nome == "resumo" else TETO_PROSA_META
    if texto and len(texto) <= teto and tom.ok(texto):
        return texto
    if texto:
        telemetria.log(
            "prosa %s trocada pelo template (%s)"
            % (nome, "tamanho" if len(texto) > teto else "tom: " + ", ".join(tom.violacoes(texto))),
            nivel="aviso",
        )
    return template


# --- fontes pendentes --------------------------------------------------------------------


def marcar_fontes_pendentes(dados: Path, metas: dict[str, dict[str, Any]]) -> list[str]:
    avisos = []
    for meta_id, meta in sorted(metas.items()):
        path = dados / "fontes" / ("%s.md" % meta_id)
        if not path.exists() or meta.get("estado", "ativa") != "ativa":
            continue
        try:
            bruto, corpo = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["fonte_pesquisa"])
        if erros:
            continue
        atual = schema.hash_meta_pesquisa(meta)
        if coagido.get("hash_meta") and coagido["hash_meta"] != atual and coagido.get("estado") != "pendente":
            coagido["estado"] = "pendente"
            frontmatter.escrever_arquivo(path, coagido, corpo)
        if coagido.get("estado") == "pendente":
            avisos.append(copy.texto("mensal.custo_pendente", meta=render.rotulo_meta(meta_id)))
    return avisos


# --- orquestração ------------------------------------------------------------------------


def gerar(
    dados: Path,
    *,
    mes: Optional[str] = None,
    modo_offline: bool,
    agora: Optional[datetime] = None,
    run_id: Optional[str] = None,
    com_evidencias: bool = True,
    regenerar_prosa: bool = True,
    prosa_viva_forcada: bool = False,
    modo: str = MODO,
) -> dict[str, Any]:
    agora = agora or clock.agora()
    run_id = run_id or _run_id(agora, modo)
    registro_proxies: list = []
    avisos: list[str] = []
    contexto = validar.contexto_valido(dados)
    tz = clock.fuso(contexto["timezone"])
    agora = agora.astimezone(tz)
    mes = mes or clock.mes_da_semana(clock.semana_iso(agora.date()))
    metas = prf._ler_metas(dados)
    perfil = prf.calcular(dados, agora)
    prf.gravar(dados, perfil)
    resumo_evidencias = None
    if com_evidencias:
        resumo_evidencias = evidencias(
            dados,
            contexto,
            metas,
            modo_offline=modo_offline,
            agora=agora,
            run_id=run_id,
            registro_proxies=registro_proxies,
        )
        avisos += resumo_evidencias["avisos"]
    eventos = _agenda_do_mes(
        dados, contexto, mes, agora, run_id=run_id, modo_offline=modo_offline, registro_proxies=registro_proxies
    )
    registro = reg.carregar(dados)
    res = balanco.calcular(
        mes=mes,
        contexto=contexto,
        metas=metas,
        registro=registro,
        perfil=perfil,
        blocos=prf.blocos_com_registro(dados, registro),
        eventos=eventos,
        agora=agora,
    )
    espelhos, avisos_prosa = _escrever_plano(
        dados,
        res,
        metas,
        agora,
        run_id=run_id,
        regenerar=regenerar_prosa,
        viva=(not modo_offline) or prosa_viva_forcada,
        modo_offline=modo_offline,
        registro_proxies=registro_proxies,
        whatsapp=(resumo_evidencias or {}).get("whatsapp"),
    )
    avisos += avisos_prosa
    avisos += marcar_fontes_pendentes(dados, metas)
    conexoes.registrar_uso(registro_proxies, agora, simulado=modo_offline)
    _registrar_geracao(dados, run_id, modo, agora, registro_proxies, metas)
    return _saida(res, run_id, espelhos, resumo_evidencias, avisos)


def _agenda_do_mes(
    dados: Path,
    contexto: dict[str, Any],
    mes: str,
    agora: datetime,
    *,
    run_id: str,
    modo_offline: bool,
    registro_proxies: list,
) -> list[dict[str, Any]]:
    """Eventos do mês dos calendários lidos (e do primário e do Metas), gravados no cache do mensal; sem Google
    Calendar, nenhum (o balanço conta só o horário útil)."""
    if not conexoes.usa_agenda(contexto):
        return []
    calendarios = calendar_ops.listar_calendarios(
        dados,
        modo_offline=modo_offline,
        agora=agora,
        calendar_id_metas=contexto["calendar_id_metas"],
        registro=registro_proxies,
    )
    if calendarios and contexto["calendar_id_metas"] not in {c["id"] for c in calendarios}:
        raise GpErro(EXIT_VALIDACAO, copy.texto("diario.metas_nao_encontrado"), classe="MetasNaoEncontrado")
    lidos = set(contexto.get("calendarios_lidos") or [c["id"] for c in calendarios])
    lidos |= {contexto["calendar_id_primario"], contexto["calendar_id_metas"]}
    inicio, fim = balanco.janela_leitura(mes, agora, agora.tzinfo)
    eventos: list[dict[str, Any]] = []
    for cal_id in sorted(lidos) if fim > inicio else []:
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
    gpio.escrever_json(base.caminho_dados("cache", "calendar-mensal-%s.json" % mes), cache)
    return eventos


def _escrever_plano(
    dados: Path,
    res: dict[str, Any],
    metas: dict[str, dict[str, Any]],
    agora: datetime,
    *,
    run_id: str,
    regenerar: bool,
    viva: bool,
    modo_offline: bool,
    registro_proxies: list,
    whatsapp: Optional[str],
) -> tuple[list[str], list[str]]:
    """``planos/AAAA-MM.md`` (prosa guardada ou refeita, tom conferido) e os espelhos ``semanas/``."""
    mes = res["mes"]
    caminho_plano = base.caminho_dados("planos", mes + ".md")
    existente = balanco.extrair_prosa(caminho_plano.read_text(encoding="utf-8")) if caminho_plano.exists() else {}
    evidencias_lista, fontes_sinais = leitor.ler_sinais(dados, agora)
    evidencias_lista = [e for e in evidencias_lista if e[2] in metas]
    prosa, avisos = compor_prosa(
        res,
        existente,
        regenerar=regenerar,
        viva=viva,
        evidencias_lista=evidencias_lista,
        run_id=run_id,
        modo_offline=modo_offline,
        registro_proxies=registro_proxies,
    )
    notas = []
    if whatsapp in ("ok", "stale", "truncado", "nao_reconhecido"):
        notas.append(copy.texto("mensal.whatsapp_lido", data=balanco.ddmm(agora.date()), status=whatsapp))
    texto = balanco.render_plano(
        res,
        prosa,
        evidencias_lista,
        hash_metas=schema.hash_metas(metas.values()),
        fontes=fontes_sinais,
        run_id=run_id,
        notas=notas,
    )
    violacoes = tom.violacoes(schema.RE_BLOCO_PROSA.sub("", texto))
    if violacoes:
        raise GpErro(EXIT_VALIDACAO, "plano gerado viola o tom (bug de template): %s" % ", ".join(violacoes))
    gpio.escrever_atomico(caminho_plano, texto)
    espelhos = []
    for semana in res["semanas"]:
        path = base.caminho_dados("semanas", semana["semana"] + ".md")
        gpio.escrever_atomico(path, balanco.render_semana(res, semana, run_id))
        espelhos.append("semanas/%s" % path.name)
    return espelhos, avisos


def _registrar_geracao(
    dados: Path, run_id: str, modo: str, agora: datetime, registro_proxies: list, metas: dict[str, dict[str, Any]]
) -> None:
    registro = reg.carregar(dados)
    reg.registrar_geracao(
        registro,
        {
            "run_id": run_id,
            "modo": modo,
            "data": agora.date().isoformat(),
            "ts": clock.agora().isoformat(timespec="seconds"),
            "exit_code": 0,
            "duracao_s": 0.0,
            "tokens": somar_tokens(registro_proxies),
            "sessoes": [r["session_id"] for r in registro_proxies if r.get("session_id")],
            "hash_metas": schema.hash_metas(metas.values()),
        },
    )
    reg.salvar(registro, dados)


def _saida(
    res: dict[str, Any],
    run_id: str,
    espelhos: list[str],
    resumo_evidencias: Optional[dict[str, Any]],
    avisos: list[str],
) -> dict[str, Any]:
    mes = res["mes"]
    decisoes = {m: i["decisao"] for m, i in res["metas"].items() if i["decisao"]}
    return {
        "mes": mes,
        "run_id": run_id,
        "arquivo": "planos/%s.md" % mes,
        "semanas": espelhos,
        "oferta_mes_h": res["oferta_mes_h"],
        "demanda_mes_h": res["demanda_mes_h"],
        "apertado": res["apertado"],
        "decisoes": decisoes,
        "evidencias": resumo_evidencias,
        "avisos": avisos,
        "resumo": copy.texto(
            "mensal.resumo",
            mes=balanco.mes_e_ano(mes),
            coberta=", ".join(render.rotulo_meta(m) for m, d in sorted(decisoes.items()) if d == "manter") or "nenhuma",
            outras=", ".join(
                "%s em %s" % (render.rotulo_meta(m), balanco.pct(res["metas"][m]["cobertura_pct"]))
                for m, d in sorted(decisoes.items())
                if d != "manter"
            )
            or "nenhuma",
        ),
    }


somar_tokens = proxy.somar_tokens


def _parser(descricao: str) -> argparse.ArgumentParser:
    parser = cli.parser_base(descricao)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mes", default=None, help="AAAA-MM (padrão: mês da semana de hoje)")
    parser.add_argument(
        "--sem-evidencias", dest="sem_evidencias", action="store_true", help="não lê Gmail/WhatsApp/Notion/Drive"
    )
    parser.add_argument(
        "--manter-prosa", dest="manter_prosa", action="store_true", help="só preenche blocos de prosa vazios"
    )
    parser.add_argument(
        "--prosa-viva",
        dest="prosa_viva",
        action="store_true",
        help="prosa por claude -p mesmo com --offline (golden run)",
    )
    return parser


def executar_cli(
    argv: Optional[list[str]], *, descricao: str, modo: str, com_evidencias_padrao: bool, manter_prosa_padrao: bool
) -> int:
    args = _parser(descricao).parse_args(argv)
    trava = None
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        trava = reg.lock(dados)
        saida = gerar(
            dados,
            mes=args.mes,
            modo_offline=args.offline,
            com_evidencias=com_evidencias_padrao and not args.sem_evidencias,
            regenerar_prosa=not (manter_prosa_padrao or args.manter_prosa),
            prosa_viva_forcada=args.prosa_viva,
            modo=modo,
        )
        if args.json:
            sys.stdout.write(json.dumps(saida, ensure_ascii=False, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(
                "%s: %s\n%s" % (saida["arquivo"], saida["resumo"], "".join("- %s\n" % a for a in saida["avisos"]))
            )
        return EXIT_OK
    except GpErro as erro:
        if args.json:
            sys.stdout.write(json.dumps(execucao.erro_json(erro), ensure_ascii=False) + "\n")
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    finally:
        if trava is not None:
            trava.liberar()


def main(argv: Optional[list[str]] = None) -> int:
    return executar_cli(
        argv,
        descricao="plano do mês: evidências, balanço de horas, prosa e espelhos semanais",
        modo=MODO,
        com_evidencias_padrao=True,
        manter_prosa_padrao=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
