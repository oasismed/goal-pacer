#!/usr/bin/env python3
"""parse_whatsapp.py: exports de inbox/whatsapp/ → cache/whatsapp-AAAA-MM.json (fora de qualquer sessão).

    parse_whatsapp.py [--mes AAAA-MM] [--json]

Palavras-chave vêm de ``metas/M<nn>.md`` (metas ativas). Nunca falha por
formato: export não reconhecido vira ``status: nao_reconhecido`` e o plano
diz "export não reconhecido". Exit 0 ok; 2 sem onboarding; 3 inválido; 4 IO.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, clock, io as gpio, perfil as prf, whatsapp
from goalpacer.base import EXIT_ESTADO, EXIT_OK, GpErro

PASTA_INBOX = ("inbox", "whatsapp")


def caminho_cache(mes: str) -> Path:
    return base.caminho_dados("cache", "whatsapp-%s.json" % mes)


def processar(dados: Path, mes: str, agora) -> dict[str, Any]:
    metas = {m: meta for m, meta in prf._ler_metas(dados).items() if meta.get("estado", "ativa") == "ativa"}
    palavras = {m: list(meta.get("palavras_chave") or []) for m, meta in metas.items()}
    resultados = [
        whatsapp.ler_export(path, palavras, agora=agora) for path in whatsapp.exports(dados.joinpath(*PASTA_INBOX))
    ]
    junto = whatsapp.juntar(resultados, palavras)
    junto["mes"] = mes
    junto["gerado_em"] = agora.isoformat(timespec="seconds")
    gpio.escrever_json(caminho_cache(mes), junto)
    return junto


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("lê os exports do WhatsApp e grava os trechos por meta no cache")
    parser.add_argument("--mes", default=None, help="AAAA-MM (padrão: mês de hoje)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        if not (dados / "contexto.md").exists():
            print("sem_onboarding: rode /goal-pacer onboarding", file=sys.stderr)
            return EXIT_ESTADO
        agora = clock.agora()
        mes = args.mes or clock.mes_id(agora.date())
        junto = processar(dados, mes, agora)
        if args.json:
            resumo = {k: v for k, v in junto.items() if k != "trechos"}
            resumo["trechos_por_meta"] = {m: len(t) for m, t in junto["trechos"].items()}
            sys.stdout.write(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n")
        else:
            print(
                "whatsapp: %s (%d exports, %d mensagens com palavra-chave)"
                % (junto["status"], len(junto["arquivos"]), junto["vistos"])
            )
        return EXIT_OK
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo


if __name__ == "__main__":
    raise SystemExit(main())
