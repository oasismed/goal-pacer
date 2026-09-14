"""saude.py: métricas da pasta de dados e alertas perto do limite (análise de 13/09, O5 e O6).

Nada aqui chama conector nem grava: lê ``registro.geracoes``, os traces e os eventos locais
(``goalpacer/telemetria.py``) e os tamanhos dos arquivos. Quem mostra é o ``status`` (seção
"Perto do limite"), o email das 7h (avisos do job) e o ``run_job`` (notificação quando o mesmo
alerta aparece em três jobs seguidos, uma vez por sequência)::

    chave                limite                                         fonte
    job_perto_do_teto    duração acima de 70% do teto do job            geracoes (duracao_s, teto_s), 7 dias
    espera_lock          espera pela pasta de dados acima de 5 min       geracoes (espera_lock_s), 7 dias
    limite_de_uso        2 ou mais RateLimited em 7 dias                 geracoes (classe)
    tokens_acima         último job acima de 1,5 vez a mediana (≥ 5)     geracoes (tokens), 14 jobs
    chamada_lenta        chamada de conector acima de 90 s               traces, 7 dias
    retries_startup      mais de 30% das chamadas repetidas (≥ 10)       traces, 7 dias
    registro_grande      registro.json acima de 5 MB                     tamanho do arquivo
    painel_lento         p95 das telas acima de 300 ms (≥ 20 pedidos)    eventos do painel, 7 dias
    erros_tela           erro de JavaScript ou erro inesperado do painel eventos, 7 dias

Os alertas do job (os seis primeiros) vão para o email; os do painel e do registro só para o ``status``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Callable, NamedTuple, Optional

from goalpacer import clock, copy, telemetria
from goalpacer.base import GpErro

FRACAO_TETO = 0.7
ESPERA_LOCK_S = 5 * 60
LIMITES_DE_USO_7D = 2
FATOR_TOKENS = 1.5
MINIMO_AMOSTRAS_TOKENS = 5
CHAMADA_LENTA_MS = 90_000
FRACAO_RETRIES = 0.3
MINIMO_CHAMADAS = 10
REGISTRO_GRANDE_KB = 5 * 1024
PAINEL_LENTO_MS = 300.0
MINIMO_PEDIDOS = 20
JANELA_DIAS = 7


def _kb(path: Path) -> float:
    try:
        return round(path.stat().st_size / 1024.0, 1)
    except OSError:
        return 0.0


def metricas(dados: Path) -> dict[str, Any]:
    pasta_logs = telemetria.pasta()
    logs_kb = 0.0
    if pasta_logs is not None and pasta_logs.is_dir():
        logs_kb = round(sum(p.stat().st_size for p in pasta_logs.glob("*") if p.is_file()) / 1024.0, 1)
    resumo = telemetria.resumo(JANELA_DIAS)
    telas = [linha for rota, linha in resumo["painel"].items() if rota.startswith("GET /api/")]
    pedidos = sum(linha["n"] for linha in telas)
    return {
        "registro_kb": _kb(dados / "registro.json"),
        "anuais_kb": round(sum(_kb(p) for p in dados.glob("registro-[0-9][0-9][0-9][0-9].json")), 1),
        "dias": len(list((dados / "dias").glob("*.md"))) if (dados / "dias").is_dir() else 0,
        "planos": len(list((dados / "planos").glob("*.md"))) if (dados / "planos").is_dir() else 0,
        "logs_kb": logs_kb,
        "painel_pedidos_7d": pedidos,
        "painel_p95_ms": max((linha["p95_ms"] for linha in telas), default=None),
        "conectores": resumo["conectores"],
        "chamadas_7d": resumo["chamadas"],
        "erros_front_7d": resumo["erros_front"],
        "erros_painel_7d": resumo["erros_painel"],
    }


def _instante(geracao: dict[str, Any]) -> Optional[datetime]:
    try:
        return clock.parse_iso(str(geracao.get("ts")))
    except GpErro:
        return None


def _jobs(registro: dict[str, Any]) -> list[tuple[datetime, dict[str, Any]]]:
    saida = [
        (t, g)
        for g in registro.get("geracoes", {}).values()
        if str(g.get("modo", "")).startswith("job:")
        for t in [_instante(g)]
        if t is not None
    ]
    return sorted(saida, key=lambda par: par[0])


def _tokens(geracao: dict[str, Any]) -> int:
    lido = geracao.get("tokens")
    tokens: dict[str, Any] = lido if isinstance(lido, dict) else {}
    return sum(int(v or 0) for v in tokens.values() if isinstance(v, (int, float)))


def _quando(instante: datetime, agora: datetime) -> str:
    local = instante.astimezone(agora.tzinfo)
    return "%s %s" % (copy.dia_curto(local.date()), copy.data_curta(local.date()))


class _Base(NamedTuple):
    """O que os verificadores leem: jobs do registro (todos e os da janela), spans de conector e medidas da pasta."""

    agora: datetime
    jobs: list[tuple[datetime, dict[str, Any]]]
    recentes: list[tuple[datetime, dict[str, Any]]]
    spans: list[dict[str, Any]]
    medidas: Optional[dict[str, Any]]


def _job_perto_do_teto(b: _Base) -> Optional[str]:
    perto = [
        (t, g)
        for t, g in b.recentes
        if isinstance(g.get("teto_s"), (int, float))
        and g.get("teto_s")
        and float(g.get("duracao_s") or 0) > FRACAO_TETO * float(g["teto_s"])
    ]
    if not perto:
        return None
    t, g = perto[-1]
    return copy.texto(
        "saude.job_perto_do_teto",
        quando=_quando(t, b.agora),
        minutos=max(1, round(float(g["duracao_s"]) / 60)),
        teto=max(1, round(float(g["teto_s"]) / 60)),
    )


def _espera_lock(b: _Base) -> Optional[str]:
    esperas = [(t, g) for t, g in b.recentes if float(g.get("espera_lock_s") or 0) > ESPERA_LOCK_S]
    if not esperas:
        return None
    t, g = esperas[-1]
    return copy.texto("saude.espera_lock", quando=_quando(t, b.agora), minutos=round(float(g["espera_lock_s"]) / 60))


def _limite_de_uso(b: _Base) -> Optional[str]:
    limites = sum(1 for _, g in b.recentes if g.get("classe") == "RateLimited")
    return copy.texto("saude.limite_de_uso", n=limites) if limites >= LIMITES_DE_USO_7D else None


def _tokens_acima(b: _Base) -> Optional[str]:
    if len(b.jobs) <= MINIMO_AMOSTRAS_TOKENS:
        return None
    anteriores = [_tokens(g) for _, g in b.jobs[-15:-1] if _tokens(g) > 0]
    ultimo = _tokens(b.jobs[-1][1])
    if len(anteriores) < MINIMO_AMOSTRAS_TOKENS or ultimo <= FATOR_TOKENS * median(anteriores):
        return None
    return copy.texto("saude.tokens_acima", tokens=ultimo, mediana=int(median(anteriores)))


def _chamada_lenta(b: _Base) -> Optional[str]:
    lentas = [s for s in b.spans if float(s["ms"]) > CHAMADA_LENTA_MS]
    if not lentas:
        return None
    pior = max(lentas, key=lambda s: float(s["ms"]))
    return copy.texto(
        "saude.chamada_lenta", ferramenta=pior.get("ferramenta") or "?", segundos=round(float(pior["ms"]) / 1000)
    )


def _retries_startup(b: _Base) -> Optional[str]:
    repetidas = sum(1 for s in b.spans if (s.get("tentativa") or 1) > 1)
    if len(b.spans) < MINIMO_CHAMADAS or repetidas <= FRACAO_RETRIES * len(b.spans):
        return None
    return copy.texto("saude.retries_startup", pct=round(100.0 * repetidas / len(b.spans)))


def _registro_grande(b: _Base) -> Optional[str]:
    kb = b.medidas["registro_kb"] if b.medidas else 0.0
    return copy.texto("saude.registro_grande", mb=round(kb / 1024.0, 1)) if kb > REGISTRO_GRANDE_KB else None


def _painel_lento(b: _Base) -> Optional[str]:
    m = b.medidas or {}
    if (
        m.get("painel_p95_ms") is None
        or m["painel_pedidos_7d"] < MINIMO_PEDIDOS
        or m["painel_p95_ms"] <= PAINEL_LENTO_MS
    ):
        return None
    return copy.texto("saude.painel_lento", ms=round(m["painel_p95_ms"]))


def _erros_tela(b: _Base) -> Optional[str]:
    erros = (b.medidas or {}).get("erros_front_7d", 0) + (b.medidas or {}).get("erros_painel_7d", 0)
    return copy.texto("saude.erros_tela", n=erros) if erros else None


# A ordem das tuplas é a ordem da tabela do módulo (e das linhas do status e do email).
VERIFICADORES_DO_JOB: tuple[tuple[str, Callable[[_Base], Optional[str]]], ...] = (
    ("job_perto_do_teto", _job_perto_do_teto),
    ("espera_lock", _espera_lock),
    ("limite_de_uso", _limite_de_uso),
    ("tokens_acima", _tokens_acima),
    ("chamada_lenta", _chamada_lenta),
    ("retries_startup", _retries_startup),
)
VERIFICADORES_DA_PASTA: tuple[tuple[str, Callable[[_Base], Optional[str]]], ...] = (
    ("registro_grande", _registro_grande),
    ("painel_lento", _painel_lento),
    ("erros_tela", _erros_tela),
)
ALERTAS_DO_JOB = tuple(chave for chave, _ in VERIFICADORES_DO_JOB)


def alertas(dados: Path, agora: datetime, registro: dict[str, Any], *, so_do_job: bool = False) -> list[dict[str, Any]]:
    """``[{"chave", "texto"}]`` na ordem da tabela do módulo; vazio quando tudo está longe dos limites.
    ``so_do_job`` fica nos seis primeiros e não lê a pasta (tamanhos e eventos do painel)."""
    limite = clock.para_utc(agora) - timedelta(days=JANELA_DIAS)
    jobs = _jobs(registro)
    spans = [
        s
        for s in telemetria.ler("trace-*.jsonl", dias=JANELA_DIAS)
        if s.get("nome") == "conector" and isinstance(s.get("ms"), (int, float))
    ]
    base_ = _Base(
        agora=agora,
        jobs=jobs,
        recentes=[(t, g) for t, g in jobs if clock.para_utc(t) >= limite],
        spans=spans,
        medidas=None if so_do_job else metricas(dados),
    )
    verificadores = VERIFICADORES_DO_JOB if so_do_job else VERIFICADORES_DO_JOB + VERIFICADORES_DA_PASTA
    saida = []
    for chave, verificar in verificadores:
        texto = verificar(base_)
        if texto is not None:
            saida.append({"chave": chave, "texto": texto})
    return saida


def notificacao_repetida(
    registro: dict[str, Any], chaves_agora: list[str], *, run_id_atual: str, vezes: int = 3
) -> Optional[str]:
    """Chave de alerta presente neste job e nos ``vezes - 1`` anteriores, ainda não notificada nessa sequência."""
    anteriores = [g for _, g in _jobs(registro) if g.get("run_id") != run_id_atual][-(vezes - 1) :] if vezes > 1 else []
    if len(anteriores) < vezes - 1:
        return None
    for chave in chaves_agora:
        if all(chave in (g.get("alertas") or []) for g in anteriores) and not any(
            g.get("alerta_notificado") == chave for g in anteriores
        ):
            return chave
    return None
