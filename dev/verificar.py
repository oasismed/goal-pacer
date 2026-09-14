#!/usr/bin/env python3
"""verificar.py: os gates de qualidade do Goal Pacer, na máquina de quem desenvolve (docs/qualidade.md).

Rode com as ferramentas fixadas em ``requirements-dev.txt``::

    uv run --no-project --with-requirements requirements-dev.txt python dev/verificar.py            # tudo
    uv run --no-project --with-requirements requirements-dev.txt python dev/verificar.py --rapido   # sem testes

Etapas (todas bloqueiam; ``Etapa.bloqueia=False`` fica para uma ferramenta nova em período de observação)::

    formato       ruff format --check
    lint          ruff check
    complexidade  complexipy: teto 15 por função, catraca pelo complexipy-snapshot.json
    tipos         ty check na versão fixada (ty 0.0.x muda entre versões: subir a versão = corrigir no mesmo commit)
    codigo_morto  vulture com a lista de usos que ele não enxerga (dev/vulture_permitidos.py)
    shell         shellcheck nos scripts shell
    front         Biome (lint do JavaScript e do CSS do painel, versão fixada, config em biome.json) e node --test
                  em tests/front/; sem node na máquina, pula com aviso
    testes        pytest sob coverage (ramos e subprocessos) + pisos de dev/pisos-cobertura.json
    auditoria     pip-audit das ferramentas de desenvolvimento (só com --auditar: precisa de rede)

``--atualizar-pisos`` sobe os pisos até a cobertura medida (nunca desce). A cobertura é gravada numa pasta
temporária; nada fica no repo além do snapshot apertado pelo complexipy, que deve ser commitado.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, NamedTuple, Optional

RAIZ = Path(__file__).resolve().parent.parent
PYTHON_ALVOS = ["scripts", "jobs", "tests", "dev"]
SHELL_ALVOS = ["install.sh", "Instalar Goal Pacer.command", "tests/e2e/painel.sh"]
BIOME = "@biomejs/biome@2.5.13"  # D-12: binário do npm pela versão exata, sem package.json nem node_modules no repo
PISOS = RAIZ / "dev" / "pisos-cobertura.json"
SNAPSHOT = RAIZ / "complexipy-snapshot.json"
TIMEOUT_ETAPA_S = 1800


class Resultado(NamedTuple):
    ok: bool
    detalhe: str = ""


class Etapa(NamedTuple):
    nome: str
    rodar: Callable[[argparse.Namespace], Resultado]
    bloqueia: bool = True
    rapida: bool = True


def _binario(nome: str) -> Optional[str]:
    """Ferramenta do mesmo ambiente do Python que roda este script (uv run ou venv) ou do PATH."""
    vizinho = Path(sys.executable).parent / nome
    return str(vizinho) if vizinho.exists() else shutil.which(nome)


def _rodar(comando: list[str], env: Optional[dict[str, str]] = None) -> Resultado:
    executavel = _binario(comando[0]) if not comando[0].startswith(("/", ".")) else comando[0]
    if executavel is None:
        return Resultado(
            False, "%s não encontrado: rode com uv run --with-requirements requirements-dev.txt" % comando[0]
        )
    proc = subprocess.run(
        [executavel, *comando[1:]],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        env=env,
        timeout=TIMEOUT_ETAPA_S,
        check=False,
    )
    saida = (proc.stdout + proc.stderr).strip()
    return Resultado(proc.returncode == 0, saida if proc.returncode else "")


def formato(_args: argparse.Namespace) -> Resultado:
    return _rodar(["ruff", "format", "--check", *PYTHON_ALVOS])


def lint(_args: argparse.Namespace) -> Resultado:
    return _rodar(["ruff", "check", *PYTHON_ALVOS])


def complexidade(_args: argparse.Namespace) -> Resultado:
    antes = SNAPSHOT.read_bytes() if SNAPSHOT.exists() else b""
    resultado = _rodar(["complexipy", "--quiet"])
    if resultado.ok and SNAPSHOT.exists() and SNAPSHOT.read_bytes() != antes:
        return Resultado(True, "funções melhoraram: complexipy-snapshot.json apertado, commite o arquivo")
    return resultado


def tipos(_args: argparse.Namespace) -> Resultado:
    return _rodar(
        [
            "ty",
            "check",
            "scripts",
            "jobs/run_job.py",
            "dev/verificar.py",
            "dev/mutacao.py",
            "dev/release.py",
            "dev/empacotar.py",
        ]
    )


def codigo_morto(_args: argparse.Namespace) -> Resultado:
    return _rodar(["vulture", "scripts", "jobs/run_job.py", "dev/vulture_permitidos.py", "--min-confidence", "60"])


def shell(_args: argparse.Namespace) -> Resultado:
    return _rodar(["shellcheck", *SHELL_ALVOS])


def auditoria(args: argparse.Namespace) -> Resultado:
    if not args.auditar:
        return Resultado(True, "pulada (use --auditar)")
    return _rodar(
        [
            "pip-audit",
            "--requirement",
            "requirements-dev.txt",
            "--requirement",
            "requirements-e2e.txt",
            "--requirement",
            "requirements-dmg.txt",
            "--progress-spinner",
            "off",
        ]
    )


def _cobertura_por_arquivo(relatorio: dict) -> dict[str, float]:
    return {nome: dados["summary"]["percent_covered"] for nome, dados in relatorio["files"].items()}


def conferir_pisos(medido_total: float, por_arquivo: dict[str, float], pisos: dict) -> list[str]:
    """Frases do que ficou abaixo do piso: total e cada módulo listado (arquivo ausente do relatório conta como 0)."""
    abaixo = []
    if medido_total + 1e-9 < pisos["total"]:
        abaixo.append("total %.2f%% < piso %d%%" % (medido_total, pisos["total"]))
    for arquivo, piso in sorted(pisos["modulos"].items()):
        medido = por_arquivo.get(arquivo, 0.0)
        if medido + 1e-9 < piso:
            abaixo.append("%s %.2f%% < piso %d%%" % (arquivo, medido, piso))
    return abaixo


def subir_pisos(medido_total: float, por_arquivo: dict[str, float], pisos: dict) -> dict:
    """Catraca: cada piso vai ao inteiro abaixo do medido, nunca abaixo do piso anterior."""
    return {
        "total": max(pisos["total"], math.floor(medido_total)),
        "modulos": {
            arquivo: max(piso, math.floor(por_arquivo.get(arquivo, 0.0))) for arquivo, piso in pisos["modulos"].items()
        },
    }


def testes(args: argparse.Namespace) -> Resultado:
    with tempfile.TemporaryDirectory(prefix="gp-cobertura-") as pasta:
        env = dict(os.environ, COVERAGE_FILE=str(Path(pasta) / ".coverage"))
        python = sys.executable
        rodada = _rodar([python, "-m", "coverage", "run", "-m", "pytest", "-q", "-p", "no:cacheprovider"], env=env)
        if not rodada.ok:
            return Resultado(False, rodada.detalhe[-4000:])
        relatorio_json = Path(pasta) / "cobertura.json"
        for passo in (["combine", "--quiet"], ["json", "--quiet", "-o", str(relatorio_json)]):
            feito = _rodar([python, "-m", "coverage", *passo], env=env)
            if not feito.ok:
                return feito
        relatorio = json.loads(relatorio_json.read_text(encoding="utf-8"))
    total = relatorio["totals"]["percent_covered"]
    por_arquivo = _cobertura_por_arquivo(relatorio)
    pisos = json.loads(PISOS.read_text(encoding="utf-8"))
    if args.atualizar_pisos:
        PISOS.write_text(
            json.dumps(subir_pisos(total, por_arquivo, pisos), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    abaixo = conferir_pisos(total, por_arquivo, pisos)
    if abaixo:
        return Resultado(False, "\n".join(abaixo))
    return Resultado(True, "cobertura %.1f%% (piso %d%%)" % (total, pisos["total"]))


def front(_args: argparse.Namespace) -> Resultado:
    npx, node = shutil.which("npx"), shutil.which("node")
    if not (npx and node):
        return Resultado(True, "pulada: node não encontrado (instale o node para o lint e os testes do front)")
    resultado = _rodar([npx, "--yes", BIOME, "lint", "web"])
    if not resultado.ok:
        return resultado
    return _rodar(
        [node, "--test", *sorted(str(p.relative_to(RAIZ)) for p in (RAIZ / "tests" / "front").glob("*.test.mjs"))]
    )


ETAPAS = (
    Etapa("formato", formato),
    Etapa("lint", lint),
    Etapa("complexidade", complexidade),
    Etapa("tipos", tipos),
    Etapa("codigo_morto", codigo_morto),
    Etapa("shell", shell),
    Etapa("front", front),
    Etapa("auditoria", auditoria),
    Etapa("testes", testes, rapida=False),
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gates de qualidade do Goal Pacer.")
    parser.add_argument("--rapido", action="store_true", help="sem a suíte de testes e a cobertura")
    parser.add_argument(
        "--so", action="append", choices=[e.nome for e in ETAPAS], help="roda só esta etapa (repetível)"
    )
    parser.add_argument("--auditar", action="store_true", help="inclui o pip-audit das ferramentas (precisa de rede)")
    parser.add_argument("--atualizar-pisos", action="store_true", help="sobe os pisos de cobertura até o medido")
    args = parser.parse_args(argv)
    escolhidas = [e for e in ETAPAS if _escolhida(e, args)]
    resultados = [_executar(etapa, args) for etapa in escolhidas]
    return 1 if any(not r.ok and e.bloqueia for e, r in zip(escolhidas, resultados)) else 0


def _escolhida(etapa: Etapa, args: argparse.Namespace) -> bool:
    return (not args.so or etapa.nome in args.so) and (etapa.rapida or not args.rapido)


def _executar(etapa: Etapa, args: argparse.Namespace) -> Resultado:
    inicio = time.monotonic()
    resultado = etapa.rodar(args)
    rotulo = "OK" if resultado.ok else ("FALHOU" if etapa.bloqueia else "AVISO")
    print("%-7s %-13s %5.1fs" % (rotulo, etapa.nome, time.monotonic() - inicio), flush=True)
    if resultado.detalhe:
        print("\n".join("        " + linha for linha in resultado.detalhe.splitlines()[-40:]), flush=True)
    return resultado


if __name__ == "__main__":
    sys.exit(main())
