"""D-14: caminhos de erro do sistema operacional em io, seguranca e telemetria (permissão, disco, arquivo sumindo).

É o que acontece na máquina dos outros e quase nunca na de quem desenvolve; cada falha é simulada no ponto exato.
"""

from __future__ import annotations

import json
import os

import pytest

from goalpacer import io as gpio, seguranca, telemetria
from goalpacer.base import EXIT_IO, GpErro

# --- io: lock ----------------------------------------------------------------------------------------------------------


def test_pid_de_outro_usuario_conta_como_vivo():
    assert gpio._pid_vivo(1) is True  # launchd/init: PermissionError no macOS, sinal permitido como root no Docker


def test_identidade_de_arquivo_ilegivel_usa_conteudo_vazio(tmp_path):
    pasta = tmp_path / "nao-e-arquivo"
    pasta.mkdir()
    assert gpio._identidade(os.stat(pasta), pasta)[3] == b""


def test_lock_que_nao_consegue_gravar_apaga_o_arquivo_e_avisa(tmp_path):
    lock = gpio.Lock(tmp_path / ".lock")
    lock.path.write_text("", encoding="utf-8")
    fd = os.open(str(lock.path), os.O_RDONLY)  # escrever num descritor só de leitura falha no write
    with pytest.raises(GpErro, match="não foi possível gravar o lock") as erro:
        lock._gravar(fd)
    assert erro.value.codigo == EXIT_IO and not lock.path.exists()


def test_lock_sumido_nao_e_obsoleto_e_info_sem_objeto_e_none(tmp_path):
    lock = gpio.Lock(tmp_path / ".lock")
    assert lock._obsoleto() is None
    lock.path.write_text("[1, 2]", encoding="utf-8")
    assert lock.info() is None


def test_remover_obsoleto_nos_tres_pontos_de_falha(tmp_path, monkeypatch):
    lock = gpio.Lock(tmp_path / ".lock")
    lock.path.write_text(json.dumps({"pid": 999999999}), encoding="utf-8")
    identidade = gpio._identidade(os.stat(lock.path), lock.path)

    def negado(*_a, **_k):
        raise PermissionError("negado")

    monkeypatch.setattr(gpio.os, "rename", negado)
    with pytest.raises(GpErro, match="não foi possível remover lock obsoleto"):
        lock._remover_obsoleto(identidade)
    monkeypatch.undo()

    # o renomeado mudou entre o stat e o rename (lock novo de outro processo): volta ao lugar e não apaga
    identidades = iter([identidade, ("outro",)])
    monkeypatch.setattr(gpio, "_identidade", lambda *_a: next(identidades))
    assert lock._remover_obsoleto(identidade) is False and lock.path.exists()
    monkeypatch.undo()

    def sumiu(*_a, **_k):
        raise FileNotFoundError("outro processo apagou antes")

    monkeypatch.setattr(gpio.os, "unlink", sumiu)
    assert lock._remover_obsoleto(identidade) is True
    monkeypatch.undo()
    obsoleto = next(tmp_path.glob(".lock.obsoleto.*"))
    obsoleto.rename(lock.path)
    monkeypatch.setattr(gpio.os, "unlink", negado)
    with pytest.raises(GpErro, match="não foi possível remover lock obsoleto"):
        lock._remover_obsoleto(identidade)


def test_liberar_lock_sumido_ou_protegido(tmp_path, monkeypatch):
    lock = gpio.Lock(tmp_path / ".lock")
    lock.path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

    def sumiu(*_a, **_k):
        raise FileNotFoundError("já apagado")

    monkeypatch.setattr(gpio.os, "unlink", sumiu)
    lock.liberar()

    def negado(*_a, **_k):
        raise PermissionError("negado")

    monkeypatch.setattr(gpio.os, "unlink", negado)
    with pytest.raises(GpErro, match="não foi possível remover o lock"):
        lock.liberar()


# --- seguranca -------------------------------------------------------------------------------------------------------


