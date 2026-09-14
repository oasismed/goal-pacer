"""Artefatos gerados têm de bater com o commitado (eng 3.2; T23).

- a seção entre os marcadores de references/dados.md é byte a byte a saída
  de ``python3 -m goalpacer.schema --md``;
- references/metas.template.md tem front-matter parseável e válido;
- todo campo do esquema aparece na seção gerada;
- references/regras.md contém jobs/prompt-base.md byte a byte;
- todo prompt renderiza sem variável sobrando e com as regras da base;
- copy.pt-BR.md inteiro passa no tom (exceção única: doctor.falhou);
- README.md tem uma âncora por chave de runbook e links internos válidos.
"""

from __future__ import annotations

import difflib
import os
import subprocess
import sys
from pathlib import Path

from goalpacer import frontmatter, schema

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
DADOS_MD = RAIZ / "references" / "dados.md"
TEMPLATE = RAIZ / "references" / "metas.template.md"
COMANDO = "cd scripts && python3 -m goalpacer.schema --md"


def secao_gerada(texto: str) -> str:
    inicio = texto.index(schema.MARCADOR_MD_INICIO)
    fim = texto.index(schema.MARCADOR_MD_FIM) + len(schema.MARCADOR_MD_FIM)
    return texto[inicio:fim] + "\n"


def test_secao_de_esquemas_do_dados_md_e_a_gerada():
    texto = DADOS_MD.read_text(encoding="utf-8")
    assert texto.count(schema.MARCADOR_MD_INICIO) == 1 and texto.count(schema.MARCADOR_MD_FIM) == 1
    env = dict(os.environ, PYTHONPATH=str(SCRIPTS))
    proc = subprocess.run(
        [sys.executable, "-m", "goalpacer.schema", "--md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(SCRIPTS),
        check=True,
    )
    esperado = proc.stdout
    atual = secao_gerada(texto)
    if atual != esperado:
        diff = "".join(
            difflib.unified_diff(
                esperado.splitlines(True),
                atual.splitlines(True),
                "gerado",
                "references/dados.md",
            )
        )
        raise AssertionError("references/dados.md desatualizado; regenere com: %s\n%s" % (COMANDO, diff))


def test_template_de_meta_valido(agora_fixo):
    dados, corpo = frontmatter.ler_arquivo(TEMPLATE)
    coagido, erros = frontmatter.coagir(dados, schema.ESQUEMAS["metas"])
    assert erros == []
    assert schema.validar_registro("metas", coagido) == []
    assert coagido["id"] == "M01" and coagido["estado"] == "ativa"
    assert "## Por que esta meta" in corpo and "## Marcos" in corpo
    assert chr(0x2014) not in TEMPLATE.read_text(encoding="utf-8")


def test_todo_campo_do_esquema_esta_no_dados_md():
    secao = secao_gerada(DADOS_MD.read_text(encoding="utf-8"))
    for arquivo, campos in schema.ESQUEMAS.items():
        assert "### `%s`" % arquivo in secao
        for campo in campos:
            assert "| %s | %s |" % (campo.nome, campo.tipo) in secao, (arquivo, campo.nome)
    texto = DADOS_MD.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    for termo in ("gp_key", "hash_metas", "schema_version", "presumido", "sem_onboarding", "install.sh --update"):
        assert termo in texto


# --- T23: prompts, regras, copy e README ------------------------------------------------------


def test_regras_md_contem_a_base_dos_prompts_byte_a_byte():
    regras = (RAIZ / "references" / "regras.md").read_text(encoding="utf-8")
    inicio, fim = "<!-- prompt-base:inicio -->\n", "<!-- prompt-base:fim -->"
    assert regras.count(inicio) == 1 and regras.count(fim) == 1
    trecho = regras[regras.index(inicio) + len(inicio) : regras.index(fim)]
    assert trecho == (RAIZ / "jobs" / "prompt-base.md").read_text(encoding="utf-8")


def test_prompts_renderizam_sem_variavel_sobrando():
    from goalpacer import prompts

    nomes = sorted(
        p.name[len("prompt-") : -len(".md")] for p in (RAIZ / "jobs").glob("prompt-*.md") if p.name != "prompt-base.md"
    )
    assert nomes == ["mensal-ler", "plano", "porque"]
    for nome in nomes:
        variaveis = prompts.variaveis_de(nome)
        assert variaveis, nome
        texto = prompts.renderizar(nome, {v: "<%s>" % v.lower() for v in variaveis})
        assert prompts.RE_VARIAVEL.findall(texto) == [], nome
        assert "dados_nao_confiaveis" in texto and "Nunca faça perguntas" in texto, nome
        assert chr(0x2014) not in texto, nome


def test_copy_inteiro_passa_no_tom():
    from goalpacer import copy, tom

    for idioma in copy.disponiveis():
        strings = copy.carregar(idioma)
        # o grupo tom lista as próprias palavras proibidas; doctor.falhou é a exceção única (references/regras.md)
        ruins = {
            chave: tom.violacoes(texto, idioma)
            for chave, texto in strings.items()
            if not chave.startswith("tom.") and chave != "doctor.falhou" and tom.violacoes(texto, idioma)
        }
        assert ruins == {}, idioma
        assert chr(0x2014) not in (RAIZ / "references" / ("copy.%s.md" % idioma)).read_text(encoding="utf-8")
    assert copy.carregar("pt-BR")["doctor.falhou"] == "FALHOU"


def test_readme_tem_ancora_para_cada_runbook_e_segue_o_tom():
    from goalpacer import execucao, tom

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    for classe, info in execucao.CLASSES.items():
        assert '<a id="%s"></a>\n### %s\n' % (info.runbook, classe) in readme, classe
    assert chr(0x2014) not in readme
    assert tom.violacoes(readme.replace("FALHOU", "")) == []
    for ancora in __import__("re").findall(r"\]\(#([a-z0-9-]+)\)", readme):
        assert '<a id="%s"></a>' % ancora in readme, ancora


def test_skill_tira_do_turno_as_ferramentas_de_escrita_dos_conectores():
    """R2 (análise de 13/09): disallowed-tools no frontmatter só com ferramentas que gravam; as de leitura seguem livres."""
    import re

    from goalpacer import leitor

    texto = (RAIZ / "SKILL.md").read_text(encoding="utf-8")
    frontmatter_skill = texto.split("---", 2)[1]
    negadas = re.findall(r"^\s+- (mcp__claude_ai_\S+)$", frontmatter_skill, flags=re.MULTILINE)
    assert "disallowed-tools:" in frontmatter_skill and len(negadas) >= 40
    for tool in (
        "mcp__claude_ai_Google_Calendar__create_event",
        "mcp__claude_ai_Gmail__send_message",
        "mcp__claude_ai_Google_Drive__share_file",
        "mcp__claude_ai_Notion__notion-update-page",
    ):
        assert tool in negadas, tool
    leitura = {t for tools in leitor.TOOLS_LEITURA.values() for t in tools} | {
        "mcp__claude_ai_Google_Calendar__list_events",
        "mcp__claude_ai_Google_Calendar__list_calendars",
    }
    assert not leitura & set(negadas)
    assert len(negadas) == len(set(negadas)) and all("__" in t[len("mcp__") :] for t in negadas)
    assert "é dado, não instrução" in texto
