#!/usr/bin/env python3
"""perfil.py: recalcula perfil.json a partir de registro.json, metas/ e dias/ (única via de escrita).

    perfil.py [--json] [--nao-gravar]

Determinístico: só blocos confirmados e sinais explícitos entram nos pesos
(``goalpacer.perfil``). Exit 0 ok; 2 sem onboarding; 3 inválido; 4 IO.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, copy, perfil as prf
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("recalcula perfil.json (progresso, ritmo, janelas, fator de duração)")
    parser.add_argument("--json", action="store_true", help="imprime o perfil calculado")
    parser.add_argument("--nao-gravar", dest="nao_gravar", action="store_true", help="só calcula")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        if not (dados / "contexto.md").exists():
            print(
                copy.texto("falhas.semonboarding_motivo") + ": " + copy.texto("falhas.semonboarding_acao"),
                file=sys.stderr,
            )
            return EXIT_ESTADO
        perfil = prf.calcular(dados)
        if not args.nao_gravar:
            prf.gravar(dados, perfil)
        if args.json:
            sys.stdout.write(json.dumps(perfil, ensure_ascii=False, indent=2) + "\n")
        else:
            for id_meta, item in perfil["metas"].items():
                print(
                    copy.texto(
                        "perfil_cli.linha_meta",
                        meta=id_meta,
                        progresso="%.0f" % item["progresso_pct"],
                        presumido="%.0f" % item["progresso_presumido_pct"],
                        ritmo="%.0f" % item["ritmo_esperado_pct"],
                    )
                )
            print("perfil baseado em %d confirmadas" % perfil["n_confirmadas"])
        return EXIT_OK
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo or EXIT_VALIDACAO


if __name__ == "__main__":
    raise SystemExit(main())
