"""Respostas de fixture para o modo ``--offline`` (eng 6.1).

Com ``--offline`` nenhum CLI chama ``claude -p`` nem conectores: as
respostas dos proxies vêm de arquivos na pasta ``GP_OFFLINE_DIR`` (por
padrão ``tests/fixtures/offline/`` do repo), um JSON por tool, com o nome
da tool sem o prefixo do servidor (``list_calendars.json``,
``search_threads.json``) e ``mcp_list.txt`` para ``claude mcp list``.
Quando a chamada tem ``calendarId`` (ou ``eventId``), procura antes
``<tool>--<valor sanitizado>.json`` (ex.:
``list_events--metas-fixture_group.calendar.google.com.json``), para que
Metas e primário tenham fixtures próprias. Arquivo ausente = resposta
vazia (``{}`` ou ``""``): o modo offline nunca falha por falta de fixture,
só devolve menos dados. As fixtures têm a forma CRUA do conector (a
projeção de privacidade roda igual ao caminho vivo).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from goalpacer.base import EXIT_VALIDACAO, GpErro

ENV_OFFLINE_DIR = "GP_OFFLINE_DIR"
CHAVES_DISCRIMINANTES = ("calendarId", "calendar_id", "eventId", "event_id", "messageId")
RE_SANITIZAR = re.compile(r"[^A-Za-z0-9._-]")


def pasta() -> Path:
    valor = os.environ.get(ENV_OFFLINE_DIR, "")
    if valor:
        return Path(valor).expanduser()
    return Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "offline"


def _nome_curto(tool: str) -> str:
    return tool.rsplit("__", 1)[-1]


def sanitizar(valor: str) -> str:
    return RE_SANITIZAR.sub("_", valor)


def candidatos(tool: str, args: Optional[dict[str, Any]] = None) -> list[str]:
    curto = _nome_curto(tool)
    nomes = [
        "%s--%s.json" % (curto, sanitizar(str(args[chave])))
        for chave in CHAVES_DISCRIMINANTES
        if args and args.get(chave)
    ]
    nomes.append(curto + ".json")
    return nomes


def resposta(tool: str, args: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Conteúdo da primeira fixture que existir para ``tool``/``args``, ou ``{}``."""
    for nome in candidatos(tool, args):
        path = pasta() / nome
        if not path.exists():
            continue
        try:
            with open(path, encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, ValueError) as erro:
            raise GpErro(EXIT_VALIDACAO, "fixture offline inválida %s: %s" % (path, erro)) from erro
        return dados if isinstance(dados, dict) else {}
    return {}


def texto(nome: str) -> str:
    """Conteúdo de ``<nome>`` (ex.: ``mcp_list.txt``) da pasta offline, ou ``""``."""
    path = pasta() / nome
    if not path.exists():
        return ""
    with open(path, encoding="utf-8") as arquivo:
        return arquivo.read()


def chamar(tool: str, args: Optional[dict[str, Any]] = None, **_: Any) -> dict[str, Any]:
    """Mesma assinatura de ``proxy.chamar`` (argumentos extras ignorados)."""
    return resposta(tool, args)
