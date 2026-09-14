#!/usr/bin/env python3
"""onboarding.py detectar | rascunho ver|salvar|descartar | gravar: a parte do
onboarding que grava (T4/T25; achado 4.1; eng 3.4).

A coleta das até 8 respostas é da skill (SKILL.md, AskUserQuestion); este
script nunca pergunta nada. Fluxo::

    detectar  --> JSON com o que dá para pré-preencher (fuso do sistema,
                  e-mail próprio, calendários, "Metas" existe?, fontes
                  conectadas), via proxies; --offline lê fixtures
    rascunho  --> cache/onboarding-rascunho.json (atômico), uma chamada por
                  resposta; ver | salvar --respostas | descartar
    gravar    --> valida as respostas contra schema.py, monta metas/M<nn>.md,
                  fontes/M<nn>.md e contexto.md em memória, valida cada um,
                  e só então grava tudo (atômico, um arquivo por vez);
                  depois roda validar_grafo e apaga o rascunho

Resposta inválida (custo não numérico, timezone fora da lista IANA, horário
útil malformado, ...) = exit 3 listando ``campo: valor recusado (motivo)``,
sem gravar nada. Pasta de dados em Desktop/Downloads/Documents é recusada
por ``cli.aplicar_args_base`` (exit 3).

Rerodar ``gravar`` numa pasta já configurada: ``contexto.md`` é
reescrito (mantendo ``instalacao_id`` e ``schema_version``); metas com o
mesmo título de uma existente são ignoradas com aviso; metas novas ganham
os próximos ids. Nunca apaga meta (remoção é ``estado: arquivada``).

Formato das respostas (``--respostas`` ou o rascunho)::

    {"objetivos": [{"titulo", "porque", "como_vou_saber"}],           (opcional, até 3)
     "metas": [{"titulo", "horizonte", "prazo", "prazo_externo", "custo_h_semana_escolhido",
                "semanas_pesquisa", "confianca", "custo_h_semana_min", "custo_h_semana_max",
                "palavras_chave", "porque", "marcos", "pesquisa": {"busca", "urls", "trecho"},
                "objetivo": <título de um objetivo desta resposta ou de um já cadastrado>,
                "impacto": "essencial|importante|apoio"}],
     "horario_util": {"seg_sex", "sab", "dom"}, "calendar_id_metas", "calendar_id_primario",
     "calendarios_lidos", "lembretes", "fontes_ativas", "email_proprio", "email_alias",
     "timezone", "idioma", "pessoas"}
"""

from __future__ import annotations

import argparse
import json
import math
import re
import secrets
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validar
from goalpacer import base, cli, clock, copy, frontmatter, io as gpio, offline, proxy, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro

VERSAO_RASCUNHO = 1
NOME_RASCUNHO = "onboarding-rascunho.json"
NOMES_CALENDARIO_METAS = ("metas", "goals")  # o nome sugerido no copy de cada idioma
TETO_METAS = 5
TOOL_LIST_CALENDARS = "mcp__claude_ai_Google_Calendar__list_calendars"
TOOL_SEARCH_THREADS = "mcp__claude_ai_Gmail__search_threads"
SERVIDOR_PARA_FONTE = {"Gmail": "gmail", "Notion": "notion", "Google_Drive": "drive"}
RE_ANGULO = re.compile(r"<([^<>\s]+@[^<>\s]+)>")
RE_EMAIL = schema.RE_EMAIL

# Respostas → chaves planas de contexto.md.
CHAVES_HORARIO = {"seg_sex": "horario_util_seg_sex", "sab": "horario_util_sab", "dom": "horario_util_dom"}
CHAVES_CONTEXTO_DIRETAS = (
    "timezone",
    "idioma",
    "calendar_id_metas",
    "calendar_id_primario",
    "calendarios_lidos",
    "email_proprio",
    "email_alias",
    "fontes_ativas",
    "lembretes",
    "pessoas",
)
TETO_OBJETIVOS = 3
CHAVES_META = (
    "titulo",
    "horizonte",
    "prazo",
    "prazo_externo",
    "estado",
    "custo_h_semana_min",
    "custo_h_semana_max",
    "custo_h_semana_escolhido",
    "semanas_pesquisa",
    "confianca",
    "palavras_chave",
)
CHAVES_META_EXTRAS = ("porque", "marcos", "pesquisa", "objetivo")


class RespostaInvalida(GpErro):
    """Uma ou mais respostas recusadas; ``.erros`` lista ``campo: valor (motivo)``."""

    def __init__(self, erros: list[str]) -> None:
        super().__init__(EXIT_VALIDACAO, "\n".join(erros))
        self.erros = erros


# --- detectar --------------------------------------------------------------


def _email_de(valor: Any) -> Optional[str]:
    if not isinstance(valor, str):
        return None
    m = RE_ANGULO.search(valor)
    candidato = m.group(1) if m else valor.strip()
    return candidato.lower() if RE_EMAIL.fullmatch(candidato) else None


def _email_da_resposta(resposta: dict[str, Any]) -> Optional[str]:
    """Remetente da primeira mensagem enviada (``in:sent``), sem ler conteúdo:
    procura ``sender``/``from`` nas mensagens das threads."""
    candidatos = (_email_de(m.get(chave)) for m in _mensagens(resposta) for chave in CHAVES_REMETENTE)
    return next((email for email in candidatos if email), None)


CHAVES_REMETENTE = ("sender", "from", "from_", "remetente")


