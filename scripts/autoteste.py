#!/usr/bin/env python3
"""autoteste.py [--json]: prova, sem conectores e sem tokens, que este código roda nesta máquina.

    python3 >= 3.9 -> importa todos os CLIs -> pasta de exemplo numa pasta temporária
    (demo_painel: mensal e diário offline, relógio fixo) -> validar grafo -> email das 7h
    -> status -> painel -> strings de cada idioma -> apaga a pasta temporária

Nunca lê nem escreve ``~/.goal-pacer``: raiz, dados e agenda são temporários e o processo
é descartável. ``install.sh --update`` roda o autoteste do código novo antes de trocar os
jobs: exit 0 segue, exit 3 volta o app para a versão anterior. Também serve para quem
instala conferir a máquina: ``goal-pacer autoteste``.
"""

from __future__ import annotations

import argparse
import functools
import importlib
import json
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import copy
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO

CLIS = (
    "balanco",
    "checkin",
    "diario",
    "instalar",
    "mensal",
    "metas",
    "migrar",
    "onboarding",
    "painel",
    "parse_whatsapp",
    "perfil",
    "registro",
    "semanal",
    "status",
    "validar",
    "web",
)
VERSAO_MINIMA = (3, 9)


def _passos(pasta: Path) -> list[tuple[str, Callable[[], Any]]]:
    """Cada passo recebe a pasta temporária e o estado compartilhado (o exemplo grava ``dados``)."""
    estado: dict[str, Any] = {}
    return [(nome, functools.partial(passo, pasta, estado)) for nome, passo in PASSOS]


def _passo_python(_pasta: Path, _estado: dict[str, Any]) -> None:
    if tuple(sys.version_info[:2]) < VERSAO_MINIMA:
        raise RuntimeError("python3 %d.%d; use 3.9 ou mais novo" % sys.version_info[:2])


def _passo_modulos(_pasta: Path, _estado: dict[str, Any]) -> None:
    for nome in CLIS:
        importlib.import_module(nome)


def _passo_exemplo(pasta: Path, estado: dict[str, Any]) -> None:
    import demo_painel

    estado["dados"] = demo_painel.preparar(pasta)


def _passo_grafo(_pasta: Path, estado: dict[str, Any]) -> None:
    import validar

    resultado = validar.validar_grafo(estado["dados"])
    if resultado.erros:
        raise RuntimeError(resultado.erros[0])


def _passo_email(_pasta: Path, estado: dict[str, Any]) -> None:
    import diario

    assunto, texto, html = diario.montar_email(estado["dados"], date(2026, 9, 28))
    if not assunto.startswith("[goal-pacer] ") or not texto.strip() or "<table" not in html:
        raise RuntimeError("email das 7h incompleto")


def _passo_status_e_painel(_pasta: Path, estado: dict[str, Any]) -> None:
    import painel
    import status
    from goalpacer import clock

    agora = clock.agora()
    if not status.render_status(status.coletar(estado["dados"], agora)).strip():
        raise RuntimeError("status vazio")
    if painel.modelo(estado["dados"], agora).get("tela") != "hoje":
        raise RuntimeError("modelo do painel sem a tela Hoje")


def _passo_idiomas(_pasta: Path, _estado: dict[str, Any]) -> None:
    padrao = set(copy.carregar(copy.IDIOMA_PADRAO))
    for idioma in copy.disponiveis():
        faltam = padrao - set(copy.carregar(idioma))
        if faltam:
            raise RuntimeError("copy.%s.md sem %s" % (idioma, min(faltam)))


PASSOS = (
    ("python", _passo_python),
    ("modulos", _passo_modulos),
    ("exemplo", _passo_exemplo),
    ("grafo", _passo_grafo),
    ("email", _passo_email),
    ("status_e_painel", _passo_status_e_painel),
    ("idiomas", _passo_idiomas),
)


def rodar() -> dict[str, Any]:
    inicio = time.monotonic()
    temporaria = Path(tempfile.mkdtemp(prefix="gp-autoteste-"))
    feitos: list[str] = []
    erro: Optional[str] = None
    try:
        for nome, passo in _passos(temporaria):
            try:
                passo()
            except Exception as falha:  # noqa: BLE001 - qualquer falha reprova a versão
                erro = "%s: %s: %s" % (nome, type(falha).__name__, falha)
                break
            feitos.append(nome)
    finally:
        shutil.rmtree(str(temporaria), ignore_errors=True)
    return {
        "ok": erro is None,
        "passos": feitos,
        "erro": erro,
        "duracao_s": round(time.monotonic() - inicio, 1),
        "python": "%d.%d.%d" % sys.version_info[:3],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="confere, sem conectores e sem tokens, que o código roda nesta máquina"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    resultado = rodar()
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False))
    elif resultado["ok"]:
        segundos = str(resultado["duracao_s"]).replace(".", copy.texto("calendario.decimal"))
        print(
            copy.texto(
                "instalar.autoteste_ok", n=len(resultado["passos"]), segundos=segundos, python=resultado["python"]
            )
        )
    else:
        print(copy.texto("instalar.autoteste_erro", erro=resultado["erro"]), file=sys.stderr)
    return EXIT_OK if resultado["ok"] else EXIT_VALIDACAO


if __name__ == "__main__":
    raise SystemExit(main())
