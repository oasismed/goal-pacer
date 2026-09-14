"""goalpacer/migracoes.py e migrar.py: cadeia de versões, backup zip, conferência e volta atrás."""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import migrar as migrar_cli
from goalpacer import frontmatter, io as gpio, migracoes, registro as reg, schema
from goalpacer.base import GpErro

CONFERIR = migrar_cli.conferir_depois_da_migracao

FIXTURES = Path(__file__).resolve().parent / "fixtures"
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def dados(tmp_path):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "diario" / "dados", destino)
    (destino / "inbox" / "whatsapp").mkdir(parents=True, exist_ok=True)
    (destino / "inbox" / "whatsapp" / "export.txt").write_text("mensagem", encoding="utf-8")
    return destino


def v1_para_v2(dados: Path) -> list[str]:
    """Migração de exemplo: grava explícitos os padrões de campos novos e cria a pasta de objetivos."""
    registro = gpio.ler_json(dados / "registro.json")
    registro["sentimentos"] = registro.get("sentimentos") or {}
    gpio.escrever_json(dados / "registro.json", registro)
    (dados / "objetivos").mkdir(exist_ok=True)
    return ["registro.json: sentimentos explícito"]


def test_pasta_em_dia_sem_onboarding_e_mais_nova_que_o_app(dados, tmp_path):
    assert migracoes.versao_da_pasta(dados) == schema.SCHEMA_VERSION
    assert migracoes.migrar(dados, conferir=CONFERIR)["estado"] == "em_dia" and not (dados / "backups").exists()
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    assert migracoes.migrar(vazia, conferir=CONFERIR)["estado"] == "sem_onboarding"
    with pytest.raises(GpErro, match="mais novo que o deste app"):
        migracoes.plano(3, 2)
    with pytest.raises(GpErro, match="sem migração do esquema v1 para v2"):
        migracoes.plano(1, 2, ())


def test_migra_com_backup_e_confere(dados, monkeypatch):
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 2)
    cadeia = (migracoes.Migracao(1, 2, "exemplo", v1_para_v2),)
    simulado = migracoes.migrar(dados, simular=True, migracoes=cadeia, conferir=CONFERIR)
    assert (
        simulado["estado"] == "simulado"
        and simulado["passos"] == ["v1 -> v2: exemplo"]
        and migracoes.versao_da_pasta(dados) == 1
    )
    feito = migracoes.migrar(dados, agora=AGORA, migracoes=cadeia, conferir=CONFERIR)
    assert feito["estado"] == "migrado" and feito["mudancas"] == ["registro.json: sentimentos explícito"]
    assert (
        migracoes.versao_da_pasta(dados) == 2
        and frontmatter.ler_arquivo(dados / "contexto.md")[0]["schema_version"] == 2
    )
    assert reg.carregar(dados)["schema_version"] == 2
    zip_path = Path(feito["backup"])
    assert (
        zip_path.parent == dados / "backups"
        and ((zip_path.stat().st_mode & 0o777) == 0o600 or os.name == "nt")  # no Windows vale a ACL do perfil
        and (((dados / "backups").stat().st_mode & 0o777) == 0o700 or os.name == "nt")
    )
    with zipfile.ZipFile(str(zip_path)) as arquivo:
        nomes = arquivo.namelist()
        assert (
            "contexto.md" in nomes
            and "registro.json" in nomes
            and not any(n.startswith(("inbox/", "backups/")) for n in nomes)
        )
        assert json.loads(arquivo.read("registro.json"))["schema_version"] == 1


def test_falha_volta_a_pasta_ao_backup(dados, monkeypatch):
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 2)
    antes = {p.relative_to(dados).as_posix(): p.read_bytes() for p in dados.rglob("*") if p.is_file()}

    def quebra(pasta: Path) -> list[str]:
        v1_para_v2(pasta)
        (pasta / "metas" / "M01.md").write_text("---\nlixo\n", encoding="utf-8")
        return []

    with pytest.raises(GpErro, match="desfeita, pasta restaurada do backup"):
        migracoes.migrar(dados, agora=AGORA, migracoes=(migracoes.Migracao(1, 2, "quebra", quebra),), conferir=CONFERIR)
    depois = {
        p.relative_to(dados).as_posix(): p.read_bytes()
        for p in dados.rglob("*")
        if p.is_file() and p.relative_to(dados).parts[0] != "backups"
    }
    assert depois == antes and not (dados / "objetivos").exists()  # inclusive o que a migração criou some
    # conferência que falha também desfaz
    with pytest.raises(GpErro):
        migracoes.migrar(
            dados,
            agora=AGORA,
            migracoes=(migracoes.Migracao(1, 2, "ok", v1_para_v2),),
            conferir=lambda pasta: (_ for _ in ()).throw(GpErro(3, "não confere")),
        )
    assert migracoes.versao_da_pasta(dados) == 1


def test_versoes_misturadas_e_backup_hostil(dados, tmp_path):
    registro = gpio.ler_json(dados / "registro.json")
    registro["schema_version"] = 2
    gpio.escrever_json(dados / "registro.json", registro)
    with pytest.raises(GpErro, match="versões misturadas"):
        migracoes.versao_da_pasta(dados)
    hostil = tmp_path / "hostil.zip"
    with zipfile.ZipFile(str(hostil), "w") as arquivo:
        arquivo.writestr("../fora.txt", "x")
    with pytest.raises(GpErro, match="fora da pasta de dados"):
        migracoes.restaurar_backup(dados, hostil)
    assert not (tmp_path / "fora.txt").exists()


def test_poda_mantem_os_backups_mais_novos(dados):
    for dia in range(1, 9):
        migracoes.fazer_backup(dados, "teste", datetime(2026, 9, dia, tzinfo=timezone.utc))
    migracoes.podar_backups(dados)
    assert [p.name[:8] for p in sorted((dados / "backups").glob("*.zip"))] == ["2026090%d" % d for d in range(4, 9)]
