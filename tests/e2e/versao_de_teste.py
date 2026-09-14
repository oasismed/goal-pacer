#!/usr/bin/env python3
"""versao_de_teste.py: a árvore de trabalho empacotada como uma versão publicada, assinada por uma chave do teste.

Os E2E de instalação (``windows.py``, ``instaladores.py``) usam no lugar do zip do ``dev/release.py``, que exige a chave
de release: a pasta sai sem .git, com ``VERSAO_APP`` trocado, a lista de assinantes com a chave do teste e o
``release/manifesto.json`` assinado. Nada daqui vai para quem instala.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]


def chave_de_teste(pasta: Path) -> Path:
    chave = pasta / "chave-teste"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True, timeout=60)
    return chave


def pasta_baixada(destino: Path, versao: str, chave: Path, extra: str = "") -> Path:
    """A árvore de trabalho como o zip da versão descompactado: sem .git, com a lista de assinantes e o manifesto."""
    sys.path.insert(0, str(RAIZ_REPO / "scripts"))
    from goalpacer import assinatura

    pasta = destino / ("goal-pacer-v%s" % versao)
    shutil.copytree(
        str(RAIZ_REPO),
        str(pasta),
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "dist", "out", ".venv*"),
    )
    base_py = pasta / "scripts" / "goalpacer" / "base.py"
    base_py.write_text(
        re.sub(
            r'^VERSAO_APP = "[^"]+"',
            'VERSAO_APP = "%s"' % versao,
            base_py.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
    tipo, publica = Path(str(chave) + ".pub").read_text(encoding="utf-8").split()[:2]
    (pasta / "release" / "assinantes").write_text(
        'ci@exemplo.test namespaces="git,goal-pacer-release" %s %s\n' % (tipo, publica), encoding="utf-8"
    )
    if extra:
        (pasta / extra).write_text("versão %s\n" % versao, encoding="utf-8")
    arquivos = {p.relative_to(pasta).as_posix(): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()}
    manifesto = pasta / assinatura.ARQUIVO_MANIFESTO
    manifesto.write_bytes(assinatura.manifesto(versao, arquivos, []))
    subprocess.run(
        ["ssh-keygen", "-q", "-Y", "sign", "-f", str(chave), "-n", assinatura.ESPACO_ZIP, str(manifesto)],
        check=True,
        timeout=60,
    )
    return pasta
