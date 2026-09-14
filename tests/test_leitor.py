"""Testes de goalpacer.leitor: argv só-leitura, query do Gmail, sessão com stream sintético, validação e sinais."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from goalpacer import frontmatter, leitor, proxy, schema
from goalpacer.base import GpErro

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
METAS = {"M01": {"id": "M01", "titulo": "Curso"}, "M02": {"id": "M02", "titulo": "Corrida"}}


def test_argv_leitura_so_leitura():
    argv = leitor.argv_leitura("PROMPT", ["gmail", "drive"], max_turns=17)
    assert argv[-1] == "PROMPT" and argv[-3:-1] == ["--model", "sonnet"]
    i_tools = argv.index("--tools")
    assert argv[i_tools + 1] == ""
    permitidas = argv[argv.index("--allowedTools") + 1 : argv.index("--disallowedTools")]
    assert permitidas == list(leitor.TOOLS_LEITURA["gmail"]) + list(leitor.TOOLS_LEITURA["drive"])
    negadas = argv[argv.index("--disallowedTools") + 1 : argv.index("--setting-sources")]
    assert (
        "mcp__claude_ai_Google_Calendar" in negadas
        and "mcp__claude_ai_Notion" in negadas
        and "mcp__claude_ai_Slack" in negadas
    )
    assert "mcp__claude_ai_Gmail" not in negadas and "mcp__claude_ai_Gmail__send_message" in negadas
    assert "mcp__claude_ai_Google_Drive__trash_file" in negadas
    assert not set(permitidas) & set(negadas)
    assert argv[argv.index("--max-turns") + 1] == "17" and "--append-system-prompt" not in argv
    assert argv[argv.index("--setting-sources") + 1] == "" and argv[argv.index("--permission-prompts") + 1] == "none"
    with pytest.raises(Exception):
        leitor.argv_leitura("P", [])
    assert leitor.max_turnos(["gmail"], 2) == 14 and leitor.max_turnos(["gmail", "notion", "drive"], 5) == 60


def test_query_gmail():
    q = leitor.query_gmail(["estatística", "curso online", 'x"y'], "pessoa@exemplo.test", ["alias@exemplo.test", ""])
    assert (
        q
        == '(estatística OR "curso online" OR xy) newer_than:30d -from:pessoa@exemplo.test -from:alias@exemplo.test -subject:"[goal-pacer]"'
    )
    assert leitor.query_gmail([], "p@e.test", []) == 'newer_than:30d -from:p@e.test -subject:"[goal-pacer]"'


def stream(
    result_texto, *, servidores=("Gmail",), status="connected", subtype="success", denials=None, rate=None
) -> str:
    linhas = [
        {
            "type": "system",
            "subtype": "init",
            "session_id": "sess-l",
            "tools": [],
            "mcp_servers": [{"name": "claude.ai " + s.replace("_", " "), "status": status} for s in servidores],
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "mcp__claude_ai_Gmail__search_threads", "input": {}}
                ]
            },
        },
        {
            "type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"threads": []}'}]},
        },
    ]
    if rate:
        linhas.append(rate)
    linhas.append(
        {
            "type": "result",
            "subtype": subtype,
            "is_error": False,
            "result": result_texto,
            "session_id": "sess-l",
            "num_turns": 3,
            "permission_denials": denials or [],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
    )
    return "\n".join(json.dumps(l) for l in linhas) + "\n"


def executor(saidas):
    chamadas = []

    def executar(argv, *, timeout_s, cwd, env):
        chamadas.append(argv)
        return proxy.Resultado(saidas[min(len(chamadas), len(saidas)) - 1], "", 0, 1.0)

    executar.chamadas = chamadas
    return executar


def test_ler_sessao(dados_tmp):
    resposta = 'Aqui está:\n{"evidencias": [{"meta": "M01", "fonte": "gmail", "data": "2026-09-20", "resumo": "ok"}], "fontes": {}}'
    registro = []
    ex = executor([stream(resposta)])
    dados = leitor.ler("P", ["gmail"], n_metas=2, executar=ex, registro=registro)
    assert dados["evidencias"][0]["meta"] == "M01"
    assert len(ex.chamadas) == 1  # conector conectado na 1ª: a sessão (sonnet, a mais cara) não roda duas vezes
    ex = executor([stream(resposta, servidores=("Google_Drive",))])
    assert leitor.ler("P", ["drive"], n_metas=1, executar=ex)["evidencias"] and len(ex.chamadas) == 1
    assert registro[0]["tool"] == "mensal-ler" and registro[0]["session_id"] == "sess-l"
    # catálogo não carregou na 1ª: tenta de novo
    ex = executor([stream(resposta, status="pending"), stream(resposta)])
    assert leitor.ler("P", ["gmail"], n_metas=1, executar=ex)["evidencias"]
    assert len(ex.chamadas) == 2
    with pytest.raises(proxy.TurnosEsgotados):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream(None, subtype="error_max_turns")]))
    with pytest.raises(proxy.RespostaInvalida):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream("sem json nenhum")]))
    rate = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected", "resetsAt": 1790000000}}
    with pytest.raises(proxy.RateLimited):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream(resposta, rate=rate)]))
    # negações não derrubam: só avisam
    assert leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream(resposta, denials=[{"tool_name": "x"}])]))


def test_validar_resultado_e_render_sinais():
    dados = {
        "evidencias": [
            {"meta": "M01", "fonte": "gmail", "data": "2026-09-20", "resumo": "matrícula\nconfirmada\x07 " + "x" * 200},
            {"meta": "M01", "fonte": "drive", "data": "2026-09-20", "resumo": "fonte inativa"},
            {"meta": "M09", "fonte": "gmail", "data": "2026-09-20", "resumo": "meta desconhecida"},
            {"meta": "M02", "fonte": "gmail", "data": "2026-10-01", "resumo": "futuro"},
            {"meta": "M02", "fonte": "gmail", "data": "20/09/2026", "resumo": "data ruim"},
            "lixo",
        ]
        + [
            {"meta": "M02", "fonte": "whatsapp", "data": "2026-09-2%d" % i, "resumo": "treino %d" % i} for i in range(7)
        ],
        "fontes": {
            "gmail": {"query": "q" * 400, "vistos": 12, "abertos": True},
            "notion": {"query": "não ativa", "vistos": 3},
        },
    }
    wa = {
        "status": "ok",
        "vistos": 4,
        "ultima_mensagem": "2026-09-27T10:00",
        "trechos": {"M02": [{"ts": "x", "texto": "y"}] * 3},
    }
    sinais, avisos = leitor.validar_resultado(
        dados, metas=METAS, fontes_ativas=["gmail", "whatsapp"], agora=AGORA, whatsapp=wa
    )
    assert len(avisos) == 5
    resumo = sinais["evidencias"]["M01"][0][2]
    assert "\n" not in resumo and "\x07" not in resumo and len(resumo) == leitor.TETO_RESUMO and resumo.endswith("…")
    assert len(sinais["evidencias"]["M02"]) == leitor.TETO_EVIDENCIAS_META
    assert sinais["contadores"]["gmail_vistos"] == 12 and sinais["contadores"]["gmail_abertos"] == 0
    assert sinais["contadores"]["whatsapp_vistos"] == 4 and sinais["contadores"]["whatsapp_abertos"] == 3
    assert len(sinais["queries"]["gmail"]) == leitor.TETO_QUERY and "notion" not in sinais["queries"]
    texto = leitor.render_sinais(
        sinais, metas=METAS, fontes=["gmail", "whatsapp"], agora=AGORA, run_id="r1", whatsapp=wa
    )
    fm, corpo = frontmatter.separar(texto)
    dados_fm = frontmatter.parse(fm)
    coagido, erros = frontmatter.coagir(dados_fm, schema.ESQUEMAS["sinais"])
    assert erros == [] and schema.validar_registro("sinais", coagido) == []
    assert dados_fm["whatsapp_status"] == "ok" and dados_fm["gmail_vistos"] == 12
    assert "- gmail: viu 12 / abriu 0 · busca: `" in corpo and "- whatsapp: viu 4 / abriu 3 · export: ok" in corpo
    assert "## M01 Curso" in corpo and "- evidencia: 2026-09-20 gmail: matrícula confirmada" in corpo


def test_ler_sinais(tmp_path):
    pasta = tmp_path / "sinais"
    pasta.mkdir()
    sinais = {
        "evidencias": {"M01": [("2026-09-20", "gmail", "matrícula")], "M02": [("2026-08-01", "whatsapp", "antigo")]},
        "contadores": {},
        "queries": {},
    }
    (pasta / "2026-09-27.md").write_text(
        leitor.render_sinais(
            sinais, metas=METAS, fontes=["gmail", "whatsapp"], agora=datetime(2026, 9, 27, 7, tzinfo=TZ), run_id="r"
        ),
        encoding="utf-8",
    )
    (pasta / "2026-07-01.md").write_text(
        leitor.render_sinais(
            sinais, metas=METAS, fontes=["drive"], agora=datetime(2026, 7, 1, 7, tzinfo=TZ), run_id="r"
        ),
        encoding="utf-8",
    )
    (pasta / "lixo.md").write_text("x", encoding="utf-8")
    evidencias, fontes = leitor.ler_sinais(tmp_path, AGORA)
    assert evidencias == [
        ("2026-09-20", "gmail", "M01", "matrícula")
    ]  # a de agosto saiu da janela; o arquivo de julho também
    assert fontes == ["gmail", "whatsapp"]
    assert leitor.ler_sinais(tmp_path / "nada", AGORA) == ([], [])


def test_auditoria_das_chamadas_da_leitura():
    resposta = '{"evidencias": [], "fontes": {}}'
    chamadas = []
    leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream(resposta)]), chamadas=chamadas)
    assert chamadas == [{"tool": "mcp__claude_ai_Gmail__search_threads", "input": {}}]
    contexto = {"tetos_gmail_threads_inteiras": 3}
    busca = {
        "tool": "mcp__claude_ai_Gmail__search_threads",
        "input": {"query": leitor.query_gmail(["curso"], "p@e.test", [])},
    }
    abrir = {"tool": "mcp__claude_ai_Gmail__get_thread", "input": {"threadId": "t1"}}
    ok = leitor.auditar([busca, abrir, abrir, abrir], ["gmail"], n_metas=1, contexto=contexto)
    assert ok["ok"] and ok["chamadas"] == 4
    acima = leitor.auditar([busca] + [abrir] * 4, ["gmail"], n_metas=1, contexto=contexto)
    assert (
        not acima["ok"]
        and acima["acima_do_teto"] == {"mcp__claude_ai_Gmail__get_thread": {"chamadas": 4, "teto": 3}}
        and not acima["fora_da_lista"]
    )
    assert leitor.auditar([busca] + [abrir] * 4, ["gmail"], n_metas=2, contexto=contexto)["ok"]  # o teto é por meta
    sem = leitor.auditar(
        [{"tool": busca["tool"], "input": {"query": "curso newer_than:30d"}}], ["gmail"], n_metas=1, contexto=contexto
    )
    assert sem["busca_sem_exclusao"] == 1 and not sem["ok"]
    fora = leitor.auditar(
        [
            busca,
            {"tool": "mcp__claude_ai_Gmail__send_message", "input": {"to": ["x@y"]}},
            {"tool": "mcp__claude_ai_Notion__notion-fetch", "input": {}},
        ],
        ["gmail"],
        n_metas=1,
        contexto=contexto,
    )
    assert fora["fora_da_lista"] == ["mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_Notion__notion-fetch"]
    linhas = leitor.auditoria_jsonl([busca, abrir], ok, run_id="r1").strip().split("\n")
    assert json.loads(linhas[0]) == {"run_id": "r1", "n": 1, "tool": busca["tool"], "input": busca["input"]}
    assert json.loads(linhas[-1])["resumo"] is True and len(linhas) == 3 and "content" not in linhas[1]


def _sem_evento(texto_stream: str, tipo: str) -> str:
    return "".join(l + "\n" for l in texto_stream.splitlines() if json.loads(l).get("type") != tipo)


def _com_resultado(texto_stream: str, **campos) -> str:
    linhas = [json.loads(l) for l in texto_stream.splitlines()]
    linhas[-1].update(campos)
    return "\n".join(json.dumps(l) for l in linhas) + "\n"


def test_ler_recusa_envelope_quebrado_e_conector_que_nao_carrega():
    resposta = '{"evidencias": [], "fontes": {}}'
    with pytest.raises(proxy.McpNaoCarregado):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([stream(resposta, status="pending")]))
    # sem evento init não há o que conferir: vale como carregado
    assert leitor.ler("P", ["gmail"], n_metas=1, executar=executor([_sem_evento(stream(resposta), "system")])) == {
        "evidencias": [],
        "fontes": {},
    }
    with pytest.raises(proxy.RespostaInvalida, match="sem evento result"):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([_sem_evento(stream(resposta), "result")]))
    with pytest.raises(proxy.ProxyErro, match="is_error"):
        leitor.ler("P", ["gmail"], n_metas=1, executar=executor([_com_resultado(stream(resposta), is_error=True)]))


def test_extrair_json_so_aceita_objeto_em_texto():
    assert leitor.extrair_json('antes {"a": 1} depois') == {"a": 1}
    for invalido, trecho in ((None, "não é texto"), ("sem chaves", "sem JSON"), ("{não é json}", "JSON inválido")):
        with pytest.raises(proxy.RespostaInvalida, match=trecho):
            leitor.extrair_json(invalido)


def test_sinais_sem_whatsapp_e_contador_invalido(tmp_path):
    sinais, avisos = leitor.validar_resultado(
        {"evidencias": [], "fontes": {"gmail": {"vistos": 2}}}, metas=METAS, fontes_ativas=["gmail"], agora=AGORA
    )
    assert avisos == [] and "whatsapp_vistos" not in sinais["contadores"]
    texto = leitor.render_sinais(
        sinais, metas=METAS, fontes=["whatsapp"], agora=AGORA, run_id="r", whatsapp={"status": "sem_export"}
    )
    assert "whatsapp_status: sem_export" in texto and "whatsapp_ultima_mensagem" not in texto
    with pytest.raises(GpErro, match="sinais inválidos: gmail_vistos"):
        leitor.render_sinais(
            {"evidencias": {}, "contadores": {"gmail_vistos": -1}, "queries": {}},
            metas=METAS,
            fontes=["gmail"],
            agora=AGORA,
            run_id="r",
        )
    (tmp_path / "sinais").mkdir()
    (tmp_path / "sinais" / "2026-09-27.md").write_text("---\nsem fechar", encoding="utf-8")
    assert leitor.ler_sinais(tmp_path, AGORA) == ([], [])