def _mensagens(resposta: dict[str, Any]) -> Iterator[dict[str, Any]]:
    threads = resposta.get("threads")
    for thread in threads if isinstance(threads, list) else []:
        if isinstance(thread, dict):
            yield from (m for m in thread.get("messages") or [] if isinstance(m, dict))


def _parece_email_pessoal(calendar_id: str) -> bool:
    return "@" in calendar_id and "group.calendar.google.com" not in calendar_id and "#" not in calendar_id


def detectar(*, modo_offline: bool, servidores: Optional[list[str]] = None) -> dict[str, Any]:
    """Pré-preenchimento das perguntas; nunca falha por causa de um conector
    (o problema vira ``avisos[]`` e a skill pergunta ao usuário)."""
    chamar = offline.chamar if modo_offline else proxy.chamar
    saida: dict[str, Any] = {
        "timezone": getattr(clock.fuso(), "key", "") or "",
        "idiomas": list(copy.disponiveis()),
        "email_proprio": None,
        "calendarios": [],
        "calendar_id_primario": None,
        "calendar_id_metas": None,
        "fontes_disponiveis": ["whatsapp"],
        "avisos": [],
    }
    for rotulo, passo in (
        ("email_proprio", lambda: _detectar_email(chamar, saida)),
        ("calendarios", lambda: _detectar_calendarios(chamar, saida)),
        ("fontes", lambda: _detectar_fontes(modo_offline, servidores, saida)),
    ):
        try:
            passo()
        except GpErro as erro:
            saida["avisos"].append("%s: %s" % (rotulo, erro.mensagem))
    return saida


def _detectar_email(chamar: Callable[..., dict[str, Any]], saida: dict[str, Any]) -> None:
    resposta = chamar(TOOL_SEARCH_THREADS, {"query": "in:sent", "pageSize": 1, "view": "THREAD_VIEW_METADATA_ONLY"})
    saida["email_proprio"] = _email_da_resposta(resposta)
    if saida["email_proprio"] is None:
        saida["avisos"].append("email_proprio: não encontrei mensagem enviada; pergunte ao usuário")


def _detectar_calendarios(chamar: Callable[..., dict[str, Any]], saida: dict[str, Any]) -> None:
    resposta = chamar(TOOL_LIST_CALENDARS, {})
    calendarios = [c for c in resposta.get("calendars") or [] if isinstance(c, dict) and c.get("id")]
    saida["calendarios"] = [{"id": str(c["id"]), "summary": str(c.get("summary") or "")} for c in calendarios]
    saida["calendar_id_primario"] = _calendario_primario(saida["calendarios"], saida["email_proprio"], saida["avisos"])
    saida["calendar_id_metas"] = _calendario_metas(saida["calendarios"], saida["avisos"])


def _calendario_primario(calendarios: list[dict[str, str]], email: Optional[str], avisos: list[str]) -> Optional[str]:
    """O calendário cujo id é o e-mail próprio; sem ele, o único com cara de e-mail pessoal."""
    primarios = [c["id"] for c in calendarios if email and c["id"].lower() == email]
    primarios = primarios or [c["id"] for c in calendarios if _parece_email_pessoal(c["id"])]
    if len(primarios) == 1:
        return primarios[0]
    avisos.append("calendar_id_primario: %d candidatos; pergunte ao usuário" % len(primarios))
    return None


def _calendario_metas(calendarios: list[dict[str, str]], avisos: list[str]) -> Optional[str]:
    metas = [c["id"] for c in calendarios if c["summary"].strip().lower() in NOMES_CALENDARIO_METAS]
    if len(metas) == 1:
        return metas[0]
    if not metas:
        avisos.append("calendar_id_metas: " + copy.texto("onboarding.p5_calendario_nao_encontrado"))
    else:
        avisos.append("calendar_id_metas: mais de um calendário chamado Metas; pergunte ao usuário")
    return None


def _detectar_fontes(modo_offline: bool, servidores: Optional[list[str]], saida: dict[str, Any]) -> None:
    if servidores is None:
        servidores = (
            proxy.servidores_de_mcp_list(offline.texto("mcp_list.txt")) if modo_offline else proxy.servidores_mcp_list()
        )
    for servidor in servidores:
        fonte = SERVIDOR_PARA_FONTE.get(servidor)
        if fonte and fonte not in saida["fontes_disponiveis"]:
            saida["fontes_disponiveis"].append(fonte)
    saida["calendar_conectado"] = "Google_Calendar" in servidores


# --- rascunho --------------------------------------------------------------


def caminho_rascunho() -> Path:
    return base.caminho_dados("cache", NOME_RASCUNHO)


def ler_rascunho() -> Optional[dict[str, Any]]:
    path = caminho_rascunho()
    if not path.exists():
        return None
    dados = gpio.ler_json(path)
    erros = schema.validar_registro("rascunho_onboarding", dados) if isinstance(dados, dict) else ["esperado objeto"]
    if erros:
        raise GpErro(
            EXIT_VALIDACAO, "rascunho inválido (%s); descarte com: onboarding.py rascunho descartar" % "; ".join(erros)
        )
    return dados


def salvar_rascunho(novas: dict[str, Any]) -> dict[str, Any]:
    """Funde ``novas`` (chaves de topo sobrescrevem) no rascunho e grava atômico."""
    atual = ler_rascunho() or {"versao": VERSAO_RASCUNHO, "respostas": {}}
    respostas = dict(atual.get("respostas") or {})
    respostas.update(novas)
    rascunho = {
        "versao": VERSAO_RASCUNHO,
        "atualizado_em": clock.agora().isoformat(timespec="seconds"),
        "respostas": respostas,
    }
    gpio.escrever_json(caminho_rascunho(), rascunho)
    return rascunho


