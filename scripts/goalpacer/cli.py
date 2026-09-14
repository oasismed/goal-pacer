"""cli.py: os argumentos comuns a todos os CLIs (``--agora``, ``--tz``, ``--offline``, ``--dados``, ``--idioma``,
``--run-id``) e a aplicação deles ao processo. Todo CLI nasce de ``cli.parser_base(descricao)`` e chama
``cli.aplicar_args_base(args)`` logo depois do ``parse_args``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from goalpacer import base, clock, copy, plataforma


def parser_base(descricao: str) -> argparse.ArgumentParser:
    """ArgumentParser com os argumentos comuns a todos os CLIs.

    Já inclui ``--agora`` e ``--tz`` (via ``clock.adicionar_args_relogio``),
    ``--offline``, ``--dados`` (sobrepõe ``GP_DATA_DIR``) e ``--run-id``
    (sobrepõe ``GP_RUN_ID``). O CLI chama ``aplicar_args_base(args)`` depois
    do ``parse_args`` (ela aplica ``--dados``/``--run-id`` ao ambiente e chama
    ``clock.aplicar_args_relogio``).
    """
    parser = argparse.ArgumentParser(description=descricao)
    clock.adicionar_args_relogio(parser)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="não chama claude -p nem conectores; usa fixtures e cache locais",
    )
    parser.add_argument(
        "--dados",
        type=Path,
        default=None,
        metavar="PASTA",
        help="pasta de dados (sobrepõe %s)" % base.ENV_DATA_DIR,
    )
    parser.add_argument(
        "--idioma",
        default=None,
        metavar="IDIOMA",
        help="idioma das superfícies (pt-BR, en); sem ele vale o de contexto.md",
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        default=None,
        metavar="ID",
        help="identificador da execução para o log (sobrepõe %s)" % base.ENV_RUN_ID,
    )
    return parser


def aplicar_args_base(args: argparse.Namespace) -> None:
    """Aplica os argumentos comuns depois do ``parse_args``.

    ``--dados`` vira ``GP_DATA_DIR`` (absoluto, sem resolver symlinks, para
    que subprocessos com outro cwd vejam a mesma pasta; em Desktop,
    Downloads ou Documents é ``GpErro(base.EXIT_VALIDACAO)``, AGENTS.md) e
    ``--run-id`` vira ``GP_RUN_ID`` no ambiente do processo (assim os
    subprocessos, proxies e hooks herdam); depois delega a
    ``clock.aplicar_args_relogio(args)``. Argumentos ausentes no namespace
    são ignorados.
    """
    dados = getattr(args, "dados", None)
    if dados:
        pasta = Path(os.path.abspath(Path(dados).expanduser()))
        if plataforma.dir_tcc_proibido(pasta):
            raise base.GpErro(
                base.EXIT_VALIDACAO,
                "pasta de dados não pode ficar em %s: %s" % ("/".join(plataforma.PASTAS_TCC), pasta),
            )
        os.environ[base.ENV_DATA_DIR] = str(pasta)
    run_id = getattr(args, "run_id", None)
    if run_id:
        os.environ[base.ENV_RUN_ID] = str(run_id)
    idioma = getattr(args, "idioma", None)
    if idioma:
        if idioma not in copy.disponiveis():
            raise base.GpErro(
                base.EXIT_VALIDACAO,
                "idioma %r sem references/copy.%s.md; disponíveis: %s"
                % (idioma, idioma, ", ".join(copy.disponiveis())),
            )
        os.environ[copy.ENV_IDIOMA] = idioma
    clock.aplicar_args_relogio(args)
