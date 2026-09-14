"""Provedor de IA da instalação (claude ou openai), a prosa pelo Codex e a trava dos conectores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from goalpacer import base, codex, ia, leitor, provedor, proxy
from goalpacer.base import EXIT_VALIDACAO, GpErro


def gravar_instalacao(conteudo) -> None:
    base.jobs_dir().mkdir(parents=True, exist_ok=True)
    (base.jobs_dir() / base.NOME_INSTALACAO).write_text(
        conteudo if isinstance(conteudo, str) else json.dumps(conteudo), encoding="utf-8"
    )


def test_ordem_ambiente_instalacao_padrao(dados_tmp, monkeypatch):
    assert provedor.ativo().nome == "claude"  # sem instalação: o padrão
    gravar_instalacao({"provedor": "openai"})
    assert provedor.ativo().nome == "openai"
    monkeypatch.setenv("GP_PROVEDOR", " Claude ")
    assert provedor.ativo().nome == "claude"  # o ambiente vence a instalação
    monkeypatch.setenv("GP_PROVEDOR", "gemini")
    with pytest.raises(GpErro, match="provedor desconhecido 'gemini': use claude ou openai"):
        provedor.ativo()
    monkeypatch.delenv("GP_PROVEDOR")
    for quebrado in ("{nao e json", json.dumps(["openai"]), json.dumps({"provedor": 3})):
        gravar_instalacao(quebrado)
        assert provedor.ativo().nome == "claude"


def test_conectores_recusados_no_provedor_sem_conectores(dados_tmp, monkeypatch):
    provedor.exigir_conectores("qualquer")  # claude tem conectores
    monkeypatch.setenv("GP_PROVEDOR", "openai")

    def proibido(*_a, **_k):
        raise AssertionError("não devia abrir o claude -p")

    with pytest.raises(GpErro, match="pelo Codex depende do spike dos conectores") as erro:
        proxy.chamar("mcp__claude_ai_Google_Calendar__list_calendars", {}, executar=proibido)
    assert erro.value.codigo == EXIT_VALIDACAO and "hoje só a prosa usa o" in erro.value.mensagem
    with pytest.raises(GpErro, match="mensal-ler pelo Codex"):
        leitor.ler("P", ["gmail"], n_metas=1, executar=proibido)


def stream_codex(*, usage=None, falha=None, extra=()) -> str:
    eventos = [{"type": "thread.started", "thread_id": "th-1"}, {"type": "turn.started"}, *extra]
    if falha is not None:
        eventos.append(falha)
    else:
        eventos.append(
            {
                "type": "turn.completed",
                "usage": usage or {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 12},
            }
        )
    return "aviso solto que não é JSON\n" + "\n".join(json.dumps(e) for e in eventos) + "\n[1, 2]\n"


def executor_codex(stdout: str, texto: str = "Linha 1\nLinha 2\n", codigo: int = 0, stderr: str = ""):
    chamadas = []

    def executar(argv, *, timeout_s, cwd, env):
        saida = Path(argv[argv.index("-o") + 1])
        chamadas.append({"argv": list(argv), "cwd": cwd, "env": env, "saida": saida, "existia": saida.exists()})
        if texto is not None:
            saida.write_text(texto, encoding="utf-8")
        return proxy.Resultado(stdout, stderr, codigo, 0.5)

    executar.chamadas = chamadas
    return executar


def test_prosa_pelo_codex(dados_tmp):
    registro: list = []
    ex = executor_codex(stream_codex())
    assert codex.prosa("Escreva duas linhas.", executar=ex, registro=registro) == "Linha 1\nLinha 2"
    chamada = ex.chamadas[0]
    argv = chamada["argv"]
    assert argv[1:3] == ["exec", "--json"] and argv[-2:] == ["--", "Escreva duas linhas."]
    for par in (
        ["--sandbox", "read-only"],
        ["-c", "features.apps=false"],
        ["-c", 'approval_policy="never"'],
        ["-c", 'forced_login_method="chatgpt"'],
        ["-c", 'model_reasoning_effort="low"'],
    ):
        assert any(argv[i : i + 2] == par for i in range(len(argv))), par
    assert {"--ephemeral", "--skip-git-repo-check", "--ignore-user-config"} <= set(argv) and "-m" not in argv
    assert chamada["cwd"] == base.jobs_dir() and chamada["env"] is None  # o executor padrão tira as chaves de API
    assert chamada["existia"] and chamada["saida"].parent == base.jobs_dir()
    assert not chamada["saida"].exists()  # a resposta não fica em disco
    assert registro[0]["tool"] == "prosa" and registro[0]["session_id"] == "th-1"
    assert registro[0]["usage"] == {
        "input_tokens": 40,
        "cache_read_input_tokens": 60,
        "cache_creation_input_tokens": 0,
        "output_tokens": 12,
    }
    assert proxy.somar_tokens(registro) == {"input": 40, "cache_read": 60, "cache_creation": 0, "output": 12}
    longa = executor_codex(stream_codex())
    codex.prosa("x", modelo="sonnet", curta=False, executar=longa)
    assert 'model_reasoning_effort="medium"' in longa.chamadas[0]["argv"]
    assert codex.esforco("desconhecido", curta=False) == codex.ESFORCO_PADRAO


def test_prosa_pelo_codex_erros(dados_tmp):
    falha = {"type": "turn.failed", "error": {"message": "You've hit your usage limit"}}
    with pytest.raises(proxy.ProxyErro, match="usage limit"):
        codex.prosa("x", executar=executor_codex(stream_codex(falha=falha)))
    with pytest.raises(proxy.ProxyErro, match="stream error"):
        codex.prosa("x", executar=executor_codex(stream_codex(extra=[{"type": "error", "message": "stream error"}])))
    with pytest.raises(proxy.ProxyErro, match="Not logged in"):
        codex.prosa("x", executar=executor_codex("", texto=None, codigo=1, stderr="Not logged in\n"))
    with pytest.raises(proxy.ProxyErro, match="código 2"):
        codex.prosa("x", executar=executor_codex("", texto=None, codigo=2))
    with pytest.raises(proxy.RespostaInvalida, match="resposta vazia"):
        codex.prosa("x", executar=executor_codex(stream_codex(), texto="  \n"))
    with pytest.raises(GpErro, match="prompt de prosa vazio"):
        codex.prosa("   ", executar=executor_codex(stream_codex()))
    assert list(base.jobs_dir().glob("prosa-*")) == []  # nenhum arquivo de resposta sobra, nem nos erros
    assert codex._texto_da_falha({"type": "error"}) == "error"


def test_codex_bin(monkeypatch, tmp_path):
    monkeypatch.setenv("GP_CODEX_BIN", "/opt/codex")
    assert codex.codex_bin() == "/opt/codex"
    monkeypatch.delenv("GP_CODEX_BIN")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert codex.codex_bin() == "codex"
    binario = tmp_path / "codex"
    binario.write_text("#!/bin/sh\n", encoding="utf-8")
    binario.chmod(0o755)
    assert codex.codex_bin() == str(binario)


def test_chaves_de_api_nunca_chegam_ao_cli():
    assert {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY"} <= set(proxy.ENV_CHAVES_API)


def test_ia_manda_a_prosa_ao_provedor_da_instalacao(dados_tmp, monkeypatch):
    chamadas = []
    for nome, modulo in ia.MODULOS.items():
        monkeypatch.setattr(modulo, "prosa", lambda prompt, _n=nome, **kw: chamadas.append((_n, prompt, kw)) or _n)
    assert ia.prosa("p1", modelo="sonnet", curta=False) == "claude"
    monkeypatch.setenv("GP_PROVEDOR", "openai")
    assert ia.prosa("p2") == "openai"
    assert chamadas == [
        ("claude", "p1", {"modelo": "sonnet", "curta": False, "executar": None, "registro": None}),
        ("openai", "p2", {"modelo": "haiku", "curta": True, "executar": None, "registro": None}),
    ]
    assert set(ia.MODULOS) == set(provedor.PROVEDORES)
