"""dev/verificar.py: a catraca dos pisos de cobertura (sobe, nunca desce) e a escolha das etapas."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("verificar", RAIZ / "dev" / "verificar.py")
assert _spec and _spec.loader
verificar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verificar)

PISOS = {"total": 90, "modulos": {"scripts/goalpacer/proxy.py": 93, "scripts/web.py": 86}}


def test_pisos_respeitados_nao_reclamam():
    assert verificar.conferir_pisos(90.4, {"scripts/goalpacer/proxy.py": 93.0, "scripts/web.py": 99.0}, PISOS) == []


def test_abaixo_do_piso_diz_onde_e_modulo_sumido_conta_zero():
    abaixo = verificar.conferir_pisos(89.9, {"scripts/goalpacer/proxy.py": 92.5}, PISOS)
    assert abaixo == [
        "total 89.90% < piso 90%",
        "scripts/goalpacer/proxy.py 92.50% < piso 93%",
        "scripts/web.py 0.00% < piso 86%",
    ]


def test_catraca_sobe_ate_o_inteiro_medido_e_nunca_desce():
    novos = verificar.subir_pisos(93.7, {"scripts/goalpacer/proxy.py": 91.0, "scripts/web.py": 88.99}, PISOS)
    assert novos == {"total": 93, "modulos": {"scripts/goalpacer/proxy.py": 93, "scripts/web.py": 88}}


def test_rapido_pula_so_a_suite_e_so_escolhe_as_pedidas():
    rapido = argparse.Namespace(rapido=True, so=None)
    assert [e.nome for e in verificar.ETAPAS if verificar._escolhida(e, rapido)] == [
        "formato",
        "lint",
        "complexidade",
        "tipos",
        "codigo_morto",
        "shell",
        "front",
        "auditoria",
    ]
    so = argparse.Namespace(rapido=False, so=["lint", "testes"])
    assert [e.nome for e in verificar.ETAPAS if verificar._escolhida(e, so)] == ["lint", "testes"]
    assert [e.nome for e in verificar.ETAPAS if not e.bloqueia] == []  # D-09: o ty bloqueia na versão fixada


def test_arquivo_de_pisos_do_repo_tem_a_forma_esperada():
    import json

    pisos = json.loads((RAIZ / "dev" / "pisos-cobertura.json").read_text(encoding="utf-8"))
    assert isinstance(pisos["total"], int) and 0 < pisos["total"] <= 100
    assert all((RAIZ / arquivo).is_file() and 0 < piso <= 100 for arquivo, piso in pisos["modulos"].items())
