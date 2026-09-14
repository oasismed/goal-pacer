#!/usr/bin/env python3
"""empacotar.py: os instaladores de um arquivo de uma versão, para mandar direto a quem vai usar.

    python3 dev/empacotar.py --zip dist/goal-pacer-v0.5.0.zip              # o zip assinado que o release.py gerou
    python3 dev/empacotar.py --pasta <pasta com release/manifesto.json>     # a pasta de uma versão (os E2E usam uma de teste)
        [--mac] [--windows]  (sem nenhum dos dois: os dois)  [--dist dist]  [--cache ~/.cache/goal-pacer-empacotar]

A pasta precisa ser uma versão publicada: o instalador de dentro confere o manifesto com a lista de assinantes da
instalação que já existe (update) ou, na primeira vez, só copia. Nada aqui assina com a chave de release: a pasta já
vem assinada pelo release.py.

Mac, ``dist/Goal-Pacer-<versão>.dmg`` (arrastar para Aplicativos e abrir)::

    Python universal: python-build-standalone arm64 + x86_64 (versão e sha256 fixos), sem o que o app não usa
    (tkinter, idle, testes, ensurepip, libpython estática), juntados arquivo a arquivo com lipo
    Goal Pacer.app: macos/main.swift compilado para arm64 e x86_64 (macOS 13+), ícone, Info.plist com os textos dos
    dois idiomas, Resources/python e Resources/goal-pacer; cada Mach-O e o app assinados localmente (ad hoc)
    .dmg (UDZO, dmgbuild com as versões de requirements-dmg.txt) com o app, o atalho para Aplicativos e a janela com
    fundo (macos/dmg/fundo.png e @2x, gerados por dev/fundo_dmg.py): arrastar para Aplicativos e o passo da primeira
    abertura sem certificado pago

Windows, ``dist/Goal-Pacer-Setup-<versão>.exe`` (NSIS, instalação por usuário, desinstalação em Aplicativos)::

    Python embutível oficial (amd64, versão e sha256 fixos) com o tzdata dentro, a pasta da versão e o ícone,
    compilados por windows/instalador.nsi (makensis)

Sem certificado pago, o sistema avisa na primeira abertura do arquivo recebido (Mac: Ajustes do Sistema >
Privacidade e Segurança > Abrir mesmo assim; Windows: Mais informações > Executar assim mesmo).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import icones_painel  # noqa: E402
from goalpacer import assinatura, atalhos, copy, janela  # noqa: E402
from goalpacer.base import GpErro  # noqa: E402

PYTHON = "3.13.15"
PBS = "20260901"
URL_PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/%s/%s"
PYTHON_MAC = {
    "arm64": (
        "cpython-%s+%s-aarch64-apple-darwin-install_only_stripped.tar.gz" % (PYTHON, PBS),
        "d3904bd6a072246e07aa0bdadee9a14e80521e42a943c0848059feb16a2816dc",
    ),
    "x86_64": (
        "cpython-%s+%s-x86_64-apple-darwin-install_only_stripped.tar.gz" % (PYTHON, PBS),
        "f712a9143c8a5d248438ec7921a0b48d548bca4f1337d33c690d28c2d0504137",
    ),
}
PYTHON_WINDOWS = (
    "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip" % (PYTHON, PYTHON),
    "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf",
)
TZDATA_WHEEL = (
    (
        "https://files.pythonhosted.org/packages/f9/bc/8737e8d54cf51106118039b83f485a4783112fab49ea9d044b234978a46e/"
        "tzdata-2026.4-py2.py3-none-any.whl"
    ),
    "c2169a8b0a7a5e9674da5a135ccdfb2b3e671b333ed9fed17b41f73c34476e81",
)
MINIMO_MAC = "13.0"
# o que o app nunca importa: fica fora do Python embutido no Mac
PODAR_MAC = (
    "include",
    "share",
    "lib/pkgconfig",
    "lib/itcl4.3.2",
    "lib/tcl9",
    "lib/tcl8",
    "lib/tcl8.6",
    "lib/tk8.6",
    "lib/tk9.0",
    "lib/thread3.0.1",
    "lib/python3.13/test",
    "lib/python3.13/idlelib",
    "lib/python3.13/tkinter",
    "lib/python3.13/turtledemo",
    "lib/python3.13/ensurepip",
    "lib/python3.13/site-packages",
    "lib/python3.13/config-3.13-darwin",
)
PREFIXOS_PODADOS = ("libtcl", "libtk", "_tkinter", "idle3", "pip3", "pydoc3")
TIMEOUT_S = 900
MAGICOS_MACHO = (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe")


class Falha(Exception):
    """Um passo do empacotamento que não passou; o arquivo final não é gerado."""


def _rodar(argv: list[str], cwd: Optional[Path] = None) -> str:
    proc = subprocess.run(
        argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
    )
    if proc.returncode != 0:
        raise Falha("%s: %s" % (Path(argv[0]).name, (proc.stderr or proc.stdout).strip()[-600:]))
    return proc.stdout


def baixar(url: str, sha256: str, cache: Path) -> Path:
    """Baixa uma vez para o cache e confere o sha256 fixado (no cache também, a cada uso)."""
    cache.mkdir(parents=True, exist_ok=True)
    destino = cache / url.rsplit("/", 1)[1]
    if not destino.is_file():
        temporario = destino.with_name(destino.name + ".baixando")
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as resposta, open(temporario, "wb") as saida:  # noqa: S310
            shutil.copyfileobj(resposta, saida)
        os.replace(str(temporario), str(destino))
    obtido = hashlib.sha256(destino.read_bytes()).hexdigest()
    if obtido != sha256:
        destino.unlink()
        raise Falha("%s com sha256 %s, esperado %s" % (destino.name, obtido, sha256))
    return destino


def pasta_da_versao(zip_da_versao: Path, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    return assinatura.extrair_zip(zip_da_versao, destino)


def conferir_pasta(pasta: Path) -> str:
    """A versão do manifesto; pasta sem manifesto assinado não é uma versão publicada."""
    versao = assinatura.versao_do_manifesto(pasta)
    selo = pasta / (assinatura.ARQUIVO_MANIFESTO.as_posix() + ".sig")
    if versao is None or not selo.is_file():
        raise Falha("%s não tem release/manifesto.json assinado: use o zip do dev/release.py" % pasta)
    return "%d.%d.%d" % versao


def _copiar_versao(pasta: Path, destino: Path) -> None:
    shutil.copytree(str(pasta), str(destino), ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))


def textos_da_janela(idioma: str) -> dict[str, str]:
    return {chave: copy.texto("janela." + chave, idioma=idioma) for chave in janela.CHAVES_TEXTOS}


# --- Mac ---------------------------------------------------------------------------------------------------------


def _eh_macho(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    with open(path, "rb") as arquivo:
        return arquivo.read(4) in MAGICOS_MACHO


def _extrair_tar(arquivo: Path, destino: Path) -> Path:
    with tarfile.open(str(arquivo)) as pacote:
        membros = [m for m in pacote.getmembers() if not (m.name.startswith("/") or ".." in Path(m.name).parts)]
        if hasattr(tarfile, "data_filter"):
            pacote.extractall(str(destino), members=membros, filter="tar")
        else:  # pragma: no cover - Python sem filtro de extração
            pacote.extractall(str(destino), members=membros)  # noqa: S202
    return destino / "python"


def _podar(python: Path) -> None:
    for relativo in PODAR_MAC:
        alvo = python / relativo
        if alvo.is_dir() and not alvo.is_symlink():
            shutil.rmtree(str(alvo))
    for path in list(python.rglob("*")):
        if path.name.startswith(PREFIXOS_PODADOS) and (path.is_file() or path.is_symlink()):
            path.unlink()


def python_universal(cache: Path, destino: Path) -> Path:
    """Python arm64 + x86_64 num só: cada Mach-O vira universal pelo lipo; o resto sai da árvore arm64."""
    with tempfile.TemporaryDirectory(prefix="gp-python-") as pasta:
        arvores = {}
        for arquitetura, (nome, sha) in PYTHON_MAC.items():
            arvores[arquitetura] = _extrair_tar(baixar(URL_PBS % (PBS, nome), sha, cache), Path(pasta) / arquitetura)
            _podar(arvores[arquitetura])
        arm, intel = arvores["arm64"], arvores["x86_64"]
        for origem in sorted(arm.rglob("*")):
            relativo = origem.relative_to(arm)
            alvo = destino / relativo
            if origem.is_symlink():
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.symlink_to(os.readlink(str(origem)))
            elif origem.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
            elif _eh_macho(origem) and _eh_macho(intel / relativo):
                alvo.parent.mkdir(parents=True, exist_ok=True)
                _rodar(["lipo", "-create", str(origem), str(intel / relativo), "-output", str(alvo)])
                shutil.copymode(str(origem), str(alvo))
            else:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(origem), str(alvo))
    for path in sorted(destino.rglob("*")):
        if _eh_macho(path):
            _rodar(["codesign", "--force", "--sign", "-", str(path)])
    return destino


def _binario_da_janela(pasta: Path, saida: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="gp-swift-") as temporaria:
        partes = []
        for arquitetura in ("arm64", "x86_64"):
            parte = Path(temporaria) / arquitetura
            alvo = "%s-apple-macos%s" % (arquitetura, MINIMO_MAC.split(".")[0])
            _rodar(
                [
                    "xcrun",
                    "swiftc",
                    "-O",
                    "-swift-version",
                    "5",
                    "-target",
                    alvo,
                    "-o",
                    str(parte),
                    str(pasta / janela.FONTE),
                ]
            )
            partes.append(str(parte))
        _rodar(["lipo", "-create", *partes, "-output", str(saida)])


def montar_app(pasta: Path, versao: str, python: Path, destino: Path) -> Path:
    """Goal Pacer.app com a janela universal, o Python e a versão dentro, assinado localmente."""
    conteudo = destino / "Contents"
    recursos = conteudo / "Resources"
    (conteudo / "MacOS").mkdir(parents=True)
    recursos.mkdir()
    _binario_da_janela(pasta, conteudo / "MacOS" / janela.EXECUTAVEL)
    with tempfile.TemporaryDirectory(prefix="gp-icone-") as temporaria:
        janela._icone(pasta, Path(temporaria), recursos)
    info = janela.info_plist(
        versao=versao,
        endereco="http://127.0.0.1:8765/",
        agente="com.goal-pacer.painel",
        idioma="pt-BR",
        textos=textos_da_janela("pt-BR"),
    )
    info.update(
        {
            "LSMinimumSystemVersion": MINIMO_MAC,
            "GPTextosIdiomas": {idioma: textos_da_janela(idioma) for idioma in ("pt-BR", "en")},
            "CFBundleDevelopmentRegion": "pt-BR",
        }
    )
    info.pop("GPFonte", None)
    (conteudo / "Info.plist").write_bytes(plistlib.dumps(info))
    shutil.copytree(str(python), str(recursos / "python"), symlinks=True)
    _copiar_versao(pasta, recursos / "goal-pacer")
    _rodar(["codesign", "--force", "--sign", "-", str(destino)])
    _rodar(["codesign", "--verify", "--deep", "--strict", str(destino)])
    return destino


REQUISITOS_DMG = RAIZ / "requirements-dmg.txt"
FUNDO_DMG = RAIZ / "macos" / "dmg"
NOME_ATALHO_APLICATIVOS = "Aplicativos"
JANELA_DMG = (660, 472)  # o fundo.png tem 660x440; a barra de título do Finder ocupa os 32 pontos de cima
POSICOES_DMG = {janela.NOME_APP: (165, 180), NOME_ATALHO_APLICATIVOS: (495, 180)}  # os lugares que o fundo.html desenha


def comando_dmgbuild() -> list[str]:
    """O dmgbuild do Python atual, se instalado; senão pelo uv, com as versões fixadas em requirements-dmg.txt."""
    if importlib.util.find_spec("dmgbuild") is not None:
        return [sys.executable, "-m", "dmgbuild"]
    uv = shutil.which("uv")
    if uv is None:
        raise Falha("dmgbuild ausente: pip install -r requirements-dmg.txt (ou instale o uv)")
    return [uv, "run", "--no-project", "--with-requirements", str(REQUISITOS_DMG), "python", "-m", "dmgbuild"]


def ajustes_dmg(app: Path, fundo: Path) -> str:
    """O arquivo de ajustes do dmgbuild (Python que ele executa): conteúdo, fundo e a janela sem barras."""
    ajustes = {
        "format": "UDZO",
        "filesystem": "HFS+",
        "files": [str(app)],
        "symlinks": {NOME_ATALHO_APLICATIVOS: "/Applications"},
        "icon_locations": POSICOES_DMG,
        "background": str(fundo),
        "window_rect": ((200, 140), JANELA_DMG),
        "default_view": "icon-view",
        "icon_size": 128,
        "text_size": 13,
        "show_status_bar": False,
        "show_tab_view": False,
        "show_toolbar": False,
        "show_pathbar": False,
        "show_sidebar": False,
    }
    return "".join("%s = %r\n" % item for item in ajustes.items())


def construir_dmg(pasta: Path, dist: Path, cache: Path) -> Path:
    versao = conferir_pasta(pasta)
    saida = dist / ("Goal-Pacer-%s.dmg" % versao)
    with tempfile.TemporaryDirectory(prefix="gp-dmg-") as temporaria:
        base = Path(temporaria)
        python = python_universal(cache, base / "python")
        palco = base / "palco"
        palco.mkdir()
        montar_app(pasta, versao, python, palco / janela.NOME_APP)
        fundo = base / "fundo.tiff"  # 1x e 2x num arquivo só: nítido em tela Retina
        _rodar(
            [
                "tiffutil",
                "-cathidpicheck",
                str(FUNDO_DMG / "fundo.png"),
                str(FUNDO_DMG / "fundo@2x.png"),
                "-out",
                str(fundo),
            ]
        )
        ajustes = base / "ajustes_dmg.py"
        ajustes.write_text(ajustes_dmg(palco / janela.NOME_APP, fundo), encoding="utf-8")
        dist.mkdir(parents=True, exist_ok=True)
        if saida.exists():
            saida.unlink()
        _rodar([*comando_dmgbuild(), "-s", str(ajustes), "Goal Pacer", str(saida)])
    _rodar(["hdiutil", "verify", str(saida)])
    return saida


# --- Windows -----------------------------------------------------------------------------------------------------


def _extrair_zip_confiavel(arquivo: Path, destino: Path, prefixo: str = "") -> None:
    """Zip de fonte fixada (sha256): só os membros sem caminho absoluto nem ``..``, opcionalmente só um prefixo."""
    with zipfile.ZipFile(str(arquivo)) as pacote:
        for membro in pacote.infolist():
            partes = Path(membro.filename).parts
            if membro.filename.startswith("/") or ".." in partes or not membro.filename.startswith(prefixo):
                continue
            pacote.extract(membro, str(destino))


def construir_setup(pasta: Path, dist: Path, cache: Path) -> Path:
    versao = conferir_pasta(pasta)
    makensis = shutil.which("makensis")
    if makensis is None:
        raise Falha("makensis não encontrado: brew install makensis (Mac) ou apt install nsis (Linux)")
    saida = dist / ("Goal-Pacer-Setup-%s.exe" % versao)
    with tempfile.TemporaryDirectory(prefix="gp-setup-") as temporaria:
        base = Path(temporaria)
        da_versao = base / "origem" / versao
        python = da_versao / "python"
        python.mkdir(parents=True)
        _extrair_zip_confiavel(baixar(*PYTHON_WINDOWS, cache), python)
        _extrair_zip_confiavel(baixar(*TZDATA_WHEEL, cache), python, prefixo="tzdata/")  # "." está no python313._pth
        _copiar_versao(pasta, da_versao / "goal-pacer")
        icone = base / atalhos.NOME_ICONE
        icone.write_bytes(atalhos.ico({lado: icones_painel.png(lado) for lado in (16, 32, 48, 256)}))
        dist.mkdir(parents=True, exist_ok=True)
        roteiro = (RAIZ / "windows" / "instalador.nsi").read_text(encoding="utf-8")
        for chave, valor in {
            "VERSAO": versao,
            "SAIDA": str(saida.resolve()),
            "ARQUIVOS": str(da_versao.resolve()) + os.sep + "*",  # o makensis do Windows só acha com \\
            "ICONE": str(icone.resolve()),
        }.items():
            roteiro = roteiro.replace("{{%s}}" % chave, valor)
        nsi = base / "instalador.nsi"
        nsi.write_text(roteiro, encoding="utf-8")
        _rodar([makensis, "-V2", "-INPUTCHARSET", "UTF8", str(nsi)])
    return saida


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="instaladores de um arquivo (.dmg e Setup.exe) de uma versão")
    origem = parser.add_mutually_exclusive_group(required=True)
    origem.add_argument("--zip", type=Path, help="o zip assinado da versão (dev/release.py)")
    origem.add_argument("--pasta", type=Path, help="a pasta de uma versão com release/manifesto.json assinado")
    parser.add_argument("--mac", action="store_true")
    parser.add_argument("--windows", action="store_true")
    parser.add_argument("--dist", type=Path, default=RAIZ / "dist")
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache" / "goal-pacer-empacotar")
    args = parser.parse_args(argv)
    mac, windows = (args.mac or not args.windows), (args.windows or not args.mac)
    try:
        with tempfile.TemporaryDirectory(prefix="gp-versao-") as temporaria:
            pasta = args.pasta or pasta_da_versao(args.zip, Path(temporaria))
            if mac:
                print("mac: %s" % construir_dmg(pasta, args.dist, args.cache))
            if windows:
                print("windows: %s" % construir_setup(pasta, args.dist, args.cache))
    except (Falha, GpErro) as erro:
        print("recusado: %s" % erro, file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
