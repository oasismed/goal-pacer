"""Ajustes em ``metas/M<nn>.md`` feitos por script (decisões do check-in, recalibração, arquivar).

O modelo nunca edita metas à mão: a skill coleta a resposta e chama
``ajustar``, que valida contra ``schema.py`` e grava de forma atômica,
preservando o corpo. Custo mudado sem confiança informada vira
``confianca: usuario``. Mudar título, horizonte ou prazo muda o
``hash_metas`` (o próximo diário encadeia o mensal) e deixa a pesquisa de
``fontes/`` pendente.

Saídas de uma decisão (``aplicar_decisao``)::

    manter      -> nada muda
    reduzir     -> custo_h_semana_escolhido = custo informado (> 0)
    adiar       -> prazo = data informada (ou a sugerida pelo plano)
    renegociar  -> prazo = data informada (prazo externo continua externo)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from goalpacer import frontmatter, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

CAMPOS_AJUSTAVEIS = (
    "custo_h_semana_escolhido",
    "semanas_pesquisa",
    "prazo",
    "prazo_externo",
    "estado",
    "confianca",
    "palavras_chave",
    "titulo",
    "horizonte",
    "objetivo",
    "impacto",
)
RE_MARCO = __import__("re").compile(r"^- \[( |x|X)\] (.+)$")
SAIDAS = ("manter", "reduzir", "adiar", "renegociar")


def caminho(dados: Path, meta_id: str) -> Path:
    if not schema.validar_id("meta", meta_id):
        raise GpErro(EXIT_VALIDACAO, "meta inválida: %r" % (meta_id,))
    return dados / "metas" / ("%s.md" % meta_id)


def ajustar(dados: Path, meta_id: str, mudancas: dict[str, Any]) -> dict[str, Any]:
    """Aplica ``mudancas`` e devolve ``{campo: (antes, depois)}`` do que mudou."""
    path = caminho(dados, meta_id)
    if not path.exists():
        raise GpErro(EXIT_VALIDACAO, "meta %s não existe" % meta_id)
    desconhecidos = sorted(set(mudancas) - set(CAMPOS_AJUSTAVEIS))
    if desconhecidos:
        raise GpErro(EXIT_VALIDACAO, "campos não ajustáveis: %s" % ", ".join(desconhecidos))
    bruto, corpo = frontmatter.ler_arquivo(path)
    atual, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])
    if erros:
        raise GpErro(EXIT_VALIDACAO, "%s inválida antes do ajuste: %s" % (meta_id, "; ".join(erros)))
    novo = dict(atual)
    novo.update({k: v for k, v in mudancas.items() if v is not None})
    if "custo_h_semana_escolhido" in mudancas and "confianca" not in mudancas:
        novo["confianca"] = "usuario"
    coagido, erros = frontmatter.coagir(novo, schema.ESQUEMAS["metas"])
    erros = erros or schema.validar_registro("metas", coagido)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "ajuste recusado em %s: %s" % (meta_id, "; ".join(erros)))
    diferencas = {c: (atual.get(c), coagido.get(c)) for c in coagido if atual.get(c) != coagido.get(c)}
    if diferencas:
        frontmatter.escrever_arquivo(path, coagido, corpo)
    return {c: [_texto(a), _texto(b)] for c, (a, b) in diferencas.items()}


def _texto(valor: Any) -> Any:
    return valor.isoformat() if isinstance(valor, date) else valor


def aplicar_decisao(dados: Path, meta_id: str, decisao: dict[str, Any]) -> dict[str, Any]:
    saida = decisao.get("saida")
    if saida not in SAIDAS:
        raise GpErro(EXIT_VALIDACAO, "decisão de %s: saída %r fora de %s" % (meta_id, saida, "|".join(SAIDAS)))
    if saida == "manter":
        return {}
    if saida == "reduzir":
        custo = decisao.get("custo")
        if not isinstance(custo, (int, float)) or isinstance(custo, bool) or custo <= 0:
            raise GpErro(EXIT_VALIDACAO, "decisão de %s: reduzir pede custo (h/semana > 0)" % meta_id)
        return ajustar(dados, meta_id, {"custo_h_semana_escolhido": float(custo)})
    prazo = decisao.get("prazo")
    try:
        data = date.fromisoformat(str(prazo))
    except ValueError:
        raise GpErro(EXIT_VALIDACAO, "decisão de %s: %s pede prazo AAAA-MM-DD" % (meta_id, saida)) from None
    return ajustar(dados, meta_id, {"prazo": data})


def marcos(corpo: str) -> list[dict[str, Any]]:
    """Checklist de ``## Marcos``: ``[{indice, texto, feito}]``; linhas sem ``[ ]``/``[x]`` não contam."""
    saida: list[dict[str, Any]] = []
    secao = False
    for linha in corpo.split("\n"):
        if linha.startswith("## "):
            secao = linha.strip() == "## Marcos"
            continue
        m = RE_MARCO.match(linha.strip()) if secao else None
        if m:
            saida.append({"indice": len(saida), "texto": m.group(2).strip(), "feito": m.group(1).lower() == "x"})
    return saida


def marcar_marco(dados: Path, meta_id: str, indice: int, feito: bool) -> dict[str, Any]:
    """Marca ou desmarca o marco ``indice`` de ``metas/<meta>.md`` sem mexer no resto do arquivo."""
    path = caminho(dados, meta_id)
    if not path.exists():
        raise GpErro(EXIT_VALIDACAO, "meta %s não existe" % meta_id)
    bruto, corpo = frontmatter.ler_arquivo(path)
    coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])
    if erros:
        raise GpErro(EXIT_VALIDACAO, "%s inválida: %s" % (meta_id, "; ".join(erros)))
    linhas = corpo.split("\n")
    secao = False
    contador = -1
    alvo = None
    for i, linha in enumerate(linhas):
        if linha.startswith("## "):
            secao = linha.strip() == "## Marcos"
            continue
        m = RE_MARCO.match(linha.strip()) if secao else None
        if m:
            contador += 1
            if contador == indice:
                alvo = (i, m.group(2).strip())
                break
    if alvo is None:
        raise GpErro(EXIT_VALIDACAO, "marco %r não existe em %s" % (indice, meta_id))
    i, texto = alvo
    linhas[i] = "- [%s] %s" % ("x" if feito else " ", texto)
    frontmatter.escrever_arquivo(path, coagido, "\n".join(linhas))
    return {"meta": meta_id, "indice": indice, "texto": texto, "feito": bool(feito)}
