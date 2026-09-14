"""Codex CLI (``codex exec``) como provedor de prosa, com o login ChatGPT da própria pessoa (``provedor: openai``).

Receita, par da prosa do ``claude -p`` (a confirmar no spike do Codex, ``docs/spike-codex.md``)::

    codex exec --json --ephemeral --skip-git-repo-check --ignore-user-config --sandbox read-only
               -c features.apps=false -c approval_policy="never" -c forced_login_method="chatgpt"
               -c model_reasoning_effort="low|medium" [-m MODELO] -o <arquivo> -- "<prompt>"

- ``--ignore-user-config`` e ``features.apps=false``: prosa sem ferramentas, sem conectores e sem o config da
  pessoa (o par de ``--strict-mcp-config --tools "" --setting-sources ""``).
- ``forced_login_method="chatgpt"`` e o ambiente sem ``OPENAI_API_KEY``/``CODEX_API_KEY`` (``proxy.ENV_CHAVES_API``):
  cobra na assinatura, nunca na API. O app nunca lê ``~/.codex/auth.json``.
- O texto é a última mensagem, gravada pelo ``-o`` num arquivo 0600 em ``jobs/`` e apagada logo depois da leitura;
  o stdout ``--json`` só dá sinais: ``thread.started`` (sessão), ``turn.completed`` (uso), ``turn.failed`` e
  ``error`` (``ProxyErro``). Limite de uso ainda não tem sinal estruturado conhecido: vira ``ProxyErro`` até o spike.
- cwd ``~/.goal-pacer/jobs`` (fora de repositório) e em série com os proxies do Claude (``proxy._SERIE``).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from goalpacer import base, proxy
from goalpacer.base import EXIT_VALIDACAO, GpErro

ENV_CODEX_BIN = "GP_CODEX_BIN"
NOME_CODEX = "codex"
MODELO: Optional[str] = None  # None = o modelo padrão da conta no Codex; o spike decide se fixa um
ESFORCO_CURTA = "low"
ESFORCO_POR_MODELO = {"haiku": "low", "sonnet": "medium"}  # os apelidos que o app usa viram esforço de raciocínio
ESFORCO_PADRAO = "medium"
EVENTOS_DE_FALHA = ("turn.failed", "error")


def codex_bin() -> str:
    """``GP_CODEX_BIN``; senão o ``codex`` do PATH; senão só o nome (o executor diz que não achou)."""
    return os.environ.get(ENV_CODEX_BIN) or shutil.which(NOME_CODEX) or NOME_CODEX


def esforco(modelo: str, curta: bool) -> str:
    return ESFORCO_CURTA if curta else ESFORCO_POR_MODELO.get(modelo, ESFORCO_PADRAO)


def argv_prosa(prompt: str, arquivo_saida: Path, *, modelo: str = "haiku", curta: bool = True) -> list[str]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise GpErro(EXIT_VALIDACAO, "prompt de prosa vazio")
    argv = [
        codex_bin(),
        "exec",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "-c",
        "features.apps=false",
        "-c",
        'approval_policy="never"',
        "-c",
        'forced_login_method="chatgpt"',
        "-c",
        'model_reasoning_effort="%s"' % esforco(modelo, curta),
        "-o",
        str(arquivo_saida),
    ]
    if MODELO:
        argv += ["-m", MODELO]
    return [*argv, "--", prompt]


def sinais(stdout: str) -> dict[str, Any]:
    """``{"session_id", "usage", "falhas"}`` do stream ``--json``; linha que não é objeto JSON é ignorada."""
    lido: dict[str, Any] = {"session_id": None, "usage": {}, "falhas": []}
    for linha in stdout.split("\n"):
        try:
            evento = json.loads(linha)
        except ValueError:
            continue
        if not isinstance(evento, dict):
            continue
        tipo = evento.get("type")
        if tipo == "thread.started":
            lido["session_id"] = evento.get("thread_id")
        elif tipo == "turn.completed" and isinstance(evento.get("usage"), dict):
            lido["usage"] = evento["usage"]
        elif tipo in EVENTOS_DE_FALHA:
            lido["falhas"].append(_texto_da_falha(evento))
    return lido


def _texto_da_falha(evento: dict[str, Any]) -> str:
    erro = evento.get("error")
    if isinstance(erro, dict):
        erro = erro.get("message")
    return str(erro or evento.get("message") or evento.get("type"))[:200]


def uso_no_registro(uso: dict[str, Any]) -> dict[str, int]:
    """Uso do Codex na forma do registro do Claude: lá ``input_tokens`` inclui o cache; aqui o cache sai à parte."""
    entrada = int(uso.get("input_tokens") or 0)
    cache = int(uso.get("cached_input_tokens") or 0)
    return {
        "input_tokens": max(0, entrada - cache),
        "cache_read_input_tokens": cache,
        "cache_creation_input_tokens": 0,
        "output_tokens": int(uso.get("output_tokens") or 0),
    }


def prosa(
    prompt: str,
    *,
    modelo: str = "haiku",
    curta: bool = True,
    timeout_s: float = proxy.TIMEOUT_PADRAO_S,
    executar: Optional[proxy.Executar] = None,
    registro: proxy.Registro = None,
) -> str:
    """Prosa sem ferramentas pelo Codex; mesma assinatura e mesmos erros de ``proxy.prosa``."""
    rodar = executar if executar is not None else proxy.executar_padrao
    cwd = base.jobs_dir()
    cwd.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(prefix="prosa-", suffix=".txt", dir=str(cwd))
    os.close(descritor)
    saida = Path(nome)
    try:
        argv = argv_prosa(prompt, saida, modelo=modelo, curta=curta)
        with proxy._SERIE:
            resultado = rodar(argv, timeout_s=timeout_s, cwd=cwd, env=None)
        lido = sinais(resultado.stdout)
        proxy._registrar(registro, _entrada_registro(lido, resultado, cwd))
        if lido["falhas"] or resultado.codigo != 0:
            motivo = "; ".join(lido["falhas"]) or resultado.stderr.strip()[-200:] or "código %d" % resultado.codigo
            raise proxy.ProxyErro("prosa pelo Codex: " + motivo)
        texto = saida.read_text(encoding="utf-8").strip()
    finally:
        with contextlib.suppress(OSError):
            saida.unlink()
    if not texto:
        raise proxy.RespostaInvalida("prosa pelo Codex: resposta vazia")
    return texto


def _entrada_registro(lido: dict[str, Any], resultado: proxy.Resultado, cwd: Path) -> dict[str, Any]:
    return {
        "tool": "prosa",
        "session_id": lido["session_id"],
        "duracao_s": resultado.duracao_s,
        "codigo": resultado.codigo,
        "subtype": None,
        "is_error": bool(lido["falhas"]),
        "num_turns": None,
        "usage": uso_no_registro(lido["usage"]),
        "total_cost_usd": None,
        "tentativa": 1,
        "cwd": str(cwd),
    }
