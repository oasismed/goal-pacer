"""Provedor de IA da instalação: o login que a pessoa já tem, nunca uma chave ou um token guardado por nós.

    claude   Claude Code (``claude -p``) com a assinatura Claude: conectores do claude.ai, prosa e mensal-ler (padrão)
    openai   Codex CLI (``codex exec``) com o login ChatGPT: prosa; os conectores dependem do spike do Codex
             (docs/spike-codex.md) e, até lá, qualquer chamada de conector é recusada com o motivo

Qual vale, nesta ordem: ``GP_PROVEDOR``; o campo ``provedor`` de ``jobs/instalacao.json`` (gravado por
``install.sh --provedor``); ``claude``. Cada CLI oficial cuida do próprio login: o app nunca lê, copia nem
guarda credencial de nenhum dos dois (docs de compliance do Claude Code; ``~/.codex/auth.json`` é senha).
Provedor novo = uma linha em ``PROVEDORES`` + um módulo com ``prosa`` registrado em ``ia.MODULOS``.
"""

from __future__ import annotations

import json
import os
from typing import NamedTuple

from goalpacer import base
from goalpacer.base import EXIT_VALIDACAO, GpErro

ENV_PROVEDOR = "GP_PROVEDOR"
PADRAO = "claude"


class Provedor(NamedTuple):
    nome: str
    rotulo: str  # como aparece nas mensagens
    conectores: bool  # Calendar, Gmail, Notion e Drive pelo login deste provedor


PROVEDORES = {
    "claude": Provedor("claude", "Claude Code", conectores=True),
    "openai": Provedor("openai", "Codex", conectores=False),  # True quando o spike do Codex passar
}


def por_nome(nome: str) -> Provedor:
    try:
        return PROVEDORES[nome.strip().lower()]
    except KeyError:
        raise GpErro(
            EXIT_VALIDACAO, "provedor desconhecido %r: use %s" % (nome, " ou ".join(sorted(PROVEDORES)))
        ) from None


def ativo() -> Provedor:
    return por_nome(os.environ.get(ENV_PROVEDOR) or _da_instalacao() or PADRAO)


def _da_instalacao() -> str:
    try:
        registro = json.loads((base.jobs_dir() / base.NOME_INSTALACAO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    valor = registro.get("provedor") if isinstance(registro, dict) else None
    return valor if isinstance(valor, str) else ""


def exigir_conectores(operacao: str) -> None:
    """Recusa a chamada de conector quando o provedor da instalação ainda não tem conectores."""
    atual = ativo()
    if not atual.conectores:
        raise GpErro(
            EXIT_VALIDACAO,
            "%s pelo %s depende do spike dos conectores; hoje só a prosa usa o %s"
            % (operacao, atual.rotulo, atual.rotulo),
        )
