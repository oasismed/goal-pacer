"""Caracterização do diário antes da refatoração (manual de qualidade: rede de segurança primeiro).

Fixa o comportamento observável dos ramos que a suíte não exercitava: todas as linhas do "Desde", o porquê em
prosa viva com as trocas pelo template e os caminhos de erro do gerar (grafo, respostas ao email, reparo de ops).
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import diario
from goalpacer import calendar_ops, proxy, respostas_email
from goalpacer.base import EXIT_VALIDACAO, GpErro

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
DIA = date(2026, 9, 28)
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "diario"


def bloco(task_id: str, meta: str, titulo: str, hora: int) -> dict:
    inicio = datetime(2026, 9, 26, hora, 0, tzinfo=TZ)
    return {"id": task_id, "meta": meta, "titulo": titulo, "inicio": inicio, "fim": inicio + timedelta(hours=1)}


TODOS = {
    "D-2026-09-26-01": bloco("D-2026-09-26-01", "M01", "Curso", 8),
    "D-2026-09-26-02": bloco("D-2026-09-26-02", "M02", "Corrida", 9),
    "D-2026-09-26-03": bloco("D-2026-09-26-03", "M01", "Exercícios", 10),
    "D-2026-09-26-04": bloco("D-2026-09-26-04", "M03", "Artigo", 11),
    "D-2026-09-26-05": bloco("D-2026-09-26-05", "M02", "Treino", 12),
    "D-2026-09-26-06": bloco("D-2026-09-26-06", "M01", "Leitura", 13),
    "D-2026-09-26-07": bloco("D-2026-09-26-07", "M03", "Rascunho", 14),
    "D-2026-09-27-01": bloco("D-2026-09-27-01", "M01", "Revisão", 15),
}
ULTIMA = {"data": "2026-09-26", "ts": "2026-09-26T07:00:00-03:00"}


def test_desde_sem_diario_anterior_fica_vazio():
    assert diario.desde([], {}, TODOS, None, TZ, AGORA) == (
        None,
        "",
        [],
        {"confirmadas": 0, "presumidas": 0, "movidas": 0},
    )


def test_desde_todas_as_linhas_na_ordem():
    registro = {
        "checkins": {
            # confirmadas depois do último diário: feita conta, não feita só aparece
            "D-2026-09-26-01": {"estado": "feita", "origem": "confirmado", "ts": "2026-09-27T20:00:00-03:00"},
            "D-2026-09-26-02": {"estado": "nao_feita", "origem": "confirmado", "ts": "2026-09-27T20:00:00-03:00"},
            "D-2026-09-26-03": {"estado": "movida", "origem": "confirmado", "ts": "2026-09-27T20:00:00-03:00"},
            "D-2026-09-99-99": {"estado": "feita", "origem": "confirmado", "ts": "2026-09-27T20:00:00-03:00"},
            # confirmada antes do corte: fora
            "D-2026-09-26-06": {"estado": "feita", "origem": "confirmado", "ts": "2026-09-25T20:00:00-03:00"},
            # presumidas: recente entra, antiga não
            "D-2026-09-27-01": {"estado": "feita", "origem": "presumido", "ts": "2026-09-27T16:00:00-03:00"},
            "D-2026-09-26-07": {"estado": "feita", "origem": "presumido", "ts": "2026-09-20T16:00:00-03:00"},
        }
    }
    aplicadas = [
        {"task_id": "D-2026-09-26-01", "estado": "feita"},  # já vista pela confirmação
        {"task_id": "D-2026-09-26-04", "estado": "movida", "inicio": "2026-09-26T18:30:00-03:00"},
        {"task_id": "D-2026-09-26-05", "estado": "reagendada", "inicio": "2026-09-30T07:15:00-03:00"},
        {"task_id": "D-2026-09-26-06", "estado": "apagada"},
        {"task_id": "D-2026-09-26-07", "estado": "feita"},
        {"task_id": "D-2026-09-26-03", "estado": "sem_sinal"},
        {"task_id": "D-2026-09-99-98", "estado": "feita"},  # bloco que não existe mais
    ]
    dia, contagem, linhas, contagens = diario.desde(aplicadas, registro, TODOS, ULTIMA, TZ, AGORA)
    assert dia == "sáb"
    assert contagens == {"confirmadas": 1, "presumidas": 2, "movidas": 2, "fora": 1}
    assert contagem == "1 confirmada(s) · 2 feita? · 2 movida(s) · 1 fora da agenda"
    assert linhas == [
        "Curso (M1): confirmada",
        "Corrida (M2): não fiz",
        "Artigo (M3): movida para 18h30",
        "Treino (M2): fica para qua 07h15",
        "Leitura (M1): saiu da agenda",
        "Rascunho (M3): feita?",
        "Revisão (M1): feita?",
    ]


def test_desde_sem_agora_nao_lista_presumidas_do_registro():
    registro = {
        "checkins": {"D-2026-09-27-01": {"estado": "feita", "origem": "presumido", "ts": "2026-09-27T16:00:00-03:00"}}
    }
    movida_sem_inicio = [{"task_id": "D-2026-09-26-04", "estado": "movida"}]
    _, contagem, linhas, contagens = diario.desde(movida_sem_inicio, registro, TODOS, ULTIMA, TZ)
    assert linhas == ["Artigo (M3): movida para 11h"] and contagens["presumidas"] == 0 and contagem == "1 movida(s)"


# --- porquê em prosa viva ----------------------------------------------------------------------------------------------


def _blocos_porque() -> list[dict]:
    return [
        {"id": "D-2026-09-28-01", "meta": "M01", "inicio": datetime(2026, 9, 28, 8, 0, tzinfo=TZ)},
        {"id": "D-2026-09-28-02", "meta": "M02", "inicio": datetime(2026, 9, 28, 9, 0, tzinfo=TZ)},
        {"id": "D-2026-09-28-03", "meta": "M01", "inicio": datetime(2026, 9, 28, 10, 0, tzinfo=TZ)},
    ]


METAS_PORQUE = {
    "M01": {"id": "M01", "titulo": "Curso", "custo_h_semana_escolhido": 4.0, "estado": "ativa"},
    "M02": {"id": "M02", "titulo": "Corrida", "custo_h_semana_escolhido": 2.0, "estado": "ativa"},
}


def _rodar_porques(tmp_path, monkeypatch, resposta=None, erro=None):
    offline = tmp_path / "offline"
    offline.mkdir()
    if resposta is not None:
        (offline / diario.FIXTURE_PORQUE).write_text(resposta, encoding="utf-8")
    monkeypatch.setenv("GP_OFFLINE_DIR", str(offline))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    if erro is not None:

        def falha(*_a, **_k):
            raise erro

        monkeypatch.setattr(proxy, "prosa", falha)
    monkeypatch.setattr(
        diario.demanda, "demanda_semana", lambda meta, _registro, _semana: meta["custo_h_semana_escolhido"]
    )
    blocos, avisos, logs = _blocos_porque(), [], []
    monkeypatch.setattr(diario.telemetria, "log", lambda mensagem, **_k: logs.append(mensagem))
    diario.porques(
        blocos,
        METAS_PORQUE,
        {},
        "2026-W40",
        dia=DIA,
        viva=True,
        modo_offline=resposta is not None,
        run_id="r-porque",
        registro_proxies=[],
        avisos=avisos,
    )
    return [b["porque"] for b in blocos], avisos, logs


def test_porque_vivo_usa_a_prosa_boa_e_troca_a_ruim_pelo_template(tmp_path, monkeypatch):
    resposta = "\n".join(
        [
            "D-2026-09-28-01: Módulo 3   do curso antes do trabalho",
            "D-2026-09-28-02: " + "x" * 120,  # longo demais
            "linha fora do formato",
        ]
    )
    porques, avisos, logs = _rodar_porques(tmp_path, monkeypatch, resposta=resposta)
    assert porques == [
        "Módulo 3 do curso antes do trabalho",
        "M2 pede 2h nesta semana; janela livre das 09h",
        "M1 pede 4h nesta semana; janela livre das 10h",
    ]
    assert avisos == [] and logs == ["porquê de D-2026-09-28-02 trocado pelo template"]


def test_porque_vivo_com_falha_do_conector_avisa_e_usa_template(tmp_path, monkeypatch):
    porques, avisos, _ = _rodar_porques(tmp_path, monkeypatch, erro=GpErro(4, "timeout do proxy"))
    assert porques[0] == "M1 pede 4h nesta semana; janela livre das 08h" and len(avisos) == 1


def test_porque_vivo_com_limite_de_uso_propaga(tmp_path, monkeypatch):
    with pytest.raises(proxy.RateLimited):
        _rodar_porques(tmp_path, monkeypatch, erro=proxy.RateLimited("limite"))


# --- caminhos de erro do gerar -------------------------------------------------------------------------------------------


@pytest.fixture
def dados(tmp_path, agora_fixo, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    return destino


def test_gerar_com_grafo_invalido_para_com_validacao(dados):
    (dados / "metas" / "M01.md").write_text("---\nlixo\n", encoding="utf-8")
    with pytest.raises(GpErro) as erro:
        diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=True, agora=AGORA, run_id="r-grafo")
    assert erro.value.codigo == EXIT_VALIDACAO and erro.value.mensagem.startswith("validar grafo: ")


def test_gerar_segue_quando_as_respostas_ao_email_falham(dados, monkeypatch):
    logs = []
    monkeypatch.setattr(diario.telemetria, "log", lambda mensagem, **_k: logs.append(mensagem))

    def falha(*_a, **_k):
        raise GpErro(3, "Insufficient scope")

    monkeypatch.setattr(respostas_email, "aplicar", falha)
    saida = diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="r-email")
    assert saida["arquivo"] == "dias/2026-09-28.md"
    assert any(m.startswith("respostas ao email não lidas: ") for m in logs)


def test_gerar_propaga_limite_de_uso_das_respostas_ao_email(dados, monkeypatch):
    def limite(*_a, **_k):
        raise proxy.RateLimited("limite")

    monkeypatch.setattr(respostas_email, "aplicar", limite)
    with pytest.raises(proxy.RateLimited):
        diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="r-limite")


def test_gerar_repara_op_que_falhou_uma_vez(dados, monkeypatch):
    original = calendar_ops.aplicar_resultados
    chamadas = []

    def primeira_falha(blocos, doc, metas):
        chamadas.append(len(doc["ops"]))
        com_erro = original(blocos, doc, metas)
        return ["D-2026-09-28-02"] if len(chamadas) == 1 else com_erro

    monkeypatch.setattr(calendar_ops, "aplicar_resultados", primeira_falha)
    monkeypatch.setattr(calendar_ops, "ops_de_reparo", lambda doc, run_id, agora: {"run_id": run_id, "ops": []})
    saida = diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=False, agora=AGORA, run_id="r-reparo")
    assert len(chamadas) == 2 and saida["ops"]["erro"] == 0
    assert not any("não entrou na agenda" in a for a in saida["avisos"])


def test_gerar_avisa_fuso_do_sistema_diferente_do_contexto(dados, monkeypatch):
    monkeypatch.setenv("GP_TZ", "Europe/Lisbon")
    saida = diario.gerar(dados, dia=DIA, modo_offline=True, sem_inferir=True, agora=AGORA, run_id="r-fuso")
    assert any("Europe/Lisbon" in a for a in saida["avisos"])


def test_gerar_propaga_limite_de_uso_do_email(dados, monkeypatch):
    def limite(*_a, **_k):
        raise proxy.RateLimited("limite")

    monkeypatch.setattr(diario.correio, "enviar", limite)
    with pytest.raises(proxy.RateLimited):
        diario.gerar(
            dados, dia=DIA, modo_offline=True, sem_inferir=True, agora=AGORA, run_id="r-email", enviar_email=True
        )