def descartar_rascunho() -> bool:
    path = caminho_rascunho()
    existia = path.exists()
    for arquivo in (path, gpio.caminho_bak(path)):
        if arquivo.exists():
            arquivo.unlink()
    return existia


def resumo_rascunho(rascunho: Optional[dict[str, Any]]) -> dict[str, Any]:
    if rascunho is None:
        return {"existe": False, "atualizado_em": None, "respondidas": [], "respostas": {}}
    respostas = rascunho.get("respostas") or {}
    return {
        "existe": True,
        "atualizado_em": rascunho.get("atualizado_em"),
        "respondidas": sorted(respostas),
        "respostas": respostas,
    }


# --- gravar: validação das respostas --------------------------------------


_numero = base.numero


def _bool(valor: Any) -> Optional[bool]:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in ("true", "sim", "s", "yes", "y"):
            return True
        if texto in ("false", "nao", "não", "n", "no"):
            return False
    return None


def _data(valor: Any) -> Optional[date]:
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, str) and schema.RE_DIA_ID.fullmatch(valor.strip()):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def _lista_str(valor: Any) -> Optional[list[str]]:
    if valor is None:
        return []
    if isinstance(valor, str):
        return [item.strip() for item in valor.split(",") if item.strip()]
    if isinstance(valor, list) and all(isinstance(item, str) for item in valor):
        return [item.strip() for item in valor if item.strip()]
    return None


def _recusa(erros: list[str], campo: str, valor: Any, motivo: str) -> None:
    erros.append("%s: %r recusado (%s)" % (campo, valor, motivo))


def _meta_de_resposta(indice: int, resposta: Any, erros: list[str]) -> dict[str, Any]:
    """Uma resposta de meta → dict no esquema ``metas`` (sem ``id``/``criado_em``)."""
    prefixo = "metas[%d]" % indice
    if not isinstance(resposta, dict):
        _recusa(erros, prefixo, resposta, "esperado objeto com titulo, horizonte, prazo, custo")
        return {}
    meta: dict[str, Any] = {}
    for campo, conferir in CAMPOS_DA_META:
        try:
            valor = conferir(resposta)
        except Recusado as recusa:
            _recusa(erros, "%s.%s" % (prefixo, campo), recusa.valor, recusa.motivo)
            continue
        if valor is not AUSENTE:
            meta[campo] = valor
    for chave in resposta:
        if chave not in CHAVES_META and chave not in CHAVES_META_EXTRAS and chave != "impacto":
            _recusa(erros, "%s.%s" % (prefixo, chave), resposta[chave], "campo desconhecido")
    return meta


class Recusado(Exception):
    """Resposta recusada por uma conferência de campo: o valor a mostrar e o motivo."""

    def __init__(self, valor: Any, motivo: str) -> None:
        super().__init__(motivo)
        self.valor = valor
        self.motivo = motivo


AUSENTE = object()  # campo opcional que não veio: não entra na meta


def _titulo_da_meta(resposta: dict[str, Any]) -> str:
    titulo = resposta.get("titulo")
    if not isinstance(titulo, str) or not titulo.strip():
        raise Recusado(titulo, "título vazio")
    if len(titulo.strip()) > 120:
        raise Recusado(titulo[:30] + "...", "até 120 caracteres")
    return " ".join(titulo.split())


def _um_de(campo: str, opcoes: tuple, padrao: Any = AUSENTE) -> Callable[[dict[str, Any]], Any]:
    def conferir(resposta: dict[str, Any]) -> Any:
        valor = resposta.get(campo) if padrao is AUSENTE else resposta.get(campo, padrao)
        if valor not in opcoes:
            raise Recusado(valor, "esperado %s" % "|".join(opcoes))
        return valor

    return conferir


def _prazo_da_meta(resposta: dict[str, Any]) -> date:
    prazo = _data(resposta.get("prazo"))
    if prazo is None:
        raise Recusado(resposta.get("prazo"), "esperado AAAA-MM-DD")
    return prazo


def _prazo_externo(resposta: dict[str, Any]) -> bool:
    externo = _bool(resposta.get("prazo_externo", False))
    if externo is None:
        raise Recusado(resposta.get("prazo_externo"), "esperado sim/não")
    return externo


def _horas(campo: str, *, obrigatorio: bool = False) -> Callable[[dict[str, Any]], Any]:
    def conferir(resposta: dict[str, Any]) -> Any:
        bruto = resposta.get(campo)
        if bruto is None or bruto == "":
            if obrigatorio:
                raise Recusado(bruto, "horas por semana são obrigatórias (número > 0)")
            return AUSENTE
        numero = _numero(bruto)
        if numero is None or numero <= 0 or math.isnan(numero):
            raise Recusado(bruto, "esperado número > 0")
        return numero

    return conferir


def _semanas_da_pesquisa(resposta: dict[str, Any]) -> int:
    semanas = _numero(resposta.get("semanas_pesquisa"))
    if semanas is None or semanas <= 0 or int(semanas) != semanas:
        raise Recusado(resposta.get("semanas_pesquisa"), "esperado inteiro > 0 (semanas)")
    return int(semanas)


def _palavras_chave(resposta: dict[str, Any]) -> list[str]:
    palavras = _lista_str(resposta.get("palavras_chave"))
    if palavras is None:
        raise Recusado(resposta.get("palavras_chave"), "esperado lista de até 3 palavras")
    if len(palavras) > schema.TETO_PALAVRAS_CHAVE:
        raise Recusado(palavras, "no máximo %d" % schema.TETO_PALAVRAS_CHAVE)
    return palavras


