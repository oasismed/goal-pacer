"""Painel sem terminal: tela Começar (onboarding pela tela), doctor e atualizar pelo painel (acoes_locais.py e web.py),
o disparo do job pelo agendador e a meta completada pelo prazo."""

from __future__ import annotations

import http.client
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import pytest

import acoes_locais
import onboarding
import web
from goalpacer import base, copy, plataforma
from test_web import RAIZ_REPO, dados, na_rede, pedir, rede  # noqa: F401 - fixtures

FIXTURES = Path(__file__).resolve().parent / "fixtures"
METAS_DA_TELA = [
    {"titulo": "Correr 10 km", "prazo": "2026-12-15", "custo_h_semana_escolhido": 3, "impacto": "essencial"},
    {"titulo": "Ler 6 livros", "prazo": "2027-06-30", "custo_h_semana_escolhido": 2, "objetivo": "Mais repertório"},
]


@pytest.fixture
def vazio(tmp_path, agora_fixo, monkeypatch):
    pasta = tmp_path / "vazia"
    pasta.mkdir()
    monkeypatch.setenv("GP_DATA_DIR", str(pasta))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    monkeypatch.setenv("GP_AGORA", "2026-09-28T09:00:00-03:00")
    srv = web.servir(0, pasta)
    srv.offline = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def test_sem_metas_as_telas_abrem_vazias_e_o_comecar_responde(vazio):
    """Antes do onboarding as telas abrem com valores vazios (nunca dados de exemplo) e marcadas como vazias; o front
    manda a primeira visita para a tela Começar."""
    for rota in ("/api/painel", "/api/metas", "/api/objetivos", "/api/checkin", "/api/status", "/api/conexoes"):
        status, corpo, _ = pedir(vazio, "GET", rota)
        assert status == 200 and corpo["vazio"] is True, (rota, corpo)
    assert pedir(vazio, "GET", "/api/metas")[1]["modelo"]["metas"] == []
    assert pedir(vazio, "GET", "/api/periodo?nivel=ano")[1]["vazio"] is True
    assert not (vazio.dados / "contexto.md").exists()  # a pasta de dados de verdade segue intocada
    status, html, _ = pedir(vazio, "GET", "/", token=False)
    assert status == 200 and vazio.token in html
    status, corpo, _ = pedir(vazio, "GET", "/api/comecar")
    modelo = corpo["modelo"]
    assert status == 200 and modelo["configurado"] is False and modelo["rascunho"]["existe"] is False
    assert modelo["textos"]["comecar_gravar"] == copy.texto("painel.comecar_gravar") and modelo["deteccao"] is None
    assert modelo["versao"] == base.VERSAO_APP and modelo["hoje"] == "2026-09-28" and modelo["teto_metas"] == 5
    assert pedir(vazio, "GET", "/api/comecar", token=False)[0] == 403


def test_comecar_confere_a_conta_grava_o_rascunho_e_as_metas(vazio):
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/detectar", {})
    deteccao = corpo["deteccao"]
    assert status == 200 and deteccao["calendar_id_metas"] == "metas-fixture@group.calendar.google.com"
    assert pedir(vazio, "GET", "/api/comecar")[1]["modelo"]["deteccao"] == deteccao  # guardada para a tela voltar
    assert pedir(vazio, "POST", "/api/comecar/gravar", {})[0] == 409  # nada respondido
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/rascunho", {"respostas": {"segredo": 1}})
    assert status == 400 and "segredo" in corpo["erro"]
    assert pedir(vazio, "POST", "/api/comecar/rascunho", {"respostas": []})[0] == 400
    respostas = {
        "metas": [dict(METAS_DA_TELA[0]), {"titulo": "Sem horas", "prazo": "2026-11-01"}],
        "objetivos": [{"titulo": "Mais repertório"}],
        "horario_util": {"seg_sex": "08:00-19:00", "sab": "nenhum", "dom": "nenhum"},
        "fontes_ativas": ["gmail"],
        "email_proprio": deteccao["email_proprio"],
        "calendar_id_metas": deteccao["calendar_id_metas"],
        "calendar_id_primario": deteccao["calendar_id_primario"],
        "timezone": "America/Sao_Paulo",
        "idioma": "pt-BR",
    }
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/rascunho", {"respostas": respostas})
    assert status == 200 and "metas" in corpo["rascunho"]["respondidas"]
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/gravar", {})
    assert status == 400 and corpo["erro"] == copy.texto("painel.comecar_corrigir")
    assert any("metas[1].custo_h_semana_escolhido" in erro for erro in corpo["erros"])
    assert not (vazio.dados / "contexto.md").exists()  # nada gravado com campo recusado
    pedir(vazio, "POST", "/api/comecar/rascunho", {"respostas": {"metas": [dict(m) for m in METAS_DA_TELA]}})
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/gravar", {})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.comecar_gravado"), corpo
    assert (vazio.dados / "contexto.md").exists() and len(list((vazio.dados / "metas").glob("M*.md"))) == 2
    modelo = pedir(vazio, "GET", "/api/comecar")[1]["modelo"]
    assert modelo["configurado"] is True and modelo["rascunho"]["existe"] is False
    assert pedir(vazio, "GET", "/api/metas")[0] == 200
    assert not (vazio.dados / ".lock").exists()


