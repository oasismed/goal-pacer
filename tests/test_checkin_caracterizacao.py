"""Caracterização do check-in antes da refatoração: todas as recusas de uma vez (na ordem em que saem), sentimento e
decisão aplicados com a mensagem de cada mudança, e a saída do inferir sem bloco aberto."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import checkin
from goalpacer import perfil, registro as reg
from goalpacer.base import EXIT_VALIDACAO, GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "checkin"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)


@pytest.fixture
def dados(tmp_path, agora_fixo, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    return destino


def test_todas_as_recusas_saem_juntas_e_nada_e_gravado(dados):
    checkin.inferir(dados, modo_offline=True, agora=AGORA)
    antes = (dados / "registro.json").read_text(encoding="utf-8")
    respostas = {
        "feitas": [
            "D-2026-09-99-01",
            {"task_id": "D-2026-09-26-01", "duracao_real_h": "zero"},
            {"task_id": "D-2026-09-26-02", "duracao_real_h": -1},
        ],
        "nao_feitas": ["D-2026-09-99-02"],
        "progresso": {"M01": "muito", "X1": 10},
        "sentimentos": {"M01": "cansada", "M77": "firme"},
        "decisoes": {"M01": {"saida": "sumir"}, "M77": {"saida": "manter"}, "M02": "manter"},
    }
    with pytest.raises(GpErro) as erro:
        checkin.confirmar(dados, respostas, agora=AGORA)
    assert erro.value.codigo == EXIT_VALIDACAO
    assert erro.value.mensagem.split("\n") == [
        "feitas: bloco 'D-2026-09-99-01' não existe",
        "feitas: duracao_real_h de D-2026-09-26-01 inválida: 'zero'",
        "feitas: duracao_real_h de D-2026-09-26-02 inválida: -1",
        "nao_feitas: bloco 'D-2026-09-99-02' não existe",
        "progresso: 'muito' para 'M01' inválido (0 a 100)",
        "progresso: 10 para 'X1' inválido (0 a 100)",
        "sentimentos: 'cansada' para 'M01' inválido (energia|firme|pesada)",
        "sentimentos: 'firme' para 'M77' inválido (energia|firme|pesada)",
        "decisoes: M01 precisa de {saida: manter|reduzir|adiar|renegociar}",
        "decisoes: M02 precisa de {saida: manter|reduzir|adiar|renegociar}",
        "decisoes: meta M77 não existe",
    ]
    assert (dados / "registro.json").read_text(encoding="utf-8") == antes


def test_sentimento_e_decisao_viram_mudancas(dados):
    saida = checkin.confirmar(
        dados, {"sentimentos": {"M01": "energia"}, "decisoes": {"M01": {"saida": "manter"}}}, agora=AGORA
    )
    assert saida["mudancas"] == ["M01: sentimento com energia", "M01: manter"]
    assert saida["proximo"] == "semanal.py e diario.py --sem-inferir"
    assert reg.carregar(dados)["sentimentos"]["M01"][-1]["valor"] == "energia"


def test_inferir_sem_bloco_aberto_nao_chama_o_calendar(dados, monkeypatch):
    from goalpacer import calendar_ops

    checkin.inferir(dados, modo_offline=True, agora=AGORA)
    abertos = checkin._abertos(perfil.blocos_com_registro(dados, reg.carregar(dados)))
    for bloco in abertos:
        checkin.confirmar(dados, {"nao_feitas": [bloco["id"]]}, agora=AGORA)

    def proibido(*_a, **_k):
        raise AssertionError("não devia ler o Calendar")

    monkeypatch.setattr(calendar_ops, "ler_eventos", proibido)
    saida = checkin.inferir(dados, modo_offline=True, agora=AGORA)
    assert saida["aplicadas"] == [] and saida["segunda"] is True
    assert set(saida) == {
        "resumo",
        "contagens",
        "aplicadas",
        "presumidas",
        "inferidas",
        "sem_sinal",
        "segunda",
        "nota_sugerida",
        "decisoes",
        "perfil",
        "metas_sentir",
    }
