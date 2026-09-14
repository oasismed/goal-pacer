"""Regras de tom verificáveis por script (design 3.1, 1.2; references/regras.md).

Toda superfície que o usuário lê (email, status, plano, blocos, prosa do
modelo) passa por ``violacoes``: palavras proibidas (culpa, cobrança), o
padrão "N de M" (placar), "pendente há N dias" e o travessão longo. As
palavras e o conector do placar vêm do grupo ``tom`` do copy de cada idioma
(``copy.<idioma>.md``), então um idioma novo traz as próprias regras.
``normalizar`` troca o travessão da prosa do modelo por vírgula antes do lint.
Prosa do modelo que viola é trocada pelo template determinístico; texto de
template que viola é bug (teste).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional, Pattern

from goalpacer import copy

TRAVESSAO = "\u2014"  # em dash: fora de toda superfície (AGENTS.md)
RE_TRAVESSAO_ESPACADO = re.compile(r"\s*\u2014\s*")


@lru_cache(maxsize=8)
def regras(idioma: str) -> tuple[Pattern[str], ...]:
    """Regex de palavras proibidas, "pendente há N dias" e placar "N de M" do idioma."""
    palavras = copy.lista("tom.palavras_proibidas", idioma)
    proibidas = re.compile(r"(?<!\w)(%s)(?!\w)" % "|".join(re.escape(p) for p in palavras), re.IGNORECASE)
    pendentes = [
        re.escape(frase).replace(re.escape("{n}"), r"\d+") + "s?" for frase in copy.lista("tom.pendente_ha", idioma)
    ]
    pendente = re.compile("(%s)" % "|".join(pendentes), re.IGNORECASE)
    conector = re.escape(copy.texto("tom.placar", idioma).strip())
    placar = re.compile(r"(?<![\w/])\d+\s+%s\s+\d+(?![\w/%%])" % conector)
    return proibidas, pendente, placar


def violacoes(texto: str, idioma: Optional[str] = None) -> list[str]:
    """Trechos que violam o tom (vazio = ok), em ordem de aparição."""
    achados: list[str] = []
    for regex in regras(idioma or copy.atual()):
        achados.extend(m.group(0) for m in regex.finditer(texto))
    achados.extend(TRAVESSAO for _ in range(texto.count(TRAVESSAO)))
    return achados


def normalizar(texto: str) -> str:
    """Conserto mecânico de prosa do modelo antes do lint: travessão vira vírgula.

    Só pontuação; palavras proibidas continuam levando ao template."""
    if TRAVESSAO not in texto:
        return texto
    limpo = RE_TRAVESSAO_ESPACADO.sub(", ", texto)
    return re.sub(r",\s*([,.;:!?])", r"\1", limpo).strip(" ,")


def ok(texto: str, idioma: Optional[str] = None) -> bool:
    return not violacoes(texto, idioma)
