"""Testes de goalpacer.calendar_ops: corpo dos eventos, keep+diff, execução (stub e offline), reparo, desinstalar."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from goalpacer import calendar_ops as co, proxy, schema
from goalpacer.base import GpErro

TZ = ZoneInfo("America/Sao_Paulo")
DIA = date(2026, 9, 28)
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
METAS = "metas-fixture@group.calendar.google.com"
CONTEXTO = {
    "calendar_id_metas": METAS,
    "calendar_id_primario": "pessoa@exemplo.test",
    "instalacao_id": "inst-fixture-01",
    "timezone": "America/Sao_Paulo",
    "lembretes": "nao",
}


def bloco(sufixo: str, hora: int, estado: str = "planejada", **extra) -> dict:
    inicio = datetime(2026, 9, 28, hora, 0, tzinfo=TZ)
    b = {
        "id": "D-2026-09-28-" + sufixo,
        "titulo": "Bloco " + sufixo,
        "meta": "M01",
        "semana": "2026-W40",
        "inicio": inicio,
        "fim": inicio + timedelta(hours=1),
        "duracao_h": 1.0,
        "porque": "porquê",
        "efeito": "se feita: M1 1% → 2%",
        "estado": estado,
        "origem": "inferido",
    }
    b.update(extra)
    return b


def evento(ev_id: str, task: str, hora: int, created: str = "2026-09-27T07:00:00Z", **extra) -> dict:
    inicio = datetime(2026, 9, 28, hora, 0, tzinfo=TZ)
    e = {
        "id": ev_id,
        "calendar_id": METAS,
        "start": inicio.isoformat(),
        "end": (inicio + timedelta(hours=1)).isoformat(),
        "all_day": False,
        "status": "confirmed",
        "gp_key": "gp:%s/inst-fixture-01" % task if task else None,
        "created": created,
        "summary": "[GP] x",
        "description": "porquê\ngp:%s/inst-fixture-01" % task if task else "sem chave",
    }
    e.update(extra)
    return e


def test_corpo_dos_eventos():
    b = bloco("01", 9)
    assert co.titulo_evento("Bloco 01") == "[GP] Bloco 01"
    assert len(co.titulo_evento("x" * 100)) == 60
    assert (
        co.descricao_evento(b, "inst-fixture-01") == "porquê\nse feita: M1 1% → 2%\ngp:D-2026-09-28-01/inst-fixture-01"
    )
    assert co.descricao_evento(dict(b, porque="", efeito=""), "i").split("\n") == ["gp:D-2026-09-28-01/i"]
    args = co.args_create(b, CONTEXTO)
    assert args == {
        "calendarId": METAS,
        "summary": "[GP] Bloco 01",
        "description": co.descricao_evento(b, "inst-fixture-01"),
        "start": "2026-09-28T09:00:00-03:00",
        "end": "2026-09-28T10:00:00-03:00",
        "timeZone": "America/Sao_Paulo",
        "overrideReminders": [],
        "notificationLevel": "NONE",
    }
    assert "overrideReminders" not in co.args_create(b, dict(CONTEXTO, lembretes="sim"))
    assert proxy.gp_key_de(args["description"]) == "gp:D-2026-09-28-01/inst-fixture-01"
    b["calendar_event_id"] = "evt-1"
    assert set(co.args_update(b, CONTEXTO, janela=False)) == {"calendarId", "eventId", "description"}
    assert set(co.args_update(b, CONTEXTO, janela=True)) == {
        "calendarId",
        "eventId",
        "description",
        "start",
        "end",
        "timeZone",
    }
    assert co.args_delete(METAS, "evt-1") == {"calendarId": METAS, "eventId": "evt-1"}


def test_planejar_ops_keep_diff():
    blocos = [
        bloco("01", 9),  # sem evento → create
        bloco("02", 10, calendar_event_id="evt-02"),  # evento igual → nada
        bloco("03", 11, calendar_event_id="evt-03"),  # evento em outro horário → update janela
        bloco("04", 12, calendar_event_id="evt-04"),  # evento sem gp_key → update descrição
        bloco("05", 13),  # sem id, mas evento com gp_key → adota e nada
        bloco("06", 14, estado="cancelada", calendar_event_id="evt-06"),  # cancelada → delete
        bloco("07", 15, estado="movida", calendar_event_id="evt-07"),  # movida → nada
        bloco("08", 16, estado="feita", origem="presumido", calendar_event_id="evt-08"),  # feita → nada
    ]
    eventos = [
        evento("evt-02", "D-2026-09-28-02", 10),
        evento("evt-03", "D-2026-09-28-03", 8),
        evento("evt-04", None, 12),
        evento("evt-05", "D-2026-09-28-05", 13),
        evento("evt-06", "D-2026-09-28-06", 14),
        evento("evt-07", "D-2026-09-28-07", 18),
        evento("evt-08", "D-2026-09-28-08", 16),
        evento("evt-orfao", "D-2026-09-27-05", 17),  # nosso, começa hoje, sem bloco → delete
        evento("evt-orfao-ontem", "D-2026-09-27-06", 17, start="2026-09-27T17:00:00-03:00"),  # começou ontem: fica
        evento(
            "evt-dup-a", "D-2026-09-28-02", 10, created="2026-09-27T09:00:00Z"
        ),  # duplicata do 02 (mais nova) → delete
        evento(
            "evt-outra", "D-2026-09-28-01", 9, gp_key="gp:D-2026-09-28-01/outra", description="gp:D-2026-09-28-01/outra"
        ),
        evento("evt-cancelado", "D-2026-09-28-09", 9, status="cancelled"),
    ]
    doc = co.planejar_ops(blocos, eventos, CONTEXTO, run_id="r1", agora=AGORA, dia=DIA)
    assert schema.validar_registro("ops", doc) == []
    resumo = [(op["op"], op["task_id"], op.get("calendar_event_id")) for op in doc["ops"]]
    assert resumo == [
        ("create", "D-2026-09-28-01", None),
        ("update", "D-2026-09-28-03", "evt-03"),
        ("update", "D-2026-09-28-04", "evt-04"),
        ("delete", "D-2026-09-28-06", "evt-06"),
        ("delete", "D-2026-09-27-05", "evt-orfao"),
        ("delete", "D-2026-09-28-02", "evt-dup-a"),
    ]
    assert "start" in doc["ops"][1]["corpo"] and "start" not in doc["ops"][2]["corpo"]
    assert blocos[4]["calendar_event_id"] == "evt-05" and blocos[4]["calendar_id"] == METAS
    assert all(op["calendar_id"] == METAS for op in doc["ops"])


def test_executar_ops_stub_reparo_e_aplicar():
    blocos = [bloco("01", 9), bloco("02", 10, calendar_event_id="evt-02")]
    doc = co.planejar_ops(blocos, [evento("evt-02", "D-2026-09-28-02", 8)], CONTEXTO, run_id="r1", agora=AGORA, dia=DIA)
    chamadas = []

    def chamar(tool, corpo):
        chamadas.append((tool.rsplit("__", 1)[-1], corpo.get("eventId")))
        if tool.endswith("create_event"):
            return {"id": "evt-novo"}
        if tool.endswith("update_event"):
            raise proxy.ErroConector("Insufficient scope: required calendar.events")
        return {}

    co.executar_ops(doc, calendar_id_metas=METAS, chamar=chamar)
    assert [op["status"] for op in doc["ops"]] == ["ok", "erro"]
    assert doc["ops"][0]["event_id_resultado"] == "evt-novo" and "Insufficient scope" in doc["ops"][1]["mensagem"]
    com_erro = co.aplicar_resultados(blocos, doc, METAS)
    assert com_erro == ["D-2026-09-28-02"]
    assert blocos[0]["calendar_event_id"] == "evt-novo" and blocos[0]["calendar_id"] == METAS
    reparo = co.ops_de_reparo(doc, "r1", AGORA)
    assert [op["task_id"] for op in reparo["ops"]] == ["D-2026-09-28-02"] and "status" not in reparo["ops"][0]
    assert schema.validar_registro("ops", reparo) == []
    # create sem id na resposta é erro; ops já ok não rodam de novo
    doc2 = co.planejar_ops([bloco("03", 11)], [], CONTEXTO, run_id="r2", agora=AGORA, dia=DIA)
    co.executar_ops(doc2, calendar_id_metas=METAS, chamar=lambda tool, corpo: {})
    assert doc2["ops"][0]["status"] == "erro"
    chamadas.clear()
    co.executar_ops(doc, calendar_id_metas=METAS, chamar=chamar)
    assert chamadas == [("update_event", "evt-02")]


def test_delete_de_evento_ja_apagado_nao_e_erro():
    blocos = [bloco("01", 9, calendar_event_id="evt-a"), bloco("02", 10, calendar_event_id="evt-b")]
    doc = co.planejar_ops(
        [],
        [evento("evt-a", "D-2026-09-28-01", 9), evento("evt-b", "D-2026-09-28-02", 10)],
        CONTEXTO,
        run_id="r1",
        agora=AGORA,
        dia=DIA,
    )
    assert [op["op"] for op in doc["ops"]] == ["delete", "delete"]

    def chamar(tool, corpo):
        if corpo["eventId"] == "evt-a":
            raise proxy.ErroConector("Event evt-a could not be found or has been deleted")
        raise proxy.ErroConector("Insufficient scope: required calendar.events")

    co.executar_ops(doc, calendar_id_metas=METAS, chamar=chamar)
    assert [op["status"] for op in doc["ops"]] == ["ok", "erro"]
    assert "mensagem" not in doc["ops"][0] and "Insufficient scope" in doc["ops"][1]["mensagem"]
    assert co.aplicar_resultados(blocos, doc, METAS) == ["D-2026-09-28-02"]
    assert [op["task_id"] for op in co.ops_de_reparo(doc, "r1", AGORA)["ops"]] == ["D-2026-09-28-02"]


def test_executar_ops_offline_com_sombra(dados_tmp, agora_fixo):
    blocos = [bloco("01", 9), bloco("02", 10)]
    doc = co.planejar_ops(blocos, [], CONTEXTO, run_id="r1", agora=AGORA, dia=DIA)
    co.executar_ops(doc, calendar_id_metas=METAS, modo_offline=True)
    assert [op["status"] for op in doc["ops"]] == ["ok", "ok"]
    assert doc["ops"][0]["event_id_resultado"] == "off-D-2026-09-28-01"
    co.aplicar_resultados(blocos, doc, METAS)
    # a sombra faz a leitura offline enxergar os eventos criados (fixtures ausentes → só a sombra)
    inicio = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    eventos = co.ler_eventos(METAS, inicio, inicio + timedelta(days=1), calendar_id_metas=METAS, modo_offline=True)
    assert sorted(e["id"] for e in eventos) == ["off-D-2026-09-28-01", "off-D-2026-09-28-02"]
    assert eventos[0]["gp_key"] == "gp:D-2026-09-28-01/inst-fixture-01" and eventos[0]["summary"] == "[GP] Bloco 01"
    assert (
        co.ler_eventos(
            METAS, inicio + timedelta(days=1), inicio + timedelta(days=2), calendar_id_metas=METAS, modo_offline=True
        )
        == []
    )
    # segunda rodada: nada a fazer
    doc2 = co.planejar_ops(blocos, eventos, CONTEXTO, run_id="r2", agora=AGORA, dia=DIA)
    assert doc2["ops"] == []
    # update e delete simulados
    blocos[0]["inicio"] += timedelta(hours=1)
    blocos[0]["fim"] += timedelta(hours=1)
    blocos[1]["estado"] = "cancelada"
    doc3 = co.planejar_ops(blocos, eventos, CONTEXTO, run_id="r3", agora=AGORA, dia=DIA)
    assert [op["op"] for op in doc3["ops"]] == ["update", "delete"]
    co.executar_ops(doc3, calendar_id_metas=METAS, modo_offline=True)
    eventos = co.ler_eventos(METAS, inicio, inicio + timedelta(days=1), calendar_id_metas=METAS, modo_offline=True)
    assert [(e["id"], e["start"][11:16], e["status"]) for e in eventos] == [
        ("off-D-2026-09-28-01", "10:00", "confirmed"),
        ("off-D-2026-09-28-02", "10:00", "cancelled"),
    ]
    assert (
        json.loads((dados_tmp / "cache" / "offline-eventos.json").read_text(encoding="utf-8"))["off-D-2026-09-28-02"][
            "status"
        ]
        == "cancelled"
    )


def test_ops_desinstalar_so_da_propria_instalacao():
    eventos = [
        evento("e1", "D-2026-09-28-01", 9),
        evento("e2", "D-2026-09-27-01", 10),
        evento("e3", None, 11),
        evento("e4", "D-2026-09-28-02", 12, gp_key="gp:D-2026-09-28-02/outra"),
    ]
    doc = co.ops_desinstalar(eventos, CONTEXTO, run_id="d1", agora=AGORA)
    assert [(op["op"], op["calendar_event_id"]) for op in doc["ops"]] == [("delete", "e1"), ("delete", "e2")]
    assert schema.validar_registro("ops", doc) == []


def test_executar_ops_recusa_escrita_fora_do_metas():
    blocos = [bloco("01", 9), bloco("02", 10)]
    doc = co.planejar_ops(blocos, [], CONTEXTO, run_id="r1", agora=AGORA, dia=DIA)
    doc["ops"][1]["corpo"]["calendarId"] = "pessoa@exemplo.test"
    chamadas = []
    co.executar_ops(
        doc, calendar_id_metas=METAS, chamar=lambda tool, corpo: chamadas.append(corpo["calendarId"]) or {"id": "evt-x"}
    )
    assert chamadas == [METAS]
    assert doc["ops"][1]["status"] == "erro" and "fora do calendário Metas" in doc["ops"][1]["mensagem"]
    with pytest.raises(GpErro):
        co.executar_ops(doc, calendar_id_metas="")


def test_lista_de_calendarios_uma_vez_por_dia_no_modo_vivo(tmp_path, monkeypatch):
    """P2 (análise de 13/09): mensal e diário do mesmo job reaproveitam o list_calendars; sem o Metas na lista, lista de novo."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from goalpacer import calendar_ops, proxy

    chamadas = []
    respostas = [
        {"calendars": [{"id": "eu@exemplo.test", "summary": "Eu", "timeZone": "America/Sao_Paulo", "extra": "x"}]},
        {"calendars": [{"id": "eu@exemplo.test"}, {"id": "metas@group.calendar.google.com", "summary": "Metas"}]},
    ]
    monkeypatch.setattr(proxy, "chamar", lambda tool, args, **_: chamadas.append(tool) or respostas[len(chamadas) - 1])
    agora = datetime(2026, 9, 28, 7, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    primeira = calendar_ops.listar_calendarios(tmp_path, modo_offline=False, agora=agora)
    assert primeira == [{"id": "eu@exemplo.test", "summary": "Eu", "timeZone": "America/Sao_Paulo"}]
    assert calendar_ops.listar_calendarios(tmp_path, modo_offline=False, agora=agora) == primeira and len(chamadas) == 1
    nova = calendar_ops.listar_calendarios(
        tmp_path, modo_offline=False, agora=agora, calendar_id_metas="metas@group.calendar.google.com"
    )
    assert len(chamadas) == 2 and [c["id"] for c in nova] == ["eu@exemplo.test", "metas@group.calendar.google.com"]
    assert (tmp_path / "cache" / "calendar-lista-2026-09-28.json").exists()


# --- D-11: o que os mutantes sobreviventes mostraram sem teste -----------------------------------------------------------


def test_leitura_viva_passa_argumentos_projecao_e_registro(monkeypatch):
    inicio = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    fim = inicio + timedelta(days=1)
    capturado = {}

    def paginado(tool, args, **kw):
        capturado.update(tool=tool, args=dict(args), **kw)
        return [{"id": "x"}]

    monkeypatch.setattr(proxy, "chamar_paginado", paginado)
    registro: list = []
    assert co.ler_eventos(
        "pessoa@exemplo.test", inicio, fim, calendar_id_metas=METAS, full_text="[GP]", registro=registro
    ) == [{"id": "x"}]
    assert capturado["tool"] == co.TOOL_LIST_EVENTS and capturado["chave_lista"] == "events"
    assert capturado["args"] == {
        "calendarId": "pessoa@exemplo.test",
        "timeMin": inicio.isoformat(timespec="seconds"),
        "timeMax": fim.isoformat(timespec="seconds"),
        "fullText": "[GP]",
    }
    assert capturado["registro"] is registro
    bruto = {
        "id": "t",
        "summary": "reunião de terceiro",
        "description": "texto",
        "start": {"dateTime": inicio.isoformat()},
        "end": {"dateTime": fim.isoformat()},
    }
    projetado = capturado["projecao"]({"events": [bruto]})["events"][0]
    assert projetado["calendar_id"] == "pessoa@exemplo.test" and projetado["summary"] is None  # fora do Metas
    sem_termo = []
    co.ler_eventos(
        METAS,
        inicio,
        fim,
        calendar_id_metas=METAS,
        chamar=lambda tool, args: sem_termo.append((tool, args)) or {"events": [bruto, "lixo"]},
    )
    assert sem_termo[0][0] == co.TOOL_LIST_EVENTS and "fullText" not in sem_termo[0][1]
    assert (
        co.ler_eventos(METAS, inicio, fim, calendar_id_metas=METAS, chamar=lambda *_a: {"events": [bruto]})[0][
            "summary"
        ]
        == "reunião de terceiro"
    )
    assert co.ler_eventos(METAS, inicio, fim, calendar_id_metas=METAS, chamar=lambda *_a: {}) == []


def test_leitura_offline_usa_os_argumentos_e_a_sombra_por_janela_e_termo(dados_tmp, monkeypatch):
    inicio = datetime(2026, 9, 28, 0, 0, tzinfo=TZ)
    fim = inicio + timedelta(days=1)
    pedidos = []
    fixture = evento("fx-1", "D-2026-09-28-09", 9)
    monkeypatch.setattr(
        co.offline,
        "chamar",
        lambda tool, args: (
            pedidos.append((tool, args))
            or {
                "events": [
                    dict(fixture, start={"dateTime": fixture["start"]}, end={"dateTime": fixture["end"]}),
                    "lixo",
                ]
            }
        ),
    )
    sombra = {
        "fx-1": dict(evento("fx-1", "D-2026-09-28-09", 11), summary="[GP] trocado"),  # a sombra substitui a fixture
        "no-inicio": evento("no-inicio", "D-2026-09-28-01", 0, summary="[GP] a"),
        "no-fim": dict(evento("no-fim", "D-2026-09-28-02", 0), start=fim.isoformat(), summary="[GP] b"),
        "sem-termo": evento("sem-termo", "D-2026-09-28-03", 8, summary="outro"),
        "sem-resumo": evento("sem-resumo", "D-2026-09-28-05", 8, summary=None),
        "ilegivel": dict(evento("ilegivel", "D-2026-09-28-04", 8), start="ontem"),
        "outro-cal": dict(evento("outro-cal", "D-2026-09-28-06", 8), calendar_id="pessoa@exemplo.test"),
    }
    (dados_tmp / "cache").mkdir(exist_ok=True)
    (dados_tmp / "cache" / co.NOME_SOMBRA).write_text(json.dumps(sombra), encoding="utf-8")
    eventos = co.ler_eventos(METAS, inicio, fim, calendar_id_metas=METAS, modo_offline=True, full_text="[GP]")
    assert pedidos == [
        (
            co.TOOL_LIST_EVENTS,
            {
                "calendarId": METAS,
                "timeMin": inicio.isoformat(timespec="seconds"),
                "timeMax": fim.isoformat(timespec="seconds"),
                "fullText": "[GP]",
            },
        )
    ]
    assert sorted(e["id"] for e in eventos) == ["fx-1", "no-inicio"]  # início inclusivo, fim exclusivo, só com o termo
    assert next(e for e in eventos if e["id"] == "fx-1")["summary"] == "[GP] trocado"
    todos = co.ler_eventos(METAS, inicio, fim, calendar_id_metas=METAS, modo_offline=True)
    assert sorted(e["id"] for e in todos) == ["fx-1", "no-inicio", "sem-resumo", "sem-termo"]


def test_criacao_simulada_tem_a_forma_do_evento_projetado():
    sombra: dict = {}
    corpo = co.args_create(bloco("01", 9), CONTEXTO)
    op = {"op": "create", "task_id": "D-2026-09-28-01", "calendar_id": METAS, "corpo": corpo}
    co._simular_op(op, sombra)
    assert op["status"] == "ok" and op["event_id_resultado"] == "off-D-2026-09-28-01"
    assert sombra["off-D-2026-09-28-01"] == {
        "id": "off-D-2026-09-28-01",
        "calendar_id": METAS,
        "start": corpo["start"],
        "end": corpo["end"],
        "all_day": False,
        "status": "confirmed",
        "transparency": "opaque",
        "self_response": "",
        "event_type": "default",
        "recurring_event_id": "",
        "summary": corpo["summary"],
        "description": corpo["description"],
        "gp_key": "gp:D-2026-09-28-01/inst-fixture-01",
        "created": corpo["start"],
    }
    assert set(sombra["off-D-2026-09-28-01"]) <= {c.nome for c in schema.ESQUEMAS["evento"]}  # só campos do esquema
    vazio: dict = {}
    co._simular_op({"op": "create", "task_id": "D-2026-09-28-02", "calendar_id": METAS, "corpo": None}, vazio)
    assert vazio["off-D-2026-09-28-02"]["start"] == "" and vazio["off-D-2026-09-28-02"]["end"] == ""
    fantasma: dict = {}
    co._simular_op(
        {"op": "delete", "task_id": "D-2026-09-28-03", "calendar_id": METAS, "calendar_event_id": "sumido"}, fantasma
    )
    assert fantasma == {"sumido": {"id": "sumido", "calendar_id": METAS, "start": "", "end": "", "status": "cancelled"}}
    co._simular_op(
        {"op": "update", "task_id": "x", "calendar_event_id": "nao-existe", "corpo": {"start": "a"}}, fantasma
    )
    assert "nao-existe" not in fantasma


def test_execucao_viva_escreve_e_offline_sem_ops_nao_grava_sombra(dados_tmp, monkeypatch):
    with pytest.raises(GpErro, match="executar_ops sem calendar_id_metas") as erro:
        co.executar_ops({"ops": []}, calendar_id_metas="")
    assert erro.value.codigo == 3
    chamadas = []
    monkeypatch.setattr(proxy, "chamar", lambda tool, corpo, **kw: chamadas.append((tool, kw)) or {"id": "novo"})
    registro: list = []
    doc = co.planejar_ops([bloco("01", 9)], [], CONTEXTO, run_id="r", agora=AGORA, dia=DIA)
    co.executar_ops(doc, calendar_id_metas=METAS, registro=registro)
    assert chamadas == [(co.TOOL_POR_OP["create"], {"modo_leitura": False, "registro": registro})]
    co.executar_ops({"ops": []}, calendar_id_metas=METAS, modo_offline=True)
    co.executar_ops({}, calendar_id_metas=METAS, modo_offline=True)
    assert not (dados_tmp / "cache" / co.NOME_SOMBRA).exists()
    longo = co.planejar_ops([bloco("02", 10)], [], CONTEXTO, run_id="r", agora=AGORA, dia=DIA)

    def falha(*_a, **_k):
        raise GpErro(3, "x" * 300)

    co.executar_ops(longo, calendar_id_metas=METAS, chamar=falha)
    assert longo["ops"][0]["mensagem"] == "x" * 200
    sem_id = co.planejar_ops([bloco("03", 11)], [], CONTEXTO, run_id="r", agora=AGORA, dia=DIA)
    co.executar_ops(sem_id, calendar_id_metas=METAS, chamar=lambda *_a: ["nao", "e", "dict"])
    assert sem_id["ops"][0]["mensagem"] == "create_event sem id na resposta"


def test_casamento_por_chave_duplicatas_e_reparo():
    b = bloco("01", 9)
    antigo = evento("evt-velho", "D-2026-09-28-01", 9, created="2026-09-01T07:00:00Z")
    novo = evento("evt-novo", "D-2026-09-28-01", 9, created="2026-09-20T07:00:00Z")
    doc = co.planejar_ops([b], [novo, antigo], CONTEXTO, run_id="r", agora=AGORA, dia=DIA)
    assert b["calendar_event_id"] == "evt-velho"  # sem id guardado, casa com a chave mais antiga
    assert [(op["op"], op["calendar_event_id"]) for op in doc["ops"]] == [("delete", "evt-novo")]
    mesmo_created = [evento("b", "D-2026-09-28-02", 10, created="x"), evento("a", "D-2026-09-28-02", 10, created="x")]
    assert [e["id"] for e in co._sobras(mesmo_created, set(), orfao_de=None)] == ["b"]  # empate: fica o menor id
    sem_data = [
        evento("c", "D-2026-09-28-02", 10, created=None),
        evento("d", "D-2026-09-28-02", 10, created="2026-01-01"),
    ]
    assert [e["id"] for e in co._sobras(sem_data, set(), orfao_de=None)] == ["d"]
    reparo = co.ops_de_reparo(
        {"calendar_id_metas": METAS, "ops": [{"op": "create", "status": "erro", "mensagem": "m"}]}, "r2", AGORA
    )
    assert (
        reparo["ops"] == [{"op": "create"}] and co.ops_de_reparo({"calendar_id_metas": METAS}, "r3", AGORA)["ops"] == []
    )
    ingenuo = dict(bloco("04", 9), inicio=datetime(2026, 9, 28, 9, 0, tzinfo=TZ))
    assert co._mesma_janela(
        ingenuo, {"start": "2026-09-28T09:00:00", "end": "2026-09-28T10:00:00"}
    )  # sem fuso: o do bloco


def test_desinstalar_com_barras_no_id_e_eventos_estranhos():
    eventos = [
        {"id": "e1", "gp_key": "gp:D-2026-09-28-01/inst-fixture-01"},
        {"id": "e2", "gp_key": "gp:D-2026-09-28-02/x/inst-fixture-01"},
        "lixo",
        {"gp_key": "gp:D-2026-09-28-03/inst-fixture-01"},
    ]
    ops = co.ops_desinstalar(eventos, CONTEXTO, run_id="r", agora=AGORA)["ops"]
    assert [(op["task_id"], op["calendar_event_id"], op["corpo"]) for op in ops] == [
        ("D-2026-09-28-01", "e1", co.args_delete(METAS, "e1")),
        ("D-2026-09-28-02", "e2", co.args_delete(METAS, "e2")),
    ]


def test_lista_de_calendarios_viva_guarda_so_o_necessario(dados_tmp, monkeypatch):
    registro: list = []
    pedidos = []
    resposta = {
        "calendars": [
            {"id": METAS, "summary": "Metas", "timeZone": "America/Sao_Paulo", "accessRole": "owner"},
            {"summary": "sem id"},
            "lixo",
        ]
    }
    monkeypatch.setattr(proxy, "chamar", lambda tool, args, **kw: pedidos.append((tool, args, kw)) or resposta)
    lista = co.listar_calendarios(
        dados_tmp, modo_offline=False, agora=AGORA, calendar_id_metas=METAS, registro=registro
    )
    assert lista == [{"id": METAS, "summary": "Metas", "timeZone": "America/Sao_Paulo"}]
    assert pedidos == [(co.TOOL_LIST_CALENDARS, {}, {"registro": registro})]
    guardado = dados_tmp / "cache" / ("%s%s.json" % (co.PREFIXO_LISTA, AGORA.date().isoformat()))
    assert json.loads(guardado.read_text(encoding="utf-8")) == {"calendars": lista}
    monkeypatch.setattr(co.offline, "chamar", lambda tool, args: pedidos.append((tool, args)) or resposta)
    assert co.listar_calendarios(dados_tmp, modo_offline=True, agora=AGORA) == [resposta["calendars"][0]]
    assert pedidos[-1] == (co.TOOL_LIST_CALENDARS, {})
    monkeypatch.setattr(proxy, "chamar", lambda *_a, **_k: {})
    shutil = __import__("shutil")
    shutil.rmtree(dados_tmp / "cache")
    assert (
        co.listar_calendarios(dados_tmp, modo_offline=False, agora=AGORA) == [] and not (dados_tmp / "cache").exists()
    )