# Campo da meta -> conferência; a ordem é a das mensagens (o montar ordena antes de mostrar).
CAMPOS_DA_META: tuple[tuple[str, Callable[[dict[str, Any]], Any]], ...] = (
    ("titulo", _titulo_da_meta),
    ("horizonte", _um_de("horizonte", schema.HORIZONTES)),
    ("prazo", _prazo_da_meta),
    ("prazo_externo", _prazo_externo),
    ("estado", _um_de("estado", schema.ESTADOS_META, "ativa")),
    ("custo_h_semana_min", _horas("custo_h_semana_min")),
    ("custo_h_semana_max", _horas("custo_h_semana_max")),
    ("custo_h_semana_escolhido", _horas("custo_h_semana_escolhido", obrigatorio=True)),
    ("semanas_pesquisa", _semanas_da_pesquisa),
    ("confianca", _um_de("confianca", schema.CONFIANCAS, "usuario")),
    ("impacto", _um_de("impacto", schema.IMPACTOS, "importante")),
    ("palavras_chave", _palavras_chave),
)


def _contexto_de_respostas(respostas: dict[str, Any], erros: list[str]) -> dict[str, Any]:
    """Respostas → dict no esquema ``contexto`` (sem ``schema_version``/``instalacao_id``)."""
    contexto = _horarios(respostas, erros)
    contexto.update({chave: respostas[chave] for chave in CHAVES_CONTEXTO_DIRETAS if respostas.get(chave) is not None})
    _normalizar_listas(contexto, erros)
    _normalizar_lembretes(contexto, erros)
    _normalizar_emails(contexto, erros)
    tz = contexto.get("timezone")
    if isinstance(tz, str) and tz:
        try:
            clock.fuso(tz)
        except GpErro:
            _recusa(erros, "timezone", tz, "não está na lista IANA (ex.: America/Sao_Paulo)")
    idioma = contexto.get("idioma")
    if idioma is not None and idioma not in copy.disponiveis():
        _recusa(erros, "idioma", idioma, "use um destes: %s" % ", ".join(copy.disponiveis()))
    return contexto


VAZIOS_HORARIO = ("", "nenhum", "nenhuma", "-", "nao", "não")


def _horarios(respostas: dict[str, Any], erros: list[str]) -> dict[str, Any]:
    """``horario_util`` (objeto seg_sex/sab/dom) ou as chaves planas; "nenhum" vira vazio."""
    horario = respostas.get("horario_util") or {}
    if not isinstance(horario, dict):
        _recusa(erros, "horario_util", horario, "esperado objeto com seg_sex, sab, dom")
        horario = {}
    saida: dict[str, Any] = {}
    for curta, chave in CHAVES_HORARIO.items():
        valor = horario.get(curta, respostas.get(chave))
        if valor is None:
            continue
        texto = valor.strip() if isinstance(valor, str) else None
        if texto is not None and texto.lower() in VAZIOS_HORARIO:
            saida[chave] = ""
        elif texto is not None and schema.RE_HORARIO_UTIL.fullmatch(texto):
            saida[chave] = texto
        else:
            _recusa(erros, chave, valor, "esperado HH:MM-HH:MM ou nenhum")
    return saida


def _normalizar_listas(contexto: dict[str, Any], erros: list[str]) -> None:
    for chave in ("calendarios_lidos", "email_alias", "fontes_ativas", "pessoas"):
        if chave not in contexto:
            continue
        lista = _lista_str(contexto[chave])
        if lista is None:
            _recusa(erros, chave, contexto.pop(chave), "esperado lista")
        else:
            contexto[chave] = lista


def _normalizar_lembretes(contexto: dict[str, Any], erros: list[str]) -> None:
    if "lembretes" not in contexto:
        return
    lembretes = contexto["lembretes"]
    if isinstance(lembretes, bool):
        contexto["lembretes"] = "sim" if lembretes else "nao"
    elif isinstance(lembretes, str) and lembretes.strip().lower() in ("sim", "nao", "não"):
        contexto["lembretes"] = "nao" if lembretes.strip().lower() == "não" else lembretes.strip().lower()
    else:
        _recusa(erros, "lembretes", contexto.pop("lembretes"), "esperado sim ou nao")


def _normalizar_emails(contexto: dict[str, Any], erros: list[str]) -> None:
    valor = contexto.get("email_proprio")
    if isinstance(valor, str) and not valor.strip():
        contexto["email_proprio"] = ""  # sem Gmail: o dia fica no app
    elif isinstance(valor, str):
        email = _email_de(valor)
        if email is None:
            _recusa(erros, "email_proprio", valor, "não parece um e-mail")
        else:
            contexto["email_proprio"] = email
    if "email_alias" not in contexto:
        return
    limpos = []
    for item in contexto["email_alias"]:
        email = _email_de(item)
        if email is None:
            _recusa(erros, "email_alias", item, "não parece um e-mail")
        else:
            limpos.append(email)
    contexto["email_alias"] = limpos


def _validar_contexto(contexto: dict[str, Any], erros: list[str]) -> Optional[dict[str, Any]]:
    coagido, erros_coagir = frontmatter.coagir(contexto, schema.ESQUEMAS["contexto"])
    for erro in erros_coagir + (schema.validar_registro("contexto", coagido) if not erros_coagir else []):
        campo = erro.split(":", 1)[0]
        _recusa(erros, campo, contexto.get(campo), erro.split(":", 1)[1].strip())
    return None if erros else coagido


