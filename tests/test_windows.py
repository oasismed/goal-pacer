"""Windows: Agendador de Tarefas, atalhos, lançador, ícone e comando, testados em qualquer sistema.

``schtasks`` e PowerShell nunca rodam aqui: ``plataforma._rodar`` e o executor do PowerShell viram gravadores; o
painel não sobe (``subir_painel``/``parar_painel`` trocados). A instalação de verdade no Windows roda num Windows por
(job ``windows``: Agendador, atalho, painel respondendo e desinstalação).
"""

from __future__ import annotations

import base64
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from goalpacer import atalhos, base, io, plataforma, processos

RAIZ_REPO = Path(__file__).resolve().parent.parent
NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


@pytest.fixture
def windows(tmp_path, monkeypatch):
    monkeypatch.setenv("GP_PLATAFORMA", "windows")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    chamadas: list[list[str]] = []
    scripts: list[str] = []
    respostas: dict[str, int] = {}

    def rodar(argv, timeout_s=60):
        chamadas.append(list(argv))
        return respostas.get(argv[1], 0), ""

    def powershell(script, timeout_s=60):
        scripts.append(script)
        return 0, ""

    subidos: list[dict] = []
    parados: list[Path] = []
    monkeypatch.setattr(plataforma, "_rodar", rodar)
    monkeypatch.setattr(atalhos, "rodar_powershell", powershell)
    monkeypatch.setattr(plataforma, "subir_painel", subidos.append)
    monkeypatch.setattr(plataforma, "parar_painel", parados.append)
    jobs = tmp_path / "raiz" / "jobs"
    jobs.mkdir(parents=True)
    valores = {
        "PYTHON3": r"C:\Users\Zé Silva\AppData\Local\Programs\Python\Python312\python.exe",
        "APP": str(tmp_path / "raiz" / "app"),
        "JOBS": str(jobs),
        "RAIZ": str(tmp_path / "raiz"),
        "DADOS": str(tmp_path / "raiz" / "dados"),
        "CLAUDE": r"C:\Users\Zé Silva\.local\bin\claude.exe",
    }
    return {
        "chamadas": chamadas,
        "scripts": scripts,
        "respostas": respostas,
        "subidos": subidos,
        "parados": parados,
        "jobs": jobs,
        "valores": valores,
        "tmp": tmp_path,
    }


def test_escolhe_o_windows_pelo_sistema_ou_pela_variavel(monkeypatch):
    monkeypatch.setenv("GP_PLATAFORMA", "windows")
    sistema = plataforma.atual()
    assert sistema.nome == "windows" and isinstance(sistema.agendador, plataforma.TarefasWindows)
    assert sistema.janela_nativa and not sistema.precisa_xcode and sistema.pastas_protegidas == ()
    assert sistema.manter_acordado(123) is None
    monkeypatch.delenv("GP_PLATAFORMA")
    monkeypatch.setattr(sys, "platform", "win32")
    assert plataforma.nome_atual() == "windows"
    monkeypatch.setattr(sys, "platform", "linux")
    assert plataforma.nome_atual() == "linux"


