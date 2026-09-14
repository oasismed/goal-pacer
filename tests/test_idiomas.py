"""Idiomas das superfícies: um arquivo references/copy.<idioma>.md por idioma, nada mais a mexer.

Confere a paridade entre os arquivos, o idioma lido do contexto, as regras de tom por idioma,
a leitura de volta dos arquivos de dados em qualquer idioma e as superfícies em inglês sem
texto em português que não venha dos dados da pessoa.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from goalpacer import balanco, base, cli, copy, prompts, tom

RAIZ = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RE_VARIAVEL = re.compile(r"\{([a-z_]*)\}")
TZ = ZoneInfo("America/Sao_Paulo")


def test_idiomas_tem_as_mesmas_chaves_e_variaveis():
    assert copy.disponiveis()[0] == copy.IDIOMA_PADRAO and "en" in copy.disponiveis()
    padrao = copy.carregar(copy.IDIOMA_PADRAO)
    for idioma in copy.disponiveis()[1:]:
        outro = copy.carregar(idioma)
        assert set(outro) == set(padrao), (idioma, sorted(set(outro) ^ set(padrao)))
        for chave, texto in padrao.items():
            if chave == "calendario.data_curta":
                assert set(RE_VARIAVEL.findall(outro[chave])) <= {"dd", "mm", "d", "mes_curto"}
                continue
            assert set(RE_VARIAVEL.findall(outro[chave])) == set(RE_VARIAVEL.findall(texto)), (idioma, chave)
        for chave in (
            "calendario.dias_longos",
            "calendario.dias_curtos",
            "calendario.dias_celula",
            "calendario.dias_nota",
        ):
            assert len(copy.lista(chave, idioma)) == 7, (idioma, chave)
        assert (
            len(copy.lista("calendario.meses", idioma)) == 12
            and len(copy.lista("calendario.meses_curtos", idioma)) == 12
        )


def test_nenhuma_string_usa_variavel_reservada():
    # copy.texto(chave, idioma, **valores): uma {idioma} no texto seria engolida pelo parâmetro
    for idioma in copy.disponiveis():
        assert [c for c, t in copy.carregar(idioma).items() if "idioma" in RE_VARIAVEL.findall(t)] == [], idioma


def test_idioma_vem_do_contexto_do_ambiente_ou_do_padrao(dados_tmp, monkeypatch):
    assert copy.atual() == "pt-BR"  # sem contexto
    (dados_tmp / "contexto.md").write_text("---\nidioma: en\n---\n", encoding="utf-8")
    assert copy.atual() == "en" and copy.texto("email.titulo_hoje") == "Today"
    (dados_tmp / "contexto.md").write_text("---\nidioma: xx-YY\n---\n", encoding="utf-8")
    os.utime(dados_tmp / "contexto.md", ns=(1, 1))
    assert copy.atual() == "pt-BR"  # idioma sem arquivo cai no padrão
    monkeypatch.setenv("GP_IDIOMA", "en")
    assert copy.atual() == "en"
    monkeypatch.delenv("GP_IDIOMA")
    copy.usar("en")
    assert copy.atual() == "en"
    copy.usar(None)
    assert copy.dia_longo(date(2026, 9, 28), "en") == "Monday" and copy.data_curta(date(2026, 9, 28), "en") == "Sep 28"
    assert (
        copy.dia_curto(date(2026, 10, 3), "pt-BR") == "sáb" and copy.data_curta(date(2026, 9, 28), "pt-BR") == "28/09"
    )
    assert copy.nome_mes(10, "en") == "October" and copy.nome_mes(10, "pt-BR") == "outubro"


def test_argumento_idioma_valida_e_vale_para_o_processo(monkeypatch, guardar_env):
    guardar_env("GP_IDIOMA")
    parser = cli.parser_base("teste")
    cli.aplicar_args_base(parser.parse_args(["--idioma", "en"]))
    assert os.environ["GP_IDIOMA"] == "en" and copy.atual() == "en"
    with pytest.raises(base.GpErro) as erro:
        cli.aplicar_args_base(parser.parse_args(["--idioma", "fr"]))
    assert "disponíveis: pt-BR, en" in erro.value.mensagem


def test_tom_por_idioma():
    assert tom.violacoes("You are behind on M1 again", "en") == ["behind", "again"]
    assert tom.violacoes("2 of 5 blocks", "en") == ["2 of 5"] and tom.violacoes("pending for 3 days", "en") == [
        "pending for 3 days"
    ]
    assert tom.violacoes("2 of 5 blocks", "pt-BR") == [] and tom.violacoes("2 de 5 blocos, ainda", "pt-BR") == [
        "ainda",
        "2 de 5",
    ]
    assert tom.ok("M1 fits in the month", "en")


def test_prompt_sai_no_idioma_da_instalacao(monkeypatch):
    pt = prompts.renderizar("porque", {"DATA": "2026-09-28", "BLOCOS": "-"})
    assert "em pt-BR," in pt and "atrasada, falhou" in pt
    monkeypatch.setenv("GP_IDIOMA", "en")
    en = prompts.renderizar("porque", {"DATA": "2026-09-28", "BLOCOS": "-"})
    assert "em English (en)," in en and "late, overdue" in en and "atrasada" not in en


def test_plano_escrito_num_idioma_e_lido_em_outro():
    linhas = {
        "pt-BR": (
            "- " + copy.texto("plano.linha_mes", "pt-BR", demanda="20", alocado="19,2", feito="0", cobertura="96%"),
            "- " + copy.texto("plano.linha_decisao", "pt-BR", decisao="reduzir"),
        ),
        "en": (
            "- " + copy.texto("plano.linha_mes", "en", demanda="20", alocado="19.2", feito="0", cobertura="96%"),
            "- " + copy.texto("plano.linha_decisao", "en", decisao="reduzir"),
        ),
    }
    for idioma, (mes, decisao) in linhas.items():
        texto = "---\nmes: 2026-10\n---\n\n## Metas\n\n### M01 Curso\n\n%s\n%s\n" % (mes, decisao)
        assert balanco.ler_plano(texto)["metas"]["M01"] == {"cobertura": "96%", "decisao": "reduzir"}, idioma
    assert copy.casar("plano.linha_decisao", "outra coisa: reduzir", {"decisao": "[a-z]+"}) is None


@pytest.fixture
def pasta_en(tmp_path, monkeypatch):
    """A pasta de exemplo do painel gerada inteira com a instalação em inglês."""
    import demo_painel

    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setenv("GP_IDIOMA", "en")
    dados = demo_painel.preparar(tmp_path / "demo")
    for var, valor in demo_painel.ambiente(tmp_path / "demo").items():
        monkeypatch.setenv(var, valor)
    monkeypatch.setattr("goalpacer.clock._AGORA_FIXADO", None)
    return dados


RE_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{4,}")
# chaves e valores de enum que o arquivo de dados guarda (contrato, iguais em todo idioma)
ESTRUTURA = {
    "hoje",
    "progresso",
    "avisos",
    "desde",
    "balanço",
    "metas",
    "semanas",
    "evidências",
    "decisões",
    "semana",
    "cobertura",
    "meta",
    "evidencia",
    "nota",
    "plano",
    "prosa",
    "resumo",
    "ativa",
    "manter",
    "reduzir",
    "adiar",
    "renegociar",
    "usuario",
    "media",
    "baixa",
    "alta",
    "movida",
    "movidas",
    "confirmadas",
    "presumidas",
    "planejada",
    "inferido",
    "presumido",
    "confirmado",
    "feita",
    "estado",
    "origem",
    "porque",
    "efeito",
    "inicio",
    "duracao",
    "semanal",
    "pausada",
    "concluida",
}


def _palavras(texto: str) -> set:
    return {p.lower() for p in RE_PALAVRA.findall(texto)}


def test_superficies_em_ingles_sem_portugues_do_codigo(pasta_en):
    import checkin
    import diario
    import painel
    import status
    from goalpacer import clock

    agora = clock.agora()
    # palavras que vêm dos dados da pessoa (títulos, objetivos, resumos, eventos) podem estar em português
    dos_dados = set()
    for origem in (pasta_en, FIXTURES / "mensal"):
        for arquivo in origem.rglob("*"):
            if (
                arquivo.is_file()
                and arquivo.suffix in (".md", ".json", ".txt")
                and not {"dias", "planos", "semanas"} & set(arquivo.parts)
            ):
                dos_dados |= _palavras(arquivo.read_text(encoding="utf-8", errors="ignore"))
    marcadores = set().union(*map(_palavras, copy.carregar("pt-BR").values())) - set().union(
        *map(_palavras, copy.carregar("en").values())
    )
    marcadores -= dos_dados | ESTRUTURA

    textos: list[str] = []

    def juntar(valor):
        if isinstance(valor, str):
            if not re.match(r"^[a-z0-9_.\-]+$", valor):  # ids e chaves do front, não texto
                textos.append(valor)
        elif isinstance(valor, dict):
            for chave, item in valor.items():
                if chave not in (
                    "textos",
                    "motivo",
                ):  # motivo da inferência é diagnóstico técnico do JSON, a skill não mostra
                    juntar(item)
        elif isinstance(valor, list):
            for item in valor:
                juntar(item)

    juntar(painel.modelo(pasta_en, agora))
    juntar(painel.modelo_objetivos(pasta_en, agora))
    juntar(painel.modelo_metas(pasta_en, agora))
    juntar(painel.modelo_meta(pasta_en, agora, "M01"))
    for nivel, pid in (
        ("ano", None),
        ("semestre", "2026-S2"),
        ("trimestre", "2026-T4"),
        ("mes", "2026-10"),
        ("semana", "2026-W40"),
    ):
        juntar(painel.modelo_periodo(pasta_en, agora, nivel, pid))
    juntar(painel.modelo_checkin(pasta_en, agora))
    juntar(painel.modelo_status(pasta_en, agora))
    juntar(painel.modelo_conexoes(pasta_en, agora))
    juntar(list(painel.textos().values()))
    juntar(checkin.inferir(pasta_en, modo_offline=True, agora=agora))
    textos.append(status.render_status(status.coletar(pasta_en, agora)))
    assunto, corpo, _ = diario.montar_email(pasta_en, date(2026, 9, 28))
    textos += [assunto, corpo]
    for pasta in ("dias", "planos", "semanas"):
        textos += [arquivo.read_text(encoding="utf-8") for arquivo in sorted((pasta_en / pasta).glob("*.md"))[-2:]]

    vazou = {palavra: texto[:120] for texto in textos for palavra in _palavras(texto) & marcadores}
    assert vazou == {}
    assert (
        assunto.startswith("[goal-pacer] Mon Sep 28 · ")
        and "TODAY" in corpo
        and "HOW THE MILESTONES ARE GOING" in corpo
    )
    assert all(tom.violacoes(t, "en") == [] for t in [assunto, corpo]), [
        tom.violacoes(t, "en") for t in [assunto, corpo]
    ]


def test_toda_chave_do_copy_tem_uso():
    """D5 (análise de 13/09): chave sem uso em código, front ou SKILL.md não fica nos arquivos de idioma."""
    codigo = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [*(RAIZ / "scripts").rglob("*.py"), RAIZ / "jobs" / "run_job.py"]
        if "__pycache__" not in p.parts
    )
    front = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [
            RAIZ / "web" / "app.js",
            RAIZ / "web" / "index.html",
            RAIZ / "web" / "parear.html",
            *sorted((RAIZ / "web" / "js").rglob("*.js")),
        ]
    )
    skill = (RAIZ / "SKILL.md").read_text(encoding="utf-8")
    literais = set(re.findall(r'"([a-z_]+\.[a-z0-9_]+)"', codigo))
    prefixos = set(re.findall(r'"([a-z_]+\.[a-z0-9_]*)"\s*(?:\+|%)', codigo)) | set(
        re.findall(r'"([a-z_]+\.[a-z0-9_]*?)%s', codigo)
    )
    ditas = {"instalar." + k for k in re.findall(r'(?:dizer|perguntar)\("([a-z0-9_]+)"', codigo)}
    no_front = (
        set(re.findall(r'\bt\("([a-z_.0-9]+)"', front))
        | set(re.findall(r'data-t(?:-rotulo)?="([a-z_]+)"', front))
        | set(re.findall(r"\{\{T:([a-z_]+)\}\}", front))
    )
    prefixos_front = set(re.findall(r'\bt\("([a-z_.0-9]+)"\s*\+', front))
    # grupos lidos por nome montado: calendario (copy.py), tom (tom.py), comando (goal_pacer.py), falhas (execucao.py)
    montados = ("calendario.", "tom.", "comando.", "falhas.")
    sem_uso = []
    for chave in copy.carregar("pt-BR"):
        grupo, _, nome = chave.partition(".")
        if (
            chave in literais
            or chave in ditas
            or chave.startswith(montados)
            or any(chave.startswith(p) for p in prefixos if p)
        ):
            continue
        if grupo in ("painel", "coach") and (
            (nome if grupo == "painel" else chave) in no_front
            or any((nome if grupo == "painel" else chave).startswith(p) for p in prefixos_front)
        ):
            continue
        if "`%s`" % nome in skill or "`%s`" % chave in skill or "%s." % grupo + nome in skill:
            continue
        sem_uso.append(chave)
    assert sem_uso == []