def _ids_existentes(dados: Path) -> dict[str, str]:
    """``titulo normalizado → id`` das metas já gravadas (para não duplicar)."""
    pasta = dados / "metas"
    existentes: dict[str, str] = {}
    if not pasta.is_dir():
        return existentes
    for path in sorted(pasta.glob("M*.md")):
        if not schema.validar_id("meta", path.stem):
            continue
        try:
            bruto, _ = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        titulo = bruto.get("titulo")
        existentes[" ".join(str(titulo).lower().split()) if titulo else path.stem] = path.stem
    return existentes


def _proximo_id(usados: set[str]) -> str:
    for n in range(1, 100):
        candidato = "M%02d" % n
        if candidato not in usados:
            return candidato
    raise GpErro(EXIT_VALIDACAO, "sem id livre para meta (M01..M99)")


def _contexto_existente(dados: Path) -> dict[str, Any]:
    path = dados / schema.CAMINHOS["contexto"]
    if not path.exists():
        return {}
    try:
        bruto, _ = frontmatter.ler_arquivo(path)
    except GpErro:
        return {}
    return bruto


def _corpo_meta(resposta: dict[str, Any]) -> str:
    lido = resposta.get("porque")
    porque = lido if isinstance(lido, str) else ""
    marcos = _lista_str(resposta.get("marcos")) or []
    linhas = ["", "## Por que esta meta", "", porque.strip() or "(preencha)", "", "## Marcos", ""]
    linhas.extend("- [ ] " + m for m in marcos) if marcos else linhas.append("- [ ] (preencha o primeiro marco)")
    linhas.extend(["", "## Notas", "", ""])
    return "\n".join(linhas)


def _fonte_de_resposta(meta: dict[str, Any], resposta: dict[str, Any], agora: datetime) -> tuple[dict[str, Any], str]:
    lida = resposta.get("pesquisa")
    pesquisa: dict[str, Any] = lida if isinstance(lida, dict) else {}
    urls = _lista_str(pesquisa.get("urls")) or []
    trecho = str(pesquisa.get("trecho") or "").strip()
    busca = str(pesquisa.get("busca") or "").strip()
    fonte = {
        "id": meta["id"],
        "pesquisado_em": agora,
        "estado": "ok" if (urls or trecho or meta.get("confianca") == "usuario") else "sem_numero",
        "busca": busca,
        "urls": urls,
        "trecho": trecho,
        "hash_meta": schema.hash_meta_pesquisa(meta),
    }
    for nome in ("custo_h_semana_min", "custo_h_semana_max", "semanas_pesquisa"):
        if meta.get(nome) is not None:
            fonte[nome] = meta[nome]
    corpo = ["", "## Pesquisa de custo", ""]
    if meta.get("confianca") == "usuario" and not urls:
        corpo.append("Número dado pelo usuário no onboarding; sem pesquisa registrada.")
    else:
        corpo.append("Busca: %s" % (busca or "(não registrada)"))
        corpo.extend("- " + u for u in urls)
        if trecho:
            corpo.extend(["", "> " + trecho.replace("\n", " ")])
    corpo.append("")
    return fonte, "\n".join(corpo)


def _chave_titulo(titulo: str) -> str:
    return " ".join(str(titulo).lower().split())


def _objetivos_existentes(dados: Path) -> dict[str, str]:
    """Título normalizado -> id dos objetivos já gravados."""
    saida = {}
    pasta = dados / "objetivos"
    for path in sorted(pasta.glob("O*.md")) if pasta.is_dir() else []:
        if not schema.validar_id("objetivo", path.stem):
            continue
        try:
            bruto, _ = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        saida[_chave_titulo(bruto.get("titulo", ""))] = path.stem
    return saida


def _objetivos_de_respostas(
    respostas: dict[str, Any], dados: Path, agora_iso: str, erros: list[str]
) -> tuple[list[tuple[dict[str, Any], str]], dict[str, str]]:
    """Objetivos novos prontos para gravar e o mapa título -> id (novos e já cadastrados)."""
    existentes = _objetivos_existentes(dados)
    mapa = dict(existentes)
    lista = respostas.get("objetivos") or []
    if not isinstance(lista, list):
        _recusa(erros, "objetivos", lista, "esperado lista de objetivos")
        return [], mapa
    if len(lista) > TETO_OBJETIVOS:
        _recusa(erros, "objetivos", len(lista), "no máximo %d objetivos" % TETO_OBJETIVOS)
    usados = set(existentes.values())
    novos = []
    for i, item in enumerate(lista):
        titulo = _titulo_do_objetivo(i, item, erros)
        if titulo is None or _chave_titulo(titulo) in mapa:
            continue
        oid = next("O%02d" % n for n in range(1, 1000) if "O%02d" % n not in usados)
        usados.add(oid)
        mapa[_chave_titulo(titulo)] = oid
        novos.append(_objetivo_novo(oid, titulo, item, agora_iso))
    return novos, mapa


def _titulo_do_objetivo(indice: int, item: Any, erros: list[str]) -> Optional[str]:
    prefixo = "objetivos[%d]" % indice
    titulo = item.get("titulo") if isinstance(item, dict) else None
    if not isinstance(titulo, str) or not titulo.strip() or len(titulo) > 120:
        _recusa(erros, prefixo + ".titulo", titulo, "título de 1 a 120 caracteres")
        return None
    for chave in item:
        if chave not in ("titulo", "porque", "como_vou_saber"):
            _recusa(erros, "%s.%s" % (prefixo, chave), item[chave], "campo desconhecido")
    return titulo