def test_acoes_locais_nunca_pela_rede_nem_no_exemplo(rede, vazio):  # noqa: F811
    srv = rede()
    for rota in (*web.ACOES_LOCAIS, "/api/comecar", "/api/atualizacao"):
        metodo = "GET" if rota in web.LEITURAS_LOCAIS else "POST"
        assert na_rede(srv, metodo, rota, {} if metodo == "POST" else None, token=True)[0] == 403, rota
    vazio.demo = True
    status, corpo, _ = pedir(vazio, "POST", "/api/doctor", {})
    assert status == 409 and corpo["erro"] == copy.texto("painel.acao_no_exemplo")


def test_primeiro_dia_dispara_o_job_pelo_agendador(vazio, monkeypatch):
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/primeiro-dia", {})
    assert status == 409 and corpo["erro"] == copy.texto("painel.comecar_sem_instalacao")
    monkeypatch.setattr(acoes_locais, "_instalacao", lambda: {"modo": "clone"})
    pedidos: list = []

    class Agendador:
        def iniciar(self, job):
            pedidos.append(job)
            return None if len(pedidos) == 1 else "Could not find service"

    class Plataforma:
        agendador = Agendador()

    monkeypatch.setattr(plataforma, "atual", Plataforma)
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/primeiro-dia", {})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.comecar_primeiro_dia_ok") and pedidos == ["diario"]
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/primeiro-dia", {})
    assert status == 500 and "Could not find service" in corpo["erro"]


def test_doctor_pela_tela(vazio, monkeypatch):
    chamadas: list = []

    def rodar(argv, timeout_s):
        chamadas.append((argv, timeout_s))
        return 3, {"ok": False, "itens": [{"nome": "pasta de dados", "ok": False, "detalhe": "rode o onboarding"}]}

    monkeypatch.setattr(acoes_locais, "_rodar_json", rodar)
    status, corpo, _ = pedir(vazio, "POST", "/api/doctor", {})
    assert status == 200 and corpo["tudo_certo"] is False and corpo["itens"][0]["nome"] == "pasta de dados"
    assert chamadas[0][0][1:] == ["--doctor", "--json", "--offline"] and chamadas[0][1] == acoes_locais.TIMEOUT_DOCTOR_S
    monkeypatch.setattr(acoes_locais, "_rodar_json", lambda *_a: (0, {"sem": "itens"}))
    assert pedir(vazio, "POST", "/api/doctor", {})[0] == 500


def _script(tmp_path: Path, corpo: str) -> str:
    caminho = tmp_path / "cli_falso.py"
    caminho.write_text(corpo, encoding="utf-8")
    return str(caminho)


