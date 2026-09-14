"""Testes de goalpacer.schema: versão, enums, regexes, validar, defaults, hash, md, seções.

Dados sintéticos com a forma dos arquivos reais (design doc, "Pasta de dados
do usuário"); nada de conteúdo de usuário.
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import goalpacer
from goalpacer import schema
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

ARQUIVOS_ESPERADOS = (
    "metas",
    "objetivo",
    "fonte_pesquisa",
    "contexto",
    "plano",
    "sinais",
    "semana",
    "dia",
    "task",
    "registro",
    "geracao",
    "checkin",
    "feita",
    "progresso_declarado",
    "sentimento",
    "nota_recusada",
    "perfil",
    "perfil_meta",
    "perfil_janela",
    "perfil_preferencias",
    "cache_calendar",
    "calendario",
    "evento",
    "ops",
    "op",
    "rascunho_onboarding",
)

UTC = timezone.utc
CAL_METAS = "abc123@group.calendar.google.com"
CAL_PRIMARIO = "pessoa@exemplo.test"


def meta_valida() -> dict:
    return {
        "id": "M01",
        "titulo": "Meta sintética",
        "horizonte": "trimestre",
        "prazo": date(2026, 12, 31),
        "prazo_externo": True,
        "estado": "ativa",
        "custo_h_semana_min": 3.0,
        "custo_h_semana_max": 6.0,
        "custo_h_semana_escolhido": 4.0,
        "semanas_pesquisa": 12,
        "confianca": "media",
        "fonte": "fontes/M01.md",
        "palavras_chave": ["alfa", "beta", "gama"],
        "criado_em": datetime(2026, 9, 12, 10, 0, tzinfo=UTC),
    }


def contexto_valido() -> dict:
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "instalacao_id": "inst-teste-01",
        "timezone": "America/Sao_Paulo",
        "calendar_id_metas": CAL_METAS,
        "calendar_id_primario": CAL_PRIMARIO,
        "email_proprio": CAL_PRIMARIO,
        "fontes_ativas": ["gmail", "notion"],
        "horario_util_seg_sex": "09:00-18:00",
        "horario_util_sab": "",
        "lembretes": "nao",
    }


def task_valida(sufixo: str = "01") -> dict:
    inicio = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
    return {
        "id": "D-2026-09-28-" + sufixo,
        "titulo": "Bloco sintético",
        "meta": "M01",
        "semana": "2026-W40",
        "inicio": inicio.isoformat(),
        "fim": (inicio + timedelta(hours=1)).isoformat(),
        "duracao_h": 1.0,
        "porque": "M1 pede 4h nesta semana; janela livre das 9h",
        "efeito": "se feita: M1 41% → 44%",
        "estado": "planejada",
        "origem": "inferido",
        "calendar_event_id": "evt-01",
        "calendar_id": CAL_METAS,
        "atualizado_em": "2026-09-28T07:00:00Z",
    }


def geracao_valida(run_id: str = "r1") -> dict:
    return {
        "run_id": run_id,
        "modo": "diario",
        "data": "2026-09-28",
        "ts": "2026-09-28T07:05:00-03:00",
        "exit_code": 0,
        "duracao_s": 12.5,
        "tokens": {"input": 10, "output": 5},
        "sessoes": ["sess-1", "sess-2"],
        "email": "enviado",
    }


def registro_valido() -> dict:
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "geracoes": {"r1": geracao_valida("r1")},
        "checkins": {
            "D-2026-09-28-01": {
                "estado": "feita",
                "origem": "confirmado",
                "ts": "2026-09-28T19:00:00-03:00",
                "duracao_real_h": 1.5,
            },
            "D-2026-09-28-02": {"estado": "feita", "origem": "presumido", "ts": "2026-09-29T07:00:00-03:00"},
        },
        "feitas": {
            "M01": [
                {"task_id": "D-2026-09-28-01", "duracao_h": 1.0, "duracao_real_h": 1.5, "origem": "confirmado"},
                {"task_id": "D-2026-09-28-02", "duracao_h": 1.0, "origem": "presumido"},
            ]
        },
        "progresso": {"M01": [{"declarado_pct": 50, "ts": "2026-09-28T19:05:00-03:00"}]},
        "notas_recusadas": [{"texto": "sem blocos antes das 9h", "ts": "2026-09-28T19:06:00-03:00"}],
    }


def perfil_valido() -> dict:
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "gerado_em": "2026-09-28T07:00:00Z",
        "n_confirmadas": 7,
        "metas": {
            "M01": {
                "progresso_pct": 41.0,
                "ritmo_esperado_pct": 45.0,
                "delta": -4.0,
                "horas_confirmadas": 19.5,
                "fator_duracao": 1.2,
            }
        },
        "janelas": {"seg-manha": {"taxa_conclusao": 0.8, "n": 6}, "sab-tarde": {"taxa_conclusao": 0.0, "n": 1}},
        "preferencias": {"bloco_medio_h": 1.25, "taxa_por_duracao": {"curto": 0.9, "longo": 0.4}},
    }


def evento_valido(**extra) -> dict:
    evento = {
        "id": "evt-1",
        "calendar_id": CAL_PRIMARIO,
        "start": "2026-09-28T09:00:00-03:00",
        "end": "2026-09-28T10:00:00-03:00",
        "all_day": False,
        "status": "confirmed",
        "transparency": "opaque",
        "self_response": "",
        "event_type": "default",
        "recurring_event_id": "",
        "summary": None,
        "description": None,
        "gp_key": None,
    }
    evento.update(extra)
    return evento


def cache_valido() -> dict:
    return {
        "calendar_id_metas": CAL_METAS,
        "janela_inicio": "2026-09-28T00:00:00-03:00",
        "janela_fim": "2026-09-29T00:00:00-03:00",
        "gerado_em": "2026-09-28T07:00:00-03:00",
        "run_id": "r1",
        "calendarios": [
            {"id": CAL_PRIMARIO, "summary": "Pessoal", "time_zone": "America/Sao_Paulo"},
            {"id": CAL_METAS, "summary": "Metas"},
        ],
        "eventos": [
            evento_valido(),
            evento_valido(
                id="evt-2",
                calendar_id=CAL_METAS,
                summary="[GP] Bloco",
                description="porquê\ngp:D-2026-09-28-01/inst-teste-01",
                gp_key="gp:D-2026-09-28-01/inst-teste-01",
            ),
            evento_valido(id="evt-3", start="2026-09-29", end="2026-09-30", all_day=True, transparency="transparent"),
        ],
    }


def ops_validas() -> dict:
    return {
        "run_id": "r1",
        "calendar_id_metas": CAL_METAS,
        "gerado_em": "2026-09-28T07:00:00-03:00",
        "ops": [
            {
                "op": "create",
                "task_id": "D-2026-09-28-01",
                "calendar_id": CAL_METAS,
                "corpo": {"summary": "[GP] Bloco", "start": {"dateTime": "x"}},
                "status": "ok",
                "event_id_resultado": "evt-9",
            },
            {
                "op": "update",
                "task_id": "D-2026-09-28-02",
                "calendar_id": CAL_METAS,
                "calendar_event_id": "evt-2",
                "corpo": {"description": "..."},
                "status": "erro",
                "mensagem": "Insufficient scope",
            },
            {"op": "delete", "task_id": "D-2026-09-27-03", "calendar_id": CAL_METAS, "calendar_event_id": "evt-3"},
        ],
    }


def test_schema_version_e_reexport():
    assert schema.SCHEMA_VERSION == 1
    assert type(schema.SCHEMA_VERSION) is int
    assert goalpacer.SCHEMA_VERSION is schema.SCHEMA_VERSION
    assert goalpacer.__version__ == "0.1.0"


def test_estados_origens_e_transicoes_proibidas():
    assert schema.ESTADOS == (
        "planejada",
        "feita",
        "movida",
        "reagendada",
        "apagada",
        "nao_feita",
        "sem_sinal",
        "cancelada",
    )
    assert schema.ORIGENS == ("inferido", "confirmado", "presumido", "prazo")
    assert len(set(schema.ESTADOS)) == len(schema.ESTADOS)
    assert len(set(schema.ORIGENS)) == len(schema.ORIGENS)
    for atual, nova in schema.TRANSICOES_PROIBIDAS:
        assert atual in schema.ORIGENS and nova in schema.ORIGENS
    # inferido/presumido nunca sobrescrevem confirmado; o resto é permitido.
    assert ("confirmado", "inferido") in schema.TRANSICOES_PROIBIDAS
    assert ("confirmado", "presumido") in schema.TRANSICOES_PROIBIDAS
    assert ("confirmado", "confirmado") not in schema.TRANSICOES_PROIBIDAS
    assert ("inferido", "confirmado") not in schema.TRANSICOES_PROIBIDAS
    assert ("presumido", "confirmado") not in schema.TRANSICOES_PROIBIDAS
    assert schema.HORIZONTES == ("trimestre", "semestre", "ano")
    assert schema.ESTADOS_META == ("ativa", "pausada", "concluida", "vencida", "arquivada")
    assert schema.CONFIANCAS == ("alta", "media", "baixa", "usuario")
    assert schema.FONTES == ("gmail", "whatsapp", "notion", "drive")
    assert schema.LEMBRETES == ("sim", "nao")
    assert schema.OPS == ("create", "update", "delete")


@pytest.mark.parametrize(
    "tipo, valor",
    [
        ("meta", "M01"),
        ("meta", "M99"),
        ("mes", "2026-09"),
        ("mes", "2026-12"),
        ("semana", "2026-W01"),
        ("semana", "2026-W40"),
        ("semana", "2026-W53"),
        ("dia", "2026-09-28"),
        ("dia", "2026-02-29"),
        ("task", "D-2026-09-28-01"),
        ("task", "D-2026-12-31-99"),
    ],
)
def test_regexes_valores_validos(tipo, valor):
    assert schema.REGEX_POR_TIPO_ID[tipo].match(valor)
    assert schema.validar_id(tipo, valor) is True


@pytest.mark.parametrize(
    "tipo, valor",
    [
        ("meta", "M1"),
        ("meta", "M001"),
        ("meta", "m01"),
        ("meta", "M01 "),
        ("meta", "XM01"),
        ("mes", "2026-9"),
        ("mes", "2026-13"),
        ("mes", "2026-00"),
        ("mes", "2026-09-01"),
        ("semana", "2026-W0"),
        ("semana", "2026-W54"),
        ("semana", "2026-W00"),
        ("semana", "2026-40"),
        ("semana", "2026-w40"),
        ("dia", "2026-9-28"),
        ("dia", "2026-09-32"),
        ("dia", "2026-13-01"),
        ("dia", "28/09/2026"),
        ("dia", "2026-09-28T07:00:00"),
        ("task", "D-2026-09-28-1"),
        ("task", "D-2026-09-28-001"),
        ("task", "2026-09-28-01"),
        ("task", "D-2026-09-28-01\n"),
    ],
)
def test_regexes_valores_invalidos(tipo, valor):
    assert schema.REGEX_POR_TIPO_ID[tipo].match(valor) is None  # \Z: nem com "\n" no fim
    assert schema.validar_id(tipo, valor) is False


def test_validar_id_por_tipo():
    assert set(schema.REGEX_POR_TIPO_ID) == {"meta", "objetivo", "mes", "semana", "dia", "task"}
    assert schema.validar_id("meta", 1) is False
    assert schema.validar_id("meta", None) is False
    assert schema.validar_id("task", ["D-2026-09-28-01"]) is False
    with pytest.raises(GpErro) as info:
        schema.validar_id("bloco", "M01")
    assert info.value.codigo == EXIT_VALIDACAO
    assert schema.RE_HORARIO_UTIL.match("09:00-18:00")
    assert schema.RE_HORARIO_UTIL.match("9:00-18:00") is None
    assert schema.RE_HORARIO_UTIL.match("09:00-24:00") is None


def test_regex_gp_key_e_janela_perfil():
    assert schema.RE_GP_KEY.match("gp:D-2026-09-28-01/inst-teste-01").groups() == ("D-2026-09-28-01", "inst-teste-01")
    for ruim in (
        "gp:D-2026-09-28-01/",
        "gp:D-2026-9-28-01/x",
        "GP:D-2026-09-28-01/x",
        "gp:D-2026-09-28-01/x y",
        "gp:D-2026-09-28-01/x\n",
        "gp:D-2026-09-28-01/" + "a" * 65,
        "gp:D-2026-09-28-01/-x",
    ):
        assert schema.RE_GP_KEY.match(ruim) is None, ruim
    assert schema.REGEX_POR_FORMATO["gp_key"] is schema.RE_GP_KEY
    assert schema.RE_JANELA_PERFIL.match("seg-manha") and schema.RE_JANELA_PERFIL.match("dom-noite")
    assert schema.RE_JANELA_PERFIL.match("segunda-manha") is None
    assert schema.RE_JANELA_PERFIL.match("seg-madrugada") is None
    assert schema.RE_INSTALACAO_ID.match("inst-teste-01") and schema.RE_INSTALACAO_ID.match("-x") is None


def test_esquemas_todos_os_arquivos_e_tipos_conhecidos():
    assert tuple(schema.ESQUEMAS) == ARQUIVOS_ESPERADOS
    assert set(schema.CAMINHOS) == set(ARQUIVOS_ESPERADOS)
    assert schema.verificar_esquemas() == []
    for arquivo, campos in schema.ESQUEMAS.items():
        assert campos, arquivo
        for campo in campos:
            assert isinstance(campo, schema.Campo)
            assert campo.tipo in schema.TIPOS
            if campo.tipo == "enum":
                assert campo.enum
            if campo.obrigatorio:
                assert campo.default is None
            if arquivo in schema.ARQUIVOS_FRONTMATTER:
                assert campo.tipo not in ("dict", "list_dict"), (arquivo, campo.nome)


def test_campos_do_design_doc():
    """Os campos batem com a seção "Pasta de dados do usuário" do design doc."""
    por_nome = {a: {c.nome: c for c in cs} for a, cs in schema.ESQUEMAS.items()}
    metas = por_nome["metas"]
    assert set(metas) == {
        "id",
        "titulo",
        "horizonte",
        "prazo",
        "prazo_externo",
        "estado",
        "custo_h_semana_min",
        "custo_h_semana_max",
        "custo_h_semana_escolhido",
        "semanas_pesquisa",
        "confianca",
        "fonte",
        "palavras_chave",
        "criado_em",
        "objetivo",
        "impacto",
    }
    assert (
        metas["impacto"].enum == schema.IMPACTOS
        and metas["impacto"].default == "importante"
        and metas["impacto"].no_hash
    )
    assert metas["objetivo"].default == "" and metas["objetivo"].no_hash
    assert metas["custo_h_semana_escolhido"].obrigatorio and metas["custo_h_semana_escolhido"].tipo == "float"
    assert metas["semanas_pesquisa"].obrigatorio and metas["semanas_pesquisa"].tipo == "int"
    assert metas["estado"].enum == schema.ESTADOS_META and metas["estado"].default == "ativa"
    assert metas["confianca"].enum == schema.CONFIANCAS
    assert metas["prazo"].tipo == "date"
    for nome in ("status", "custo_h", "progresso_declarado_pct"):
        assert nome not in metas  # progresso vive em registro/perfil; custo é por semana
    contexto = por_nome["contexto"]
    assert {
        "schema_version",
        "instalacao_id",
        "idioma",
        "timezone",
        "horario_util_seg_sex",
        "horario_util_sab",
        "horario_util_dom",
        "buffer_min",
        "calendar_id_metas",
        "calendar_id_primario",
        "calendarios_lidos",
        "email_proprio",
        "email_alias",
        "fontes_ativas",
        "lembretes",
        "restricoes_horario",
        "pessoas",
    } <= set(contexto)
    assert contexto["idioma"].default == "pt-BR"
    assert contexto["buffer_min"].default == 10
    assert contexto["lembretes"].enum == schema.LEMBRETES and contexto["lembretes"].default == "nao"
    assert contexto["horario_util_seg_sex"].default == "08:00-19:00"
    assert contexto["horario_util_sab"].default == "09:00-13:00"
    assert contexto["horario_util_dom"].default == ""
    assert contexto["fontes_ativas"].enum == schema.FONTES
    assert contexto["tetos_gmail_threads"].default == 15
    assert contexto["tetos_gmail_threads_inteiras"].default == 3
    assert contexto["tetos_notion_paginas"].default == 5
    assert contexto["tetos_drive_arquivos"].default == 5
    assert contexto["tetos_drive_caracteres"].default == 4000
    assert set(por_nome["plano"]) == {"mes", "hash_metas", "hash_numeros", "fontes", "gerado_em", "run_id"}
    assert set(por_nome["semana"]) == {"semana", "mes", "gerado_em", "run_id"}
    assert set(por_nome["dia"]) == {
        "data",
        "run_id",
        "resumo_confirmadas",
        "resumo_presumidas",
        "resumo_movidas",
        "decisao_pendente",
        "motivo",
    }
    task = por_nome["task"]
    assert set(task) == {
        "id",
        "titulo",
        "meta",
        "semana",
        "inicio",
        "fim",
        "duracao_h",
        "porque",
        "efeito",
        "estado",
        "origem",
        "calendar_event_id",
        "calendar_id",
        "duracao_real_h",
        "atualizado_em",
    }
    assert task["estado"].enum == schema.ESTADOS
    assert task["origem"].enum == schema.ORIGENS
    registro = por_nome["registro"]
    assert set(registro) == {
        "schema_version",
        "geracoes",
        "checkins",
        "feitas",
        "progresso",
        "notas_recusadas",
        "sentimentos",
        "respostas_email",
    }
    assert "tasks" not in registro  # o estado dos blocos vive em dias/ e em checkins
    assert registro["notas_recusadas"].tipo == "list_dict"
    assert set(por_nome["perfil"]) == {
        "schema_version",
        "gerado_em",
        "n_confirmadas",
        "metas",
        "janelas",
        "preferencias",
    }
    assert set(por_nome["perfil_meta"]) == {
        "progresso_pct",
        "progresso_presumido_pct",
        "ritmo_esperado_pct",
        "delta",
        "horas_confirmadas",
        "horas_presumidas_nao_contadas",
        "fator_duracao",
        "h_semana_real",
    }
    assert por_nome["perfil_meta"]["fator_duracao"].default == 1.0
    evento = por_nome["evento"]
    assert set(evento) == {
        "id",
        "calendar_id",
        "start",
        "end",
        "all_day",
        "created",
        "updated",
        "status",
        "transparency",
        "self_response",
        "event_type",
        "recurring_event_id",
        "summary",
        "description",
        "gp_key",
    }
    assert "reminders" not in " ".join(c.nome for cs in schema.ESQUEMAS.values() for c in cs)
    op = por_nome["op"]
    assert op["op"].enum == schema.OPS and op["status"].enum == schema.STATUS_OP and not op["status"].obrigatorio
    assert set(por_nome["rascunho_onboarding"]) == {"versao", "atualizado_em", "respostas"}


def test_campos_hash_metas():
    # Design doc: hash_metas cobre só titulo, prazo, prazo_externo, horizonte (+ id como chave).
    assert schema.campos_hash("metas") == ["id", "titulo", "horizonte", "prazo", "prazo_externo"]
    assert set(schema.HASH_METAS_CAMPOS) <= set(schema.campos_hash("metas"))
    assert schema.campos_hash("plano") == ["mes", "hash_metas", "hash_numeros", "fontes", "gerado_em", "run_id"]
    with pytest.raises(GpErro):
        schema.campos_hash("nada")


def test_hash_metas_ignora_custo_estado_e_ordem():
    a = meta_valida()
    b = dict(meta_valida(), id="M02", titulo="Outra")
    h = schema.hash_metas([a, b])
    assert len(h) == schema.HASH_METAS_TAMANHO and h == h.lower()
    assert schema.hash_metas([b, a]) == h  # ordem não importa
    assert (
        schema.hash_metas(
            [
                dict(
                    a,
                    custo_h_semana_escolhido=9.0,
                    estado="arquivada",
                    confianca="usuario",
                    palavras_chave=[],
                    fonte="",
                ),
                b,
            ]
        )
        == h
    )  # no_hash não muda
    assert schema.hash_metas([dict(a, titulo="Mudou"), b]) != h
    assert schema.hash_metas([dict(a, prazo=date(2027, 1, 1)), b]) != h
    assert schema.hash_metas([dict(a, prazo="2026-12-31"), b]) == h  # date e string ISO são a mesma coisa
    assert schema.hash_metas([dict(a, prazo_externo=False), b]) != h
    assert schema.hash_metas([dict(a, horizonte="ano"), b]) != h
    assert schema.hash_metas([a]) != h  # meta a menos
    assert schema.hash_metas([]) == schema.hash_metas(iter([]))


def test_validar_registro_obrigatorios():
    assert schema.validar_registro("metas", meta_valida()) == []
    assert schema.validar_registro("contexto", contexto_valido()) == []
    assert schema.validar_registro("task", task_valida()) == []
    assert schema.validar_registro("registro", registro_valido()) == []
    assert schema.validar_registro("registro", {"schema_version": 1}) == []
    assert schema.validar_registro("perfil", perfil_valido()) == []
    assert schema.validar_registro("cache_calendar", cache_valido()) == []
    assert schema.validar_registro("ops", ops_validas()) == []
    assert (
        schema.validar_registro(
            "rascunho_onboarding",
            {"versao": 1, "atualizado_em": "2026-09-28T07:00:00Z", "respostas": {"metas": [1, {"x": None}]}},
        )
        == []
    )
    sem_titulo = meta_valida()
    del sem_titulo["titulo"]
    assert schema.validar_registro("metas", sem_titulo) == ["titulo: obrigatório"]
    com_none = meta_valida()
    com_none["custo_h_semana_escolhido"] = None
    assert schema.validar_registro("metas", com_none) == ["custo_h_semana_escolhido: obrigatório"]
    vazio = meta_valida()
    vazio["titulo"] = "   "
    assert schema.validar_registro("metas", vazio) == ["titulo: vazio"]
    erros = schema.validar_registro("metas", {})
    obrigatorios = [c.nome for c in schema.ESQUEMAS["metas"] if c.obrigatorio]
    assert erros == ["%s: obrigatório" % nome for nome in obrigatorios]
    # Opcional ausente ou None não é erro.
    opcional = meta_valida()
    opcional["custo_h_semana_min"] = None
    del opcional["palavras_chave"]
    del opcional["fonte"]
    assert schema.validar_registro("metas", opcional) == []


def test_validar_registro_enum():
    meta = meta_valida()
    meta["horizonte"] = "mensal"
    (erro,) = schema.validar_registro("metas", meta)
    assert erro.startswith("horizonte: ") and "trimestre, semestre, ano" in erro
    meta = meta_valida()
    meta["estado"] = "suspensa"
    assert schema.validar_registro("metas", meta) == [
        "estado: 'suspensa' fora de ativa, pausada, concluida, vencida, arquivada"
    ]
    meta = meta_valida()
    meta["confianca"] = "pesquisa"
    assert schema.validar_registro("metas", meta)[0].startswith("confianca: ")
    contexto = contexto_valido()
    contexto["fontes_ativas"] = ["gmail", "telegram"]
    (erro,) = schema.validar_registro("contexto", contexto)
    assert erro.startswith("fontes_ativas: ") and "telegram" in erro
    contexto["fontes_ativas"] = ["gmail", "gmail"]
    assert schema.validar_registro("contexto", contexto) == ["fontes_ativas: itens repetidos"]
    contexto = contexto_valido()
    contexto["lembretes"] = True
    assert schema.validar_registro("contexto", contexto) == ["lembretes: esperado str, veio bool"]
    contexto["lembretes"] = "talvez"
    assert schema.validar_registro("contexto", contexto) == ["lembretes: 'talvez' fora de sim, nao"]
    task = task_valida()
    task["estado"] = "feita?"
    task["origem"] = "chute"
    erros = schema.validar_registro("task", task)
    assert [e.split(":")[0] for e in erros] == ["estado", "origem"]


def test_validar_registro_tipo():
    casos = [
        ("custo_h_semana_escolhido", "4", "esperado float, veio str"),
        ("custo_h_semana_escolhido", True, "esperado float, veio bool"),
        ("semanas_pesquisa", 12.5, "esperado int, veio float"),
        ("prazo_externo", "sim", "esperado bool, veio str"),
        ("prazo_externo", 1, "esperado bool, veio int"),
        ("prazo", datetime(2026, 12, 31, tzinfo=UTC), "esperado date, veio datetime"),
        ("prazo", "31/12/2026", "data inválida"),
        ("prazo", "2026-02-30", "data inválida"),
        ("criado_em", "2026-09-12", "datetime inválido"),
        ("criado_em", date(2026, 9, 12), "esperado datetime, veio date"),
        ("criado_em", "ontem", "datetime inválido"),
        ("palavras_chave", "alfa", "esperado list, veio str"),
        ("palavras_chave", ["alfa", 2], "não é str"),
        ("titulo", 5, "esperado str, veio int"),
    ]
    for campo, valor, trecho in casos:
        meta = meta_valida()
        meta[campo] = valor
        erros = schema.validar_registro("metas", meta)
        assert len(erros) == 1, (campo, valor, erros)
        assert erros[0].startswith(campo + ": ") and trecho in erros[0], erros
    # Aceitos: int onde é float, date como string ISO, datetime nativo ou string com Z.
    meta = meta_valida()
    meta["custo_h_semana_escolhido"] = 4
    meta["prazo"] = "2026-12-31"
    meta["criado_em"] = "2026-09-12T10:00:00Z"
    assert schema.validar_registro("metas", meta) == []
    contexto = contexto_valido()
    contexto["buffer_min"] = 15.5
    assert schema.validar_registro("contexto", contexto) == ["buffer_min: esperado int, veio float"]
    contexto["buffer_min"] = True
    assert schema.validar_registro("contexto", contexto) == ["buffer_min: esperado int, veio bool"]
    registro = registro_valido()
    registro["checkins"] = []
    registro["notas_recusadas"] = {}
    assert schema.validar_registro("registro", registro) == [
        "checkins: esperado dict, veio list",
        "notas_recusadas: esperado list, veio dict",
    ]


def test_validar_registro_ids_e_formatos():
    meta = meta_valida()
    meta["id"] = "M1"
    assert schema.validar_registro("metas", meta) == ["id: 'M1' não tem o formato meta"]
    task = task_valida()
    task["id"] = "D-2026-09-28-1"
    task["meta"] = "meta1"
    task["semana"] = "2026-40"
    erros = schema.validar_registro("task", task)
    assert [e.split(":")[0] for e in erros] == ["id", "meta", "semana"]
    plano = {
        "mes": "2026-9",
        "hash_metas": "abc",
        "hash_numeros": "def",
        "gerado_em": "2026-09-01T07:00:00-03:00",
        "run_id": "r1",
    }
    assert schema.validar_registro("plano", plano) == ["mes: '2026-9' não tem o formato mes"]
    plano["mes"] = "2026-09"
    assert schema.validar_registro("plano", plano) == []
    semana = {"semana": "2026-40", "mes": "2026-09", "gerado_em": "2026-09-28T07:00:00-03:00"}
    assert schema.validar_registro("semana", semana) == ["semana: '2026-40' não tem o formato semana"]
    dia = {"data": "2026-09-28", "run_id": "r1", "decisao_pendente": "M3"}
    assert schema.validar_registro("dia", dia) == ["decisao_pendente: 'M3' não tem o formato meta"]
    dia["decisao_pendente"] = ""
    assert schema.validar_registro("dia", dia) == []
    dia["decisao_pendente"] = "M03"
    dia["data"] = date(2026, 9, 28)
    dia["motivo"] = "sem_janela"
    assert schema.validar_registro("dia", dia) == []
    contexto = contexto_valido()
    contexto["horario_util_seg_sex"] = "9h-18h"
    contexto["horario_util_dom"] = "10:00-25:00"
    contexto["email_proprio"] = "sem-arroba"
    contexto["instalacao_id"] = "-inicio-invalido"
    erros = schema.validar_registro("contexto", contexto)
    assert [e.split(":")[0] for e in erros] == [
        "instalacao_id",
        "horario_util_seg_sex",
        "horario_util_dom",
        "email_proprio",
    ]
    evento = evento_valido(gp_key="gp:D-2026-09-28-01")
    assert schema.validar_registro("evento", evento) == ["gp_key: 'gp:D-2026-09-28-01' não tem o formato gp_key"]


def test_validar_registro_mapas_e_listas():
    # Chave de checkins precisa ser task_id; geracoes repete run_id; feitas por meta com itens válidos.
    registro = registro_valido()
    registro["checkins"]["errada"] = {"estado": "feita", "origem": "confirmado", "ts": "2026-09-28T19:00:00-03:00"}
    registro["geracoes"]["r1"]["run_id"] = "outro"
    registro["feitas"]["M1"] = []
    registro["feitas"]["M01"].append({"task_id": "x", "duracao_h": 0, "origem": "prazo"})
    registro["progresso"]["M01"].append({"declarado_pct": 120, "ts": "2026-09-28T19:05:00-03:00"})
    registro["notas_recusadas"].append({"texto": "sem ts"})
    assert schema.validar_registro("registro", registro) == [
        "geracoes.r1.run_id: difere da chave 'r1'",
        "checkins.errada: chave não tem o formato task",
        "feitas.M01[2].task_id: 'x' não tem o formato task",
        "feitas.M01[2].duracao_h: deve ser > 0",
        "feitas.M1: chave não tem o formato meta",
        "progresso.M01[1].declarado_pct: fora de 0 a 100",
        "notas_recusadas[1].ts: obrigatório",
    ]
    registro = registro_valido()
    registro["feitas"]["M01"] = {"task_id": "D-2026-09-28-01"}
    assert schema.validar_registro("registro", registro) == ["feitas.M01: esperado list, veio dict"]
    registro = registro_valido()
    registro["notas_recusadas"] = ["texto solto"]
    assert schema.validar_registro("registro", registro) == ["notas_recusadas[0]: esperado dict, veio str"]
    perfil = perfil_valido()
    perfil["metas"]["M1"] = {}
    perfil["metas"]["M01"]["fator_duracao"] = "x"
    perfil["janelas"]["segunda-manha"] = {"taxa_conclusao": 1.5, "n": 2}
    perfil["janelas"]["seg-manha"]["n"] = -1
    perfil["preferencias"]["taxa_por_duracao"]["longo"] = "muito"
    perfil["preferencias"]["extra"] = 1
    assert schema.validar_registro("perfil", perfil) == [
        "metas.M01.fator_duracao: esperado float, veio str",
        "metas.M1: chave não tem o formato meta",
        "janelas.seg-manha.n: não pode ser negativo",
        "janelas.segunda-manha: chave não tem o formato janela_perfil",
        "janelas.segunda-manha.taxa_conclusao: fora de 0 a 1",
        "preferencias.taxa_por_duracao.longo: esperado float, veio str",
        "preferencias.extra: campo desconhecido em perfil_preferencias",
    ]
    # delta pode ser negativo; demais floats não.
    perfil = perfil_valido()
    perfil["metas"]["M01"]["delta"] = -30.0
    assert schema.validar_registro("perfil", perfil) == []
    perfil["metas"]["M01"]["horas_confirmadas"] = -1
    assert schema.validar_registro("perfil", perfil) == ["metas.M01.horas_confirmadas: não pode ser negativo"]


def test_validar_registro_cache_calendar_e_ops():
    cache = cache_valido()
    cache["eventos"][0]["summary"] = "Convite de terceiro"
    cache["eventos"][0]["description"] = "texto"
    cache["eventos"][2]["all_day"] = False
    cache["eventos"].append(evento_valido(id="evt-4", start="hoje", end="2026-09-28T10:00:00-03:00"))
    cache["eventos"].append("lixo")
    assert schema.validar_registro("cache_calendar", cache) == [
        "eventos[2].all_day: deve ser true quando start é só data",
        "eventos[3].start: nem data AAAA-MM-DD nem datetime ISO: 'hoje'",
        "eventos[4]: esperado dict, veio str",
        "eventos[0].summary: deve ser null fora do calendário Metas",
        "eventos[0].description: deve ser null fora do calendário Metas",
    ]
    cache = cache_valido()
    cache["eventos"][0]["all_day"] = True
    assert schema.validar_registro("cache_calendar", cache) == [
        "eventos[0].all_day: deve ser false quando start é datetime"
    ]
    cache = cache_valido()
    del cache["eventos"]
    del cache["calendarios"]
    assert schema.validar_registro("cache_calendar", cache) == []
    ops = ops_validas()
    ops["ops"][0]["calendar_id"] = CAL_PRIMARIO
    ops["ops"][1]["calendar_event_id"] = ""
    ops["ops"][2]["op"] = "remove"
    ops["ops"][2]["status"] = "talvez"
    assert schema.validar_registro("ops", ops) == [
        "ops[1].calendar_event_id: obrigatório em update e delete",
        "ops[2].op: 'remove' fora de create, update, delete",
        "ops[2].status: 'talvez' fora de ok, erro",
        "ops[0].calendar_id: create só no calendário Metas",
    ]
    ops = ops_validas()
    del ops["ops"][2]["calendar_event_id"]
    assert schema.validar_registro("ops", ops) == ["ops[2].calendar_event_id: obrigatório em update e delete"]


def test_validar_registro_palavras_chave_teto():
    meta = meta_valida()
    meta["palavras_chave"] = ["a", "b", "c", "d"]
    assert schema.validar_registro("metas", meta) == ["palavras_chave: no máximo 3 itens"]
    meta["palavras_chave"] = ["a", "b", "c"]
    assert schema.validar_registro("metas", meta) == []
    meta["palavras_chave"] = []
    assert schema.validar_registro("metas", meta) == []
    meta["palavras_chave"] = ["a", "a"]
    assert schema.validar_registro("metas", meta) == ["palavras_chave: itens repetidos"]
    assert schema.TETO_PALAVRAS_CHAVE == 3


def test_validar_registro_faixas_numericas_e_cruzadas():
    meta = meta_valida()
    meta["custo_h_semana_escolhido"] = 0
    assert schema.validar_registro("metas", meta) == ["custo_h_semana_escolhido: deve ser > 0"]
    meta["custo_h_semana_escolhido"] = -3.5
    assert schema.validar_registro("metas", meta) == ["custo_h_semana_escolhido: deve ser > 0"]
    meta = meta_valida()
    meta["semanas_pesquisa"] = 0
    assert schema.validar_registro("metas", meta) == ["semanas_pesquisa: deve ser > 0"]
    meta = meta_valida()
    meta["custo_h_semana_min"] = 8.0
    assert schema.validar_registro("metas", meta) == ["custo_h_semana_min: maior que custo_h_semana_max"]
    meta["custo_h_semana_min"] = -1.0
    assert schema.validar_registro("metas", meta) == ["custo_h_semana_min: não pode ser negativo"]
    contexto = contexto_valido()
    contexto["buffer_min"] = -1
    assert schema.validar_registro("contexto", contexto) == ["buffer_min: não pode ser negativo"]
    dia = {"data": "2026-09-28", "run_id": "r1", "resumo_movidas": -2}
    assert schema.validar_registro("dia", dia) == ["resumo_movidas: não pode ser negativo"]
    task = task_valida()
    task["fim"] = task["inicio"]
    assert schema.validar_registro("task", task) == ["fim: deve ser depois de inicio"]
    task = task_valida()
    task["inicio"] = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
    task["fim"] = datetime(2026, 9, 28, 10, 0)
    assert schema.validar_registro("task", task) == ["fim: inicio e fim precisam ter o mesmo tipo de fuso"]
    task = task_valida()
    task["duracao_h"] = 0
    task["duracao_real_h"] = 0
    assert schema.validar_registro("task", task) == ["duracao_h: deve ser > 0"]
    task = task_valida()
    task["porque"] = "x" * 91
    task["titulo"] = "t" * 61
    assert schema.validar_registro("task", task) == [
        "titulo: no máximo 60 caracteres",
        "porque: no máximo 90 caracteres",
    ]


def test_validar_registro_recusa_nan_e_infinity():
    nan, inf = float("nan"), float("inf")
    meta = meta_valida()
    meta["custo_h_semana_escolhido"] = nan
    assert schema.validar_registro("metas", meta) == ["custo_h_semana_escolhido: não é número finito"]
    meta["custo_h_semana_escolhido"] = inf
    meta["custo_h_semana_min"] = nan
    assert schema.validar_registro("metas", meta) == [
        "custo_h_semana_min: não é número finito",
        "custo_h_semana_escolhido: não é número finito",
    ]
    task = task_valida()
    task["duracao_h"] = nan
    assert schema.validar_registro("task", task) == ["duracao_h: não é número finito"]
    perfil = perfil_valido()
    perfil["preferencias"]["taxa_por_duracao"] = {"curto": nan, "longo": 0.5}
    perfil["metas"]["M01"]["fator_duracao"] = inf
    assert schema.validar_registro("perfil", perfil) == [
        "metas.M01.fator_duracao: não é número finito",
        "preferencias.taxa_por_duracao.curto: não é número finito",
    ]


def test_validar_registro_horario_util_invertido():
    contexto = contexto_valido()
    contexto["horario_util_seg_sex"] = "18:00-09:00"
    assert schema.validar_registro("contexto", contexto) == ["horario_util_seg_sex: fim deve ser depois do início"]
    contexto["horario_util_seg_sex"] = "09:00-09:00"
    assert schema.validar_registro("contexto", contexto) == ["horario_util_seg_sex: fim deve ser depois do início"]
    contexto["horario_util_seg_sex"] = "09:00-18:00"
    contexto["horario_util_dom"] = ""  # janela vazia continua aceita
    assert schema.validar_registro("contexto", contexto) == []
    contexto["horario_util_dom"] = "10:00-25:00"  # formato errado: só o erro de formato
    assert schema.validar_registro("contexto", contexto) == [
        "horario_util_dom: '10:00-25:00' não tem o formato horario_util"
    ]


@pytest.mark.parametrize(
    "texto, valido",
    [
        ("2026-09-28T07:00:00.1234567Z", True),  # fração de 7 dígitos (só 3 ou 6 no 3.9 cru)
        ("2026-09-28T07:00:00+0000", True),  # offset sem ':'
        ("2026-09-28T07:00:00.12Z", True),  # fração de 2 dígitos
        ("2026-09-28T07:00:00Z", True),
        ("20260928T070000", False),  # formato básico: recusado nas duas versões
        ("2026-09-28", False),  # só data
        ("ontem", False),
    ],
)
def test_parse_datetime_igual_nas_duas_versoes(texto, valido):
    """validar_registro passa por clock.normalizar_iso: mesmo veredito em 3.9 e 3.13."""
    meta = meta_valida()
    meta["criado_em"] = texto
    erros = schema.validar_registro("metas", meta)
    if valido:
        assert erros == []
        assert schema._parse_datetime(texto) is not None
    else:
        assert erros == ["criado_em: datetime inválido (ISO 8601 com hora): %r" % texto]
        assert schema._parse_datetime(texto) is None


def test_validar_registro_schema_version_e_campos_desconhecidos():
    contexto = contexto_valido()
    contexto["schema_version"] = schema.SCHEMA_VERSION + 1
    assert schema.validar_registro("contexto", contexto) == [
        "schema_version: esperado %d, veio %d" % (schema.SCHEMA_VERSION, schema.SCHEMA_VERSION + 1)
    ]
    contexto = contexto_valido()
    contexto["schema_version"] = "1"
    assert schema.validar_registro("contexto", contexto) == ["schema_version: esperado int, veio str"]
    contexto = contexto_valido()
    contexto["zebra"] = 1
    contexto["alfa"] = 2
    assert schema.validar_registro("contexto", contexto) == [
        "alfa: campo desconhecido em contexto",
        "zebra: campo desconhecido em contexto",
    ]
    registro = registro_valido()
    registro["checkins"]["D-2026-09-28-01"]["cor"] = "azul"
    assert schema.validar_registro("registro", registro) == [
        "checkins.D-2026-09-28-01.cor: campo desconhecido em checkin"
    ]
    assert schema.validar_registro("metas", ["M01"]) == ["(raiz): esperado dict, veio list"]


def test_validar_registro_geracoes():
    # Achado 8.1 + eng 2.3: run_id, duracao_s, exit_code, tokens, sessoes, claude_version, classe, chave_runbook, mensagem.
    nomes = {c.nome for c in schema.ESQUEMAS["geracao"]}
    assert {
        "run_id",
        "modo",
        "data",
        "ts",
        "exit_code",
        "duracao_s",
        "tokens",
        "sessoes",
        "claude_version",
        "classe",
        "chave_runbook",
        "mensagem",
        "email",
        "hash_metas",
    } <= nomes
    registro = registro_valido()
    assert schema.validar_registro("registro", registro) == []
    geracao = registro["geracoes"]["r1"]
    geracao["classe"] = "ToolDenied"
    geracao["chave_runbook"] = "tool-denied"
    geracao["mensagem"] = "ferramenta negada"
    geracao["claude_version"] = "2.1.270"
    assert schema.validar_registro("registro", registro) == []
    geracao["email"] = "talvez"
    geracao["tokens"] = {"input": "muitos"}
    geracao["sessoes"] = ["a", 1]
    del geracao["exit_code"]
    assert schema.validar_registro("registro", registro) == [
        "geracoes.r1.exit_code: obrigatório",
        "geracoes.r1.tokens.input: esperado int, veio str",
        "geracoes.r1.sessoes: item 1 não é str",
        "geracoes.r1.email: 'talvez' fora de enviado, falhou, nao_enviado",
    ]


def test_validar_registro_arquivo_desconhecido_erro():
    with pytest.raises(GpErro) as info:
        schema.validar_registro("bloco", {})
    assert info.value.codigo == EXIT_VALIDACAO
    assert "bloco" in info.value.mensagem
    with pytest.raises(GpErro):
        schema.defaults("bloco")


def test_defaults_copias_novas():
    a = schema.defaults("metas")
    b = schema.defaults("metas")
    assert a == b
    assert a["palavras_chave"] == [] and a["palavras_chave"] is not b["palavras_chave"]
    a["palavras_chave"].append("x")
    assert schema.defaults("metas")["palavras_chave"] == []
    assert a["estado"] == "ativa" and a["prazo_externo"] is False and a["fonte"] == ""
    assert "custo_h_semana_min" not in a  # opcional sem default
    assert "custo_h_semana_escolhido" not in a  # obrigatório
    contexto = schema.defaults("contexto")
    assert contexto["buffer_min"] == 10
    assert contexto["idioma"] == "pt-BR"
    assert contexto["lembretes"] == "nao"
    assert contexto["horario_util_seg_sex"] == "08:00-19:00"
    assert contexto["horario_util_sab"] == "09:00-13:00"
    assert contexto["horario_util_dom"] == ""
    assert contexto["fontes_ativas"] == [] and contexto["calendarios_lidos"] == [] and contexto["email_alias"] == []
    assert contexto["tetos_drive_caracteres"] == 4000
    registro = schema.defaults("registro")
    assert registro == {
        "geracoes": {},
        "checkins": {},
        "feitas": {},
        "progresso": {},
        "notas_recusadas": [],
        "sentimentos": {},
        "respostas_email": [],
    }
    registro["checkins"]["x"] = 1
    assert schema.defaults("registro")["checkins"] == {}
    # Defaults preenchidos passam na validação junto dos obrigatórios.
    base = {"schema_version": 1, "gerado_em": "2026-09-28T07:00:00Z"}
    assert schema.validar_registro("perfil", dict(schema.defaults("perfil"), **base)) == []
    assert schema.validar_registro("perfil_meta", schema.defaults("perfil_meta")) == []
    for arquivo in schema.ESQUEMAS:
        for nome, valor in schema.defaults(arquivo).items():
            campo = next(c for c in schema.ESQUEMAS[arquivo] if c.nome == nome)
            assert not campo.obrigatorio
            assert valor == campo.default and (valor is not campo.default or not isinstance(valor, (list, dict)))


def test_gerar_md_deterministico():
    md = schema.gerar_md()
    assert md == schema.gerar_md()
    assert md == copy.deepcopy(md)
    saidas = []
    for semente in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=semente, PYTHONPATH=str(SCRIPTS))
        proc = subprocess.run(
            [sys.executable, "-m", "goalpacer.schema", "--md"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=str(SCRIPTS),
            check=True,
        )
        # Sem RuntimeWarning de "found in sys.modules": __init__ não importa schema.
        assert proc.stderr == ""
        saidas.append(proc.stdout)
    assert saidas[0] == saidas[1] == md


def test_gerar_md_contem_todos_os_arquivos_e_marcadores():
    md = schema.gerar_md()
    linhas = md.splitlines()
    assert linhas[0] == schema.MARCADOR_MD_INICIO
    assert linhas[-1] == schema.MARCADOR_MD_FIM
    assert md.endswith("\n")
    assert md.count(schema.MARCADOR_MD_INICIO) == 1 and md.count(schema.MARCADOR_MD_FIM) == 1
    assert "| campo | tipo | obrigatório | enum/default | descrição |" in md
    total_campos = 0
    for arquivo, campos in schema.ESQUEMAS.items():
        assert "### `%s` (`%s`)" % (arquivo, schema.CAMINHOS[arquivo]) in md
        total_campos += len(campos)
        for campo in campos:
            assert "| %s | %s | %s |" % (campo.nome, campo.tipo, "sim" if campo.obrigatorio else "não") in md
    tabelas = sum(
        1 for l in linhas if l.startswith("| ") and not l.startswith("| campo") and not l.startswith("| formato")
    )
    assert tabelas == total_campos + len(schema.REGEX_POR_TIPO_ID) + 3  # + gp_key, horario_util, janela_perfil
    for valor in (
        schema.ESTADOS + schema.ORIGENS + schema.HORIZONTES + schema.CONFIANCAS + schema.FONTES + schema.ESTADOS_META
    ):
        assert valor in md
    for secoes in schema.SECOES.values():
        for secao in secoes:
            assert "`%s`" % secao in md
    for marcador in schema.MARCADORES_PROSA:
        assert "`%s`" % marcador in md
    assert "`confirmado` → `inferido`" in md
    assert "default: 10" in md and 'default: "pt-BR"' in md and "itens: gmail, whatsapp, notion, drive" in md
    assert "(fora do `hash_metas`)" in md
    assert (
        "chave: meta; valor: lista de `feita`" in md
        and "objeto `perfil_preferencias`" in md
        and "itens: `evento`" in md
    )
    assert "formato: gp_key" in md and "conteúdo livre" in md
    assert "\t" not in md
    assert chr(0x2014) not in md  # sem em dash


def test_secoes_e_condicionais():
    assert schema.SECOES["dia"] == ("## Hoje", "## Desde <dia>", "## Progresso", "## Avisos")
    assert schema.SECOES["plano"] == ("## Balanço", "## Metas", "## Semanas", "## Evidências", "## Decisões")
    assert schema.SECOES_CONDICIONAIS["dia"] == ("## Desde <dia>", "## Avisos")
    assert schema.SECOES_CONDICIONAIS["plano"] == ("## Evidências", "## Decisões")
    for arquivo, condicionais in schema.SECOES_CONDICIONAIS.items():
        posicoes = [schema.SECOES[arquivo].index(s) for s in condicionais]
        assert posicoes == sorted(posicoes)
    assert schema.casa_secao("## Desde <dia>", "## Desde sáb")
    assert schema.casa_secao("## Desde <dia>", "## Desde 12/09\n")
    assert not schema.casa_secao("## Desde <dia>", "## Desde ")
    assert not schema.casa_secao("## Desde <dia>", "### Desde sáb")
    assert schema.casa_secao("## Hoje", "## Hoje")
    assert not schema.casa_secao("## Hoje", "## Hoje mesmo")
    assert schema.titulo_secao("## Desde <dia>", dia="qui") == "## Desde qui"
    assert schema.titulo_secao("## Hoje") == "## Hoje"
    with pytest.raises(KeyError):
        schema.titulo_secao("## Desde <dia>")
    assert schema.RE_SUBSECAO_SEMANA.match("### 2026-W40").group(1) == "2026-W40"
    assert schema.RE_SUBSECAO_SEMANA.match("### 2026-W54") is None
    assert schema.RE_SUBSECAO_META.match("### M03 Título da meta").groups() == ("M03", "Título da meta")
    assert schema.RE_SUBSECAO_META.match("### M03").groups() == ("M03", None)
    assert schema.RE_SUBSECAO_META.match("### Meta 3") is None
    assert schema.RE_SUBSECAO_TASK.match("### D-2026-09-28-01 Ler o capítulo 3").groups() == (
        "D-2026-09-28-01",
        "Ler o capítulo 3",
    )
    assert schema.RE_SUBSECAO_TASK.match("### D-2026-09-28-1") is None
    assert schema.RE_LINHA_CAMPO_BLOCO.match("- meta: M01").groups() == ("meta", "M01")
    assert schema.RE_LINHA_CAMPO_BLOCO.match("- porque:").groups() == ("porque", "")
    assert schema.RE_LINHA_CAMPO_BLOCO.match("meta: M01") is None
    assert set(schema.SUBSECOES["plano"]) == {"## Metas", "## Semanas"}
    assert set(schema.SUBSECOES["dia"]) == {"## Hoje"}


def test_marcadores_prosa():
    assert schema.MARCADORES_PROSA == ("<!-- prosa:marcos -->", "<!-- prosa:atualizar -->")
    for marcador in schema.MARCADORES_PROSA:
        assert schema.RE_MARCADOR_PROSA.fullmatch(marcador)
    assert schema.RE_MARCADOR_PROSA.search("x <!-- prosa:marcos --> y").group(1) == "marcos"
    assert schema.RE_MARCADOR_PROSA.search("<!-- prosa:Marcos -->") is None
    assert schema.RE_MARCADOR_PROSA.search("<!-- prosa:m01 -->").group(1) == "m01"
    bloco = "a <!-- prosa:m01 -->\ntexto\n<!-- /prosa:m01 --> b <!-- prosa:resumo --><!-- /prosa:resumo -->"
    assert [(m.group(2), m.group(3)) for m in schema.RE_BLOCO_PROSA.finditer(bloco)] == [
        ("m01", "\ntexto\n"),
        ("resumo", ""),
    ]
    assert schema.RE_EVIDENCIA_SINAL.match("- evidencia: 2026-09-20 gmail: matrícula confirmada").groups() == (
        "2026-09-20",
        "gmail",
        "matrícula confirmada",
    )
    assert schema.RE_MARCADOR_PROSA.search("<!-- /prosa:marcos -->") is None
    assert schema.RE_MARCADOR_PROSA_FIM.search("<!-- /prosa:marcos -->").group(1) == "marcos"
    assert schema.RE_MARCADOR_PROSA_FIM.search("<!-- prosa:marcos -->") is None


def test_cli_md_e_versao(capsys):
    assert schema.main(["--versao"]) == EXIT_OK
    assert capsys.readouterr().out == "1\n"
    assert schema.main(["--md"]) == EXIT_OK
    assert capsys.readouterr().out == schema.gerar_md()
    assert schema.main([]) == EXIT_VALIDACAO
    saida = capsys.readouterr()
    assert saida.out == "" and "--md" in saida.err
    with pytest.raises(SystemExit):
        schema.main(["--nada"])
    capsys.readouterr()
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    proc = subprocess.run(
        [sys.executable, "-m", "goalpacer.schema", "--versao"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(SCRIPTS),
    )
    assert proc.returncode == EXIT_OK and proc.stdout == "1\n" and proc.stderr == ""


# --- D-11: o que os mutantes sobreviventes mostraram sem teste -----------------------------------------------------------


def test_hash_das_metas_e_estavel_e_ignora_o_que_nao_entra():
    metas = [
        {
            "id": "M02",
            "titulo": "Corrida ção",
            "horizonte": "trimestre",
            "prazo": date(2026, 12, 31),
            "prazo_externo": False,
            "custo_h_semana_escolhido": 3,
        },
        {"id": "M01", "titulo": "Curso", "horizonte": "ano", "prazo": date(2027, 6, 30), "prazo_externo": True},
    ]
    assert schema.hash_metas(metas) == "31a1aac9bc264d94"  # mudar este valor regenera todos os planos
    reordenadas = [dict(reversed(list(m.items()))) for m in reversed(metas)]
    assert schema.hash_metas(reordenadas) == "31a1aac9bc264d94"
    assert (
        schema.hash_metas([dict(metas[0], custo_h_semana_escolhido=9, estado="pausada"), metas[1]])
        == "31a1aac9bc264d94"
    )
    assert schema.campos_hash() == schema.campos_hash("metas")


def test_formatacao_dos_defaults_na_doc():
    formatar = schema._formatar_valor
    assert [formatar(None), formatar(True), formatar(False), formatar("ção"), formatar(3)] == [
        "",
        "true",
        "false",
        '"ção"',
        "3",
    ]
    assert formatar(["a", "ç"]) == '["a", "ç"]' and formatar([]) == "[]"
    assert formatar({}) == "{}" and formatar({"b": 1, "a": "ç"}) == '{"a": "ç", "b": 1}'
    assert [schema._nome_tipo(v) for v in (None, True, datetime(2026, 1, 1), date(2026, 1, 1), 1.5)] == [
        "null",
        "bool",
        "datetime",
        "date",
        "float",
    ]


def test_limites_inclusivos_das_regras():
    teto = schema.TETOS_TEXTO[("task", "titulo")]
    campo_titulo = next(c for c in schema.ESQUEMAS["task"] if c.nome == "titulo")
    assert schema._regras_de_texto("task", campo_titulo, "x" * teto) == []
    assert schema._regras_de_texto("task", campo_titulo, "x" * (teto + 1)) == ["no máximo %d caracteres" % teto]
    pct = schema.Campo("declarado_pct", "float")
    assert schema._regras_de_numero(pct, 100.0) == [] and schema._regras_de_numero(pct, 100.5) == ["fora de 0 a 100"]
    assert schema._cruzadas_metas({"custo_h_semana_min": 4, "custo_h_semana_max": 4}, "") == []
    assert schema._cruzadas_metas({"custo_h_semana_min": 5, "custo_h_semana_max": 4}, "m: ") == [
        "m: custo_h_semana_min: maior que custo_h_semana_max"
    ]


def test_mapa_de_escalares_aceita_zero_e_recusa_negativo():
    regra = schema.RegraDict(valor_tipo="int")
    assert schema._validar_escalar_mapa(regra, "M01", 0) == []
    assert schema._validar_escalar_mapa(regra, "M01", -1) == ["M01: não pode ser negativo"]
    assert schema._validar_escalar_mapa(regra, "M01", "x")[0].startswith("M01: ")
    assert schema._validar_escalar_mapa(schema.RegraDict(valor_tipo="float"), "M02", float("inf")) == [
        "M02: não é número finito"
    ]
    assert schema._validar_escalar_mapa(schema.RegraDict(valor_tipo=None), "k", "texto") == []


def test_evento_confere_fim_e_dia_inteiro():
    assert schema._cruzadas_evento({"start": "2026-09-28T09:00:00-03:00", "end": "amanhã"}, "e: ") == [
        "e: end: nem data AAAA-MM-DD nem datetime ISO: 'amanhã'"
    ]
    assert schema._cruzadas_evento({"start": "2026-09-28", "end": "2026-09-29"}, "") == [
        "all_day: deve ser true quando start é só data"
    ]
    assert schema._cruzadas_evento({"start": None, "end": "", "all_day": True}, "") == []
    assert schema._cruzadas_evento({"start": 3, "end": "ruim"}, "")[0].startswith("end:")


def test_secao_com_dois_espacos_reservados():
    modelo = "## <meta> e <semana>"
    assert schema.casa_secao(modelo, "## M01 e 2026-W40\n")
    assert not schema.casa_secao(modelo, "## M01 ou 2026-W40")
    assert not schema.casa_secao("## Desde <dia>", "## Desde ")