def _objetivo_novo(oid: str, titulo: str, item: dict[str, Any], agora_iso: str) -> tuple[dict[str, Any], str]:
    porque = " ".join(str(item.get("porque") or "").split()) or "(preencha)"
    saber = " ".join(str(item.get("como_vou_saber") or "").split()) or "(preencha)"
    front = {"id": oid, "titulo": " ".join(titulo.split()), "estado": "ativo", "criado_em": agora_iso}
    return front, "\n## Por que\n\n%s\n\n## Como vou saber\n\n%s\n" % (porque, saber)


def montar(respostas: dict[str, Any], dados: Path, instalacao_id: Optional[str]) -> dict[str, Any]:
    """Valida as respostas e devolve tudo pronto para gravar (sem tocar no disco):
    ``{"contexto": (dict, corpo), "metas": [(dict, corpo)], "fontes": [(dict, corpo)],
    "ignoradas": [titulos], "instalacao_id": str}``; ``RespostaInvalida`` se algo é recusado."""
    erros: list[str] = []
    if not isinstance(respostas, dict):
        raise RespostaInvalida(["respostas: esperado objeto JSON"])
    metas_resp = _lista_de_metas(respostas, erros)
    for chave, valor in respostas.items():
        if chave not in CHAVES_DE_TOPO:
            _recusa(erros, chave, valor, "campo desconhecido")
    metas_parciais = [_meta_de_resposta(i, r, erros) for i, r in enumerate(metas_resp)]
    contexto = _contexto_completo(respostas, dados, instalacao_id, erros)
    objetivos_novos, mapa_objetivos = _objetivos_de_respostas(
        respostas, dados, clock.agora(_fuso_ou_sistema(contexto)).isoformat(timespec="seconds"), erros
    )
    _conferir_objetivo_das_metas(metas_resp, mapa_objetivos, erros)
    contexto_ok = _validar_contexto(contexto, erros) if not erros else None
    if erros or contexto_ok is None:
        raise RespostaInvalida(sorted(set(erros)))
    agora = clock.agora(clock.fuso(contexto_ok["timezone"]))
    metas_prontas, fontes, ignoradas = _metas_prontas(metas_resp, metas_parciais, dados, mapa_objetivos, agora)
    corpo_contexto = (
        "\n# Contexto\n\nGravado pelo onboarding em %s. Edite à vontade; o esquema está em references/dados.md.\n"
        % agora.date().isoformat()
    )
    return {
        "contexto": (contexto_ok, corpo_contexto),
        "objetivos": [_pronto("objetivo", "objetivos", front, corpo) for front, corpo in objetivos_novos],
        "metas": metas_prontas,
        "fontes": fontes,
        "ignoradas": ignoradas,
        "instalacao_id": contexto_ok["instalacao_id"],
    }


def _conferir_objetivo_das_metas(metas_resp: list[Any], mapa_objetivos: dict[str, str], erros: list[str]) -> None:
    for i, resposta in enumerate(metas_resp):
        alvo = resposta.get("objetivo") if isinstance(resposta, dict) else None
        if alvo not in (None, "") and (not isinstance(alvo, str) or _chave_titulo(alvo) not in mapa_objetivos):
            _recusa(
                erros, "metas[%d].objetivo" % i, alvo, "título que não está em objetivos nem entre os já cadastrados"
            )


OBRIGATORIOS_CONTEXTO = ("timezone",)
# o que o contexto já gravado guarda quando a resposta não traz (reonboarding sem perder os conectores escolhidos)
PRESERVADOS_CONTEXTO = ("timezone", "calendar_id_metas", "calendar_id_primario", "email_proprio")
CHAVES_DE_TOPO = frozenset(("metas", "horario_util", "objetivos", *CHAVES_CONTEXTO_DIRETAS, *CHAVES_HORARIO.values()))


def _lista_de_metas(respostas: dict[str, Any], erros: list[str]) -> list[Any]:
    metas_resp = respostas.get("metas")
    if not isinstance(metas_resp, list) or not metas_resp:
        _recusa(erros, "metas", metas_resp, "pelo menos uma meta")
        return []
    if len(metas_resp) > TETO_METAS:
        _recusa(erros, "metas", len(metas_resp), "no máximo %d metas" % TETO_METAS)
    return metas_resp


def _contexto_completo(
    respostas: dict[str, Any], dados: Path, instalacao_id: Optional[str], erros: list[str]
) -> dict[str, Any]:
    """Padrões do esquema, o que o contexto já gravado tem e a resposta não traz, e as respostas por cima."""
    contexto_novo = _contexto_de_respostas(respostas, erros)
    existente = _contexto_existente(dados)
    contexto = dict(schema.defaults("contexto"))
    contexto.update({c: existente[c] for c in PRESERVADOS_CONTEXTO if c in existente and c not in contexto_novo})
    contexto.update(contexto_novo)
    contexto["schema_version"] = schema.SCHEMA_VERSION
    contexto["instalacao_id"] = instalacao_id or existente.get("instalacao_id") or ("inst-" + secrets.token_hex(4))
    for chave in OBRIGATORIOS_CONTEXTO:
        if not contexto.get(chave):
            _recusa(erros, chave, contexto.get(chave), "obrigatório")
    if bool(contexto.get("calendar_id_metas")) != bool(contexto.get("calendar_id_primario")):
        faltando = "calendar_id_primario" if contexto.get("calendar_id_metas") else "calendar_id_metas"
        _recusa(erros, faltando, contexto.get(faltando), "vem junto com o outro calendário (ou nenhum dos dois)")
    if "gmail" in (contexto.get("fontes_ativas") or []) and not contexto.get("email_proprio"):
        _recusa(erros, "email_proprio", "", "a fonte gmail precisa do e-mail próprio")
    if contexto.get("calendar_id_metas") and contexto.get("calendar_id_metas") == contexto.get("calendar_id_primario"):
        _recusa(
            erros,
            "calendar_id_metas",
            contexto["calendar_id_metas"],
            "igual ao calendário primário; o Metas precisa ser separado",
        )
    return contexto


