"""instalar.py pelo app do .dmg e pelo Setup.exe (``--de-app``): o Python dos jobs, a janela e a limpeza de versões.

O percurso inteiro, com o .dmg e o Setup.exe de verdade, está em ``tests/e2e/instaladores.py`` (roda na máquina de cada sistema).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

import instalar
from goalpacer import base, processos


@pytest.mark.posix  # symlink do Python como no .dmg
def test_python_dos_jobs_sai_do_app_e_fica_num_lugar_estavel(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    assert instalar.python_para_jobs(raiz, None) == sys.executable  # pelo terminal: o Python que rodou
    app_python = tmp_path / "Goal Pacer.app" / "Contents" / "Resources" / "python"
    (app_python / "bin").mkdir(parents=True)
    (app_python / "bin" / "python3.13").write_text("binario", encoding="utf-8")
    (app_python / "bin" / "python3").symlink_to("python3.13")
    (app_python / "lib").mkdir()
    monkeypatch.setattr(instalar.sys, "executable", str(app_python / "bin" / "python3"))
    monkeypatch.setattr(instalar.sys, "version_info", (3, 13, 15, "final", 0))
    monkeypatch.setattr(processos, "WINDOWS", False)
    copiado = Path(instalar.python_para_jobs(raiz, str(tmp_path / "Goal Pacer.app")))
    assert copiado == raiz / "runtime" / "python-3.13.15" / "bin" / "python3" and copiado.is_symlink()
    assert copiado.resolve().read_text(encoding="utf-8") == "binario"
    (raiz / "runtime" / "python-3.13.1").mkdir()
    assert instalar.python_para_jobs(raiz, "app") == str(copiado)  # já copiado: não copia outra vez
    instalar.limpar_runtimes(raiz, str(copiado))
    assert [p.name for p in (raiz / "runtime").iterdir()] == ["python-3.13.15"]
    monkeypatch.setattr(processos, "WINDOWS", True)
    assert instalar.python_para_jobs(raiz, "C:/Programs/Goal Pacer/9.0.0") == str(app_python / "bin" / "python3")


def test_setup_do_windows_limpa_as_pastas_de_versoes_anteriores(tmp_path):
    for nome in ("9.0.0", "9.1.0", "dados-da-pessoa"):
        (tmp_path / nome).mkdir()
    (tmp_path / "goal-pacer.ico").write_bytes(b"ico")
    instalar.limpar_versoes_do_setup(tmp_path / "9.1.0")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["9.1.0", "dados-da-pessoa", "goal-pacer.ico"]


def test_app_do_dmg_e_a_janela_e_troca_o_runtime_no_update(tmp_path, monkeypatch):
    app = tmp_path / "Aplicativos" / "Goal Pacer.app"
    app.mkdir(parents=True)
    assert instalar.instalar_janela(tmp_path, tmp_path, "py", sem_janela=False, janela_do_app=str(app)) == str(app)
    assert instalar.instalar_janela(tmp_path, tmp_path, "py", sem_janela=True, janela_do_app=str(app)) == ""
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setattr(instalar, "python_para_jobs", lambda raiz, de_app: "/runtime/python-3.13.15/bin/python3")
    instalacao = {"raiz": str(tmp_path / "raiz"), "python3": "/opt/homebrew/bin/python3"}
    instalar._trocar_runtime(instalacao, str(app))
    gravada = json.loads((base.jobs_dir() / base.NOME_INSTALACAO).read_text(encoding="utf-8"))
    assert gravada["python3"] == "/runtime/python-3.13.15/bin/python3" and gravada["janela_do_app"] == str(app)


def test_update_da_copia_pelo_canal(tmp_path, monkeypatch, capsys):
    """Cópia sem origem: com release/canal o update baixa o zip anunciado (e segue pelo zip); sem versão nova, nada."""
    app = tmp_path / "app"
    (app / "release").mkdir(parents=True)
    temporaria = tmp_path / "t"
    temporaria.mkdir()
    monkeypatch.setattr(instalar.assinatura, "versao_instalada", lambda _app: (0, 4, 1))
    monkeypatch.setattr(instalar.canal, "ultima", lambda _app, _pasta: {"versao_tupla": (0, 4, 1), "zip": "g.zip"})
    assert instalar._zip_do_canal(app, temporaria) is None
    monkeypatch.setattr(instalar.canal, "ultima", lambda _app, _pasta: {"versao_tupla": (0, 5, 0), "zip": "g.zip"})
    monkeypatch.setattr(instalar.canal, "baixar_zip", lambda _app, dados, pasta: pasta / dados["zip"])
    segunda = tmp_path / "t2"
    segunda.mkdir()
    assert instalar._zip_do_canal(app, segunda) == str(segunda / "canal" / "g.zip")
    assert "versão nova no canal: 0.5.0" in capsys.readouterr().out
    args = argparse.Namespace(origem=None, copiar=False)
    assert instalar._recusa_do_update(args, app, False)[0] == instalar.EXIT_VALIDACAO  # sem canal: recusa
    (app / "release" / "canal").write_text("https://versoes.exemplo.test/\n", encoding="utf-8")
    assert instalar._recusa_do_update(args, app, False) == (None, "")
