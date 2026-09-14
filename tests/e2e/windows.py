#!/usr/bin/env python3
"""Instalação de verdade no Windows pelo clique duplo (roda num Windows de teste ou numa máquina virtual, nunca na máquina de uso: cria tarefas e atalhos de verdade).

Numa pasta de usuário temporária (``USERPROFILE``, ``APPDATA`` e ``LOCALAPPDATA`` trocados), monta duas pastas
"baixadas" como o zip da versão sai descompactado (cópia da árvore, sem .git, com manifesto assinado por uma chave do
teste), roda o ``Instalar Goal Pacer.cmd`` de cada uma como o Explorer rodaria e confere, com as ferramentas do Windows::

    instala       exit 0 sem o Claude Code; tarefas GoalPacer\\diario e \\mensal no Agendador; atalhos na pasta
                  Inicializar e no menu Iniciar; instalacao.json com plataforma windows; tzdata acessível
    painel        http://127.0.0.1:8765/ responde (o lançador pelo pythonw, sem console) e o comando goal-pacer.cmd roda
    outra vez     o mesmo clique duplo com a instalação em dia: exit 0, só reaplica
    atualiza      o clique duplo na pasta da versão seguinte confere o manifesto e troca o app
    desinstala    tarefas e atalhos somem e o painel sai do ar; os dados ficam

Uso: ``python tests/e2e/windows.py`` (sai com 1 e a lista do que falhou).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from versao_de_teste import pasta_baixada  # noqa: E402

ENDERECO = "http://127.0.0.1:8765/"
TAREFAS = ("GoalPacer\\diario", "GoalPacer\\mensal")


def rodar(argv: list[str], env: dict, timeout_s: float = 900) -> subprocess.CompletedProcess:
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
    print("$ %s -> %d\n%s%s" % (" ".join(argv), proc.returncode, proc.stdout, proc.stderr), flush=True)
    return proc


def tarefa_existe(nome: str, env: dict) -> bool:
    return rodar(["schtasks", "/Query", "/TN", nome], env, 60).returncode == 0


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


def main() -> int:
    falhas: list[str] = []

    def conferir(ok: bool, texto: str) -> None:
        print(("OK      " if ok else "FALHOU  ") + texto, flush=True)
        if not ok:
            falhas.append(texto)

    perfil = Path(tempfile.mkdtemp(prefix="goal-pacer-perfil-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_")}
    env.update(
        USERPROFILE=str(perfil),
        HOME=str(perfil),
        APPDATA=str(perfil / "AppData" / "Roaming"),
        LOCALAPPDATA=str(perfil / "AppData" / "Local"),
    )
    raiz = perfil / ".goal-pacer"
    inicializar = Path(env["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    menu = inicializar.parent
    downloads = perfil / "Downloads"
    downloads.mkdir()
    chave = perfil / "chave-ci"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True, timeout=60)
    v1 = pasta_baixada(downloads, "9.0.0", chave)
    v2 = pasta_baixada(downloads, "9.1.0", chave, "NOVIDADE.md")
    instalador = ["cmd", "/c", str(v1 / "Instalar Goal Pacer.cmd"), "--sem-abrir", "--offline"]

    proc = rodar(instalador, env)
    conferir(proc.returncode == 0, "o clique duplo instala sem o Claude Code (exit %d)" % proc.returncode)
    conferir("Claude Code: não achei neste computador" in proc.stdout, "avisa que falta o Claude Code")
    for nome in TAREFAS:
        conferir(tarefa_existe(nome, env), "tarefa %s no Agendador" % nome)
    conferir((inicializar / "Goal Pacer (painel).lnk").is_file(), "atalho do painel na pasta Inicializar")
    conferir((menu / "Goal Pacer.lnk").is_file(), "atalho Goal Pacer no menu Iniciar")
    instalacao_path = raiz / "jobs" / "instalacao.json"
    instalacao = json.loads(instalacao_path.read_text(encoding="utf-8")) if instalacao_path.is_file() else {}
    conferir(instalacao.get("plataforma") == "windows", "instalacao.json com plataforma windows")
    python = instalacao.get("python3") or sys.executable
    fuso = rodar(
        [
            python,
            "-c",
            "import sys; sys.path.insert(0, r'%s'); import goalpacer.clock as c; print(c.fuso('America/Sao_Paulo'))"
            % (raiz / "app" / "scripts"),
        ],
        env,
        60,
    )
    conferir(fuso.returncode == 0 and "America/Sao_Paulo" in fuso.stdout, "fusos IANA disponíveis para o app")
    conferir(esperar(painel_no_ar, 90), "painel respondendo em %s" % ENDERECO)
    comando = raiz / "bin" / "goal-pacer.cmd"
    versao = rodar(["cmd", "/c", str(comando), "versao"], env, 120)
    conferir(versao.returncode == 0, "goal-pacer.cmd versao roda")

    proc = rodar(instalador, env)
    conferir(proc.returncode == 0, "o mesmo clique duplo com a instalação em dia (exit %d)" % proc.returncode)
    conferir(esperar(painel_no_ar, 90), "painel no ar depois de reaplicar")

    proc = rodar(["cmd", "/c", str(v2 / "Instalar Goal Pacer.cmd"), "--sem-abrir", "--offline"], env)
    conferir(proc.returncode == 0, "o clique duplo na versão seguinte atualiza (exit %d)" % proc.returncode)
    conferir("manifesto assinado por ci@exemplo.test conferido" in proc.stdout, "manifesto da pasta conferido")
    conferir((raiz / "app" / "NOVIDADE.md").is_file(), "app trocado pela versão 9.1.0")
    conferir(esperar(painel_no_ar, 90), "painel no ar depois do update")

    desinstalar = [
        python,
        str(raiz / "app" / "scripts" / "instalar.py"),
        "--uninstall",
        "--nao-interativo",
        "--offline",
    ]
    proc = rodar(desinstalar, env)
    conferir(proc.returncode == 0, "desinstala (exit %d)" % proc.returncode)
    for nome in TAREFAS:
        conferir(not tarefa_existe(nome, env), "tarefa %s removida" % nome)
    conferir(not (inicializar / "Goal Pacer (painel).lnk").exists(), "atalho do painel removido")
    conferir(not (menu / "Goal Pacer.lnk").exists(), "atalho do menu Iniciar removido")
    conferir(esperar(lambda: not painel_no_ar(), 60), "painel fora do ar")
    conferir((raiz / "dados").exists(), "dados preservados")

    if falhas:
        print("\n%d falha(s):\n  %s" % (len(falhas), "\n  ".join(falhas)))
        return 1
    print("\ninstalação no Windows conferida")
    return 0


if __name__ == "__main__":
    sys.exit(main())
