"""janela.py: monta o ``Goal Pacer.app`` (macOS), a janela nativa do painel, compilado na máquina de quem instala.

Compilar aqui, em vez de distribuir um binário, é o que dispensa conta de desenvolvedor Apple e notarização: arquivo
criado na própria máquina não carrega a marca de baixado da internet. Tudo passa pelo ``xcrun`` das Command Line
Tools, que o Goal Pacer já exige para o python3 da Apple::

    xcrun swiftc -O -swift-version 5 macos/main.swift   -> Contents/MacOS/GoalPacer
    xcrun sips / iconutil  web/icone-512.png              -> Contents/Resources/GoalPacer.icns
    plistlib                                              -> Contents/Info.plist (endereço, agente, versão, textos)
    xcrun codesign --force --sign -                       assinatura local (ad hoc), que o Apple Silicon pede

A montagem acontece numa pasta temporária e só troca o app de ``destino`` quando tudo deu certo: falha no meio deixa
o app anterior. O Info.plist guarda a impressão da fonte (sha256 de ``main.swift`` e do ícone): reinstalar a mesma
versão, com os mesmos textos, não compila outra vez (``montado_com``). ``GP_XCRUN`` troca o xcrun (testes).
"""

from __future__ import annotations

import hashlib
import os
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

ENV_XCRUN = "GP_XCRUN"
NOME_APP = "Goal Pacer.app"
EXECUTAVEL = "GoalPacer"
IDENTIFICADOR = "com.goal-pacer.janela"
FONTE = Path("macos") / "main.swift"
ICONE = Path("web") / "icone-512.png"
LADOS_ICONE = (16, 32, 128, 256, 512)
TIMEOUT_COMPILAR_S = 600
TIMEOUT_FERRAMENTA_S = 60
CHAVES_TEXTOS = (
    "esperando",
    "sem_painel",
    "instalando",
    "instalacao_parou",
    "tentar_outra_vez",
    "ocultar",
    "sair",
    "editar",
    "desfazer",
    "refazer",
    "recortar",
    "copiar",
    "colar",
    "selecionar_tudo",
    "ver",
    "recarregar",
    "janela",
    "minimizar",
    "fechar",
)


def destino_padrao() -> Path:
    """``~/Applications/Goal Pacer.app``: a pasta de apps do usuário, sem pedir senha de administrador."""
    return Path.home() / "Applications" / NOME_APP


def _xcrun() -> str:
    return os.environ.get(ENV_XCRUN) or "/usr/bin/xcrun"