def test_rodar_json_le_a_ultima_linha_json_e_diz_por_que_falhou(tmp_path, monkeypatch):
    assert acoes_locais._rodar_json([_script(tmp_path, "print('{\"a\": 1}')")], 30) == (0, {"a": 1})
    aviso = "print('aviso antes'); print('{\"b\": 2}'); raise SystemExit(3)"
    assert acoes_locais._rodar_json([_script(tmp_path, aviso)], 30) == (3, {"b": 2})
    assert acoes_locais._rodar_json([_script(tmp_path, "print('[1, 2]')")], 30) == (0, {})
    quebra = "import sys; print('sem json'); print('erro: conector fora do ar', file=sys.stderr); raise SystemExit(4)"
    with pytest.raises(base.GpErro, match="conector fora do ar") as exc:
        acoes_locais._rodar_json([_script(tmp_path, quebra)], 30)
    assert exc.value.codigo == 4
    with pytest.raises(base.GpErro, match="passou de"):
        acoes_locais._rodar_json([_script(tmp_path, "import time; time.sleep(5)")], 0.5)
    monkeypatch.setattr(acoes_locais.sys, "executable", str(tmp_path / "nao-existe"))
    with pytest.raises(base.GpErro, match="não consegui rodar"):
        acoes_locais._rodar_json(["x.py"], 5)


def test_atualizar_pela_tela_roda_em_segundo_plano(vazio, monkeypatch, tmp_path):
    assert pedir(vazio, "POST", "/api/atualizar", {})[0] == 409  # sem instalação
    monkeypatch.setattr(acoes_locais, "_instalacao", lambda: {"modo": "copia", "versao": "0.1.0"})
    monkeypatch.setattr(acoes_locais.canal, "endereco", lambda _app: None)  # cópia sem canal de versões
    status, corpo, _ = pedir(vazio, "POST", "/api/atualizar", {})
    assert status == 400 and corpo["erro"] == copy.texto("painel.atualizar_pelo_zip")
    monkeypatch.setattr(acoes_locais, "_instalacao", lambda: {"modo": "clone", "versao": "0.1.0"})
    iniciados: list = []

    class Processo:
        def __init__(self, argv, **kw):
            iniciados.append((argv, kw))
            kw["stdout"].write("versão nova: v0.2.0, assinada por quem publica o Goal Pacer\n")
            self.pid = os.getpid()  # vivo enquanto o teste roda

    monkeypatch.setattr(acoes_locais.subprocess, "Popen", Processo)
    status, corpo, _ = pedir(vazio, "POST", "/api/atualizar", {})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.atualizar_iniciado")
    argv, kw = iniciados[0]
    assert argv[1:] == [str(acoes_locais.SCRIPTS / "instalar.py"), "--update", "--nao-interativo"]
    assert kw["start_new_session"] is True
    status, corpo, _ = pedir(vazio, "POST", "/api/atualizar", {})
    assert corpo["mensagem"] == copy.texto("painel.atualizar_em_andamento") and len(iniciados) == 1
    status, corpo, _ = pedir(vazio, "GET", "/api/atualizacao")
    assert status == 200 and corpo["modelo"]["rodando"] is True and corpo["modelo"]["versao"] == "0.1.0"
    assert corpo["modelo"]["linhas"] == ["versão nova: v0.2.0, assinada por quem publica o Goal Pacer"]
    (base.jobs_dir() / "logs" / acoes_locais.NOME_PID_ATUALIZAR).write_text("lixo", encoding="utf-8")
    assert pedir(vazio, "GET", "/api/atualizacao")[1]["modelo"]["rodando"] is False


def test_agendador_inicia_o_job_agora(tmp_path, monkeypatch):
    registro = tmp_path / "chamadas.txt"
    falso = tmp_path / "bin"
    falso.write_text(
        '#!/bin/sh\necho "$@" >> "%s"\n[ "$FALHAR" = 1 ] && echo "sem servico" && exit 3\nexit 0\n' % registro
    )
    falso.chmod(0o755)
    monkeypatch.setenv("GP_LAUNCHCTL", str(falso))
    monkeypatch.setenv("GP_SYSTEMCTL", str(falso))
    assert plataforma.Launchd().iniciar("diario") is None
    assert plataforma.Systemd().iniciar("diario") is None
    monkeypatch.setenv("FALHAR", "1")
    assert plataforma.Launchd().iniciar("diario") == "sem servico"
    linhas = registro.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "kickstart gui/%d/com.goal-pacer.diario" % os.getuid()
    assert linhas[1] == "--user start --no-block goal-pacer-diario.service"


