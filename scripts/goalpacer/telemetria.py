"""telemetria.py: logs estruturados e traces locais, e a leitura de volta para status, alertas e ``goal-pacer logs``.

Tudo fica em ``~/.goal-pacer/jobs/logs/`` (ou ``GP_LOGS_DIR``), pasta 0700, retenção de 7 dias do job::

    log(mensagem, nivel=)             linha em stderr (texto ou JSON); aviso e erro também viram evento "log"
    evento(tipo, **campos)            uma linha JSON em eventos-AAAA-MM-DD.jsonl
                                      tipos: painel (pedido), painel_erro, erro_front, log (aviso/erro), alerta
    registrar_span(nome, ms, **attrs) um span já medido em trace-<trace_id>.jsonl
    span(nome, **attrs)               context manager que mede e grava o span (filhos herdam o pai)

    trace_id = GP_TRACE_ID (o job passa o próprio run_id aos passos) > GP_RUN_ID > interativo-AAAAMMDD
    pai      = span aberto neste processo > GP_TRACE_PAI (o job passa o span do passo ao subprocesso)

Regras de conteúdo: nunca texto de terceiros, título de evento, texto da pessoa, token ou cookie; só
campos escalares, textos cortados em 200 caracteres. Sem instalação (``jobs/`` ausente) e sem
``GP_LOGS_DIR`` nada é gravado; ``GP_TELEMETRIA=0`` desliga. Falha de escrita nunca derruba quem chamou.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import secrets
import sys
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

from goalpacer import base, clock

NIVEIS_LOG = ("debug", "info", "aviso", "erro")
RUN_ID_AUSENTE = "-"  # run_id do log quando nem o argumento nem GP_RUN_ID existem
ENV_LOG_JSON = "GP_LOG_JSON"  # 1 = log escreve uma linha JSON por mensagem (ts, run_id, nivel, mensagem)
ENV_LOGS = "GP_LOGS_DIR"
ENV_DESLIGAR = "GP_TELEMETRIA"
ENV_TRACE_ID = "GP_TRACE_ID"
ENV_TRACE_PAI = "GP_TRACE_PAI"
TETO_TEXTO = 200
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
RE_ID_ARQUIVO = re.compile(r"[^A-Za-z0-9_.-]")
_trava = threading.Lock()
_span_atual: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("gp_span_atual", default=None)


def pasta() -> Optional[Path]:
    if os.environ.get(ENV_DESLIGAR) == "0":
        return None
    env = os.environ.get(ENV_LOGS)
    if env:
        return Path(env)
    jobs = base.jobs_dir()
    return jobs / "logs" if jobs.is_dir() else None


def _limpo(valor: Any) -> Any:
    if valor is None or isinstance(valor, (bool, int)):
        return valor
    if isinstance(valor, float):
        return round(valor, 3)
    return RE_CONTROLE.sub(" ", str(valor))[:TETO_TEXTO]


def _gravar(nome: str, linha: dict[str, Any]) -> None:
    destino = pasta()
    if destino is None:
        return
    try:
        with _trava:
            if not destino.is_dir():
                destino.mkdir(parents=True, exist_ok=True)
                os.chmod(str(destino), 0o700)
            with open(destino / nome, "a", encoding="utf-8") as arquivo:
                arquivo.write(json.dumps(linha, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        return


def evento(tipo: str, **campos: Any) -> None:
    agora = clock.instante_real()
    linha = {"ts": agora.isoformat(timespec="milliseconds"), "tipo": tipo}
    linha.update({k: _limpo(v) for k, v in campos.items()})
    _gravar("eventos-%s.jsonl" % agora.strftime("%Y-%m-%d"), linha)


def trace_id() -> str:
    bruto = (
        os.environ.get(ENV_TRACE_ID)
        or os.environ.get(base.ENV_RUN_ID)
        or "interativo-%s" % clock.instante_real().strftime("%Y%m%d")
    )
    return RE_ID_ARQUIVO.sub("_", bruto)[:80]


def novo_span_id() -> str:
    return secrets.token_hex(6)


def registrar_span(
    nome: str, ms: float, *, pai: Optional[str] = None, span_id: Optional[str] = None, **atributos: Any
) -> str:
    """``pai=""`` marca a raiz (o próprio job); ``None`` herda o span aberto ou ``GP_TRACE_PAI``."""
    span_id = span_id or novo_span_id()
    fim = clock.instante_real()
    linha = {
        "ts": (fim - timedelta(milliseconds=ms)).isoformat(timespec="milliseconds"),
        "tipo": "span",
        "trace_id": trace_id(),
        "span_id": span_id,
        "pai": (pai or None) if pai is not None else (_span_atual.get() or os.environ.get(ENV_TRACE_PAI)),
        "nome": _limpo(nome),
        "ms": round(float(ms), 1),
        "run_id": _limpo(os.environ.get(base.ENV_RUN_ID) or ""),
    }
    linha.update({k: _limpo(v) for k, v in atributos.items()})
    _gravar("trace-%s.jsonl" % trace_id(), linha)
    return span_id


@contextmanager
def span(nome: str, **atributos: Any) -> Iterator[dict[str, Any]]:
    """Mede o bloco; atributos acrescentados ao dict devolvido também são gravados (ex.: ``s["codigo"] = 3``)."""
    span_id = secrets.token_hex(6)
    pai = _span_atual.get() or os.environ.get(ENV_TRACE_PAI)
    ficha = _span_atual.set(span_id)
    extra: dict[str, Any] = dict(atributos)
    comeco = time.monotonic()
    try:
        yield extra
    except BaseException as erro:
        extra.setdefault("erro", type(erro).__name__)
        raise
    finally:
        _span_atual.reset(ficha)
        registrar_span(nome, (time.monotonic() - comeco) * 1000, pai=pai, span_id=span_id, **extra)


def log(mensagem: str, *, run_id: Optional[str] = None, nivel: str = "info") -> None:
    """Uma linha em stderr: ``AAAA-MM-DDTHH:MM:SS±hh:mm [run_id] nivel mensagem``.

    ``run_id`` vem de ``GP_RUN_ID`` quando não informado (``-`` se ausente).
    O instante vem de ``clock.agora()``, nunca de ``datetime.now()``.
    Quebras de linha na mensagem viram espaço. ``nivel`` fora de
    ``NIVEIS_LOG`` é ``ValueError`` (erro de programação, não do usuário).
    """
    if nivel not in NIVEIS_LOG:
        raise ValueError("nível de log desconhecido: %r" % (nivel,))
    instante = clock.agora().isoformat(timespec="seconds")
    if run_id is None:
        run_id = os.environ.get(base.ENV_RUN_ID) or RUN_ID_AUSENTE
    texto = " ".join(str(mensagem).splitlines()) or ""
    if os.environ.get(ENV_LOG_JSON) == "1":
        print(
            json.dumps({"ts": instante, "run_id": run_id, "nivel": nivel, "mensagem": texto}, ensure_ascii=False),
            file=sys.stderr,
        )
    else:
        print("%s [%s] %s %s" % (instante, run_id, nivel, texto), file=sys.stderr)
    sys.stderr.flush()
    if nivel in ("aviso", "erro"):
        evento("log", nivel=nivel, run_id=run_id, mensagem=texto)


# --- leitura -------------------------------------------------------------------------------


def ler(padrao: str, *, dias: Optional[int] = 7) -> list[dict[str, Any]]:
    """Linhas dos arquivos ``padrao`` (glob) modificados nos últimos ``dias`` (``None`` = todos), na ordem do arquivo."""
    destino = pasta()
    if destino is None or not destino.is_dir():
        return []
    limite = None if dias is None else time.time() - dias * 86400
    linhas: list[dict[str, Any]] = []
    for path in sorted(destino.glob(padrao)):
        try:
            recente = limite is None or path.stat().st_mtime >= limite
        except OSError:
            continue
        if recente:
            _objetos_do_arquivo(path, linhas)
    return linhas


def _objetos_do_arquivo(path: Path, linhas: list[dict[str, Any]]) -> None:
    """Acrescenta a ``linhas`` cada linha que é um objeto JSON; linha quebrada é pulada, arquivo ilegível para ali."""
    try:
        with open(path, encoding="utf-8") as arquivo:
            for bruta in arquivo:
                try:
                    item = json.loads(bruta)
                except ValueError:
                    continue
                if isinstance(item, dict):
                    linhas.append(item)
    except OSError:
        return


def percentil(valores: list[float], p: float) -> Optional[float]:
    if not valores:
        return None
    ordenados = sorted(valores)
    return round(ordenados[min(len(ordenados) - 1, round(p / 100.0 * (len(ordenados) - 1)))], 1)


def resumo(dias: int = 7) -> dict[str, Any]:
    """p50/p95 por rota do painel e por ferramenta de conector, erros do front e retries de startup."""
    rotas: dict[str, list[float]] = {}
    erros = {"erro_front": 0, "painel_erro": 0}
    for item in ler("eventos-*.jsonl", dias=dias):
        if item.get("tipo") == "painel" and isinstance(item.get("ms"), (int, float)):
            rotas.setdefault("%s %s" % (item.get("metodo"), item.get("rota")), []).append(float(item["ms"]))
        elif item.get("tipo") in erros:
            erros[item["tipo"]] += 1
    ferramentas: dict[str, list[float]] = {}
    tentativas: dict[str, int] = {"total": 0, "repetidas": 0}
    for item in ler("trace-*.jsonl", dias=dias):
        if item.get("nome") == "conector" and isinstance(item.get("ms"), (int, float)):
            ferramentas.setdefault(str(item.get("ferramenta")), []).append(float(item["ms"]))
            tentativas["total"] += 1
            tentativas["repetidas"] += 1 if (item.get("tentativa") or 1) > 1 else 0
    return {
        "dias": dias,
        "painel": _tabela_de_tempos(rotas),
        "conectores": _tabela_de_tempos(ferramentas),
        "erros_front": erros["erro_front"],
        "erros_painel": erros["painel_erro"],
        "chamadas": tentativas,
    }


def _tabela_de_tempos(grupos: dict[str, list[float]]) -> dict[str, dict[str, Any]]:
    return {
        k: {"n": len(v), "p50_ms": percentil(v, 50), "p95_ms": percentil(v, 95), "max_ms": round(max(v), 1)}
        for k, v in sorted(grupos.items())
    }


def trace(trace_id_ou_run: str) -> list[dict[str, Any]]:
    """Spans de um trace (ordenados pelo início)."""
    nome = RE_ID_ARQUIVO.sub("_", trace_id_ou_run)[:80]
    spans = [s for s in ler("trace-%s.jsonl" % nome, dias=None) if s.get("tipo") == "span"]
    return sorted(spans, key=lambda s: str(s.get("ts")))


def ultimo_trace(prefixo: str = "job-") -> Optional[str]:
    destino = pasta()
    if destino is None or not destino.is_dir():
        return None
    candidatos = sorted(destino.glob("trace-%s*.jsonl" % prefixo), key=lambda p: p.stat().st_mtime)
    return candidatos[-1].name[len("trace-") : -len(".jsonl")] if candidatos else None
