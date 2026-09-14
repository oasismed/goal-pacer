"""Testes de goalpacer.registro: máquina de estados, feitas, progresso, notas, carga e gravação."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from goalpacer import registro as reg, schema
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

UTC = timezone.utc
TS = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)
TASK = "D-2026-09-28-01"


def test_vazio_e_valido():
    r = reg.vazio()
    assert r["schema_version"] == schema.SCHEMA_VERSION
    assert schema.validar_registro("registro", r) == []


def test_maquina_de_estados():
    r = reg.vazio()
    assert reg.registrar_checkin(r, TASK, "sem_sinal", "inferido", ts=TS) is True
    assert reg.registrar_checkin(r, TASK, "feita", "presumido", ts=TS) is True
    assert r["checkins"][TASK] == {"estado": "feita", "origem": "presumido", "ts": "2026-09-28T07:00:00+00:00"}
    assert reg.registrar_checkin(r, TASK, "feita", "confirmado", ts=TS, duracao_real_h=1.5) is True
    # confirmado nunca é sobrescrito por inferido/presumido
    assert reg.registrar_checkin(r, TASK, "apagada", "inferido", ts=TS) is False
    assert reg.registrar_checkin(r, TASK, "feita", "presumido", ts=TS) is False
    assert r["checkins"][TASK]["estado"] == "feita" and r["checkins"][TASK]["duracao_real_h"] == 1.5
    # confirmado sobre confirmado e prazo sobre qualquer coisa: ok
    assert reg.registrar_checkin(r, TASK, "nao_feita", "confirmado", ts=TS) is True
    assert "duracao_real_h" not in r["checkins"][TASK]
    assert reg.registrar_checkin(r, TASK, "cancelada", "prazo", ts=TS) is True
    assert reg.transicao_permitida(None, "inferido") and not reg.transicao_permitida("confirmado", "presumido")
    with pytest.raises(GpErro):
        reg.registrar_checkin(r, TASK, "feita?", "inferido")
    with pytest.raises(GpErro):
        reg.registrar_checkin(r, "bloco-1", "feita", "inferido")
    assert schema.validar_registro("registro", r) == []


def test_feitas_progresso_geracoes_notas():
    r = reg.vazio()
    reg.registrar_feita(r, "M01", TASK, 1.0, "presumido", ts=TS)
    reg.registrar_feita(r, "M01", TASK, 1.0, "confirmado", duracao_real_h=1.5, ts=TS)
    assert r["feitas"]["M01"] == [
        {
            "task_id": TASK,
            "duracao_h": 1.0,
            "origem": "confirmado",
            "ts": "2026-09-28T07:00:00+00:00",
            "duracao_real_h": 1.5,
        }
    ]
    reg.remover_feita(r, TASK)
    assert r["feitas"]["M01"] == []
    with pytest.raises(GpErro):
        reg.registrar_feita(r, "meta1", TASK, 1.0, "confirmado")
    assert reg.ultimo_progresso_declarado(r, "M01") is None
    reg.declarar_progresso(r, "M01", 40, ts=TS)
    reg.declarar_progresso(r, "M01", 55, ts=datetime(2026, 10, 5, tzinfo=UTC))
    assert reg.ultimo_progresso_declarado(r, "M01") == 55.0
    with pytest.raises(GpErro):
        reg.declarar_progresso(r, "M01", 120)
    reg.registrar_geracao(
        r, {"run_id": "r1", "modo": "diario", "data": "2026-09-28", "ts": "2026-09-28T07:04:00-03:00", "exit_code": 0}
    )
    reg.registrar_geracao(
        r, {"run_id": "r2", "modo": "mensal", "data": "2026-09-01", "ts": "2026-09-01T05:40:00-03:00", "exit_code": 0}
    )
    assert set(r["geracoes"]) == {"r1", "r2"}
    with pytest.raises(GpErro):
        reg.registrar_geracao(r, {"run_id": "r3"})
    reg.recusar_nota(r, "Sem blocos antes das 9h ", ts=TS)
    assert reg.nota_recusada_recente(r, "sem blocos antes das 9h", agora=datetime(2026, 10, 20, tzinfo=UTC))
    assert not reg.nota_recusada_recente(r, "sem blocos antes das 9h", agora=datetime(2026, 11, 20, tzinfo=UTC))
    assert not reg.nota_recusada_recente(r, "outra nota", agora=TS)
    assert schema.validar_registro("registro", r) == []


def test_carregar_e_salvar(dados_tmp, agora_fixo):
    assert reg.carregar(dados_tmp) == reg.vazio()
    r = reg.vazio()
    reg.registrar_checkin(r, TASK, "feita", "confirmado", ts=TS)
    path = reg.salvar(r, dados_tmp)
    assert path == dados_tmp / "registro.json" and reg.carregar(dados_tmp) == r
    # segunda gravação deixa .bak; corromper o principal recupera do .bak
    reg.registrar_checkin(r, "D-2026-09-28-02", "apagada", "inferido", ts=TS)
    reg.salvar(r, dados_tmp)
    path.write_text('{"schema_version": 1, "checkins": {', encoding="utf-8")
    recuperado = reg.carregar(dados_tmp)
    assert TASK in recuperado["checkins"]
    # sem .bak válido: RegistroCorrompido (exit 4)
    path.write_text("{", encoding="utf-8")
    (dados_tmp / "registro.json.bak").write_text("{", encoding="utf-8")
    with pytest.raises(GpErro) as info:
        reg.carregar(dados_tmp)
    assert info.value.codigo == EXIT_IO and "RegistroCorrompido" in info.value.mensagem
    # inválido não é gravado
    with pytest.raises(GpErro) as info:
        reg.salvar({"schema_version": 1, "checkins": {"x": {}}}, dados_tmp)
    assert info.value.codigo == EXIT_VALIDACAO
    # versão diferente
    path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    with pytest.raises(GpErro) as info:
        reg.carregar(dados_tmp)
    assert "install.sh --update" in info.value.mensagem


def test_lock(dados_tmp):
    trava = reg.lock(dados_tmp)
    assert (dados_tmp / ".lock").exists()
    with pytest.raises(GpErro) as info:
        reg.lock(dados_tmp)
    assert info.value.codigo == EXIT_IO
    trava.liberar()
    assert not (dados_tmp / ".lock").exists()


def test_lock_herdado_so_do_processo_pai(dados_tmp, monkeypatch):
    """Com GP_LOCK_HERDADO=1 o passo do job usa o lock do pai sem disputá-lo; outro dono não vale."""
    import os

    (dados_tmp / ".lock").write_text(
        json.dumps({"pid": os.getppid(), "criado_em": "2026-09-28T10:00:00+00:00"}), encoding="utf-8"
    )
    with pytest.raises(GpErro):
        reg.lock(dados_tmp)
    monkeypatch.setenv(reg.ENV_LOCK_HERDADO, "1")
    trava = reg.lock(dados_tmp)
    assert isinstance(trava, reg.LockHerdado)
    trava.liberar()
    assert (dados_tmp / ".lock").exists()
    (dados_tmp / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "criado_em": "2026-09-28T10:00:00+00:00"}), encoding="utf-8"
    )
    with pytest.raises(GpErro) as info:
        reg.lock(dados_tmp)
    assert info.value.codigo == EXIT_IO


# --- arquivo anual ----------------------------------------------------------------------


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """Pasta de dados do demo (cinco semanas de histórico em 2026), com o ambiente limpo depois."""
    import os

    import demo_painel
    from goalpacer import clock

    for var in [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    dados = demo_painel.preparar(tmp_path)
    for var, valor in demo_painel.ambiente(tmp_path).items():
        monkeypatch.setenv(var, valor)
    return dados


def test_arquivar_move_anos_antigos_sem_mudar_totais(demo):
    from goalpacer import perfil as prf

    depois_de_um_ano = datetime(2027, 6, 1, 7, 0, tzinfo=UTC)
    antes = prf.calcular(demo, depois_de_um_ano)["metas"]
    principal_antes = json.loads((demo / "registro.json").read_text(encoding="utf-8"))
    assert reg.arquivar(demo, datetime(2026, 12, 20, tzinfo=UTC)) == {}  # nada de ano anterior ainda
    contagem = reg.arquivar(demo, depois_de_um_ano)
    assert list(contagem) == [2026] and contagem[2026] > 100
    principal = json.loads((demo / "registro.json").read_text(encoding="utf-8"))
    anual = json.loads((demo / "registro-2026.json").read_text(encoding="utf-8"))
    assert (
        principal["checkins"] == {}
        and principal["feitas"] == {}
        and len(anual["checkins"]) == len(principal_antes["checkins"])
    )
    assert [p.name for p in reg.caminhos_anuais(demo)] == ["registro-2026.json"]
    # a leitura junta os dois: perfil e progresso idênticos
    assert prf.calcular(demo, depois_de_um_ano)["metas"] == antes
    carregado = reg.carregar(demo)
    assert carregado["checkins"] == principal_antes["checkins"] and carregado["feitas"] == principal_antes["feitas"]
    # salvar o que foi carregado não devolve o histórico ao principal
    reg.salvar(carregado, demo)
    assert json.loads((demo / "registro.json").read_text(encoding="utf-8"))["checkins"] == {}
    # corrigir uma entrada antiga: a correção fica no principal e vence o arquivo anual
    task = min(carregado["checkins"])
    reg.registrar_checkin(carregado, task, "nao_feita", "confirmado", ts=depois_de_um_ano)
    reg.salvar(carregado, demo)
    assert list(json.loads((demo / "registro.json").read_text(encoding="utf-8"))["checkins"]) == [task]
    assert reg.carregar(demo)["checkins"][task]["estado"] == "nao_feita"
    # idempotente, e a correção antiga volta ao anual na próxima rodada
    assert reg.arquivar(demo, depois_de_um_ano) == {2026: 0}
    assert json.loads((demo / "registro.json").read_text(encoding="utf-8"))["checkins"] == {}
    assert reg.carregar(demo)["checkins"][task]["estado"] == "nao_feita"


def test_arquivo_anual_corrompido_volta_do_bak(demo):
    import registro as cli
    from goalpacer import io as gpio

    reg.arquivar(demo, datetime(2027, 6, 1, tzinfo=UTC))
    anual = demo / "registro-2026.json"
    gpio.escrever_json(anual, json.loads(anual.read_text(encoding="utf-8")))  # segunda escrita deixa o .bak
    anual.write_text("{ quebrado", encoding="utf-8")
    assert len(reg.carregar(demo)["checkins"]) > 80  # a leitura restaura sozinha
    anual.write_text("{ quebrado", encoding="utf-8")
    assert cli.main(["recuperar"]) == 0 and json.loads(anual.read_text(encoding="utf-8"))["checkins"]


def test_validacao_poupada_so_para_conteudo_ja_validado(tmp_path):
    """P3 (análise de 13/09): o mesmo conteúdo não é validado duas vezes; conteúdo novo e inválido segue recusado."""
    import json

    import pytest

    from goalpacer import registro as reg, schema
    from goalpacer.base import GpErro

    registro = reg.vazio()
    reg.salvar(registro, tmp_path)
    chamadas = []
    original = schema.validar_registro

    def contar(nome, valor):
        chamadas.append(nome)
        return original(nome, valor)

    schema.validar_registro = contar
    try:
        reg.carregar(tmp_path)
        reg.carregar(tmp_path)
        assert chamadas.count("registro") <= 1
        bruto = json.loads((tmp_path / "registro.json").read_text(encoding="utf-8"))
        bruto["checkins"] = {
            "D-2026-09-28-01": {"estado": "voando", "origem": "confirmado", "ts": "2026-09-28T07:00:00-03:00"}
        }
        (tmp_path / "registro.json").write_text(json.dumps(bruto), encoding="utf-8")
        with pytest.raises(GpErro):
            reg.carregar(tmp_path)
    finally:
        schema.validar_registro = original