def test_meta_da_tela_ganha_horizonte_semanas_e_confianca_pelo_prazo():
    hoje = date(2026, 9, 28)
    completa = onboarding.completar_meta
    assert completa({"prazo": "2026-12-29"}, hoje) == {
        "prazo": "2026-12-29",
        "horizonte": "trimestre",
        "semanas_pesquisa": 14,
        "confianca": "usuario",
    }
    assert completa({"prazo": "2026-12-30"}, hoje)["horizonte"] == "semestre"
    assert completa({"prazo": "2027-03-31"}, hoje)["horizonte"] == "semestre"
    assert completa({"prazo": "2027-04-01"}, hoje)["horizonte"] == "ano"
    assert completa({"prazo": "2026-09-28"}, hoje)["semanas_pesquisa"] == 1
    dada = {"prazo": "2027-06-01", "horizonte": "trimestre", "semanas_pesquisa": 5, "confianca": "alta"}
    assert completa(dada, hoje) == dada
    assert completa({"prazo": "amanhã"}, hoje) == {"prazo": "amanhã"}


def test_cli_sem_onboarding_serve_a_tela_comecar(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    env["GP_LOGS_DIR"] = str(tmp_path / "logs")
    processo = subprocess.Popen(
        [sys.executable, str(RAIZ_REPO / "scripts" / "web.py"), "--dados", str(tmp_path / "vazia"), "--porta", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        primeira = processo.stdout.readline() if processo.stdout else ""
        porta = int(primeira.rsplit(":", 1)[-1].split("/")[0]) if "127.0.0.1:" in primeira else 0
        for _ in range(600):  # pronto = responde HTTP; o sinal antes disso mata sem o handler de encerrar
            try:
                conexao = http.client.HTTPConnection("127.0.0.1", porta, timeout=1)
                conexao.request("GET", "/")
                conexao.getresponse().read()
                conexao.close()
                break
            except OSError:
                time.sleep(0.1)
    finally:
        processo.terminate()
        saida, erro = processo.communicate(timeout=30)
    assert "http://127.0.0.1:" in primeira and processo.returncode == 0, erro + saida


def test_conta_confere_claude_e_conectores_sem_token(vazio, monkeypatch, tmp_path):
    """A tela Começar confere sozinha: ``claude auth status`` e ``claude mcp list`` (sem tokens). Sem o Claude Code,
    tudo desconectado; no --offline, as fixtures."""
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/conta", {})
    conta = corpo["conta"]
    assert status == 200 and conta["claude"]["logado"] is True and conta["conectores"]["Google_Calendar"] == "conectado"
    monkeypatch.setattr(acoes_locais, "_caminho_do_claude", lambda: None)
    conta = acoes_locais.estado_da_conta(offline=False)
    assert conta["claude"] == {"instalado": False, "logado": False, "plano": None, "instalando": False}
    assert set(conta["conectores"].values()) == {"desconectado"}
    claude = tmp_path / "claude"
    claude.write_text(
        '#!/bin/sh\nif [ "$1" = auth ]; then echo \'{"loggedIn": true, "subscriptionType": "pro"}\'; exit 0; fi\n'
        'printf "claude.ai Gmail: https://x - \\342\\234\\224 Connected\\nclaude.ai Google Calendar: https://x - \\342\\234\\230 Needs authentication\\n"\n',
        encoding="utf-8",
    )
    claude.chmod(0o755)
    monkeypatch.setattr(acoes_locais, "_caminho_do_claude", lambda: str(claude))
    conta = acoes_locais.estado_da_conta(offline=False)
    assert conta["claude"]["plano"] == "pro" and conta["conectores"]["Gmail"] == "conectado"
    assert conta["conectores"]["Google_Calendar"] == "reconectar" and conta["conectores"]["Notion"] == "desconectado"


def test_instalar_e_login_do_claude_pela_tela(vazio, monkeypatch, tmp_path):
    abertos: list = []
    monkeypatch.setattr(
        acoes_locais.subprocess,
        "Popen",
        lambda argv, **kw: abertos.append((argv, kw)) or type("P", (), {"pid": 999999})(),
    )
    monkeypatch.setattr(acoes_locais, "_caminho_do_claude", lambda: None)
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/instalar-claude", {})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.comecar_claude_instalando")
    assert abertos[0][0] == acoes_locais.INSTALAR_CLAUDE_POSIX and abertos[0][1]["start_new_session"] is True
    assert (base.jobs_dir() / "logs" / acoes_locais.NOME_PID_CLAUDE).read_text(encoding="utf-8") == "999999"
    assert pedir(vazio, "POST", "/api/comecar/login-claude", {})[0] == 409  # sem claude não há login
    monkeypatch.setattr(acoes_locais, "_caminho_do_claude", lambda: "/opt/claude/bin/claude")
    assert pedir(vazio, "POST", "/api/comecar/instalar-claude", {})[1]["mensagem"] == copy.texto(
        "painel.comecar_claude_ok"
    )


LOGIN_FALSO = """#!%s
import sys
print("Opening browser to sign in...")
print("If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?code=true&state=teste", flush=True)
sys.stdout.write("Paste code here if prompted > ")
sys.stdout.flush()
codigo = sys.stdin.readline().strip()
if codigo == "certo#estado-1":
    print("Login successful.")
    sys.exit(0)
print("Login failed: Request failed with status code 400 (https://platform.claude.com/x)")
sys.exit(1)
"""


def test_login_do_claude_sem_terminal(vazio, monkeypatch, tmp_path):
    """O claude auth login roda por baixo: a tela recebe o endereço da página de login e manda o código colado."""
    claude = tmp_path / "claude"
    claude.write_text(LOGIN_FALSO % sys.executable, encoding="utf-8")
    claude.chmod(0o755)
    monkeypatch.setattr(acoes_locais, "_caminho_do_claude", lambda: str(claude))
    assert pedir(vazio, "POST", "/api/comecar/login-codigo", {"codigo": "certo#estado-1"})[0] == 409  # sem login aberto
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/login-claude", {})
    assert status == 200 and corpo["url"] == "https://claude.com/cai/oauth/authorize?code=true&state=teste"
    assert pedir(vazio, "POST", "/api/comecar/login-codigo", {"codigo": "curto"})[0] == 400
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/login-codigo", {"codigo": "errado#estado-1"})
    assert status == 400 and "status code 400" in corpo["erro"] and "https://" not in corpo["erro"]
    assert pedir(vazio, "POST", "/api/comecar/login-claude", {})[1]["url"]  # pede outro
    status, corpo, _ = pedir(vazio, "POST", "/api/comecar/login-codigo", {"codigo": " certo#estado-1 "})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.comecar_login_ok") and vazio.login is None


def test_remover_pelo_painel_pede_confirmacao(vazio, monkeypatch, tmp_path):
    abertos: list = []
    monkeypatch.setattr(
        acoes_locais.subprocess, "Popen", lambda argv, **kw: abertos.append(argv) or type("P", (), {"pid": 1})()
    )
    assert pedir(vazio, "POST", "/api/desinstalar", {})[0] == 400
    assert pedir(vazio, "POST", "/api/desinstalar", {"confirmar": True})[0] == 409  # sem instalação
    instalacao = {"app": str(tmp_path / "app"), "python3": "/py/python3", "dados": "/d"}
    monkeypatch.setattr(acoes_locais, "_instalacao", lambda: instalacao)
    status, corpo, _ = pedir(vazio, "POST", "/api/desinstalar", {"confirmar": True})
    assert status == 200 and corpo["mensagem"] == copy.texto("painel.manutencao_removendo", dados="/d")
    assert abertos == [
        ["/py/python3", str(tmp_path / "app" / "scripts" / "instalar.py"), "--uninstall", "--nao-interativo"]
    ]