def _fuso_ou_sistema(contexto: dict[str, Any]) -> Any:
    try:
        return clock.fuso(contexto.get("timezone"))
    except GpErro:
        return clock.fuso()


def _pronto(esquema: str, rotulo: str, front: dict[str, Any], corpo: str) -> tuple[dict[str, Any], str]:
    """Front-matter coagido e validado no esquema; o que não passa vira ``RespostaInvalida`` com o título."""
    coagido, erros = frontmatter.coagir(front, schema.ESQUEMAS[esquema])
    erros = erros or schema.validar_registro(esquema, coagido)
    if erros:
        raise RespostaInvalida(["%s (%s): %s" % (rotulo, front["titulo"], e) for e in erros])
    return coagido, corpo


def _metas_prontas(
    metas_resp: list[Any],
    metas_parciais: list[dict[str, Any]],
    dados: Path,
    mapa_objetivos: dict[str, str],
    agora: datetime,
) -> tuple[list[tuple[dict[str, Any], str]], list[tuple[dict[str, Any], str]], list[str]]:
    """``(metas, fontes, títulos ignorados)``: metas novas com id livre; título já cadastrado ou repetido é ignorado."""
    existentes = _ids_existentes(dados)
    usados = set(existentes.values())
    metas: list[tuple[dict[str, Any], str]] = []
    fontes: list[tuple[dict[str, Any], str]] = []
    ignoradas: list[str] = []
    vistos: set[str] = set()
    for resposta, parcial in zip(metas_resp, metas_parciais):
        chave = _chave_titulo(parcial["titulo"])
        if chave in existentes or chave in vistos:
            ignoradas.append(parcial["titulo"])
            continue
        vistos.add(chave)
        meta = dict(schema.defaults("metas"), **parcial)
        meta["id"] = _proximo_id(usados)
        usados.add(meta["id"])
        meta["fonte"] = "fontes/%s.md" % meta["id"]
        if isinstance(resposta.get("objetivo"), str) and resposta["objetivo"].strip():
            meta["objetivo"] = mapa_objetivos[_chave_titulo(resposta["objetivo"])]
        meta["criado_em"] = agora
        coagido, _ = _pronto("metas", "metas", meta, "")
        fonte, corpo_fonte = _fonte_de_resposta(coagido, resposta, agora)
        erros_fonte = schema.validar_registro("fonte_pesquisa", fonte)
        if erros_fonte:
            raise RespostaInvalida(["fontes (%s): %s" % (meta["titulo"], e) for e in erros_fonte])
        metas.append((coagido, _corpo_meta(resposta)))
        fontes.append((fonte, corpo_fonte))
    if not metas and not usados:
        raise RespostaInvalida(["metas: nenhuma meta nova e nenhuma existente"])
    return metas, fontes, ignoradas


def gravar(montado: dict[str, Any], dados: Path) -> list[str]:
    """Grava o que ``montar`` preparou (atômico, um arquivo por vez) e
    devolve os caminhos relativos gravados."""
    gravados: list[str] = []
    for objetivo, corpo in montado.get("objetivos", []):
        path = base.caminho_dados("objetivos", objetivo["id"] + ".md")
        frontmatter.escrever_arquivo(path, objetivo, corpo)
        gravados.append(validar._relativo(path, dados))
    for meta, corpo in montado["metas"]:
        path = base.caminho_dados("metas", meta["id"] + ".md")
        frontmatter.escrever_arquivo(path, meta, corpo)
        gravados.append(validar._relativo(path, dados))
    for fonte, corpo in montado["fontes"]:
        path = base.caminho_dados("fontes", fonte["id"] + ".md")
        frontmatter.escrever_arquivo(path, fonte, corpo)
        gravados.append(validar._relativo(path, dados))
    contexto, corpo = montado["contexto"]
    path = base.caminho_dados(schema.CAMINHOS["contexto"])
    frontmatter.escrever_arquivo(path, contexto, corpo)
    gravados.append(validar._relativo(path, dados))
    return gravados


# --- CLI ---------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = cli.parser_base("onboarding do Goal Pacer: detectar, rascunho e gravação das respostas")
    parser.add_argument("--json", action="store_true", help="saída em JSON no stdout")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("detectar", help="pré-preenche e-mail, calendários, Metas e fontes (proxies ou --offline)")
    p_r = sub.add_parser("rascunho", help="ver | salvar --respostas <json> | descartar")
    p_r.add_argument("acao", choices=("ver", "salvar", "descartar"))
    p_r.add_argument("--respostas", type=Path, default=None, help="JSON com as respostas a fundir no rascunho")
    p_g = sub.add_parser("gravar", help="valida e grava metas/, fontes/ e contexto.md (das --respostas ou do rascunho)")
    p_g.add_argument("--respostas", type=Path, default=None, help="JSON com todas as respostas; sem ele usa o rascunho")
    p_g.add_argument("--instalacao-id", dest="instalacao_id", default=None, help="fixa o id da instalação (testes)")
    p_g.add_argument("--manter-rascunho", action="store_true", help="não apaga o rascunho depois de gravar")
    return parser


