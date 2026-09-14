#!/usr/bin/env python3
"""goal_pacer.py <comando> [argumentos]: um comando só para o terminal (``goal-pacer`` depois do install.sh).

Cada comando é uma linha da tabela ``COMANDOS`` (script, argumentos fixos, texto da ajuda no
copy); um comando novo é uma linha aqui e uma chave ``comando.<nome>`` em cada idioma::

    goal-pacer status | doctor | painel | diario | mensal | checkin | validar | autoteste | logs
    goal-pacer atualizar | desinstalar | versao | ajuda
    (em inglês também: dashboard, daily, monthly, validate, selftest, update, uninstall, version, help)

Os argumentos depois do comando seguem para o script (``goal-pacer doctor --sondar-escrita``).
O script roda no mesmo processo, com o mesmo python3 que o install.sh escolheu.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, copy, plataforma, schema
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO


class Comando(NamedTuple):
    modulo: str
    argumentos: tuple = ()  # antes dos argumentos da pessoa
    depois: tuple = ()  # depois deles (subcomando do argparse, que precisa vir por último)


COMANDOS = {
    "status": Comando("status"),
    "doctor": Comando("status", ("--doctor",)),
    "painel": Comando("web", ("--abrir",)),
    "diario": Comando("diario"),
    "mensal": Comando("mensal"),
    "checkin": Comando("checkin"),
    "validar": Comando("validar", depois=("grafo",)),
    "autoteste": Comando("autoteste"),
    "logs": Comando("logs"),
    "atualizar": Comando("instalar", ("--update",)),
    "desinstalar": Comando("instalar", ("--uninstall",)),
}
APELIDOS = {
    "dashboard": "painel",
    "daily": "diario",
    "monthly": "mensal",
    "validate": "validar",
    "selftest": "autoteste",
    "update": "atualizar",
    "uninstall": "desinstalar",
    "version": "versao",
    "help": "ajuda",
    "--help": "ajuda",
    "-h": "ajuda",
}


def ajuda() -> str:
    linhas = [copy.texto("comando.uso"), ""]
    linhas.extend("  %-12s %s" % (nome, copy.texto("comando." + nome)) for nome in [*COMANDOS, "versao", "ajuda"])
    return "\n".join(linhas)


def versao() -> dict:
    app = Path(__file__).resolve().parent.parent
    instalacao = {}
    caminho = base.jobs_dir() / base.NOME_INSTALACAO
    if caminho.is_file():
        try:
            instalacao = json.loads(caminho.read_text(encoding="utf-8"))
        except ValueError:
            instalacao = {}
    return {
        "versao": base.VERSAO_APP,
        "revisao": instalacao.get("revisao") or "dev",
        "schema_version": schema.SCHEMA_VERSION,
        "plataforma": plataforma.nome_atual(),
        "idioma": copy.atual(),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "app": str(app),
    }


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    nome = APELIDOS.get(argv[0], argv[0]) if argv else "ajuda"
    resto = argv[1:]
    if nome == "ajuda":
        print(ajuda())
        return EXIT_OK
    if nome == "versao":
        info = versao()
        print(
            json.dumps(info, ensure_ascii=False)
            if "--json" in resto
            else copy.texto(
                "comando.versao_linha", lingua=info["idioma"], **{k: v for k, v in info.items() if k != "idioma"}
            )
        )
        return EXIT_OK
    comando = COMANDOS.get(nome)
    if comando is None:
        print(copy.texto("comando.desconhecido", nome=nome), file=sys.stderr)
        print(ajuda(), file=sys.stderr)
        return EXIT_VALIDACAO
    argumentos = [*comando.argumentos, *resto, *comando.depois]
    sys.argv = [comando.modulo + ".py", *argumentos]  # nome certo no uso do argparse
    modulo = importlib.import_module(comando.modulo)
    return int(modulo.main(argumentos) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
