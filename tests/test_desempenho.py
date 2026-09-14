"""Funções de aptidão de desempenho: contam leituras, não medem tempo (determinístico em qualquer máquina).

Com histórico longo o custo de uma tela é dominado por ler ``dias/*.md``: cada tela do painel, o status e o
check-in leem cada dia no máximo uma vez (análise de 13/09, P1: eram duas a três leituras por pedido).
"""

from __future__ import annotations

import os

import pytest

import checkin
import painel
import status
from goalpacer import clock, perfil as prf


@pytest.fixture
def demo(tmp_path, monkeypatch):
    import demo_painel

    for var in [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    dados = demo_painel.preparar(tmp_path)
    for var, valor in demo_painel.ambiente(tmp_path).items():
        monkeypatch.setenv(var, valor)
    return dados


@pytest.fixture
def leituras_de_dia(monkeypatch):
    contagem: dict[str, int] = {}
    original = prf._blocos_do_dia

    def contar(path):
        contagem[path.name] = contagem.get(path.name, 0) + 1
        return original(path)

    monkeypatch.setattr(prf, "_blocos_do_dia", contar)
    return contagem


@pytest.mark.parametrize(
    "tela",
    [
        painel.modelo,
        painel.modelo_metas,
        lambda dados, agora: painel.modelo_periodo(dados, agora, "ano"),
        painel.modelo_status,
        status.coletar,
    ],
    ids=["hoje", "metas", "periodo-ano", "status-painel", "status-terminal"],
)
def test_cada_tela_le_cada_dia_uma_vez(demo, leituras_de_dia, tela):
    tela(demo, clock.agora())
    dias = sorted(p.name for p in (demo / "dias").glob("*.md"))
    assert len(dias) > 30 and sorted(leituras_de_dia) == dias
    assert max(leituras_de_dia.values()) == 1, {d: n for d, n in leituras_de_dia.items() if n > 1}


def test_check_in_le_cada_dia_uma_vez(demo, leituras_de_dia):
    agora = clock.agora()
    checkin.confirmar(demo, {"sentimentos": {"M01": "firme"}}, agora=agora)
    assert max(leituras_de_dia.values()) == 1
    leituras_de_dia.clear()
    checkin.inferir(demo, modo_offline=True, agora=agora)
    assert max(leituras_de_dia.values()) == 1
