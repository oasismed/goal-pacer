"""dev/release.py: ensaio com chave e repositório de teste (tag assinada, zip e .sig conferidos, tag desfeita), as
recusas antes de criar qualquer coisa e o que o --publicar manda para o GitHub."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from goalpacer import assinatura

RAIZ_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release", RAIZ_REPO / "dev" / "release.py")
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="sem ssh-keygen nesta máquina")
AUTOR = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@exemplo.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@exemplo.test",
}


@pytest.fixture(autouse=True)
def identidade_do_git(monkeypatch):
    """A tag anotada precisa de quem a cria; runner de CI e contêiner não têm ``user.email``."""
    for nome, valor in AUTOR.items():
        monkeypatch.setenv(nome, valor)


def _git(repo: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=str(repo), check=True, capture_output=True, text=True, env=dict(os.environ, **AUTOR)
    ).stdout


def _repo(tmp_path: Path, versao: str = "0.2.0") -> tuple[Path, Path]:
    chave = tmp_path / "chave"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "p@t", "-f", str(chave)], check=True)
    repo = tmp_path / "repo"
    (repo / "scripts" / "goalpacer").mkdir(parents=True)
    (repo / "release").mkdir()
    (repo / "scripts" / "goalpacer" / "base.py").write_text('VERSAO_APP = "%s"\n' % versao, encoding="utf-8")
    (repo / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "install.sh").chmod(0o755)
    (repo / "CHANGELOG.md").write_text(
        "# Mudanças\n\n## 0.2.0 (13/09/2026)\n\n- primeira\n\n## 0.1.0\n\n- velha\n", "utf-8"
    )
    tipo, publica = (tmp_path / "chave.pub").read_text(encoding="utf-8").split()[:2]
    (repo / "release" / "assinantes").write_text(
        'p@t namespaces="git,goal-pacer-release" %s %s\n' % (tipo, publica), "utf-8"
    )
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo, chave


def test_ensaio_assina_confere_e_desfaz_a_tag(tmp_path, capsys):
    repo, chave = _repo(tmp_path)
    dist = tmp_path / "dist"
    assert release.main(["--versao", "0.2.0", "--chave", str(chave), "--repo", str(repo), "--dist", str(dist)]) == 0
    pacote = dist / "goal-pacer-v0.2.0.zip"
    assert "ensaio conferido e desfeito" in capsys.readouterr().out and _git(repo, "tag", "--list").strip() == ""
    assert assinatura.verificar_arquivo(pacote, repo / "release" / "assinantes") == "p@t"
    extraido = tmp_path / "extraido"
    extraido.mkdir()
    pasta = assinatura.extrair_zip(pacote, extraido)
    assert pasta.name == "goal-pacer-v0.2.0"
    # a pasta descompactada é uma versão conferível sozinha: manifesto assinado com o sha256 de cada arquivo
    versao, quem = assinatura.copiar_versao(pasta, tmp_path / "copia", repo / "release" / "assinantes")
    assert (versao, quem) == ((0, 2, 0), "p@t")
    manifesto = json.loads((pasta / "release" / "manifesto.json").read_text(encoding="utf-8"))
    assert "install.sh" in manifesto["arquivos"]
    assert manifesto["arquivos"]["install.sh"]["executavel"] is (os.name != "nt")  # o git do Windows não guarda o bit
    assert "release/manifesto.json" not in manifesto["arquivos"]
    ultima = dist / "ultima.json"
    assert json.loads(ultima.read_text(encoding="utf-8")) == {"versao": "0.2.0", "zip": "goal-pacer-v0.2.0.zip"}
    assert assinatura.verificar_arquivo(ultima, repo / "release" / "assinantes") == "p@t"  # o canal confere assim


def test_secao_do_changelog():
    texto = "# M\n\n## 0.2.0 (x)\n\n- a\n- b\n\n## 0.1.0\n\n- c\n"
    assert release.secao_do_changelog(texto, "0.2.0") == "- a\n- b"
    assert release.secao_do_changelog(texto, "0.1.0") == "- c"
    assert release.secao_do_changelog(texto, "0.1") is None


@pytest.mark.parametrize(
    ("mexer", "versao", "trecho"),
    [
        (None, "0.3.0", "VERSAO_APP = 0.2.0"),
        (None, "0.2", "fora do formato"),
        ("changelog", "0.2.0", "sem a seção ## 0.2.0"),
        ("sujo", "0.2.0", "fora de commit"),
        ("tag", "0.2.0", "já existe"),
        ("outra_chave", "0.2.0", "não está em"),
    ],
)
def test_recusa_antes_de_criar_qualquer_coisa(tmp_path, capsys, mexer, versao, trecho):
    repo, chave = _repo(tmp_path)
    if mexer == "changelog":
        (repo / "CHANGELOG.md").write_text("# Mudanças\n", encoding="utf-8")
        _git(repo, "commit", "-qam", "sem seção")
    elif mexer == "sujo":
        (repo / "install.sh").write_text("#!/bin/sh\necho mexi\n", encoding="utf-8")
    elif mexer == "tag":
        _git(repo, "tag", "v0.2.0")
    elif mexer == "outra_chave":
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(tmp_path / "outra")], check=True)
        chave = tmp_path / "outra"
    codigo = release.main(
        ["--versao", versao, "--chave", str(chave), "--repo", str(repo), "--dist", str(tmp_path / "d")]
    )
    assert codigo == 3 and trecho in capsys.readouterr().err
    assert not (tmp_path / "d").exists()


def test_publicar_empurra_a_tag_e_cria_a_release_com_zip_sig_e_notas(tmp_path, monkeypatch):
    chamadas: list = []

    def rodar(argv, repo):
        chamadas.append(list(argv))
        if argv[:2] == ["gh", "release"]:
            notas = argv[argv.index("--notes-file") + 1]
            chamadas.append(Path(notas).read_text(encoding="utf-8"))
        return "https://github.com/exemplo/goal-pacer/releases/tag/v0.2.0\n"

    monkeypatch.setattr(release, "_rodar", rodar)
    pacote = tmp_path / "goal-pacer-v0.2.0.zip"
    url = release.publicar(tmp_path, "0.2.0", pacote, "- primeira")
    assert url.endswith("/v0.2.0") and chamadas[0] == ["git", "push", "origin", "v0.2.0"]
    gh = chamadas[1]
    assert gh[:4] == ["gh", "release", "create", "v0.2.0"] and "--verify-tag" in gh
    assert str(pacote) in gh and str(pacote) + ".sig" in gh and chamadas[2] == "- primeira\n"


def test_canal_padrao_e_a_ultima_versao_publicada_no_github():
    from goalpacer import canal

    raiz = Path(__file__).resolve().parent.parent
    assert canal.endereco(raiz) == "https://github.com/%s/releases/latest/download/" % release.REPO_GITHUB
