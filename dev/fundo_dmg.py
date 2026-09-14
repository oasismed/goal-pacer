#!/usr/bin/env python3
"""fundo_dmg.py: gera o fundo da janela do .dmg (macos/dmg/fundo.png e fundo@2x.png) a partir de macos/dmg/fundo.html.

    python3 dev/fundo_dmg.py        # precisa do navegador headless do gstack (BROWSE=<binário> troca o caminho)

Serve a raiz do repositório só em 127.0.0.1 (para a fonte do painel carregar), abre a página em 660x440 e em
1320x880 com zoom 2 e grava as duas capturas. Rode depois de mudar o fundo.html e commite os dois PNGs: o
dev/empacotar.py só junta os dois num TIFF para telas Retina e não depende do navegador.
"""

from __future__ import annotations

import functools
import http.server
import os
import subprocess
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "macos" / "dmg"
BROWSE = os.environ.get("BROWSE") or str(Path.home() / ".claude" / "skills" / "gstack" / "browse" / "dist" / "browse")
LARGURA, ALTURA = 660, 440


def _browse(*args: str) -> str:
    return subprocess.run([BROWSE, *args], capture_output=True, text=True, timeout=120, check=True).stdout


def main() -> int:
    tratador = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(RAIZ))
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), tratador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    endereco = "http://127.0.0.1:%d/macos/dmg/fundo.html" % servidor.server_address[1]
    try:
        for escala, nome in ((1, "fundo.png"), (2, "fundo@2x.png")):
            _browse("viewport", "%dx%d" % (LARGURA * escala, ALTURA * escala))
            _browse("goto", endereco)
            _browse("wait", "--networkidle")
            _browse("js", "document.documentElement.style.setProperty('--escala', '%d')" % escala)
            time.sleep(1)  # a fonte e o zoom assentam antes da captura
            _browse("screenshot", "--viewport", str(PASTA / nome))
            print("gravado: %s" % (PASTA / nome))
    finally:
        servidor.shutdown()
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
