#!/usr/bin/env python3
"""lancador.py: porta de entrada do Windows para os jobs, o painel e a janela (roda pelo pythonw.exe, sem console).

O Agendador de Tarefas e os atalhos .lnk não passam variáveis de ambiente. O lançador lê ``jobs/instalacao.json`` da
raiz onde está instalado, monta o mesmo ambiente que o plist e a unidade systemd gravam e roda o alvo com o
``python.exe`` ao lado, num console escondido, com a saída num log::

    lancador.py job diario|mensal       jobs/run_job.py <job>                       log jobs/logs/tarefa-<job>.log
    lancador.py painel --local|--rede   scripts/web.py <modo>; se cair com erro, sobe outra vez em 30 s (como o
                                        KeepAlive do launchd); pids do lançador e do painel em jobs/painel.pid
    lancador.py janela                  painel no ar (sobe o lançador do painel se ninguém responde) e a janela em modo
                                        app: o navegador padrão quando é Chrome, Edge ou Brave; senão, o Edge

Os netos (claude, git, python) herdam o console escondido: nenhuma janela preta pisca na tela.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, plataforma, processos, proxy

ENDERECO = "http://127.0.0.1:8765/"
ENDERECO_JANELA = ENDERECO + "?janela=1"  # o painel sabe que está na janela e não oferece instalar o app
TETO_JOB_S = 3 * 3600  # o run_job tem os próprios tetos (20 ou 40 min); este só impede um lançador pendurado
ESPERA_PAINEL_CAIU_S = 30
ESPERA_PAINEL_SUBIR_S = 30
ARGUMENTOS_APP = ("--no-first-run", "--no-default-browser-check")
# ProgId do navegador padrão (registro do Windows) -> executáveis que abrem em modo app, na ordem de preferência
NAVEGADORES_POR_PADRAO = {
    "ChromeHTML": ("chrome.exe", "msedge.exe"),
    "BraveHTML": ("brave.exe", "msedge.exe"),
    "MSEdgeHTM": ("msedge.exe", "chrome.exe"),
}
NAVEGADORES_SEM_PADRAO = ("msedge.exe", "chrome.exe")
PASTAS_DE_NAVEGADOR = {
    "msedge.exe": (("ProgramFiles(x86)", "Microsoft", "Edge"), ("ProgramFiles", "Microsoft", "Edge")),
    "chrome.exe": (
        ("ProgramFiles", "Google", "Chrome"),
        ("ProgramFiles(x86)", "Google", "Chrome"),
        ("LOCALAPPDATA", "Google", "Chrome"),
    ),
    "brave.exe": (
        ("ProgramFiles", "BraveSoftware", "Brave-Browser"),
        ("LOCALAPPDATA", "BraveSoftware", "Brave-Browser"),
    ),
}


def raiz_da_instalacao(arquivo: Path = Path(__file__)) -> Path:
    """A raiz de ``app/scripts/lancador.py`` quando ela tem ``jobs/instalacao.json``; senão a raiz padrão."""
    candidata = arquivo.resolve().parents[2]
    if (candidata / base.NOME_JOBS / base.NOME_INSTALACAO).is_file():
        return candidata
    return base.raiz()


def ler_instalacao(raiz: Path) -> dict[str, Any]:
    try:
        dados = json.loads((raiz / base.NOME_JOBS / base.NOME_INSTALACAO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def ambiente(raiz: Path, instalacao: dict[str, Any], herdado: dict[str, str]) -> dict[str, str]:
    """O ambiente dos arquivos do agendador (raiz, dados e claude da instalação) em cima do ambiente do Windows."""
    env = dict(herdado)
    env[base.ENV_RAIZ] = str(instalacao.get("raiz") or raiz)
    env[base.ENV_DATA_DIR] = str(instalacao.get("dados") or raiz / base.NOME_DADOS)
    if instalacao.get("claude"):
        env[proxy.ENV_CLAUDE_BIN] = str(instalacao["claude"])
    env["PYTHONUTF8"] = "1"  # saída dos subprocessos e arquivos em UTF-8, qualquer que seja a página de código
    return env


def python_com_console(executavel: str) -> str:
    """``python.exe`` ao lado do ``pythonw.exe``: o filho precisa de stdout (o pythonw roda sem nenhum)."""
    fim = "pythonw.exe"
    return executavel[: -len(fim)] + "python.exe" if PureWindowsPath(executavel).name.lower() == fim else executavel


def _escondido() -> dict[str, Any]:
    return {"creationflags": processos.SEM_JANELA} if processos.WINDOWS else {}


def rodar_job(raiz: Path, instalacao: dict[str, Any], job: str) -> int:
    app = Path(instalacao.get("app") or raiz / base.NOME_APP)
    jobs = raiz / base.NOME_JOBS
    (jobs / "logs").mkdir(parents=True, exist_ok=True)
    argv = [python_com_console(sys.executable), str(app / "jobs" / "run_job.py"), job]
    with open(jobs / "logs" / ("tarefa-%s.log" % job), "a", encoding="utf-8") as log:
        try:
            return subprocess.run(
                argv,
                cwd=str(jobs),
                env=ambiente(raiz, instalacao, dict(os.environ)),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=TETO_JOB_S,
                check=False,
                **_escondido(),
            ).returncode
        except subprocess.TimeoutExpired:
            return base.EXIT_TIMEOUT


def servir_painel(
    raiz: Path, instalacao: dict[str, Any], modo: str, *, esperar: Callable[[float], None] = time.sleep
) -> int:
    """``web.py <modo>`` enquanto ele sair com erro (porta ocupada, update no meio); saída 0 = encerrado de propósito."""
    app = Path(instalacao.get("app") or raiz / base.NOME_APP)
    jobs = raiz / base.NOME_JOBS
    (jobs / "logs").mkdir(parents=True, exist_ok=True)
    marca = jobs / plataforma.NOME_PID_PAINEL
    while True:
        with open(jobs / "logs" / "tarefa-painel.log", "a", encoding="utf-8") as log:
            processo = subprocess.Popen(
                [python_com_console(sys.executable), str(app / "scripts" / "web.py"), modo],
                cwd=str(jobs),
                env=ambiente(raiz, ler_instalacao(raiz) or instalacao, dict(os.environ)),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                **_escondido(),
            )
            marca.write_text(json.dumps({"lancador": os.getpid(), "painel": processo.pid}) + "\n", encoding="utf-8")
            codigo = processo.wait()
        if codigo == 0:
            return 0
        esperar(ESPERA_PAINEL_CAIU_S)


def painel_responde(endereco: str = ENDERECO, timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(endereco, timeout=timeout_s):  # noqa: S310 - endereço fixo do painel local
            return True
    except urllib.error.HTTPError:
        return True  # respondeu, mesmo que com erro: o painel está no ar
    except (OSError, ValueError):
        return False


def especificacao_do_painel(raiz: Path) -> dict[str, Any]:
    """O lançador do painel que o instalador gravou (``jobs/goal-pacer-painel.json``); sem ele, o painel local."""
    jobs = raiz / base.NOME_JOBS
    try:
        dados = json.loads((jobs / "goal-pacer-painel.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = None
    if isinstance(dados, dict) and dados.get("alvo") and dados.get("argumentos"):
        return dados
    return {
        "alvo": sys.executable,
        "argumentos": [str(Path(__file__).resolve()), "painel", "--local"],
        "pasta": str(jobs),
    }


def garantir_painel(
    raiz: Path,
    *,
    responde: Callable[[], bool] = painel_responde,
    subir: Callable[[dict[str, Any]], None] = plataforma.subir_painel,
    esperar: Callable[[float], None] = time.sleep,
) -> bool:
    """True quando o painel responde, subindo o lançador dele se ninguém respondia (até 30 s)."""
    if responde():
        return True
    subir(especificacao_do_painel(raiz))
    for _ in range(ESPERA_PAINEL_SUBIR_S * 2):
        esperar(0.5)
        if responde():
            return True
    return False


def _registro(chave_raiz: str, caminho: str, valor: str) -> Optional[str]:  # pragma: no cover - só no Windows
    try:
        winreg = importlib.import_module("winreg")
        abrir, consultar = getattr(winreg, "OpenKey"), getattr(winreg, "QueryValueEx")  # noqa: B009 - só no Windows
        with abrir(getattr(winreg, chave_raiz), caminho) as chave:
            lido = consultar(chave, valor)[0]
    except (OSError, ImportError):
        return None
    return str(lido) if lido else None


def navegador_padrao() -> Optional[str]:  # pragma: no cover - só no Windows
    caminho = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
    return _registro("HKEY_CURRENT_USER", caminho, "ProgId")


def achar_executavel(nome: str, ambiente_do_windows: Optional[dict[str, str]] = None) -> Optional[str]:
    """O navegador pelo App Paths do registro; senão, nas pastas de instalação conhecidas."""
    env = os.environ if ambiente_do_windows is None else ambiente_do_windows
    caminho_app = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % nome
    for raiz in ("HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"):
        registrado = _registro(raiz, caminho_app, "") if processos.WINDOWS else None
        if registrado and os.path.isfile(registrado.strip('"')):
            return registrado.strip('"')
    for variavel, *partes in PASTAS_DE_NAVEGADOR.get(nome, ()):
        if env.get(variavel):
            candidato = os.path.join(env[variavel], *partes, "Application", nome)
            if os.path.isfile(candidato):
                return candidato
    return None


def escolher_navegador(progid: Optional[str], achar: Callable[[str], Optional[str]]) -> Optional[str]:
    for nome in NAVEGADORES_POR_PADRAO.get(progid or "", NAVEGADORES_SEM_PADRAO):
        caminho = achar(nome)
        if caminho:
            return caminho
    return None


def comando_da_janela(navegador: str, endereco: str = ENDERECO_JANELA) -> list[str]:
    return [navegador, "--app=" + endereco, *ARGUMENTOS_APP]


def abrir_no_navegador(navegador: Optional[str]) -> None:
    if navegador is None:
        plataforma.atual().abrir_url(ENDERECO)
        return
    subprocess.Popen(
        comando_da_janela(navegador),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **processos.desligado(),
    )


def abrir_janela(raiz: Path) -> int:  # pragma: no cover - só no Windows (tests/e2e/windows.py)
    garantir_painel(raiz)
    abrir_no_navegador(escolher_navegador(navegador_padrao(), achar_executavel))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="jobs, painel e janela do Goal Pacer no Windows (pythonw.exe)")
    alvos = parser.add_subparsers(dest="alvo", required=True)
    job = alvos.add_parser("job")
    job.add_argument("nome", choices=plataforma.JOBS)
    painel = alvos.add_parser("painel").add_mutually_exclusive_group()
    painel.add_argument("--local", action="store_true")
    painel.add_argument("--rede", action="store_true")
    alvos.add_parser("janela")
    args = parser.parse_args(argv)
    raiz = raiz_da_instalacao()
    instalacao = ler_instalacao(raiz)
    if args.alvo == "job":
        return rodar_job(raiz, instalacao, args.nome)
    if args.alvo == "painel":
        return servir_painel(raiz, instalacao, "--rede" if args.rede else "--local")
    return abrir_janela(raiz)


if __name__ == "__main__":
    raise SystemExit(main())
