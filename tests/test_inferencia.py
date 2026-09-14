"""Testes de goalpacer.inferencia sobre blocos e eventos sintéticos (compactos)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from goalpacer import inferencia

TZ = ZoneInfo("America/Sao_Paulo")
METAS = "metas-fixture@group.calendar.google.com"
PRIMARIO = "pessoa@exemplo.test"
INST = "inst-fixture-01"
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)


def bloco(sufixo: str, inicio: datetime, horas: float = 1.0, **extra) -> dict:
    b = {
        "id": "D-2026-09-26-" + sufixo,
        "titulo": "Bloco " + sufixo,
        "meta": "M01",
        "semana": "2026-W39",
        "inicio": inicio,
        "fim": inicio + timedelta(hours=horas),
        "duracao_h": horas,
        "estado": "planejada",
        "origem": "inferido",
        "calendar_event_id": "evt-" + sufixo,
        "calendar_id": METAS,
    }
    b.update(extra)
    return b


def evento(ev_id: str, inicio: str, fim: str, task: str, cal: str = METAS, inst: str = INST, **extra) -> dict:
    e = {
        "id": ev_id,
        "calendar_id": cal,
        "start": inicio,
        "end": fim,
        "all_day": False,
        "status": "confirmed",
        "gp_key": "gp:%s/%s" % (task, inst) if task else None,
        "summary": None,
        "description": None,
    }
    e.update(extra)
    return e


def inferir(blocos, eventos, agora=AGORA):
    return {
        i.task_id: i
        for i in inferencia.inferir(
            blocos, eventos, calendar_id_metas=METAS, calendar_id_primario=PRIMARIO, instalacao_id=INST, agora=agora
        )
    }


def test_intocado_vencido_vira_feita_presumida_e_nao_vencido_sem_sinal():
    b1 = bloco("01", datetime(2026, 9, 26, 9, 0, tzinfo=TZ))
    b2 = bloco("02", datetime(2026, 9, 28, 9, 0, tzinfo=TZ), 1.5, id="D-2026-09-28-02", calendar_event_id="evt-02")
    ev = [
        evento(
            "evt-01", "2026-09-26T09:10:00-03:00", "2026-09-26T10:00:00-03:00", "D-2026-09-26-01"
        ),  # 10 min: tolerância
        evento("evt-02", "2026-09-28T09:00:00-03:00", "2026-09-28T10:30:00-03:00", "D-2026-09-28-02"),
    ]
    r = inferir([b1, b2], ev)
    assert r["D-2026-09-26-01"].estado == "feita" and r["D-2026-09-26-01"].origem == "presumido"
    assert r["D-2026-09-26-01"].calendar_event_id == "evt-01" and r["D-2026-09-26-01"].calendar_id == METAS
    assert r["D-2026-09-28-02"].estado == "sem_sinal" and r["D-2026-09-28-02"].origem == "inferido"
    # exatamente no fim da janela conta como vencido
    r = inferir([b1], ev, agora=datetime(2026, 9, 26, 10, 0, tzinfo=TZ))
    assert r["D-2026-09-26-01"].estado == "feita"
    r = inferir([b1], ev, agora=datetime(2026, 9, 26, 9, 59, tzinfo=TZ))
    assert r["D-2026-09-26-01"].estado == "sem_sinal"


def test_movida_e_reagendada_com_nova_janela():
    b = bloco("02", datetime(2026, 9, 26, 10, 30, tzinfo=TZ))
    r = inferir([b], [evento("evt-02", "2026-09-26T15:00:00-03:00", "2026-09-26T16:00:00-03:00", "D-2026-09-26-02")])
    inf = r["D-2026-09-26-02"]
    assert inf.estado == "movida" and inf.origem == "inferido"
    assert inf.inicio.isoformat() == "2026-09-26T15:00:00-03:00" and inf.fim.isoformat() == "2026-09-26T16:00:00-03:00"
    assert "movido para 2026-09-26T15:00" in inf.motivo
    # 16 minutos: fora da tolerância de 15
    r = inferir([b], [evento("evt-02", "2026-09-26T10:46:00-03:00", "2026-09-26T11:46:00-03:00", "D-2026-09-26-02")])
    assert r["D-2026-09-26-02"].estado == "movida"
    # outro dia (mesmo horário): reagendada; fim ausente usa a duração do bloco
    r = inferir([b], [evento("evt-02", "2026-09-29T10:30:00-03:00", "", "D-2026-09-26-02")])
    inf = r["D-2026-09-26-02"]
    assert inf.estado == "reagendada" and inf.fim.isoformat() == "2026-09-29T11:30:00-03:00"
    # comparação em UTC: mesmo instante em outro offset é intocado
    r = inferir(
        [b],
        [evento("evt-02", "2026-09-26T13:30:00+00:00", "2026-09-26T14:30:00+00:00", "D-2026-09-26-02")],
        agora=datetime(2026, 9, 26, 9, 0, tzinfo=TZ),
    )
    assert r["D-2026-09-26-02"].estado == "sem_sinal"
    # dia inteiro no mesmo dia: movida (dia inteiro)
    r = inferir([b], [evento("evt-02", "2026-09-26", "2026-09-27", "D-2026-09-26-02", all_day=True)])
    assert r["D-2026-09-26-02"].estado == "movida" and "dia inteiro" in r["D-2026-09-26-02"].motivo


def test_apagada_cancelada_e_movida_para_o_primario():
    b4 = bloco("04", datetime(2026, 9, 26, 14, 0, tzinfo=TZ))
    b5 = bloco("05", datetime(2026, 9, 26, 16, 0, tzinfo=TZ))
    b6 = bloco("06", datetime(2026, 9, 26, 17, 30, tzinfo=TZ))
    ev = [
        evento(
            "evt-06", "2026-09-26T17:30:00-03:00", "2026-09-26T18:30:00-03:00", "D-2026-09-26-06", status="cancelled"
        ),
        evento("evt-05-p", "2026-09-26T16:00:00-03:00", "2026-09-26T17:00:00-03:00", "D-2026-09-26-05", cal=PRIMARIO),
        evento(
            "evt-x",
            "2026-09-26T14:00:00-03:00",
            "2026-09-26T15:00:00-03:00",
            "D-2026-09-26-04",
            cal=PRIMARIO,
            inst="outra",
        ),
    ]
    r = inferir([b4, b5, b6], ev)
    assert r["D-2026-09-26-04"].estado == "apagada" and r["D-2026-09-26-04"].motivo == "evento ausente do Metas"
    assert r["D-2026-09-26-06"].estado == "apagada"  # cancelled conta como ausente
    inf = r["D-2026-09-26-05"]
    assert inf.estado == "movida" and inf.calendar_id == PRIMARIO and inf.calendar_event_id == "evt-05-p"
    assert "calendário primário" in inf.motivo
    # movido para o primário E para outro dia: reagendada
    r = inferir(
        [b5],
        [evento("evt-05-p", "2026-09-30T16:00:00-03:00", "2026-09-30T17:00:00-03:00", "D-2026-09-26-05", cal=PRIMARIO)],
    )
    assert r["D-2026-09-26-05"].estado == "reagendada" and r["D-2026-09-26-05"].calendar_id == PRIMARIO


def test_id_recuperado_por_gp_key_sem_evento_e_bloco_confirmado():
    sem_id = bloco("07", datetime(2026, 9, 26, 9, 0, tzinfo=TZ), calendar_event_id=None)
    sem_nada = bloco("08", datetime(2026, 9, 26, 9, 0, tzinfo=TZ), calendar_event_id=None)
    confirmado = bloco("09", datetime(2026, 9, 26, 9, 0, tzinfo=TZ), estado="feita", origem="confirmado")
    final = bloco("10", datetime(2026, 9, 26, 9, 0, tzinfo=TZ), estado="apagada")
    ev = [evento("evt-novo", "2026-09-26T09:00:00-03:00", "2026-09-26T10:00:00-03:00", "D-2026-09-26-07")]
    r = inferir([sem_id, sem_nada, confirmado, final], ev)
    assert set(r) == {"D-2026-09-26-07"}
    assert r["D-2026-09-26-07"].estado == "feita" and r["D-2026-09-26-07"].calendar_event_id == "evt-novo"
    # evento sem gp_key válida nunca é reconhecido, mesmo com [GP] no título
    ev = [evento("evt-y", "2026-09-26T09:00:00-03:00", "2026-09-26T10:00:00-03:00", None, summary="[GP] Bloco 07")]
    assert inferir([sem_id], ev) == {}
    # id do bloco casa evento que perdeu a chave na descrição: continua sendo pelo id
    com_id = bloco("11", datetime(2026, 9, 26, 9, 0, tzinfo=TZ))
    ev = [evento("evt-11", "2026-09-26T09:00:00-03:00", "2026-09-26T10:00:00-03:00", None)]
    assert inferir([com_id], ev)["D-2026-09-26-11"].estado == "feita"


def test_janela_dos_blocos():
    b1 = bloco("01", datetime(2026, 9, 26, 9, 0, tzinfo=TZ))
    b2 = bloco("02", datetime(2026, 9, 30, 9, 0, tzinfo=TZ))
    inicio, fim = inferencia.janela_dos_blocos([b1, b2], AGORA)
    assert inicio == b1["inicio"] - timedelta(days=7) and fim == b2["fim"] + timedelta(days=7)
    inicio, fim = inferencia.janela_dos_blocos([], AGORA)
    assert inicio == AGORA - timedelta(days=7) and fim == AGORA + timedelta(days=7)
    assert inferencia.gp_key("D-2026-09-26-01", INST) == "gp:D-2026-09-26-01/inst-fixture-01"


# --- caracterização de cada ramo de inferir (antes de dividir a função, D-06) --------------------------------------------


def test_cada_ramo_de_inferir():
    ontem = datetime(2026, 9, 27, 9, 0, tzinfo=TZ)
    amanha = datetime(2026, 9, 29, 9, 0, tzinfo=TZ)
    blocos = [
        bloco("01", ontem, estado="feita"),  # estado final: pula
        bloco("02", ontem, origem="confirmado"),  # confirmado: pula
        bloco("03", ontem),  # evento pelo id, intocado e vencido
        bloco("04", ontem, calendar_event_id=None),  # evento pela gp_key
        bloco("05", amanha, estado="movida"),  # já movido e janela nova não venceu: segue movido
        bloco("06", ontem, calendar_event_id="sumiu"),  # no primário no mesmo horário: moveu de calendário
        bloco("07", ontem, calendar_event_id="sumiu", calendar_id=PRIMARIO),  # já estava no primário: feita
        bloco(
            "08", amanha, estado="reagendada", calendar_event_id="sumiu", calendar_id=PRIMARIO
        ),  # primário, sem sinal
        bloco("09", ontem),  # tinha evento e sumiu: apagada
        bloco("10", ontem, calendar_event_id=None),  # nunca criado: sem inferência
        bloco("11", ontem, calendar_event_id="cancelado"),  # evento cancelado conta como ausente: apagada
        bloco("12", ontem),  # no primário outro dia: reagendada
    ]
    eventos = [
        evento("evt-03", "2026-09-27T09:05:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-03"),
        evento("outro-id", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-04"),
        evento("evt-05", "2026-09-29T09:00:00-03:00", "2026-09-29T10:00:00-03:00", "D-2026-09-26-05"),
        evento("p-06", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-06", cal=PRIMARIO),
        evento("p-07", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-07", cal=PRIMARIO),
        evento("p-08", "2026-09-29T09:00:00-03:00", "2026-09-29T10:00:00-03:00", "D-2026-09-26-08", cal=PRIMARIO),
        evento(
            "cancelado", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-11", status="cancelled"
        ),
        evento("p-12", "2026-09-28T15:00:00-03:00", "2026-09-28T16:00:00-03:00", "D-2026-09-26-12", cal=PRIMARIO),
        "lixo",
    ]
    obtido = inferir(blocos, eventos)
    assert {k: (v.estado, v.origem, v.motivo, v.calendar_event_id, v.calendar_id) for k, v in obtido.items()} == {
        "D-2026-09-26-03": ("feita", "presumido", "intocado e vencido", "evt-03", METAS),
        "D-2026-09-26-04": ("feita", "presumido", "intocado e vencido", "outro-id", METAS),
        "D-2026-09-26-06": ("movida", "inferido", "movido para o calendário primário", "p-06", PRIMARIO),
        "D-2026-09-26-07": ("feita", "presumido", "intocado e vencido", "p-07", PRIMARIO),
        "D-2026-09-26-09": ("apagada", "inferido", "evento ausente do Metas", "evt-09", METAS),
        "D-2026-09-26-11": ("apagada", "inferido", "evento ausente do Metas", "cancelado", METAS),
        "D-2026-09-26-12": ("reagendada", "inferido", "reagendado para 2026-09-28T15:00-03:00", "p-12", PRIMARIO),
    }


def test_inferencia_inteira_nos_casos_de_borda():
    """Cada campo da Inferencia (motivo, id, calendário, janela nova) nos casos que só o estado não prende."""
    base = datetime(2026, 9, 27, 9, 0, tzinfo=TZ)
    fim = base + timedelta(hours=1)
    blocos = [
        bloco("01", base, estado="sem_sinal"),  # sem_sinal ainda é aberto
        bloco("02", base, estado="reagendada"),  # reagendada também
        bloco("03", base),  # evento sem início legível
        bloco("04", base),  # dia inteiro no mesmo dia: movido, com a marca
        bloco("05", base),  # fim ausente: a duração do bloco é mantida
        bloco("06", base),  # fim antes do início: idem
        bloco("07", base),  # exatamente 15 min depois: ainda intocado
        bloco("08", base),  # 16 min depois: movido
        bloco("09", base, calendar_event_id=""),  # id vazio vale como sem id
    ]
    metas = [
        evento("evt-01", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-01"),
        evento("evt-02", "2026-09-30T14:00:00-03:00", "2026-09-30T15:30:00-03:00", "D-2026-09-26-02"),
        evento("evt-03", None, None, "D-2026-09-26-03"),
        evento("evt-04", "2026-09-27", "2026-09-28", "D-2026-09-26-04", all_day=True),
        evento("evt-05", "2026-09-27T11:00:00-03:00", None, "D-2026-09-26-05"),
        evento("evt-06", "2026-09-27T12:00:00-03:00", "2026-09-27T11:00:00-03:00", "D-2026-09-26-06"),
        evento("evt-07", "2026-09-27T09:15:00-03:00", "2026-09-27T10:15:00-03:00", "D-2026-09-26-07"),
        evento("evt-08", "2026-09-27T09:16:00-03:00", "2026-09-27T10:16:00-03:00", "D-2026-09-26-08"),
        evento("", "2026-09-27T09:00:00-03:00", "2026-09-27T10:00:00-03:00", "D-2026-09-26-09"),
    ]
    obtido = inferir(blocos, metas)
    assert obtido["D-2026-09-26-01"] == inferencia.Inferencia(
        "D-2026-09-26-01", "feita", "presumido", "intocado e vencido", "evt-01", METAS, base, fim
    )
    assert obtido["D-2026-09-26-02"] == inferencia.Inferencia(
        "D-2026-09-26-02",
        "reagendada",
        "inferido",
        "reagendado para 2026-09-30T14:00-03:00",
        "evt-02",
        METAS,
        datetime(2026, 9, 30, 14, 0, tzinfo=TZ),
        datetime(2026, 9, 30, 15, 30, tzinfo=TZ),
    )
    assert obtido["D-2026-09-26-03"] == inferencia.Inferencia(
        "D-2026-09-26-03", "sem_sinal", "inferido", "evento sem início legível", "evt-03", METAS
    )
    dia_inteiro = datetime(2026, 9, 27, 0, 0, tzinfo=TZ)
    assert obtido["D-2026-09-26-04"] == inferencia.Inferencia(
        "D-2026-09-26-04",
        "movida",
        "inferido",
        "movido para 2026-09-27T00:00-03:00 (dia inteiro)",
        "evt-04",
        METAS,
        dia_inteiro,
        datetime(2026, 9, 28, 0, 0, tzinfo=TZ),
    )
    onze = datetime(2026, 9, 27, 11, 0, tzinfo=TZ)
    assert obtido["D-2026-09-26-05"][6:] == (onze, onze + timedelta(hours=1))
    doze = datetime(2026, 9, 27, 12, 0, tzinfo=TZ)
    assert obtido["D-2026-09-26-06"][6:] == (doze, doze + timedelta(hours=1))
    assert obtido["D-2026-09-26-07"][1:4] == ("feita", "presumido", "intocado e vencido")
    assert obtido["D-2026-09-26-08"][1] == "movida"
    assert obtido["D-2026-09-26-09"][4] is None  # evento sem id: a inferência não inventa id
    vivo = inferir(
        [bloco("10", AGORA + timedelta(hours=1))],
        [
            evento(
                "evt-10",
                (AGORA + timedelta(hours=1)).isoformat(),
                (AGORA + timedelta(hours=2)).isoformat(),
                "D-2026-09-26-10",
            )
        ],
    )
    assert vivo["D-2026-09-26-10"] == inferencia.Inferencia(
        "D-2026-09-26-10",
        "sem_sinal",
        "inferido",
        "intocado, janela não venceu",
        "evt-10",
        METAS,
        AGORA + timedelta(hours=1),
        AGORA + timedelta(hours=2),
    )


def test_mesmo_dia_no_fuso_do_bloco_e_indice_de_eventos():
    toquio = ZoneInfo("Asia/Tokyo")
    noite = datetime(2026, 9, 27, 23, 30, tzinfo=toquio)  # 14:30 UTC do mesmo dia
    madrugada = "2026-09-28T00:10:00+09:00"  # 40 min depois, já no dia seguinte em Tóquio
    obtido = inferir(
        [bloco("01", noite)], [evento("evt-01", madrugada, "2026-09-28T01:10:00+09:00", "D-2026-09-26-01")]
    )
    assert obtido["D-2026-09-26-01"][1:4] == ("reagendada", "inferido", "reagendado para 2026-09-28T00:10+09:00")
    por_id, por_chave = inferencia._indexar(
        [
            "lixo",
            {"id": "a", "calendar_id": METAS, "gp_key": "gp:D-2026-09-26-01/%s" % INST},
            {"id": "b", "calendar_id": METAS, "gp_key": "gp:D-2026-09-26-01/%s" % INST},  # a primeira chave vence
            {"id": "c", "gp_key": "gp:D-2026-09-26-02/%s" % INST},  # sem calendário: não é do Metas
            {"id": "d", "calendar_id": METAS, "gp_key": "texto livre"},
        ]
    )
    assert set(por_id) == {(METAS, "a"), (METAS, "b"), ("", "c"), (METAS, "d")}
    assert por_chave == {
        (METAS, "gp:D-2026-09-26-01/%s" % INST): {
            "id": "a",
            "calendar_id": METAS,
            "gp_key": "gp:D-2026-09-26-01/%s" % INST,
        },
        ("", "gp:D-2026-09-26-02/%s" % INST): {"id": "c", "gp_key": "gp:D-2026-09-26-02/%s" % INST},
    }


def test_dia_inteiro_no_inicio_fim_igual_e_futuro_no_primario():
    meia_noite = datetime(2026, 9, 27, 0, 5, tzinfo=TZ)
    futuro = AGORA + timedelta(hours=2)
    blocos = [
        bloco("01", meia_noite),  # evento de dia inteiro a 5 min do bloco: não é intocado
        bloco("02", datetime(2026, 9, 27, 9, 0, tzinfo=TZ)),  # fim igual ao início: mantém a duração do bloco
        bloco("03", futuro, calendar_event_id="sumiu"),  # no primário e a janela não venceu: moveu de calendário
    ]
    eventos = [
        evento("evt-01", "2026-09-27", "2026-09-28", "D-2026-09-26-01", all_day=True),
        evento("evt-02", "2026-09-27T11:00:00-03:00", "2026-09-27T11:00:00-03:00", "D-2026-09-26-02"),
        evento("p-03", futuro.isoformat(), (futuro + timedelta(hours=1)).isoformat(), "D-2026-09-26-03", cal=PRIMARIO),
    ]
    obtido = inferir(blocos, eventos)
    assert obtido["D-2026-09-26-01"][1:4] == ("movida", "inferido", "movido para 2026-09-27T00:00-03:00 (dia inteiro)")
    assert obtido["D-2026-09-26-02"][7] == datetime(2026, 9, 27, 12, 0, tzinfo=TZ)
    assert obtido["D-2026-09-26-03"][1:6] == (
        "movida",
        "inferido",
        "movido para o calendário primário",
        "p-03",
        PRIMARIO,
    )
