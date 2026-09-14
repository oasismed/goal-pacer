"""Conexões da instalação: os conectores do provedor e as fontes de evidência, para a tela Conexões do painel.

Quem sabe o estado é quem fala com os conectores, e só eles gravam em ``jobs/conexoes.json``::

    goal-pacer doctor   claude mcp list (conectado, reconectar, desconectado), calendário Metas, sonda de escrita
    diário e mensal     cada servidor que respondeu numa execução que terminou bem (uso_ok_em)

O painel só lê este arquivo e o ``registro.json`` (a classe do último job, para "o último job pediu reconexão");
nunca chama conector. Sem instalação (``jobs/`` ausente) e no ``--offline`` nada é gravado. Conectar e
reconectar acontecem no provedor (claude.ai ou apps do ChatGPT): o app não faz login próprio.

Conectores são opcionais (pedido do usuário, 14/09): sem nenhum, metas, plano e dia saem só do que a pessoa escreveu.
``usa_agenda`` (o onboarding gravou o calendário Metas: blocos no Google Calendar e check-in inferido) e ``usa_email``
(gravou o e-mail próprio: email das 7h e check-in pela resposta) dizem o que a instalação escolheu, e
``exigidos`` quais servidores precisam estar conectados para isso.

As fontes ativas (``fontes_ativas`` de ``contexto.md``) mudam por ``ajustar_fonte``, sob o lock de quem chama
(o painel grava sob o lock da pasta de dados); a mudança vale na próxima leitura mensal.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from goalpacer import base, frontmatter, io as gpio, proxy, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

NOME_ARQUIVO = "conexoes.json"
SERVIDORES = proxy.SERVIDORES_USADOS
OBRIGATORIOS = ("Google_Calendar", "Gmail")
ESTADOS = ("conectado", "reconectar", "desconectado", "sem_verificacao")
CLASSES_DE_RECONEXAO = ("EscopoInsuficiente", "ErroConector", "McpNaoCarregado")


def usa_agenda(contexto: dict[str, Any]) -> bool:
    """A instalação cria blocos no Google Calendar (o onboarding gravou o calendário Metas)."""
    return bool(str(contexto.get("calendar_id_metas") or "").strip())


def usa_email(contexto: dict[str, Any]) -> bool:
    """A instalação manda o email das 7h e lê as respostas (o onboarding gravou o e-mail próprio)."""
    return bool(str(contexto.get("email_proprio") or "").strip())


def exigidos(contexto: Optional[dict[str, Any]]) -> tuple[str, ...]:
    """Servidores que precisam estar conectados para o que a instalação usa; nenhum antes do onboarding."""
    if contexto is None:
        return ()
    gmail = usa_email(contexto) or "gmail" in (contexto.get("fontes_ativas") or [])
    return tuple(s for s, usa in (("Google_Calendar", usa_agenda(contexto)), ("Gmail", gmail)) if usa)


def caminho() -> Path:
    return base.jobs_dir() / NOME_ARQUIVO


def vazio() -> dict[str, Any]:
    return {"doctor_em": None, "metas_encontrado": None, "escrita_testada_em": None, "servidores": {}}


def ler() -> dict[str, Any]:
    """O estado gravado, com as chaves de ``vazio()`` sempre presentes; arquivo ausente ou quebrado é vazio."""
    try:
        lido = json.loads(caminho().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vazio()
    if not isinstance(lido, dict):
        return vazio()
    estado = vazio()
    estado.update({k: v for k, v in lido.items() if k in estado})
    if not isinstance(estado["servidores"], dict):
        estado["servidores"] = {}
    return estado


def _gravar(estado: dict[str, Any]) -> None:
    if base.jobs_dir().is_dir():
        gpio.escrever_atomico(
            caminho(), json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", bak=False
        )


def _servidor(estado: dict[str, Any], nome: str) -> dict[str, Any]:
    atual = estado["servidores"].get(nome)
    if not isinstance(atual, dict):
        atual = estado["servidores"][nome] = {}
    return atual


def estado_do_mcp(status: Optional[str]) -> str:
    """Texto de ``claude mcp list`` -> estado: ausente é desconectado; qualquer coisa além de Connected pede reconexão."""
    if status is None:
        return "desconectado"
    return "conectado" if status.strip().lower() == "connected" else "reconectar"


def registrar_doctor(
    estados_mcp: dict[str, str],
    agora: datetime,
    *,
    metas_encontrado: Optional[bool] = None,
    escrita_ok: bool = False,
    simulado: bool = False,
) -> None:
    """O que o doctor viu: estado de cada servidor usado, o calendário Metas e, com a sonda, a escrita."""
    if simulado:
        return
    estado = ler()
    instante = agora.isoformat(timespec="seconds")
    estado["doctor_em"] = instante
    for nome in SERVIDORES:
        servidor = _servidor(estado, nome)
        servidor["estado"] = estado_do_mcp(estados_mcp.get(nome))
        servidor["visto_em"] = instante
    if metas_encontrado is not None:
        estado["metas_encontrado"] = metas_encontrado
    if escrita_ok:
        estado["escrita_testada_em"] = instante
    _gravar(estado)


def servidores_usados(registro_proxies: Iterable[dict[str, Any]]) -> list[str]:
    """Servidores das chamadas registradas (``mcp__claude_ai_<Servidor>__<tool>``), na ordem, sem repetir."""
    vistos: list[str] = []
    for entrada in registro_proxies:
        partes = str(entrada.get("tool") or "").split("__")
        nome = partes[1][len("claude_ai_") :] if len(partes) >= 3 and partes[1].startswith("claude_ai_") else ""
        if nome in SERVIDORES and nome not in vistos:
            vistos.append(nome)
    return vistos


def registrar_uso(registro_proxies: Iterable[dict[str, Any]], agora: datetime, *, simulado: bool = False) -> None:
    """Uma execução que terminou bem: cada servidor chamado nela está conectado e respondeu."""
    usados = servidores_usados(registro_proxies)
    if simulado or not usados:
        return
    estado = ler()
    instante = agora.isoformat(timespec="seconds")
    for nome in usados:
        servidor = _servidor(estado, nome)
        servidor["estado"] = "conectado"
        servidor["uso_ok_em"] = instante
    _gravar(estado)


def ajustar_fonte(dados: Path, fonte: str, ativa: bool) -> bool:
    """Liga ou desliga uma fonte de evidência em ``contexto.md``; devolve se mudou. O Gmail segue obrigatório para
    o dia (email das 7h e respostas) mesmo fora das fontes: aqui só muda a leitura de evidências do mensal."""
    if fonte not in schema.FONTES:
        raise GpErro(EXIT_VALIDACAO, "fonte desconhecida %r: use %s" % (fonte, ", ".join(schema.FONTES)))
    path = Path(dados) / schema.CAMINHOS["contexto"]
    bruto, corpo = frontmatter.ler_arquivo(path)
    contexto, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["contexto"])
    if erros:
        raise GpErro(EXIT_VALIDACAO, "contexto.md inválido antes do ajuste: " + "; ".join(erros[:5]))
    atuais = list(contexto.get("fontes_ativas") or [])
    novas = [f for f in schema.FONTES if (f in atuais and f != fonte) or (f == fonte and ativa)]
    if novas == atuais:
        return False
    contexto["fontes_ativas"] = novas
    erros = schema.validar_registro("contexto", contexto)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "ajuste recusado em contexto.md: " + "; ".join(erros[:5]))
    frontmatter.escrever_arquivo(path, contexto, corpo)
    return True
