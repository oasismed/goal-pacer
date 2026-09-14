#!/usr/bin/env python3
"""migrar.py [--aplicar | --simular] [--json]: leva a pasta de dados ao esquema deste app.

Sem flag só confere: exit 0 com a pasta em dia (ou sem onboarding), exit 3 quando falta
migrar ou não há caminho (pasta mais nova que o app, versões misturadas, migração
ausente). ``--simular`` mostra os passos sem tocar em nada. ``--aplicar`` pega o lock
da pasta, faz o backup zip em ``backups/``, aplica e confere com o código novo; se algo
falhar, a pasta volta ao backup e o exit é 3. ``install.sh --update`` chama ``--aplicar``
antes de recarregar os jobs. As regras estão em ``goalpacer/migracoes.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validar
from goalpacer import base, cli, migracoes, registro as reg, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro


def conferir_depois_da_migracao(dados: Path) -> None:
    """Grafo e registro lidos com o código novo; qualquer erro desfaz a migração (``migracoes.migrar``)."""
    grafo = validar.validar_grafo(dados)
    if grafo.erros:
        raise GpErro(
            EXIT_ESTADO if grafo.codigo_forcado == EXIT_ESTADO else EXIT_VALIDACAO,
            "grafo inválido depois da migração: %s" % grafo.erros[0],
        )
    reg.carregar(dados)


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("leva a pasta de dados ao esquema deste app (backup antes, volta atrás se falhar)")
    parser.add_argument("--json", action="store_true")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--aplicar", action="store_true", help="migra com backup e conferência")
    modo.add_argument("--simular", action="store_true", help="mostra os passos sem mudar nada")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        if args.aplicar:
            trava = reg.lock(dados)
            try:
                resultado = migracoes.migrar(dados, conferir=conferir_depois_da_migracao)
            finally:
                trava.liberar()
        else:
            resultado = migracoes.migrar(dados, simular=True, conferir=conferir_depois_da_migracao)
            if not args.simular and resultado["passos"]:
                resultado["estado"] = "pendente"
    except GpErro as erro:
        if args.json:
            sys.stdout.write(json.dumps({"ok": False, "erro": erro.mensagem}, ensure_ascii=False) + "\n")
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    if args.json:
        sys.stdout.write(migracoes.resumo_json(dict(resultado, ok=resultado["estado"] != "pendente")) + "\n")
    elif resultado["estado"] in ("em_dia", "sem_onboarding"):
        print("esquema v%d: nada a migrar" % schema.SCHEMA_VERSION)
    else:
        print("\n".join(resultado["passos"]))
        if resultado["estado"] == "pendente":
            print(
                "a pasta de dados está na v%d; rode ./install.sh --update (ou migrar.py --aplicar) para chegar à v%d"
                % (resultado["de"], resultado["para"])
            )
        elif resultado["estado"] == "migrado":
            print("migrado para a v%d; backup em %s" % (resultado["para"], resultado["backup"]))
    return EXIT_VALIDACAO if resultado["estado"] == "pendente" else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
