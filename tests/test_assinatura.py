"""goalpacer.assinatura: versões, lista de assinantes, git que confere SSH e extração do zip da versão sem sair da pasta.

O caminho feliz com chave e tag de verdade está em ``tests/test_install.py`` (update por tag e por zip assinados).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Optional

import pytest

from goalpacer import assinatura
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro


def test_versao_e_maior_tag_nova_por_numero_e_nao_por_texto():
    assert assinatura.versao_de("0.10.2") == (0, 10, 2) == assinatura.versao_de("v0.10.2")
    assert assinatura.versao_de("v1.2") is None and assinatura.versao_de("v1.2.3-rc1") is None
    tags = ["v0.9.0", "v0.10.0", "lixo", "v0.10.0-rc1", "", "v0.2.0"]
    assert assinatura.maior_tag_nova(tags, (0, 2, 0)) == "v0.10.0"
    assert assinatura.maior_tag_nova(tags, (0, 10, 0)) is None
    assert assinatura.maior_tag_nova([], (0, 0, 0)) is None


def test_versao_instalada_le_o_codigo_do_app_sem_importar(tmp_path):
    app = tmp_path / "app"
    assert assinatura.versao_instalada(app) == (0, 0, 0)  # instalação anterior às versões
    base_py = app / "scripts" / "goalpacer" / "base.py"
    base_py.parent.mkdir(parents=True)
    base_py.write_text('"""doc"""\nEXIT_OK = 0\n', encoding="utf-8")
    assert assinatura.versao_instalada(app) == (0, 0, 0)
    base_py.write_text('EXIT_OK = 0\nVERSAO_APP = "1.4.12"  # comentário\n', encoding="utf-8")
    assert assinatura.versao_instalada(app) == (1, 4, 12)


def test_sem_lista_de_assinantes_nao_ha_update(tmp_path):
    with pytest.raises(GpErro) as exc:
        assinatura.copiar_assinantes(tmp_path / "app", tmp_path)
    assert exc.value.codigo == EXIT_VALIDACAO and "release/assinantes" in exc.value.mensagem
    lista = tmp_path / "app" / "release" / "assinantes"
    lista.parent.mkdir(parents=True)
    lista.write_text("# vazia\n", encoding="utf-8")
    fora = tmp_path / "fora"
    fora.mkdir()
    assert assinatura.copiar_assinantes(tmp_path / "app", fora).read_text(encoding="utf-8") == "# vazia\n"


def _git_falso(pasta: Path, saida: str, codigo: int = 0) -> str:
    git = pasta / "git"
    git.write_text("#!/bin/sh\necho '%s'\nexit %d\n" % (saida, codigo), encoding="utf-8")
    git.chmod(0o755)
    return str(git)


@pytest.mark.posix
def test_git_antigo_ou_ausente_recusa_em_vez_de_pular_a_assinatura(tmp_path):
    with pytest.raises(GpErro, match=r"2\.34"):
        assinatura.conferir_git(_git_falso(tmp_path, "git version 2.30.1"))
    with pytest.raises(GpErro):
        assinatura.conferir_git(str(tmp_path / "nao-existe"))
    assinatura.conferir_git(_git_falso(tmp_path, "git version 2.51.1"))


def test_verify_tag_que_falha_vira_recusa_com_a_tag(tmp_path, monkeypatch):
    respostas = iter([(0, "git version 2.51.1"), (1, "error: no signature found")])
    monkeypatch.setattr(assinatura, "_rodar", lambda *_a, **_k: next(respostas))
    with pytest.raises(GpErro) as exc:
        assinatura.verificar_tag("git", tmp_path, "v0.2.0", tmp_path / "lista")
    assert exc.value.codigo == EXIT_VALIDACAO
    assert (
        exc.value.mensagem == "a tag v0.2.0 não tem assinatura de quem publica o Goal Pacer (error: no signature found)"
    )


def test_arquivo_sem_sig_ou_de_quem_nao_esta_na_lista(tmp_path, monkeypatch):
    pacote = tmp_path / "goal-pacer-v0.2.0.zip"
    pacote.write_bytes(b"zip")
    lista = tmp_path / "lista"
    lista.write_text("# só comentário\n", encoding="utf-8")
    with pytest.raises(GpErro, match=r"falta goal-pacer-v0\.2\.0\.zip\.sig"):
        assinatura.verificar_arquivo(pacote, lista)
    Path(str(pacote) + ".sig").write_text("assinatura", encoding="utf-8")
    with pytest.raises(GpErro, match=r"não foi assinado por quem publica.*lista sem assinantes"):
        assinatura.verificar_arquivo(pacote, lista)
    lista.write_text(
        'a@x.test ssh-ed25519 AAAA\n"b@x.test,*@y.test" namespaces="git" ssh-ed25519 BBBB\n', encoding="utf-8"
    )
    tentados = []

    def rodar(argv, **_k):
        tentados.append(argv[argv.index("-I") + 1])
        return (0, "Good") if tentados[-1] == "b@x.test" else (255, "Signature verification failed")

    monkeypatch.setattr(assinatura, "_rodar", rodar)
    assert assinatura.verificar_arquivo(pacote, lista) == "b@x.test" and tentados == ["a@x.test", "b@x.test"]
    monkeypatch.setattr(assinatura, "_rodar", lambda *_a, **_k: (255, "Signature verification failed"))
    with pytest.raises(GpErro, match="não confere: Signature verification failed"):
        assinatura.verificar_arquivo(pacote, lista)
    monkeypatch.setattr(assinatura, "_rodar", lambda *_a, **_k: (127, "No such file"))
    with pytest.raises(GpErro, match="Cliente OpenSSH"):
        assinatura.verificar_arquivo(pacote, lista)


def test_principais_da_lista(tmp_path):
    lista = tmp_path / "assinantes"
    lista.write_text(
        "# comentário\n\n"
        'chico@x.test namespaces="git,goal-pacer-release" ssh-ed25519 AAAA\n'
        '"a@x.test, *@curinga.test,!negado@x.test" ssh-ed25519 BBBB\n'
        "chico@x.test ssh-ed25519 CCCC\n",
        encoding="utf-8",
    )
    assert assinatura.principais(lista) == ["chico@x.test", "a@x.test"]
    assert assinatura.principais(tmp_path / "nao-existe") == []


tem_ssh_keygen = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="sem ssh-keygen nesta máquina")


def _chave(tmp_path: Path) -> tuple[Path, Path]:
    chave = tmp_path / "chave"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True, capture_output=True)
    tipo, publica = Path(str(chave) + ".pub").read_text(encoding="utf-8").split()[:2]
    lista = tmp_path / "assinantes"
    lista.write_text('p@x.test namespaces="goal-pacer-release" %s %s\n' % (tipo, publica), encoding="utf-8")
    return chave, lista


def _publicar(pasta: Path, chave: Path, versao: str, arquivos: dict[str, bytes], executaveis=()) -> None:
    for nome, dados in arquivos.items():
        (pasta / nome).parent.mkdir(parents=True, exist_ok=True)
        (pasta / nome).write_bytes(dados)
    manifesto = pasta / assinatura.ARQUIVO_MANIFESTO
    manifesto.parent.mkdir(parents=True, exist_ok=True)
    manifesto.write_bytes(assinatura.manifesto(versao, arquivos, executaveis))
    subprocess.run(
        ["ssh-keygen", "-q", "-Y", "sign", "-f", str(chave), "-n", assinatura.ESPACO_ZIP, str(manifesto)],
        check=True,
        capture_output=True,
    )


@tem_ssh_keygen
def test_pasta_da_versao_conferida_pelo_manifesto(tmp_path):
    chave, lista = _chave(tmp_path)
    pasta = tmp_path / "goal-pacer-v1.2.3"
    arquivos = {"install.sh": b"#!/bin/sh\n", "scripts/a.py": b"print(1)\n"}
    _publicar(pasta, chave, "1.2.3", arquivos, ["install.sh"])
    (pasta / "__pycache__").mkdir()
    (pasta / "__pycache__" / "lixo.pyc").write_bytes(b"x")  # o instalador rodou da pasta: fora do manifesto, fica fora
    assert assinatura.versao_do_manifesto(pasta) == (1, 2, 3) and assinatura.versao_do_manifesto(tmp_path) is None
    versao, quem = assinatura.copiar_versao(pasta, tmp_path / "copia", lista)
    copia = tmp_path / "copia"
    assert (versao, quem) == ((1, 2, 3), "p@x.test")
    assert (copia / "scripts" / "a.py").read_bytes() == b"print(1)\n" and not (copia / "__pycache__").exists()
    assert (
        (copia / assinatura.ARQUIVO_MANIFESTO).is_file() and os.access(copia / "install.sh", os.X_OK)
    ) or os.name == "nt"

    (pasta / "scripts" / "a.py").write_bytes(b"print(2)\n")
    with pytest.raises(GpErro, match=r"scripts/a\.py não confere com o manifesto"):
        assinatura.copiar_versao(pasta, tmp_path / "copia2", lista)
    (pasta / "scripts" / "a.py").unlink()
    with pytest.raises(GpErro, match=r"falta scripts/a\.py"):
        assinatura.copiar_versao(pasta, tmp_path / "copia3", lista)
    (pasta / assinatura.ARQUIVO_MANIFESTO).write_bytes(assinatura.manifesto("9.9.9", arquivos, []))
    with pytest.raises(GpErro, match="não confere"):
        assinatura.copiar_versao(pasta, tmp_path / "copia4", lista)  # manifesto trocado depois de assinado
    Path(str(pasta / assinatura.ARQUIVO_MANIFESTO) + ".sig").unlink()
    with pytest.raises(GpErro, match="página de versões"):
        assinatura.copiar_versao(pasta, tmp_path / "copia5", lista)


@tem_ssh_keygen
@pytest.mark.parametrize(
    ("manifesto", "trecho"),
    [
        (b"nao e json", "ilegível"),
        (b'{"formato": 2, "versao": "1.0.0", "arquivos": {"a": {}}}', "fora do formato"),
        (b'{"formato": 1, "versao": "1.0.0", "arquivos": {"../fora": {"bytes": 1}}}', "caminho fora da pasta"),
        (b'{"formato": 1, "versao": "1.0.0", "arquivos": {"/abs": {"bytes": 1}}}', "caminho fora da pasta"),
        (b'{"formato": 1, "versao": "1.0.0", "arquivos": {"C:/x": {"bytes": 1}}}', "caminho fora da pasta"),
        (b'{"formato": 1, "versao": "1.0.0", "arquivos": {"a\\\\b": {"bytes": 1}}}', "caminho fora da pasta"),
        (b'{"formato": 1, "versao": "1.0.0", "arquivos": {"a": {"bytes": 999999999999}}}', "passa de"),
    ],
)
def test_manifesto_assinado_mas_torto(tmp_path, manifesto, trecho):
    chave, lista = _chave(tmp_path)
    pasta = tmp_path / "v"
    (pasta / "release").mkdir(parents=True)
    alvo = pasta / assinatura.ARQUIVO_MANIFESTO
    alvo.write_bytes(manifesto)
    subprocess.run(
        ["ssh-keygen", "-q", "-Y", "sign", "-f", str(chave), "-n", "goal-pacer-release", str(alvo)],
        check=True,
        capture_output=True,
    )
    with pytest.raises(GpErro, match=trecho):
        assinatura.copiar_versao(pasta, tmp_path / "copia", lista)


def _zip(caminho: Path, membros: dict[str, bytes], *, modos: Optional[dict[str, int]] = None) -> Path:
    with zipfile.ZipFile(str(caminho), "w") as pacote:
        for nome, conteudo in membros.items():
            info = zipfile.ZipInfo(nome)
            info.external_attr = (modos or {}).get(nome, 0o100644) << 16
            pacote.writestr(info, conteudo)
    return caminho


@pytest.mark.posix
def test_extrair_zip_da_versao_guarda_o_bit_de_execucao(tmp_path):
    pacote = _zip(
        tmp_path / "v.zip",
        {"goal-pacer-v0.2.0/install.sh": b"#!/bin/sh\n", "goal-pacer-v0.2.0/README.md": b"oi\n"},
        modos={"goal-pacer-v0.2.0/install.sh": 0o100755},
    )
    destino = tmp_path / "extraido"
    destino.mkdir()
    pasta = assinatura.extrair_zip(pacote, destino)
    assert pasta.name == "goal-pacer-v0.2.0" and (pasta / "install.sh").stat().st_mode & stat.S_IXUSR
    assert not (pasta / "README.md").stat().st_mode & stat.S_IXUSR


@pytest.mark.parametrize(
    ("membros", "modos", "trecho"),
    [
        ({"../fora.txt": b"x"}, None, "fora da pasta"),
        ({"/etc/goal-pacer": b"x"}, None, "fora da pasta"),
        ({"goal-pacer/link": b"/etc/passwd"}, {"goal-pacer/link": 0o120777}, "fora da pasta"),
        ({"goal-pacer/README.md": b"x"}, None, "install.sh"),
        ({"a/install.sh": b"x", "b/install.sh": b"x"}, None, "install.sh"),
    ],
)
def test_extrair_zip_recusa_o_que_sairia_da_pasta_ou_nao_e_o_app(tmp_path, membros, modos, trecho):
    destino = tmp_path / "extraido"
    destino.mkdir()
    with pytest.raises(GpErro, match=trecho) as exc:
        assinatura.extrair_zip(_zip(tmp_path / "v.zip", membros, modos=modos), destino)
    assert exc.value.codigo == EXIT_VALIDACAO


def test_extrair_zip_invalido_grande_ou_sem_disco(tmp_path, monkeypatch):
    destino = tmp_path / "extraido"
    destino.mkdir()
    lixo = tmp_path / "lixo.zip"
    lixo.write_bytes(b"nao sou zip")
    with pytest.raises(GpErro, match="não é um zip válido"):
        assinatura.extrair_zip(lixo, destino)
    monkeypatch.setattr(assinatura, "LIMITE_ZIP_BYTES", 3)
    with pytest.raises(GpErro, match="passa de"):
        assinatura.extrair_zip(_zip(tmp_path / "grande.zip", {"g/install.sh": b"#!/bin/sh\n"}), destino)
    monkeypatch.undo()

    def sem_disco(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", sem_disco)
    with pytest.raises(GpErro) as exc:
        assinatura.extrair_zip(_zip(tmp_path / "ok.zip", {"g/install.sh": b"#!/bin/sh\n"}), destino)
    assert exc.value.codigo == EXIT_IO
