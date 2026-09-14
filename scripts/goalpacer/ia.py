"""Ponto único da prosa do app: o prompt vai para o provedor da instalação (``goalpacer/provedor.py``).

    ia.prosa(prompt, modelo="haiku", curta=True)  ->  proxy.prosa (claude -p)  ou  codex.prosa (codex exec)

Os apelidos de modelo são os do Claude (``haiku``, ``sonnet``); o Codex os traduz em esforço de raciocínio.
O módulo é buscado na hora da chamada (os testes trocam ``proxy.prosa`` pelo monkeypatch).
"""

from __future__ import annotations

from typing import Optional

from goalpacer import codex, provedor, proxy

MODULOS = {"claude": proxy, "openai": codex}


def prosa(
    prompt: str,
    *,
    modelo: str = "haiku",
    curta: bool = True,
    executar: Optional[proxy.Executar] = None,
    registro: proxy.Registro = None,
) -> str:
    modulo = MODULOS[provedor.ativo().nome]
    return modulo.prosa(prompt, modelo=modelo, curta=curta, executar=executar, registro=registro)
