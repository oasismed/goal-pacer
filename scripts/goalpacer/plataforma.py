"""plataforma.py: tudo o que muda entre macOS, Linux e Windows, atrás de uma interface pequena.

O resto do app é Python stdlib e não sabe em que sistema roda. Quem agenda jobs,
notifica, abre o navegador ou segura o sono pergunta aqui::

    atual()                     macOS (darwin), Windows (win32) ou Linux; GP_PLATAFORMA=macos|linux|windows força (testes)
      .notificar(texto)         osascript "display notification" | notify-send | toast pelo PowerShell
      .agendador                launchd: plists em ~/Library/LaunchAgents + launchctl bootstrap/bootout
                                systemd --user: .service + .timer em ~/.config/systemd/user + systemctl --user
                                Windows: tarefas XML em \\GoalPacer\\ (schtasks /Create /XML) e o painel por um atalho na
                                pasta Inicializar; os dois chamam scripts/lancador.py pelo pythonw.exe
        .gerar(valores, modo_painel) -> {label: arquivo renderizado em jobs/}
        .carregar(arquivos) -> labels que não carregaram
        .descarregar(labels) -> labels removidos
        .carregados() -> (labels ativos, aviso ou None)
      .abrir_url(url)           open | xdg-open | os.startfile (também abre o app ou o atalho da janela)
      .manter_acordado(pid)     caffeinate -i -w <pid> | systemd-inhibit até o processo acabar | nada no Windows
      .pastas_protegidas        Desktop, Downloads e Documents no macOS (TCC); nenhuma no Linux e no Windows
      .precisa_xcode            o /usr/bin/python3 da Apple só funciona com as Command Line Tools
      .janela_nativa            janela própria do painel: Goal Pacer.app compilado (macOS) ou atalho do menu Iniciar
                                que abre o Edge em modo app (Windows); no Linux, o navegador

Ligações de pasta (a skill e ``dados/`` fora da raiz): symlink no macOS e no Linux, junção no Windows, que não pede
administrador nem modo de desenvolvedor (``ligar_pasta``, ``eh_ligacao``, ``desligar``).

Jobs lógicos: ``diario`` (seg a sáb 07:00), ``mensal`` (dia 1, 05:30) e o opcional
``painel`` (web.py sempre no ar: ``--local`` por padrão, ``--rede`` para o celular no Wi-Fi de casa). Os arquivos nascem de templates em ``jobs/``
com os caminhos absolutos escapados para o formato (XML no plist; aspas e ``%%`` no
systemd) e são conferidos depois de renderizados: argumento ou variável fora do
esperado recusa a instalação em vez de carregar um job torto.

Variáveis para teste: ``GP_PLATAFORMA``, ``GP_LAUNCHCTL``, ``GP_OSASCRIPT``, ``GP_SYSTEMCTL``,
``GP_NOTIFY_SEND``, ``GP_LOGINCTL``, ``HOME``, ``XDG_CONFIG_HOME``.
"""

from __future__ import annotations

import importlib
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

from goalpacer import atalhos, base, processos
from goalpacer.base import EXIT_VALIDACAO, GpErro

JOBS = ("diario", "mensal")
# Binários trocáveis por variável (testes e máquinas com caminhos fora do padrão)
ENV_PLATAFORMA = "GP_PLATAFORMA"  # macos | linux | windows: força o backend (a suíte fixa macos)
ENV_LAUNCHCTL = "GP_LAUNCHCTL"
ENV_SYSTEMCTL = "GP_SYSTEMCTL"
ENV_LOGINCTL = "GP_LOGINCTL"
ENV_OSASCRIPT = "GP_OSASCRIPT"
ENV_NOTIFY_SEND = "GP_NOTIFY_SEND"
ENV_XCODE_SELECT = "GP_XCODE_SELECT"
PAINEL = "painel"
PASTAS_TCC = ("Desktop", "Downloads", "Documents")
PLATAFORMAS = ("macos", "linux", "windows")
TENTATIVAS_BOOTSTRAP = 10
ESPERA_BOOTSTRAP_S = 1.0
NOME_PID_PAINEL = "painel.pid"  # no Windows: {"lancador": pid, "painel": pid}, gravado por scripts/lancador.py


