#!/usr/bin/env python3
"""mutacao.py: teste de mutação (mutmut) nos módulos críticos, numa cópia do último commit (docs/qualidade.md).

    uv run --no-project --with-requirements requirements-dev.txt python dev/mutacao.py
    uv run --no-project --with-requirements requirements-dev.txt python dev/mutacao.py --modulo proxy --testes tests/test_proxy.py

O mutmut 3 espera o código em ``src/`` ou na raiz; o Goal Pacer importa ``goalpacer`` de ``scripts/``. Por isso a
rodada acontece numa pasta temporária com ``scripts`` renomeado para ``src`` e o conftest apontando para lá. Nada é
gravado no repositório. Fica fora do dev/verificar.py (minutos por módulo); rode depois de mexer num módulo crítico.

Placar de referência (13/09/2026): respostas_email 365 de 379 mutantes mortos (96%); os 14 que sobram são
equivalentes (padrão que não muda o resultado, como ``texto or ""`` virar ``texto or "XXXX"``).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
MUTMUT = "mutmut==3.8.0"
PYTEST = "pytest==9.0.3"
PADRAO = ("respostas_email", ["tests/test_respostas_email.py", "tests/test_propriedades.py"])
TIMEOUT_S = 3600


def _copiar_commit(destino: Path) -> None:
    arquivo = subprocess.run(
        ["git", "-C", str(RAIZ), "archive", "HEAD"], capture_output=True, check=True, timeout=120
    ).stdout
    with tarfile.open(fileobj=BytesIO(arquivo)) as tar:
        try:
            tar.extractall(destino, filter="data")
        except TypeError:  # Python sem o filtro de extração: o tar vem do git archive do próprio repositório
            tar.extractall(destino)  # noqa: S202


def _preparar(pasta: Path, modulo: str, testes: list[str]) -> None:
    (pasta / "scripts").rename(pasta / "src")
    (pasta / "scripts").symlink_to("src")  # testes que rodam um CLI por caminho (scripts/<cli>.py) seguem achando
    conftest = pasta / "tests" / "conftest.py"
    conftest.write_text(
        conftest.read_text(encoding="utf-8").replace('RAIZ_REPO / "scripts"', 'RAIZ_REPO / "src"'), encoding="utf-8"
    )
    lista = ", ".join('"%s"' % t for t in testes)
    copiar = ", ".join('"%s"' % p.name for p in sorted(pasta.iterdir()) if p.name != "pyproject.toml")
    config = (
        "\n[tool.mutmut]\n"
        'source_paths = ["src/goalpacer/%s.py"]\n'
        "also_copy = [%s]\n"
        "pytest_add_cli_args_test_selection = [%s]\n"
        'pytest_add_cli_args = ["-p", "no:cacheprovider"]\n'
    ) % (modulo, copiar, lista)
    pyproject = pasta / "pyproject.toml"
    pyproject.write_text(pyproject.read_text(encoding="utf-8") + config, encoding="utf-8")


def _ambiente(pasta: Path) -> dict[str, str]:
    """HOME dentro da pasta da rodada: um mutante que troca o nome de ``GP_DATA_DIR`` ou ``GP_RAIZ`` faz o código cair
    no padrão ``~/.goal-pacer`` e gravaria na instalação de verdade. O cache do uv continua o de sempre."""
    casa = pasta / "home"
    casa.mkdir(exist_ok=True)
    cache = os.environ.get("UV_CACHE_DIR") or str(Path.home() / ".cache" / "uv")
    return dict(os.environ, HOME=str(casa), UV_CACHE_DIR=cache)


def _uv(pasta: Path, *argumentos: str) -> subprocess.CompletedProcess:
    uv = shutil.which("uv") or "uv"
    return subprocess.run(
        [uv, "run", "--no-project", "--with", MUTMUT, "--with", PYTEST, "mutmut", *argumentos],
        cwd=pasta,
        env=_ambiente(pasta),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )


def placar(saida_results: str) -> dict[str, int]:
    """Contagem por estado das linhas ``nome: estado`` do ``mutmut results --all true``."""
    contagem: dict[str, int] = {}
    for linha in saida_results.splitlines():
        m = re.match(r"^\s*\S+__mutmut_\d+: (\w[\w ]*)$", linha)
        if m:
            contagem[m.group(1)] = contagem.get(m.group(1), 0) + 1
    return contagem


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Teste de mutação num módulo do goalpacer (cópia do último commit).")
    parser.add_argument("--modulo", default=PADRAO[0], help="nome do módulo em scripts/goalpacer (sem .py)")
    parser.add_argument("--testes", nargs="+", default=PADRAO[1], help="arquivos de teste que exercitam o módulo")
    parser.add_argument("--sobreviventes", action="store_true", help="mostra o diff de cada mutante que sobreviveu")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="gp-mutacao-") as temporaria:
        pasta = Path(temporaria)
        _copiar_commit(pasta)
        _preparar(pasta, args.modulo, args.testes)
        rodada = _uv(pasta, "run")
        resultados = _uv(pasta, "results", "--all", "true").stdout
        contagem = placar(resultados)
        total = sum(contagem.values())
        if not total or contagem.get("not checked", 0) == total:
            print(rodada.stdout[-3000:] + rodada.stderr[-3000:], file=sys.stderr)
            return 1
        mortos = contagem.get("killed", 0) + contagem.get("timeout", 0)
        print(
            "%s: %d de %d mutantes mortos (%.0f%%) %s" % (args.modulo, mortos, total, 100.0 * mortos / total, contagem)
        )
        if args.sobreviventes:
            for linha in resultados.splitlines():
                if linha.strip().endswith(": survived"):
                    print(_uv(pasta, "show", linha.split(":")[0].strip()).stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
