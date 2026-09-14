#!/usr/bin/env python3
"""metas.py ajustar <M<nn>> [--custo H] [--semanas N] [--prazo AAAA-MM-DD] [--prazo-externo sim|nao] [--estado E] [--confianca C]

Única via da skill para mudar uma meta existente (decisões, recalibração,
arquivar). Valida contra o esquema e grava atômico; mudança de custo sem
``--confianca`` vira ``confianca: usuario``. Exit 0 ok (mesmo sem mudança); 3 inválido; 4 lock.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, metas, registro as reg, schema
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("ajusta uma meta existente (custo, prazo, estado) com validação")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="comando")
    p = sub.add_parser("ajustar")
    p.add_argument("meta")
    p.add_argument("--custo", type=float, default=None)
    p.add_argument("--semanas", type=int, default=None)
    p.add_argument("--prazo", type=date.fromisoformat, default=None)
    p.add_argument("--prazo-externo", dest="prazo_externo", choices=("sim", "nao"), default=None)
    p.add_argument("--estado", choices=schema.ESTADOS_META, default=None)
    p.add_argument("--confianca", choices=schema.CONFIANCAS, default=None)
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    trava = None
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        trava = reg.lock(dados)
        mudancas = {
            "custo_h_semana_escolhido": args.custo,
            "semanas_pesquisa": args.semanas,
            "prazo": args.prazo,
            "prazo_externo": None if args.prazo_externo is None else args.prazo_externo == "sim",
            "estado": args.estado,
            "confianca": args.confianca,
        }
        feito = metas.ajustar(dados, args.meta, {k: v for k, v in mudancas.items() if v is not None})
        if args.json:
            sys.stdout.write(json.dumps({"meta": args.meta, "mudancas": feito}, ensure_ascii=False) + "\n")
        else:
            print(
                "%s: %s"
                % (args.meta, ", ".join("%s de %s para %s" % (c, a, b) for c, (a, b) in feito.items()) or "nada mudou")
            )
        return EXIT_OK
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    finally:
        if trava is not None:
            trava.liberar()


if __name__ == "__main__":
    raise SystemExit(main())
