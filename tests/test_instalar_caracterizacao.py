"""Caracterização do desinstalar antes da refatoração: as respostas do diário --desinstalar que a suíte não
percorria (saída ilegível, erro do conector, apagar com erro por bloco, apagar com saída ilegível, blocos mantidos
sem confirmar). Roda no processo, com o diário e o agendador trocados por respostas prontas."""

from __future__ import annotations

import argparse
import json

import pytest

import instalar


def _args(**extra):
    base = {"offline": True, "apagar_blocos": False, "apagar_cache": False, "nao_interativo": True}
    base.update(extra)
    return argparse.Namespace(**base)


@pytest.fixture
def casa(tmp_path, monkeypatch, guardar_env):
    guardar_env("GP_DATA_DIR")
    raiz = tmp_path / "raiz"
    app, dados = raiz / "app", raiz / "dados"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / "diario.py").write_text("# diário de mentira\n", encoding="utf-8")
    dados.mkdir(parents=True)
    (dados / "contexto.md").write_text("---\n---\n", encoding="utf-8")
    (dados / "cache").mkdir()
    monkeypatch.setenv("GP_RAIZ", str(raiz))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setattr(instalar, "ler_instalacao", lambda: {"app": str(app), "dados": str(dados), "raiz": str(raiz)})
    monkeypatch.setattr(instalar, "descarregar_agendamento", list)
    return dados


def _rodar_com(monkeypatch, respostas):
    chamadas = []

    def rodar3(argv, **_k):
        chamadas.append("--confirmar" in argv)
        return respostas[len(chamadas) - 1]

    monkeypatch.setattr(instalar, "_rodar3", rodar3)
    return chamadas


@pytest.mark.parametrize(
    ("respostas", "extra", "esperado", "confirmou"),
    [
        ([(0, "não é json", "")], {}, "calendário Metas: blocos mantidos (não é json)", [False]),
        (
            [(3, "", "linha 1\nInsufficient scope")],
            {},
            "calendário Metas: blocos mantidos (Insufficient scope)",
            [False],
        ),
        (
            [(0, json.dumps({"blocos": ["b1", "b2"]}), "")],
            {},
            "calendário Metas: blocos mantidos (para apagar depois: ./install.sh --uninstall --apagar-blocos)",
            [False],
        ),
        (
            [(0, json.dumps({"blocos": ["b1", "b2"]}), ""), (0, json.dumps({"blocos": ["b1"], "erros": ["b2"]}), "")],
            {"apagar_blocos": True},
            "calendário Metas: blocos mantidos (não apagados: b2)",
            [False, True],
        ),
        (
            [(0, json.dumps({"blocos": ["b1"]}), ""), (4, "", "timeout\n")],
            {"apagar_blocos": True},
            "calendário Metas: blocos mantidos (timeout)",
            [False, True],
        ),
        (
            [(0, json.dumps({"blocos": ["b1", "b2"]}), ""), (0, json.dumps({"blocos": ["b1", "b2"], "erros": []}), "")],
            {"apagar_blocos": True},
            "calendário Metas: 2 bloco(s) apagados",
            [False, True],
        ),
    ],
)
def test_desinstalar_blocos(casa, monkeypatch, capsys, respostas, extra, esperado, confirmou):
    chamadas = _rodar_com(monkeypatch, respostas)
    assert instalar.desinstalar(_args(**extra)) == 0
    saida = capsys.readouterr().out
    assert chamadas == confirmou
    assert esperado in saida, saida


def test_desinstalar_apaga_cache_e_aparelhos(casa, monkeypatch, capsys):
    _rodar_com(monkeypatch, [(0, json.dumps({"blocos": []}), "")])
    aparelhos = instalar.base.jobs_dir() / "painel-aparelhos.json"
    aparelhos.parent.mkdir(parents=True)
    aparelhos.write_text("{}", encoding="utf-8")
    (casa / "sinais").mkdir()
    assert instalar.desinstalar(_args(apagar_cache=True)) == 0
    assert not (casa / "cache").exists() and not (casa / "sinais").exists() and not aparelhos.exists()


