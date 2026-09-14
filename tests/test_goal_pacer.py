"""scripts/goal_pacer.py: o comando único do terminal é uma tabela; cada linha chama um CLI existente."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import goal_pacer
from goalpacer import copy

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_todo_comando_tem_ajuda_e_modulo_com_main():
    import importlib

    for nome, comando in goal_pacer.COMANDOS.items():
        assert callable(importlib.import_module(comando.modulo).main), nome
        for idioma in copy.disponiveis():
            assert copy.texto("comando." + nome, idioma), (nome, idioma)
    assert set(goal_pacer.APELIDOS.values()) <= set(goal_pacer.COMANDOS) | {"versao", "ajuda"}


def test_despacha_com_argumentos_na_ordem_certa(dados_tmp, capsys, monkeypatch):
    shutil.rmtree(dados_tmp)
    shutil.copytree(FIXTURES / "diario" / "dados", dados_tmp)
    assert goal_pacer.main(["validate", "--json"]) == 0  # vira validar.py --json grafo
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert goal_pacer.main(["nao-existe"]) == 3
    assert "Comando nao-existe não existe." in capsys.readouterr().err
    assert goal_pacer.main([]) == 0 and "goal-pacer <comando>" in capsys.readouterr().out
    assert goal_pacer.main(["versao", "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["schema_version"] >= 1 and info["idioma"] == "pt-BR" and info["revisao"] == "dev"
    chamadas = []
    monkeypatch.setattr("status.main", lambda argv=None: chamadas.append(argv) or 0)
    assert goal_pacer.main(["doctor", "--sondar-escrita"]) == 0 and chamadas == [["--doctor", "--sondar-escrita"]]
