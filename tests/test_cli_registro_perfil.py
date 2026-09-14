"""scripts/registro.py e scripts/perfil.py pela linha de comando (T2, análise de 13/09): ver, checkin, progresso, recuperar, lock."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import perfil as perfil_cli
import registro as registro_cli
from goalpacer import registro as reg

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def copia(tmp_path: Path) -> Path:
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "diario" / "dados", destino)
    return destino


def test_registro_cli_ver_checkin_progresso_e_lock(tmp_path, capsys, agora_fixo, guardar_env):
    guardar_env("GP_DATA_DIR")
    dados = copia(tmp_path)
    assert registro_cli.main([]) == 3
    capsys.readouterr()
    assert registro_cli.main(["--dados", str(dados), "ver"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1
    assert registro_cli.main(["--dados", str(dados), "checkin", "D-2026-09-26-01", "nao_feita"]) == 0
    assert reg.carregar(dados)["checkins"]["D-2026-09-26-01"]["estado"] == "nao_feita"
    assert registro_cli.main(["--dados", str(dados), "progresso", "M01", "35"]) == 0
    assert reg.ultimo_progresso_declarado(reg.carregar(dados), "M01") == 35.0
    assert registro_cli.main(["--dados", str(dados), "progresso", "M01", "140"]) == 3
    assert registro_cli.main(["--dados", str(dados), "lock"]) == 0 and (dados / ".lock").exists()
    assert registro_cli.main(["--dados", str(dados), "unlock"]) == 0 and not (dados / ".lock").exists()
    assert registro_cli.main(["--dados", str(dados), "unlock"]) == 0


def test_registro_cli_recuperar(tmp_path, capsys, guardar_env):
    guardar_env("GP_DATA_DIR")
    dados = copia(tmp_path)
    assert registro_cli.main(["--dados", str(dados), "recuperar"]) == 2  # íntegro e sem .bak: nada a restaurar
    bom = (dados / "registro.json").read_text(encoding="utf-8")
    (dados / "registro.json.bak").write_text(bom, encoding="utf-8")
    (dados / "registro.json").write_text("{quebrado", encoding="utf-8")
    assert registro_cli.main(["--dados", str(dados), "recuperar"]) == 0
    assert json.loads((dados / "registro.json").read_text(encoding="utf-8"))["schema_version"] == 1
    assert "restaurado do .bak: registro.json" in capsys.readouterr().err


def test_perfil_cli_calcula_grava_e_mostra(tmp_path, capsys, agora_fixo, guardar_env):
    guardar_env("GP_DATA_DIR")
    dados = copia(tmp_path)
    assert perfil_cli.main(["--dados", str(dados), "--nao-gravar", "--json"]) == 0
    calculado = json.loads(capsys.readouterr().out)
    assert set(calculado["metas"])
    assert perfil_cli.main(["--dados", str(dados)]) == 0
    saida = capsys.readouterr().out
    assert saida.startswith("M01 ") and (dados / "perfil.json").exists()
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert perfil_cli.main(["--dados", str(vazio)]) == 2


def test_registro_cli_arquivar_checkin_recusado_e_feita_com_duracao(tmp_path, capsys, agora_fixo, guardar_env):
    """Caracterização antes da refatoração do main: os ramos de saída que a suíte não percorria."""
    guardar_env("GP_DATA_DIR")
    dados = copia(tmp_path)
    base = ["--dados", str(dados)]
    assert registro_cli.main([*base, "arquivar"]) == 0
    assert capsys.readouterr().err == "nada a arquivar\n"
    assert registro_cli.main([*base, "--json", "arquivar"]) == 0
    assert json.loads(capsys.readouterr().out) == {}
    argv = [*base, "--json", "checkin", "D-2026-09-26-01", "feita", "--origem", "confirmado"]
    assert registro_cli.main([*argv, "--meta", "M01", "--duracao-h", "1", "--duracao-real-h", "1.5"]) == 0
    assert json.loads(capsys.readouterr().out)["duracao_real_h"] == 1.5
    assert [f["task_id"] for f in reg.carregar(dados)["feitas"]["M01"]].count("D-2026-09-26-01") == 1
    assert registro_cli.main([*base, "checkin", "D-2026-09-26-01", "movida", "--origem", "inferido"]) == 2
    assert "transição recusada: D-2026-09-26-01 já está confirmado" in capsys.readouterr().err
    for arquivo in dados.glob("registro.json*"):
        arquivo.write_text("{quebrado", encoding="utf-8")  # sem .bak bom para recuperar
    codigo = registro_cli.main([*base, "ver"])
    assert codigo != 0 and capsys.readouterr().err.startswith("erro: ")
