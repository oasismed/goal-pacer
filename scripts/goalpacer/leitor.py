"""Sessão ``mensal-ler`` e ``sinais/`` (CEO 3.1, 7.1; D4.8; design "Protocolo: mensal-ler"; T10).

A única sessão agêntica do produto, e só-leitura::

    claude -p --output-format stream-json --verbose --max-turns N
      --tools ""                                   (nenhum built-in: sem Bash, Read, Write, WebFetch)
      --allowedTools <tools de leitura das fontes ativas>
      --disallowedTools <servidores não usados, Calendar inteiro, tools de escrita das fontes ativas>
      --setting-sources "" --permission-prompts none --model sonnet "<prompt>" < /dev/null

Ela não escreve arquivo nenhum: devolve um JSON no ``result`` e este módulo
valida a forma (metas conhecidas, fonte ativa, data nos últimos 30 dias,
resumo de uma linha com até 160 caracteres, no máximo 5 por meta) antes de
``mensal.py`` gravar ``sinais/AAAA-MM-DD.md``. O que não passa é descartado
com aviso; nada de terceiros vira instrução (o prompt envelopa os trechos).

Auditoria: o orquestrador guarda de cada ``tool_use`` do stream só o nome e os
argumentos (nunca a resposta) em ``cache/auditoria-<run_id>.jsonl`` e confere,
independente do relato do modelo::

    ferramenta fora da lista liberada           -> a leitura inteira é descartada (não se confia no resultado)
    mais aberturas que os tetos x metas          -> evidências ficam, com aviso no plano
    busca no Gmail sem -subject:"[goal-pacer]"   -> aviso (risco de ler o próprio email das 7h)
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

from goalpacer import base, clock, frontmatter, provedor, proxy, schema, telemetria
from goalpacer.base import EXIT_VALIDACAO, GpErro

TOOLS_LEITURA = {
    "gmail": (
        "mcp__claude_ai_Gmail__search_threads",
        "mcp__claude_ai_Gmail__get_thread",
        "mcp__claude_ai_Gmail__get_message",
    ),
    "notion": ("mcp__claude_ai_Notion__notion-search", "mcp__claude_ai_Notion__notion-fetch"),
    "drive": ("mcp__claude_ai_Google_Drive__search_files", "mcp__claude_ai_Google_Drive__read_file_content"),
}
SERVIDOR_DA_FONTE = {"gmail": "Gmail", "notion": "Notion", "drive": "Google_Drive"}
TIMEOUT_S = 15 * 60
MODELO = "sonnet"
TETO_TURNOS = 60
TURNOS_POR_META = {"gmail": 5, "notion": 6, "drive": 6}
TETO_EVIDENCIAS_META = 5
TETO_RESUMO = 160
TETO_QUERY = 300
JANELA_DIAS = 30
RE_JSON = re.compile(r"\{.*\}", re.DOTALL)
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
# ferramenta que abre conteúdo -> chave do teto por meta em contexto.md
ABERTURAS = {
    "mcp__claude_ai_Gmail__get_thread": "tetos_gmail_threads_inteiras",
    "mcp__claude_ai_Notion__notion-fetch": "tetos_notion_paginas",
    "mcp__claude_ai_Google_Drive__read_file_content": "tetos_drive_arquivos",
}
TOOL_BUSCA_GMAIL = "mcp__claude_ai_Gmail__search_threads"


def fontes_mcp(fontes_ativas: Iterable[str]) -> list[str]:
    return [f for f in ("gmail", "notion", "drive") if f in set(fontes_ativas)]


def max_turnos(fontes: list[str], n_metas: int) -> int:
    return min(TETO_TURNOS, 4 + max(1, n_metas) * sum(TURNOS_POR_META[f] for f in fontes))


def query_gmail(palavras: list[str], email_proprio: str, aliases: Iterable[str]) -> str:
    """``(a OR "b c") newer_than:30d -from:<próprio> -from:<alias> -subject:"[goal-pacer]"`` (D4.8)."""
    termos = ['"%s"' % p.replace('"', "") if " " in p else p.replace('"', "") for p in palavras if p.strip()]
    partes = ["(%s)" % " OR ".join(termos) if termos else ""]
    partes.append("newer_than:%dd" % JANELA_DIAS)
    partes.extend("-from:%s" % email for email in [email_proprio, *aliases] if email)
    partes.append('-subject:"[goal-pacer]"')
    return " ".join(p for p in partes if p)


def argv_leitura(
    prompt: str,
    fontes: list[str],
    *,
    servidores: Optional[Iterable[str]] = None,
    max_turns: int = 20,
    modelo: str = MODELO,
) -> list[str]:
    if not fontes:
        raise GpErro(EXIT_VALIDACAO, "mensal-ler sem fonte MCP ativa")
    permitidas = [t for f in fontes for t in TOOLS_LEITURA[f]]
    ativos = {SERVIDOR_DA_FONTE[f] for f in fontes}
    negadas: list[str] = []
    for servidor in proxy.SERVIDORES if servidores is None else list(servidores):
        if servidor in ativos:
            negadas.extend(
                "%s%s%s%s" % (proxy.PREFIXO_TOOL, servidor, proxy.SEPARADOR_TOOL, t)
                for t in proxy.TOOLS_ESCRITA.get(servidor, ())
            )
        else:
            negadas.append(proxy.PREFIXO_TOOL + servidor)
    return [
        proxy.claude_bin(),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--tools",
        "",
        "--allowedTools",
        *permitidas,
        "--disallowedTools",
        *negadas,
        "--setting-sources",
        "",
        "--permission-prompts",
        "none",
        "--model",
        modelo,
        prompt,
    ]


def extrair_json(texto: Any) -> dict[str, Any]:
    if not isinstance(texto, str):
        raise proxy.RespostaInvalida("mensal-ler: result não é texto")
    m = RE_JSON.search(texto)
    if not m:
        raise proxy.RespostaInvalida("mensal-ler: result sem JSON")
    try:
        dados = json.loads(m.group(0))
    except ValueError as erro:
        raise proxy.RespostaInvalida("mensal-ler: JSON inválido (%s)" % erro) from erro
    if not isinstance(dados, dict):
        raise proxy.RespostaInvalida("mensal-ler: JSON não é objeto")
    return dados


def ler(
    prompt: str,
    fontes: list[str],
    *,
    n_metas: int,
    executar: Optional[proxy.Executar] = None,
    registro: proxy.Registro = None,
    servidores: Optional[Iterable[str]] = None,
    timeout_s: float = TIMEOUT_S,
    chamadas: Optional[list] = None,
) -> dict[str, Any]:
    """Roda a sessão e devolve o JSON do ``result`` (sem validar a forma); ``chamadas`` recebe ``{tool, input}`` de cada tool_use."""
    provedor.exigir_conectores("mensal-ler")
    argv = argv_leitura(prompt, fontes, servidores=servidores, max_turns=max_turnos(fontes, n_metas))
    rodar = executar if executar is not None else proxy.executar_padrao
    cwd = base.jobs_dir()
    for tentativa in (1, 2):
        with proxy._SERIE:
            resultado = rodar(argv, timeout_s=timeout_s, cwd=cwd, env=None)
        stream = proxy.parse_stream(resultado.stdout.split("\n"))
        envelope = stream.get("result") or {}
        proxy._registrar(
            registro, proxy._entrada_registro("mensal-ler", envelope, stream.get("init"), resultado, tentativa, cwd)
        )
        if envelope.get("subtype") == proxy.SUBTYPE_MAX_TURNS:
            raise proxy.TurnosEsgotados("mensal-ler: turnos esgotados")
        proxy._checar_rate_limit(stream, envelope)
        if not _algum_conectado(stream.get("init") or {}, fontes):
            if tentativa == 1:
                telemetria.log("mensal-ler: catálogo MCP não carregou; nova tentativa", nivel="aviso")
            continue  # na segunda, sai do laço: conector que não carregou não vira "nenhum sinal"
        _conferir_envelope(envelope, resultado.codigo)
        if chamadas is not None:
            chamadas.extend(_chamadas_do_stream(stream))
        return extrair_json(envelope.get("result"))
    raise proxy.McpNaoCarregado("mensal-ler: conectores não carregaram em duas tentativas")


def _chamadas_do_stream(stream: dict[str, Any]) -> list[dict[str, Any]]:
    """``{tool, input}`` de cada tool_use, para a auditoria (só nome e argumentos, nunca a resposta)."""
    return [
        {"tool": str(uso.get("name")), "input": uso.get("input") if isinstance(uso.get("input"), dict) else {}}
        for uso in stream["tool_uses"]
    ]


def _algum_conectado(init: dict[str, Any], fontes: list[str]) -> bool:
    """Sem evento init não há o que conferir (vale como carregado); com init, alguma fonte precisa estar conectada."""
    if not init:
        return True
    status = {
        proxy._nome_servidor_init(s.get("name")): s.get("status")
        for s in init.get("mcp_servers") or []
        if isinstance(s, dict)
    }
    return any(status.get(SERVIDOR_DA_FONTE[f].lower()) == proxy.STATUS_MCP_CONECTADO for f in fontes)


def _conferir_envelope(envelope: dict[str, Any], codigo: int) -> None:
    if not envelope:
        raise proxy.RespostaInvalida("mensal-ler: stream sem evento result (código %d)" % codigo)
    if envelope.get("is_error"):
        raise proxy.ProxyErro("mensal-ler com is_error: " + proxy._texto_erro_envelope(envelope))
    if envelope.get("permission_denials"):
        telemetria.log(
            "mensal-ler: %d chamadas negadas (fora das tools liberadas)" % len(envelope["permission_denials"]),
            nivel="aviso",
        )


def auditar(
    chamadas: list[dict[str, Any]], fontes: list[str], *, n_metas: int, contexto: dict[str, Any]
) -> dict[str, Any]:
    """Confere as chamadas da sessão contra a lista liberada, os tetos por meta e a exclusão do próprio email."""
    permitidas = {t for f in fontes for t in TOOLS_LEITURA[f]}
    fora = sorted({c["tool"] for c in chamadas if c["tool"] not in permitidas})
    acima = {}
    for tool, chave in ABERTURAS.items():
        n = sum(1 for c in chamadas if c["tool"] == tool)
        teto = int(contexto.get(chave) or schema.defaults("contexto").get(chave) or 0) * max(1, n_metas)
        if n > teto:
            acima[tool] = {"chamadas": n, "teto": teto}
    sem_exclusao = sum(
        1
        for c in chamadas
        if c["tool"] == TOOL_BUSCA_GMAIL and '-subject:"[goal-pacer]"' not in str(c["input"].get("query", ""))
    )
    return {
        "chamadas": len(chamadas),
        "fora_da_lista": fora,
        "acima_do_teto": acima,
        "busca_sem_exclusao": sem_exclusao,
        "ok": not fora and not acima and not sem_exclusao,
    }


def auditoria_jsonl(chamadas: list[dict[str, Any]], resumo: dict[str, Any], *, run_id: str) -> str:
    linhas = [
        json.dumps(
            {"run_id": run_id, "n": i + 1, "tool": c["tool"], "input": c["input"]}, ensure_ascii=False, sort_keys=True
        )
        for i, c in enumerate(chamadas)
    ]
    linhas.append(json.dumps(dict(resumo, run_id=run_id, resumo=True), ensure_ascii=False, sort_keys=True))
    return "\n".join(linhas) + "\n"


def _texto_limpo(valor: Any, teto: int) -> str:
    texto = " ".join(RE_CONTROLE.sub(" ", str(valor or "")).split())
    return texto if len(texto) <= teto else texto[: teto - 1].rstrip() + "…"


def validar_resultado(
    dados: dict[str, Any],
    *,
    metas: dict[str, dict[str, Any]],
    fontes_ativas: list[str],
    agora: datetime,
    whatsapp: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], list[str]]:
    """``(sinais, avisos)``; ``sinais`` = ``{"evidencias": {meta: [(data, fonte, resumo)]}, "contadores": {...}, "queries": {...}}``."""
    avisos: list[str] = []
    hoje = agora.date()
    evidencias: dict[str, list[tuple[str, str, str]]] = {m: [] for m in metas}
    for item in dados.get("evidencias") or []:
        evidencia, aviso = _evidencia(item, metas, fontes_ativas, hoje)
        if aviso is not None:
            avisos.append(aviso)
        elif evidencia is not None and len(evidencias[evidencia[0]]) < TETO_EVIDENCIAS_META:
            evidencias[evidencia[0]].append(evidencia[1:])
    contadores, queries = _contadores_e_queries(dados.get("fontes"), fontes_ativas)
    if whatsapp is not None:
        contadores["whatsapp_vistos"] = int(whatsapp.get("vistos", 0))
        contadores["whatsapp_abertos"] = sum(len(t) for t in whatsapp.get("trechos", {}).values())
    return {"evidencias": evidencias, "contadores": contadores, "queries": queries}, avisos


def _evidencia(
    item: Any, metas: dict[str, dict[str, Any]], fontes_ativas: list[str], hoje: date
) -> tuple[Optional[tuple[str, str, str, str]], Optional[str]]:
    """``((meta, data, fonte, resumo), None)`` para evidência que passa; ``(None, aviso)`` com o motivo do descarte.
    Os valores recusados entram no aviso cortados em 12 caracteres (conteúdo não confiável)."""
    if not isinstance(item, dict):
        return None, "evidência descartada: não é objeto"
    meta_id, fonte = item.get("meta"), item.get("fonte")
    if meta_id not in metas:
        return None, "evidência descartada: meta %r desconhecida" % (str(meta_id)[:12],)
    if fonte not in fontes_ativas:
        return None, "evidência descartada: fonte %r não está ativa" % (str(fonte)[:12],)
    try:
        data = date.fromisoformat(str(item.get("data")))
    except ValueError:
        return None, "evidência descartada: data %r inválida" % (str(item.get("data"))[:12],)
    if not hoje - timedelta(days=JANELA_DIAS) <= data <= hoje:
        return None, "evidência descartada: data %s fora dos últimos %d dias" % (data.isoformat(), JANELA_DIAS)
    resumo = _texto_limpo(item.get("resumo"), TETO_RESUMO)
    if not resumo:
        return None, "evidência descartada: resumo vazio"
    return (str(meta_id), data.isoformat(), str(fonte), resumo), None


def _contadores_e_queries(fontes_lidas: Any, fontes_ativas: list[str]) -> tuple[dict[str, int], dict[str, str]]:
    """Quantos itens cada fonte viu e abriu (inteiros entre 0 e 10 000) e a query de cada fonte ativa."""
    brutas: dict[str, Any] = fontes_lidas if isinstance(fontes_lidas, dict) else {}
    contadores: dict[str, int] = {}
    queries: dict[str, str] = {}
    for fonte in ("gmail", "notion", "drive"):
        info_lida = brutas.get(fonte)
        info: dict[str, Any] = info_lida if isinstance(info_lida, dict) else {}
        for chave in ("vistos", "abertos"):
            valor = info.get(chave, 0)
            inteiro = isinstance(valor, int) and not isinstance(valor, bool)
            contadores["%s_%s" % (fonte, chave)] = max(0, min(10000, int(valor))) if inteiro else 0
        if fonte in fontes_ativas and info.get("query"):
            queries[fonte] = _texto_limpo(info.get("query"), TETO_QUERY)
    return contadores, queries


def render_sinais(
    sinais: dict[str, Any],
    *,
    metas: dict[str, dict[str, Any]],
    fontes: list[str],
    agora: datetime,
    run_id: str,
    whatsapp: Optional[dict[str, Any]] = None,
) -> str:
    coagido = _frontmatter_dos_sinais(sinais, fontes, agora, run_id, whatsapp)
    linhas = ["# Sinais de %s" % agora.date().strftime("%d/%m/%Y"), "", "Resumos das fontes; nunca conteúdo bruto.", ""]
    linhas += [_linha_da_fonte(fonte, coagido, sinais["queries"], whatsapp) for fonte in coagido["fontes"]] + [""]
    for meta_id in sorted(metas):
        itens = sinais["evidencias"].get(meta_id) or []
        linhas += ["## %s %s" % (meta_id, metas[meta_id]["titulo"]), ""]
        linhas += ["- evidencia: %s %s: %s" % item for item in sorted(itens)] or ["- (nenhum sinal)"]
        linhas.append("")
    return "---\n" + frontmatter.dump(coagido) + "---\n\n" + "\n".join(linhas).rstrip("\n") + "\n"


def _frontmatter_dos_sinais(
    sinais: dict[str, Any], fontes: list[str], agora: datetime, run_id: str, whatsapp: Optional[dict[str, Any]]
) -> dict[str, Any]:
    fm: dict[str, Any] = {
        "data": agora.date(),
        "run_id": run_id,
        "fontes": [f for f in schema.FONTES if f in set(fontes)],
    }
    fm.update(sinais["contadores"])
    if whatsapp is not None:
        fm["whatsapp_status"] = whatsapp.get("status", "sem_export")
        if whatsapp.get("ultima_mensagem"):
            fm["whatsapp_ultima_mensagem"] = clock.parse_iso(whatsapp["ultima_mensagem"], tz_padrao=agora.tzinfo)
    coagido, erros = frontmatter.coagir(fm, schema.ESQUEMAS["sinais"])
    erros = erros or schema.validar_registro("sinais", coagido)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "sinais inválidos: " + "; ".join(erros))
    return coagido


def _linha_da_fonte(
    fonte: str, coagido: dict[str, Any], queries: dict[str, str], whatsapp: Optional[dict[str, Any]]
) -> str:
    """``- gmail: viu 12 / abriu 3 · busca: ...`` (o export do WhatsApp mostra o estado no lugar da busca)."""
    extra = " · busca: `%s`" % queries[fonte].replace("`", "'") if fonte in queries else ""
    if fonte == "whatsapp" and whatsapp is not None:
        extra = " · export: %s" % whatsapp.get("status", "sem_export")
    return "- %s: viu %d / abriu %d%s" % (
        fonte,
        coagido.get("%s_vistos" % fonte, 0),
        coagido.get("%s_abertos" % fonte, 0),
        extra,
    )


def ler_sinais(
    dados: Path, agora: datetime, dias: int = JANELA_DIAS
) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """Evidências ``(data, fonte, meta, resumo)`` dos ``sinais/*.md`` dos últimos ``dias`` e as fontes que entraram."""
    pasta = dados / "sinais"
    if not pasta.is_dir():
        return [], []
    limite = agora.date() - timedelta(days=dias)
    evidencias: set[tuple[str, str, str, str]] = set()
    fontes: set[str] = set()
    recentes = [
        p
        for p in sorted(pasta.glob("*.md"))
        if schema.validar_id("dia", p.stem) and date.fromisoformat(p.stem) >= limite
    ]
    for path in recentes:
        try:
            fm, corpo = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        fontes.update(f for f in (fm.get("fontes") or []) if f in schema.FONTES)
        evidencias.update(_evidencias_do_corpo(corpo, limite))
    return sorted(evidencias), sorted(fontes, key=schema.FONTES.index)


def _evidencias_do_corpo(corpo: str, limite: date) -> Iterator[tuple[str, str, str, str]]:
    """``- evidencia:`` de cada ``## M<nn> <título>``, a partir de ``limite``."""
    meta_atual = None
    for linha_bruta in corpo.split("\n"):
        linha = linha_bruta.rstrip("\r")
        cabecalho = schema.RE_SUBSECAO_META.match(linha.replace("## ", "### ", 1)) if linha.startswith("## M") else None
        if cabecalho:
            meta_atual = cabecalho.group(1)
            continue
        m = schema.RE_EVIDENCIA_SINAL.match(linha)
        if m and meta_atual and date.fromisoformat(m.group(1)) >= limite:
            yield m.group(1), m.group(2), meta_atual, m.group(3)
