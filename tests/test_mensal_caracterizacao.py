"""Caracterização das evidências do mensal antes da refatoração: avisos de cada estado do export do WhatsApp,
leitura fora dos tetos, falha da leitura com o prompt apagado, e limpeza do cache do WhatsApp."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import mensal
import parse_whatsapp
from goalpacer import frontmatter, leitor, offline, prompts
from goalpacer.base import GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mensal"
TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)


@pytest.fixture
def dados(tmp_path, agora_fixo, monkeypatch):
    destino = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", destino)
    monkeypatch.setenv("GP_DATA_DIR", str(destino))
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    return destino


def _evidencias(dados):
    contexto = frontmatter.ler_contexto(dados)
    metas = mensal.prf._ler_metas(dados)
    return mensal.evidencias(
        dados, contexto, metas, modo_offline=True, agora=AGORA, run_id="r-car", registro_proxies=[]
    )


@pytest.mark.parametrize(
    ("status", "aviso"),
    [
        ("nao_reconhecido", "mensal.whatsapp_nao_reconhecido"),
        ("stale", "mensal.whatsapp_stale"),
        ("truncado", "mensal.whatsapp_truncado"),
    ],
)
def test_estado_do_export_vira_aviso(dados, monkeypatch, status, aviso):
    original = parse_whatsapp.processar

    def com_status(*a, **k):
        resultado = original(*a, **k)
        resultado["status"] = status
        return resultado

    monkeypatch.setattr(parse_whatsapp, "processar", com_status)
    saida = _evidencias(dados)
    assert mensal.copy.texto(aviso) in saida["avisos"] and saida["whatsapp"] == status


def test_leitura_fora_dos_tetos_avisa_e_mantem_evidencias(dados, monkeypatch):
    original = leitor.auditar
    monkeypatch.setattr(leitor, "auditar", lambda *a, **k: dict(original(*a, **k), ok=False, fora_da_lista=[]))
    saida = _evidencias(dados)
    assert mensal.copy.texto("mensal.leitura_fora_dos_tetos") in saida["avisos"] and saida["evidencias"] > 0


def test_falha_da_leitura_avisa_sem_evidencias_e_apaga_o_prompt(dados, monkeypatch):
    salvos = []
    salvar = prompts.salvar

    def guardar(*a, **k):
        caminho = salvar(*a, **k)
        salvos.append(caminho)
        return caminho

    def quebra(nome, *_a, **_k):
        if nome == mensal.FIXTURE_LEITURA:
            raise GpErro(4, "conector caiu")
        return {}

    monkeypatch.setattr(prompts, "salvar", guardar)
    monkeypatch.setattr(offline, "resposta", quebra)
    cache = dados / "cache"
    cache.mkdir(exist_ok=True)
    (cache / "whatsapp-2026-09.json").write_text("{}", encoding="utf-8")
    (cache / "whatsapp-2026-09.json.bak").write_text("{}", encoding="utf-8")
    saida = _evidencias(dados)
    assert mensal.copy.texto("mensal.leitura_sem_fontes", classe="GpErro") in saida["avisos"]
    assert saida["evidencias"] == 0 and salvos and not any(p.exists() for p in salvos)
    assert not list(cache.glob("whatsapp-*"))


# --- prosa do plano e geração inteira (antes de dividir gerar e compor_prosa, D-02) ------------------------------------

ESPERADO_PROSA = Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "mensal_prosa.json"


def _res_do_mes(dados, monkeypatch):
    capturado = {}
    original = mensal.compor_prosa

    def espiar(res, existente, **kw):
        capturado["res"] = res
        return original(res, existente, **kw)

    monkeypatch.setattr(mensal, "compor_prosa", espiar)
    saida = mensal.gerar(dados, modo_offline=True, agora=AGORA, run_id="r-car")
    monkeypatch.setattr(mensal, "compor_prosa", original)
    return capturado["res"], saida


def _cenarios_de_prosa(res, monkeypatch):
    from goalpacer import balanco, proxy, schema

    nomes = balanco.nomes_blocos_prosa(res)
    template = balanco.prosa_template(res)
    existente = {nomes[0]: "Prosa guardada.", nomes[1]: "Refazer isto " + schema.MARCADOR_ATUALIZAR}
    kw = {"evidencias_lista": [], "run_id": "r-car", "modo_offline": True, "registro_proxies": []}
    saidas = {}

    def viva(gerado):
        monkeypatch.setattr(mensal, "prosa_viva", lambda *_a, **_k: gerado)

    viva({n: "Texto novo para %s." % n for n in nomes})
    saidas["regenerar_viva"] = mensal.compor_prosa(res, existente, regenerar=True, viva=True, **kw)
    saidas["manter_viva"] = mensal.compor_prosa(res, existente, regenerar=False, viva=True, **kw)
    saidas["sem_viva"] = mensal.compor_prosa(res, existente, regenerar=True, viva=False, **kw)
    viva({nomes[0]: "x" * 5000, nomes[1]: "Ela está atrasada de novo.", nomes[-1]: "  espaços   \n  e quebra  "})
    saidas["tetos_e_tom"] = mensal.compor_prosa(res, {}, regenerar=True, viva=True, **kw)

    def falha(*_a, **_k):
        raise GpErro(3, "prosa quebrou")

    monkeypatch.setattr(mensal, "prosa_viva", falha)
    saidas["erro_vira_template"] = mensal.compor_prosa(res, {}, regenerar=True, viva=True, **kw)

    def limite(*_a, **_k):
        raise proxy.RateLimited("429")

    monkeypatch.setattr(mensal, "prosa_viva", limite)
    with pytest.raises(proxy.RateLimited):
        mensal.compor_prosa(res, {}, regenerar=True, viva=True, **kw)
    return {"nomes": nomes, "template": template, "saidas": saidas}


def test_prosa_e_geracao_iguais_ao_golden_master(dados, monkeypatch):
    res, saida = _res_do_mes(dados, monkeypatch)
    plano = (dados / saida["arquivo"]).read_text(encoding="utf-8")
    obtido = {
        "prosa": _cenarios_de_prosa(res, monkeypatch),
        "saida": {k: v for k, v in saida.items() if k != "run_id"},
        "plano": plano.split("\n"),
        "semanas": {p: (dados / p).read_text(encoding="utf-8").split("\n") for p in saida["semanas"]},
    }
    import json
    import os

    texto = json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO_PROSA.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert json.loads(texto) == json.loads(ESPERADO_PROSA.read_text(encoding="utf-8"))
