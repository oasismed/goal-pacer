"""Envio do email das 7h pelo Gmail (design "Email das 7h"; D4.8; T30).

Único caminho: proxy de ``send_message`` para ``email_proprio`` com ``body``
(texto) e ``htmlBody`` (HTML), multipart pelo contrato do schema do
conector; a escrita real depende do escopo ``gmail.send`` (spike §6).
Assunto sempre com o prefixo ``[goal-pacer]`` (a busca do ``mensal-ler``
exclui esses emails). Em ``--offline`` o email vai para
``cache/email-<run_id>.json`` (retenção de 7 dias) e nada sai da máquina.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from goalpacer import base, io as gpio, proxy
from goalpacer.base import EXIT_VALIDACAO, GpErro

TOOL_SEND = "mcp__claude_ai_Gmail__send_message"
PREFIXO_ASSUNTO = "[goal-pacer]"


def argumentos(contexto: dict[str, Any], assunto: str, texto: str, html: str) -> dict[str, Any]:
    if not assunto.startswith(PREFIXO_ASSUNTO):
        raise GpErro(EXIT_VALIDACAO, "assunto sem o prefixo %s" % PREFIXO_ASSUNTO)
    destino = contexto.get("email_proprio")
    if not destino:
        raise GpErro(EXIT_VALIDACAO, "contexto sem email_proprio")
    return {"to": [destino], "subject": assunto, "body": texto, "htmlBody": html}


def enviar(
    contexto: dict[str, Any],
    assunto: str,
    texto: str,
    html: str,
    *,
    run_id: str,
    modo_offline: bool,
    registro: Any = None,
    chamar: Optional[Callable[..., dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Envia e devolve ``{"id", "offline"}``; erro do conector propaga (quem chama registra ``email: falhou``)."""
    args = argumentos(contexto, assunto, texto, html)
    if modo_offline:
        path = base.caminho_dados("cache", "email-%s.json" % run_id)
        gpio.escrever_json(path, args)
        return {"id": "off-%s" % run_id, "offline": True, "arquivo": "cache/%s" % path.name}
    if chamar is not None:
        resposta = chamar(TOOL_SEND, args)
    else:
        resposta = proxy.chamar(TOOL_SEND, args, modo_leitura=False, registro=registro)
    return {"id": (resposta or {}).get("id"), "offline": False}