# --- update tudo ou nada: cada ponto de falha com o estado final (antes de dividir atualizar, D-03) --------------------

ESPERADO_UPDATE = (
    __import__("pathlib").Path(__file__).resolve().parent / "fixtures" / "caracterizacao" / "instalar_update.json"
)


def _cenario_update(
    tmp_path,
    monkeypatch,
    *,
    modo,
    respostas,
    args_extra=None,
    preparar=None,
    lock_preso=False,
    sem_instalacao=False,
    assinatura_ok=True,
):
    import os

    from goalpacer import registro as reg
    from goalpacer.base import GpErro

    raiz = tmp_path / ("raiz-" + str(len(list(tmp_path.iterdir()))))
    app, dados = raiz / "app", raiz / "dados"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / "versao.txt").write_text("antiga\n", encoding="utf-8")
    dados.mkdir(parents=True)
    (dados / "contexto.md").write_text("---\n---\n", encoding="utf-8")
    monkeypatch.setenv("GP_RAIZ", str(raiz))
    instalacao = {"app": str(app), "dados": str(dados), "python3": "/py", "claude": "/claude", "agendado": True}
    gravadas, falas, comandos = [], [], []
    monkeypatch.setattr(instalar, "ler_instalacao", lambda: None if sem_instalacao else dict(instalacao))
    monkeypatch.setattr(instalar, "gravar_instalacao", lambda d: gravadas.append(sorted(d)))
    monkeypatch.setattr(instalar, "dizer", lambda chave, **v: falas.append([chave, sorted(v)]))
    monkeypatch.setattr(instalar, "eh_repo_git", lambda _p: modo == "clone")
    monkeypatch.setattr(instalar, "instalar_comando", lambda *_a: "cmd")
    monkeypatch.setattr(instalar, "endurecer", lambda *_a: None)
    monkeypatch.setattr(instalar, "gerar_agendamento", lambda *_a, **_k: {"diario": []})
    monkeypatch.setattr(instalar, "carregar_agendamento", lambda _a: comandos.append("carregar") or [])
    monkeypatch.setattr(instalar, "instalar_janela", lambda *_a, **_k: comandos.append("janela") or "")
    monkeypatch.setattr(instalar, "revisao", lambda _a: "abc1234")
    monkeypatch.setattr(instalar.migracoes, "fazer_backup", lambda *_a: comandos.append("backup") or dados / "b.zip")
    monkeypatch.setattr(instalar.migracoes, "podar_backups", lambda *_a: None)
    if lock_preso:

        def preso(*_a, **_k):
            raise GpErro(4, "lock preso há 3 min (pid 1)")

        monkeypatch.setattr(reg, "lock", preso)

    respostas = {**respostas, "tag --list": respostas.get("tag --list", (0, "v0.1.0\nv9.9.9\nultima"))}

    def rodar(argv, **_k):
        chave = next((c for c in respostas if c in " ".join(argv)), None)
        comandos.append(chave or " ".join(os.path.basename(a) for a in argv[:3]))
        return respostas.get(chave, (0, ""))

    def conferir(*_a):
        comandos.append("assinatura")
        if not assinatura_ok:
            raise GpErro(3, "a assinatura não confere")
        return "publicador@exemplo.test"

    monkeypatch.setattr(instalar.assinatura, "copiar_assinantes", lambda _app, destino: destino / "assinantes")
    monkeypatch.setattr(instalar.assinatura, "verificar_tag", conferir)
    monkeypatch.setattr(instalar.assinatura, "verificar_arquivo", conferir)
    monkeypatch.setattr(instalar.assinatura, "extrair_zip", lambda _z, destino: destino / "goal-pacer-v9.9.9")

    monkeypatch.setattr(instalar, "_rodar", rodar)

    def preparar_falso(origem, destino, **_k):
        if preparar == "falha":
            destino.mkdir(parents=True)
            (destino / "pela-metade").write_text("x", encoding="utf-8")
            raise OSError("disco cheio")
        (destino / "scripts").mkdir(parents=True)
        (destino / "scripts" / "versao.txt").write_text("nova\n", encoding="utf-8")
        return "copia"

    monkeypatch.setattr(instalar, "preparar_app", preparar_falso)
    if modo == "copia":
        reserva = app.with_name("app.anterior")
        reserva.mkdir()
        (reserva / "velha-reserva").write_text("x", encoding="utf-8")
    args = argparse.Namespace(origem=None, copiar=False, painel_rede=False, sem_agendar=False, offline=True)
    for k, v in (args_extra or {}).items():
        setattr(args, k, v)
    try:
        codigo = instalar.atualizar(args)
    except OSError as erro:
        codigo = "OSError: %s" % erro
    arquivos = {
        str(p.relative_to(raiz)): p.read_text(encoding="utf-8")
        for p in sorted(raiz.rglob("*"))
        if p.is_file() and "dados" not in p.parts
    }
    return {
        "codigo": codigo,
        "falas": falas,
        "comandos": comandos,
        "arquivos_do_app": arquivos,
        "instalacao_gravada": gravadas,
        "lock_liberado": not (dados / ".lock").exists(),
    }


