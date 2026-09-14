"""Prompts compostos dos jobs (eng 2.2; design "Prompts compostos").

Cada prompt = ``jobs/prompt-base.md`` + ``jobs/prompt-<nome>.md``, com
variáveis ``{{NOME}}`` substituídas. Variável sem valor é erro (o prompt
nunca sai com ``{{...}}``). ``IDIOMA`` e ``REGRAS_TOM`` vêm sempre do copy do
idioma atual (a prosa sai no idioma das superfícies e passa no lint desse idioma). Conteúdo de terceiros entra só por ``envelope``
(dado, nunca instrução). O prompt final vai para
``~/.goal-pacer/jobs/logs/prompt-<run_id>-<nome>.md`` (retenção de 7 dias;
o de ``mensal-ler`` é apagado logo após gravar ``sinais/``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from goalpacer import base, copy, io as gpio
from goalpacer.base import EXIT_VALIDACAO, GpErro

RE_VARIAVEL = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
NOME_BASE = "prompt-base.md"
TAG_ENVELOPE = "dados_nao_confiaveis"


def pasta_jobs() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "jobs"


def caminho(nome: str) -> Path:
    return pasta_jobs() / ("prompt-%s.md" % nome)


def envelope(fonte: str, texto: str) -> str:
    """Conteúdo não confiável entre marcadores; o fechamento dentro do texto é neutralizado."""
    limpo = (
        str(texto)
        .replace("</%s" % TAG_ENVELOPE, "</ %s" % TAG_ENVELOPE)
        .replace("<%s" % TAG_ENVELOPE, "< %s" % TAG_ENVELOPE)
    )
    return '<%s fonte="%s">\n%s\n</%s>' % (TAG_ENVELOPE, fonte, limpo.strip("\n"), TAG_ENVELOPE)


def renderizar(nome: str, variaveis: dict[str, Any]) -> str:
    """Base + prompt do modo, variáveis substituídas; sobra de ``{{X}}`` é ``GpErro``."""
    partes = []
    for path in (pasta_jobs() / NOME_BASE, caminho(nome)):
        if not path.exists():
            raise GpErro(EXIT_VALIDACAO, "prompt não encontrado: %s" % path)
        partes.append(path.read_text(encoding="utf-8").strip("\n"))
    texto = "\n\n".join(partes) + "\n"
    variaveis = dict(variaveis_de_idioma(), **variaveis)

    def trocar(m: re.Match[str]) -> str:
        chave = m.group(1)
        if chave not in variaveis:
            raise GpErro(EXIT_VALIDACAO, "prompt %s: variável {{%s}} sem valor" % (nome, chave))
        return str(variaveis[chave])

    return RE_VARIAVEL.sub(trocar, texto)


def variaveis_de_idioma() -> dict[str, str]:
    return {"IDIOMA": copy.texto("calendario.nome_idioma"), "REGRAS_TOM": copy.texto("tom.regras_prompt")}


def variaveis_de(nome: str) -> set[str]:
    """Variáveis usadas pela base + prompt do modo (para testes e para o lint)."""
    texto = ""
    for path in (pasta_jobs() / NOME_BASE, caminho(nome)):
        if path.exists():
            texto += path.read_text(encoding="utf-8")
    return set(RE_VARIAVEL.findall(texto))


def salvar(run_id: str, nome: str, texto: str) -> Path:
    path = base.jobs_dir() / "logs" / ("prompt-%s-%s.md" % (run_id, nome))
    gpio.escrever_atomico(path, texto, bak=False)
    return path
