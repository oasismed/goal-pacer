"""goalpacer/janela.py: o Goal Pacer.app montado com um xcrun de mentira (estrutura, Info.plist, troca atômica, falhas)
e, no macOS com Swift, compilado de verdade (binário Mach-O com assinatura local válida)."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from goalpacer import copy, janela
from goalpacer.base import GpErro

RAIZ_REPO = Path(__file__).resolve().parent.parent
XCRUN_FALSO = r"""#!/bin/sh
echo "$@" >> "%(log)s"
[ -n "$FALHAR" ] && [ "$1" = "$FALHAR" ] && echo "error: deu ruim em $1" >&2 && exit 1
saida=""
anterior=""
for arg in "$@"; do
  if [ "$anterior" = "-o" ] || [ "$anterior" = "--out" ]; then saida="$arg"; fi
  anterior="$arg"
done
case "$1" in
  --find) echo /stub/swiftc ;;
  swiftc|sips|iconutil) printf '%%s' "$1" > "$saida" ;;
esac
exit 0
"""


def textos() -> dict:
    return {chave: copy.texto("janela." + chave) for chave in janela.CHAVES_TEXTOS}


def info() -> dict:
    return janela.info_plist(
        versao="0.3.0",
        endereco="http://127.0.0.1:8765/",
        agente="com.goal-pacer.painel",
        idioma="pt-BR",
        textos=textos(),
    )


@pytest.fixture
def xcrun(tmp_path, monkeypatch):
    log = tmp_path / "xcrun.log"
    binario = tmp_path / "xcrun"
    binario.write_text(XCRUN_FALSO % {"log": log}, encoding="utf-8")
    binario.chmod(0o755)
    monkeypatch.setenv("GP_XCRUN", str(binario))
    return log


def test_monta_o_app_com_icone_textos_e_assinatura_local(tmp_path, xcrun):
    destino = tmp_path / "Applications" / janela.NOME_APP
    assert janela.construir(RAIZ_REPO, destino, info()) == destino
    conteudo = destino / "Contents"
    assert (conteudo / "MacOS" / janela.EXECUTAVEL).read_text(encoding="utf-8") == "swiftc"
    assert (conteudo / "Resources" / "GoalPacer.icns").read_text(encoding="utf-8") == "iconutil"
    plist = plistlib.loads((conteudo / "Info.plist").read_bytes())
    assert plist["CFBundleExecutable"] == "GoalPacer" and plist["CFBundleIdentifier"] == "com.goal-pacer.janela"
    assert plist["CFBundleShortVersionString"] == "0.3.0" and plist["GPEndereco"] == "http://127.0.0.1:8765/"
    assert plist["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}
    assert plist["GPTextos"]["sair"] == "Sair do Goal Pacer" and set(plist["GPTextos"]) == set(janela.CHAVES_TEXTOS)
    chamadas = xcrun.read_text(encoding="utf-8").splitlines()
    assert chamadas[0].startswith("swiftc -O -swift-version 5 -o ") and chamadas[0].endswith("macos/main.swift")
    tamanhos = sorted(int(linha.split()[2]) for linha in chamadas if linha.startswith("sips"))
    assert tamanhos == [16, 32, 32, 64, 128, 256, 256, 512, 512]
    assert chamadas[-1].startswith("codesign --force --sign - ") and chamadas[-1].endswith("Goal Pacer.app")
    assert not destino.with_name(destino.name + ".anterior").exists()


def test_falha_no_meio_mantem_o_app_de_antes(tmp_path, xcrun, monkeypatch):
    destino = tmp_path / "Applications" / janela.NOME_APP
    (destino / "Contents").mkdir(parents=True)
    (destino / "Contents" / "versao-antiga").write_text("x", encoding="utf-8")
    for ferramenta in ("swiftc", "iconutil", "codesign"):
        monkeypatch.setenv("FALHAR", ferramenta)
        with pytest.raises(GpErro, match="xcrun %s falhou: error: deu ruim" % ferramenta):
            janela.construir(RAIZ_REPO, destino, info())
        assert (destino / "Contents" / "versao-antiga").exists()
    monkeypatch.delenv("FALHAR")
    janela.construir(RAIZ_REPO, destino, info())
    assert not (destino / "Contents" / "versao-antiga").exists() and (destino / "Contents" / "Info.plist").exists()
    assert janela.remover(destino) is True and not destino.exists() and janela.remover(destino) is False


def test_mesma_fonte_e_mesmos_textos_nao_compila_outra_vez(tmp_path, xcrun):
    destino = tmp_path / "Applications" / janela.NOME_APP
    impressao = janela.impressao_da_fonte(RAIZ_REPO)
    assert len(impressao) == 16 and janela.impressao_da_fonte(tmp_path) == ""
    com_fonte = dict(info(), GPFonte=impressao)
    assert not janela.montado_com(destino, com_fonte)  # nada montado ainda
    janela.construir(RAIZ_REPO, destino, com_fonte)
    assert janela.montado_com(destino, com_fonte)
    assert not janela.montado_com(destino, dict(com_fonte, CFBundleShortVersionString="9.9.9"))
    assert not janela.montado_com(destino, info())  # sem impressão da fonte, sempre compila
    (destino / "Contents" / "Info.plist").write_bytes(b"torto")
    assert not janela.montado_com(destino, com_fonte)


def test_recusas_antes_de_compilar(tmp_path, xcrun, monkeypatch):
    with pytest.raises(GpErro, match=r"não tem macos/main\.swift"):
        janela.construir(tmp_path / "app-vazio", tmp_path / "destino.app", info())
    incompletos = dict(textos(), sair="")
    with pytest.raises(GpErro, match="textos da janela sem sair"):
        janela.info_plist(versao="1.0.0", endereco="x", agente="y", idioma="en", textos=incompletos)
    assert janela.compilador_disponivel() is True
    monkeypatch.setenv("GP_XCRUN", str(tmp_path / "nao-existe"))
    assert janela.compilador_disponivel() is False
    with pytest.raises(GpErro, match="não consegui rodar o xcrun"):
        janela.construir(RAIZ_REPO, tmp_path / "destino.app", info())
    assert janela.destino_padrao() == Path.home() / "Applications" / "Goal Pacer.app"


@pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("xcrun") is None or not janela.compilador_disponivel(),
    reason="só no macOS com as Command Line Tools",
)
def test_compila_de_verdade_no_mac(tmp_path, monkeypatch):
    monkeypatch.delenv("GP_XCRUN", raising=False)
    destino = janela.construir(RAIZ_REPO, tmp_path / "Applications" / janela.NOME_APP, info())
    binario = destino / "Contents" / "MacOS" / janela.EXECUTAVEL
    assert binario.read_bytes()[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")  # Mach-O 64 ou universal
    verificado = subprocess.run(["codesign", "--verify", str(destino)], capture_output=True, timeout=60)
    assert verificado.returncode == 0, verificado.stderr
    assert (destino / "Contents" / "Resources" / "GoalPacer.icns").stat().st_size > 1000
