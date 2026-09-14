#!/usr/bin/env python3
"""Os instaladores de um arquivo de verdade (``mac`` roda em qualquer Mac, numa pasta de usuário temporária; ``windows`` só num Windows de teste, porque instala no perfil de verdade).

Monta duas versões de teste (``versao_de_teste.py``: 9.0.0 e 9.1.0, assinadas por uma chave do teste), gera os
instaladores com ``dev/empacotar.py`` e confere o que a pessoa faria::

    mac      .dmg montado, app copiado para uma pasta Aplicativos temporária e aberto de verdade (HOME temporário,
             launchctl de mentira): a janela roda o instalador embutido e termina a instalação; depois o instalador
             embutido rodado como o app roda: repete em dia, atualiza pelo app da 9.1.0; app universal, assinatura
             local intacta e jobs no Python copiado para ~/.goal-pacer/runtime
    windows  Setup.exe /S da 9.0.0 (pasta de usuário do runner): tarefas no Agendador, atalho, painel respondendo e a
             desinstalação registrada; Setup.exe /S da 9.1.0 atualiza e tira a pasta da versão anterior; o
             desinstalador tira tarefas, atalhos e o registro

Uso: ``python tests/e2e/instaladores.py mac|windows`` (sai com 1 e a lista do que falhou).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_REPO = AQUI.parents[1]
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ_REPO / "dev"))

from versao_de_teste import chave_de_teste, pasta_baixada  # noqa: E402

import empacotar  # noqa: E402

ENDERECO = "http://127.0.0.1:8765/"


class Conferencia:
    def __init__(self) -> None:
        self.falhas: list[str] = []

    def __call__(self, ok: bool, texto: str) -> None:
        print(("OK      " if ok else "FALHOU  ") + texto, flush=True)
        if not ok:
            self.falhas.append(texto)

    def fim(self, nome: str) -> int:
        if self.falhas:
            print("\n%d falha(s):\n  %s" % (len(self.falhas), "\n  ".join(self.falhas)))
            return 1
        print("\n%s conferido" % nome)
        return 0


def rodar(argv: list[str] | str, env: dict, timeout_s: float = 900) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        argv,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )
    print(
        "$ %s -> %d\n%s%s"
        % (
            argv if isinstance(argv, str) else " ".join(argv),
            proc.returncode,
            proc.stdout[-4000:],
            proc.stderr[-2000:],
        ),
        flush=True,
    )
    return proc


def painel_no_ar() -> bool:
    try:
        with urllib.request.urlopen(ENDERECO, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def esperar(condicao, segundos: float) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(1)
    return condicao()


def versoes(base: Path) -> tuple[Path, Path]:
    chave = chave_de_teste(base)
    return pasta_baixada(base, "9.0.0", chave), pasta_baixada(base, "9.1.0", chave, "NOVIDADE.md")


# --- Mac ---------------------------------------------------------------------------------------------------------


def _copiar_do_dmg(dmg: Path, aplicativos: Path, montagem: Path) -> Path:
    montagem.mkdir(exist_ok=True)
    subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(montagem), str(dmg)], check=True, timeout=300
    )
    try:
        app = aplicativos / "Goal Pacer.app"
        shutil.rmtree(str(app), ignore_errors=True)
        subprocess.run(["ditto", str(montagem / "Goal Pacer.app"), str(app)], check=True, timeout=300)
        atalho = montagem / "Aplicativos"
        return (
            app if atalho.is_symlink() and os.readlink(str(atalho)) == "/Applications" else app.with_name("sem-atalho")
        )
    finally:
        subprocess.run(["hdiutil", "detach", str(montagem)], check=False, timeout=120)


def _abrir_como_o_app(app: Path, env: dict) -> subprocess.CompletedProcess:
    """O que o Goal Pacer.app faz ao abrir quando precisa preparar (macos/main.swift, preparar())."""
    recursos = app / "Contents" / "Resources"
    return rodar(
        [
            str(recursos / "python" / "bin" / "python3"),
            str(recursos / "goal-pacer" / "scripts" / "instalar.py"),
            "--origem-padrao",
            str(recursos / "goal-pacer"),
            "--nao-interativo",
            "--instalar-ou-atualizar",
            "--de-app",
            str(app),
        ],
        env,
    )


def _abrir_a_janela(app: Path, env: dict, casa: Path) -> bool:
    """Abre o Goal Pacer.app (a janela nativa) e espera o instalador embutido que ela dispara terminar."""
    instalacao = casa / ".goal-pacer" / "jobs" / "instalacao.json"
    python = str(app / "Contents" / "Resources" / "python" / "bin" / "python3")
    janela = subprocess.Popen([str(app / "Contents" / "MacOS" / "GoalPacer")], env=env, stdin=subprocess.DEVNULL)

    def instalador_rodando() -> bool:
        return subprocess.run(["pgrep", "-f", python], capture_output=True, check=False).returncode == 0

    try:
        comecou = esperar(instalador_rodando, 60)
        terminou = esperar(lambda: not instalador_rodando(), 900)
        viva = janela.poll() is None
        print("janela: instalador começou=%s terminou=%s janela aberta=%s" % (comecou, terminou, viva), flush=True)
        return comecou and terminou and viva and instalacao.is_file()
    finally:
        janela.terminate()
        try:
            janela.wait(timeout=30)
        except subprocess.TimeoutExpired:
            janela.kill()
            janela.wait(timeout=30)


def mac() -> int:
    conferir = Conferencia()
    base = Path(tempfile.mkdtemp(prefix="gp-instaladores-"))
    v1, v2 = versoes(base)
    dist, cache = base / "dist", Path.home() / ".cache" / "goal-pacer-empacotar"
    dmg1, dmg2 = empacotar.construir_dmg(v1, dist, cache), empacotar.construir_dmg(v2, dist, cache)
    conferir(dmg1.stat().st_size < 80 * 1024 * 1024, ".dmg abaixo de 80 MB (%d MB)" % (dmg1.stat().st_size >> 20))
    casa, aplicativos = base / "casa", base / "Aplicativos"
    casa.mkdir()
    aplicativos.mkdir()
    lancador = base / "launchctl"
    lancador.write_text("#!/bin/sh\necho \"$@\" >> '%s'\n" % (base / "launchctl.log"), encoding="utf-8")
    lancador.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_")}
    env.update(HOME=str(casa), GP_LAUNCHCTL=str(lancador), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

    app = _copiar_do_dmg(dmg1, aplicativos, base / "montagem")
    conferir(app.name == "Goal Pacer.app", ".dmg com o app e o atalho para Aplicativos")
    arquiteturas = subprocess.run(
        ["lipo", "-archs", str(app / "Contents" / "MacOS" / "GoalPacer")], capture_output=True, text=True, check=False
    ).stdout
    conferir("arm64" in arquiteturas and "x86_64" in arquiteturas, "janela universal (%s)" % arquiteturas.strip())
    conferir(_abrir_a_janela(app, env, casa), "a janela do app instala na primeira abertura")
    instalacao = json.loads((casa / ".goal-pacer" / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    conferir(
        instalacao.get("versao") == "9.0.0" and instalacao.get("janela") == str(app),
        "instalacao.json com a 9.0.0 e o app como janela",
    )
    conferir("/.goal-pacer/runtime/python-" in instalacao.get("python3", ""), "jobs no Python copiado para o runtime")
    conferir(
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=False).returncode == 0,
        "assinatura do app intacta depois de instalar",
    )
    proc = _abrir_como_o_app(app, env)
    conferir(
        proc.returncode == 0 and "Já está na versão mais nova" in proc.stdout,
        "abrir outra vez na mesma versão só reaplica",
    )

    app = _copiar_do_dmg(dmg2, aplicativos, base / "montagem")
    proc = _abrir_como_o_app(app, env)
    conferir(
        proc.returncode == 0 and "manifesto assinado por" in proc.stdout,
        "o app da 9.1.0 atualiza conferindo o manifesto",
    )
    instalacao = json.loads((casa / ".goal-pacer" / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    conferir(
        instalacao.get("versao") == "9.1.0" and (casa / ".goal-pacer" / "app" / "NOVIDADE.md").is_file(),
        "instalação na 9.1.0",
    )
    return conferir.fim("instaladores do Mac")


# --- Windows -----------------------------------------------------------------------------------------------------


def _setup(setup: Path, env: dict) -> subprocess.CompletedProcess:
    return rodar([str(setup), "/S"], env, timeout_s=1200)


def windows() -> int:
    conferir = Conferencia()
    base = Path(tempfile.mkdtemp(prefix="gp-instaladores-"))
    v1, v2 = versoes(base)
    dist, cache = base / "dist", Path.home() / ".cache" / "goal-pacer-empacotar"
    setup1, setup2 = empacotar.construir_setup(v1, dist, cache), empacotar.construir_setup(v2, dist, cache)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_")}
    pasta = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Goal Pacer"
    raiz = Path.home() / ".goal-pacer"
    menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

    proc = _setup(setup1, env)
    conferir(proc.returncode == 0, "Setup.exe /S da 9.0.0 (exit %d)" % proc.returncode)
    conferir((pasta / "9.0.0" / "python" / "pythonw.exe").is_file(), "Python embutido na pasta da versão")
    instalacao = (
        json.loads((raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
        if (raiz / "jobs" / "instalacao.json").is_file()
        else {}
    )
    conferir(instalacao.get("versao") == "9.0.0", "instalacao.json com a 9.0.0")
    conferir(
        rodar(["schtasks", "/Query", "/TN", "GoalPacer\\diario"], env, 60).returncode == 0,
        "tarefa do diário no Agendador",
    )
    conferir(
        (menu / "Goal Pacer.lnk").is_file() and (menu / "Startup" / "Goal Pacer (painel).lnk").is_file(),
        "atalhos no menu Iniciar e na Inicialização",
    )
    conferir(esperar(painel_no_ar, 90), "painel respondendo")
    registro = rodar(
        ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\GoalPacer", "/v", "DisplayVersion"],
        env,
        60,
    )
    conferir(registro.returncode == 0 and "9.0.0" in registro.stdout, "desinstalação registrada em Aplicativos")

    proc = _setup(setup2, env)
    conferir(proc.returncode == 0, "Setup.exe /S da 9.1.0 atualiza (exit %d)" % proc.returncode)
    instalacao = json.loads((raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    conferir(instalacao.get("versao") == "9.1.0" and (raiz / "app" / "NOVIDADE.md").is_file(), "instalação na 9.1.0")
    conferir("9.1.0" in instalacao.get("python3", ""), "jobs no Python da pasta nova")
    conferir(esperar(lambda: not (pasta / "9.0.0").exists(), 30), "pasta da 9.0.0 removida")
    conferir(esperar(painel_no_ar, 90), "painel no ar depois do update")

    desinstalador = pasta / "Desinstalar Goal Pacer.exe"
    # _?= sem aspas e por último: é assim que o NSIS roda o desinstalador no lugar e espera o fim (entre aspas, como a
    # lista viraria, ele se copia para a pasta temporária e sai na hora)
    proc = rodar('"%s" /S _?=%s' % (desinstalador, pasta), env, 900)
    conferir(proc.returncode == 0, "desinstalador (exit %d)" % proc.returncode)
    conferir(rodar(["schtasks", "/Query", "/TN", "GoalPacer\\diario"], env, 60).returncode != 0, "tarefas removidas")
    conferir(not (menu / "Goal Pacer.lnk").exists(), "atalho removido")
    conferir(
        rodar(
            ["reg", "query", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\GoalPacer"], env, 60
        ).returncode
        != 0,
        "registro removido",
    )
    conferir((raiz / "dados").exists(), "dados preservados")
    return conferir.fim("instaladores do Windows")


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else ""
    if alvo not in ("mac", "windows"):
        raise SystemExit("uso: python tests/e2e/instaladores.py mac|windows")
    sys.exit(mac() if alvo == "mac" else windows())
