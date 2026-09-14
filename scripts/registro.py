#!/usr/bin/env python3
"""registro.py ver | checkin | progresso | recuperar | lock | unlock: única via de escrita em registro.json.

Os modos (checkin.py, diario.py) chamam ``goalpacer.registro`` direto; este
CLI serve à skill e ao usuário para consultas e correções pontuais::

    registro.py ver [--json]                        imprime o registro
    registro.py checkin <task_id> <estado> [--origem confirmado] [--duracao-real-h 1.5] [--meta M01 --duracao-h 1]
    registro.py progresso <M<nn>> <pct>             progresso declarado (0 a 100)
    registro.py recuperar                           restaura registro.json (e os registro-AAAA.json) do .bak
    registro.py arquivar [--dias 120]               move anos anteriores para registro-AAAA.json (o job faz sozinho)
    registro.py lock [--espera-min N] | unlock      lock único da pasta (jobs e modos interativos)

Códigos: 0 ok; 2 transição recusada (inferido sobre confirmado); 3 inválido; 4 IO/lock.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, io as gpio, registro as reg, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro


def _parser() -> argparse.ArgumentParser:
    parser = cli.parser_base("registro.json do Goal Pacer: ver, checkin, progresso, recuperar, lock")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("ver")
    p_c = sub.add_parser("checkin")
    p_c.add_argument("task_id")
    p_c.add_argument("estado", choices=schema.ESTADOS)
    p_c.add_argument("--origem", choices=schema.ORIGENS, default="confirmado")
    p_c.add_argument("--duracao-real-h", dest="duracao_real_h", type=float, default=None)
    p_c.add_argument("--meta", default=None, help="com --duracao-h, grava também em feitas[meta] quando estado = feita")
    p_c.add_argument("--duracao-h", dest="duracao_h", type=float, default=None)
    p_p = sub.add_parser("progresso")
    p_p.add_argument("meta")
    p_p.add_argument("pct", type=float)
    sub.add_parser("recuperar")
    p_a = sub.add_parser("arquivar")
    p_a.add_argument("--dias", type=int, default=reg.DIAS_ANTES_DE_ARQUIVAR)
    p_l = sub.add_parser("lock")
    p_l.add_argument("--espera-min", dest="espera_min", type=float, default=0)
    sub.add_parser("unlock")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    try:
        cli.aplicar_args_base(args)
        return COMANDOS[args.comando](args, base.data_dir())
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo


def _recuperar(_args: argparse.Namespace, dados: Path) -> int:
    restaurados = [p.name for p in [reg.caminho(dados), *reg.caminhos_anuais(dados)] if gpio.recuperar(p)]
    if not restaurados:
        print("nada a restaurar (sem .bak válido ou arquivos íntegros)", file=sys.stderr)
        return EXIT_ESTADO
    print("restaurado do .bak: %s" % ", ".join(restaurados), file=sys.stderr)
    return EXIT_OK


def _arquivar(args: argparse.Namespace, dados: Path) -> int:
    trava = reg.lock(dados)
    try:
        contagem = reg.arquivar(dados, dias=args.dias)
    finally:
        trava.liberar()
    if args.json:
        sys.stdout.write(json.dumps({str(ano): n for ano, n in contagem.items()}) + "\n")
    else:
        linha = "; ".join("registro-%d.json: +%d" % par for par in contagem.items()) if contagem else "nada a arquivar"
        print(linha, file=sys.stderr)
    return EXIT_OK


def _lock(args: argparse.Namespace, dados: Path) -> int:
    trava = gpio.Lock(dados / reg.NOME_LOCK, espera_s=args.espera_min * 60)
    trava.adquirir()  # sem liberar: o lock fica até o `unlock`
    print("lock adquirido: %s" % trava.path, file=sys.stderr)
    return EXIT_OK


def _unlock(_args: argparse.Namespace, dados: Path) -> int:
    path = dados / reg.NOME_LOCK
    if path.exists():
        path.unlink()
        print("lock liberado", file=sys.stderr)
    return EXIT_OK


def _ver(_args: argparse.Namespace, dados: Path) -> int:
    sys.stdout.write(json.dumps(reg.carregar(dados), ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK


def _checkin(args: argparse.Namespace, dados: Path) -> int:
    registro = reg.carregar(dados)
    if not reg.registrar_checkin(registro, args.task_id, args.estado, args.origem, duracao_real_h=args.duracao_real_h):
        print("transição recusada: %s já está confirmado" % args.task_id, file=sys.stderr)
        return EXIT_ESTADO
    if args.estado != "feita":
        reg.remover_feita(registro, args.task_id)
    elif args.meta and args.duracao_h is not None:
        reg.registrar_feita(
            registro, args.meta, args.task_id, args.duracao_h, args.origem, duracao_real_h=args.duracao_real_h
        )
    reg.salvar(registro, dados)
    if args.json:
        sys.stdout.write(json.dumps(registro["checkins"][args.task_id], ensure_ascii=False) + "\n")
    return EXIT_OK


def _progresso(args: argparse.Namespace, dados: Path) -> int:
    registro = reg.carregar(dados)
    reg.declarar_progresso(registro, args.meta, args.pct)
    reg.salvar(registro, dados)
    return EXIT_OK


COMANDOS = {
    "recuperar": _recuperar,
    "arquivar": _arquivar,
    "lock": _lock,
    "unlock": _unlock,
    "ver": _ver,
    "checkin": _checkin,
    "progresso": _progresso,
}


if __name__ == "__main__":
    raise SystemExit(main())
