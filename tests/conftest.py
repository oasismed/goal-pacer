"""Fixtures comuns: ``scripts/`` no sys.path, pasta de dados temporária e
relógio fixo (achado 6.2). Os testes nunca tocam ~/.goal-pacer nem rodam
``claude -p``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Iterator

import pytest

RAIZ_REPO = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ_REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

AGORA_FIXO = "2026-09-28T07:00:00-03:00"
TZ_FIXO = "America/Sao_Paulo"


def pytest_configure(config: pytest.Config) -> None:
    """D-08 (PYSEC-2026-1845): antes do pytest 9, a pasta dos ``tmp_path`` é ``/tmp/pytest-of-<usuário>``, previsível
    para outro usuário da máquina. No pytest 8 (o do Python 3.9), cada rodada ganha uma pasta 0700 de nome
    aleatório, apagada no fim; no pytest 9 fica o padrão, que já corrige isso."""
    config.addinivalue_line("markers", "posix: teste que só roda em macOS e Linux")
    if pytest.version_tuple >= (9,) or config.option.basetemp:
        return
    import tempfile

    config.option.basetemp = tempfile.mkdtemp(prefix="goal-pacer-pytest-")
    config._gp_basetemp_privada = config.option.basetemp  # type: ignore[attr-defined]


# Módulos que dependem de stubs em shell (#!/bin/sh), de symlink, de permissões POSIX ou do launchd: no Windows ficam
# de fora; o que é do Windows está em test_windows.py e test_lancador.py, e a instalação de verdade em tests/e2e/windows.py.
SO_POSIX = {
    "test_caminhos_de_erro.py",
    "test_install.py",
    "test_instalar_caracterizacao.py",
    "test_logs_caracterizacao.py",
    "test_janela.py",
    "test_plataforma.py",
    "test_primeiros_passos.py",
    "test_provedor.py",
    "test_proxy.py",
    "test_run_job.py",
    "test_seguranca.py",
    "test_status.py",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if sys.platform != "win32":
        return
    pular = pytest.mark.skip(reason="só em macOS e Linux (stubs em shell, symlink ou permissões POSIX)")
    for item in items:
        if item.path.name in SO_POSIX or item.get_closest_marker("posix"):
            item.add_marker(pular)


def pytest_unconfigure(config: pytest.Config) -> None:
    privada = getattr(config, "_gp_basetemp_privada", None)
    if privada:
        import shutil

        shutil.rmtree(privada, ignore_errors=True)


def _caminhos_da_instalacao() -> set[str]:
    """Arquivos de ``~/.goal-pacer`` fora de ``jobs/logs`` (o job e o painel de verdade gravam ali a qualquer hora)."""
    raiz = Path.home() / ".goal-pacer"
    logs = raiz / "jobs" / "logs"
    return {str(c) for c in raiz.rglob("*") if logs not in c.parents} if raiz.is_dir() else set()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config._gp_instalacao_antes = _caminhos_da_instalacao()  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A suíte nunca cria nada em ``~/.goal-pacer`` (a instalação de verdade de quem roda os testes): arquivo novo lá
    durante a rodada falha a sessão, com a lista, para achar o teste que não usou ``dados_tmp``."""
    antes = getattr(session.config, "_gp_instalacao_antes", None)
    if antes is None or getattr(session.config, "workerinput", None) is not None:
        return
    novos = sorted(_caminhos_da_instalacao() - antes)
    if novos:
        sys.stderr.write("\nA suíte criou arquivos em ~/.goal-pacer:\n  %s\n" % "\n  ".join(novos[:20]))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


VARS_GC = (
    "GP_RAIZ",
    "GP_DATA_DIR",
    "GP_AGORA",
    "GP_TZ",
    "GP_RUN_ID",
    "GP_CLAUDE_BIN",
    "GP_PROXY_BACKOFF_S",
)


