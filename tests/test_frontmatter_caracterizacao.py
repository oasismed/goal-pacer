"""Caracterização da coerção do front-matter antes da refatoração: um caso por ramo de cada tipo."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from goalpacer import frontmatter
from goalpacer.schema import Campo

UTC3 = timezone(timedelta(hours=-3))


@pytest.mark.parametrize(
    ("campo", "valor", "esperado"),
    [
        (Campo("x", "str"), "a", ("a", None)),
        (Campo("x", "str"), 7, ("7", None)),
        (Campo("x", "str"), True, (True, "esperado str, veio bool True")),
        (Campo("x", "int"), 3, (3, None)),
        (Campo("x", "int"), 3.0, (3, None)),
        (Campo("x", "int"), " -4 ", (-4, None)),
        (Campo("x", "int"), 3.5, (3.5, "esperado int, veio float 3.5")),
        (Campo("x", "int"), False, (False, "esperado int, veio bool False")),
        (Campo("x", "float"), 2, (2.0, None)),
        (Campo("x", "float"), "1.5e2", (150.0, None)),
        (Campo("x", "float"), "um", ("um", "esperado float, veio str 'um'")),
        (Campo("x", "bool"), True, (True, None)),
        (Campo("x", "bool"), " FALSE ", (False, None)),
        (Campo("x", "bool"), "sim", ("sim", "esperado bool, veio str 'sim'")),
        (Campo("x", "date"), datetime(2026, 9, 28, 7, tzinfo=UTC3), (date(2026, 9, 28), None)),
        (Campo("x", "date"), date(2026, 9, 28), (date(2026, 9, 28), None)),
        (Campo("x", "date"), "2026-09-28", (date(2026, 9, 28), None)),
        (Campo("x", "date"), "2026-02-30", ("2026-02-30", "data inválida: '2026-02-30'")),
        (Campo("x", "date"), 20260928, (20260928, "esperado date, veio int 20260928")),
        (Campo("x", "datetime"), datetime(2026, 9, 28, 7, tzinfo=UTC3), (datetime(2026, 9, 28, 7, tzinfo=UTC3), None)),
        (Campo("x", "datetime"), "2026-09-28T07:00:00-03:00", (datetime(2026, 9, 28, 7, tzinfo=UTC3), None)),
        (Campo("x", "datetime"), 5, (5, "esperado datetime, veio int 5")),
        (Campo("x", "enum"), "a", ("a", "esquema sem valores de enum")),
        (Campo("x", "enum", enum=("a", "b")), "b", ("b", None)),
        (Campo("x", "enum", enum=("a", "b")), "c", ("c", "valor 'c' fora de {a, b}")),
        (Campo("x", "list"), ("a", "b"), (["a", "b"], None)),
        (Campo("x", "list"), "a", ("a", "esperado list, veio str 'a'")),
        (Campo("x", "list", enum=("a",)), ["a", "z", 3], (["a", "z", 3], "itens 'z', 3 fora de {a}")),
        (Campo("x", "list"), ["a", 3], (["a", 3], "itens 3 não são str")),
        (Campo("x", "dict"), {"a": 1}, ({"a": 1}, None)),
        (Campo("x", "dict"), [], ([], "esperado dict, veio list []")),
        (Campo("x", "list_dict"), ({"a": 1},), (({"a": 1},), "esperado list_dict, veio tuple ({'a': 1},)")),
        (Campo("x", "list_dict"), [{"a": 1}], ([{"a": 1}], None)),
        (Campo("x", "list_dict"), [{"a": 1}, 2], ([{"a": 1}, 2], "esperado list_dict, veio list [{'a': 1}, 2]")),
        (Campo("x", "complexo"), 1, (1, "tipo 'complexo' desconhecido no esquema")),
    ],
)
def test_coagir_valor_um_caso_por_ramo(campo, valor, esperado):
    assert frontmatter._coagir_valor(valor, campo) == esperado


def test_datetime_de_data_vira_meia_noite_no_fuso(monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setenv("GP_TZ", "America/Sao_Paulo")
    valor, motivo = frontmatter._coagir_valor(date(2026, 9, 28), Campo("x", "datetime"))
    assert motivo is None and valor == datetime(2026, 9, 28, tzinfo=ZoneInfo("America/Sao_Paulo"))
    assert frontmatter._coagir_valor("ontem", Campo("x", "datetime"))[1].startswith("datetime inválido: 'ontem' (")
