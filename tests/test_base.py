"""Testes de goalpacer.base: raízes, caminho_dados, TCC, exit codes, sair, log, parser.

``log`` e ``parser_base`` dependem de ``clock``: os testes unitários
substituem ``clock.agora``/``clock.adicionar_args_relogio`` por stubs locais
e os de integração usam o ``clock`` real.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from goalpacer import base, cli, clock, plataforma, telemetria

AGORA_STUB = datetime(2026, 9, 28, 7, 0, 0, tzinfo=timezone(timedelta(hours=-3)))

RE_LINHA_LOG = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} \[[^\]]+\] "
    r"(debug|info|aviso|erro) .*$"
)


def _stub_agora(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "agora", lambda tz=None: AGORA_STUB)


def _stub_relogio(monkeypatch: pytest.MonkeyPatch) -> list:
    """Substitui adicionar_args_relogio por um stub que registra o parser."""
    chamadas: list = []

    def falso(parser: argparse.ArgumentParser) -> None:
        chamadas.append(parser)
        parser.add_argument("--agora", default=None)
        parser.add_argument("--tz", default=None)

    monkeypatch.setattr(clock, "adicionar_args_relogio", falso)
    return chamadas


# --- códigos de saída e GpErro ---------------------------------------------


def test_exit_codes():
    assert base.EXIT_OK == 0
    assert base.EXIT_ESTADO == 2
    assert base.EXIT_VALIDACAO == 3
    assert base.EXIT_IO == 4
    assert base.EXIT_TIMEOUT == 5
    codigos = (base.EXIT_OK, base.EXIT_ESTADO, base.EXIT_VALIDACAO, base.EXIT_IO, base.EXIT_TIMEOUT)
    assert len(set(codigos)) == len(codigos)


def test_gcerro_codigo_e_mensagem():
    erro = base.GpErro(base.EXIT_VALIDACAO, "custo_h inválido")
    assert isinstance(erro, Exception)
    assert erro.codigo == 3
    assert erro.mensagem == "custo_h inválido"
    assert str(erro) == "custo_h inválido"
    with pytest.raises(base.GpErro) as info:
        raise base.GpErro(base.EXIT_IO)
    assert info.value.codigo == 4
    assert info.value.mensagem == ""
    assert str(info.value) == "GpErro"


# --- raízes ----------------------------------------------------------------


@pytest.mark.posix
def test_raiz_padrao_no_home(monkeypatch, tmp_path):
    monkeypatch.delenv("GP_RAIZ", raising=False)
    monkeypatch.delenv("GP_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert base.raiz() == tmp_path / ".goal-pacer"
    assert base.app_dir() == tmp_path / ".goal-pacer" / "app"
    assert base.data_dir() == tmp_path / ".goal-pacer" / "dados"
    assert base.jobs_dir() == tmp_path / ".goal-pacer" / "jobs"
    # raiz_padrao é função: segue o HOME do momento, não o da importação.
    assert base.raiz_padrao() == tmp_path / ".goal-pacer"
    assert not hasattr(base, "RAIZ_PADRAO")


@pytest.mark.posix
def test_raiz_do_codigo_segue_a_instalacao_movida(monkeypatch, tmp_path):
    """Instalação fora de ~/.goal-pacer, sem GP_RAIZ: a raiz vem de onde o código está."""
    monkeypatch.delenv("GP_RAIZ", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "casa"))
    raiz = tmp_path / "dev" / ".goal-pacer"
    codigo = raiz / "app" / "scripts" / "goalpacer" / "base.py"
    codigo.parent.mkdir(parents=True)
    codigo.write_text("", encoding="utf-8")
    # sem instalacao.json acima (um clone de desenvolvimento): não é instalação
    assert base.raiz_do_codigo(str(codigo)) is None
    (raiz / "jobs").mkdir()
    (raiz / "jobs" / "instalacao.json").write_text("{}", encoding="utf-8")
    assert base.raiz_do_codigo(str(codigo)) == raiz
    # pasta que não se chama app: não é o layout da instalação
    outro = tmp_path / "x" / "scripts" / "goalpacer" / "base.py"
    outro.parent.mkdir(parents=True)
    outro.write_text("", encoding="utf-8")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "instalacao.json").write_text("{}", encoding="utf-8")
    assert base.raiz_do_codigo(str(outro)) is None
    # o repositório de testes não está dentro de uma instalação: raiz() cai no padrão do HOME
    assert base.raiz() == tmp_path / "casa" / ".goal-pacer"


@pytest.mark.posix
def test_raiz_do_codigo_com_symlink(monkeypatch, tmp_path):
    """A skill é um symlink para app/: o caminho resolvido é o que vale."""
    raiz = tmp_path / "dev" / ".goal-pacer"
    codigo = raiz / "app" / "scripts" / "goalpacer" / "base.py"
    codigo.parent.mkdir(parents=True)
    codigo.write_text("", encoding="utf-8")
    (raiz / "jobs").mkdir()
    (raiz / "jobs" / "instalacao.json").write_text("{}", encoding="utf-8")
    ligacao = tmp_path / "skills" / "goal-pacer"
    ligacao.parent.mkdir()
    ligacao.symlink_to(raiz / "app")
    assert base.raiz_do_codigo(str(ligacao / "scripts" / "goalpacer" / "base.py")) == raiz


def test_raizes_por_env(dados_tmp):
    raiz = dados_tmp.parent / "raiz"
    assert base.raiz() == raiz
    assert base.app_dir() == raiz / "app"
    assert base.jobs_dir() == raiz / "jobs"
    assert base.data_dir() == dados_tmp


@pytest.mark.posix
def test_raiz_env_vazia_e_til(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GP_RAIZ", "")
    assert base.raiz() == tmp_path / ".goal-pacer"
    monkeypatch.setenv("GP_RAIZ", "~/gp")
    assert base.raiz() == tmp_path / "gp"
    monkeypatch.setenv("GP_DATA_DIR", "~/meus-dados")
    assert base.data_dir() == tmp_path / "meus-dados"


def test_data_dir_env_sobrepoe_raiz(dados_tmp, monkeypatch):
    assert base.data_dir() == dados_tmp
    monkeypatch.delenv("GP_DATA_DIR")
    assert base.data_dir() == dados_tmp.parent / "raiz" / "dados"


# --- caminho_dados ---------------------------------------------------------


def test_caminho_dados_relativo(dados_tmp):
    assert base.caminho_dados("metas", "M01.md") == dados_tmp / "metas" / "M01.md"
    assert base.caminho_dados("dias/2026-09-28.md") == dados_tmp / "dias" / "2026-09-28.md"
    assert base.caminho_dados() == dados_tmp


def test_caminho_dados_recusa_ponto_ponto(dados_tmp):
    for partes in (("..", "x"), ("metas", "..", "..", "x"), ("metas/../../x",), ("..",)):
        with pytest.raises(base.GpErro) as info:
            base.caminho_dados(*partes)
        assert info.value.codigo == base.EXIT_IO
    # ".." colapsado lexicalmente ainda é recusado, mesmo que ficasse dentro.
    with pytest.raises(base.GpErro):
        base.caminho_dados("metas", "..", "registro.json")


def test_caminho_dados_recusa_absoluto_fora(dados_tmp):
    for fora in ("/etc/passwd", str(dados_tmp.parent), str(dados_tmp.parent / "raiz" / "x")):
        with pytest.raises(base.GpErro) as info:
            base.caminho_dados(fora)
        assert info.value.codigo == base.EXIT_IO
    # Prefixo de string parecido (dados2) não é a pasta de dados.
    with pytest.raises(base.GpErro):
        base.caminho_dados(str(dados_tmp.parent / "dados2" / "x.json"))
    # Parte absoluta no meio reinicia o caminho: também é conferida.
    with pytest.raises(base.GpErro):
        base.caminho_dados("metas", "/tmp/x")


def test_caminho_dados_aceita_absoluto_dentro(dados_tmp):
    dentro = dados_tmp / "registro.json"
    assert base.caminho_dados(str(dentro)) == dentro
    assert base.caminho_dados(str(dados_tmp)) == dados_tmp
    assert base.caminho_dados(str(dados_tmp / "metas"), "M02.md") == dados_tmp / "metas" / "M02.md"


def test_caminho_dados_recusa_symlink_para_fora(dados_tmp, tmp_path):
    fora = tmp_path / "fora"
    fora.mkdir()
    # Pasta dentro de dados/ apontando para fora: os markdowns iriam parar lá.
    (dados_tmp / "planos").symlink_to(fora)
    with pytest.raises(base.GpErro) as info:
        base.caminho_dados("planos", "2026-09.md")
    assert info.value.codigo == base.EXIT_IO
    assert "symlink" in info.value.mensagem
    # Arquivo dentro de dados/ apontando para fora: o .bak copiaria conteúdo externo.
    externo = tmp_path / "externo.json"
    externo.write_text("{}", encoding="utf-8")
    (dados_tmp / "registro.json").symlink_to(externo)
    with pytest.raises(base.GpErro):
        base.caminho_dados("registro.json")
    # Link que fica dentro da própria pasta de dados é aceito.
    (dados_tmp / "metas").mkdir()
    (dados_tmp / "atalho").symlink_to(dados_tmp / "metas")
    assert base.caminho_dados("atalho", "M01.md") == dados_tmp / "atalho" / "M01.md"
    # Alvo inexistente continua aceito (a checagem real usa o trecho que existe).
    assert base.caminho_dados("dias", "2026-09-28.md") == dados_tmp / "dias" / "2026-09-28.md"


def test_caminho_dados_base_symlink_aceita(monkeypatch, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    monkeypatch.setenv("GP_DATA_DIR", str(link))
    # A própria pasta de dados pode ser um link; os caminhos devolvidos usam o link.
    assert base.caminho_dados("metas", "M01.md") == link / "metas" / "M01.md"
    (real / "sub").mkdir()
    assert base.caminho_dados("sub", "x.md") == link / "sub" / "x.md"


# --- TCC -------------------------------------------------------------------


def _home_com_pastas_tcc(monkeypatch, tmp_path) -> Path:
    home = tmp_path / "home"
    for nome in plataforma.PASTAS_TCC:
        (home / nome).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.mark.posix
def test_dir_tcc_proibido_desktop_downloads_documents(monkeypatch, tmp_path):
    home = _home_com_pastas_tcc(monkeypatch, tmp_path)
    assert plataforma.PASTAS_TCC == ("Desktop", "Downloads", "Documents")
    for nome in plataforma.PASTAS_TCC:
        assert plataforma.dir_tcc_proibido(home / nome) is True
        assert plataforma.dir_tcc_proibido(home / nome / "goal-pacer" / "dados") is True
        assert plataforma.dir_tcc_proibido(Path("~") / nome / "x") is True
    # Nome parecido fora do HOME ou pasta-irmã com prefixo igual: permitido.
    assert plataforma.dir_tcc_proibido(home / "Downloads2" / "dados") is False
    assert plataforma.dir_tcc_proibido(tmp_path / "Downloads" / "dados") is False


@pytest.mark.posix
def test_dir_tcc_proibido_resolve_symlink(monkeypatch, tmp_path):
    home = _home_com_pastas_tcc(monkeypatch, tmp_path)
    real = home / "Downloads" / "dados"
    real.mkdir()
    link = tmp_path / "atalho"
    link.symlink_to(real)
    assert plataforma.dir_tcc_proibido(link) is True
    assert plataforma.dir_tcc_proibido(link / "metas") is True
    # A própria pasta TCC pode ser um link para fora do HOME: o alvo real também é proibido.
    destino = tmp_path / "docs-reais"
    destino.mkdir()
    (home / "Documents").rmdir()
    (home / "Documents").symlink_to(destino)
    assert plataforma.dir_tcc_proibido(destino / "gp") is True


def test_dir_tcc_permitido_fora(monkeypatch, tmp_path):
    home = _home_com_pastas_tcc(monkeypatch, tmp_path)
    assert plataforma.dir_tcc_proibido(home / ".goal-pacer" / "dados") is False
    assert plataforma.dir_tcc_proibido(home) is False
    assert plataforma.dir_tcc_proibido(tmp_path / "outra" / "pasta") is False
    assert plataforma.dir_tcc_proibido(Path("/private/tmp/gp-dados")) is False


# --- numero ----------------------------------------------------------------


def test_numero_de_resposta():
    assert base.numero(3) == 3.0 and base.numero("1,5") == 1.5 and base.numero(" 2.25 ") == 2.25
    assert (
        base.numero(True) is None and base.numero("") is None and base.numero([1]) is None and base.numero(None) is None
    )


# --- log -------------------------------------------------------------------


def test_log_formato(agora_fixo, monkeypatch, capsys):
    _stub_agora(monkeypatch)
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    telemetria.log("olá mundo")
    saida = capsys.readouterr()
    assert saida.out == ""
    assert saida.err == "2026-09-28T07:00:00-03:00 [-] info olá mundo\n"
    assert RE_LINHA_LOG.match(saida.err.rstrip("\n"))


def test_log_run_id_nivel_e_quebras(agora_fixo, monkeypatch, capsys):
    _stub_agora(monkeypatch)
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    telemetria.log("linha 1\nlinha 2\r\nlinha 3", run_id="r1", nivel="aviso")
    assert capsys.readouterr().err == "2026-09-28T07:00:00-03:00 [r1] aviso linha 1 linha 2 linha 3\n"
    for nivel in telemetria.NIVEIS_LOG:
        telemetria.log("x", nivel=nivel)
        assert RE_LINHA_LOG.match(capsys.readouterr().err.rstrip("\n"))
    with pytest.raises(ValueError):
        telemetria.log("x", nivel="fatal")


def test_log_run_id_do_env(agora_fixo, monkeypatch, capsys):
    _stub_agora(monkeypatch)
    monkeypatch.setenv("GP_RUN_ID", "20260928-070000-diario")
    telemetria.log("começou")
    assert capsys.readouterr().err == "2026-09-28T07:00:00-03:00 [20260928-070000-diario] info começou\n"
    # O argumento explícito vence o ambiente.
    telemetria.log("começou", run_id="manual")
    assert capsys.readouterr().err == "2026-09-28T07:00:00-03:00 [manual] info começou\n"


def test_log_usa_clock_agora(agora_fixo, monkeypatch, capsys):
    """Integração com o clock real: GP_AGORA fixado aparece no carimbo."""
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    telemetria.log("via clock")
    assert capsys.readouterr().err == "%s [-] info via clock\n" % agora_fixo


# --- parser_base -----------------------------------------------------------


def test_parser_base_argumentos_comuns(monkeypatch):
    chamadas = _stub_relogio(monkeypatch)
    parser = cli.parser_base("teste")
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.description == "teste"
    assert chamadas == [parser]
    args = parser.parse_args([])
    assert args.offline is False
    assert args.dados is None
    assert args.run_id is None
    assert args.agora is None and args.tz is None
    args = parser.parse_args(
        [
            "--offline",
            "--dados",
            "/tmp/gp",
            "--run-id",
            "r1",
            "--agora",
            "2026-09-28T07:00:00-03:00",
            "--tz",
            "America/Sao_Paulo",
        ]
    )
    assert args.offline is True
    assert args.dados == Path("/tmp/gp")
    assert args.run_id == "r1"
    assert args.agora == "2026-09-28T07:00:00-03:00"
    assert args.tz == "America/Sao_Paulo"


def test_parser_base_com_clock_real():
    parser = cli.parser_base("teste")
    args = parser.parse_args(["--agora", "2026-09-28T07:00:00-03:00", "--tz", "America/Sao_Paulo", "--offline"])
    assert args.agora == "2026-09-28T07:00:00-03:00"
    assert args.tz == "America/Sao_Paulo"
    assert args.offline is True


def test_aplicar_args_base(dados_tmp, monkeypatch, tmp_path):
    _stub_relogio(monkeypatch)
    # Registrado no monkeypatch para que o valor gravado por aplicar_args_base
    # em os.environ não vaze para os outros testes.
    monkeypatch.setenv("GP_RUN_ID", "anterior")
    aplicados: list = []
    monkeypatch.setattr(clock, "aplicar_args_relogio", aplicados.append)
    parser = cli.parser_base("teste")
    args = parser.parse_args(["--dados", str(tmp_path / "outros"), "--run-id", "r9"])
    cli.aplicar_args_base(args)
    assert os.environ["GP_DATA_DIR"] == str(tmp_path / "outros")
    assert os.environ["GP_RUN_ID"] == "r9"
    assert base.data_dir() == tmp_path / "outros"
    assert aplicados == [args]
    # Sem --dados/--run-id o ambiente fica como estava.
    args = parser.parse_args([])
    cli.aplicar_args_base(args)
    assert os.environ["GP_DATA_DIR"] == str(tmp_path / "outros")
    assert os.environ["GP_RUN_ID"] == "r9"
    assert len(aplicados) == 2 and aplicados[1] is args


@pytest.mark.posix
def test_aplicar_args_base_recusa_pasta_tcc(monkeypatch, tmp_path):
    home = _home_com_pastas_tcc(monkeypatch, tmp_path)
    _stub_relogio(monkeypatch)
    monkeypatch.setattr(clock, "aplicar_args_relogio", lambda args: None)
    monkeypatch.setenv("GP_DATA_DIR", str(tmp_path / "antes"))
    parser = cli.parser_base("teste")
    for pasta in (home / "Downloads" / "gp", home / "Desktop", "~/Documents/goal-pacer/dados"):
        args = parser.parse_args(["--dados", str(pasta)])
        with pytest.raises(base.GpErro) as info:
            cli.aplicar_args_base(args)
        assert info.value.codigo == base.EXIT_VALIDACAO
        assert "Desktop/Downloads/Documents" in info.value.mensagem
        assert os.environ["GP_DATA_DIR"] == str(tmp_path / "antes")
    # Fora das pastas TCC passa (e ~ é expandido).
    cli.aplicar_args_base(parser.parse_args(["--dados", "~/.goal-pacer/dados"]))
    assert os.environ["GP_DATA_DIR"] == str(home / ".goal-pacer" / "dados")


def test_aplicar_args_base_dados_relativo_vira_absoluto(dados_tmp, monkeypatch, tmp_path):
    _stub_relogio(monkeypatch)
    monkeypatch.setattr(clock, "aplicar_args_relogio", lambda args: None)
    monkeypatch.chdir(tmp_path)
    parser = cli.parser_base("teste")
    cli.aplicar_args_base(parser.parse_args(["--dados", "dados-rel"]))
    assert os.environ["GP_DATA_DIR"] == os.path.join(os.getcwd(), "dados-rel")
    assert base.data_dir().is_absolute()
    # Sem resolver symlinks: o caminho gravado é o que o usuário passou, absoluto.
    real = tmp_path / "real-dados"
    real.mkdir()
    (tmp_path / "link-dados").symlink_to(real)
    cli.aplicar_args_base(parser.parse_args(["--dados", "link-dados"]))
    assert os.environ["GP_DATA_DIR"] == os.path.join(os.getcwd(), "link-dados")


def test_aplicar_args_base_com_clock_real(dados_tmp, agora_fixo, monkeypatch):
    """Integração real: --agora/--tz chegam ao clock via aplicar_args_base."""
    monkeypatch.setenv("GP_RUN_ID", "anterior")
    parser = cli.parser_base("teste")
    args = parser.parse_args(["--agora", "2026-10-05T09:30:00", "--tz", "Europe/Lisbon", "--run-id", "r10"])
    cli.aplicar_args_base(args)
    assert os.environ["GP_RUN_ID"] == "r10"
    # --agora sem offset usa o --tz (Lisboa em horário de verão: +01:00).
    assert clock.agora().isoformat() == "2026-10-05T09:30:00+01:00"
    assert str(clock.fuso()) == "Europe/Lisbon"
    # Sem --agora/--tz, GP_AGORA/GP_TZ da fixture voltam a valer.
    cli.aplicar_args_base(parser.parse_args([]))
    assert clock.agora().isoformat() == agora_fixo
    assert str(clock.fuso()) == "America/Sao_Paulo"
