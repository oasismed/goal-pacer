"""goalpacer/plataforma.py: backend Linux (systemd --user, notify-send) e macOS (launchd, osascript) com stubs.

Nada toca o systemd, o launchd ou o HOME reais: ``systemctl``, ``loginctl``, ``notify-send``
e ``osascript`` são scripts que gravam os argumentos; o HOME é temporário.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from goalpacer import base, plataforma

RAIZ_REPO = Path(__file__).resolve().parent.parent
INSTALL = RAIZ_REPO / "install.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def stub(pasta: Path, nome: str, corpo: str) -> Path:
    path = pasta / nome
    path.write_text("#!/bin/sh\n" + corpo + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def linux(tmp_path, monkeypatch):
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "chamadas.log"
    stub(stubs, "systemctl", 'echo "systemctl $@" >> "%s"\nif [ "$2" = "is-enabled" ]; then echo enabled; fi' % log)
    stub(stubs, "loginctl", 'echo "Linger=no"')
    stub(stubs, "notify-send", 'echo "notify-send $@" >> "%s"' % log)
    stub(
        stubs,
        "claude",
        'if [ "$1" = "--version" ]; then echo "2.1.270 (Claude Code)"; else cat "%s"; fi'
        % (FIXTURES / "offline" / "mcp_list.txt"),
    )
    for nome, valor in (
        ("GP_PLATAFORMA", "linux"),
        ("GP_SYSTEMCTL", str(stubs / "systemctl")),
        ("GP_LOGINCTL", str(stubs / "loginctl")),
        ("GP_NOTIFY_SEND", str(stubs / "notify-send")),
        ("HOME", str(home)),
    ):
        monkeypatch.setenv(nome, valor)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return {"stubs": stubs, "home": home, "log": log, "tmp": tmp_path}


def chamadas(ctx) -> list[str]:
    return ctx["log"].read_text(encoding="utf-8").splitlines() if ctx["log"].exists() else []


def test_escolha_da_plataforma(monkeypatch):
    monkeypatch.setenv("GP_PLATAFORMA", "linux")
    assert (
        plataforma.nome_atual() == "linux"
        and plataforma.atual().agendador.nome == "systemd"
        and plataforma.atual().pastas_protegidas == ()
    )
    assert (
        plataforma.dir_tcc_proibido(Path.home() / "Downloads" / "dados") is False
    )  # no Linux nenhuma pasta do HOME é bloqueada
    monkeypatch.setenv("GP_PLATAFORMA", "macos")
    assert (
        plataforma.atual().agendador.nome == "launchd"
        and plataforma.dir_tcc_proibido(Path.home() / "Downloads" / "dados") is True
    )
    monkeypatch.setenv("GP_PLATAFORMA", "outro")
    assert plataforma.nome_atual() == ("macos" if sys.platform == "darwin" else "linux")


def test_systemd_renderiza_escapa_e_confere(linux, tmp_path):
    app, jobs = RAIZ_REPO, tmp_path / "jobs"
    jobs.mkdir()
    valores = {
        "PYTHON3": "/usr/bin/python3",
        "APP": "/opt/goal pacer/app",
        "JOBS": str(jobs),
        "RAIZ": "/home/x/.goal-pacer",
        "DADOS": "/home/x/Meus Dados 100% #1",
        "CLAUDE": "/home/x/.local/bin/claude",
    }
    sistema = plataforma.atual()
    gerados = sistema.agendador.gerar(app, jobs, valores, "rede")
    assert set(gerados) == {"goal-pacer-diario", "goal-pacer-mensal", "goal-pacer-painel"}
    servico = (jobs / "goal-pacer-diario.service").read_text(encoding="utf-8")
    assert 'ExecStart="/usr/bin/python3" "/opt/goal pacer/app/jobs/run_job.py" diario' in servico
    assert (
        'Environment="GP_DATA_DIR=/home/x/Meus Dados 100%% #1"' in servico
        and "UMask=0077" in servico
        and "NoNewPrivileges=yes" in servico
    )
    timer = (jobs / "goal-pacer-diario.timer").read_text(encoding="utf-8")
    assert "OnCalendar=Mon..Sat *-*-* 07:00:00" in timer and "Persistent=true" in timer
    assert "OnCalendar=*-*-01 05:30:00" in (jobs / "goal-pacer-mensal.timer").read_text(encoding="utf-8")
    assert 'ExecStart="/usr/bin/python3" "/opt/goal pacer/app/scripts/web.py" --rede' in (
        jobs / "goal-pacer-painel.service"
    ).read_text(encoding="utf-8")
    assert [p.name for p in gerados["goal-pacer-painel"]] == ["goal-pacer-painel.service"]
    # template adulterado não carrega: o ExecStart renderizado precisa ser exatamente o esperado
    falso = tmp_path / "app-falso"
    (falso / "jobs" / "systemd").mkdir(parents=True)
    for unidade in (
        "goal-pacer-diario.service",
        "goal-pacer-diario.timer",
        "goal-pacer-mensal.service",
        "goal-pacer-mensal.timer",
    ):
        texto = (RAIZ_REPO / "jobs" / "systemd" / (unidade + ".tmpl")).read_text(encoding="utf-8")
        (falso / "jobs" / "systemd" / (unidade + ".tmpl")).write_text(
            texto.replace("run_job.py", "outro.py"), encoding="utf-8"
        )
    with pytest.raises(base.GpErro):
        sistema.agendador.gerar(falso, jobs, valores, "")


def test_install_sh_no_linux_com_systemd_user(linux):
    ctx = linux
    dados = ctx["tmp"] / "Meus Dados #1"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_")}
    env.update(
        {
            "GP_PLATAFORMA": "linux",
            "GP_SYSTEMCTL": str(ctx["stubs"] / "systemctl"),
            "GP_LOGINCTL": str(ctx["stubs"] / "loginctl"),
            "GP_PYTHON3": sys.executable,
            "GP_CLAUDE_BIN": str(ctx["stubs"] / "claude"),
            "GP_OFFLINE_DIR": str(FIXTURES / "offline"),
            "GP_AGORA": "2026-09-28T07:00:00-03:00",
            "GP_TZ": "America/Sao_Paulo",
            "HOME": str(ctx["home"]),
        }
    )

    def rodar(*args):
        return subprocess.run(
            ["bash", str(INSTALL), *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300
        )

    proc = rodar(
        "--from", str(RAIZ_REPO), "--copiar", "--nao-interativo", "--dados", str(dados), "--offline", "--painel-rede"
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    unidades = ctx["home"] / ".config" / "systemd" / "user"
    assert sorted(p.name for p in unidades.iterdir()) == [
        "goal-pacer-diario.service",
        "goal-pacer-diario.timer",
        "goal-pacer-mensal.service",
        "goal-pacer-mensal.timer",
        "goal-pacer-painel.service",
    ]
    log = chamadas(ctx)
    assert "systemctl --user daemon-reload" in log and "systemctl --user enable --now goal-pacer-diario.timer" in log
    assert "systemctl --user enable --now goal-pacer-painel.service" in log
    # só LaunchAgents importa: o python3 da Apple grava caches em ~/Library/Caches mesmo com HOME temporário
    assert not (ctx["home"] / "Library" / "LaunchAgents").exists() and "xcode" not in proc.stdout.lower()
    instalacao = json.loads((ctx["home"] / ".goal-pacer" / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert (
        instalacao["plataforma"] == "linux"
        and instalacao["agendado"] is True
        and "goal-pacer-painel" in instalacao["labels"]
    )
    assert (os.stat(dados).st_mode & 0o777) == 0o700
    # desinstalar desliga os timers e remove as unidades, sem tocar nos dados
    proc = rodar("--uninstall", "--nao-interativo", "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (
        not any(unidades.iterdir())
        and "systemctl --user disable --now goal-pacer-diario.timer" in chamadas(ctx)
        and dados.is_dir()
    )


def test_doctor_notificacao_e_nome_local_no_linux(linux, monkeypatch):
    import status
    import web

    item = status.item_jobs()
    assert item.ok and "systemd" in item.detalhe and "loginctl enable-linger" in item.detalhe
    assert status.item_python().ok  # no Linux não há Xcode para exigir
    assert plataforma.atual().agendador.comando_agora("diario") == "systemctl --user start goal-pacer-diario.service"
    assert plataforma.atual().notificar("Rode /goal-pacer onboarding.") is None
    assert chamadas(linux)[-1] == "notify-send --app-name=Goal Pacer Goal Pacer Rode /goal-pacer onboarding."
    monkeypatch.delenv("GP_NOME_LOCAL", raising=False)
    monkeypatch.setattr(web.socket, "gethostname", lambda: "Estudio.lan")
    assert web.nome_local() == "estudio.local"
    stub(linux["stubs"], "systemctl", "exit 1")
    item = status.item_jobs()
    assert not item.ok and "goal-pacer-diario, goal-pacer-mensal fora do systemd" in item.detalhe


def test_notificacao_no_macos_escapa_aspas(tmp_path, monkeypatch):
    log = tmp_path / "osascript.log"
    monkeypatch.setenv("GP_OSASCRIPT", str(stub(tmp_path, "osascript", 'printf "%%s\\n" "$*" >> "%s"' % log)))
    assert plataforma.atual().notificar('diz "oi" \\ tchau') is None
    assert (
        log.read_text(encoding="utf-8").strip()
        == '-e display notification "diz \\"oi\\" \\\\ tchau" with title "Goal Pacer"'
    )
    monkeypatch.setenv("GP_OSASCRIPT", str(tmp_path / "nao-existe"))
    assert plataforma.atual().notificar("x") == "sem osascript"


def test_launchd_espera_o_agente_antigo_sair_antes_do_bootstrap(tmp_path, monkeypatch):
    """Reproduz o painel que não voltava depois do update: o bootstrap logo após o bootout falha com 5 enquanto o
    serviço antigo sai; tentar outra vez resolve, e só no fim o load -w entra."""
    monkeypatch.setenv("HOME", str(tmp_path))
    respostas = iter([(0, ""), (5, "Bootstrap failed: 5"), (5, "Bootstrap failed: 5"), (0, "")])
    chamadas = []

    def rodar(argv, timeout_s=60):
        chamadas.append(argv[1])
        return next(respostas)

    esperas = []
    monkeypatch.setattr(plataforma, "_rodar", rodar)
    monkeypatch.setattr(plataforma.time, "sleep", esperas.append)
    arquivo = tmp_path / "com.goal-pacer.painel.plist"
    arquivo.write_text("x", encoding="utf-8")
    launchd = plataforma.Launchd()
    monkeypatch.setattr(plataforma.os, "getuid", lambda: 501, raising=False)
    assert launchd.carregar({"com.goal-pacer.painel": [arquivo]}) == []
    assert chamadas == ["bootout", "bootstrap", "bootstrap", "bootstrap"] and esperas == [1.0, 1.0]
    respostas = iter([(0, "")] + [(5, "")] * plataforma.TENTATIVAS_BOOTSTRAP + [(1, "")])
    chamadas.clear()
    assert launchd.carregar({"com.goal-pacer.painel": [arquivo]}) == ["com.goal-pacer.painel"]
    assert chamadas[-1] == "load" and chamadas.count("bootstrap") == plataforma.TENTATIVAS_BOOTSTRAP