def test_tarefas_renderizadas_em_utf16_conferidas_e_carregadas(windows):
    agendador = plataforma.atual().agendador
    app = RAIZ_REPO
    gerados = agendador.gerar(app, windows["jobs"], windows["valores"], "rede")
    assert list(gerados) == ["GoalPacer\\diario", "GoalPacer\\mensal", "GoalPacer\\painel"]
    diario = gerados["GoalPacer\\diario"][0]
    bruto = diario.read_bytes()
    assert bruto[:2] in (b"\xff\xfe", b"\xfe\xff")  # UTF-16 com BOM, o que o schtasks /XML lê
    tarefa = ET.fromstring(bruto)
    execucao = tarefa.find("%sActions/%sExec" % (NS, NS))
    pythonw = windows["valores"]["PYTHON3"].replace("python.exe", "pythonw.exe")
    assert execucao.findtext(NS + "Command") == pythonw
    lancador = str(Path(windows["valores"]["APP"]) / "scripts" / "lancador.py")
    assert execucao.findtext(NS + "Arguments") == '"%s" job diario' % lancador
    semana = tarefa.find("%sTriggers/%sCalendarTrigger/%sScheduleByWeek/%sDaysOfWeek" % (NS, NS, NS, NS))
    assert [d.tag[len(NS) :] for d in semana] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    assert tarefa.findtext("%sSettings/%sStartWhenAvailable" % (NS, NS)) == "true"
    mensal = ET.fromstring(gerados["GoalPacer\\mensal"][0].read_bytes())
    assert mensal.findtext(".//%sDay" % NS) == "1" and "T05:30:00" in mensal.findtext(".//%sStartBoundary" % NS)
    painel = json.loads(gerados["GoalPacer\\painel"][0].read_text(encoding="utf-8"))
    assert painel == {"alvo": pythonw, "argumentos": [lancador, "painel", "--rede"], "pasta": str(windows["jobs"])}

    assert agendador.carregar(gerados) == []
    criadas = [c[3] for c in windows["chamadas"] if c[1] == "/Create"]
    assert criadas == ["GoalPacer\\diario", "GoalPacer\\mensal"]
    assert windows["subidos"] == [painel] and windows["parados"] == [windows["jobs"]]
    assert "Startup" in windows["scripts"][0] and "WScript.Shell" in windows["scripts"][0]

    windows["respostas"]["/Create"] = 1
    assert agendador.carregar({"GoalPacer\\diario": [diario]}) == ["GoalPacer\\diario"]


def test_tarefa_torta_e_recusada(windows, tmp_path):
    app = tmp_path / "app-torto"
    (app / "jobs" / "windows").mkdir(parents=True)
    for job in plataforma.JOBS:
        texto = (RAIZ_REPO / "jobs" / "windows" / ("goal-pacer-%s.xml.tmpl" % job)).read_text(encoding="utf-8")
        (app / "jobs" / "windows" / ("goal-pacer-%s.xml.tmpl" % job)).write_text(
            texto.replace("job %s" % job, "job outro"), encoding="utf-8"
        )
    with pytest.raises(base.GpErro, match="não confere"):
        plataforma.atual().agendador.gerar(app, windows["jobs"], windows["valores"], "local")
    (app / "jobs" / "windows" / "goal-pacer-diario.xml.tmpl").write_text("<Task", encoding="utf-8")
    with pytest.raises(base.GpErro, match="XML válido"):
        plataforma.atual().agendador.gerar(app, windows["jobs"], windows["valores"], "local")


def test_carregados_iniciar_e_descarregar(windows):
    agendador = plataforma.atual().agendador
    atalho = agendador.pasta() / atalhos.NOME_PAINEL
    atalho.parent.mkdir(parents=True)
    atalho.write_bytes(b"lnk")
    assert agendador.carregados() == ({"GoalPacer\\diario", "GoalPacer\\mensal", "GoalPacer\\painel"}, None)
    windows["respostas"]["/Query"] = 1
    assert agendador.carregados() == ({"GoalPacer\\painel"}, None)
    windows["respostas"]["/Query"] = -1
    assert agendador.carregados()[0] is None
    assert agendador.iniciar("diario") is None and windows["chamadas"][-1][1:] == ["/Run", "/TN", "GoalPacer\\diario"]
    assert agendador.comando_agora("mensal") == "schtasks /Run /TN GoalPacer\\mensal"
    assert agendador.instalados(plataforma.JOBS) == []
    (windows["jobs"] / "goal-pacer-diario.xml").write_text("x", encoding="utf-8")
    removidos = agendador.descarregar(["GoalPacer\\diario", "GoalPacer\\painel"], windows["jobs"])
    assert removidos == ["GoalPacer\\diario", "GoalPacer\\painel"]
    assert not atalho.exists() and not (windows["jobs"] / "goal-pacer-diario.xml").exists()
    assert windows["parados"] == [windows["jobs"]]
    windows["respostas"]["/Delete"] = 1
    assert agendador.descarregar(["GoalPacer\\mensal"], windows["jobs"]) == []
    windows["respostas"]["/Run"] = 1
    assert "schtasks /Run exit 1" in agendador.iniciar("diario")


