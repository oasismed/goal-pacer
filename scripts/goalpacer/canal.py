"""canal.py: onde o app procura a versão mais nova e a baixa para atualizar, sem terminal.

``release/canal`` (uma linha, ``https://...``) é a pasta pública das versões. O padrão é a última versão publicada
no repositório do Goal Pacer no GitHub (``https://github.com/oasismed/goal-pacer/releases/latest/download/``: o
repositório é público e o GitHub redireciona cada nome para o arquivo da versão mais nova, sem login), onde o
``dev/release.py --publicar`` sobe, a cada versão, o que deixa em ``dist/``::

    ultima.json       {"versao": "0.5.0", "zip": "goal-pacer-v0.5.0.zip", "mac": "Goal-Pacer-0.5.0.dmg",
                       "windows": "Goal-Pacer-Setup-0.5.0.exe"}
    ultima.json.sig   assinatura com a chave de release/assinantes (espaço goal-pacer-release)
    o zip e o .sig    o update baixa estes; o .dmg e o Setup.exe são para quem instala do zero

Sem ``release/canal``, nada é consultado e o update é abrir o instalador da versão nova.
Com canal, o
Status pergunta no máximo uma vez por dia, baixando só o ``ultima.json`` (nenhum dado da pessoa vai junto), confere a
assinatura com a lista de assinantes da instalação e mostra a versão nova; Atualizar baixa o zip e o ``.sig`` e segue
o update pelo zip, que confere tudo de novo.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from goalpacer import assinatura
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

ARQUIVO_CANAL = Path("release") / "canal"
NOME_ULTIMA = "ultima.json"
TETO_ULTIMA_BYTES = 64 * 1024
TIMEOUT_S = 20
Abrir = Callable[..., Any]


def endereco(app: Path) -> Optional[str]:
    """A pasta pública do canal, ou None sem canal (arquivo ausente, vazio ou fora de https)."""
    try:
        linha = (app / ARQUIVO_CANAL).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return linha.rstrip("/") + "/" if linha.startswith("https://") and " " not in linha else None


def baixar(url: str, destino: Path, teto_bytes: int, *, abrir: Abrir = urllib.request.urlopen) -> Path:
    """Baixa ``url`` para ``destino`` sem passar de ``teto_bytes``; erro de rede ou arquivo grande demais é GpErro."""
    try:
        with abrir(url, timeout=TIMEOUT_S) as resposta, open(destino, "wb") as saida:
            lidos = 0
            while True:
                pedaco = resposta.read(64 * 1024)
                if not pedaco:
                    break
                lidos += len(pedaco)
                if lidos > teto_bytes:
                    raise GpErro(EXIT_VALIDACAO, "%s passou de %d MB" % (destino.name, teto_bytes >> 20))
                saida.write(pedaco)
    except OSError as erro:
        raise GpErro(EXIT_IO, "não consegui baixar %s: %s" % (url, erro)) from erro
    return destino


def ultima(app: Path, pasta: Path, *, abrir: Abrir = urllib.request.urlopen) -> Optional[dict[str, Any]]:
    """O ``ultima.json`` do canal, com a assinatura conferida pela lista de assinantes da instalação; None sem canal."""
    base = endereco(app)
    if base is None:
        return None
    arquivo = baixar(base + NOME_ULTIMA, pasta / NOME_ULTIMA, TETO_ULTIMA_BYTES, abrir=abrir)
    baixar(base + NOME_ULTIMA + ".sig", pasta / (NOME_ULTIMA + ".sig"), TETO_ULTIMA_BYTES, abrir=abrir)
    assinatura.verificar_arquivo(arquivo, assinatura.copiar_assinantes(app, pasta))
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except ValueError as erro:
        raise GpErro(EXIT_VALIDACAO, "ultima.json do canal ilegível: %s" % erro) from erro
    versao = assinatura.versao_de(str(dados.get("versao") or "")) if isinstance(dados, dict) else None
    nome_zip = dados.get("zip") if isinstance(dados, dict) else None
    if versao is None or not isinstance(nome_zip, str) or "/" in nome_zip or not nome_zip.endswith(".zip"):
        raise GpErro(EXIT_VALIDACAO, "ultima.json do canal fora do formato (versao e zip)")
    return dict(dados, versao_tupla=versao)


def baixar_zip(app: Path, dados: dict[str, Any], pasta: Path, *, abrir: Abrir = urllib.request.urlopen) -> Path:
    """O zip da versão e o ``.sig`` ao lado, na pasta dada; quem confere é o update pelo zip."""
    base = endereco(app)
    if base is None:
        raise GpErro(EXIT_VALIDACAO, "sem release/canal para baixar a versão nova")
    arquivo = baixar(base + dados["zip"], pasta / dados["zip"], assinatura.LIMITE_ZIP_BYTES, abrir=abrir)
    baixar(base + dados["zip"] + ".sig", pasta / (dados["zip"] + ".sig"), TETO_ULTIMA_BYTES, abrir=abrir)
    return arquivo
