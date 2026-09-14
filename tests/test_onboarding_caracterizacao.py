"""Caracterização do onboarding antes da refatoração: cada recusa de campo, a herança do contexto já gravado,
os avisos do detectar quando um conector falha e as saídas do CLI que a suíte não percorria."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import onboarding
import validar
from goalpacer import frontmatter, offline, proxy, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO, GpErro

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def respostas() -> dict:
    return json.loads((FIXTURES / "onboarding" / "respostas-validas.json").read_text(encoding="utf-8"))


def erros_de(respostas_: dict, dados: Path) -> list[str]:
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar(respostas_, dados, None)
    assert info.value.codigo == EXIT_VALIDACAO
    return info.value.erros


def test_recusa_de_cada_campo_da_meta(dados_tmp, agora_fixo):
    r = respostas()
    r["metas"][0].update(
        {
            "titulo": "x" * 121,
            "prazo_externo": "talvez",
            "estado": "sonhando",
            "confianca": "chute",
            "impacto": "enorme",
            "palavras_chave": 42,
            "custo_h_semana_min": -1,
        }
    )
    del r["metas"][0]["custo_h_semana_escolhido"]
    r["metas"].append("uma meta em texto")
    assert erros_de(r, dados_tmp) == [
        "metas[0].confianca: 'chute' recusado (esperado alta|media|baixa|usuario)",
        "metas[0].custo_h_semana_escolhido: None recusado (horas por semana são obrigatórias (número > 0))",
        "metas[0].custo_h_semana_min: -1 recusado (esperado número > 0)",
        "metas[0].estado: 'sonhando' recusado (esperado ativa|pausada|concluida|vencida|arquivada)",
        "metas[0].impacto: 'enorme' recusado (esperado essencial|importante|apoio)",
        "metas[0].palavras_chave: 42 recusado (esperado lista de até 3 palavras)",
        "metas[0].prazo_externo: 'talvez' recusado (esperado sim/não)",
        "metas[0].titulo: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx...' recusado (até 120 caracteres)",
        "metas[2]: 'uma meta em texto' recusado (esperado objeto com titulo, horizonte, prazo, custo)",
    ]


def test_recusa_e_normalizacao_do_contexto(dados_tmp, agora_fixo):
    r = respostas()
    r.update({"horario_util": "8-18", "calendarios_lidos": 42, "email_alias": ["nao-email"], "idioma": "fr"})
    assert erros_de(r, dados_tmp) == [
        "calendarios_lidos: 42 recusado (esperado lista)",
        "email_alias: 'nao-email' recusado (não parece um e-mail)",
        "horario_util: '8-18' recusado (esperado objeto com seg_sex, sab, dom)",
        "idioma: 'fr' recusado (use um destes: pt-BR, en)",
    ]
    r = respostas()
    r["lembretes"] = True
    r["horario_util"] = {}
    r["horario_util_sab"] = "10:00-12:00"
    contexto, _ = onboarding.montar(r, dados_tmp, "inst-a")["contexto"]
    assert contexto["lembretes"] == "sim" and contexto["horario_util_sab"] == "10:00-12:00"


def test_contexto_ja_gravado_empresta_o_que_a_resposta_nao_traz(dados_tmp, agora_fixo):
    onboarding.gravar(onboarding.montar(respostas(), dados_tmp, "inst-a"), dados_tmp)
    novas = respostas()
    for chave in ("timezone", "calendar_id_metas", "calendar_id_primario", "email_proprio"):
        del novas[chave]
    novas["metas"] = [dict(novas["metas"][0], titulo="Outra meta")]
    contexto, _ = onboarding.montar(novas, dados_tmp, None)["contexto"]
    assert (contexto["timezone"], contexto["email_proprio"], contexto["instalacao_id"]) == (
        "America/Sao_Paulo",
        "pessoa@exemplo.test",
        "inst-a",
    )


@pytest.mark.parametrize("arquivo", ["metas", "fonte_pesquisa", "objetivo"])
def test_registro_que_nao_passa_no_esquema_vira_resposta_invalida(dados_tmp, agora_fixo, monkeypatch, arquivo):
    original = schema.validar_registro

    def reprova(nome, dados):
        return ["campo: forçado pelo teste"] if nome == arquivo else original(nome, dados)

    monkeypatch.setattr(schema, "validar_registro", reprova)
    r = respostas()
    r["objetivos"] = [{"titulo": "Um objetivo"}]
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar(r, dados_tmp, None)
    rotulo = {"metas": "metas", "fonte_pesquisa": "fontes", "objetivo": "objetivos"}[arquivo]
    assert info.value.erros[0].startswith("%s (" % rotulo) and info.value.erros[0].endswith("campo: forçado pelo teste")


# --- detectar com conector falhando ---------------------------------------------------------------------------------


def test_detectar_sem_remetente_e_com_conectores_falhando(dados_tmp, agora_fixo, tmp_path, monkeypatch):
    pasta = tmp_path / "off"
    pasta.mkdir()
    (pasta / "search_threads.json").write_text(json.dumps({"threads": [{"messages": [{"id": "m1"}]}, "lixo"]}))
    monkeypatch.setenv("GP_OFFLINE_DIR", str(pasta))
    original = offline.chamar

    def falha_calendar(tool, args=None, **k):
        if tool == onboarding.TOOL_LIST_CALENDARS:
            raise GpErro(3, "Insufficient scope")
        return original(tool, args, **k)

    def falha_mcp(_texto):
        raise GpErro(4, "claude mcp list não respondeu")

    monkeypatch.setattr(offline, "chamar", falha_calendar)
    monkeypatch.setattr(proxy, "servidores_de_mcp_list", falha_mcp)
    d = onboarding.detectar(modo_offline=True)
    assert d["avisos"] == [
        "email_proprio: não encontrei mensagem enviada; pergunte ao usuário",
        "calendarios: Insufficient scope",
        "fontes: claude mcp list não respondeu",
    ]
    assert d["email_proprio"] is None and d["calendarios"] == [] and d["fontes_disponiveis"] == ["whatsapp"]


# --- CLI no processo --------------------------------------------------------------------------------------------------


def test_cli_rascunho_salvar_sem_respostas_e_descartar_sem_rascunho(dados_tmp, agora_fixo, capsys, guardar_env):
    guardar_env("GP_DATA_DIR")
    assert onboarding.main(["--dados", str(dados_tmp), "rascunho", "salvar"]) == EXIT_VALIDACAO
    assert "rascunho salvar exige --respostas" in capsys.readouterr().err
    assert onboarding.main(["--dados", str(dados_tmp), "--json", "rascunho", "descartar"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out) == {"descartado": False}
    assert onboarding.main(["--dados", str(dados_tmp), "gravar"]) == EXIT_ESTADO
    assert onboarding.main([]) == EXIT_VALIDACAO


def test_cli_gravar_com_objetivos_ignoradas_e_grafo_reprovado(
    dados_tmp, agora_fixo, tmp_path, capsys, monkeypatch, guardar_env
):
    guardar_env("GP_DATA_DIR")
    r = respostas()
    r["objetivos"] = [{"titulo": "Um objetivo"}]
    arquivo = tmp_path / "respostas.json"
    arquivo.write_text(json.dumps(r), encoding="utf-8")
    argv = ["--dados", str(dados_tmp), "gravar", "--respostas", str(arquivo), "--instalacao-id", "inst-cli"]
    assert onboarding.main(argv) == EXIT_OK
    assert "objetivo" in capsys.readouterr().out
    assert onboarding.main(argv) == EXIT_OK
    assert "Ignoradas (já existem): Terminar o curso de estatística, Correr 10 km sem parar" in capsys.readouterr().out
    reprovado = validar.Resultado()
    reprovado.erro("metas/M01.md", "forçado")
    monkeypatch.setattr(validar, "validar_grafo", lambda _dados: reprovado)
    assert onboarding.main(["--json", *argv]) == EXIT_VALIDACAO
    erro = json.loads(capsys.readouterr().out)
    assert erro["ok"] is False and erro["erros"][0].startswith("gravado, mas validar.py grafo reprovou")
    assert frontmatter.ler_arquivo(dados_tmp / "contexto.md")[0]["instalacao_id"] == "inst-cli"