CENARIOS_UPDATE = {
    "sem_instalacao": {"modo": "clone", "respostas": {}, "sem_instalacao": True},
    "lock_preso": {"modo": "clone", "respostas": {}, "lock_preso": True},
    "clone_sujo": {"modo": "clone", "respostas": {"status --porcelain": (0, " M scripts/x.py")}},
    "copia_sem_origem": {"modo": "copia", "respostas": {}},
    "clone_fetch_falha": {"modo": "clone", "respostas": {"fetch": (128, "fatal: unable to access")}},
    "clone_em_dia": {"modo": "clone", "respostas": {"tag --list": (0, "v0.0.0\nv0.0.0-rc1")}},
    "clone_tag_sem_assinatura": {"modo": "clone", "respostas": {}, "assinatura_ok": False},
    "clone_commit_local_fora_da_tag": {"modo": "clone", "respostas": {"merge-base": (1, "")}},
    "clone_checkout_falha": {"modo": "clone", "respostas": {"checkout": (1, "error: pathspec did not match")}},
    "clone_autoteste_reprova": {
        "modo": "clone",
        "respostas": {"rev-parse": (0, "c0ffee"), "autoteste.py": (3, "passo 4: copy quebrado")},
    },
    "clone_autoteste_quebra": {
        "modo": "clone",
        "respostas": {"autoteste.py": (1, "Traceback\nSyntaxError: invalid syntax")},
    },
    "clone_migrar_falha": {"modo": "clone", "respostas": {"migrar.py": (3, "migração 2 recusada")}},
    "clone_migrar_timeout": {"modo": "clone", "respostas": {"migrar.py": (-1, "timeout")}},
    "clone_ok": {"modo": "clone", "respostas": {"status.py": (0, "doctor ok")}},
    "clone_reaplicar_falha": {
        "modo": "clone",
        "respostas": {"--reaplicar": (1, "erro: sem permissão em LaunchAgents")},
    },
    "copia_ok": {
        "modo": "copia",
        "respostas": {},
        "args_extra": {"origem": "/origem", "copiar": True, "sem_agendar": True},
    },
    "copia_zip_assinado_ok": {
        "modo": "copia",
        "respostas": {},
        "args_extra": {"origem": "/downloads/goal-pacer-v9.9.9.zip", "sem_agendar": True},
    },
    "copia_zip_sem_assinatura": {
        "modo": "copia",
        "respostas": {},
        "args_extra": {"origem": "/downloads/goal-pacer-v9.9.9.zip"},
        "assinatura_ok": False,
    },
    "copia_preparar_falha": {
        "modo": "copia",
        "respostas": {},
        "args_extra": {"origem": "/origem", "copiar": True},
        "preparar": "falha",
    },
    "copia_autoteste_reprova": {
        "modo": "copia",
        "respostas": {"autoteste.py": (3, "reprovado")},
        "args_extra": {"origem": "/origem", "copiar": True},
    },
}