def test_parar_painel_encerra_so_os_dois_pids(tmp_path, monkeypatch):
    encerrados = []
    monkeypatch.setattr(processos, "vivo", lambda pid: pid in (11, 22))
    monkeypatch.setattr(processos, "encerrar", encerrados.append)
    (tmp_path / plataforma.NOME_PID_PAINEL).write_text(json.dumps({"lancador": 11, "painel": 22}), encoding="utf-8")
    plataforma.parar_painel(tmp_path)
    assert encerrados == [11, 22] and not (tmp_path / plataforma.NOME_PID_PAINEL).exists()
    plataforma.parar_painel(tmp_path)  # sem arquivo: nada acontece
    assert encerrados == [11, 22]


def test_notificacao_e_abrir_no_windows(windows, monkeypatch):
    sistema = plataforma.atual()
    assert sistema.notificar("Job d'hoje parou") is None
    assert "ToastNotificationManager" in windows["scripts"][-1] and "'Job d''hoje parou'" in windows["scripts"][-1]
    monkeypatch.setattr(atalhos, "rodar_powershell", lambda script, timeout_s=60: (1, "sem toast"))
    assert sistema.notificar("x") == "sem toast"
    abertos = []
    monkeypatch.setattr(plataforma.os, "startfile", abertos.append, raising=False)
    sistema.abrir_url("http://127.0.0.1:8765/")
    assert abertos == ["http://127.0.0.1:8765/"]


def test_powershell_codificado_e_atalho(tmp_path, monkeypatch):
    rodados = []

    def falso(argv, **_kwargs):
        rodados.append(argv)
        return type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(atalhos.subprocess, "run", falso)
    assert atalhos.rodar_powershell("Write-Output 'á'") == (0, "ok")
    assert base64.b64decode(rodados[0][-1]).decode("utf-16-le") == "Write-Output 'á'"
    assert rodados[0][1:6] == ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand"]
    script = atalhos.script_do_atalho(
        tmp_path / "Start Menu" / "Goal Pacer.lnk",
        r"C:\py\pythonw.exe",
        [r"C:\a b\lancador.py", "janela"],
        r"C:\j",
        r"C:\j\goal-pacer.ico",
        "Goal Pacer",
    )
    assert "$atalho.Arguments = '\"C:\\a b\\lancador.py\" janela'" in script
    assert "IconLocation = 'C:\\j\\goal-pacer.ico,0'" in script and script.endswith("$atalho.Save()")
    with pytest.raises(base.GpErro, match="não consegui criar o atalho"):
        atalhos.criar(tmp_path / "x.lnk", "a", [], "p", rodar=lambda _s: (1, "COM falhou"))
    assert atalhos.remover(tmp_path / "x.lnk") is False
    assert (
        atalhos.pythonw(r"C:\Py\python.exe").endswith("pythonw.exe")
        and atalhos.pythonw("/usr/bin/python3") == "/usr/bin/python3"
    )
    monkeypatch.delenv("APPDATA", raising=False)
    assert atalhos.pasta_inicializar().parts[-5:] == ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def test_icone_com_um_png_por_lado():
    pngs = {16: b"\x89PNG-16", 256: b"\x89PNG-256-maior"}
    dados = atalhos.ico(pngs)
    assert struct.unpack("<HHH", dados[:6]) == (0, 1, 2)
    lado, _, _, _, _, bits, tamanho, deslocamento = struct.unpack("<BBBBHHII", dados[6:22])
    assert (lado, bits, tamanho) == (16, 32, len(pngs[16])) and dados[deslocamento : deslocamento + tamanho] == pngs[16]
    lado, *_, tamanho, deslocamento = struct.unpack("<BBBBHHII", dados[22:38])
    assert lado == 0 and dados[deslocamento : deslocamento + tamanho] == pngs[256]  # 256 se escreve 0


def test_troca_atomica_espera_o_arquivo_aberto_no_windows(tmp_path, monkeypatch):
    tentativas = []
    real = io.os.replace

    def replace(origem, destino):
        tentativas.append(destino)
        if len(tentativas) < 3:
            raise PermissionError("em uso")
        real(origem, destino)

    monkeypatch.setattr(io.os, "replace", replace)
    monkeypatch.setattr(io.time, "sleep", lambda _s: None)
    monkeypatch.setattr(processos, "WINDOWS", True)
    io.escrever_atomico(tmp_path / "a.txt", "ok", bak=False)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "ok" and len(tentativas) == 3
    tentativas.clear()

    def sempre_em_uso(_origem, destino):
        tentativas.append(destino)
        raise PermissionError("em uso")

    monkeypatch.setattr(io.os, "replace", sempre_em_uso)
    with pytest.raises(base.GpErro, match="em uso"):
        io.escrever_atomico(tmp_path / "c.txt", "x", bak=False)
    assert len(tentativas) == io.TENTATIVAS_TROCA_WINDOWS  # desiste depois de um segundo
    monkeypatch.setattr(io.os, "replace", replace)
    monkeypatch.setattr(processos, "WINDOWS", False)
    tentativas.clear()
    with pytest.raises(base.GpErro, match="em uso"):
        io.escrever_atomico(tmp_path / "b.txt", "x", bak=False)
    assert len(tentativas) == 1


