"""Responder ao email das 7h como check-in, sem terminal e sem mexer no bloco.

Roda no diário, antes da inferência pelo Calendar (o confirmado vence o inferido)::

    search_threads {query: in:sent subject:"[goal-pacer]" newer_than:3d}        conector em modo leitura
      -> mensagens com label SENT e assunto "Re: [goal-pacer] <Dia dd/mm> ..." ainda não aplicadas
    get_message {messageId, messageFormat: FULL_CONTENT} -> texto puro
      -> só o que está acima da citação, até 20 linhas, e só linhas nesta gramática (pt-BR ou en):
             02 fiz 1h          (número do bloco no email daquele dia; "02 done 1h")
             03 não fiz         ("03 skipped", "03 not done")
             D-2026-09-28-04 feita 45min
      -> checkin.confirmar (feitas com duração real, não feitas), só blocos que existem
      -> registro.respostas_email guarda o id da mensagem, nunca o texto, para não aplicar duas vezes

Segurança por construção: o label SENT só existe em mensagem enviada pela própria conta (um
terceiro não consegue fabricá-lo na caixa da pessoa); o corpo nunca vira instrução nem prompt,
só linhas que casam a gramática; mensagem já aplicada não volta; nada do texto é guardado.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from goalpacer import copy, offline, perfil, proxy, registro as reg, schema

TOOL_BUSCA = "mcp__claude_ai_Gmail__search_threads"
TOOL_MENSAGEM = "mcp__claude_ai_Gmail__get_message"
QUERY = 'in:sent subject:"[goal-pacer]" newer_than:3d'
TETO_MENSAGENS = 10
TETO_LINHAS = 20
TETO_GUARDADAS = 200
DURACAO_MAXIMA_H = 12.0
RE_ASSUNTO = re.compile(r"^\s*(re|res|resp)\s*:\s*\[goal-pacer\]\s*(.*)$", re.IGNORECASE)
RE_DATA_NUMERICA = re.compile(r"(\d{2})/(\d{2})")  # pt-BR: Seg 28/09
RE_DATA_MES_DIA = re.compile(r"\b([A-Za-z]{3})\s+(\d{1,2})\b")  # en: Mon Sep 28
FEITA = r"fiz|feita|feito|done|did"
NAO_FEITA = r"n[aã]o\s+fiz|n[aã]o\s+feita|n[aã]o\s+feito|skipped|skip|not\s+done|did\s+not|didn'?t"
RE_LINHA = re.compile(
    r"^\s*(?:(D-\d{4}-\d{2}-\d{2}-\d{2})|(\d{2}))\s+(%s|%s)" % (NAO_FEITA, FEITA)
    + r"(?:\s+(\d+(?:[.,]\d+)?)\s*(h|min))?\s*[.;]?\s*$",
    re.IGNORECASE,
)
RE_NAO_FEITA = re.compile(r"^(%s)$" % NAO_FEITA, re.IGNORECASE)
RE_CITACAO = re.compile(
    r"^\s*(>|(on|em)\s.+(wrote|escreveu)\s*:\s*$|-{2,}\s*(original|mensagem original))", re.IGNORECASE
)


def data_do_assunto(assunto: str, referencia: date) -> Optional[date]:
    """``Re: [goal-pacer] Seg 28/09 ...`` ou ``Re: [goal-pacer] Mon Sep 28 ...`` -> 2026-09-28 (o ano mais próximo da referência)."""
    m = RE_ASSUNTO.match(assunto or "")
    dia_mes = _dia_e_mes(m.group(2)) if m else None
    if dia_mes is None:
        return None
    dia, mes = dia_mes
    for ano in (referencia.year, referencia.year - 1):
        try:
            candidato = date(ano, mes, dia)
        except ValueError:
            return None
        if candidato <= referencia:
            return candidato
    return None


def _dia_e_mes(resto: str) -> Optional[tuple[int, int]]:
    """``28/09`` (pt-BR) ou ``Sep 28`` com o mês abreviado em qualquer idioma do copy."""
    numerica = RE_DATA_NUMERICA.search(resto)
    if numerica:
        return int(numerica.group(1)), int(numerica.group(2))
    mes_dia = RE_DATA_MES_DIA.search(resto)
    if not mes_dia:
        return None
    meses = {
        nome.lower(): i + 1
        for idioma in copy.disponiveis()
        for i, nome in enumerate(copy.lista("calendario.meses_curtos", idioma))
    }
    mes = meses.get(mes_dia.group(1).lower())
    return (int(mes_dia.group(2)), mes) if mes else None


def linhas_de_resposta(texto: str) -> list[str]:
    saida = []
    for linha in (texto or "").replace("\r", "").split("\n"):
        if RE_CITACAO.match(linha):
            break
        if linha.strip():
            saida.append(linha)
        if len(saida) >= TETO_LINHAS:
            break
    return saida


def interpretar(texto: str, dia_do_email: Optional[date]) -> dict[str, dict[str, Any]]:
    """``task_id -> {"feita": bool, "duracao_real_h": float|None}``; a última linha de um bloco vence."""
    saida: dict[str, dict[str, Any]] = {}
    for linha in linhas_de_resposta(texto):
        pedido = _pedido_da_linha(linha, dia_do_email)
        if pedido is not None:
            saida[pedido[0]] = pedido[1]
    return saida


def _pedido_da_linha(linha: str, dia_do_email: Optional[date]) -> Optional[tuple[str, dict[str, Any]]]:
    """Uma linha na gramática vira ``(task_id, pedido)``; número de bloco sem o dia do email não vale."""
    m = RE_LINHA.match(linha)
    if not m:
        return None
    task_id = m.group(1)
    if task_id is None:
        if dia_do_email is None:
            return None
        task_id = "D-%s-%s" % (dia_do_email.isoformat(), m.group(2))
    if not schema.validar_id("task", task_id):
        return None
    feita = RE_NAO_FEITA.match(m.group(3)) is None
    duracao = _duracao_h(m.group(4), m.group(5)) if feita else None
    return task_id, {"feita": feita, "duracao_real_h": round(duracao, 2) if duracao else None}


def _duracao_h(valor: Optional[str], unidade: Optional[str]) -> Optional[float]:
    """``1h``, ``1,5h`` ou ``45min`` em horas; fora de (0, 12 h] é ignorada."""
    if not valor or not unidade:
        return None
    horas = float(valor.replace(",", "."))
    horas = horas / 60.0 if unidade.lower() == "min" else horas
    return horas if 0 < horas <= DURACAO_MAXIMA_H else None


def _texto(mensagem: dict[str, Any]) -> str:
    for chave in ("plaintext_body", "plaintextBody", "body", "text"):
        valor = mensagem.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor
    return ""


def _chamar(tool: str, args: dict[str, Any], *, modo_offline: bool, registro_proxies: list) -> dict[str, Any]:
    if modo_offline:
        return offline.resposta(tool, args)
    return proxy.chamar(tool, args, modo_leitura=True, registro=registro_proxies)


def aplicar(
    dados: Path,
    *,
    modo_offline: bool,
    agora: datetime,
    registro_proxies: Optional[list] = None,
    confirmar: Callable[..., Any],
) -> dict[str, Any]:
    """Aplica as respostas novas; devolve ``{"mensagens", "confirmados", "nao_feitos", "ignorados"}``.
    ``confirmar`` é o ``checkin.confirmar`` injetado pelo diário (o pacote não importa CLIs)."""
    registro_proxies = registro_proxies if registro_proxies is not None else []
    resultado = {"mensagens": 0, "confirmados": 0, "nao_feitos": 0, "ignorados": 0}
    busca = _chamar(
        TOOL_BUSCA,
        {"query": QUERY, "pageSize": TETO_MENSAGENS},
        modo_offline=modo_offline,
        registro_proxies=registro_proxies,
    )
    ja_aplicadas = set(reg.carregar(dados).get("respostas_email") or [])
    for mensagem_id, dia in _candidatas(busca, ja_aplicadas, agora.date())[:TETO_MENSAGENS]:
        completa = _chamar(
            TOOL_MENSAGEM,
            {"messageId": mensagem_id, "messageFormat": "FULL_CONTENT"},
            modo_offline=modo_offline,
            registro_proxies=registro_proxies,
        )
        if "SENT" not in (completa.get("labelIds") or ["SENT"]):
            continue  # a mensagem completa precisa confirmar a origem quando traz os labels
        contagem = _aplicar_pedidos(dados, interpretar(_texto(completa), dia), agora, confirmar)
        registro = reg.carregar(dados)
        registro["respostas_email"] = [*(registro.get("respostas_email") or []), mensagem_id][-TETO_GUARDADAS:]
        reg.salvar(registro, dados)
        resultado["mensagens"] += 1
        for chave, n in contagem.items():
            resultado[chave] += n
    return resultado


def _candidatas(busca: dict[str, Any], ja_aplicadas: set[str], hoje: date) -> list[tuple[str, Optional[date]]]:
    """``(id, dia do assunto)`` das mensagens ENVIADAS com assunto de resposta ao email das 7h, ainda não aplicadas."""
    mensagens = [
        m
        for thread in busca.get("threads") or []
        if isinstance(thread, dict)
        for m in thread.get("messages") or []
        if isinstance(m, dict) and m.get("id") and m["id"] not in ja_aplicadas
    ]
    return [
        (str(m["id"]), data_do_assunto(str(m.get("subject") or ""), hoje))
        for m in mensagens
        if "SENT" in (m.get("labelIds") or []) and RE_ASSUNTO.match(str(m.get("subject") or ""))
    ]


def _aplicar_pedidos(
    dados: Path, pedidos: dict[str, dict[str, Any]], agora: datetime, confirmar: Callable[..., Any]
) -> dict[str, int]:
    """Confirma pelo check-in só os blocos que existem; os outros pedidos contam como ignorados."""
    existentes = perfil.blocos_com_registro(dados, reg.carregar(dados))
    feitas = [
        {"task_id": t, "duracao_real_h": p["duracao_real_h"]}
        for t, p in sorted(pedidos.items())
        if p["feita"] and t in existentes
    ]
    nao_feitas = [t for t, p in sorted(pedidos.items()) if not p["feita"] and t in existentes]
    if feitas or nao_feitas:
        confirmar(dados, {"feitas": feitas, "nao_feitas": nao_feitas}, agora=agora)
    return {
        "confirmados": len(feitas),
        "nao_feitos": len(nao_feitas),
        "ignorados": sum(1 for t in pedidos if t not in existentes),
    }