def test_update_igual_ao_golden_master(tmp_path, monkeypatch, guardar_env):
    import json as _json
    import os

    guardar_env("GP_DATA_DIR")
    obtido = {}
    for nome, cenario in CENARIOS_UPDATE.items():
        with monkeypatch.context() as m:
            obtido[nome] = _cenario_update(tmp_path, m, **cenario)
    texto = _json.dumps(obtido, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("GP_REGRAVAR_CARACTERIZACAO") == "1":
        ESPERADO_UPDATE.write_text(texto, encoding="utf-8")
        pytest.skip("golden master regravado")
    assert _json.loads(texto) == _json.loads(ESPERADO_UPDATE.read_text(encoding="utf-8"))


def test_preparar_app_em_cada_ramo(tmp_path, monkeypatch):
    from goalpacer.base import GpErro

    falas, comandos = [], []
    monkeypatch.setattr(instalar, "dizer", lambda chave, **_v: falas.append(chave))
    origem = tmp_path / "origem"
    (origem / "scripts").mkdir(parents=True)
    (origem / "scripts" / "x.py").write_text("x\n", encoding="utf-8")
    app = tmp_path / "raiz" / "app"

    # pasta local sem git vira cópia sozinha
    monkeypatch.setattr(instalar, "eh_repo_git", lambda _p: False)
    assert instalar.preparar_app(str(origem), app, copiar=False) == "copia" and (app / "scripts" / "x.py").exists()
    assert falas[:2] == ["origem_sem_git", "app_copiado"]
    assert instalar.preparar_app(str(origem), app, copiar=True) == "copia" and falas[-1] == "app_existente"
    with pytest.raises(GpErro, match="--copiar pede uma pasta local"):
        instalar.preparar_app(str(tmp_path / "nao-existe"), app, copiar=True)

    # clone: app existente mantém o modo; origem suja avisa; falhas do clone e do checkout param; sparse antigo desliga
    monkeypatch.setattr(instalar, "eh_repo_git", lambda _p: True)
    monkeypatch.setattr(instalar, "git_disponivel", lambda: True)
    assert instalar.preparar_app(str(origem), app, copiar=False) == "clone" and falas[-1] == "app_existente"

    def rodar_com(respostas):
        def rodar(argv, **_k):
            chave = next((c for c in respostas if c in argv), argv[3] if len(argv) > 3 else argv[1])
            comandos.append(chave)
            return respostas.get(chave, (0, ""))

        monkeypatch.setattr(instalar, "_rodar", rodar)

    novo = tmp_path / "raiz" / "app-novo"
    rodar_com({"status": (0, " M sujo.py"), "sparse-checkout": (1, "git antigo")})
    assert instalar.preparar_app(str(origem), novo, copiar=False) == "clone"
    assert (
        "origem_suja" in falas
        and falas[-1] == "app_clonado"
        and comandos[-4:] == ["sparse-checkout", "sparse-checkout", "checkout", "remote"]
    )
    rodar_com({"clone": (128, "fatal: repository not found")})
    with pytest.raises(GpErro, match=r"git clone de https://exemplo\.test/repo\.git não concluiu"):
        instalar.preparar_app("https://exemplo.test/repo.git", tmp_path / "raiz" / "app-3", copiar=False)
    rodar_com({"checkout": (1, "error: checkout falhou")})
    with pytest.raises(GpErro, match=r"git checkout em .* não concluiu"):
        instalar.preparar_app("https://exemplo.test/repo.git", tmp_path / "raiz" / "app-4", copiar=False)
