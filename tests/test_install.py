"""install.sh + scripts/instalar.py + scripts/migrar.py (T9/T18/T24) com HOME temporário e stubs.

Nada aqui toca o HOME real, o launchd real ou o claude: ``launchctl``,
``claude`` e ``xcode-select`` são stubs que gravam as chamadas; o python3 é
o mesmo do pytest (``GP_PYTHON3``); a pasta de dados tem espaço, acento e ``#``.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

from goalpacer import assinatura as assinatura_do_repo

RAIZ_REPO = Path(__file__).resolve().parent.parent
INSTALL = RAIZ_REPO / "install.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LABELS = ("com.goal-pacer.diario", "com.goal-pacer.mensal")


def stub(pasta: Path, nome: str, corpo: str) -> Path:
    path = pasta / nome
    path.write_text("#!/bin/sh\n" + corpo + "\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class Casa:
    def __init__(self, tmp: Path) -> None:
        self.home = tmp / "home"
        self.stubs = tmp / "stubs"
        self.home.mkdir()
        self.stubs.mkdir()
        self.log_launchctl = tmp / "launchctl.log"
        stub(self.stubs, "launchctl", 'echo "$@" >> "%s"' % self.log_launchctl)
        stub(
            self.stubs,
            "claude",
            'if [ "$1" = "--version" ]; then echo "2.1.270 (Claude Code)"; else cat "%s"; fi'
            % (FIXTURES / "offline" / "mcp_list.txt"),
        )
        stub(self.stubs, "xcode-select", "echo /Library/Developer/CommandLineTools")
        self.log_xcrun = tmp / "xcrun.log"
        stub(  # monta um Goal Pacer.app de mentira: compilar Swift de verdade fica no test_janela
            self.stubs,
            "xcrun",
            'echo "$@" >> "%s"; s=""; a=""; for x in "$@"; do [ "$a" = "-o" ] || [ "$a" = "--out" ] && s="$x"; a="$x"; done; '
            'case "$1" in --find) echo /stub/swiftc ;; swiftc|sips|iconutil) printf x > "$s" ;; esac' % self.log_xcrun,
        )
        self.raiz = self.home / ".goal-pacer"
        self.dados = self.home / "Meus Dados #1" / "ação"

    def env(self, **extra: str) -> dict:
        env = {
            k: v
            for k, v in os.environ.items()
            if (not k.startswith("GP_") or k == "GP_PLATAFORMA") and k not in ("CLAUDE_CONFIG_DIR", "HOME")
        }
        env.update(
            {
                "HOME": str(self.home),
                "GP_PYTHON3": sys.executable,
                "GP_LAUNCHCTL": str(self.stubs / "launchctl"),
                "GP_CLAUDE_BIN": str(self.stubs / "claude"),
                "GP_XCODE_SELECT": str(self.stubs / "xcode-select"),
                "GP_XCRUN": str(self.stubs / "xcrun"),
                "GP_OFFLINE_DIR": str(FIXTURES / "offline"),
                "GP_AGORA": "2026-09-28T07:00:00-03:00",
                "GP_TZ": "America/Sao_Paulo",
                "GP_PLATAFORMA": "macos",
            }
        )
        env.update(extra)
        return env

    def rodar(self, *args: str, entrada: str = "", **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(INSTALL), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=entrada,
            env=self.env(**extra),
            timeout=300,
        )

    def launchctl(self) -> list[str]:
        return self.log_launchctl.read_text(encoding="utf-8").splitlines() if self.log_launchctl.exists() else []


@pytest.fixture
def casa(tmp_path: Path) -> Casa:
    return Casa(tmp_path)


def instalar_copia(casa: Casa, *extra: str, **env: str) -> subprocess.CompletedProcess:
    return casa.rodar(
        "--from", str(RAIZ_REPO), "--copiar", "--nao-interativo", "--dados", str(casa.dados), "--offline", *extra, **env
    )


def test_instala_por_copia_com_caminho_hostil(casa):
    proc = instalar_copia(casa)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    app = casa.raiz / "app"
    assert (
        (app / "SKILL.md").exists()
        and (app / "jobs" / "run_job.py").exists()
        and (app / "scripts" / "goalpacer" / "schema.py").exists()
    )
    assert not (app / ".git").exists() and not list(app.rglob("__pycache__"))
    assert (
        app / "tests" / "fixtures" / "mensal" / "dados" / "contexto.md"
    ).exists()  # "dados" só é ignorado na raiz da origem
    link = casa.home / ".claude" / "skills" / "goal-pacer"
    assert link.is_symlink() and os.readlink(link) == str(app)
    assert (casa.raiz / "dados").is_symlink() and os.readlink(casa.raiz / "dados") == str(casa.dados)
    assert (casa.dados / "inbox" / "whatsapp").is_dir()
    assert (casa.dados.stat().st_mode & 0o777) == 0o700 and (
        (casa.raiz / "jobs" / "logs").stat().st_mode & 0o777
    ) == 0o700
    for label in LABELS:
        agente = casa.home / "Library" / "LaunchAgents" / ("%s.plist" % label)
        conteudo = plistlib.loads(agente.read_bytes())
        assert conteudo["ProgramArguments"] == [
            sys.executable,
            str(app / "jobs" / "run_job.py"),
            label.rsplit(".", 1)[1],
        ]
        assert conteudo["EnvironmentVariables"]["GP_DATA_DIR"] == str(casa.dados)
        assert conteudo["EnvironmentVariables"]["GP_RAIZ"] == str(casa.raiz)
        assert conteudo["EnvironmentVariables"]["GP_CLAUDE_BIN"] == str(casa.stubs / "claude")
        assert conteudo["WorkingDirectory"] == str(casa.raiz / "jobs")
        assert any(
            linha.startswith("bootstrap gui/%d " % os.getuid()) and linha.endswith(str(agente))
            for linha in casa.launchctl()
        )
    assert (
        len(
            plistlib.loads((casa.home / "Library" / "LaunchAgents" / "com.goal-pacer.diario.plist").read_bytes())[
                "StartCalendarInterval"
            ]
        )
        == 6
    )
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert (
        instalacao["dados"] == str(casa.dados)
        and instalacao["modo"] == "copia"
        and instalacao["python3"] == sys.executable
        and instalacao["agendado"] is True
        and instalacao["plataforma"] == "macos"
        and instalacao["provedor"] == "claude"
    )
    assert "OK python3" in proc.stdout and "OK claude" in proc.stdout and "OK conectores" in proc.stdout
    assert "Pronto." in proc.stdout
    # reinstalar é idempotente (symlink refeito, plists recarregados)
    proc = instalar_copia(casa)
    assert proc.returncode == 0, proc.stderr
    assert link.is_symlink()


@pytest.mark.parametrize("pasta", ["Downloads/goal-dados", "Documents", 'dados "com aspas"', "linha\nquebrada"])
def test_recusa_pasta_de_dados_perigosa(casa, pasta):
    (casa.home / "Downloads").mkdir(exist_ok=True)
    (casa.home / "Documents").mkdir(exist_ok=True)
    proc = casa.rodar(
        "--from", str(RAIZ_REPO), "--copiar", "--nao-interativo", "--dados", str(casa.home / pasta), "--offline"
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "pasta de dados" in proc.stderr
    assert not (casa.raiz / "app").exists() and not casa.launchctl()


def test_recusa_skill_que_nao_e_symlink(casa):
    alvo = casa.home / ".claude" / "skills" / "goal-pacer"
    alvo.mkdir(parents=True)
    proc = instalar_copia(casa)
    assert proc.returncode == 3 and "não é um symlink" in proc.stderr
    assert alvo.is_dir() and not alvo.is_symlink()


def test_python_antigo_recusado(casa):
    velho = stub(casa.stubs, "python3-velho", "exit 1")
    proc = casa.rodar("--check", GP_PYTHON3=str(velho))
    assert proc.returncode == 4 and "3.9 ou mais novo" in proc.stderr


def test_provedor_sem_conectores_nao_instala(casa):
    proc = instalar_copia(casa, "--provedor", "openai")
    assert proc.returncode == 3 and "--provedor openai: Calendar e Gmail pelo Codex dependem do spike" in proc.stderr
    assert not (casa.raiz / "app").exists()  # recusa antes de copiar o app


def test_sem_claude_instala_e_avisa(casa):
    """Sem o Claude Code, instala do mesmo jeito: os jobs apontam para onde o instalador oficial põe o claude e o
    --check acusa a falta (exit 3); pelo clique duplo (--instalar-ou-atualizar) a instalação sai com 0."""
    proc = instalar_copia(casa, GP_CLAUDE_BIN=str(casa.home / "nao-existe"))
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "Claude Code: não achei neste computador" in proc.stdout and (casa.raiz / "app").is_dir()
    plist = plistlib.loads((casa.raiz / "jobs" / "com.goal-pacer.diario.plist").read_bytes())
    assert plist["EnvironmentVariables"]["GP_CLAUDE_BIN"] == str(casa.home / ".local" / "bin" / "claude")


def test_check_sozinho(casa):
    proc = casa.rodar("--check", "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Checagem da instalação" in proc.stdout and proc.stdout.count("OK ") == 3


def test_uninstall_preserva_dados_e_apaga_blocos_e_cache(casa):
    assert instalar_copia(casa).returncode == 0
    shutil.rmtree(casa.dados)
    shutil.copytree(FIXTURES / "diario" / "dados", casa.dados)
    (casa.dados / "cache").mkdir(exist_ok=True)
    (casa.dados / "cache" / "calendar-diario-2026-09-27.json").write_text("{}", encoding="utf-8")
    (casa.dados / "sinais").mkdir(exist_ok=True)
    proc = casa.rodar(
        "--uninstall",
        "--nao-interativo",
        "--offline",
        "--apagar-blocos",
        "--apagar-cache",
        GP_OFFLINE_DIR=str(FIXTURES / "diario" / "offline"),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not any((casa.home / "Library" / "LaunchAgents" / ("%s.plist" % label)).exists() for label in LABELS)
    assert not (casa.home / ".claude" / "skills" / "goal-pacer").exists()
    assert sum(1 for linha in casa.launchctl() if linha.startswith("bootout gui/")) >= 4
    assert (
        (casa.dados / "contexto.md").exists()
        and (casa.dados / "metas").is_dir()
        and (casa.dados / "registro.json").exists()
    )
    assert not (casa.dados / "cache").exists() and not (casa.dados / "sinais").exists()
    assert "calendário Metas: 3 bloco(s) apagados" in proc.stdout and "Desinstalado." in proc.stdout
    assert (casa.raiz / "app").is_dir()


def test_uninstall_sem_confirmar_mantem_blocos(casa):
    assert instalar_copia(casa).returncode == 0
    shutil.rmtree(casa.dados)
    shutil.copytree(FIXTURES / "diario" / "dados", casa.dados)
    proc = casa.rodar(
        "--uninstall", "--nao-interativo", "--offline", GP_OFFLINE_DIR=str(FIXTURES / "diario" / "offline")
    )
    assert proc.returncode == 0, proc.stderr
    assert "calendário Metas: blocos mantidos" in proc.stdout
    proc = casa.rodar(
        "--uninstall", "--nao-interativo", "--offline", GP_OFFLINE_DIR=str(FIXTURES / "diario" / "offline")
    )
    assert proc.returncode == 0 and "nenhum job do Goal Pacer carregado" in proc.stdout


def origem_git(tmp: Path) -> Path:
    """Repo git temporário com a árvore de trabalho atual (inclui o que ainda não foi commitado)."""
    sys.path.insert(0, str(RAIZ_REPO / "scripts"))
    import instalar

    origem = tmp / "origem"
    shutil.copytree(str(RAIZ_REPO), str(origem), ignore=instalar.ignorar_copia(RAIZ_REPO))
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@exemplo.test",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@exemplo.test",
    )
    for argv in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "base"]):
        subprocess.run(argv, cwd=str(origem), check=True, capture_output=True, env=env)
    return origem


AUTOR = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@exemplo.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@exemplo.test",
}
PUBLICADOR = "publicador@exemplo.test"


def _acima(passo: int, correcao: int = 0) -> str:
    """Versão ``passo`` degraus de menor acima do ``VERSAO_APP`` do repositório (o teste não envelhece a cada release)."""
    maior, menor, _ = (
        int(parte)
        for parte in re.match(
            r'.*^VERSAO_APP = "([^"]+)"',
            (RAIZ_REPO / "scripts" / "goalpacer" / "base.py").read_text(encoding="utf-8"),
            re.DOTALL | re.MULTILINE,
        )
        .group(1)
        .split(".")
    )
    return "%d.%d.%d" % (maior, menor + passo, correcao)


ATUAL = "%d.%d.%d" % assinatura_do_repo.versao_instalada(RAIZ_REPO)  # com a correção (0.4.1), não só a menor
N1, N2, N2B, N3 = _acima(1), _acima(2), _acima(2, 1), _acima(3)
tem_assinatura_ssh = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="sem ssh-keygen nesta máquina")


def chave_de_release(tmp: Path, nome: str = "chave-release") -> Path:
    """Par de chaves ed25519 sem senha só para o teste; devolve o caminho da chave privada."""
    chave = tmp / nome
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", PUBLICADOR, "-f", str(chave)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    return chave


def lista_de_assinantes(chave: Path) -> str:
    tipo, publica = Path(str(chave) + ".pub").read_text(encoding="utf-8").split()[:2]
    return '%s namespaces="git,goal-pacer-release" %s %s\n' % (PUBLICADOR, tipo, publica)


def origem_assinada(tmp: Path) -> tuple[Path, Path]:
    """Repo de origem com a lista de assinantes do teste já no commit base."""
    chave = chave_de_release(tmp)
    origem = origem_git(tmp)
    commit(origem, "release/assinantes", lista_de_assinantes(chave))
    return origem, chave


def versao_nova(repo: Path, versao: str, chave: Optional[Path], arquivo: str = "", texto: str = "") -> None:
    """Commit com ``VERSAO_APP`` subido (e um arquivo, se dado) e a tag ``v<versao>``: assinada por ``chave`` ou, sem
    chave, anotada sem assinatura."""
    base_py = repo / "scripts" / "goalpacer" / "base.py"
    atual = base_py.read_text(encoding="utf-8")
    base_py.write_text(
        re.sub(r'^VERSAO_APP = "[^"]+"', 'VERSAO_APP = "%s"' % versao, atual, flags=re.MULTILINE),
        encoding="utf-8",
    )
    commit(repo, arquivo or "scripts/goalpacer/base.py", texto if arquivo else base_py.read_text(encoding="utf-8"))
    assinar = ["-c", "gpg.format=ssh", "-c", "user.signingkey=%s" % chave, "tag", "-s"] if chave else ["tag", "-a"]
    subprocess.run(
        ["git", *assinar, "v" + versao, "-m", "versão " + versao],
        cwd=str(repo),
        check=True,
        capture_output=True,
        env=dict(os.environ, **AUTOR),
        timeout=60,
    )


def commit(repo: Path, arquivo: str, texto: str) -> None:
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@exemplo.test",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@exemplo.test",
    )
    (repo / arquivo).parent.mkdir(parents=True, exist_ok=True)
    (repo / arquivo).write_text(texto, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", arquivo], cwd=str(repo), check=True, capture_output=True, env=env)


@tem_assinatura_ssh
def test_update_por_tag_assinada_com_lock_em_dia_e_recusas(casa, tmp_path):
    origem, chave = origem_assinada(tmp_path)
    proc = casa.rodar("--from", str(origem), "--nao-interativo", "--dados", str(casa.dados), "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    app = casa.raiz / "app"
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert (app / ".git").exists() and instalacao["modo"] == "clone" and instalacao["versao"] == ATUAL
    versao_nova(origem, N1, chave, "NOVIDADE.md", "nova versão\n")
    # lock de um job em andamento: update recusa sem mexer em nada
    (casa.dados / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "criado_em": "2026-09-28T10:00:00+00:00"}), encoding="utf-8"
    )
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 4 and "job" in proc.stdout and not (app / "NOVIDADE.md").exists()
    (casa.dados / ".lock").unlink()
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "versão nova: v%s" % N1 in proc.stdout and "Atualizado para a versão %s" % N1 in proc.stdout
    assert (app / "NOVIDADE.md").exists() and "Goal Pacer · doctor" in proc.stdout
    # o fim do update roda com o instalador da versão nova, que regrava a instalação e remonta a janela
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert instalacao["versao"] == N1 and instalacao["painel"] == "local"
    assert "--reaplicar" not in proc.stdout and "janela: " in proc.stdout
    assert not (casa.dados / ".lock").exists()
    # já na mais nova: nada muda e o doctor não roda
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 0 and "Já está na versão mais nova publicada (%s)" % N1 in proc.stdout
    assert "Goal Pacer · doctor" not in proc.stdout
    # commit sem tag não é versão; tag sem assinatura ou de outra chave é recusada
    commit(origem, "SEM-TAG.md", "x\n")
    assert "Já está na versão mais nova" in casa.rodar("--update", "--offline").stdout
    versao_nova(origem, N2, None, "SEM-ASSINATURA.md", "x\n")
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 3 and "Atualização recusada" in proc.stdout and not (app / "SEM-ASSINATURA.md").exists()
    versao_nova(origem, N2B, chave_de_release(tmp_path, "outra-chave"), "OUTRA-CHAVE.md", "x\n")
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 3 and "v" + N2B in proc.stdout and not (app / "OUTRA-CHAVE.md").exists()
    # commit local no app fora da versão nova: o checkout o apagaria, então nada muda
    versao_nova(origem, N3, chave, "OUTRA.md", "outra versão\n")
    commit(app, "LOCAL.md", "mudança local\n")
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 4 and "Nada mudou" in proc.stdout and not (app / "OUTRA.md").exists()


def test_clone_segue_o_remoto_de_onde_veio(casa, tmp_path):
    origem = origem_git(tmp_path)
    subprocess.run(
        ["git", "-C", str(origem), "remote", "add", "origin", "https://github.com/exemplo/goal-pacer.git"],
        check=True,
        capture_output=True,
    )
    proc = casa.rodar("--from", str(origem), "--nao-interativo", "--dados", str(casa.dados), "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    remoto = subprocess.run(
        ["git", "-C", str(casa.raiz / "app"), "remote", "get-url", "origin"], capture_output=True, text=True
    ).stdout.strip()
    assert remoto == "https://github.com/exemplo/goal-pacer.git" and "clone de https://github.com" in proc.stdout


@tem_assinatura_ssh
def test_update_da_copia_so_pelo_zip_assinado(casa, tmp_path):
    origem, chave = origem_assinada(tmp_path)
    proc = casa.rodar("--from", str(origem), "--copiar", "--nao-interativo", "--dados", str(casa.dados), "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    app = casa.raiz / "app"
    versao_nova(origem, N1, chave, "NOVIDADE.md", "nova versão\n")
    zips = tmp_path / "downloads"
    zips.mkdir()
    pacote = zips / ("goal-pacer-v%s.zip" % N1)
    subprocess.run(
        ["git", "archive", "--format=zip", "--prefix=goal-pacer-v%s/" % N1, "-o", str(pacote), "v" + N1],
        cwd=str(origem),
        check=True,
        capture_output=True,
    )
    # sem o .sig ao lado: recusa
    proc = casa.rodar("--update", "--from", str(pacote), "--offline")
    assert proc.returncode == 3 and "goal-pacer-v%s.zip.sig" % N1 in proc.stdout and not (app / "NOVIDADE.md").exists()
    subprocess.run(
        ["ssh-keygen", "-q", "-Y", "sign", "-f", str(chave), "-n", "goal-pacer-release", str(pacote)],
        check=True,
        capture_output=True,
        timeout=60,
    )
    # zip mexido depois da assinatura: recusa
    mexido = zips / "mexido" / pacote.name
    mexido.parent.mkdir()
    mexido.write_bytes(pacote.read_bytes() + b"x")
    shutil.copyfile(str(pacote) + ".sig", str(mexido) + ".sig")
    proc = casa.rodar("--update", "--from", str(mexido), "--offline")
    assert proc.returncode == 3 and "não confere" in proc.stdout and not (app / "NOVIDADE.md").exists()
    proc = casa.rodar("--update", "--from", str(pacote), "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "assinatura de %s conferida" % PUBLICADOR in proc.stdout and (app / "NOVIDADE.md").exists()
    assert os.access(app / "install.sh", os.X_OK) and "Atualizado para a versão %s" % N1 in proc.stdout


def pasta_publicada(origem: Path, versao: str, chave: Path, downloads: Path) -> Path:
    """O zip da versão como o dev/release.py monta (git archive + manifesto assinado), já descompactado."""
    sys.path.insert(0, str(RAIZ_REPO / "dev"))
    import release
    from goalpacer import assinatura

    prefixo = "goal-pacer-v%s/" % versao
    pacote = downloads / ("goal-pacer-v%s.zip" % versao)
    subprocess.run(
        ["git", "archive", "--format=zip", "--prefix=" + prefixo, "-o", str(pacote), "v" + versao],
        cwd=str(origem),
        check=True,
        capture_output=True,
    )
    release.embutir_manifesto(pacote, prefixo, versao, chave, origem)
    destino = downloads / ("descompactado-%s" % versao)
    destino.mkdir()
    return assinatura.extrair_zip(pacote, destino)


def clique_duplo(casa: Casa, pasta: Path) -> subprocess.CompletedProcess:
    """O que o Instalar Goal Pacer.command faz, sem abrir o app: o install.sh da pasta baixada."""
    return subprocess.run(
        [
            "bash",
            str(pasta / "install.sh"),
            "--nao-interativo",
            "--instalar-ou-atualizar",
            "--offline",
            "--dados",
            str(casa.dados),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=casa.env(),
        timeout=600,
    )


@tem_assinatura_ssh
def test_clique_duplo_instala_e_depois_atualiza_pela_pasta_baixada(casa, tmp_path):
    origem, chave = origem_assinada(tmp_path)
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    versao_nova(origem, N1, chave)
    v1 = pasta_publicada(origem, N1, chave, downloads)
    # sem instalação: instala (cópia, a pasta não é clone)
    proc = clique_duplo(casa, v1)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    app = casa.raiz / "app"
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert (
        instalacao["modo"] == "copia" and instalacao["versao"] == N1 and (app / "release" / "manifesto.json").is_file()
    )
    # a mesma pasta outra vez: em dia, só reaplica (agendador, comando, janela)
    proc = clique_duplo(casa, v1)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (
        "Já está na versão mais nova publicada (%s)" % N1 in proc.stdout
        and "Atualizado para a versão %s" % N1 in proc.stdout
    )
    # versão nova baixada: atualiza pela pasta, conferindo o manifesto
    versao_nova(origem, N2, chave, "NOVIDADE.md", "nova versão\n")
    v2 = pasta_publicada(origem, N2, chave, downloads)
    mexida = downloads / "mexida"
    shutil.copytree(str(v2), str(mexida))
    (mexida / "NOVIDADE.md").write_text("trocado depois de assinado\n", encoding="utf-8")
    proc = clique_duplo(casa, mexida)
    assert proc.returncode == 3 and "NOVIDADE.md não confere com o manifesto" in proc.stdout
    assert not (app / "NOVIDADE.md").exists()
    proc = clique_duplo(casa, v2)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "manifesto assinado por %s conferido" % PUBLICADOR in proc.stdout and (app / "NOVIDADE.md").exists()
    assert "Atualizado para a versão %s" % N2 in proc.stdout
    # a pasta antiga não volta a versão
    proc = clique_duplo(casa, v1)
    assert proc.returncode == 0 and "mais antiga que a instalada (%s)" % N2 in proc.stdout
    assert json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))["versao"] == N2
    # árvore de trabalho sem manifesto (não é versão publicada): recusa em vez de copiar sem conferir
    proc = clique_duplo(casa, RAIZ_REPO)
    assert proc.returncode == 3 and "descompacte e clique duas vezes em Instalar Goal Pacer" in proc.stdout


@tem_assinatura_ssh
def test_update_volta_atras_quando_a_versao_nova_nao_roda(casa, tmp_path):
    origem, chave = origem_assinada(tmp_path)
    proc = casa.rodar("--from", str(origem), "--nao-interativo", "--dados", str(casa.dados), "--offline")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    app = casa.raiz / "app"
    antes = subprocess.run(["git", "-C", str(app), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    # R8 (análise de 13/09): as sondagens do spike ficam no repositório, não no app instalado, e o clone segue limpo
    assert not (app / "jobs" / "spike").exists() and (app / "jobs" / "run_job.py").exists()
    assert not (app / "dev").exists() and (app / "scripts" / "goal_pacer.py").exists()
    assert (
        subprocess.run(["git", "-C", str(app), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        == ""
    )
    # instalação endurecida: código só do dono, pastas e instalacao.json privados
    assert all((p.stat().st_mode & 0o022) == 0 for p in [app, app / "scripts", app / "scripts" / "diario.py"])
    assert (casa.raiz / "jobs").stat().st_mode & 0o777 == 0o700 and (
        casa.raiz / "jobs" / "instalacao.json"
    ).stat().st_mode & 0o777 == 0o600
    # versão nova quebrada: o autoteste reprova, o app volta ao commit anterior e os dados ficam com backup
    versao_nova(origem, N1, chave, "scripts/goalpacer/copy.py", "def quebrado(:\n")
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "Atualização desfeita" in proc.stdout and "autoteste" in proc.stdout
    depois = subprocess.run(["git", "-C", str(app), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert depois == antes and "def quebrado" not in (app / "scripts" / "goalpacer" / "copy.py").read_text(
        encoding="utf-8"
    )
    assert (
        len(list((casa.dados / "backups").glob("*-antes-do-update.zip"))) == 1 and not (casa.dados / ".lock").exists()
    )
    # app com mudança fora de commit: update recusa antes de mexer em qualquer coisa
    (app / "README.md").write_text("mexi\n", encoding="utf-8")
    proc = casa.rodar("--update", "--offline")
    assert proc.returncode == 3 and "mudanças fora de commit" in proc.stdout
    assert len(list((casa.dados / "backups").glob("*-antes-do-update.zip"))) == 1


def test_comando_unico_goal_pacer(casa):
    local_bin = casa.home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    proc = instalar_copia(casa, PATH=str(local_bin) + os.pathsep + os.environ.get("PATH", ""))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    shim = casa.raiz / "bin" / "goal-pacer"
    assert (local_bin / "goal-pacer").resolve() == shim.resolve() and "comando: goal-pacer (em" in proc.stdout
    assert not (casa.raiz / "app" / "jobs" / "spike").exists()  # R8: cópia também sem o spike
    assert not (casa.raiz / "app" / "dev").exists()  # nem as ferramentas de desenvolvimento
    assert "depois goal-pacer doctor para conferir tudo" in proc.stdout
    texto = shim.read_text(encoding="utf-8")
    assert (
        texto.startswith("#!/bin/sh\n")
        and '"%s" "%s" "$@"' % (sys.executable, casa.raiz / "app" / "scripts" / "goal_pacer.py") in texto
    )
    ajuda = subprocess.run([str(shim), "ajuda"], capture_output=True, text=True, encoding="utf-8", env=casa.env())
    assert ajuda.returncode == 0 and "autoteste" in ajuda.stdout and "atualizar" in ajuda.stdout
    autoteste = subprocess.run(
        [str(shim), "autoteste", "--json"], capture_output=True, text=True, encoding="utf-8", env=casa.env()
    )
    assert autoteste.returncode == 0 and json.loads(autoteste.stdout)["ok"] is True, autoteste.stdout + autoteste.stderr
    # um goal-pacer de outra origem em ~/.local/bin nunca é sobrescrito
    (local_bin / "goal-pacer").unlink()
    (local_bin / "goal-pacer").write_text("#!/bin/sh\necho outro\n", encoding="utf-8")
    proc = instalar_copia(casa)
    assert (
        proc.returncode == 0
        and "adicione" in proc.stdout
        and (local_bin / "goal-pacer").read_text(encoding="utf-8").endswith("echo outro\n")
    )
    (local_bin / "goal-pacer").unlink()
    assert instalar_copia(casa, PATH=str(local_bin) + os.pathsep + os.environ.get("PATH", "")).returncode == 0
    proc = casa.rodar("--uninstall", "--nao-interativo", "--offline")
    assert (
        proc.returncode == 0
        and not (local_bin / "goal-pacer").exists()
        and not shim.exists()
        and "comando: goal-pacer removido" in proc.stdout
    )


def test_zip_sem_git_instala_por_copia(casa, tmp_path):
    sys.path.insert(0, str(RAIZ_REPO / "scripts"))
    import instalar

    zip_baixado = tmp_path / "goal-pacer-main"
    shutil.copytree(str(RAIZ_REPO), str(zip_baixado), ignore=instalar.ignorar_copia(RAIZ_REPO))
    proc = subprocess.run(
        ["bash", str(zip_baixado / "install.sh"), "--nao-interativo", "--dados", str(casa.dados), "--offline"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=casa.env(),
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "não é um clone git" in proc.stdout and (casa.raiz / "app" / "scripts" / "goal_pacer.py").exists()
    assert json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))["modo"] == "copia"


def test_update_sem_instalacao(casa):
    proc = casa.rodar("--update")
    assert proc.returncode == 2 and "Nenhuma instalação" in proc.stdout


def test_migrar(tmp_path):
    dados = tmp_path / "dados"
    shutil.copytree(FIXTURES / "diario" / "dados", dados)
    script = RAIZ_REPO / "scripts" / "migrar.py"
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    proc = subprocess.run(
        [sys.executable, str(script), "--dados", str(dados), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 0 and json.loads(proc.stdout)["ok"] is True
    contexto = dados / "contexto.md"
    contexto.write_text(
        contexto.read_text(encoding="utf-8").replace("schema_version: 1", "schema_version: 2"), encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(script), "--dados", str(dados)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 3 and "versões misturadas" in proc.stderr and "contexto.md v2" in proc.stderr
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    proc = subprocess.run(
        [sys.executable, str(script), "--dados", str(vazio)], capture_output=True, text=True, encoding="utf-8", env=env
    )
    assert proc.returncode == 0


def test_painel_sempre_no_ar_local_na_rede_ou_desligado(casa):
    agente = casa.home / "Library" / "LaunchAgents" / "com.goal-pacer.painel.plist"
    web_py = str(casa.raiz / "app" / "scripts" / "web.py")
    proc = instalar_copia(casa)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    conteudo = plistlib.loads(agente.read_bytes())
    assert conteudo["ProgramArguments"] == [sys.executable, web_py, "--local"]
    assert conteudo["KeepAlive"] is True and conteudo["RunAtLoad"] is True
    assert conteudo["EnvironmentVariables"]["GP_DATA_DIR"] == str(casa.dados)
    assert any(l.startswith("bootstrap gui/") and l.endswith(str(agente)) for l in casa.launchctl())
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert instalacao["painel"] == "local" and instalacao["painel_rede"] is False
    assert "com.goal-pacer.painel" in instalacao["labels"] and "painel: no ar em http://127.0.0.1:8765/" in proc.stdout
    proc = instalar_copia(casa, "--painel-rede")
    assert proc.returncode == 0 and plistlib.loads(agente.read_bytes())["ProgramArguments"][-1] == "--rede"
    assert "painel: no ar" in proc.stdout
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert instalacao["painel"] == "rede" and instalacao["painel_rede"] is True
    (casa.raiz / "jobs" / "painel-aparelhos.json").write_text('{"aparelhos": []}', encoding="utf-8")
    proc = instalar_copia(casa, "--sem-painel")
    assert proc.returncode == 0 and not agente.exists() and "agente do login desligado" in proc.stdout
    assert json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))["painel"] == ""
    assert instalar_copia(casa, "--painel-rede", "--sem-painel").returncode != 0  # uma escolha só
    assert instalar_copia(casa).returncode == 0 and agente.exists()
    proc = casa.rodar("--uninstall", "--nao-interativo", "--offline")
    assert proc.returncode == 0 and not agente.exists() and not (casa.raiz / "jobs" / "painel-aparelhos.json").exists()


def test_janela_nativa_no_mac_montada_na_instalacao_e_removida_no_uninstall(casa):
    app_janela = casa.home / "Applications" / "Goal Pacer.app"
    proc = instalar_copia(casa)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    plist = plistlib.loads((app_janela / "Contents" / "Info.plist").read_bytes())
    assert plist["GPEndereco"] == "http://127.0.0.1:8765/" and plist["GPLabelPainel"] == "com.goal-pacer.painel"
    assert "janela: %s" % app_janela in proc.stdout
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert instalacao["janela"] == str(app_janela) and instalacao["sem_janela"] is False
    proc = casa.rodar("--uninstall", "--nao-interativo", "--offline")
    assert proc.returncode == 0 and not app_janela.exists() and "janela: %s removido" % app_janela in proc.stdout
    proc = instalar_copia(casa, "--sem-janela")
    assert proc.returncode == 0 and not app_janela.exists()
    instalacao = json.loads((casa.raiz / "jobs" / "instalacao.json").read_text(encoding="utf-8"))
    assert instalacao["janela"] == "" and instalacao["sem_janela"] is True
    # sem o compilador Swift: só avisa, e a instalação segue com o painel no navegador
    (casa.stubs / "xcrun").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    proc = instalar_copia(casa)
    assert proc.returncode == 0 and "falta o compilador Swift" in proc.stdout and not app_janela.exists()