def _rodar(argv: list[str], timeout_s: float) -> None:
    try:
        proc = subprocess.run(
            [_xcrun(), *argv],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        raise GpErro(EXIT_IO, "xcrun %s passou de %d s" % (argv[0], timeout_s)) from erro
    except OSError as erro:
        raise GpErro(EXIT_IO, "não consegui rodar o xcrun: %s" % erro) from erro
    if proc.returncode != 0:
        detalhe = (proc.stderr or proc.stdout).strip().split("\n")
        raise GpErro(EXIT_VALIDACAO, "xcrun %s falhou: %s" % (argv[0], detalhe[-1][:300] if detalhe else "sem saída"))


def compilador_disponivel() -> bool:
    try:
        return (
            subprocess.run(
                [_xcrun(), "--find", "swiftc"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=TIMEOUT_FERRAMENTA_S,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def impressao_da_fonte(app: Path) -> str:
    """sha256 (16 hex) de ``main.swift`` e do ícone: muda quando o que vai ser compilado muda."""
    resumo = hashlib.sha256()
    for relativo in (FONTE, ICONE):
        try:
            resumo.update((app / relativo).read_bytes())
        except OSError:
            return ""
    return resumo.hexdigest()[:16]


def montado_com(destino: Path, info: dict) -> bool:
    """O app em ``destino`` já foi montado com este Info.plist (versão, endereço, textos e fonte) e tem o binário."""
    if not info.get("GPFonte") or not (destino / "Contents" / "MacOS" / EXECUTAVEL).is_file():
        return False
    try:
        return plistlib.loads((destino / "Contents" / "Info.plist").read_bytes()) == info
    except (OSError, plistlib.InvalidFileException, ValueError):
        return False


def info_plist(
    *, versao: str, endereco: str, agente: str, idioma: str, textos: dict[str, str], fonte: str = ""
) -> dict:
    faltam = [chave for chave in CHAVES_TEXTOS if not textos.get(chave)]
    if faltam:
        raise GpErro(EXIT_VALIDACAO, "textos da janela sem %s" % ", ".join(faltam))
    return {
        "CFBundleDevelopmentRegion": idioma,
        "CFBundleDisplayName": "Goal Pacer",
        "CFBundleExecutable": EXECUTAVEL,
        "CFBundleIconFile": EXECUTAVEL,
        "CFBundleIdentifier": IDENTIFICADOR,
        "CFBundleName": "Goal Pacer",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": versao,
        "CFBundleVersion": versao,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},  # http no 127.0.0.1, nada de fora
        "GPEndereco": endereco,
        "GPLabelPainel": agente,
        "GPTextos": {chave: textos[chave] for chave in CHAVES_TEXTOS},
        "GPFonte": fonte,
    }


def _icone(app: Path, pasta: Path, recursos: Path) -> None:
    conjunto = pasta / (EXECUTAVEL + ".iconset")
    conjunto.mkdir()
    origem = str(app / ICONE)
    for lado in LADOS_ICONE:
        for escala in (1, 2):
            if lado * escala > 512:
                continue
            nome = "icon_%dx%d%s.png" % (lado, lado, "@2x" if escala == 2 else "")
            _rodar(["sips", "-z", str(lado * escala), str(lado * escala), origem, "--out", str(conjunto / nome)], 60)
    _rodar(["iconutil", "-c", "icns", str(conjunto), "-o", str(recursos / (EXECUTAVEL + ".icns"))], 60)


def construir(app: Path, destino: Path, info: dict, *, temporaria: Optional[Path] = None) -> Path:
    """Compila, monta, assina e só então troca ``destino``; devolve o caminho do app."""
    fonte = app / FONTE
    if not fonte.is_file() or not (app / ICONE).is_file():
        raise GpErro(EXIT_VALIDACAO, "o app em %s não tem %s e %s" % (app, FONTE, ICONE))
    with tempfile.TemporaryDirectory(prefix="goal-pacer-janela-", dir=temporaria) as pasta_texto:
        pasta = Path(pasta_texto)
        pacote = pasta / NOME_APP
        executaveis, recursos = pacote / "Contents" / "MacOS", pacote / "Contents" / "Resources"
        executaveis.mkdir(parents=True)
        recursos.mkdir(parents=True)
        _rodar(
            ["swiftc", "-O", "-swift-version", "5", "-o", str(executaveis / EXECUTAVEL), str(fonte)],
            TIMEOUT_COMPILAR_S,
        )
        _icone(app, pasta, recursos)
        (pacote / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
        _rodar(["codesign", "--force", "--sign", "-", str(pacote)], TIMEOUT_FERRAMENTA_S)
        destino.parent.mkdir(parents=True, exist_ok=True)
        antigo = destino.with_name(destino.name + ".anterior")
        if antigo.exists():
            shutil.rmtree(str(antigo))
        if destino.exists():
            os.replace(str(destino), str(antigo))
        try:
            shutil.move(str(pacote), str(destino))
        except OSError as erro:
            if antigo.exists():
                os.replace(str(antigo), str(destino))  # o app de antes volta
            raise GpErro(EXIT_IO, "não consegui pôr o app em %s: %s" % (destino, erro)) from erro
        shutil.rmtree(str(antigo), ignore_errors=True)
    return destino


def remover(destino: Path) -> bool:
    if not destino.exists():
        return False
    shutil.rmtree(str(destino))
    return True