def nome_atual() -> str:
    forcado = (os.environ.get(ENV_PLATAFORMA) or "").strip().lower()
    if forcado in PLATAFORMAS:
        return forcado
    if sys.platform == "darwin":
        return "macos"
    return "windows" if sys.platform == "win32" else "linux"


def _rodar(argv: list[str], timeout_s: float = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # schtasks e outros do Windows respondem na página de código do console
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return -1, str(erro)
    return r.returncode, "\n".join(p for p in ((r.stdout or "").strip(), (r.stderr or "").strip()) if p)


def _binario(variavel: str, padrao: str) -> str:
    return os.environ.get(variavel) or shutil.which(os.path.basename(padrao)) or padrao


MODOS_PAINEL = ("local", "rede")  # "" = sem o agente do painel


def _com_modo_painel(valores: dict[str, str], modo_painel: str) -> dict[str, str]:
    if modo_painel and modo_painel not in MODOS_PAINEL:
        raise GpErro(EXIT_VALIDACAO, "modo do painel %r: use local ou rede" % modo_painel)
    return dict(valores, MODO_PAINEL="--" + (modo_painel or "local"))


def _argumentos_esperados(job: str, valores: dict[str, str]) -> list[str]:
    if job == PAINEL:
        return [valores["PYTHON3"], valores["APP"] + "/scripts/web.py", valores["MODO_PAINEL"]]
    return [valores["PYTHON3"], valores["APP"] + "/jobs/run_job.py", job]


# --- launchd (macOS) ---------------------------------------------------------------------


class Launchd:
    nome = "launchd"

    def label(self, job: str) -> str:
        return "com.goal-pacer.%s" % job

    def pasta(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents"

    def _launchctl(self) -> str:
        return os.environ.get(ENV_LAUNCHCTL) or "/bin/launchctl"

    def gerar(self, app: Path, jobs_dir: Path, valores: dict[str, str], modo_painel: str) -> dict[str, list[Path]]:
        gerados: dict[str, list[Path]] = {}
        valores = _com_modo_painel(valores, modo_painel)
        for job in JOBS + ((PAINEL,) if modo_painel else ()):
            label = self.label(job)
            template = (app / "jobs" / ("%s.plist.tmpl" % label)).read_text(encoding="utf-8")
            texto = _substituir(template, {k: escape(v) for k, v in valores.items()})
            conteudo = plistlib.loads(texto.encode("utf-8"))
            if (
                conteudo.get("Label") != label
                or conteudo.get("ProgramArguments") != _argumentos_esperados(job, valores)
                or conteudo["EnvironmentVariables"].get(base.ENV_DATA_DIR) != valores["DADOS"]
            ):
                raise GpErro(EXIT_VALIDACAO, "plist %s renderizado não confere com os caminhos" % label)
            path = jobs_dir / ("%s.plist" % label)
            path.write_text(texto, encoding="utf-8")
            gerados[label] = [path]
        return gerados

    def carregar(self, arquivos: dict[str, list[Path]]) -> list[str]:
        destino = self.pasta()
        destino.mkdir(parents=True, exist_ok=True)
        dominio = "gui/%d" % os.getuid()
        falhas = []
        for label, paths in arquivos.items():
            alvo = destino / paths[0].name
            _rodar([self._launchctl(), "bootout", "%s/%s" % (dominio, label)])
            shutil.copyfile(str(paths[0]), str(alvo))
            if self._bootstrap(dominio, alvo) != 0:
                falhas.append(label)
        return falhas

    def _bootstrap(self, dominio: str, alvo: Path) -> int:
        """O ``bootout`` de um agente vivo (o painel) volta antes de o serviço sair: o ``bootstrap`` logo depois
        falha com 5 (Input/output error) por alguns segundos, e o ``load -w`` nessa hora devolve 0 sem carregar
        nada. Tenta outra vez a cada segundo antes de recorrer ao ``load``."""
        for tentativa in range(TENTATIVAS_BOOTSTRAP):
            codigo, _ = _rodar([self._launchctl(), "bootstrap", dominio, str(alvo)])
            if codigo == 0:
                return 0
            if tentativa + 1 < TENTATIVAS_BOOTSTRAP:
                time.sleep(ESPERA_BOOTSTRAP_S)
        return _rodar([self._launchctl(), "load", "-w", str(alvo)])[0]

    def descarregar(self, labels: list[str], jobs_dir: Path) -> list[str]:
        dominio = "gui/%d" % os.getuid()
        removidos = []
        for label in labels:
            _rodar([self._launchctl(), "bootout", "%s/%s" % (dominio, label)])
            for path in (self.pasta() / ("%s.plist" % label), jobs_dir / ("%s.plist" % label)):
                if path.exists() or path.is_symlink():
                    path.unlink()
                    if path.parent == self.pasta():
                        removidos.append(label)
        return removidos

    def comando_agora(self, job: str) -> str:
        return "launchctl kickstart gui/$(id -u)/%s" % self.label(job)

    def iniciar(self, job: str) -> Optional[str]:
        """Roda o job agora, fora do horário; None = o launchd aceitou, senão a mensagem dele."""
        codigo, saida = _rodar([self._launchctl(), "kickstart", "gui/%d/%s" % (os.getuid(), self.label(job))])
        return None if codigo == 0 else (saida or "launchctl kickstart exit %d" % codigo)[:200]

    def instalados(self, jobs: tuple) -> list[Path]:
        """Arquivos que o launchd lê (para conferir quem pode alterá-los)."""
        return [self.pasta() / ("%s.plist" % self.label(job)) for job in jobs]

    def carregados(self) -> tuple[Optional[set[str]], Optional[str]]:
        codigo, saida = _rodar([self._launchctl(), "list"])
        if codigo != 0:
            return None, (saida.strip().split("\n") or ["?"])[0][:60]
        return {linha.split()[-1] for linha in saida.split("\n") if linha.strip()}, None


# --- systemd --user (Linux) ----------------------------------------------------------------


def _conferir_servico(unidade: str, texto: str, job: str, valores: dict[str, str], escapados: dict[str, str]) -> None:
    """O ``ExecStart`` e o ``GP_DATA_DIR`` renderizados precisam ser exatamente os caminhos da instalação."""
    exec_start = next((linha for linha in texto.split("\n") if linha.startswith("ExecStart=")), "")
    esperado = "ExecStart=" + " ".join(
        '"%s"' % a.replace("%", "%%") if " " in a or a.startswith("/") else a
        for a in _argumentos_esperados(job, valores)
    )
    ambiente = 'Environment="GP_DATA_DIR=%s"' % escapados["DADOS"]
    if exec_start != esperado or ambiente not in texto:
        raise GpErro(EXIT_VALIDACAO, "unidade %s renderizada não confere com os caminhos" % unidade)


class Systemd:
    nome = "systemd"

    def label(self, job: str) -> str:
        return "goal-pacer-%s" % job

    def pasta(self) -> Path:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(base) / "systemd" / "user"

    def _systemctl(self) -> list[str]:
        return [_binario(ENV_SYSTEMCTL, "/usr/bin/systemctl"), "--user"]

    def unidades(self, job: str) -> tuple[str, ...]:
        label = self.label(job)
        return ("%s.service" % label,) if job == PAINEL else ("%s.service" % label, "%s.timer" % label)

    def ativavel(self, job: str) -> str:
        return self.unidades(job)[-1]

    def instalados(self, jobs: tuple) -> list[Path]:
        """Unidades que o systemd --user lê (para conferir quem pode alterá-las)."""
        return [self.pasta() / unidade for job in jobs for unidade in self.unidades(job)]

    def gerar(self, app: Path, jobs_dir: Path, valores: dict[str, str], modo_painel: str) -> dict[str, list[Path]]:
        gerados: dict[str, list[Path]] = {}
        valores = _com_modo_painel(valores, modo_painel)
        escapados = {k: v.replace("%", "%%") for k, v in valores.items()}
        for job in JOBS + ((PAINEL,) if modo_painel else ()):
            paths = []
            for unidade in self.unidades(job):
                template = (app / "jobs" / "systemd" / ("%s.tmpl" % unidade)).read_text(encoding="utf-8")
                texto = _substituir(template, escapados)
                if unidade.endswith(".service"):
                    _conferir_servico(unidade, texto, job, valores, escapados)
                path = jobs_dir / unidade
                path.write_text(texto, encoding="utf-8")
                paths.append(path)
            gerados[self.label(job)] = paths
        return gerados

    def carregar(self, arquivos: dict[str, list[Path]]) -> list[str]:
        destino = self.pasta()
        destino.mkdir(parents=True, exist_ok=True)
        for paths in arquivos.values():
            for path in paths:
                shutil.copyfile(str(path), str(destino / path.name))
        _rodar([*self._systemctl(), "daemon-reload"])
        falhas = []
        for label, paths in arquivos.items():
            ativavel = paths[-1].name
            codigo, _ = _rodar([*self._systemctl(), "enable", "--now", ativavel])
            if codigo != 0:
                falhas.append(label)
        return falhas

    def descarregar(self, labels: list[str], jobs_dir: Path) -> list[str]:
        removidos = []
        for label in labels:
            job = label[len("goal-pacer-") :]
            unidades = self.unidades(job)
            _rodar([*self._systemctl(), "disable", "--now", unidades[-1]])
            achou = False
            for unidade in unidades:
                for path in (self.pasta() / unidade, jobs_dir / unidade):
                    if path.exists() or path.is_symlink():
                        path.unlink()
                        achou = achou or path.parent == self.pasta()
            if achou:
                removidos.append(label)
        if removidos:
            _rodar([*self._systemctl(), "daemon-reload"])
        return removidos

    def comando_agora(self, job: str) -> str:
        return "systemctl --user start %s.service" % self.label(job)

    def iniciar(self, job: str) -> Optional[str]:
        """Roda o job agora, fora do horário; None = o systemd aceitou, senão a mensagem dele."""
        codigo, saida = _rodar([*self._systemctl(), "start", "--no-block", "%s.service" % self.label(job)])
        return None if codigo == 0 else (saida or "systemctl start exit %d" % codigo)[:200]

    def carregados(self) -> tuple[Optional[set[str]], Optional[str]]:
        ativos = set()
        for job in (*JOBS, PAINEL):
            codigo, saida = _rodar([*self._systemctl(), "is-enabled", self.ativavel(job)])
            if codigo == -1:
                return None, saida[:60]
            if codigo == 0 and saida.strip().split("\n")[-1].strip() in ("enabled", "enabled-runtime", "static"):
                ativos.add(self.label(job))
        return ativos, None

    def linger(self) -> Optional[bool]:
        """Sem linger, os timers do usuário só rodam com sessão aberta (como o launchd com a sessão do Mac)."""
        usuario = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        codigo, saida = _rodar([_binario(ENV_LOGINCTL, "/usr/bin/loginctl"), "show-user", usuario, "--property=Linger"])
        if codigo != 0:
            return None
        return saida.strip().endswith("yes")


# --- Agendador de Tarefas (Windows) ---------------------------------------------------------


def _comando_da_tarefa(texto: str) -> tuple[str, str, str]:
    """``(Command, Arguments, WorkingDirectory)`` da ação de uma tarefa renderizada (XML do Agendador de Tarefas)."""
    ns = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"
    try:
        raiz = ET.fromstring(texto.encode("utf-16"))  # noqa: S314 - XML que o próprio instalador renderizou
    except ET.ParseError as erro:
        raise GpErro(EXIT_VALIDACAO, "tarefa renderizada não é XML válido: %s" % erro) from erro
    execucao = raiz.find("%sActions/%sExec" % (ns, ns))
    if execucao is None:
        return "", "", ""
    comando, argumentos, pasta = (
        (execucao.findtext(ns + campo) or "") for campo in ("Command", "Arguments", "WorkingDirectory")
    )
    return comando, argumentos, pasta


def parar_painel(jobs_dir: Path) -> None:
    """Encerra o lançador e o web.py de ``jobs/painel.pid`` (só esses dois pids: um update que o painel disparou
    segue vivo) e apaga o arquivo."""
    marca = jobs_dir / NOME_PID_PAINEL
    try:
        pids = json.loads(marca.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pids = {}
    for chave in ("lancador", "painel"):  # o lançador primeiro, para não subir o painel outra vez
        pid = pids.get(chave) if isinstance(pids, dict) else None
        if isinstance(pid, int) and processos.vivo(pid):
            processos.encerrar(pid)
    if marca.exists():
        marca.unlink()


def subir_painel(especificacao: dict[str, Any]) -> None:
    """Sobe o lançador do painel fora deste processo (o instalador acaba; o painel fica)."""
    subprocess.Popen(
        [especificacao["alvo"], *especificacao["argumentos"]],
        cwd=especificacao["pasta"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **processos.desligado(),
    )


class TarefasWindows:
    nome = "Agendador de Tarefas"
    prefixo = "GoalPacer\\"

    def label(self, job: str) -> str:
        return self.prefixo + job

    def pasta(self) -> Path:
        """Onde fica o atalho que sobe o painel a cada login."""
        return atalhos.pasta_inicializar()

    def _schtasks(self) -> str:
        return shutil.which("schtasks") or r"C:\Windows\System32\schtasks.exe"

    def _valores(self, valores: dict[str, str], modo_painel: str) -> dict[str, str]:
        valores = _com_modo_painel(valores, modo_painel)
        return dict(
            valores,
            PYTHONW=atalhos.pythonw(valores["PYTHON3"]),
            LANCADOR=str(Path(valores["APP"]) / "scripts" / "lancador.py"),
        )

    def gerar(self, app: Path, jobs_dir: Path, valores: dict[str, str], modo_painel: str) -> dict[str, list[Path]]:
        valores = self._valores(valores, modo_painel)
        gerados: dict[str, list[Path]] = {}
        for job in JOBS:
            template = (app / "jobs" / "windows" / ("goal-pacer-%s.xml.tmpl" % job)).read_text(encoding="utf-8")
            texto = _substituir(template, {k: escape(v) for k, v in valores.items()})
            esperado = (valores["PYTHONW"], '"%s" job %s' % (valores["LANCADOR"], job), valores["JOBS"])
            if _comando_da_tarefa(texto) != esperado:
                raise GpErro(EXIT_VALIDACAO, "tarefa %s renderizada não confere com os caminhos" % self.label(job))
            path = jobs_dir / ("goal-pacer-%s.xml" % job)
            path.write_text(texto, encoding="utf-16")  # o schtasks /XML lê UTF-16 (com BOM)
            gerados[self.label(job)] = [path]
        if modo_painel:
            path = jobs_dir / "goal-pacer-painel.json"
            especificacao = {
                "alvo": valores["PYTHONW"],
                "argumentos": [valores["LANCADOR"], PAINEL, valores["MODO_PAINEL"]],
                "pasta": valores["JOBS"],
            }
            path.write_text(json.dumps(especificacao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            gerados[self.label(PAINEL)] = [path]
        return gerados

    def carregar(self, arquivos: dict[str, list[Path]]) -> list[str]:
        falhas = []
        for label, paths in arquivos.items():
            if label == self.label(PAINEL):
                if not self._ligar_painel(paths[0]):
                    falhas.append(label)
                continue
            codigo, _ = _rodar([self._schtasks(), "/Create", "/TN", label, "/XML", str(paths[0]), "/F"])
            if codigo != 0:
                falhas.append(label)
        return falhas

    def _ligar_painel(self, arquivo: Path) -> bool:
        especificacao = json.loads(arquivo.read_text(encoding="utf-8"))
        try:
            atalhos.criar(
                self.pasta() / atalhos.NOME_PAINEL,
                especificacao["alvo"],
                especificacao["argumentos"],
                especificacao["pasta"],
            )
        except GpErro:
            return False
        parar_painel(Path(especificacao["pasta"]))
        subir_painel(especificacao)
        return True

    def descarregar(self, labels: list[str], jobs_dir: Path) -> list[str]:
        removidos = []
        for label in labels:
            job = label[len(self.prefixo) :]
            if job == PAINEL:
                achou = atalhos.remover(self.pasta() / atalhos.NOME_PAINEL)
                parar_painel(jobs_dir)
                arquivo = jobs_dir / "goal-pacer-painel.json"
            else:
                achou = _rodar([self._schtasks(), "/Delete", "/TN", label, "/F"])[0] == 0
                arquivo = jobs_dir / ("goal-pacer-%s.xml" % job)
            if arquivo.exists():
                arquivo.unlink()
            if achou:
                removidos.append(label)
        return removidos

    def comando_agora(self, job: str) -> str:
        return "schtasks /Run /TN %s" % self.label(job)

    def iniciar(self, job: str) -> Optional[str]:
        """Roda o job agora, fora do horário; None = o Agendador aceitou, senão a mensagem dele."""
        codigo, saida = _rodar([self._schtasks(), "/Run", "/TN", self.label(job)])
        return None if codigo == 0 else (saida or "schtasks /Run exit %d" % codigo)[:200]

    def instalados(self, jobs: tuple) -> list[Path]:  # noqa: ARG002 - mesma assinatura dos outros agendadores
        """No Windows as tarefas moram no registro do Agendador, protegidas por ele (nenhum arquivo para conferir)."""
        return []

    def carregados(self) -> tuple[Optional[set[str]], Optional[str]]:
        ativos = set()
        for job in JOBS:
            codigo, saida = _rodar([self._schtasks(), "/Query", "/TN", self.label(job)])
            if codigo == -1:
                return None, saida[:60]
            if codigo == 0:
                ativos.add(self.label(job))
        if (self.pasta() / atalhos.NOME_PAINEL).is_file():
            ativos.add(self.label(PAINEL))
        return ativos, None


# --- plataformas -------------------------------------------------------------------------


class MacOS:
    nome = "macos"
    pastas_protegidas = PASTAS_TCC
    precisa_xcode = True
    janela_nativa = True  # o Goal Pacer.app (goalpacer/janela.py)

    def __init__(self) -> None:
        self.agendador = Launchd()

    def notificar(self, texto: str) -> Optional[str]:
        binario = os.environ.get(ENV_OSASCRIPT) or "/usr/bin/osascript"
        if not Path(binario).exists():
            return "sem osascript"
        seguro = texto.replace("\\", "\\\\").replace('"', '\\"')
        codigo, saida = _rodar(
            [binario, "-e", 'display notification "%s" with title "Goal Pacer"' % seguro], timeout_s=15
        )
        return None if codigo == 0 else (saida or "osascript exit %d" % codigo)

    def abrir_url(self, url: str) -> None:
        _rodar(["/usr/bin/open", url], timeout_s=15)

    def manter_acordado(self, pid: int) -> Optional[subprocess.Popen]:
        if not Path("/usr/bin/caffeinate").exists():
            return None
        return subprocess.Popen(
            ["/usr/bin/caffeinate", "-i", "-w", str(pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class Linux:
    nome = "linux"
    pastas_protegidas: tuple = ()
    precisa_xcode = False
    janela_nativa = False  # no Linux o painel abre pelo navegador (e instala como app por ele)

    def __init__(self) -> None:
        self.agendador = Systemd()

    def notificar(self, texto: str) -> Optional[str]:
        binario = os.environ.get(ENV_NOTIFY_SEND) or shutil.which("notify-send")
        if not binario:
            return "sem notify-send"
        codigo, saida = _rodar([binario, "--app-name=Goal Pacer", "Goal Pacer", texto], timeout_s=15)
        return None if codigo == 0 else (saida or "notify-send exit %d" % codigo)

    def abrir_url(self, url: str) -> None:
        binario = shutil.which("xdg-open")
        if binario:
            _rodar([binario, url], timeout_s=15)

    def manter_acordado(self, pid: int) -> Optional[subprocess.Popen]:
        binario = shutil.which("systemd-inhibit")
        if not binario:
            return None
        espera = "while kill -0 %d 2>/dev/null; do sleep 30; done" % pid
        return subprocess.Popen(
            [binario, "--what=sleep", "--who=Goal Pacer", "--why=painel no ar", "/bin/sh", "-c", espera],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


TOAST = """[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $xml.GetElementsByTagName('text')
$textos.Item(0).AppendChild($xml.CreateTextNode('Goal Pacer')) > $null
$textos.Item(1).AppendChild($xml.CreateTextNode(%s)) > $null
$aviso = [Windows.UI.Notifications.ToastNotification]::new($xml)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($aviso)"""


class Windows:
    nome = "windows"
    pastas_protegidas: tuple = ()
    precisa_xcode = False
    janela_nativa = True  # atalho "Goal Pacer" no menu Iniciar: o painel no Edge (ou Chrome) em modo app

    def __init__(self) -> None:
        self.agendador = TarefasWindows()

    def notificar(self, texto: str) -> Optional[str]:
        codigo, saida = atalhos.rodar_powershell(TOAST % atalhos.literal(texto), timeout_s=30)
        return None if codigo == 0 else (saida or "powershell exit %d" % codigo)[:200]

    def abrir_url(self, url: str) -> None:
        abrir = getattr(os, "startfile", None)
        if abrir is not None:
            try:
                abrir(url)
            except OSError:
                return

    def manter_acordado(self, pid: int) -> Optional[subprocess.Popen]:  # noqa: ARG002 - mesma assinatura
        return None  # sem equivalente sem administrador; o painel na rede segue enquanto o computador está acordado


def atual() -> Any:
    nome = nome_atual()
    if nome == "macos":
        return MacOS()
    return Windows() if nome == "windows" else Linux()


def _substituir(template: str, valores: dict[str, str]) -> str:
    texto = template
    for chave, valor in valores.items():
        texto = texto.replace("{{%s}}" % chave, valor)
    if "{{" in texto:
        inicio = texto.index("{{")
        raise GpErro(EXIT_VALIDACAO, "template com variável sem valor: %s" % texto[inicio : inicio + 20])
    return texto


def dir_tcc_proibido(path: Path) -> bool:
    """True se ``path`` (símlinks resolvidos) está em Desktop, Downloads ou
    Documents do HOME atual, ou é uma dessas pastas. Só no macOS (TCC); no Linux
    nenhuma pasta do HOME é bloqueada para o agendador."""
    if not atual().pastas_protegidas:
        return False
    alvo = Path(path).expanduser().resolve()
    home = Path.home()
    for nome in PASTAS_TCC:
        pasta = (home / nome).resolve()
        if alvo == pasta or pasta in alvo.parents:
            return True
    return False


# --- ligações de pasta -----------------------------------------------------------------------

REPARSE_JUNCAO = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def ligar_pasta(link: Path, alvo: Path) -> None:
    """``link`` passa a apontar para a pasta ``alvo``: symlink no macOS e no Linux, junção no Windows."""
    if not processos.WINDOWS:
        link.symlink_to(alvo, target_is_directory=True)
        return
    winapi = importlib.import_module("_winapi")  # pragma: no cover - só no Windows
    winapi.CreateJunction(str(alvo), str(link))  # pragma: no cover


def eh_ligacao(link: Path) -> bool:
    if link.is_symlink():
        return True
    if not processos.WINDOWS:
        return False
    try:  # pragma: no cover - só no Windows
        return getattr(os.lstat(str(link)), "st_reparse_tag", 0) == REPARSE_JUNCAO
    except OSError:  # pragma: no cover
        return False


def desligar(link: Path) -> None:
    """Remove a ligação, nunca o conteúdo da pasta para onde ela aponta."""
    if processos.WINDOWS and not link.is_symlink():
        os.rmdir(str(link))  # pragma: no cover - junção: rmdir tira só a ligação
    else:
        link.unlink()
