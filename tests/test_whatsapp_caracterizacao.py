"""Golden master da leitura do export do WhatsApp antes da refatoração: exports longos (mais linhas que a detecção),
com linhas em branco no começo, continuação, mídia, sistema, mensagens fora da janela, teto de trechos, corte por
tamanho no meio da detecção e depois dela, e cabeçalho não reconhecido com 25 linhas.

Esperado em tests/fixtures/caracterizacao/whatsapp-ler-export.json (sintético). Regravar depois de mudança
intencional: GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_whatsapp_caracterizacao.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import whatsapp

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
PALAVRAS = {"M01": ["estatística", " "], "M02": ["corrida", "treino"], "M03": []}
ESPERADO = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "whatsapp-ler-export.json"


def _longo() -> list[str]:
    linhas = ["", "   ", "25/08/2026 07:15 - Pessoa A: treino de agosto fica fora da janela"]
    for dia in range(1, 27):
        linhas.append("%02d/09/2026 07:%02d - Pessoa B: treino %d feito" % (dia, dia, dia))
        if dia % 5 == 0:
            linhas.append("continuação sobre estatística do dia %d" % dia)
        if dia % 7 == 0:
            linhas.append("%02d/09/2026 08:00 - Pessoa C: <Mídia oculta>" % dia)
            linhas.append("%02d/09/2026 08:01 - As mensagens e as chamadas são protegidas com a criptografia" % dia)
    linhas.append("27/09/2026 21:00 - Pessoa D: Estatistica: prova amanhã")
    return linhas


CENARIOS = {
    "longo": (_longo(), {}),
    "longo_truncado_depois_da_deteccao": (_longo(), {"limite_bytes": 1800}),
    "longo_truncado_na_deteccao": (_longo(), {"limite_bytes": 300}),
    "cabecalho_nao_reconhecido": (["linha %d sem data nenhuma" % i for i in range(25)] + _longo(), {}),
    "ios_com_ampm": (
        ["[9/%d/26, %d:05:00 PM] Pessoa: treino de corrida %d" % (d, d % 12 or 12, d) for d in range(1, 28)],
        {},
    ),
}


def test_leitura_do_export_igual_ao_golden_master(tmp_path):
    obtido = {}
    for nome, (linhas, extra) in CENARIOS.items():
        path = tmp_path / (nome + ".txt")
        path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        obtido[nome] = whatsapp.ler_export(path, PALAVRAS, agora=AGORA, **extra)
    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO.read_text(encoding="utf-8"))
