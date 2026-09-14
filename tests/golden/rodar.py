#!/usr/bin/env python3
"""rodar.py [--viva] [--caso NOME] [--atualizar-baseline]: golden run do diário e do mensal (T26; AGENTS.md, regra de eval).

Sem ``--viva``: os mesmos asserts do ``tests/test_golden.py`` (zero tokens).
Com ``--viva``: o porquê de cada bloco vem de ``claude -p`` de verdade
(haiku, sem ferramentas; proxies e agenda continuam de fixture). Custa
tokens da assinatura: rode antes do /ship quando mudar ``SKILL.md``,
``references/regras.md``, ``references/copy.*.md``, ``jobs/prompt-*.md``
ou ``goalpacer/schema.py``.

Verde = nenhum problema em nenhum caso, ``hash_dia`` igual ao baseline e,
na viva, tokens até 1,5 vez o baseline de tokens e prosa sem cair no
template. ``--atualizar-baseline`` grava os hashes (e os tokens, na viva)
do run atual em ``tests/golden/baseline.json``. Os transcripts das sessões
criadas são apagados no fim.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI.parent.parent / "scripts"))

from goalpacer import proxy  # noqa: E402
from golden import casos, verificar  # noqa: E402

BASELINE = AQUI / "baseline.json"
FATOR_TOKENS = 1.5


def apagar_sessoes(raiz: Path, sessoes: list[str]) -> int:
    apagadas = 0
    for sessao in sessoes:
        try:
            for alvo in (
                proxy.caminho_transcript(raiz / "jobs", sessao),
                proxy.caminho_tool_results(raiz / "jobs", sessao),
            ):
                if alvo.is_file():
                    alvo.unlink()
                    apagadas += 1
                elif alvo.is_dir():
                    shutil.rmtree(alvo)
                    apagadas += 1
        except Exception:  # transcript é heurística do slug; ausente não é erro
            continue
    # a raiz do caso é temporária: a pasta do projeto só guarda pastas vazias (memory/) e pode sair inteira
    try:
        projeto = proxy.caminho_transcript(raiz / "jobs", "x").parent
        if projeto.is_dir() and not any(p.is_file() for p in projeto.rglob("*")):
            shutil.rmtree(projeto)
    except Exception:
        pass
    return apagadas


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="golden run do diário")
    parser.add_argument("--viva", action="store_true", help="prosa real por claude -p (custa tokens)")
    parser.add_argument("--caso", choices=casos.CASOS + casos.CASOS_MENSAL, action="append", default=None)
    parser.add_argument("--atualizar-baseline", dest="atualizar", action="store_true")
    args = parser.parse_args(argv)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"casos": {}}
    verde = True
    relatorio = {}
    with tempfile.TemporaryDirectory(prefix="gp-golden-") as tmp:
        for caso in args.caso or (casos.CASOS + casos.CASOS_MENSAL):
            run_id = "golden-%s" % caso
            mensal = caso in casos.CASOS_MENSAL
            chave_hash = "hash_numeros" if mensal else "hash_dia"
            if mensal:
                montagem = casos.montar_mensal(caso, Path(tmp) / caso)
                proc = casos.rodar_mensal(montagem, run_id=run_id, viva=args.viva)
                problemas, medidas = verificar.verificar_mensal(montagem, proc, run_id)
            else:
                montagem = casos.montar(caso, Path(tmp) / caso)
                proc = casos.rodar(montagem, run_id=run_id, viva=args.viva)
                problemas, medidas = verificar.verificar(montagem, proc, run_id)
            base_caso = baseline["casos"].get(caso, {})
            if not args.atualizar and base_caso.get(chave_hash) and medidas.get(chave_hash) != base_caso[chave_hash]:
                problemas.append(
                    "%s %s diferente do baseline %s" % (chave_hash, medidas.get(chave_hash), base_caso[chave_hash])
                )
            if args.viva:
                if medidas.get("prosa_em_template"):
                    problemas.append("prosa viva caiu no template (veja os avisos do dia)")
                if medidas.get("n_blocos") and not medidas.get("sessoes"):
                    problemas.append("nenhuma sessão viva registrada")
                teto = base_caso.get("tokens_viva")
                if teto and not args.atualizar and medidas.get("tokens", 0) > FATOR_TOKENS * teto:
                    problemas.append(
                        "tokens %d acima de %.1f x baseline (%d)" % (medidas["tokens"], FATOR_TOKENS, teto)
                    )
                medidas["transcripts_apagados"] = apagar_sessoes(montagem.raiz, medidas.get("sessoes") or [])
            relatorio[caso] = {
                "problemas": problemas,
                chave_hash: medidas.get(chave_hash),
                "tokens": medidas.get("tokens"),
            }
            verde = verde and not problemas
            print(
                "%s %s%s"
                % ("OK    " if not problemas else "FALHOU", caso, "" if not problemas else ": " + "; ".join(problemas))
            )
            if args.atualizar and not problemas:
                base_caso[chave_hash] = medidas[chave_hash]
                if args.viva:
                    base_caso["tokens_viva"] = medidas.get("tokens", 0)
                baseline["casos"][caso] = base_caso
    if args.atualizar:
        BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(relatorio, ensure_ascii=False))
    return 0 if verde else 1


if __name__ == "__main__":
    raise SystemExit(main())