def test_arvore_que_some_durante_a_varredura(tmp_path, monkeypatch):
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / "x.py").write_text("", encoding="utf-8")
    original = os.lstat

    def lstat_que_some(caminho, *a, **k):
        if str(caminho).endswith(("x.py", "app")):
            raise FileNotFoundError(caminho)
        return original(caminho, *a, **k)

    monkeypatch.setattr(seguranca.os, "lstat", lstat_que_some)
    assert [c.name for c, _ in seguranca._arvore(app)] == ["scripts"]


def test_codigo_de_outro_dono_e_agendador_ilegivel(tmp_path, monkeypatch):
    app = tmp_path / "app"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / "x.py").write_text("", encoding="utf-8")
    (app / "scripts" / "x.py").chmod(0o644)
    app.chmod(0o755)
    (app / "scripts").chmod(0o755)
    (app / "link.py").symlink_to(app / "scripts" / "x.py")
    monkeypatch.setattr(seguranca, "_uid", lambda: os.getuid() + 1)
    problemas = seguranca.codigo_protegido(app)
    assert [(p.tipo, p.quantos) for p in problemas] == [("codigo_de_outro", 3)]  # o link não conta
    assert seguranca.agendador_protegido([tmp_path / "nao-existe.plist"]) == []
    assert seguranca.skill_aponta_para(tmp_path / "nao-e-link", app) == []


# --- telemetria ------------------------------------------------------------------------------------------------------


def test_telemetria_sem_disco_nao_derruba_quem_mede(tmp_path, monkeypatch):
    arquivo = tmp_path / "ocupado"
    arquivo.write_text("", encoding="utf-8")
    monkeypatch.setenv("GP_LOGS_DIR", str(arquivo / "logs"))  # a pasta não pode existir dentro de um arquivo
    telemetria.evento("teste", x=1)
    assert telemetria.ler("eventos-*.jsonl") == [] and telemetria.ultimo_trace() is None


def test_span_anota_a_excecao_e_repassa(monkeypatch, tmp_path):
    with pytest.raises(KeyError), telemetria.span("bloco") as extra:
        raise KeyError("x")
    assert extra["erro"] == "KeyError"
    spans = telemetria.ler("trace-*.jsonl")
    assert spans[-1]["nome"] == "bloco" and spans[-1]["erro"] == "KeyError"


def test_log_em_json_e_leitura_tolerante(monkeypatch, capsys):
    monkeypatch.setenv("GP_LOG_JSON", "1")
    telemetria.log("uma\nlinha", run_id="r1", nivel="aviso")
    linha = json.loads(capsys.readouterr().err.strip())
    assert linha["mensagem"] == "uma linha" and linha["run_id"] == "r1" and linha["nivel"] == "aviso"
    pasta = telemetria.pasta()
    assert pasta is not None
    (pasta / "eventos-2020-01-01.jsonl").write_text('{"tipo": "painel_erro"}\n', encoding="utf-8")
    os.utime(pasta / "eventos-2020-01-01.jsonl", (0, 0))  # fora da janela de 7 dias
    (pasta / "eventos-9999-01-01.jsonl").write_text('nao json\n[1]\n{"tipo": "painel_erro"}\n', encoding="utf-8")
    (pasta / "eventos-9999-01-02.jsonl").mkdir()  # ilegível como arquivo
    resumo = telemetria.resumo(dias=7)
    assert resumo["erros_painel"] == 1
    assert telemetria.percentil([], 50) is None


def test_leitura_pula_arquivo_que_some_entre_a_listagem_e_o_stat():
    pasta = telemetria.pasta()
    assert pasta is not None
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "eventos-9999-01-01.jsonl").write_text('{"tipo": "painel"}\n', encoding="utf-8")
    (pasta / "eventos-9999-01-02.jsonl").symlink_to(pasta / "nao-existe.jsonl")  # a retenção apagou o alvo
    assert telemetria.ler("eventos-*.jsonl") == [{"tipo": "painel"}]
