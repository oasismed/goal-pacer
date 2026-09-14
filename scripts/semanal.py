#!/usr/bin/env python3
"""semanal.py: refaz o balanço do mês da semana de hoje e os espelhos semanas/*.md (sem ler as fontes).

Sob demanda (/goal-pacer semanal) e automaticamente no diário de segunda
(``run_job.py``). Mantém a prosa existente; só preenche blocos vazios.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mensal


def main(argv: Optional[list[str]] = None) -> int:
    return mensal.executar_cli(
        argv,
        descricao="balanço da semana: refaz números e espelhos sem ler as fontes",
        modo="semanal",
        com_evidencias_padrao=False,
        manter_prosa_padrao=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
