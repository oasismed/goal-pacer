"""Golden master da leitura de coach antes da refatoração: leituras por meta e por objetivo da pasta do demo
(seis metas, três objetivos, sentimentos, marcos, evidências, cinco semanas de histórico) mais uma meta arquivada,
uma meta sem objetivo e um objetivo cadastrado sem metas.

Esperado em tests/fixtures/caracterizacao/leitura-demo.json. Regravar depois de mudança intencional:
GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_leitura_caracterizacao.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from goalpacer import clock, frontmatter, leitura as gpleitura

ESPERADO = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "leitura-demo.json"


def test_leitura_do_demo_igual_ao_golden_master(tmp_path, monkeypatch):
    import demo_painel

    regravar = os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1"
    for var in [v for v in os.environ if v.startswith("GP_") and v != "GP_PLATAFORMA"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    dados = demo_painel.preparar(tmp_path)
    for var, valor in demo_painel.ambiente(tmp_path).items():
        monkeypatch.setenv(var, valor)
    for meta_id, mudanca in (("M04", {"estado": "arquivada"}), ("M05", {"objetivo": ""})):
        path = dados / "metas" / ("%s.md" % meta_id)
        fm, corpo = frontmatter.ler_arquivo(path)
        frontmatter.escrever_arquivo(path, dict(fm, **mudanca), corpo)
    (dados / "objetivos" / "O04.md").write_text(
        (dados / "objetivos" / "O03.md")
        .read_text(encoding="utf-8")
        .replace("O03", "O04")
        .replace("Ser lido", "Aprender piano"),
        encoding="utf-8",
    )
    b = gpleitura.leitura(dados, clock.parse_iso(demo_painel.AGORA_PAINEL))
    obtido = {"leituras": b["leituras"], "objetivos": b["objetivos"], "semana": b["semana"], "mes": b["mes"]}
    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    if regravar:
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO.read_text(encoding="utf-8"))
