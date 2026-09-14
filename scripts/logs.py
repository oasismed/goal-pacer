#!/usr/bin/env python3
"""logs.py resumo | eventos | trace: lê, sem gravar nada, os registros locais do Goal Pacer (``goal-pacer logs``).

    resumo  [--dias 7]                 tempo por tela do painel e por ferramenta de conector (p50, p95, máximo),
                                       chamadas repetidas, erros de tela, tamanhos da pasta de dados e alertas
    eventos [--dias 1] [--tipo T]      as últimas linhas de eventos-*.jsonl (painel, painel_erro, erro_front, log, alerta)
    trace   [RUN_ID | ultimo]          os spans de um job em árvore (job > passo > conector), com o tempo de cada um

Todos aceitam ``--json``. É a porta de leitura para quem diagnostica, pessoa ou agente: nenhuma
credencial, nenhum conector, nenhum dado de terceiros (a telemetria não guarda conteúdo).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, clock, copy, registro as reg, saude, telemetria
from goalpacer.base import EXIT_ESTADO, EXIT_OK, GpErro

TETO_EVENTOS = 200


def _arvore(spans: list[dict[str, Any]]) -> list[str]:
    filhos: dict[Optional[str], list[dict[str, Any]]] = {}
    ids = {s.get("span_id") for s in spans}
    for s in spans:
        pai = s.get("pai") if s.get("pai") in ids else None
        filhos.setdefault(pai, []).append(s)
    linhas: list[str] = []

    def descer(pai: Optional[str], nivel: int) -> None:
        for s in filhos.get(pai, []):
            detalhe = s.get("passo") or s.get("ferramenta") or s.get("modo") or ""
            extra = (
                ""
                if s.get("codigo") in (None, 0)
                else " (exit %s%s)" % (s.get("codigo"), ", " + s["classe"] if s.get("classe") else "")
            )
            tentativa = " tentativa %s" % s["tentativa"] if (s.get("tentativa") or 1) > 1 else ""
            linhas.append(
                "%s%s %s  %.1f s%s%s"
                % ("  " * nivel, s.get("nome"), detalhe, float(s.get("ms") or 0) / 1000.0, tentativa, extra)
            )
            descer(s.get("span_id"), nivel + 1)

    descer(None, 0)
    return linhas


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("lê os registros locais: resumo, eventos ou trace de um job")
    parser.add_argument("comando", nargs="?", default="resumo", choices=("resumo", "eventos", "trace"))
    parser.add_argument("alvo", nargs="?", default="ultimo", help="com trace: o run_id do job ou ultimo")
    parser.add_argument("--dias", type=int, default=None)
    parser.add_argument("--tipo", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    if telemetria.pasta() is None:
        print(copy.texto("logs.sem_registros"), file=sys.stderr)
        return EXIT_ESTADO
    {"trace": _trace, "eventos": _eventos, "resumo": _resumo}[args.comando](args)
    return EXIT_OK


def _trace(args: argparse.Namespace) -> None:
    alvo = telemetria.ultimo_trace() if args.alvo == "ultimo" else args.alvo
    spans = telemetria.trace(alvo) if alvo else []
    if args.json:
        print(json.dumps({"trace_id": alvo, "spans": spans}, ensure_ascii=False))
    elif not spans:
        print(copy.texto("logs.sem_trace"))
    else:
        print(copy.texto("logs.titulo_trace", trace=alvo))
        print("\n".join(_arvore(spans)))


def _eventos(args: argparse.Namespace) -> None:
    dias = args.dias if args.dias is not None else 1
    lidos = telemetria.ler("eventos-*.jsonl", dias=dias)
    itens = [e for e in lidos if args.tipo is None or e.get("tipo") == args.tipo][-TETO_EVENTOS:]
    if args.json:
        print(json.dumps({"dias": dias, "eventos": itens}, ensure_ascii=False))
        return
    for e in itens:
        campos = " ".join("%s=%s" % (k, v) for k, v in e.items() if k not in ("ts", "tipo") and v not in (None, ""))
        print("%s %s %s" % (e.get("ts"), e.get("tipo"), campos))
    if not itens:
        print(copy.texto("logs.sem_eventos", dias=dias))


def _resumo(args: argparse.Namespace) -> None:
    dias = args.dias if args.dias is not None else saude.JANELA_DIAS
    dados = base.data_dir()
    resumo = telemetria.resumo(dias)
    metricas = saude.metricas(dados) if dados.is_dir() else {}
    alertas = _alertas(dados) if dados.is_dir() else []
    if args.json:
        print(json.dumps({"resumo": resumo, "metricas": metricas, "alertas": alertas}, ensure_ascii=False))
        return
    print(copy.texto("logs.titulo_resumo", dias=dias))
    for titulo, grupo in (
        (copy.texto("logs.titulo_painel"), resumo["painel"]),
        (copy.texto("logs.titulo_conectores"), resumo["conectores"]),
    ):
        print()
        print(titulo)
        if not grupo:
            print("  " + copy.texto("logs.nada_medido"))
        for nome, linha in grupo.items():
            print(
                "  %-34s %5d  p50 %8.1f ms  p95 %8.1f ms  máx %8.1f ms"
                % (nome, linha["n"], linha["p50_ms"], linha["p95_ms"], linha["max_ms"])
            )
    print()
    chamadas = resumo["chamadas"]
    print(
        copy.texto(
            "logs.linha_chamadas",
            total=chamadas["total"],
            repetidas=chamadas["repetidas"],
            erros_front=resumo["erros_front"],
            erros_painel=resumo["erros_painel"],
        )
    )
    if metricas:
        linha = copy.texto(
            "logs.linha_dados", registro=metricas["registro_kb"], dias=metricas["dias"], logs=metricas["logs_kb"]
        )
        print(linha)
    for alerta in alertas:
        print("- " + alerta["texto"])


def _alertas(dados: Path) -> list[dict[str, Any]]:
    try:
        return saude.alertas(dados, clock.agora(), reg.carregar(dados))
    except GpErro:
        return []


if __name__ == "__main__":
    raise SystemExit(main())
