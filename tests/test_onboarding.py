"""Testes de scripts/onboarding.py: detectar (offline), rascunho, gravar (E2E offline).

Fixtures sintéticas em tests/fixtures/onboarding/ e tests/fixtures/offline/.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import onboarding
import validar
from goalpacer import copy, frontmatter, schema
from goalpacer.base import EXIT_ESTADO, EXIT_OK, EXIT_VALIDACAO

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "onboarding.py"
VALIDAS = FIXTURES / "onboarding" / "respostas-validas.json"
INVALIDAS = FIXTURES / "onboarding" / "respostas-invalidas.json"
AGORA = ["--agora", "2026-09-28T07:00:00-03:00", "--tz", "America/Sao_Paulo"]


def respostas(nome: str = "respostas-validas.json") -> dict:
    return json.loads((FIXTURES / "onboarding" / nome).read_text(encoding="utf-8"))


# --- detectar ------------------------------------------------------------------


def test_detectar_offline(dados_tmp, agora_fixo, monkeypatch):
    monkeypatch.setenv("GP_OFFLINE_DIR", str(FIXTURES / "offline"))
    d = onboarding.detectar(modo_offline=True)
    assert d["email_proprio"] == "pessoa@exemplo.test"  # de "Nome <Pessoa@Exemplo.test>", minúsculo
    assert d["calendar_id_primario"] == "pessoa@exemplo.test"
    assert d["calendar_id_metas"] == "metas-fixture@group.calendar.google.com"
    assert [c["id"] for c in d["calendarios"]][:2] == ["pessoa@exemplo.test", "metas-fixture@group.calendar.google.com"]
    assert d["fontes_disponiveis"] == ["whatsapp", "gmail", "notion"]  # Slack não é fonte; Drive não conectado
    assert d["calendar_conectado"] is True
    assert d["timezone"] == "America/Sao_Paulo"
    assert d["avisos"] == []


def test_detectar_offline_sem_fixtures(dados_tmp, agora_fixo, tmp_path, monkeypatch):
    monkeypatch.setenv("GP_OFFLINE_DIR", str(tmp_path / "vazio"))
    d = onboarding.detectar(modo_offline=True)
    assert d["email_proprio"] is None and d["calendar_id_metas"] is None and d["calendar_id_primario"] is None
    assert d["fontes_disponiveis"] == ["whatsapp"]
    assert any(a.startswith("email_proprio:") for a in d["avisos"])
    assert any(copy.texto("onboarding.p5_calendario_nao_encontrado") in a for a in d["avisos"])


def test_detectar_primario_por_forma_do_id_e_metas_duplicado(dados_tmp, agora_fixo, tmp_path, monkeypatch):
    pasta = tmp_path / "off"
    pasta.mkdir()
    (pasta / "list_calendars.json").write_text(
        json.dumps(
            {
                "calendars": [
                    {"id": "alguem@exemplo.test", "summary": "x"},
                    {"id": "a@group.calendar.google.com", "summary": "metas"},
                    {"id": "b@group.calendar.google.com", "summary": "Metas "},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GP_OFFLINE_DIR", str(pasta))
    d = onboarding.detectar(modo_offline=True, servidores=["Google_Drive"])
    assert d["calendar_id_primario"] == "alguem@exemplo.test"
    assert d["calendar_id_metas"] is None and any("mais de um" in a for a in d["avisos"])
    assert d["fontes_disponiveis"] == ["whatsapp", "drive"] and d["calendar_conectado"] is False


# --- rascunho ------------------------------------------------------------------


def test_rascunho_salvar_ver_descartar(dados_tmp, agora_fixo):
    assert onboarding.ler_rascunho() is None
    assert onboarding.resumo_rascunho(None)["existe"] is False
    r1 = onboarding.salvar_rascunho({"metas": [{"titulo": "A"}]})
    assert r1["versao"] == 1 and r1["atualizado_em"] == "2026-09-28T07:00:00-03:00"
    r2 = onboarding.salvar_rascunho({"timezone": "America/Sao_Paulo", "metas": [{"titulo": "B"}]})
    assert r2["respostas"] == {"metas": [{"titulo": "B"}], "timezone": "America/Sao_Paulo"}
    assert onboarding.caminho_rascunho() == dados_tmp / "cache" / "onboarding-rascunho.json"
    assert (
        schema.validar_registro(
            "rascunho_onboarding", json.loads(onboarding.caminho_rascunho().read_text(encoding="utf-8"))
        )
        == []
    )
    resumo = onboarding.resumo_rascunho(onboarding.ler_rascunho())
    assert resumo["existe"] and resumo["respondidas"] == ["metas", "timezone"]
    assert onboarding.descartar_rascunho() is True
    assert onboarding.descartar_rascunho() is False
    assert (
        not onboarding.caminho_rascunho().exists()
        and not (dados_tmp / "cache" / "onboarding-rascunho.json.bak").exists()
    )


def test_rascunho_invalido_e_recusado(dados_tmp, agora_fixo):
    path = onboarding.caminho_rascunho()
    path.parent.mkdir(parents=True)
    path.write_text('{"versao": "x"}', encoding="utf-8")
    with pytest.raises(Exception) as info:
        onboarding.ler_rascunho()
    assert "descartar" in str(info.value)


# --- gravar (E2E offline) --------------------------------------------------------


def test_montar_e_gravar_validas(dados_tmp, agora_fixo):
    montado = onboarding.montar(respostas(), dados_tmp, "inst-teste-01")
    assert montado["instalacao_id"] == "inst-teste-01" and montado["ignoradas"] == []
    assert [m["id"] for m, _ in montado["metas"]] == ["M01", "M02"]
    m1, m2 = (m for m, _ in montado["metas"])
    assert m1["custo_h_semana_escolhido"] == 4.0 and m1["confianca"] == "media" and m1["fonte"] == "fontes/M01.md"
    assert (
        m2["custo_h_semana_escolhido"] == 2.5
        and m2["prazo_externo"] is True
        and m2["palavras_chave"] == ["corrida", "treino"]
    )
    assert m2["estado"] == "ativa" and m2["criado_em"].isoformat() == "2026-09-28T07:00:00-03:00"
    contexto, _ = montado["contexto"]
    assert contexto["email_proprio"] == "pessoa@exemplo.test" and contexto["horario_util_dom"] == ""
    assert contexto["buffer_min"] == 10 and contexto["lembretes"] == "nao" and contexto["idioma"] == "pt-BR"
    assert contexto["schema_version"] == 1
    f1, f2 = (f for f, _ in montado["fontes"])
    assert (
        f1["estado"] == "ok"
        and f1["urls"] == ["https://exemplo.test/curso-estatistica"]
        and f1["custo_h_semana_min"] == 3.0
    )
    assert f2["estado"] == "ok" and f2["busca"] == "" and "custo_h_semana_min" not in f2
    assert f1["hash_meta"] == schema.hash_meta_pesquisa(m1)
    # Nada gravado ainda.
    assert not (dados_tmp / "contexto.md").exists()
    gravados = onboarding.gravar(montado, dados_tmp)
    assert gravados == ["metas/M01.md", "metas/M02.md", "fontes/M01.md", "fontes/M02.md", "contexto.md"]
    r = validar.validar_grafo(dados_tmp)
    assert r.codigo == EXIT_OK and r.erros == [] and r.avisos == []
    dados, corpo = frontmatter.ler_arquivo(dados_tmp / "metas" / "M01.md")
    assert (
        dados["titulo"] == "Terminar o curso de estatística"
        and "## Por que esta meta" in corpo
        and "Módulos 1 a 4" in corpo
    )
    fonte, corpo_fonte = frontmatter.ler_arquivo(dados_tmp / "fontes" / "M01.md")
    assert schema.validar_registro("fonte_pesquisa", fonte) == [] and "recomenda-se" in corpo_fonte
    texto = (dados_tmp / "contexto.md").read_text(encoding="utf-8")
    assert "instalacao_id: inst-teste-01" in texto and "email_alias: [alias@exemplo.test]" in texto


def test_gravar_de_novo_ignora_titulos_repetidos_e_mantem_instalacao(dados_tmp, agora_fixo):
    onboarding.gravar(onboarding.montar(respostas(), dados_tmp, "inst-a"), dados_tmp)
    novas = respostas()
    novas["metas"].append(
        {
            "titulo": "Meta nova",
            "horizonte": "ano",
            "prazo": "2027-06-30",
            "custo_h_semana_escolhido": 1,
            "semanas_pesquisa": 30,
        }
    )
    novas["timezone"] = "Europe/Lisbon"
    montado = onboarding.montar(novas, dados_tmp, None)
    assert montado["ignoradas"] == ["Terminar o curso de estatística", "Correr 10 km sem parar"]
    assert [m["id"] for m, _ in montado["metas"]] == ["M03"]
    assert montado["instalacao_id"] == "inst-a"  # mantido do contexto existente
    onboarding.gravar(montado, dados_tmp)
    assert sorted(p.name for p in (dados_tmp / "metas").iterdir()) == ["M01.md", "M02.md", "M03.md"]
    contexto, _ = frontmatter.ler_arquivo(dados_tmp / "contexto.md")
    assert contexto["timezone"] == "Europe/Lisbon" and contexto["instalacao_id"] == "inst-a"
    assert validar.validar_grafo(dados_tmp).codigo == EXIT_OK


def test_montar_recusa_invalidas_sem_gravar(dados_tmp, agora_fixo):
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar(respostas("respostas-invalidas.json"), dados_tmp, None)
    erros = info.value.erros
    assert info.value.codigo == EXIT_VALIDACAO
    esperados = [
        "metas[0].custo_h_semana_escolhido: 'muito' recusado (esperado número > 0)",
        "metas[1].titulo: '' recusado (título vazio)",
        "metas[1].horizonte: 'mensal' recusado (esperado trimestre|semestre|ano)",
        "metas[1].prazo: '15/12/2026' recusado (esperado AAAA-MM-DD)",
        "metas[1].semanas_pesquisa: 0 recusado (esperado inteiro > 0 (semanas))",
        "metas[1].palavras_chave: ['a', 'b', 'c', 'd'] recusado (no máximo 3)",
        "metas[1].cor: 'azul' recusado (campo desconhecido)",
        "horario_util_seg_sex: '8h-19h' recusado (esperado HH:MM-HH:MM ou nenhum)",
        "lembretes: 'talvez' recusado (esperado sim ou nao)",
        "email_proprio: 'sem-arroba' recusado (não parece um e-mail)",
        "timezone: 'Marte/Base' recusado (não está na lista IANA (ex.: America/Sao_Paulo))",
        "calendar_id_metas: 'pessoa@exemplo.test' recusado (igual ao calendário primário; o Metas precisa ser separado)",
    ]
    for esperado in esperados:
        assert esperado in erros, esperado
    assert not (dados_tmp / "contexto.md").exists() and not (dados_tmp / "metas").exists()


def test_montar_recusa_faltas_e_excessos(dados_tmp, agora_fixo):
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar({}, dados_tmp, None)
    assert "metas: None recusado (pelo menos uma meta)" in info.value.erros
    assert "timezone: None recusado (obrigatório)" in info.value.erros
    r = respostas()
    r["metas"] = r["metas"] * 3
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar(r, dados_tmp, None)
    assert "metas: 6 recusado (no máximo 5 metas)" in info.value.erros
    r = respostas()
    r["zebra"] = 1
    with pytest.raises(onboarding.RespostaInvalida) as info:
        onboarding.montar(r, dados_tmp, None)
    assert info.value.erros == ["zebra: 1 recusado (campo desconhecido)"]
    with pytest.raises(onboarding.RespostaInvalida):
        onboarding.montar([], dados_tmp, None)


def test_montar_gera_instalacao_id(dados_tmp, agora_fixo):
    a = onboarding.montar(respostas(), dados_tmp, None)["instalacao_id"]
    b = onboarding.montar(respostas(), dados_tmp, None)["instalacao_id"]
    assert a != b and schema.RE_INSTALACAO_ID.match(a) and a.startswith("inst-")


# --- CLI ---------------------------------------------------------------------


def executar(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    ambiente = dict(os.environ)
    for chave in list(ambiente):
        if chave.startswith("GP_") and chave != "GP_PLATAFORMA":
            del ambiente[chave]
    if env:
        ambiente.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8", env=ambiente
    )


def test_cli_fluxo_completo(tmp_path):
    dados = tmp_path / "dados"
    env = {"GP_OFFLINE_DIR": str(FIXTURES / "offline")}
    proc = executar("--json", "--dados", str(dados), *AGORA, "--offline", "detectar", env=env)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert json.loads(proc.stdout)["calendar_id_metas"] == "metas-fixture@group.calendar.google.com"
    proc = executar("--dados", str(dados), *AGORA, "rascunho", "ver")
    assert proc.returncode == EXIT_ESTADO
    parcial = tmp_path / "parcial.json"
    parcial.write_text(json.dumps({"metas": respostas()["metas"]}), encoding="utf-8")
    proc = executar("--dados", str(dados), *AGORA, "rascunho", "salvar", "--respostas", str(parcial))
    assert proc.returncode == EXIT_OK and "rascunho salvo: metas" in proc.stdout
    resto = tmp_path / "resto.json"
    r = respostas()
    del r["metas"]
    resto.write_text(json.dumps(r), encoding="utf-8")
    assert (
        executar("--dados", str(dados), *AGORA, "rascunho", "salvar", "--respostas", str(resto)).returncode == EXIT_OK
    )
    proc = executar("--dados", str(dados), *AGORA, "gravar", "--instalacao-id", "inst-cli")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert "Gravei 2 metas" in proc.stdout and copy.texto("onboarding.tela_final") in proc.stdout
    assert not (dados / "cache" / "onboarding-rascunho.json").exists()
    proc = executar("--json", "--dados", str(dados), *AGORA, "gravar")
    assert proc.returncode == EXIT_ESTADO and "sem rascunho" in proc.stderr
    proc = executar("--json", "--dados", str(dados), *AGORA, "gravar", "--respostas", str(INVALIDAS))
    assert proc.returncode == EXIT_VALIDACAO
    saida = json.loads(proc.stdout)
    assert saida["ok"] is False and any("timezone: 'Marte/Base'" in e for e in saida["erros"])
    assert proc.stderr.count("erro: ") == len(saida["erros"])
    # DATA_DIR em pasta TCC: recusado antes de ler qualquer coisa (exit 3).
    proc = executar(
        "--dados", str(Path.home() / "Documents" / "gp-inexistente"), *AGORA, "gravar", "--respostas", str(VALIDAS)
    )
    assert proc.returncode == EXIT_VALIDACAO and "Desktop/Downloads/Documents" in proc.stderr
    proc = executar(*AGORA)
    assert proc.returncode == EXIT_VALIDACAO


def test_copy_onboarding_tem_as_oito_perguntas():
    for chave in (
        "abertura",
        "p1_metas",
        "p2_prazos",
        "p3_custo",
        "p4_horario_util",
        "p5_calendario",
        "p6_fontes",
        "p7_palavras_chave",
        "p8_email_fuso",
        "rascunho_existente",
        "gravado",
        "tela_final",
    ):
        texto = (
            copy.texto("onboarding." + chave)
            if "{" not in copy.carregar()["onboarding." + chave]
            else copy.carregar()["onboarding." + chave]
        )
        assert texto.strip()
    for chave in (
        "p1_metas",
        "p2_prazos",
        "p3_custo",
        "p4_horario_util",
        "p5_calendario",
        "p6_fontes",
        "p7_palavras_chave",
        "p8_email_fuso",
    ):
        assert "Por que:" in copy.carregar()["onboarding." + chave]
    assert copy.texto("onboarding.gravado", n_metas=2, instalacao_id="x").startswith("Gravei 2 metas")
    with pytest.raises(Exception):
        copy.texto("onboarding.nao_existe")
    proibidas = ("atrasada", "falhou", "perdeu", "não fez", "deveria", "de novo", "ainda")
    texto = (Path(__file__).resolve().parent.parent / "references" / "copy.pt-BR.md").read_text(encoding="utf-8")
    corpo = texto.split("## onboarding", 1)[1].split("\n## tom\n", 1)[0]  # o grupo tom lista as proibidas de propósito
    # exceção única documentada em references/regras.md: o estado FALHOU do status --doctor
    assert corpo.count("\n### falhou\nFALHOU\n") == 1
    corpo = corpo.replace("\n### falhou\nFALHOU\n", "\n")
    for palavra in proibidas:
        assert palavra not in corpo.lower(), palavra
    assert chr(0x2014) not in texto


def test_onboarding_encadeia_mensal_e_primeiro_dia(tmp_path):
    """T4/T35: o fim do onboarding na skill roda o mensal e o primeiro diário; offline tudo passa no validar."""
    import os

    dados = tmp_path / "dados"
    scripts = SCRIPT.parent
    env = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    env.update(
        {"GP_OFFLINE_DIR": str(FIXTURES / "offline"), "GP_RAIZ": str(tmp_path / "raiz"), "GP_PROXY_BACKOFF_S": "0"}
    )

    def rodar(script, *args):
        return subprocess.run(
            [sys.executable, str(scripts / script), "--dados", str(dados), *AGORA, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
        )

    proc = rodar("onboarding.py", "gravar", "--respostas", str(VALIDAS), "--instalacao-id", "inst-e2e")
    assert proc.returncode == EXIT_OK, proc.stderr
    proc = rodar("mensal.py", "--json", "--offline")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (dados / "planos" / "2026-10.md").exists()
    proc = rodar("diario.py", "--json", "--offline", "--email")
    assert proc.returncode == EXIT_OK, proc.stderr
    saida = json.loads(proc.stdout)
    assert saida["primeiro_dia"] is True and saida["email"]["status"] == "enviado"
    assert (dados / "dias" / "2026-09-28.md").exists()
    assert validar.validar_grafo(dados).codigo == EXIT_OK
    proc = rodar("diario.py", "--email-texto")
    assert proc.returncode == EXIT_OK and "COMO FUNCIONA" in proc.stdout


def test_objetivos_e_impacto_no_onboarding(dados_tmp, agora_fixo):
    from goalpacer import objetivos as gpobjetivos, perfil as prf

    respostas_ = respostas()
    respostas_["objetivos"] = [
        {
            "titulo": "Mudar de carreira para dados",
            "porque": "Trabalho com o que gosto.",
            "como_vou_saber": "Uma proposta de vaga.",
        },
        {"titulo": "Ter energia para a família"},
    ]
    respostas_["metas"][0].update({"objetivo": "mudar de carreira PARA dados", "impacto": "essencial"})
    respostas_["metas"][1].update({"objetivo": "Ter energia para a família", "impacto": "apoio"})
    montado = onboarding.montar(respostas_, dados_tmp, None)
    onboarding.gravar(montado, dados_tmp)
    objetivos = gpobjetivos.ler(dados_tmp)
    assert [(o["id"], o["titulo"], o["por_que"]) for o in objetivos.values()] == [
        ("O01", "Mudar de carreira para dados", "Trabalho com o que gosto."),
        ("O02", "Ter energia para a família", "(preencha)"),
    ]
    metas = prf._ler_metas(dados_tmp)
    assert (metas["M01"]["objetivo"], metas["M01"]["impacto"], metas["M02"]["objetivo"], metas["M02"]["impacto"]) == (
        "O01",
        "essencial",
        "O02",
        "apoio",
    )
    assert validar.validar_grafo(dados_tmp).erros == []
    # regravar reaproveita o objetivo pelo título e uma meta nova pode apontar para um já cadastrado
    novas = dict(
        respostas_,
        objetivos=[],
        metas=[dict(respostas_["metas"][1], titulo="Dormir 7 horas", objetivo="Ter energia para a família")],
    )
    montado = onboarding.montar(novas, dados_tmp, None)
    assert montado["objetivos"] == [] and montado["metas"][0][0]["objetivo"] == "O02"
    # objetivo desconhecido, impacto fora do enum e objetivos demais são recusados sem gravar
    ruins = dict(respostas_, objetivos=[{"titulo": "A"}, {"titulo": "B"}, {"titulo": "C"}, {"titulo": "D", "extra": 1}])
    ruins["metas"] = [
        dict(respostas_["metas"][0], titulo="Outra", objetivo="Objetivo que não existe", impacto="máximo")
    ]
    with pytest.raises(onboarding.RespostaInvalida) as erro:
        onboarding.montar(ruins, dados_tmp, None)
    texto = "\n".join(erro.value.erros)
    assert (
        "metas[0].impacto" in texto
        and "objetivos: 4" in texto
        and "objetivos[3].extra" in texto
        and "metas[0].objetivo" in texto
    )


def test_checkin_lista_metas_para_sentir_por_impacto(tmp_path, monkeypatch):
    import shutil

    import checkin
    from goalpacer import metas as gpmetas, registro as reg

    dados = tmp_path / "dados"
    shutil.copytree(Path(__file__).resolve().parent / "fixtures" / "checkin" / "dados", dados)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    gpmetas.ajustar(dados, "M02", {"impacto": "essencial"})
    registro = reg.carregar(dados)
    reg.registrar_sentimento(registro, "M01", "pesada")
    lista = checkin.metas_para_sentir(dados, registro)
    assert (
        [m["meta"] for m in lista][:2] == ["M02", "M01"]
        and lista[1]["ultimo"] == "pesada"
        and len(lista) <= checkin.TETO_SENTIR
    )
