"""Caracterização do schema antes da refatoração: cada checagem de coerência das tabelas declarativas (que a suíte
só via passar), os tipos que não tinham caso e as regras cruzadas nos dois lados."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from goalpacer import schema
from goalpacer.base import GpErro
from goalpacer.schema import Campo, RegraDict


def test_verificar_esquemas_acusa_cada_tabela_incoerente(monkeypatch):
    monkeypatch.setattr(
        schema,
        "ESQUEMAS",
        {
            "plano": [
                Campo("mes", "str"),
                Campo("mes", "str"),
                Campo("Nome-Ruim", "str"),
                Campo("x", "tipo_novo"),
                Campo("mapa", "dict"),
                Campo("lista", "list_dict"),
                Campo("cor", "enum", enum=()),
                Campo("nota", "str", enum=("a",)),
                Campo("tags", "list", enum=("a", "a")),
                Campo("n", "int", obrigatorio=True, default=1),
                Campo("m", "int", obrigatorio=False, default="dez"),
            ],
            "sem_caminho": [Campo("regras", "dict", obrigatorio=False), Campo("itens", "list_dict", obrigatorio=False)],
            "metas": [Campo("titulo", "str", no_hash=True)],
        },
    )
    monkeypatch.setattr(
        schema,
        "REGRAS_DICT",
        {
            ("sem_caminho", "fantasma"): RegraDict("formato_novo", valor_tipo="tipo_novo", valor_esquema="nenhum"),
            ("sem_caminho", "regras"): RegraDict("meta", objeto_esquema="nenhum"),
        },
    )
    monkeypatch.setattr(schema, "REGRAS_LISTA", {("plano", "mes"): "nenhum"})
    monkeypatch.setattr(schema, "FORMATOS", {("plano", "lista"): "formato_novo"})
    monkeypatch.setattr(schema, "TETOS_TEXTO", {("plano", "cor"): 10})
    monkeypatch.setattr(schema, "SECOES", {"plano": ("## A",)})
    monkeypatch.setattr(schema, "SECOES_CONDICIONAIS", {"plano": ("## B",)})
    monkeypatch.setattr(schema, "HASH_METAS_CAMPOS", ("titulo",))
    assert schema.verificar_esquemas() == [
        "plano.mes: repetido",
        "plano.Nome-Ruim: nome inválido para front-matter",
        "plano.x: tipo desconhecido 'tipo_novo'",
        "plano.mapa: dict não cabe em front-matter plano",
        "plano.mapa: dict sem regra em REGRAS_DICT",
        "plano.lista: list_dict não cabe em front-matter plano",
        "plano.lista: list_dict sem esquema em REGRAS_LISTA",
        "plano.cor: enum sem valores",
        "plano.nota: enum só vale para enum ou list",
        "plano.tags: enum com valores repetidos",
        "plano.n: obrigatório não tem default",
        "plano.m: default inválido (esperado int, veio str)",
        "sem_caminho: sem caminho em CAMINHOS",
        "sem_caminho.itens: list_dict sem esquema em REGRAS_LISTA",
        "REGRAS_DICT sem_caminho.fantasma: não é campo dict",
        "REGRAS_DICT sem_caminho.fantasma: formato de chave desconhecido",
        "REGRAS_DICT sem_caminho.fantasma: exatamente um modo (valor_tipo, valor_esquema, valor_lista_esquema, objeto_esquema, livre)",
        "REGRAS_DICT sem_caminho.fantasma: valor_tipo desconhecido",
        "REGRAS_DICT sem_caminho.fantasma: esquema desconhecido 'nenhum'",
        "REGRAS_DICT sem_caminho.regras: esquema desconhecido 'nenhum'",
        "REGRAS_DICT sem_caminho.regras: objeto não tem formato de chave",
        "REGRAS_LISTA plano.mes: não é campo list_dict",
        "REGRAS_LISTA plano.mes: esquema desconhecido 'nenhum'",
        "FORMATOS plano.lista: não é campo str",
        "FORMATOS plano.lista: formato desconhecido",
        "TETOS_TEXTO plano.cor: não é campo str",
        "SECOES_CONDICIONAIS plano: '## B' não está em SECOES",
        "HASH_METAS_CAMPOS: titulo está marcado no_hash",
    ]


@pytest.mark.parametrize(
    ("campo", "valor", "motivo"),
    [
        (Campo("x", "str"), 1, "esperado str, veio int"),
        (Campo("x", "int"), True, "esperado int, veio bool"),
        (Campo("x", "float"), "1", "esperado float, veio str"),
        (Campo("x", "bool"), 0, "esperado bool, veio int"),
        (Campo("x", "date"), datetime(2026, 9, 28, tzinfo=timezone.utc), "esperado date, veio datetime"),
        (Campo("x", "date"), "28/09/2026", "data inválida (AAAA-MM-DD): '28/09/2026'"),
        (Campo("x", "date"), 20260928, "esperado date, veio int"),
        (Campo("x", "date"), date(2026, 9, 28), None),
        (Campo("x", "datetime"), "2026-09-28", "datetime inválido (ISO 8601 com hora): '2026-09-28'"),
        (Campo("x", "datetime"), date(2026, 9, 28), "esperado datetime, veio date"),
        (Campo("x", "list"), "a", "esperado list, veio str"),
        (Campo("x", "list"), ["a", 1], "item 1 não é str"),
        (Campo("x", "list", enum=("a",)), ["b"], "item 'b' fora de a"),
        (Campo("x", "list"), ["a", "a"], "itens repetidos"),
        (Campo("x", "enum", enum=("a", "b")), 3, "esperado str, veio int"),
        (Campo("x", "enum", enum=("a", "b")), "c", "'c' fora de a, b"),
        (Campo("x", "enum"), "c", "'c' fora de "),
        (Campo("x", "dict"), [], "esperado dict, veio list"),
        (Campo("x", "dict"), {1: "a"}, "chave 1 não é str"),
        (Campo("x", "list_dict"), {}, "esperado list, veio dict"),
        (Campo("x", "list_dict"), [], None),
    ],
)
def test_validar_tipo_um_caso_por_ramo(campo, valor, motivo):
    assert schema._validar_tipo(campo, valor) == motivo


def test_validar_tipo_desconhecido_e_erro_do_esquema():
    with pytest.raises(GpErro, match="tipo desconhecido no esquema"):
        schema._validar_tipo(Campo("x", "complexo"), 1)


def test_regras_cruzadas_dos_dois_lados():
    cruzadas = schema._regras_cruzadas
    inicio = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
    assert cruzadas("task", {"inicio": inicio, "fim": inicio}, "") == ["fim: deve ser depois de inicio"]
    assert cruzadas("task", {"inicio": inicio, "fim": datetime(2026, 9, 28, 10, 0)}, "t.") == [
        "t.fim: inicio e fim precisam ter o mesmo tipo de fuso"
    ]
    assert cruzadas("task", {"inicio": inicio}, "") == []
    assert cruzadas("metas", {"custo_h_semana_min": 5, "custo_h_semana_max": 2}, "") == [
        "custo_h_semana_min: maior que custo_h_semana_max"
    ]
    assert cruzadas("metas", {"custo_h_semana_min": True, "custo_h_semana_max": 0}, "") == []
    assert cruzadas("evento", {"start": "amanhã", "end": "2026-09-29"}, "") == [
        "start: nem data AAAA-MM-DD nem datetime ISO: 'amanhã'"
    ]
    assert cruzadas("evento", {"start": "2026-09-28", "end": "2026-09-29", "all_day": False}, "") == [
        "all_day: deve ser true quando start é só data"
    ]
    assert cruzadas("evento", {"start": "2026-09-28T09:00:00Z", "all_day": True}, "") == [
        "all_day: deve ser false quando start é datetime"
    ]
    assert cruzadas("op", {"op": "delete"}, "") == ["calendar_event_id: obrigatório em update e delete"]
    assert cruzadas("op", {"op": "create"}, "") == []
    ops = {"calendar_id_metas": "m", "ops": [{"op": "create", "calendar_id": "outro"}, "lixo", {"op": "delete"}]}
    assert cruzadas("ops", ops, "") == ["ops[0].calendar_id: create só no calendário Metas"]
    cache = {
        "calendar_id_metas": "m",
        "eventos": [
            {"calendar_id": "outro", "summary": "x", "description": None},
            {"calendar_id": "m", "summary": "y"},
            3,
        ],
    }
    assert cruzadas("cache_calendar", cache, "") == ["eventos[0].summary: deve ser null fora do calendário Metas"]
    assert cruzadas("contexto", {"qualquer": 1}, "") == []