@pytest.fixture(autouse=True)
def ambiente_sem_vazamento(request: pytest.FixtureRequest) -> Iterator[None]:
    """Nenhum teste deixa GP_* no ambiente nem relógio fixado para o próximo (vazamento que fazia um teste depender
    da ordem: test_registro antes de test_calendar_ops). Quem muda o ambiente usa o monkeypatch; o resto falha aqui."""
    import os

    from goalpacer import clock

    antes = {v: os.environ[v] for v in os.environ if v.startswith("GP_")}
    relogio = (clock._AGORA_FIXADO, clock._TZ_FIXADO)
    yield
    depois = {v: os.environ[v] for v in os.environ if v.startswith("GP_")}
    vazou = sorted(v for v in set(antes) | set(depois) if antes.get(v) != depois.get(v))
    relogio_vazou = relogio != (clock._AGORA_FIXADO, clock._TZ_FIXADO)
    for v in vazou:
        if v in antes:
            os.environ[v] = antes[v]
        else:
            os.environ.pop(v, None)
    clock._AGORA_FIXADO, clock._TZ_FIXADO = relogio
    if vazou or relogio_vazou:
        pytest.fail(
            "%s deixou o ambiente mudado: %s%s"
            % (request.node.nodeid, ", ".join(vazou), " relógio fixado" if relogio_vazou else "")
        )


@pytest.fixture(autouse=True)
def telemetria_isolada(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Cada teste tem a própria pasta de telemetria: nunca ~/.goal-pacer/jobs/logs, e um teste não vê os alertas de outro."""
    monkeypatch.setenv("GP_LOGS_DIR", str(tmp_path_factory.mktemp("telemetria")))


@pytest.fixture(autouse=True)
def plataforma_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    """A suíte assume macOS, a plataforma principal, em qualquer sistema (Linux pelo Docker incluso);
    os testes do backend Linux trocam ``GP_PLATAFORMA`` explicitamente."""
    monkeypatch.setenv("GP_PLATAFORMA", "macos")
    monkeypatch.delenv("GP_IDIOMA", raising=False)  # o idioma vem do contexto de cada teste
    monkeypatch.delenv("GP_PROVEDOR", raising=False)  # a suíte assume o provedor padrão (claude)
    from goalpacer import copy

    copy.usar(None)
    copy.seguir_pasta(None)


@pytest.fixture
def dados_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """GP_RAIZ e GP_DATA_DIR apontando para tmp_path; demais GP_* limpas.

    Devolve a pasta de dados. A raiz fica em ``tmp_path / "raiz"``.
    """
    for nome in VARS_GC:
        monkeypatch.delenv(nome, raising=False)
    raiz = tmp_path / "raiz"
    dados = tmp_path / "dados"
    raiz.mkdir()
    dados.mkdir()
    monkeypatch.setenv("GP_RAIZ", str(raiz))
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_PROXY_BACKOFF_S", "0")
    return dados


@pytest.fixture
def guardar_env(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """``guardar_env("GP_DATA_DIR", ...)``: o teste devolve estas variáveis como achou mesmo quando um ``main()`` em
    processo as grava (``monkeypatch.delenv`` de variável ausente não registra nada para desfazer)."""
    import os

    def guardar(*nomes: str) -> None:
        for nome in nomes:
            if nome in os.environ:
                monkeypatch.setenv(nome, os.environ[nome])
            else:
                monkeypatch.setenv(nome, "")
                monkeypatch.delenv(nome)

    return guardar


@pytest.fixture
def agora_fixo(monkeypatch: pytest.MonkeyPatch) -> str:
    """GP_AGORA=2026-09-28T07:00:00-03:00 (segunda-feira, W40) e
    GP_TZ=America/Sao_Paulo; zera o estado fixado em ``clock``.

    Devolve o ISO fixado.
    """
    monkeypatch.setenv("GP_AGORA", AGORA_FIXO)
    monkeypatch.setenv("GP_TZ", TZ_FIXO)
    from goalpacer import clock

    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    monkeypatch.setattr(clock, "_TZ_FIXADO", None, raising=False)
    return AGORA_FIXO
