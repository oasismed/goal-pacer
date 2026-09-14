"""objetivos/O<nn>.md: o que a pessoa quer que mude, e as metas que servem a cada objetivo (coach qualitativo).

Sem objetivos cadastrados (instalações antigas), cada meta ativa vira o próprio
objetivo implícito (``implicito: True``, id igual ao da meta), para que a
leitura qualitativa funcione igual. Corpo do arquivo::

    ## Por que          uma ou duas frases da pessoa
    ## Como vou saber   o sinal de que o objetivo mudou de verdade
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from goalpacer import frontmatter, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

SECOES = {"## Por que": "por_que", "## Como vou saber": "como_vou_saber"}


def _secoes(corpo: str) -> dict[str, str]:
    saida = dict.fromkeys(SECOES.values(), "")
    atual = None
    linhas: dict[str, list[str]] = {v: [] for v in SECOES.values()}
    for linha in corpo.split("\n"):
        if linha.startswith("## "):
            atual = SECOES.get(linha.strip())
            continue
        if atual:
            linhas[atual].append(linha)
    for chave, conteudo in linhas.items():
        saida[chave] = " ".join(" ".join(conteudo).split())
    return saida


def ler(dados: Path) -> dict[str, dict[str, Any]]:
    """``O<nn> → objetivo`` (front-matter coagido + ``por_que`` e ``como_vou_saber``); inválido é GpErro."""
    pasta = dados / "objetivos"
    saida: dict[str, dict[str, Any]] = {}
    if not pasta.is_dir():
        return saida
    for path in sorted(pasta.glob("O*.md")):
        if not schema.validar_id("objetivo", path.stem):
            continue
        bruto, corpo = frontmatter.ler_arquivo(path)
        coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["objetivo"])
        erros = erros or schema.validar_registro("objetivo", coagido)
        if erros:
            raise GpErro(EXIT_VALIDACAO, "%s: %s" % (path.name, "; ".join(erros)))
        if coagido["id"] != path.stem:
            raise GpErro(EXIT_VALIDACAO, "%s: id %s diferente do nome do arquivo" % (path.name, coagido["id"]))
        coagido.update(_secoes(corpo))
        coagido["implicito"] = False
        saida[coagido["id"]] = coagido
    return saida


def com_implicitos(objetivos: dict[str, dict[str, Any]], metas: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Objetivos cadastrados mais um implícito por meta ativa sem objetivo válido."""
    saida = dict(objetivos)
    for meta_id, meta in sorted(metas.items()):
        if meta.get("estado", "ativa") != "ativa":
            continue
        if meta.get("objetivo") and meta["objetivo"] in objetivos:
            continue
        saida[meta_id] = {
            "id": meta_id,
            "titulo": meta["titulo"],
            "estado": "ativo",
            "por_que": "",
            "como_vou_saber": "",
            "implicito": True,
        }
    return saida


def objetivo_da_meta(meta: dict[str, Any], objetivos: dict[str, dict[str, Any]]) -> str:
    return meta["objetivo"] if meta.get("objetivo") in objetivos else meta["id"]
