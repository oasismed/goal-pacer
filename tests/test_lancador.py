"""scripts/lancador.py: o que o Agendador de Tarefas e os atalhos do Windows chamam, testado com um app de mentira.

Os alvos (``run_job.py``, ``web.py``) são scripts Python curtos numa raiz temporária; o painel de verdade e o navegador
nunca sobem aqui.
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import threading
from pathlib import Path

import pytest

import lancador
from goalpacer import base, plataforma, processos, proxy


def raiz_falsa(tmp_path: Path, *, run_job: str = "", web: str = "") -> tuple[Path, dict]:
    raiz = tmp_path / "raiz"
    (raiz / "app" / "jobs").mkdir(parents=True)
    (raiz / "app" / "scripts").mkdir(parents=True)
    (raiz / "jobs").mkdir()
    (raiz / "app" / "jobs" / "run_job.py").write_text(run_job, encoding="utf-8")
    (raiz / "app" / "scripts" / "web.py").write_text(web, encoding="utf-8")
    instalacao = {"raiz": str(raiz), "app": str(raiz / "app"), "dados": str(tmp_path / "dados"), "claude": "/c/claude"}
    (raiz / "jobs" / base.NOME_INSTALACAO).write_text(json.dumps(instalacao), encoding="utf-8")
    return raiz, instalacao


def test_raiz_instalacao_e_ambiente(tmp_path, monkeypatch):
    raiz, instalacao = raiz_falsa(tmp_path)
    assert lancador.raiz_da_instalacao(raiz / "app" / "scripts" / "lancador.py") == raiz
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "outra"))
    assert lancador.raiz_da_instalacao(tmp_path / "solto" / "a" / "lancador.py") == tmp_path / "outra"
    assert lancador.ler_instalacao(raiz) == instalacao and lancador.ler_instalacao(tmp_path) == {}
    (raiz / "jobs" / base.NOME_INSTALACAO).write_text("[1]", encoding="utf-8")
    assert lancador.ler_instalacao(raiz) == {}
    env = lancador.ambiente(raiz, instalacao, {"PATH": "x"})
    assert env[base.ENV_RAIZ] == str(raiz) and env[base.ENV_DATA_DIR] == instalacao["dados"]
    assert env[proxy.ENV_CLAUDE_BIN] == "/c/claude" and env["PYTHONUTF8"] == "1" and env["PATH"] == "x"
    sem_claude = lancador.ambiente(raiz, {}, {})
    assert proxy.ENV_CLAUDE_BIN not in sem_claude and sem_claude[base.ENV_DATA_DIR] == str(raiz / "dados")
    assert lancador.python_com_console(r"C:\Py\pythonw.exe") == r"C:\Py\python.exe"
    assert lancador.python_com_console("/usr/bin/python3") == "/usr/bin/python3"


def test_job_roda_com_o_ambiente_da_instalacao_e_log(tmp_path):
    corpo = "import os, sys\nprint('job', sys.argv[1], os.environ['GP_DATA_DIR'])\nsys.exit(7)\n"
    raiz, instalacao = raiz_falsa(tmp_path, run_job=corpo)
    assert lancador.rodar_job(raiz, instalacao, "diario") == 7
    log = (raiz / "jobs" / "logs" / "tarefa-diario.log").read_text(encoding="utf-8")
    assert log.strip() == "job diario %s" % instalacao["dados"]


def test_job_que_passa_do_teto(tmp_path, monkeypatch):
    raiz, instalacao = raiz_falsa(tmp_path, run_job="import time\ntime.sleep(30)\n")
    monkeypatch.setattr(lancador, "TETO_JOB_S", 0.5)
    assert lancador.rodar_job(raiz, instalacao, "mensal") == base.EXIT_TIMEOUT


def test_painel_sobe_outra_vez_depois_de_cair(tmp_path):
    contador = tmp_path / "vezes"
    corpo = (
        "import pathlib, sys\n"
        "p = pathlib.Path(%r)\n"
        "n = int(p.read_text()) + 1 if p.exists() else 1\n"
        "p.write_text(str(n))\n"
        "print('painel', sys.argv[1], n)\n"
        "sys.exit(0 if n >= 3 else 1)\n" % str(contador)
    )
    raiz, instalacao = raiz_falsa(tmp_path, web=corpo)
    esperas = []
    assert lancador.servir_painel(raiz, instalacao, "--local", esperar=esperas.append) == 0
    assert esperas == [lancador.ESPERA_PAINEL_CAIU_S] * 2 and contador.read_text(encoding="utf-8") == "3"
    pids = json.loads((raiz / "jobs" / plataforma.NOME_PID_PAINEL).read_text(encoding="utf-8"))
    assert pids["lancador"] == os.getpid() and isinstance(pids["painel"], int)
    assert "painel --local 3" in (raiz / "jobs" / "logs" / "tarefa-painel.log").read_text(encoding="utf-8")


class _Respostas(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404 if self.path == "/erro" else 200)
        self.end_headers()

    def log_message(self, *_args):
        return


def test_painel_responde_ate_com_erro_http():
    servidor = http.server.HTTPServer(("127.0.0.1", 0), _Respostas)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        porta = servidor.server_address[1]
        assert lancador.painel_responde("http://127.0.0.1:%d/" % porta)
        assert lancador.painel_responde("http://127.0.0.1:%d/erro" % porta)
    finally:
        servidor.shutdown()
        servidor.server_close()
    livre = socket.socket()
    livre.bind(("127.0.0.1", 0))
    porta_fechada = livre.getsockname()[1]
    livre.close()
    assert not lancador.painel_responde("http://127.0.0.1:%d/" % porta_fechada, timeout_s=0.5)
    assert not lancador.painel_responde("nao-e-url")


def test_janela_sobe_o_painel_quando_ninguem_responde(tmp_path):
    raiz, _ = raiz_falsa(tmp_path)
    padrao = lancador.especificacao_do_painel(raiz)
    assert padrao["argumentos"][1:] == ["painel", "--local"] and padrao["alvo"] == sys.executable
    gravada = {"alvo": "pythonw.exe", "argumentos": ["lancador.py", "painel", "--rede"], "pasta": "j"}
    (raiz / "jobs" / "goal-pacer-painel.json").write_text(json.dumps(gravada), encoding="utf-8")
    assert lancador.especificacao_do_painel(raiz) == gravada

    subidos = []
    assert lancador.garantir_painel(raiz, responde=lambda: True, subir=subidos.append) and subidos == []
    respostas = iter([False, False, True])
    assert lancador.garantir_painel(
        raiz, responde=lambda: next(respostas), subir=subidos.append, esperar=lambda _s: None
    )
    assert subidos == [gravada]
    assert not lancador.garantir_painel(raiz, responde=lambda: False, subir=subidos.append, esperar=lambda _s: None)


def test_navegador_em_modo_app(tmp_path, monkeypatch):
    edge = tmp_path / "PF86" / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    chrome = tmp_path / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"
    for exe in (edge, chrome):
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
    ambiente = {"ProgramFiles(x86)": str(tmp_path / "PF86"), "LOCALAPPDATA": str(tmp_path / "Local")}
    monkeypatch.setattr(processos, "WINDOWS", False)  # sem o registro de verdade: só as pastas do teste
    achar = lambda nome: lancador.achar_executavel(nome, ambiente)  # noqa: E731
    assert achar("msedge.exe") == str(edge) and achar("chrome.exe") == str(chrome) and achar("brave.exe") is None
    assert lancador.escolher_navegador("ChromeHTML", achar) == str(chrome)
    assert lancador.escolher_navegador("BraveHTML", achar) == str(edge)  # sem Brave, o Edge
    assert lancador.escolher_navegador("FirefoxURL-308046B0AF4A39CB", achar) == str(edge)
    assert lancador.escolher_navegador(None, lambda _n: None) is None
    assert lancador.comando_da_janela("msedge.exe") == [
        "msedge.exe",
        "--app=http://127.0.0.1:8765/?janela=1",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    abertos = []
    monkeypatch.setattr(plataforma, "atual", type("S", (), {"abrir_url": staticmethod(abertos.append)}))
    lancador.abrir_no_navegador(None)
    assert abertos == [lancador.ENDERECO]


@pytest.mark.parametrize(
    ("argv", "esperado"),
    [
        (["job", "diario"], ("job", "diario")),
        (["painel", "--rede"], ("painel", "--rede")),
        (["painel"], ("painel", "--local")),
        (["janela"], ("janela",)),
    ],
)
def test_main_escolhe_o_alvo(argv, esperado, tmp_path, monkeypatch):
    chamadas = []
    monkeypatch.setattr(lancador, "raiz_da_instalacao", lambda: tmp_path)
    monkeypatch.setattr(lancador, "rodar_job", lambda _r, _i, job: chamadas.append(("job", job)) or 0)
    monkeypatch.setattr(lancador, "servir_painel", lambda _r, _i, modo: chamadas.append(("painel", modo)) or 0)
    monkeypatch.setattr(lancador, "abrir_janela", lambda _r: chamadas.append(("janela",)) or 0)
    assert lancador.main(argv) == 0 and chamadas == [esperado]
