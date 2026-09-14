"""goalpacer: pacote stdlib do Goal Pacer (Python 3.9+).

Módulos: base (raízes, códigos de saída, log), clock (única fonte de
"agora"), frontmatter (subconjunto plano de YAML), io (escrita atômica,
.bak, lock), schema (fonte única do esquema) e proxy (proxy MCP burro e
prosa via ``claude -p``).

O pacote tem nome longo de propósito: um nome curto como ``gc`` seria
sombreado pelo módulo embutido ``gc`` do Python. Os CLIs em ``scripts/*.py``
inserem ``scripts/`` no ``sys.path`` e fazem ``import goalpacer``.

``SCHEMA_VERSION`` é reexportado de ``schema`` sob demanda (PEP 562): o
import do pacote não carrega ``schema``, e ``python3 -m goalpacer.schema``
não dispara o RuntimeWarning de módulo já presente em ``sys.modules``.

No Windows o Python não traz a base de fusos IANA: o instalador põe o ``tzdata`` em ``<raiz>/vendor`` e o import do
pacote acrescenta essa pasta ao ``sys.path`` (a raiz de quem roda a partir de ``app/scripts``, ou ``GP_RAIZ``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

__version__ = "0.1.0"


def _pastas_vendor() -> list[str]:
    candidatas = [Path(__file__).resolve().parents[3] / "vendor"]
    from goalpacer import base

    candidatas.append(base.raiz() / "vendor")
    return [str(p) for p in candidatas if p.is_dir()]


if os.name == "nt":  # pragma: no cover - só no Windows
    sys.path.extend(p for p in _pastas_vendor() if p not in sys.path)

__all__ = ["SCHEMA_VERSION", "__version__"]


def __getattr__(nome: str) -> Any:
    if nome == "SCHEMA_VERSION":
        from goalpacer.schema import SCHEMA_VERSION

        return SCHEMA_VERSION
    raise AttributeError("module 'goalpacer' has no attribute %r" % (nome,))
