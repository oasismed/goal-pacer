"""D-14: caminhos de erro do painel (web.py): rede sem interface, pedidos malformados, cliente que some e o CLI
do servidor do começo ao fim, fechado por sinal como o launchctl faz."""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

import web
from goalpacer import copy
from test_web import IP_TESTE, RAIZ_REPO, dados, na_rede, pedir, rede, servidor  # noqa: F401 - fixtures


class SocketFalso:
    def __init__(self, ip=None, erro=None):
        self.ip, self.erro, self.fechado = ip, erro, False

    def connect(self, _destino):
        if self.erro:
            raise self.erro

    def getsockname(self):
        return (self.ip, 1)

    def close(self):
        self.fechado = True


def test_ip_e_nome_na_rede_sem_interface(monkeypatch):
    monkeypatch.delenv("GP_IP_REDE", raising=False)
    monkeypatch.delenv("GP_NOME_LOCAL", raising=False)
    for falso, esperado in (
        (SocketFalso(ip="192.168.1.20"), "192.168.1.20"),
        (SocketFalso(ip="127.0.0.1"), None),
        (SocketFalso(ip="0.0.0.0"), None),
        (SocketFalso(erro=OSError("rede fora")), None),
    ):
        monkeypatch.setattr(web.socket, "socket", lambda *_a, _f=falso: _f)
        assert web.ip_na_rede() == esperado and falso.fechado
    monkeypatch.setenv("GP_PLATAFORMA", "linux")
    monkeypatch.setattr(web.socket, "gethostname", lambda: "Casa.lan")
    assert web.nome_local() == "casa.local"
    monkeypatch.setattr(web.socket, "gethostname", lambda: "")
    assert web.nome_local() is None
    monkeypatch.setenv("GP_PLATAFORMA", "macos")

    def scutil_ausente(*_a, **_k):
        raise FileNotFoundError("scutil")

    monkeypatch.setattr(web.subprocess, "run", scutil_ausente)
    assert web.nome_local() is None
    monkeypatch.setattr(
        web.subprocess, "run", lambda *_a, **_k: subprocess.CompletedProcess([], 0, stdout="Mac-Teste\n", stderr="")
    )
    assert web.nome_local() == "mac-teste.local"


def pedido_cru(srv, metodo, caminho, corpo: bytes, cabecalhos: dict):
    conexao = http.client.HTTPConnection("127.0.0.1", srv.porta, timeout=10)
    headers = {"Host": "127.0.0.1:%d" % srv.porta, "X-GP-Token": srv.token, **cabecalhos}
    conexao.putrequest(metodo, caminho, skip_accept_encoding=True)
    for nome, valor in headers.items():
        conexao.putheader(nome, valor)
    conexao.endheaders(corpo)
    resposta = conexao.getresponse()
    status, bruto = resposta.status, resposta.read()
    conexao.close()
    return status, json.loads(bruto or b"{}")


def test_corpos_malformados(servidor):  # noqa: F811
    json_tipo = {"Content-Type": "application/json"}
    assert pedido_cru(servidor, "POST", "/api/checkin", b"{}", {**json_tipo, "Content-Length": "abc"})[0] == 413
    status, corpo = pedido_cru(servidor, "POST", "/api/checkin", b"[1]", {**json_tipo, "Content-Length": "3"})
    assert status == 400 and corpo["erro"] == "esperado objeto JSON"
    assert pedir(servidor, "POST", "/api/decisao", {"meta": "../M01", "saida": "manter"})[0] == 400
    status, _ = pedido_cru(
        servidor, "POST", "/api/erro-front", b"x", {"Content-Type": "text/plain", "Content-Length": "1"}
    )
    assert status == 415
    cabecalho_ruim = {"Cookie": 'gp_aparelho="sem fim'}
    assert pedir(servidor, "GET", "/api/status", cabecalhos=cabecalho_ruim)[0] == 200  # cookie ilegível é ignorado


def test_cookie_ilegivel_nao_derruba(monkeypatch, servidor):  # noqa: F811
    def quebra(*_a, **_k):
        raise web.CookieError("biscoito quebrado")

    monkeypatch.setattr(web, "SimpleCookie", quebra)
    assert pedir(servidor, "GET", "/api/status")[0] == 200


def test_pareamento_com_corpo_errado(rede):  # noqa: F811
    srv = rede()
    host = "%s:%d" % (IP_TESTE, srv.porta)
    conexao = http.client.HTTPConnection("127.0.0.1", srv.porta, timeout=10)
    conexao.request(
        "POST",
        "/api/parear",
        body="x",
        headers={"Host": host, "Origin": "http://" + host, "Content-Type": "text/plain"},
    )
    assert conexao.getresponse().status == 415
    conexao.close()


def test_cliente_que_some_no_meio_da_resposta(monkeypatch, servidor):  # noqa: F811
    def some(*_a, **_k):
        raise BrokenPipeError("cliente fechou")

    monkeypatch.setattr(web.Tratador, "_tela", some)
    with pytest.raises((http.client.RemoteDisconnected, ConnectionError)):
        pedir(servidor, "GET", "/api/status")
    monkeypatch.undo()
    status, corpo, _ = pedir(servidor, "GET", "/api/status")  # o servidor segue atendendo
    assert status == 200 and corpo["ok"]


def test_demo_sem_fixtures(monkeypatch, tmp_path):
    import demo_painel

    monkeypatch.setattr(demo_painel, "FIXTURE", tmp_path / "nao-existe")
    with pytest.raises(web.GpErro, match="fixtures de exemplo ausentes"):
        web.preparar_demo(tmp_path / "destino")


def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


@pytest.mark.posix
def test_cli_do_demo_do_comeco_ao_sinal(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    env.update({"GP_LOGS_DIR": str(tmp_path / "logs"), "TMPDIR": str(tmp_path) + "/"})
    porta = _porta_livre()
    processo = subprocess.Popen(
        [sys.executable, str(RAIZ_REPO / "scripts" / "web.py"), "--demo", "--porta", str(porta)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        # pronto = responde HTTP: o connect sozinho passa assim que a porta escuta, antes do servidor pôr o handler
        # do sinal (e o SIGTERM cedo demais mata sem apagar a pasta do demo)
        for _ in range(600):
            try:
                conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=1)
                conexao.request("GET", "/")
                conexao.getresponse().read()
                conexao.close()
                break
            except OSError:
                time.sleep(0.1)
        demos = list(Path(tmp_path).glob("gp-demo-*"))
        assert len(demos) == 1
        processo.send_signal(signal.SIGTERM)
        saida, erro = processo.communicate(timeout=30)
    finally:
        if processo.poll() is None:
            processo.kill()
            processo.communicate(timeout=10)
    assert processo.returncode == 0, erro
    assert copy.texto("painel.rodape", endereco="http://127.0.0.1:%d/" % porta).split("http")[0] in saida
    assert "Ctrl+C" in saida and not demos[0].exists()  # a pasta do demo some ao fechar

    ocupada = socket.socket()
    ocupada.bind(("127.0.0.1", 0))
    ocupada.listen(1)
    try:
        proc = subprocess.run(
            [sys.executable, str(RAIZ_REPO / "scripts" / "web.py"), "--demo", "--porta", str(ocupada.getsockname()[1])],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=60,
        )
    finally:
        ocupada.close()
    assert proc.returncode == 4 and "indisponível" in proc.stderr and not list(Path(tmp_path).glob("gp-demo-*"))
