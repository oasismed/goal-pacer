#!/usr/bin/env python3
"""balanco.py --precisa-mensal | --render [--mes AAAA-MM]: balanço de horas do mês.

``--precisa-mensal``: exit 2 (e o motivo no stdout) quando ``planos/<mês da
semana de hoje>.md`` não existe, não tem a seção ``### <semana de hoje>`` ou
foi gerado com outro ``hash_metas``; exit 0 quando o plano serve. O job
diário usa isso para encadear o mensal antes do diário.

``--render``: refaz tabelas, seções semanais e espelhos sem ler as fontes e
sem reescrever prosa (igual a ``semanal.py --mes``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mensal
from goalpacer import balanco, base, cli, clock, frontmatter, perfil as prf, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, GpErro


def precisa_mensal(dados: Path, agora) -> Optional[str]:
    """Motivo para rodar o mensal, ou None."""
    semana = clock.semana_iso(agora.date())
    mes = clock.mes_da_semana(semana)
    path = dados / "planos" / ("%s.md" % mes)
    if not path.exists():
        return "sem plano de %s" % mes
    texto = path.read_text(encoding="utf-8")
    if not balanco.secao_semana_existe(texto, semana):
        return "plano de %s sem a seção %s" % (mes, semana)
    fm, _ = frontmatter.ler_arquivo(path)
    atual = schema.hash_metas(prf._ler_metas(dados).values())
    if fm.get("hash_metas") != atual:
        return "metas mudaram desde o plano de %s" % mes
    return None


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("balanço de horas: --precisa-mensal ou --render")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--precisa-mensal", dest="precisa", action="store_true")
    grupo.add_argument("--render", action="store_true")
    parser.add_argument("--mes", default=None)
    parser.add_argument("--json", action="store_true")
    args, _resto = parser.parse_known_args(argv)
    if args.render:
        repasse = [a for a in (argv if argv is not None else sys.argv[1:]) if a != "--render"]
        return mensal.executar_cli(
            repasse,
            descricao="balanço do mês sem fontes",
            modo="balanco",
            com_evidencias_padrao=False,
            manter_prosa_padrao=True,
        )
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        if not (dados / "contexto.md").exists():
            print("sem_onboarding", file=sys.stdout)
            return EXIT_ESTADO
        motivo = precisa_mensal(dados, clock.agora())
        print(motivo or "plano em dia")
        return EXIT_ESTADO if motivo else EXIT_OK
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo


if __name__ == "__main__":
    raise SystemExit(main())
