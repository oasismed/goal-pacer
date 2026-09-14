"""Golden master das saídas de texto do ``goal-pacer logs`` antes da refatoração (a suíte só olhava o JSON):
resumo com e sem pasta de dados, eventos com filtro e vazio, trace ausente, e o erro de argumento.

Esperado em tests/fixtures/caracterizacao/logs-textos.txt; instantes reais viram <ts>. Regravar depois de mudança
intencional: GP_REGRAVAR_CARACTERIZACAO=1 python3 -m pytest tests/test_logs_caracterizacao.py
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

import logs as logs_cli
from goalpacer import telemetria

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ESPERADO = FIXTURES / "caracterizacao" / "logs-textos.txt"
RE_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")


def test_textos_do_logs_iguais_ao_golden_master(tmp_path, monkeypatch, capsys, guardar_env):
    regravar = os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1"
    guardar_env("GP_DATA_DIR", "GP_TRACE_ID", "GP_TRACE_PAI")
    dados = tmp_path / "dados"
    shutil.copytree(FIXTURES / "diario" / "dados", dados)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    monkeypatch.setenv("GP_AGORA", "2026-09-29T09:00:00-03:00")
    monkeypatch.setenv("GP_TZ", "America/Sao_Paulo")
    monkeypatch.delenv("GP_TRACE_ID", raising=False)
    telemetria.evento("painel", metodo="GET", rota="/api/painel", status=200, ms=18.0, bytes=0, origem="local")
    telemetria.evento("erro_front", mensagem="x is undefined", arquivo="app.js", linha=3, coluna=0, tela="hoje")
    telemetria.registrar_span("conector", 91000.0, ferramenta="list_events", tentativa=1)
    blocos = []
    for argv in (
        ["resumo"],
        ["eventos"],
        ["eventos", "--tipo", "alerta"],
        ["trace", "nao-existe"],
        ["--dados", str(Path.home() / "Downloads" / "dados"), "resumo"],
    ):
        codigo = logs_cli.main(argv)
        saida = capsys.readouterr()
        blocos.append(
            "$ logs %s -> %d\n%s%s"
            % (" ".join(argv[-2:] if argv[0] == "--dados" else argv), codigo, saida.out, saida.err)
        )
    monkeypatch.setenv("GP_DATA_DIR", str(tmp_path / "nao-existe"))
    codigo = logs_cli.main(["resumo"])
    saida = capsys.readouterr()
    blocos.append("$ logs resumo (sem pasta) -> %d\n%s%s" % (codigo, saida.out, saida.err))
    texto = RE_TS.sub("<ts>", "\n".join(blocos)).replace(str(tmp_path), "<tmp>").replace(str(Path.home()), "<home>")
    if regravar:
        ESPERADO.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert texto == ESPERADO.read_text(encoding="utf-8")
