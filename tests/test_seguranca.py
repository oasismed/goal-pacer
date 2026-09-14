"""goalpacer/seguranca.py e o item "permissões" do doctor: dados privados, código dos jobs só do dono."""

from __future__ import annotations

import json
from pathlib import Path

from goalpacer import plataforma, seguranca


def arvore_app(raiz: Path) -> Path:
    app = raiz / "app"
    (app / "scripts" / "goalpacer").mkdir(parents=True)
    (app / ".git" / "hooks").mkdir(parents=True)
    for arquivo in (
        app / "scripts" / "diario.py",
        app / "scripts" / "goalpacer" / "base.py",
        app / ".git" / "hooks" / "post-merge",
    ):
        arquivo.write_text("# código\n", encoding="utf-8")
        arquivo.chmod(0o644)
    for pasta in (app, app / "scripts", app / "scripts" / "goalpacer", app / ".git", app / ".git" / "hooks"):
        pasta.chmod(0o755)
    return app


def test_pastas_arquivos_e_codigo(tmp_path):
    app = arvore_app(tmp_path)
    assert seguranca.codigo_protegido(app) == []
    (app / ".git" / "hooks" / "post-merge").chmod(0o666)  # um hook alterável vira código no próximo git pull
    (app / "scripts").chmod(0o777)
    problema = seguranca.codigo_protegido(app)
    assert [(p.tipo, p.quantos) for p in problema] == [("codigo_alteravel", 2)]
    dados = tmp_path / "dados"
    dados.mkdir()
    dados.chmod(0o755)
    segredo = tmp_path / "painel-aparelhos.json"
    segredo.write_text("{}", encoding="utf-8")
    segredo.chmod(0o644)
    assert [(p.tipo, p.modo) for p in seguranca.pastas_privadas([dados, tmp_path / "nao-existe"])] == [
        ("pasta_aberta", "0755")
    ]
    assert [(p.tipo, p.modo) for p in seguranca.arquivos_privados([segredo])] == [("arquivo_aberto", "0644")]
    assert seguranca.endurecer(app, [dados], [segredo]) == 4
    assert (
        seguranca.codigo_protegido(app) == []
        and seguranca.pastas_privadas([dados]) == []
        and seguranca.arquivos_privados([segredo]) == []
    )
    assert oct((app / "scripts").stat().st_mode & 0o777) == "0o755" and oct(segredo.stat().st_mode & 0o777) == "0o600"


def test_skill_e_agendador(tmp_path):
    app = arvore_app(tmp_path)
    link = tmp_path / "skills" / "goal-pacer"
    link.parent.mkdir()
    link.symlink_to(app, target_is_directory=True)
    assert seguranca.skill_aponta_para(link, app) == []
    link.unlink()
    link.symlink_to(tmp_path, target_is_directory=True)
    assert [p.tipo for p in seguranca.skill_aponta_para(link, app)] == ["skill_desviada"]
    plist = tmp_path / "com.goal-pacer.diario.plist"
    plist.write_text("<plist/>", encoding="utf-8")
    plist.chmod(0o664)
    assert [p.tipo for p in seguranca.agendador_protegido([plist, tmp_path / "ausente.plist"])] == [
        "agendador_alteravel"
    ]


def test_item_do_doctor_numa_instalacao(tmp_path, monkeypatch):
    import status

    raiz = tmp_path / "raiz"
    jobs = raiz / "jobs"
    (jobs / "logs").mkdir(parents=True)
    dados = raiz / "dados"
    dados.mkdir()
    app = arvore_app(raiz)
    casa = tmp_path / "casa"
    (casa / "Library" / "LaunchAgents").mkdir(parents=True)
    config = tmp_path / "claude"
    (config / "skills").mkdir(parents=True)
    (config / "skills" / "goal-pacer").symlink_to(app, target_is_directory=True)
    for nome, valor in (("GP_RAIZ", raiz), ("HOME", casa), ("CLAUDE_CONFIG_DIR", config)):
        monkeypatch.setenv(nome, str(valor))
    (jobs / "instalacao.json").write_text(json.dumps({"app": str(app)}), encoding="utf-8")
    for pasta in (raiz, jobs, jobs / "logs", dados):
        pasta.chmod(0o700)
    (jobs / "instalacao.json").chmod(0o600)
    item = status.item_seguranca(dados)
    assert item.ok and item.nome == "permissões", item
    (jobs / "logs").chmod(0o755)
    (app / "scripts" / "diario.py").chmod(0o646)
    plist = plataforma.atual().agendador.instalados(plataforma.JOBS)[0]
    plist.write_text("<plist/>", encoding="utf-8")
    plist.chmod(0o666)
    item = status.item_seguranca(dados)
    assert not item.ok
    assert item.detalhe.startswith("%s aberta para outros usuários (0755): rode chmod 700" % (jobs / "logs"))
    assert "1 caminho(s) do app alteráveis por outros usuários" in item.detalhe and item.detalhe.endswith("; e mais 1")
