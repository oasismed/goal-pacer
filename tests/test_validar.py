"""Testes de scripts/validar.py (grafo | cache | ops) sobre fixtures sintéticas.

Cada regra do docstring de validar.py tem um teste; os exit codes e o
``--json`` são provados também por subprocess.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import validar
from goalpacer import frontmatter, schema
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_VALIDACAO

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validar.py"
AGORA = ["--agora", "2026-09-28T07:00:00-03:00", "--tz", "America/Sao_Paulo"]
METAS = "metas-fixture@group.calendar.google.com"


def copia(nome: str, tmp_path: Path) -> Path:
    destino = tmp_path / nome
    shutil.copytree(FIXTURES / nome, destino)
    return destino


def grafo(dados: Path, *extra: str) -> validar.Resultado:
    return validar.validar_grafo(dados)


# --- grafo ----------------------------------------------------------------


def test_grafo_valido(agora_fixo):
    r = grafo(FIXTURES / "dados-valido")
    assert r.erros == []
    assert r.avisos == []
    assert r.codigo == EXIT_OK and r.estado is None
    assert r.como_dict() == {"ok": True, "codigo": 0, "estado": None, "erros": [], "avisos": []}


def test_grafo_sem_onboarding_pasta_vazia(agora_fixo, tmp_path):
    r = grafo(FIXTURES / "dados-sem-onboarding")
    assert r.codigo == EXIT_ESTADO and r.estado == "sem_onboarding"
    assert r.avisos == ["sem_onboarding: rode /goal-pacer onboarding"]
    # contexto.md presente, mas metas/ vazia ou ausente: também sem_onboarding.
    dados = copia("dados-valido", tmp_path)
    shutil.rmtree(dados / "metas")
    assert grafo(dados).estado == "sem_onboarding"
    (dados / "metas").mkdir()
    (dados / "metas" / ".gitkeep").write_text("", encoding="utf-8")
    assert grafo(dados).estado == "sem_onboarding"
    # metas/ com arquivo mas sem contexto.md: idem.
    dados2 = copia("dados-sem-meta-ativa", tmp_path / "b")
    (dados2 / "contexto.md").unlink()
    assert grafo(dados2).estado == "sem_onboarding"


def test_grafo_pasta_inexistente(agora_fixo, tmp_path):
    r = grafo(tmp_path / "nao-existe")
    assert r.codigo == EXIT_IO and r.erros and "não existe" in r.erros[0]


def test_grafo_sem_meta_ativa(agora_fixo):
    r = grafo(FIXTURES / "dados-sem-meta-ativa")
    assert r.erros == []
    assert r.codigo == EXIT_ESTADO and r.estado == "sem_meta_ativa"
    assert r.avisos == ["sem_meta_ativa: rode /goal-pacer onboarding"]


def test_grafo_schema_version_diferente(agora_fixo):
    r = grafo(FIXTURES / "dados-schema-antigo")
    assert r.codigo == EXIT_VALIDACAO and r.estado == "schema_mismatch"
    assert r.erros == ["contexto.md: schema_version: esperado 1, veio 0; rode install.sh --update"]


def test_grafo_registro_schema_version_diferente(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    registro = json.loads((dados / "registro.json").read_text(encoding="utf-8"))
    registro["schema_version"] = 2
    (dados / "registro.json").write_text(json.dumps(registro), encoding="utf-8")
    r = grafo(dados)
    assert r.codigo == EXIT_VALIDACAO and r.estado == "schema_mismatch"
    assert any(e.startswith("registro.json: schema_version: esperado 1, veio 2") for e in r.erros)


def test_grafo_invalido_lista_todos_os_problemas(agora_fixo):
    r = grafo(FIXTURES / "dados-invalido")
    assert r.codigo == EXIT_VALIDACAO
    assert "contexto.md: timezone: " in "\n".join(r.erros)
    assert any(e.startswith("metas/M01.md: custo_h_semana_escolhido: esperado float") for e in r.erros)
    assert "metas/M02.md: id: 'M01' difere do nome do arquivo" in r.erros
    assert any("dias/2026-09-28.md: bloco D-2026-09-28-02" in e and "estado:" in e for e in r.erros)
    assert any(
        "dias/2026-09-28.md: bloco D-2026-09-28-03" in e and "fim: deve ser depois de inicio" in e for e in r.erros
    )
    # Órfão é aviso, mesmo com erros por perto.
    assert r.avisos == [
        "dias/2026-09-28.md: bloco D-2026-09-28-01 (linha do corpo 4): órfão: meta M07 sem metas/M07.md"
    ]
    # Nenhum conteúdo do arquivo além de nomes de campo, ids e motivos.
    assert "Bloco de meta inexistente" not in "\n".join(r.erros + r.avisos)


def test_grafo_id_duplicado_e_nome_de_arquivo(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    shutil.copy(dados / "metas" / "M02.md", dados / "metas" / "M04.md")
    (dados / "metas" / "rascunho.md").write_text("---\nid: M09\n---\n", encoding="utf-8")
    (dados / "metas" / "M05.txt").write_text("x", encoding="utf-8")
    r = grafo(dados)
    assert "metas/M04.md: id: 'M02' difere do nome do arquivo" in r.erros
    assert "metas/rascunho.md: nome de arquivo inválido (esperado M<nn>.md)" in r.erros
    assert "metas/M05.txt: nome de arquivo inválido (esperado M<nn>.md)" in r.erros


def test_grafo_frontmatter_invalido_tem_linha(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    (dados / "metas" / "M01.md").write_text("---\nid: M01\n  titulo: x\n---\n", encoding="utf-8")
    r = grafo(dados)
    assert r.codigo == EXIT_VALIDACAO
    assert any(e.startswith("metas/M01.md: ") and "linha 3" in e and "indentação" in e for e in r.erros)


def test_grafo_contexto_regras(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    texto = (dados / "contexto.md").read_text(encoding="utf-8")
    texto = texto.replace(
        "calendar_id_metas: metas-fixture@group.calendar.google.com", "calendar_id_metas: pessoa@exemplo.test"
    )
    (dados / "contexto.md").write_text(texto, encoding="utf-8")
    r = grafo(dados)
    assert "contexto.md: calendar_id_metas: igual ao primário (o Metas precisa ser um calendário separado)" in r.erros


def test_grafo_planos_orfao_e_nome(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    plano = dados / "planos" / "2026-09.md"
    plano.write_text(plano.read_text(encoding="utf-8") + "\n### M09 Meta que não existe\n", encoding="utf-8")
    shutil.copy(plano, dados / "planos" / "setembro.md")
    r = grafo(dados)
    assert "planos/2026-09.md: órfão: seção de M09 sem metas/M09.md" in r.avisos
    assert "planos/setembro.md: nome de arquivo inválido (esperado AAAA-MM.md)" in r.erros
    # mes do front-matter tem de bater com o nome do arquivo.
    plano.write_text(plano.read_text(encoding="utf-8").replace("mes: 2026-09", "mes: 2026-10"), encoding="utf-8")
    assert "planos/2026-09.md: mes: '2026-10' difere do nome do arquivo" in grafo(dados).erros


def test_grafo_dias_regras(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    dia = dados / "dias" / "2026-09-28.md"
    texto = dia.read_text(encoding="utf-8")
    # data do front-matter diferente do nome
    dia.write_text(texto.replace("data: 2026-09-28", "data: 2026-09-29"), encoding="utf-8")
    assert "dias/2026-09-28.md: data: 2026-09-29 difere do nome do arquivo" in grafo(dados).erros
    # bloco repetido
    dia.write_text(texto + "\n### D-2026-09-28-01 Repetido\n- meta: M01\n", encoding="utf-8")
    assert any("bloco D-2026-09-28-01" in e and "id repetido" in e for e in grafo(dados).erros)
    # linha "- " malformada dentro de um bloco
    dia.write_text(texto.replace("- meta: M01\n", "- meta: M01\n- sem dois pontos\n"), encoding="utf-8")
    assert any("esperado '- chave: valor' dentro do bloco D-2026-09-28-01" in e for e in grafo(dados).erros)
    # lista de prosa fora de bloco (## Progresso) não é erro: a fixture original passa
    dia.write_text(texto, encoding="utf-8")
    assert grafo(dados).erros == []
    # dias/ ausente não é erro
    shutil.rmtree(dados / "dias")
    assert grafo(dados).codigo == EXIT_OK


def test_grafo_registro_truncado_recupera_do_bak(agora_fixo, tmp_path):
    dados = copia("dados-registro-truncado", tmp_path)
    r = grafo(dados)
    assert r.codigo == EXIT_OK
    assert r.avisos == ["registro.json: JSON corrompido; restaurado do .bak"]
    assert json.loads((dados / "registro.json").read_text(encoding="utf-8"))["schema_version"] == 1
    assert (dados / "registro.json.bak").exists()  # nunca apaga o .bak


def test_grafo_registro_truncado_sem_bak(agora_fixo, tmp_path):
    dados = copia("dados-registro-truncado", tmp_path)
    (dados / "registro.json.bak").unlink()
    r = grafo(dados)
    assert r.codigo == EXIT_IO and r.estado == "registro_corrompido"
    assert r.erros == ["registro.json: JSON corrompido e sem .bak válido; rode registro.py --recuperar"]


def test_grafo_registro_invalido(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    registro = json.loads((dados / "registro.json").read_text(encoding="utf-8"))
    registro["checkins"]["errada"] = {"estado": "feita", "origem": "confirmado", "ts": "2026-09-28T19:00:00-03:00"}
    (dados / "registro.json").write_text(json.dumps(registro), encoding="utf-8")
    r = grafo(dados)
    assert r.codigo == EXIT_VALIDACAO
    assert "registro.json: checkins.errada: chave não tem o formato task" in r.erros
    (dados / "registro.json").write_text("[]", encoding="utf-8")
    assert "registro.json: esperado objeto JSON" in grafo(dados).erros


def test_grafo_numeros_do_plano_alterados(agora_fixo, tmp_path):
    dados = copia("dados-valido", tmp_path)
    plano = dados / "planos" / "2026-09.md"
    texto = plano.read_text(encoding="utf-8")
    # prosa pode mudar à vontade
    plano.write_text(texto.replace("Prosa sintética do plano.", "Outra prosa, escrita à mão."), encoding="utf-8")
    assert grafo(dados).erros == []
    # número de tabela, não
    plano.write_text(
        texto.replace("| 2026-W37 | 12.0 | 6.5 | 100% |", "| 2026-W37 | 40.0 | 6.5 | 100% |"), encoding="utf-8"
    )
    assert grafo(dados).erros == [
        "planos/2026-09.md: hash_numeros: números do plano alterados fora do balanço (NumerosAlterados); rode balanco.py --render"
    ]
    assert validar.verificar_numeros_plano({"hash_numeros": "x"}, "## Balanço\n") != []


# --- blocos de dias/ (parser) ------------------------------------------------


def test_parse_blocos_do_dia_fixture():
    _, corpo = frontmatter.ler_arquivo(FIXTURES / "dados-valido" / "dias" / "2026-09-28.md")
    blocos = frontmatter.parse_blocos(corpo)
    assert [b["id"] for b in blocos] == ["D-2026-09-28-01", "D-2026-09-28-02"]
    assert blocos[0]["titulo"] == "Exercícios do módulo 3"
    assert blocos[0]["meta"] == "M01" and blocos[0]["duracao_h"] == 1.5
    assert blocos[0]["efeito"] == "se feita: M1 41% → 44%"
    assert blocos[0]["inicio"].isoformat() == "2026-09-28T09:00:00-03:00"
    assert blocos[1]["_linha"] > blocos[0]["_linha"] > 0
    for bloco in blocos:
        bloco.pop("_linha")
        coagido, erros = frontmatter.coagir(bloco, schema.ESQUEMAS["task"])
        assert erros == [] and schema.validar_registro("task", coagido) == []


def test_parse_blocos_erros():
    # fora de um bloco, listas são prosa (## Progresso) e não erro
    assert frontmatter.parse_blocos("## Hoje\n- meta: M01\n## Progresso\n- M1 41%\n") == []
    with pytest.raises(frontmatter.ErroFrontmatter) as info:
        frontmatter.parse_blocos("### D-2026-09-28-01 T\n- meta: M01\n- item solto\n")
    assert info.value.linha == 3 and "esperado '- chave: valor'" in info.value.motivo
    with pytest.raises(frontmatter.ErroFrontmatter) as info:
        frontmatter.parse_blocos("### D-2026-09-28-01 T\n- meta: M01\n- meta: M02\n")
    assert info.value.linha == 3 and "duplicada" in info.value.motivo
    with pytest.raises(frontmatter.ErroFrontmatter):
        frontmatter.parse_blocos("### D-2026-09-28-01 T\n- id: D-2026-09-28-09\n")
    with pytest.raises(frontmatter.ErroFrontmatter):
        frontmatter.parse_blocos("### D-2026-09-28-01 T\n- meta:\n")
    with pytest.raises(frontmatter.ErroFrontmatter):
        frontmatter.parse_blocos("### D-2026-09-28-01 T\n- Meta: M01\n")
    # prosa entre blocos e seções seguintes são ignoradas; bloco sem título tem titulo vazio
    blocos = frontmatter.parse_blocos(
        "texto\n\n### D-2026-09-28-01\n- meta: M01\n\nnota solta\n## Progresso\n- M1 41%\n", deslocamento=10
    )
    assert blocos == [{"id": "D-2026-09-28-01", "titulo": "", "_linha": 13, "meta": "M01"}]
    assert frontmatter.parse_blocos("") == []


# --- cache ----------------------------------------------------------------


def test_cache_valido(agora_fixo):
    r = validar.validar_cache(FIXTURES / "cache-valido.json", METAS, None)
    assert r.erros == [] and r.avisos == [] and r.codigo == EXIT_OK
    # sem id do Metas e sem pasta de dados: aviso, não erro
    r = validar.validar_cache(FIXTURES / "cache-valido.json", None, None)
    assert r.codigo == EXIT_OK and r.avisos == [
        "cache-valido.json: calendar_id_metas não conferido (sem --calendar-id-metas nem contexto.md)"
    ]
    # lendo o id do contexto.md da fixture
    r = validar.validar_cache(FIXTURES / "cache-valido.json", None, FIXTURES / "dados-valido")
    assert r.codigo == EXIT_OK and r.avisos == []


def test_cache_terceiro_com_descricao(agora_fixo):
    r = validar.validar_cache(FIXTURES / "cache-terceiro-com-descricao.json", METAS, None)
    assert r.codigo == EXIT_VALIDACAO
    assert r.erros == [
        "cache-terceiro-com-descricao.json: eventos[0].summary: deve ser null fora do calendário Metas",
        "cache-terceiro-com-descricao.json: eventos[0].description: deve ser null fora do calendário Metas",
    ]
    assert "texto que não deveria" not in "\n".join(r.erros)


def test_cache_vazio_e_outra_instalacao(agora_fixo):
    assert validar.validar_cache(FIXTURES / "cache-vazio.json", METAS, None).codigo == EXIT_OK
    r = validar.validar_cache(FIXTURES / "cache-vazio.json", "outro@group.calendar.google.com", None)
    assert r.erros == ["cache-vazio.json: calendar_id_metas: difere do contexto (cache de outra instalação?)"]


def test_cache_json_invalido_e_gp_key(agora_fixo, tmp_path):
    ruim = tmp_path / "cache-ruim.json"
    ruim.write_text("{", encoding="utf-8")
    assert validar.validar_cache(ruim, METAS, None).codigo == EXIT_VALIDACAO
    ruim.write_text("[]", encoding="utf-8")
    assert validar.validar_cache(ruim, METAS, None).erros == ["cache-ruim.json: esperado objeto JSON"]
    cache = json.loads((FIXTURES / "cache-valido.json").read_text(encoding="utf-8"))
    cache["eventos"][2]["gp_key"] = "gp:D-2026-09-28-01"
    cache["eventos"][1]["all_day"] = False
    cache["eventos"][0]["start"] = "ontem"
    ruim.write_text(json.dumps(cache), encoding="utf-8")
    r = validar.validar_cache(ruim, METAS, None)
    assert r.erros == [
        "cache-ruim.json: eventos[0].start: nem data AAAA-MM-DD nem datetime ISO: 'ontem'",
        "cache-ruim.json: eventos[1].all_day: deve ser true quando start é só data",
        "cache-ruim.json: eventos[2].gp_key: 'gp:D-2026-09-28-01' não tem o formato gp_key",
    ]


# --- ops ------------------------------------------------------------------


def test_ops_ok(agora_fixo):
    r = validar.validar_ops(FIXTURES / "ops-ok.json", False, FIXTURES / "dados-valido")
    assert r.erros == [] and r.codigo == EXIT_OK


def test_ops_sem_status_e_erro(agora_fixo):
    r = validar.validar_ops(FIXTURES / "ops-sem-status.json", False, None)
    assert r.codigo == EXIT_VALIDACAO
    assert r.erros == [
        "ops-sem-status.json: ops[1] (create D-2026-09-28-02): sem status = falhou",
        "ops-sem-status.json: ops[2] (delete D-2026-09-27-03): erro: The requested event could not be found or has been deleted.",
    ]
    # --planejadas: status ausente é aceito; status erro continua erro
    r = validar.validar_ops(FIXTURES / "ops-sem-status.json", True, None)
    assert r.erros == [
        "ops-sem-status.json: ops[2] (delete D-2026-09-27-03): erro: The requested event could not be found or has been deleted."
    ]


def test_ops_fora_do_metas_e_sem_event_id(agora_fixo, tmp_path):
    r = validar.validar_ops(FIXTURES / "ops-fora-do-metas.json", True, None)
    assert r.erros == [
        "ops-fora-do-metas.json: ops[1].calendar_event_id: obrigatório em update e delete",
        "ops-fora-do-metas.json: ops[0].calendar_id: create só no calendário Metas",
    ]
    ops = json.loads((FIXTURES / "ops-ok.json").read_text(encoding="utf-8"))
    del ops["ops"][0]["event_id_resultado"]
    ops["calendar_id_metas"] = "outro@group.calendar.google.com"
    ops["ops"][0]["calendar_id"] = "outro@group.calendar.google.com"
    arquivo = tmp_path / "ops-x.json"
    arquivo.write_text(json.dumps(ops), encoding="utf-8")
    r = validar.validar_ops(arquivo, False, FIXTURES / "dados-valido")
    assert r.erros == [
        "ops-x.json: ops[0] (create D-2026-09-28-01): ok sem event_id_resultado",
        "ops-x.json: calendar_id_metas: difere do contexto",
    ]


# --- CLI ------------------------------------------------------------------


def executar(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cli_grafo_json_e_exit_codes(tmp_path):
    # As fixtures vivem no repo (que pode estar em Downloads, pasta TCC recusada por --dados):
    # o CLI roda sobre cópias em tmp_path.
    valido = copia("dados-valido", tmp_path)
    proc = executar("--json", "--dados", str(valido), *AGORA, "grafo")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert json.loads(proc.stdout) == {"ok": True, "codigo": 0, "estado": None, "erros": [], "avisos": []}
    assert proc.stderr == ""
    proc = executar("--json", "--dados", str(copia("dados-sem-onboarding", tmp_path)), *AGORA, "grafo")
    assert proc.returncode == EXIT_ESTADO
    saida = json.loads(proc.stdout)
    assert saida["estado"] == "sem_onboarding" and saida["ok"] is False
    assert proc.stderr == "aviso: sem_onboarding: rode /goal-pacer onboarding\n"
    proc = executar("--dados", str(copia("dados-schema-antigo", tmp_path)), *AGORA, "grafo")
    assert proc.returncode == EXIT_VALIDACAO
    assert proc.stdout == ""
    assert proc.stderr == "erro: contexto.md: schema_version: esperado 1, veio 0; rode install.sh --update\n"
    proc = executar("--dados", str(copia("dados-sem-meta-ativa", tmp_path)), *AGORA, "grafo")
    assert proc.returncode == EXIT_ESTADO


def test_cli_cache_ops_e_sem_comando(tmp_path):
    valido = copia("dados-valido", tmp_path)
    proc = executar("--dados", str(valido), *AGORA, "cache", str(FIXTURES / "cache-valido.json"))
    assert proc.returncode == EXIT_OK and proc.stderr == ""
    proc = executar(*AGORA, "cache", str(FIXTURES / "cache-terceiro-com-descricao.json"), "--calendar-id-metas", METAS)
    assert proc.returncode == EXIT_VALIDACAO and "summary: deve ser null" in proc.stderr
    proc = executar(*AGORA, "ops", str(FIXTURES / "ops-sem-status.json"))
    assert proc.returncode == EXIT_VALIDACAO and "sem status = falhou" in proc.stderr
    proc = executar(*AGORA, "ops", "--planejadas", str(FIXTURES / "ops-fora-do-metas.json"))
    assert proc.returncode == EXIT_VALIDACAO and "create só no calendário Metas" in proc.stderr
    proc = executar(*AGORA)
    assert proc.returncode == EXIT_VALIDACAO and "grafo" in proc.stderr
    # --dados em pasta TCC é recusado pelo base (exit 3), sem ler nada.
    proc = executar("--dados", str(Path.home() / "Downloads" / "gp-teste-inexistente"), *AGORA, "grafo")
    assert proc.returncode == EXIT_VALIDACAO and "Desktop/Downloads/Documents" in proc.stderr


def test_main_por_funcao(agora_fixo, capsys, monkeypatch):
    monkeypatch.setenv("GP_DATA_DIR", str(FIXTURES / "dados-invalido"))
    assert validar.main(["--json", "grafo"]) == EXIT_VALIDACAO
    saida = capsys.readouterr()
    dados = json.loads(saida.out)
    assert dados["codigo"] == 3 and dados["ok"] is False and len(dados["erros"]) >= 4
    assert saida.err.count("erro: ") == len(dados["erros"]) and saida.err.count("aviso: ") == len(dados["avisos"])


def test_grafo_avisa_feitas_e_checkins_divergentes(agora_fixo, tmp_path):
    """R7 (análise de 13/09): horas em feitas sem check-in feita, ou o contrário, aparecem no validar."""
    from goalpacer import registro as reg

    dados = copia("dados-valido", tmp_path)
    assert not [a for a in grafo(dados).avisos if "feitas" in a]
    registro = reg.carregar(dados)
    task_id = next(item["task_id"] for lista in registro["feitas"].values() for item in lista)
    registro["checkins"][task_id]["estado"] = "nao_feita"
    reg.salvar(registro, dados)
    avisos = [a for a in grafo(dados).avisos if "feitas" in a]
    assert avisos == [
        "registro.json: feitas tem %s, mas o check-in do bloco não está feita (nao_feita); a demanda do mês conta horas que o estado não confirma"
        % task_id
    ]
