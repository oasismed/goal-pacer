"""Classes de erro dos jobs, runbook e textos de falha (eng 2.3; CEO Error & Rescue Registry; design 2.2).

``classe_de(erro)`` dá o nome estável de um ``GpErro`` (usado no JSON de
erro dos CLIs, em ``geracoes[run_id].classe``, na notificação e no email
mínimo de falha). ``CLASSES`` diz o código de saída, a chave do runbook no
README e se o job tenta de novo. Os textos em português ficam em
``references/copy.pt-BR.md`` (grupo ``falhas``: ``<classe>_motivo`` e
``<classe>_acao``).
"""

from __future__ import annotations

from typing import Any, NamedTuple, Optional

from goalpacer import copy, proxy
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_TIMEOUT, EXIT_VALIDACAO, GpErro


class Classe(NamedTuple):
    codigo: int
    runbook: str
    retentar: bool = False


CLASSES: dict[str, Classe] = {
    "SemOnboarding": Classe(EXIT_ESTADO, "sem-onboarding"),
    "SemMetaAtiva": Classe(EXIT_ESTADO, "sem-meta-ativa"),
    "GrafoInvalido": Classe(EXIT_VALIDACAO, "grafo-invalido"),
    "SchemaMismatch": Classe(EXIT_VALIDACAO, "schema-mismatch"),
    "CacheInvalido": Classe(EXIT_VALIDACAO, "cache-invalido"),
    "NumerosAlterados": Classe(EXIT_VALIDACAO, "numeros-alterados"),
    "MetasNaoEncontrado": Classe(EXIT_VALIDACAO, "metas-nao-encontrado"),
    "EscopoInsuficiente": Classe(EXIT_VALIDACAO, "escopo-insuficiente"),
    "ErroConector": Classe(EXIT_VALIDACAO, "erro-conector"),
    "ToolNegada": Classe(EXIT_VALIDACAO, "tool-negada"),
    "TurnosEsgotados": Classe(EXIT_VALIDACAO, "turnos-esgotados"),
    "RespostaInvalida": Classe(EXIT_VALIDACAO, "resposta-invalida"),
    "McpNaoCarregado": Classe(EXIT_IO, "mcp-nao-carregado"),
    "RateLimited": Classe(EXIT_VALIDACAO, "rate-limited", retentar=True),
    "RegistroCorrompido": Classe(EXIT_IO, "registro-corrompido"),
    "LockTimeout": Classe(EXIT_IO, "lock-timeout"),
    "BinaryMissing": Classe(EXIT_IO, "binario-ausente"),
    "SessionTimeout": Classe(EXIT_TIMEOUT, "session-timeout"),
    "Desconhecida": Classe(EXIT_VALIDACAO, "desconhecida"),
}


# marcador na mensagem do GpErro sem classe -> classe (a primeira que casa vence)
MARCADORES = (
    ("schema_version", "SchemaMismatch"),
    ("install.sh --update", "SchemaMismatch"),
    ("CacheInvalid", "CacheInvalido"),
    ("NumerosAlterados", "NumerosAlterados"),
    ("RegistroCorrompido", "RegistroCorrompido"),
    ('"Metas"', "MetasNaoEncontrado"),
    ("lock preso", "LockTimeout"),
    ("binário", "BinaryMissing"),
    ("não encontrado: claude", "BinaryMissing"),
    ("validar grafo", "GrafoInvalido"),
)


def classe_de(erro: BaseException) -> str:
    """Nome da classe para um erro dos scripts (nunca levanta): tipo do proxy > classe explícita > código e texto."""
    do_proxy = _classe_do_proxy(erro)
    if do_proxy is not None:
        return do_proxy
    if not isinstance(erro, GpErro):
        return "Desconhecida"
    classe = getattr(erro, "classe", None)
    if isinstance(classe, str) and classe in CLASSES:
        return classe
    return _classe_pelo_codigo_e_texto(erro)


def _classe_do_proxy(erro: BaseException) -> Optional[str]:
    if isinstance(erro, proxy.RateLimited):
        return "RateLimited"
    if isinstance(erro, proxy.ErroConector):
        return "EscopoInsuficiente" if erro.escopo_insuficiente else "ErroConector"
    tipos = (proxy.ToolNegada, proxy.TurnosEsgotados, proxy.McpNaoCarregado, proxy.RespostaInvalida)
    return next((tipo.__name__ for tipo in tipos if isinstance(erro, tipo)), None)


def _classe_pelo_codigo_e_texto(erro: GpErro) -> str:
    mensagem = erro.mensagem or ""
    if erro.codigo == EXIT_TIMEOUT:
        return "SessionTimeout"
    if erro.codigo == EXIT_ESTADO:
        return "SemMetaAtiva" if "sem_meta_ativa" in mensagem else "SemOnboarding"
    marcada = next((classe for marcador, classe in MARCADORES if marcador in mensagem), None)
    if marcada is not None:
        return marcada
    if erro.codigo != EXIT_IO:
        return "Desconhecida"
    minuscula = mensagem.lower()
    return "LockTimeout" if "lock" in minuscula else "RegistroCorrompido" if "registro" in minuscula else "Desconhecida"


def info(classe: str) -> Classe:
    return CLASSES.get(classe, CLASSES["Desconhecida"])


def motivo(classe: str) -> str:
    chave = classe if classe in CLASSES else "Desconhecida"
    return copy.texto("falhas.%s_motivo" % chave.lower())


def acao(classe: str) -> str:
    chave = classe if classe in CLASSES else "Desconhecida"
    return copy.texto("falhas.%s_acao" % chave.lower())


def erro_json(erro: GpErro) -> dict[str, Any]:
    classe = classe_de(erro)
    return {
        "ok": False,
        "codigo": erro.codigo,
        "classe": classe,
        "runbook": info(classe).runbook,
        "erros": (erro.mensagem or "").split("\n"),
    }


def classe_do_json(saida: str) -> Optional[str]:
    """Classe informada no JSON de erro de um CLI (última linha JSON do stdout)."""
    import json

    for linha in reversed([l for l in saida.strip().split("\n") if l.strip()]):
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dados, dict) and dados.get("classe"):
            return str(dados["classe"])
    try:
        dados = json.loads(saida)
        if isinstance(dados, dict) and dados.get("classe"):
            return str(dados["classe"])
    except ValueError:
        pass
    return None
