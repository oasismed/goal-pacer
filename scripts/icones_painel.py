#!/usr/bin/env python3
"""icones_painel.py: gera os ícones do painel (web/icone-180.png, -192, -512) em Python puro.

Desenho minimalista: um único anel verde aberto em três quartos, com pontas arredondadas,
sobre um trilho claro e fundo liso, nas cores de ``web/app.css``. Antisserrilhado por
cobertura analítica; PNG RGB 8 bits escrito com zlib. Determinístico: rodar de novo gera os
mesmos bytes (``tests/test_web.py`` confere). Uso: ``python3 scripts/icones_painel.py``.
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

PASTA_WEB = Path(__file__).resolve().parent.parent / "web"
TAMANHOS = (180, 192, 512)
FUNDO = (0xEE, 0xF2, 0xEF)
# (raio relativo, cor, fração do arco)
ANEIS = ((0.27, (0x2F, 0x6B, 0x55), 0.75),)
ESPESSURA = 0.13
OPACIDADE_TRILHO = 0.10


def _cobertura(distancia: float, meia_largura: float) -> float:
    return max(0.0, min(1.0, meia_largura - distancia + 0.5))


def _misturar(base: tuple, cor: tuple, alfa: float) -> tuple:
    return tuple(b + (c - b) * alfa for b, c in zip(base, cor))


def desenhar(tamanho: int) -> bytes:
    centro = tamanho / 2.0
    meia = ESPESSURA * tamanho / 2.0
    linhas = bytearray()
    for y in range(tamanho):
        linhas.append(0)  # filtro "none"
        for x in range(tamanho):
            cor = _cor_do_pixel(x + 0.5, y + 0.5, tamanho, centro, meia)
            linhas.extend(round(max(0, min(255, c))) for c in cor)
    return bytes(linhas)


def _cor_do_pixel(px: float, py: float, tamanho: int, centro: float, meia: float) -> tuple:
    cor = FUNDO
    dx, dy = px - centro, py - centro
    d = math.hypot(dx, dy)
    angulo = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0  # a partir do topo, no sentido horário, em [0, 1)
    for raio_rel, tinta, fracao in ANEIS:
        raio = raio_rel * tamanho
        banda = _cobertura(abs(d - raio), meia)
        if banda > 0.0:
            cor = _misturar(cor, tinta, OPACIDADE_TRILHO * banda)
            cor = _misturar(cor, tinta, _alfa_do_arco(px, py, centro, raio, meia, banda, angulo, fracao))
    return cor


def _alfa_do_arco(
    px: float, py: float, centro: float, raio: float, meia: float, banda: float, angulo: float, fracao: float
) -> float:
    """Opacidade do arco preenchido no pixel: corpo com bordas suaves e as duas pontas arredondadas."""
    alfa = 0.0
    if angulo <= fracao:
        borda = min(angulo, fracao - angulo) * 2 * math.pi * raio  # suaviza as bordas pelo comprimento em pixels
        alfa = banda * max(0.0, min(1.0, borda + 0.5))
    for ponta in (0.0, fracao):
        teta = 2 * math.pi * ponta
        cx, cy = centro + raio * math.sin(teta), centro - raio * math.cos(teta)
        alfa = max(alfa, _cobertura(math.hypot(px - cx, py - cy), meia))
    return alfa


def png(tamanho: int) -> bytes:
    def pedaco(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + pedaco(b"IHDR", cabecalho)
        + pedaco(b"IDAT", zlib.compress(desenhar(tamanho), 9))
        + pedaco(b"IEND", b"")
    )


def main() -> int:
    for tamanho in TAMANHOS:
        destino = PASTA_WEB / ("icone-%d.png" % tamanho)
        destino.write_bytes(png(tamanho))
        print(destino.relative_to(PASTA_WEB.parent))
    return 0


if __name__ == "__main__":
    sys.exit(main())
