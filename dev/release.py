#!/usr/bin/env python3
"""release.py: publica uma versão do Goal Pacer (tag assinada, zip e assinatura do zip), na máquina de quem mantém.

    python3 dev/release.py --versao 0.1.0 --chave ~/.ssh/id_ed25519_2026              # ensaio: faz, confere e desfaz a tag
    python3 dev/release.py --versao 0.1.0 --chave ~/.ssh/id_ed25519_2026 --publicar   # faz, confere e publica

Confere antes de tocar em qualquer coisa: a versão pedida é o ``VERSAO_APP`` do código, o ``CHANGELOG.md`` tem a seção
da versão, a árvore está sem mudança fora de commit, a tag ainda não existe e a chave está em ``release/assinantes``.
Depois cria a tag anotada e assinada ``v<versão>``, confere a assinatura com a mesma lista que o ``--update`` usa,
gera ``dist/goal-pacer-v<versão>.zip`` pelo ``git archive`` da tag, acrescenta ``release/manifesto.json`` (sha256 de cada
arquivo) e a assinatura dele, assina o zip (``.sig``, espaço ``goal-pacer-release``) e confere os dois: o ``.sig`` do zip
e, na pasta descompactada, o manifesto (o que o clique duplo no instalador da versão nova confere). Sem ``--publicar`` é ensaio: a tag local sai no fim e o zip fica em ``dist/`` para olhar. Com
``--publicar``: ``git push`` da tag e ``gh release create`` com o zip, o ``.sig`` e a seção
do changelog como notas. Qualquer falha depois da tag criada apaga a tag local; nada vai para o GitHub sem conferir.
A chave privada nunca sai da máquina: só o ``ssh-keygen`` e o ``git`` a leem.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "dev"))

from goalpacer import assinatura  # noqa: E402
from goalpacer.base import GpErro  # noqa: E402

TIMEOUT_S = 600


class Recusa(Exception):
    """Pré-condição da versão que não passou; nada foi criado."""


def _rodar(argv: list[str], repo: Path) -> str:
    proc = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise Recusa("%s: %s" % (" ".join(argv[:3]), (proc.stderr or proc.stdout).strip()[-400:]))
    return proc.stdout


def secao_do_changelog(texto: str, versao: str) -> Optional[str]:
    """O corpo de ``## <versão>`` até o próximo ``## `` (sem o título), ou None."""
    m = re.search(r"^## %s(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)" % re.escape(versao), texto, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


def conferir(repo: Path, versao: str, chave: Path) -> str:
    """Pré-condições; devolve as notas da versão."""
    if assinatura.versao_de(versao) is None:
        raise Recusa("versão %r fora do formato X.Y.Z" % versao)
    no_codigo = "%d.%d.%d" % assinatura.versao_instalada(repo)
    if no_codigo != versao:
        raise Recusa(
            "o código diz VERSAO_APP = %s; suba scripts/goalpacer/base.py antes de publicar %s" % (no_codigo, versao)
        )
    changelog = repo / "CHANGELOG.md"
    notas = secao_do_changelog(changelog.read_text(encoding="utf-8"), versao) if changelog.is_file() else None
    if not notas:
        raise Recusa("CHANGELOG.md sem a seção ## %s" % versao)
    if _rodar(["git", "status", "--porcelain"], repo).strip():
        raise Recusa("há mudança fora de commit; a versão sai só do que está commitado")
    if _rodar(["git", "tag", "--list", "v" + versao], repo).strip():
        raise Recusa("a tag v%s já existe" % versao)
    publica = Path(str(chave) + ".pub")
    if not chave.is_file() or not publica.is_file():
        raise Recusa("chave %s (e o .pub ao lado) não encontrada" % chave)
    corpo = publica.read_text(encoding="utf-8").split()[1]
    if corpo not in (repo / assinatura.ARQUIVO_ASSINANTES).read_text(encoding="utf-8"):
        raise Recusa("a chave %s não está em %s" % (publica, assinatura.ARQUIVO_ASSINANTES))
    return notas


def preparar(repo: Path, versao: str, chave: Path, dist: Path) -> Path:
    """Tag assinada e conferida, zip e .sig conferidos; devolve o zip. Falhou depois da tag: a tag local sai."""
    tag = "v" + versao
    _rodar(
        [
            "git",
            "-c",
            "gpg.format=ssh",
            "-c",
            "user.signingkey=%s" % chave,
            "tag",
            "-s",
            tag,
            "-m",
            "Goal Pacer " + versao,
        ],
        repo,
    )
    try:
        assinatura.verificar_tag("git", repo, tag, repo / assinatura.ARQUIVO_ASSINANTES)
        dist.mkdir(parents=True, exist_ok=True)
        pacote = dist / ("goal-pacer-%s.zip" % tag)
        for velho in (pacote, Path(str(pacote) + ".sig")):
            velho.unlink(missing_ok=True)
        prefixo = "goal-pacer-%s/" % tag
        _rodar(["git", "archive", "--format=zip", "--prefix=" + prefixo, "-o", str(pacote), tag], repo)
        embutir_manifesto(pacote, prefixo, versao, chave, repo)
        _assinar(pacote, chave, repo)
        assinatura.verificar_arquivo(pacote, repo / assinatura.ARQUIVO_ASSINANTES)
        conferir_pasta(pacote, repo / assinatura.ARQUIVO_ASSINANTES)
    except (Recusa, GpErro):
        subprocess.run(["git", "tag", "-d", tag], cwd=str(repo), capture_output=True, timeout=60, check=False)
        raise
    return pacote


def _assinar(arquivo: Path, chave: Path, repo: Path) -> Path:
    ssh_keygen = shutil.which("ssh-keygen") or "ssh-keygen"
    _rodar([ssh_keygen, "-q", "-Y", "sign", "-f", str(chave), "-n", assinatura.ESPACO_ZIP, str(arquivo)], repo)
    return Path(str(arquivo) + ".sig")


def embutir_manifesto(pacote: Path, prefixo: str, versao: str, chave: Path, repo: Path) -> None:
    """``release/manifesto.json`` (sha256 e bit de execução de cada arquivo do ``git archive``) e a assinatura dele,
    acrescentados ao zip com a data dos outros membros."""
    with zipfile.ZipFile(str(pacote)) as zip_lido:
        membros = [m for m in zip_lido.infolist() if not m.is_dir()]
        arquivos = {m.filename[len(prefixo) :]: zip_lido.read(m) for m in membros}
        executaveis = [m.filename[len(prefixo) :] for m in membros if (m.external_attr >> 16) & 0o111]
        data = membros[0].date_time
    corpo = assinatura.manifesto(versao, arquivos, executaveis)
    with tempfile.TemporaryDirectory(prefix="goal-pacer-manifesto-") as pasta:
        manifesto = Path(pasta) / "manifesto.json"
        manifesto.write_bytes(corpo)
        selo = _assinar(manifesto, chave, repo).read_bytes()
    with zipfile.ZipFile(str(pacote), "a", compression=zipfile.ZIP_DEFLATED) as zip_escrito:
        for nome, dados in (
            (assinatura.ARQUIVO_MANIFESTO.as_posix(), corpo),
            (assinatura.ARQUIVO_MANIFESTO.as_posix() + ".sig", selo),
        ):
            info = zipfile.ZipInfo(prefixo + nome, date_time=data)
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_escrito.writestr(info, dados)


def conferir_pasta(pacote: Path, assinantes: Path) -> None:
    """Descompacta o zip e confere a pasta como o instalador da versão nova confere (manifesto e sha256)."""
    with tempfile.TemporaryDirectory(prefix="goal-pacer-conferir-") as pasta:
        (Path(pasta) / "zip").mkdir()
        extraida = assinatura.extrair_zip(pacote, Path(pasta) / "zip")
        assinatura.copiar_versao(extraida, Path(pasta) / "copia", assinantes)


def escrever_ultima(dist: Path, versao: str, chave: Path, repo: Path, instaladores: list[Path]) -> list[Path]:
    """``ultima.json`` (e o ``.sig``) para o canal de versões (goalpacer/canal.py): a versão, o zip e os instaladores."""
    dados = {"versao": versao, "zip": "goal-pacer-v%s.zip" % versao}
    for arquivo in instaladores:
        dados["mac" if arquivo.suffix == ".dmg" else "windows"] = arquivo.name
    ultima = dist / "ultima.json"
    for velho in (ultima, Path(str(ultima) + ".sig")):
        velho.unlink(missing_ok=True)
    ultima.write_text(json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return [ultima, _assinar(ultima, chave, repo)]


def construir_instaladores(pacote: Path, dist: Path) -> list[Path]:
    """O .dmg e o Setup.exe da versão, a partir do zip já conferido (dev/empacotar.py)."""
    import empacotar

    with tempfile.TemporaryDirectory(prefix="goal-pacer-instaladores-") as pasta:
        extraida = empacotar.pasta_da_versao(pacote, Path(pasta))
        cache = Path.home() / ".cache" / "goal-pacer-empacotar"
        try:
            return [empacotar.construir_dmg(extraida, dist, cache), empacotar.construir_setup(extraida, dist, cache)]
        except empacotar.Falha as erro:
            raise Recusa("instaladores: %s" % erro) from erro


REPO_GITHUB = "oasismed/goal-pacer"  # público: release/canal lê a última versão daqui, sem login


def publicar(repo: Path, versao: str, pacote: Path, notas: str, extras: Optional[list[Path]] = None) -> str:
    tag = "v" + versao
    _rodar(["git", "push", "origin", tag], repo)
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as arquivo:
        arquivo.write(notas + "\n")
    try:
        saida = _rodar(
            [
                "gh",
                "release",
                "create",
                tag,
                str(pacote),
                str(pacote) + ".sig",
                *(str(p) for p in extras or []),
                "--verify-tag",
                "--title",
                "Goal Pacer " + versao,
                "--notes-file",
                arquivo.name,
            ],
            repo,
        )
    finally:
        Path(arquivo.name).unlink(missing_ok=True)
    return saida.strip()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Tag assinada, zip e assinatura de uma versão do Goal Pacer.")
    parser.add_argument("--versao", required=True, help="X.Y.Z, igual ao VERSAO_APP do código")
    parser.add_argument("--chave", required=True, type=Path, help="chave SSH privada de release/assinantes")
    parser.add_argument("--publicar", action="store_true", help="git push da tag e gh release create")
    parser.add_argument("--repo", type=Path, default=RAIZ, help=argparse.SUPPRESS)
    parser.add_argument("--dist", type=Path, default=None, help="pasta do zip (padrão: dist/ no repo)")
    parser.add_argument(
        "--instaladores", action="store_true", help="também o .dmg (Mac) e o Setup.exe (Windows), por dev/empacotar.py"
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    chave = args.chave.expanduser()
    try:
        notas = conferir(repo, args.versao, chave)
        dist = args.dist or repo / "dist"
        pacote = preparar(repo, args.versao, chave, dist)
        print("tag v%s assinada e conferida" % args.versao)
        print("zip: %s (+ .sig conferido)" % pacote)
        instaladores = construir_instaladores(pacote, dist) if args.instaladores else []
        for arquivo in instaladores:
            print("instalador: %s" % arquivo)
        extras = instaladores + escrever_ultima(dist, args.versao, chave, repo, instaladores)
        print(
            "na página da versão (com --publicar, sobem sozinhos): %s, o zip e o .sig"
            % ", ".join(p.name for p in extras)
        )
        if args.publicar:
            print("release: %s" % publicar(repo, args.versao, pacote, notas, extras))
        else:
            subprocess.run(
                ["git", "tag", "-d", "v" + args.versao], cwd=str(repo), capture_output=True, timeout=60, check=False
            )
            print("ensaio conferido e desfeito (a tag local saiu); para publicar, acrescente --publicar")
    except (Recusa, GpErro) as erro:
        print("recusado: %s" % erro, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
