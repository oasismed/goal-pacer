"""processos.py: isolar, encerrar e conferir processos do mesmo jeito no macOS, no Linux e no Windows.

O ``claude -p`` cria netos; no estouro do teto a árvore inteira precisa morrer, e nunca o processo que chamou::

    isolamento()      kwargs do Popen: sessão própria (POSIX) ou grupo novo (Windows)
    desligado()       o mesmo e, no Windows, um console próprio e escondido: o filho sobrevive ao fim do pai (update
                      pelo painel) e os netos (git, ssh-keygen, python) não abrem janela preta
    matar_arvore(p)   SIGKILL no grupo (POSIX) ou taskkill /T /F (Windows); sem grupo, só o processo
    encerrar(pid)     SIGTERM (POSIX) ou taskkill /F só daquele pid (Windows): os filhos seguem vivos
    vivo(pid)         existe? os.kill(pid, 0) no POSIX; no Windows, OpenProcess + GetExitCodeProcess, porque lá
                      os.kill(pid, 0) encerraria o processo em vez de consultar
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from typing import Any

WINDOWS = os.name == "nt"
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW: console escondido, herdado pelos netos
AINDA_ATIVO = 259  # STILL_ACTIVE do GetExitCodeProcess
ACESSO_NEGADO = 5
CONSULTA_LIMITADA = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
LIMITE_PID = 2**32 - 1  # acima disso não é pid em sistema nenhum (e o DWORD do Windows não comporta)


def isolamento() -> dict[str, Any]:
    if WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}


def desligado() -> dict[str, Any]:
    if WINDOWS:
        grupo = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)
        return {"creationflags": grupo | SEM_JANELA}
    return {"start_new_session": True}


def matar_arvore(processo: subprocess.Popen) -> None:
    if WINDOWS:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(processo.pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
                check=False,
            )
        with contextlib.suppress(OSError):
            processo.kill()
        return
    try:
        os.killpg(os.getpgid(processo.pid), signal.SIGKILL)  # pragma: no mutate (mutante mataria o grupo do teste)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(OSError):
            processo.kill()


def encerrar(pid: int) -> None:
    """Pede para o processo ``pid`` sair; os filhos dele não são tocados."""
    if WINDOWS:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=30,
                check=False,
            )
        return
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)


def vivo(pid: Any) -> bool:
    """True se existe um processo com ``pid``. Valores que não são pid positivo contam como mortos."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or pid > LIMITE_PID:
        return False
    return _vivo_windows(pid) if WINDOWS else _vivo_posix(pid)


def _vivo_posix(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, de outro usuário
    except (OverflowError, ValueError):
        return False  # pid impossível (acima do int do sistema)
    return True


def _vivo_windows(pid: int) -> bool:  # pragma: no cover - só roda no Windows
    import ctypes

    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009 - só existe no Windows
    alca = kernel32.OpenProcess(CONSULTA_LIMITADA, False, pid)
    if not alca:
        return getattr(ctypes, "get_last_error")() == ACESSO_NEGADO  # noqa: B009 - só existe no Windows
    try:
        codigo = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
            return False
        return codigo.value == AINDA_ATIVO
    finally:
        kernel32.CloseHandle(alca)
