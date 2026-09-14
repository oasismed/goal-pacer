"""atalhos.py: atalhos do Windows (.lnk) e o ícone .ico, só com o PowerShell que vem com o sistema.

No Windows não há plist nem unidade systemd para o painel e a janela: quem abre no login é um atalho na pasta
Inicializar, e quem abre a janela é um atalho no menu Iniciar. Os dois apontam para o ``pythonw.exe`` (sem console)
com ``scripts/lancador.py``::

    criar(atalho, alvo, argumentos, pasta, icone)   WScript.Shell pelo PowerShell (-EncodedCommand, sem aspas soltas)
    pasta_inicializar() / pasta_menu_iniciar()      %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs[\\Startup]
    ico(pngs)                                       ícone com PNGs por tamanho (16 a 256), o formato do Windows Vista em diante
    pythonw(python)                                 o pythonw.exe ao lado do python.exe escolhido na instalação

Caminhos passam por ``instalar.validar_caminho`` antes (sem aspas, $, % nem quebra de linha); aqui ainda viram literal
do PowerShell com a aspa simples dobrada.
"""

from __future__ import annotations

import base64
import os
import shutil
import struct
import subprocess
from pathlib import Path, PureWindowsPath
from typing import Callable, Optional

from goalpacer.base import EXIT_IO, GpErro

NOME_JANELA = "Goal Pacer.lnk"
NOME_PAINEL = "Goal Pacer (painel).lnk"
NOME_ICONE = "goal-pacer.ico"
TIMEOUT_POWERSHELL_S = 60
POWERSHELL_PADRAO = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def powershell() -> str:
    return shutil.which("powershell") or POWERSHELL_PADRAO


def rodar_powershell(script: str, timeout_s: float = TIMEOUT_POWERSHELL_S) -> tuple[int, str]:
    """Roda ``script`` codificado em base64 (UTF-16LE, como o ``-EncodedCommand`` pede); devolve código e saída."""
    codificado = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    argv = [powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", codificado]
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return -1, str(erro)
    return proc.returncode, "\n".join(p.strip() for p in (proc.stdout or "", proc.stderr or "") if p.strip())


def literal(texto: str) -> str:
    """Literal do PowerShell entre aspas simples: dentro dele nada expande, e a aspa simples se escreve dobrada."""
    return "'" + texto.replace("'", "''") + "'"


def argumentos_de_linha(argumentos: list[str]) -> str:
    """A linha de argumentos do atalho: cada um entre aspas duplas quando tem espaço (os caminhos não têm aspas)."""
    return " ".join('"%s"' % a if " " in a or not a else a for a in argumentos)


def script_do_atalho(atalho: Path, alvo: str, argumentos: list[str], pasta: str, icone: str, descricao: str) -> str:
    linhas = [
        "$ErrorActionPreference = 'Stop'",
        "New-Item -ItemType Directory -Force -Path %s | Out-Null" % literal(str(atalho.parent)),
        "$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut(%s)" % literal(str(atalho)),
        "$atalho.TargetPath = %s" % literal(alvo),
        "$atalho.Arguments = %s" % literal(argumentos_de_linha(argumentos)),
        "$atalho.WorkingDirectory = %s" % literal(pasta),
        "$atalho.Description = %s" % literal(descricao),
    ]
    if icone:
        linhas.append("$atalho.IconLocation = %s" % literal(icone + ",0"))
    linhas.append("$atalho.Save()")
    return "\n".join(linhas)


def criar(
    atalho: Path,
    alvo: str,
    argumentos: list[str],
    pasta: str,
    *,
    icone: str = "",
    descricao: str = "Goal Pacer",
    rodar: Optional[Callable[[str], tuple[int, str]]] = None,
) -> Path:
    codigo, saida = (rodar or rodar_powershell)(script_do_atalho(atalho, alvo, argumentos, pasta, icone, descricao))
    if codigo != 0:
        raise GpErro(EXIT_IO, "não consegui criar o atalho %s: %s" % (atalho.name, (saida or "sem saída")[-200:]))
    return atalho


def remover(atalho: Path) -> bool:
    if not atalho.is_file():
        return False
    atalho.unlink()
    return True


def _roaming() -> Path:
    return Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming"))


def pasta_menu_iniciar() -> Path:
    return _roaming() / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def pasta_inicializar() -> Path:
    return pasta_menu_iniciar() / "Startup"


def pythonw(python: str) -> str:
    """``pythonw.exe`` ao lado de ``python.exe`` (o mesmo Python, sem abrir console); outro nome fica como está."""
    fim = "python.exe"
    return python[: -len(fim)] + "pythonw.exe" if PureWindowsPath(python).name.lower() == fim else python


def ico(pngs: dict[int, bytes]) -> bytes:
    """Arquivo .ico com um PNG por lado (``{16: bytes, ..., 256: bytes}``); lado 256 se escreve 0 no diretório."""
    lados = sorted(pngs)
    cabecalho = struct.pack("<HHH", 0, 1, len(lados))
    deslocamento = len(cabecalho) + 16 * len(lados)
    diretorio = b""
    corpo = b""
    for lado in lados:
        dados = pngs[lado]
        byte_lado = 0 if lado >= 256 else lado
        diretorio += struct.pack("<BBBBHHII", byte_lado, byte_lado, 0, 0, 1, 32, len(dados), deslocamento + len(corpo))
        corpo += dados
    return cabecalho + diretorio + corpo