def test_comando_cmd_do_windows(tmp_path):
    import instalar

    raiz = tmp_path / "raiz"
    texto, codificacao = instalar._texto_do_cmd(raiz, raiz / "app", r"C:\Python312\python.exe")
    assert codificacao == "utf-8" and texto.endswith("\r\n") and "chcp" not in texto
    assert '"C:\\Python312\\python.exe" "%~dp0..\\app\\scripts\\goal_pacer.py" %*' in texto
    texto, _ = instalar._texto_do_cmd(raiz, tmp_path / "outro-app", r"C:\Users\Zé\python.exe")
    assert "chcp 65001 >nul" in texto and str(tmp_path / "outro-app" / "scripts" / "goal_pacer.py") in texto


def test_prompt_longo_vai_pela_entrada_no_windows(tmp_path, monkeypatch):
    """D-18: a linha de comando do Windows para em cerca de 32 mil caracteres; o prompt longo vai pela entrada padrão."""
    from goalpacer import proxy

    longo = "x" * (proxy.LIMITE_ARGUMENTO_WINDOWS + 1)
    monkeypatch.setattr(processos, "WINDOWS", False)
    assert proxy.prompt_pela_entrada(["claude", "-p", longo]) == (["claude", "-p", longo], None)
    monkeypatch.setattr(processos, "WINDOWS", True)
    assert proxy.prompt_pela_entrada(["claude", "-p", "curto"]) == (["claude", "-p", "curto"], None)
    assert proxy.prompt_pela_entrada(["claude", "-p", longo]) == (["claude", "-p"], longo)
    no_limite = "x" * proxy.LIMITE_ARGUMENTO_WINDOWS
    assert proxy.prompt_pela_entrada(["claude", no_limite]) == (["claude", no_limite], None)  # no teto, cabe
    assert proxy.prompt_pela_entrada(["claude", longo]) == (["claude"], longo)
    assert proxy.prompt_pela_entrada([longo]) == ([longo], None)  # sem binário antes, não é um prompt
    eco = tmp_path / "eco.py"
    eco.write_text("import sys\nprint(len(sys.argv), len(sys.stdin.read()))\n", encoding="utf-8")
    monkeypatch.setattr(processos, "isolamento", dict)  # os flags de console só existem no Windows de verdade
    resultado = proxy.executar_padrao([sys.executable, str(eco), longo], timeout_s=30, cwd=tmp_path)
    assert resultado.stdout.split() == [
        "1",
        str(len(longo)),
    ]  # só o script na linha de comando; o prompt veio pelo stdin


def test_claude_exe_antes_do_claude_cmd_do_npm(tmp_path, monkeypatch):
    from goalpacer import proxy

    monkeypatch.delenv("GP_CLAUDE_BIN", raising=False)
    npm = tmp_path / "npm" / "claude.cmd"
    npm.parent.mkdir()
    npm.write_text("@echo off", encoding="utf-8")
    nativo = tmp_path / "nativo" / "claude.exe"
    monkeypatch.setattr(proxy.shutil, "which", lambda _nome: str(npm))
    monkeypatch.setattr(proxy, "claude_bin_padrao", lambda: str(nativo))
    assert proxy.claude_bin() == str(npm)  # sem o nativo instalado, o do npm
    nativo.parent.mkdir()
    nativo.write_bytes(b"MZ")
    assert proxy.claude_bin() == str(nativo)
    monkeypatch.setattr(proxy.shutil, "which", lambda _nome: str(tmp_path / "npm" / "CLAUDE.BAT"))
    assert proxy.claude_bin() == str(nativo)
