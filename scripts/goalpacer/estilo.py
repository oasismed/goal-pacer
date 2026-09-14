"""Tokens de ``references/estilo.md`` (design 5.1): a única fonte de valores de estilo.

Formato: seção ``## tokens`` com linhas ``- chave: valor``. Token pedido e
ausente é ``GpErro`` (o arquivo de estilo está incompleto).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from goalpacer.base import EXIT_VALIDACAO, GpErro

RE_TOKEN = re.compile(r"^- ([a-z][a-z0-9_]*): (.+)$")


def caminho() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "references" / "estilo.md"


@lru_cache(maxsize=1)
def tokens() -> dict[str, str]:
    texto = caminho().read_text(encoding="utf-8")
    saida: dict[str, str] = {}
    dentro = False
    for linha in texto.split("\n"):
        if linha.startswith("## "):
            dentro = linha.strip() == "## tokens"
            continue
        if dentro:
            m = RE_TOKEN.match(linha.rstrip())
            if m:
                saida[m.group(1)] = m.group(2).strip()
    return saida


def token(nome: str) -> str:
    valores = tokens()
    if nome not in valores:
        raise GpErro(EXIT_VALIDACAO, "token de estilo %r não existe em references/estilo.md" % nome)
    return valores[nome]


def inteiro(nome: str) -> int:
    return int(re.sub(r"[^0-9]", "", token(nome)))
