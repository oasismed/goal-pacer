"""goalpacer/processos.py e o lado Windows de seguranca.py, conferidos em qualquer sistema."""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

from goalpacer import processos, seguranca


def test_vivo_confere_sem_encerrar_e_recusa_pid_impossivel():
    assert processos.vivo(os.getpid()) is True
    for ruim in (0, -1, True, "123", None, 2**40):
        assert processos.vivo(ruim) is False
    filho = subprocess.Popen([sys.executable, "-c", "pass"])
    filho.wait(timeout=30)
    assert processos.vivo(filho.pid) is False


def test_isolamento_por_sistema(monkeypatch):
    monkeypatch.setattr(processos, "WINDOWS", False)
    assert processos.isolamento() == {"start_new_session": True} == processos.desligado()
    monkeypatch.setattr(processos, "WINDOWS", True)
    assert processos.isolamento() == {"creationflags": 0x200}
    assert processos.desligado() == {"creationflags": 0x200 | 0x08000000}  # console próprio e escondido


def test_matar_arvore_no_windows_usa_taskkill_na_arvore(monkeypatch):
    monkeypatch.setattr(processos, "WINDOWS", True)
    chamadas: list = []
    monkeypatch.setattr(processos.subprocess, "run", lambda argv, **_k: chamadas.append(argv))
    mortos: list = []
    processos.matar_arvore(SimpleNamespace(pid=4321, kill=lambda: mortos.append(True)))  # type: ignore[arg-type]
    assert chamadas == [["taskkill", "/T", "/F", "/PID", "4321"]] and mortos == [True]

    def sem_taskkill(*_a, **_k):
        raise FileNotFoundError("taskkill")

    monkeypatch.setattr(processos.subprocess, "run", sem_taskkill)
    processos.matar_arvore(SimpleNamespace(pid=1, kill=lambda: mortos.append(True)))  # type: ignore[arg-type]
    assert mortos == [True, True]


def test_matar_arvore_no_posix_mata_o_grupo_do_filho():
    filho = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], **processos.isolamento())
    try:
        processos.matar_arvore(filho)
        assert filho.wait(timeout=30) != 0
    finally:
        if filho.poll() is None:
            filho.kill()


def test_seguranca_no_windows_nao_acusa_modo_nem_mexe(tmp_path, monkeypatch):
    aberta = tmp_path / "aberta"
    aberta.mkdir()
    aberta.chmod(0o777)
    arquivo = aberta / "segredo.json"
    arquivo.write_text("{}", encoding="utf-8")
    arquivo.chmod(0o666)
    monkeypatch.setattr(seguranca, "WINDOWS", True)
    assert seguranca.pastas_privadas([aberta]) == [] and seguranca.arquivos_privados([arquivo]) == []
    assert seguranca.codigo_protegido(aberta) == [] and seguranca.agendador_protegido([arquivo]) == []
    assert seguranca.endurecer(aberta, [aberta], [arquivo]) == 0 and (arquivo.stat().st_mode & 0o777) == 0o666
    aberta.chmod(0o700)