def _ler_respostas(path: Path) -> dict[str, Any]:
    try:
        dados = gpio.ler_json(path)
    except GpErro as erro:
        raise RespostaInvalida(["respostas: %s" % erro.mensagem]) from erro
    if not isinstance(dados, dict):
        raise RespostaInvalida(["respostas: esperado objeto JSON"])
    return dados


def _saida(args: argparse.Namespace, dados: dict[str, Any], texto: str = "") -> None:
    if args.json:
        sys.stdout.write(json.dumps(dados, ensure_ascii=False, indent=2, default=str) + "\n")
    elif texto:
        sys.stdout.write(texto + "\n")
    sys.stdout.flush()


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    try:
        cli.aplicar_args_base(args)
        if args.comando == "detectar":
            deteccao = detectar(modo_offline=args.offline)
            _saida(args, deteccao, json.dumps(deteccao, ensure_ascii=False, indent=2))
            return EXIT_OK
        if args.comando == "rascunho":
            return _comando_rascunho(args)
        return _comando_gravar(args, base.data_dir())
    except GpErro as erro:
        erros = erro.erros if isinstance(erro, RespostaInvalida) else [erro.mensagem]
        if args.json:
            _saida(args, {"ok": False, "codigo": erro.codigo, "erros": erros})
        for texto in erros:
            print("erro: " + texto, file=sys.stderr)
        return erro.codigo


def _comando_rascunho(args: argparse.Namespace) -> int:
    if args.acao == "ver":
        resumo = resumo_rascunho(ler_rascunho())
        _saida(args, resumo, json.dumps(resumo, ensure_ascii=False, indent=2))
        return EXIT_OK if resumo["existe"] else EXIT_ESTADO
    if args.acao == "salvar":
        if args.respostas is None:
            raise GpErro(EXIT_VALIDACAO, "rascunho salvar exige --respostas <json>")
        resumo = resumo_rascunho(salvar_rascunho(_ler_respostas(args.respostas)))
        _saida(args, resumo, "rascunho salvo: %s" % ", ".join(resumo["respondidas"]))
        return EXIT_OK
    existia = descartar_rascunho()
    _saida(args, {"descartado": existia}, "rascunho descartado" if existia else "não havia rascunho")
    return EXIT_OK


def _comando_gravar(args: argparse.Namespace, dados: Path) -> int:
    if args.respostas is not None:
        respostas = _ler_respostas(args.respostas)
    else:
        rascunho = ler_rascunho()
        if rascunho is None:
            raise GpErro(EXIT_ESTADO, "sem --respostas e sem rascunho em cache/%s" % NOME_RASCUNHO)
        respostas = rascunho.get("respostas") or {}
    saida = gravar_respostas(respostas, dados, instalacao_id=args.instalacao_id, manter_rascunho=args.manter_rascunho)
    _saida(args, {k: v for k, v in saida.items() if k != "texto"}, saida["texto"])
    return EXIT_OK


def gravar_respostas(
    respostas: dict[str, Any], dados: Path, *, instalacao_id: Optional[str] = None, manter_rascunho: bool = False
) -> dict[str, Any]:
    """Valida, grava metas/, objetivos/, fontes/ e contexto.md, confere o grafo e apaga o rascunho (a skill e o
    painel gravam por aqui). Resposta recusada é ``RespostaInvalida`` sem nada gravado."""
    montado = montar(respostas, dados, instalacao_id)
    gravados = gravar(montado, dados)
    resultado = validar.validar_grafo(dados)
    if resultado.codigo not in (EXIT_OK, EXIT_ESTADO):
        raise GpErro(resultado.codigo, "gravado, mas validar.py grafo reprovou:\n" + "\n".join(resultado.erros))
    if not manter_rascunho:
        descartar_rascunho()
    return {
        "gravados": gravados,
        "ignoradas": montado["ignoradas"],
        "instalacao_id": montado["instalacao_id"],
        "avisos": resultado.avisos,
        "estado": resultado.estado,
        "texto": _texto_gravado(montado),
    }


DIAS_TRIMESTRE = 92
DIAS_SEMESTRE = 184


def completar_meta(resposta: dict[str, Any], hoje: date) -> dict[str, Any]:
    """Meta vinda de um formulário sem pesquisa (painel): o horizonte sai do prazo (até 92 dias trimestre, até 184
    semestre, depois ano), as semanas são as que faltam até o prazo e a confiança é a da pessoa. Campo já dado fica."""
    meta = dict(resposta)
    prazo = _data(meta.get("prazo"))
    if prazo is None:
        return meta
    dias = max(1, (prazo - hoje).days)
    if not meta.get("horizonte"):
        meta["horizonte"] = "trimestre" if dias <= DIAS_TRIMESTRE else "semestre" if dias <= DIAS_SEMESTRE else "ano"
    if not meta.get("semanas_pesquisa"):
        meta["semanas_pesquisa"] = max(1, math.ceil(dias / 7))
    meta.setdefault("confianca", "usuario")
    return meta


def _texto_gravado(montado: dict[str, Any]) -> str:
    valores: dict[str, Any] = {"n_metas": len(montado["metas"]), "instalacao_id": montado["instalacao_id"]}
    if montado["objetivos"]:
        texto = copy.texto("onboarding.gravado_objetivos", n_objetivos=len(montado["objetivos"]), **valores)
    else:
        texto = copy.texto("onboarding.gravado", **valores)
    if montado["ignoradas"]:
        texto += "\nIgnoradas (já existem): %s" % ", ".join(montado["ignoradas"])
    return texto + "\n" + copy.texto("onboarding.tela_final")


if __name__ == "__main__":
    raise SystemExit(main())
