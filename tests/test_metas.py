"""goalpacer/metas.py e scripts/metas.py: ajustes validados de metas/M<nn>.md (decisões do check-in)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from goalpacer import frontmatter, metas, schema
from goalpacer.base import EXIT_IO, EXIT_OK, EXIT_VALIDACAO, GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "checkin"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "metas.py"


@pytest.fixture
def dados(tmp_path: Path) -> Path:
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    return destino


def ler(dados: Path, meta: str) -> tuple[dict, str]:
    bruto, corpo = frontmatter.ler_arquivo(dados / "metas" / ("%s.md" % meta))
    return frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])[0], corpo


def test_ajustar_custo_vira_confianca_usuario_e_preserva_corpo(dados):
    antes, corpo = ler(dados, "M01")
    mudou = metas.ajustar(dados, "M01", {"custo_h_semana_escolhido": 1.5})
    depois, corpo_depois = ler(dados, "M01")
    assert depois["custo_h_semana_escolhido"] == 1.5 and corpo_depois == corpo
    assert mudou["custo_h_semana_escolhido"] == [antes["custo_h_semana_escolhido"], 1.5]
    assert depois["confianca"] == "usuario"
    assert metas.ajustar(dados, "M01", {"custo_h_semana_escolhido": 1.5}) == {}


def test_ajustar_prazo_muda_hash_e_recusa_invalidos(dados):
    antes, _ = ler(dados, "M02")
    hash_antes = schema.hash_metas([antes])
    assert metas.ajustar(dados, "M02", {"prazo": "2027-04-12"}) == {"prazo": ["2027-03-01", "2027-04-12"]}
    assert schema.hash_metas([ler(dados, "M02")[0]]) != hash_antes
    texto = (dados / "metas" / "M02.md").read_text(encoding="utf-8")
    for mudancas, trecho in (
        ({"estado": "sumida"}, "ajuste recusado"),
        ({"custo_h_semana_escolhido": "muito"}, "ajuste recusado"),
        ({"criado_em": "2026-01-01T00:00:00-03:00"}, "não ajustáveis"),
    ):
        with pytest.raises(GpErro) as info:
            metas.ajustar(dados, "M02", mudancas)
        assert info.value.codigo == EXIT_VALIDACAO and trecho in info.value.mensagem
    with pytest.raises(GpErro):
        metas.ajustar(dados, "M09", {"prazo": "2027-01-01"})
    with pytest.raises(GpErro):
        metas.ajustar(dados, "../x", {"prazo": "2027-01-01"})
    assert (dados / "metas" / "M02.md").read_text(encoding="utf-8") == texto


def test_aplicar_decisao(dados):
    assert metas.aplicar_decisao(dados, "M01", {"saida": "manter"}) == {}
    custo_antes = ler(dados, "M01")[0]["custo_h_semana_escolhido"]
    assert custo_antes != 1.0
    mudou = metas.aplicar_decisao(dados, "M01", {"saida": "reduzir", "custo": 1})
    assert mudou["custo_h_semana_escolhido"] == [custo_antes, 1.0]
    assert ler(dados, "M01")[0]["custo_h_semana_escolhido"] == 1.0
    metas.aplicar_decisao(dados, "M02", {"saida": "renegociar", "prazo": "2027-05-01"})
    assert ler(dados, "M02")[0]["prazo"].isoformat() == "2027-05-01" and ler(dados, "M02")[0]["prazo_externo"] is True
    for decisao in (
        {"saida": "talvez"},
        {"saida": "reduzir"},
        {"saida": "reduzir", "custo": 0},
        {"saida": "reduzir", "custo": True},
        {"saida": "adiar"},
        {"saida": "adiar", "prazo": "amanhã"},
    ):
        with pytest.raises(GpErro):
            metas.aplicar_decisao(dados, "M02", decisao)


def executar(*args: str, dados: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--dados", str(dados), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_cli(dados):
    proc = executar("--json", "ajustar", "M02", "--prazo", "2027-04-12", "--prazo-externo", "nao", dados=dados)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert json.loads(proc.stdout) == {
        "meta": "M02",
        "mudancas": {"prazo": ["2027-03-01", "2027-04-12"], "prazo_externo": [True, False]},
    }
    proc = executar("ajustar", "M02", "--estado", "arquivada", dados=dados)
    assert proc.returncode == EXIT_OK and proc.stdout.strip() == "M02: estado de ativa para arquivada"
    proc = executar("ajustar", "M02", "--custo", "-1", dados=dados)
    assert proc.returncode == EXIT_VALIDACAO and "ajuste recusado" in proc.stderr
    assert executar(dados=dados).returncode == EXIT_VALIDACAO
    (dados / ".lock").write_text(
        json.dumps({"pid": os.getpid(), "criado_em": "2026-09-28T10:00:00+00:00"}), encoding="utf-8"
    )
    proc = executar("ajustar", "M02", "--custo", "2", dados=dados)
    assert proc.returncode == EXIT_IO
    assert (dados / ".lock").exists()


def test_ajuste_deixa_o_grafo_valido_mesmo_com_bak(dados):
    """Regressão: a escrita atômica deixa metas/Mxx.md.bak, e o validar grafo não pode recusar a pasta por isso."""
    import validar
    from goalpacer.base import EXIT_OK as OK

    metas.ajustar(dados, "M02", {"prazo": "2027-04-12"})
    assert (dados / "metas" / "M02.md.bak").exists()
    resultado = validar.validar_grafo(dados)
    assert resultado.codigo == OK, resultado.erros
