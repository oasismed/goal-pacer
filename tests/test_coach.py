"""goalpacer/coach.py: sinais, tração, estados, jornada, objetivo, alavanca e horizontes com dados sintéticos."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from goalpacer import coach

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 9, 0, tzinfo=TZ)


def bloco(dias_atras: float, estado: str, origem: str = "confirmado", meta: str = "M01") -> dict:
    fim = AGORA - timedelta(days=dias_atras)
    return {
        "id": "D-x",
        "meta": meta,
        "inicio": fim - timedelta(minutes=45),
        "fim": fim,
        "estado": estado,
        "origem": origem,
    }


def test_presenca_fluidez_e_dias_sem_feito():
    blocos = [
        bloco(1, "feita"),
        bloco(2, "feita", "presumido"),
        bloco(3, "movida"),
        bloco(4, "nao_feita"),
        bloco(30, "feita"),
        bloco(-1, "planejada"),
    ]
    presenca, fluidez, n = coach.presenca_fluidez(blocos, AGORA)
    assert n == 4 and presenca == 1.5 / 4 and fluidez == 0.5
    assert coach.presenca_fluidez([bloco(-1, "planejada")], AGORA) == (None, None, 0)
    assert coach.presenca_fluidez([bloco(0.01, "planejada", "inferido"), bloco(1, "feita")], AGORA) == (
        0.75,
        1.0,
        2,
    )  # intocado e passado = feita?
    assert (
        round(coach.dias_desde_feito(blocos, AGORA)) == 1
        and coach.dias_desde_feito([bloco(2, "movida")], AGORA) is None
    )


def test_energia_decai_para_neutro_e_evidencia_espaco_avanco():
    recente = [
        {"valor": "pesada", "ts": (AGORA - timedelta(days=3)).isoformat()},
        {"valor": "energia", "ts": (AGORA - timedelta(days=20)).isoformat()},
    ]
    assert coach.energia(recente, AGORA) == 0.25 and coach.ultimo_sentimento(recente) == "pesada"
    antigo = [{"valor": "energia", "ts": (AGORA - timedelta(days=21)).isoformat()}]
    assert 0.5 < coach.energia(antigo, AGORA) < 1.0
    assert coach.energia([{"valor": "energia", "ts": (AGORA - timedelta(days=40)).isoformat()}], AGORA) == 0.5
    assert coach.energia([], AGORA) is None
    hoje = AGORA.date()
    assert coach.evidencia([], hoje) is None and coach.evidencia([hoje - timedelta(days=5)], hoje) == 0.6
    assert coach.evidencia([hoje, hoje - timedelta(days=2), hoje - timedelta(days=90)], hoje) == 1.0
    assert coach.espaco(None, False) is None and coach.espaco(100, True) == 1.0 and coach.espaco(80, False) == 0.65
    assert coach.espaco(62, True) == 0.2
    assert coach.avanco([{"feito": True}, {"feito": False}], 90) == 0.5 and coach.avanco([], 30) == 0.3


def test_tracao_estados_e_jornada():
    cheio = {"presenca": 0.9, "fluidez": 1.0, "energia": 1.0, "evidencia": 1.0, "espaco": 1.0}
    assert round(coach.tracao(cheio), 3) == 0.965
    assert coach.tracao({}) == 0.5
    meta = {"id": "M01", "estado": "ativa", "prazo_externo": False}
    marcos = [{"feito": True}, {"feito": False}]
    assert coach.estado_meta(meta, cheio, 0.965, marcos, 1, 5) == "florescendo"
    assert coach.estado_meta(meta, dict(cheio, fluidez=0.5), 0.8, marcos, 1, 5) == "atencao"
    assert coach.estado_meta(meta, cheio, 0.6, marcos, 2, 5) == "ritmo"
    assert coach.estado_meta(meta, cheio, 0.6, marcos, 12, 5) == "travada"
    assert coach.estado_meta(meta, cheio, 0.25, marcos, 1, 5) == "travada"
    assert coach.estado_meta(dict(meta, prazo_externo=True), dict(cheio, espaco=0.2), 0.8, marcos, 1, 5) == "atencao"
    assert coach.estado_meta(meta, cheio, 0.9, [{"feito": True}], 1, 5) == "conquistada"
    assert coach.estado_meta(dict(meta, estado="arquivada"), cheio, 0.9, marcos, 1, 5) == "pausada"
    assert coach.estado_meta(meta, {}, 0.5, [], None, 0) == "ritmo"  # sem blocos vencidos não é travada
    assert [coach.estagio(v) for v in (0, 0.2, 0.5, 0.8, 1.0)] == [
        "comeco",
        "construcao",
        "consolidacao",
        "reta_final",
        "conquista",
    ]


def test_tendencia_trilha_forte_fraco_nivel_quadrante():
    subindo = [bloco(d, "nao_feita") for d in (8, 10, 12)] + [bloco(d, "feita") for d in (1, 3, 5)]
    assert coach.tendencia(subindo, AGORA) == "acelerando"
    caindo = [bloco(d, "feita") for d in (8, 10, 12)] + [bloco(d, "apagada") for d in (1, 3, 5)]
    assert coach.tendencia(caindo, AGORA) == "desacelerando" and coach.tendencia([bloco(1, "feita")], AGORA) is None
    trilha = coach.trilha(subindo, AGORA)
    assert len(trilha) == 6 and trilha[-1] == 1.0 and trilha[-2] == 0.0 and trilha[0] is None
    assert coach.forte_e_fraco({"presenca": 0.9, "energia": 0.2, "espaco": None, "avanco": 0.1}) == (
        "presenca",
        "energia",
    )
    assert coach.forte_e_fraco({"presenca": 0.9, "energia": 0.8}) == ("presenca", None)
    assert [coach.nivel(v) for v in (None, 0.2, 0.5, 0.9)] == ["sem_sinal", "baixo", "medio", "alto"]
    assert coach.quadrante(0.8, 3) == "proteger" and coach.quadrante(0.3, 3) == "destravar"
    assert coach.quadrante(0.8, 1) == "manter_leve" and coach.quadrante(0.3, 1) == "repensar"


def test_objetivo_alavanca_e_horizontes():
    metas = [
        {"id": "M01", "peso": 3, "tracao": 0.8, "avanco": 0.4, "estado": "florescendo"},
        {"id": "M04", "peso": 2, "tracao": 0.3, "avanco": 0.2, "estado": "travada"},
        {"id": "M05", "peso": 1, "tracao": 0.2, "avanco": 0.0, "estado": "pausada"},
    ]
    forca = coach.forca_objetivo(metas)
    assert round(forca, 3) == round((3 * 0.64 + 2 * 0.26) / 5, 3)
    assert coach.estado_objetivo(forca, metas) == "construcao"
    assert coach.estado_objetivo(0.7, metas) == "firme" and coach.estado_objetivo(0.3, metas) == "foco"
    assert coach.estado_objetivo(None, []) == "pausado"
    assert coach.alavanca(metas) == "M04"
    assert coach.estado_objetivo(0.9, [dict(metas[0], estado="conquistada")]) == "conquistado"
    hoje = [dict(bloco(-1, "planejada"), meta="M01"), dict(bloco(-2, "feita"), meta="M05")]
    valor, chave = coach.presenca_hoje(hoje, {"M01": 3, "M05": 1})
    assert valor == 0.25 and chave == "andamento"
    assert coach.presenca_hoje([], {}) == (None, "sem_blocos")
    assert coach.presenca_hoje([dict(bloco(-1, "planejada"))], {})[1] == "por_comecar"
    assert coach.media_ponderada([(0.8, 3), (None, 2), (0.2, 1)]) == (0.8 * 3 + 0.2) / 4
    assert [coach.leitura_ritmo(v) for v in (None, 0.3, 0.6, 0.8)] == ["sem_sinal", "atencao", "ritmo", "florescendo"]


def test_compasso_e_avanco_relativo_contra_o_prazo():
    criado, prazo = date(2026, 9, 1), date(2026, 12, 10)  # 100 dias
    assert (
        coach.tempo_da_meta(criado, prazo, date(2026, 10, 11)) == 0.4
        and coach.tempo_da_meta(criado, criado, date(2026, 10, 1)) == 1.0
    )
    assert coach.compasso(0.6, criado, prazo, date(2026, 10, 11)) == "folga"
    assert coach.compasso(0.3, criado, prazo, date(2026, 10, 11)) == "compasso"
    assert coach.compasso(0.1, criado, prazo, date(2026, 10, 11)) == "folego"
    assert coach.compasso(0.0, criado, prazo, date(2026, 9, 3)) == "compasso"  # acabou de começar
    assert (
        coach.avanco_relativo(0.2, criado, prazo, date(2026, 10, 11)) == 0.5
        and coach.avanco_relativo(0.9, criado, prazo, date(2026, 10, 11)) == 1.0
    )
    assert coach.avanco_relativo(0.0, criado, prazo, date(2026, 9, 2)) == 1.0
