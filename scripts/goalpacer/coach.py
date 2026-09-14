"""Leitura qualitativa de coach (docs/designs/coach-qualitativo.md). Só cálculo, sem ler arquivos.

Os números ficam aqui; a interface recebe chaves de leitura (``florescendo``,
``destravar``...) e usa o número só para desenhar. Pipeline::

    blocos, sentimentos, evidências, plano, marcos, progresso
        -> sinais da meta (0 a 1): presença, fluidez, energia, evidência, espaço, avanço
        -> tração = 0,35 presença + 0,20 fluidez + 0,20 energia + 0,15 evidência + 0,10 espaço
        -> estado (pausada, conquistada, travada, atenção, ritmo, florescendo), jornada, tendência, trilha
        -> objetivo: força = média ponderada pelo impacto de (0,6 tração + 0,4 avanço); alavanca
        -> horizontes: hoje = presença ponderada; semana = ritmo; mês = direção
        -> compasso: avanço contra o tempo até o prazo (folga, compasso, fôlego), para trimestre, semestre e ano

Sinal ausente (sem blocos vencidos, sem sentimento, sem plano) entra como neutro
(0,5) na tração e volta como ``None`` para a interface dizer "sem sinal".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from goalpacer import schema

NEUTRO = 0.5
PESOS_TRACAO = {"presenca": 0.35, "fluidez": 0.20, "energia": 0.20, "evidencia": 0.15, "espaco": 0.10}
JANELA_DIAS = 21
JANELA_SEMANA_DIAS = 7
DIAS_TRAVADA = 10
DIAS_ENERGIA_PLENA = 14
DIAS_EVIDENCIA = 30
VALOR_SENTIMENTO = {"energia": 1.0, "firme": 0.65, "pesada": 0.25}
ESTADOS_ATRITO = ("movida", "reagendada", "apagada", "nao_feita")
ESTADOS_FORA = ("cancelada",)
ESTADOS_PRESUMIVEIS = ("feita", "planejada", "sem_sinal")
LIMIAR_TRAVADA = 0.30
LIMIAR_ATENCAO = 0.50
LIMIAR_FLORESCER = 0.70
LIMIAR_FLUIDEZ = 0.60
ESTAGIOS = (
    (0.15, "comeco"),
    (0.45, "construcao"),
    (0.75, "consolidacao"),
    (0.999, "reta_final"),
    (float("inf"), "conquista"),
)
SEMANAS_TRILHA = 6
MINIMO_TEMPO_COMPASSO = 0.05
FOLGA_COMPASSO = 0.10
FOLEGO_COMPASSO = 0.15


def _instante(valor: Any) -> Optional[datetime]:
    from goalpacer import clock

    return clock.instante(valor)  # dado ruim vira None ("sem sinal"); sem offset, o fuso da instalação


def _limitar(valor: float) -> float:
    return max(0.0, min(1.0, valor))


def peso(meta: dict[str, Any]) -> int:
    return schema.PESO_IMPACTO.get(meta.get("impacto") or "importante", 2)


# --- sinais --------------------------------------------------------------------------------


def presenca_fluidez(
    blocos: Iterable[dict[str, Any]], agora: datetime, dias: int = JANELA_DIAS
) -> tuple[Optional[float], Optional[float], int]:
    """``(presença, fluidez, blocos vencidos)`` dos blocos que terminaram nos últimos ``dias``.

    Confirmado vale 1; "feita?" vale meio, e o bloco intocado que já passou (planejado, o diário
    ainda não presumiu) conta igual ao "feita?", pela mesma regra de presunção do produto."""
    inicio = agora - timedelta(days=dias)
    vencidos = [b for b in blocos if b.get("estado") not in ESTADOS_FORA and inicio <= b["fim"] <= agora]
    if not vencidos:
        return None, None, 0
    feitos = sum(
        1.0 if b.get("estado") == "feita" and b.get("origem") == "confirmado" else 0.5
        for b in vencidos
        if b.get("estado") in ESTADOS_PRESUMIVEIS
    )
    atrito = sum(1 for b in vencidos if b.get("estado") in ESTADOS_ATRITO)
    return _limitar(feitos / len(vencidos)), _limitar(1.0 - atrito / len(vencidos)), len(vencidos)


def dias_desde_feito(blocos: Iterable[dict[str, Any]], agora: datetime) -> Optional[float]:
    feitos = [b["fim"] for b in blocos if b.get("estado") == "feita" and b["fim"] <= agora]
    if not feitos:
        return None
    return (agora - max(feitos)).total_seconds() / 86400


def energia(sentimentos: Iterable[dict[str, Any]], agora: datetime) -> Optional[float]:
    """Último sentimento; depois de 14 dias volta aos poucos ao neutro (some em 28)."""
    itens = [
        (t, s["valor"])
        for s in sentimentos
        for t in [_instante(s.get("ts"))]
        if t is not None and s.get("valor") in VALOR_SENTIMENTO
    ]
    if not itens:
        return None
    quando, valor = max(itens, key=lambda par: par[0])
    idade = (agora - quando).total_seconds() / 86400
    base = VALOR_SENTIMENTO[valor]
    if idade <= DIAS_ENERGIA_PLENA:
        return base
    confianca = max(0.0, 1.0 - (idade - DIAS_ENERGIA_PLENA) / DIAS_ENERGIA_PLENA)
    return NEUTRO + (base - NEUTRO) * confianca


def ultimo_sentimento(sentimentos: Iterable[dict[str, Any]]) -> Optional[str]:
    itens = [(t, s["valor"]) for s in sentimentos for t in [_instante(s.get("ts"))] if t is not None]
    return max(itens, key=lambda par: par[0])[1] if itens else None


def evidencia(datas: Iterable[date], hoje: date) -> Optional[float]:
    recentes = [d for d in datas if hoje - timedelta(days=DIAS_EVIDENCIA) <= d <= hoje]
    if not recentes:
        return None
    return 1.0 if len(recentes) >= 2 else 0.6


def espaco(cobertura_pct: Optional[int], prazo_externo: bool) -> Optional[float]:
    if cobertura_pct is None:
        return None
    valor = 1.0 if cobertura_pct >= 100 else 0.65 if cobertura_pct >= 70 else 0.3
    if prazo_externo and cobertura_pct < 100:
        valor -= 0.1
    return round(_limitar(valor), 3)


def avanco(marcos: list[dict[str, Any]], progresso_pct: float) -> float:
    if marcos:
        return _limitar(sum(1 for m in marcos if m.get("feito")) / len(marcos))
    return _limitar(progresso_pct / 100.0)


def tracao(sinais: dict[str, Optional[float]]) -> float:
    total = 0.0
    for nome, peso in PESOS_TRACAO.items():
        valor = sinais.get(nome)
        total += peso * (valor if valor is not None else NEUTRO)
    return _limitar(total)


# --- leituras ------------------------------------------------------------------------------


def estagio(valor_avanco: float) -> str:
    for limite, chave in ESTAGIOS:
        if valor_avanco < limite:
            return chave
    return "conquista"


def estado_meta(
    meta: dict[str, Any],
    sinais: dict[str, Optional[float]],
    valor_tracao: float,
    marcos: list[dict[str, Any]],
    dias_sem_feito: Optional[float],
    vencidos: int,
) -> str:
    if meta.get("estado", "ativa") != "ativa":
        return "conquistada" if meta.get("estado") == "concluida" else "pausada"
    if marcos and all(m.get("feito") for m in marcos):
        return "conquistada"
    parada = vencidos > 0 and (dias_sem_feito is None or dias_sem_feito >= DIAS_TRAVADA)
    if parada or valor_tracao < LIMIAR_TRAVADA:
        return "travada"
    espaco, fluidez = sinais.get("espaco"), sinais.get("fluidez")
    espaco_curto = bool(meta.get("prazo_externo")) and espaco is not None and espaco < LIMIAR_ATENCAO
    fluidez_baixa = fluidez is not None and fluidez < LIMIAR_FLUIDEZ
    if valor_tracao < LIMIAR_ATENCAO or fluidez_baixa or espaco_curto:
        return "atencao"
    return "florescendo" if valor_tracao >= LIMIAR_FLORESCER else "ritmo"


def tendencia(blocos: list[dict[str, Any]], agora: datetime) -> Optional[str]:
    atual, _, n_atual = presenca_fluidez(blocos, agora, JANELA_SEMANA_DIAS)
    anterior, _, n_anterior = presenca_fluidez(
        [b for b in blocos if b["fim"] <= agora - timedelta(days=JANELA_SEMANA_DIAS)],
        agora - timedelta(days=JANELA_SEMANA_DIAS),
        JANELA_SEMANA_DIAS,
    )
    if not n_atual or not n_anterior:
        return None
    diferenca = (atual or 0.0) - (anterior or 0.0)
    return "acelerando" if diferenca > 0.15 else "desacelerando" if diferenca < -0.15 else "estavel"


def trilha(blocos: list[dict[str, Any]], agora: datetime, semanas: int = SEMANAS_TRILHA) -> list[Optional[float]]:
    """Tração de presença e fluidez por semana, da mais antiga à atual (``None`` = semana sem blocos)."""
    saida = []
    for k in range(semanas - 1, -1, -1):
        fim = agora - timedelta(days=7 * k)
        presenca, fluidez, n = presenca_fluidez([b for b in blocos if b["fim"] <= fim], fim, 7)
        saida.append(None if not n else round(ritmo(presenca, fluidez), 3))
    return saida


def ritmo(presenca: Optional[float], fluidez: Optional[float]) -> float:
    """Leitura de uma janela de blocos (semana da trilha, período do drill-down): 0,65 presença + 0,35 fluidez."""
    return _limitar(0.65 * (presenca or 0) + 0.35 * (fluidez or 0))


def forte_e_fraco(sinais: dict[str, Optional[float]]) -> tuple[Optional[str], Optional[str]]:
    presentes = {k: v for k, v in sinais.items() if v is not None and k != "avanco"}
    if not presentes:
        return None, None
    forte = max(presentes, key=lambda k: (presentes[k], k))
    fraco = min(presentes, key=lambda k: (presentes[k], k))
    return forte, (fraco if presentes[fraco] < 0.6 else None)


def nivel(valor: Optional[float]) -> str:
    if valor is None:
        return "sem_sinal"
    return "alto" if valor >= 0.7 else "medio" if valor >= 0.45 else "baixo"


def quadrante(valor_tracao: float, peso_meta: int) -> str:
    alto_impacto = peso_meta >= 2
    if valor_tracao >= LIMIAR_ATENCAO:
        return "proteger" if alto_impacto else "manter_leve"
    return "destravar" if alto_impacto else "repensar"


def forca_objetivo(metas: list[dict[str, Any]]) -> Optional[float]:
    """``metas`` = leituras com ``peso``, ``tracao`` e ``avanco``; pausadas ficam de fora."""
    ativas = [m for m in metas if m["estado"] != "pausada"]
    if not ativas:
        return None
    total = sum(m["peso"] for m in ativas)
    return _limitar(sum(m["peso"] * (0.6 * m["tracao"] + 0.4 * m["avanco"]) for m in ativas) / total)


def estado_objetivo(forca: Optional[float], metas: list[dict[str, Any]]) -> str:
    if metas and all(m["estado"] == "conquistada" for m in metas):
        return "conquistado"
    if forca is None:
        return "pausado"
    return "firme" if forca >= 0.6 else "construcao" if forca >= 0.42 else "foco"


def alavanca(metas: list[dict[str, Any]]) -> Optional[str]:
    """Meta que mais move o objetivo agora: peso vezes o quanto falta de tração (conquistadas e pausadas fora)."""
    candidatas = [m for m in metas if m["estado"] not in ("pausada", "conquistada")]
    if not candidatas:
        return None
    return max(candidatas, key=lambda m: (m["peso"] * (1.0 - m["tracao"]), m["peso"], m["id"]))["id"]


def tempo_da_meta(criado: date, prazo: date, hoje: date) -> float:
    """Fração do caminho entre o cadastro e o prazo que já passou (0 a 1)."""
    total = (prazo - criado).days
    return 1.0 if total <= 0 else _limitar((hoje - criado).days / total)


def compasso(valor_avanco: float, criado: date, prazo: date, hoje: date) -> str:
    """Avanço (marcos) contra o tempo até o prazo: ``folga``, ``compasso`` ou ``folego``. Começo recente é compasso."""
    tempo = tempo_da_meta(criado, prazo, hoje)
    if tempo < MINIMO_TEMPO_COMPASSO:
        return "compasso"
    diferenca = valor_avanco - tempo
    return "folga" if diferenca >= FOLGA_COMPASSO else "compasso" if diferenca >= -FOLEGO_COMPASSO else "folego"


def avanco_relativo(valor_avanco: float, criado: date, prazo: date, hoje: date) -> float:
    """Avanço dividido pelo tempo já passado, até 1: quem está no compasso do prazo vale 1."""
    tempo = tempo_da_meta(criado, prazo, hoje)
    return 1.0 if tempo < MINIMO_TEMPO_COMPASSO else _limitar(valor_avanco / tempo)


def presenca_hoje(blocos_hoje: list[dict[str, Any]], pesos: dict[str, int]) -> tuple[Optional[float], str]:
    if not blocos_hoje:
        return None, "sem_blocos"
    total = sum(pesos.get(b["meta"], 2) for b in blocos_hoje)
    feito = sum(
        pesos.get(b["meta"], 2) * (1.0 if b.get("origem") == "confirmado" else 0.5)
        for b in blocos_hoje
        if b.get("estado") == "feita"
    )
    valor = _limitar(feito / total) if total else 0.0
    if valor >= 0.99:
        return valor, "cumprido"
    return valor, "andamento" if valor > 0 else "por_comecar"


def media_ponderada(itens: Iterable[tuple[float, float]]) -> Optional[float]:
    lista = [(v, p) for v, p in itens if v is not None]
    total = sum(p for _, p in lista)
    return _limitar(sum(v * p for v, p in lista) / total) if total else None


def leitura_ritmo(valor: Optional[float]) -> str:
    if valor is None:
        return "sem_sinal"
    return "florescendo" if valor >= LIMIAR_FLORESCER else "ritmo" if valor >= LIMIAR_ATENCAO else "atencao"
