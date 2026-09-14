"""Testes de goalpacer.frontmatter: separar, parse estrito, dump, arquivo, coagir.

``clock.parse_iso`` e ``io.escrever_atomico`` são os reais; o relógio vem
da fixture ``agora_fixo`` do conftest.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from goalpacer import frontmatter as fm
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro
from goalpacer.frontmatter import ErroFrontmatter
from goalpacer.schema import ESQUEMAS, Campo

SP = ZoneInfo("America/Sao_Paulo")
MENOS3 = timezone(timedelta(hours=-3))


def _erro(texto):
    with pytest.raises(ErroFrontmatter) as info:
        fm.parse(texto)
    return info.value


# --- separar -----------------------------------------------------------------


def test_separar_ok():
    texto = "---\nid: M01\ntitulo: Meta\n---\n# Corpo\n\ntexto\n"
    cabeca, corpo = fm.separar(texto)
    assert cabeca == "id: M01\ntitulo: Meta\n"
    assert corpo == "# Corpo\n\ntexto\n"


def test_separar_sem_abertura_erro():
    with pytest.raises(ErroFrontmatter) as info:
        fm.separar("id: M01\n---\ncorpo\n")
    assert info.value.linha == 1
    assert "---" in info.value.motivo
    assert info.value.codigo == EXIT_VALIDACAO
    with pytest.raises(ErroFrontmatter):
        fm.separar("")


def test_separar_sem_fechamento_erro():
    with pytest.raises(ErroFrontmatter) as info:
        fm.separar("---\nid: M01\ncorpo sem fechamento\n")
    assert info.value.linha == 1
    assert "fechamento" in info.value.motivo


def test_separar_vazio_crlf_e_bom():
    assert fm.separar("---\n---\n") == ("", "")
    assert fm.separar("---\n---") == ("", "")
    cabeca, corpo = fm.separar("\ufeff---\r\na: 1\r\n---\r\ncorpo\r\n")
    assert fm.parse(cabeca) == {"a": 1}
    assert corpo == "corpo\r\n"
    # só o primeiro fechamento conta; um "---" no corpo é do corpo
    cabeca, corpo = fm.separar("---\na: 1\n---\nx\n---\ny\n")
    assert corpo == "x\n---\ny\n"


# --- parse: tipos ------------------------------------------------------------


def test_parse_todos_os_tipos(agora_fixo):
    texto = (
        "texto: Reunião com o time\n"
        "inteiro: 42\n"
        "negativo: -7\n"
        "decimal: 12.5\n"
        "expoente: 1e3\n"
        "verdadeiro: true\n"
        "falso: false\n"
        "nulo: null\n"
        "data: 2026-12-31\n"
        "instante: 2026-09-28T07:00:00-03:00\n"
        "zulu: 2026-09-28T10:00:00Z\n"
        "naive: 2026-09-28T07:00:00\n"
        "lista: [a, 2, true]\n"
    )
    dados = fm.parse(texto)
    assert list(dados) == [
        "texto",
        "inteiro",
        "negativo",
        "decimal",
        "expoente",
        "verdadeiro",
        "falso",
        "nulo",
        "data",
        "instante",
        "zulu",
        "naive",
        "lista",
    ]
    assert dados["texto"] == "Reunião com o time"
    assert dados["inteiro"] == 42 and type(dados["inteiro"]) is int
    assert dados["negativo"] == -7
    assert dados["decimal"] == 12.5 and type(dados["decimal"]) is float
    assert dados["expoente"] == 1000.0
    assert dados["verdadeiro"] is True and dados["falso"] is False
    assert dados["nulo"] is None
    assert dados["data"] == date(2026, 12, 31) and type(dados["data"]) is date
    esperado = datetime(2026, 9, 28, 7, 0, tzinfo=MENOS3)
    assert dados["instante"] == esperado and dados["instante"].tzinfo is not None
    assert dados["zulu"] == esperado
    assert dados["naive"] == datetime(2026, 9, 28, 7, 0, tzinfo=SP)
    assert dados["lista"] == ["a", 2, True]


def test_parse_valores_que_parecem_mas_nao_sao():
    dados = fm.parse(
        "hora: 08:00-18:00\nmes: 2026-09\nsemana: 2026-W40\nid: M01\n"
        "hexa: 0x1F\nversao: 1.2.3\ntil: ~casa\nnao_nulo: nulo\n"
    )
    assert dados["hora"] == "08:00-18:00"
    assert dados["mes"] == "2026-09"
    assert dados["semana"] == "2026-W40"
    assert dados["id"] == "M01"
    assert dados["hexa"] == "0x1F"
    assert dados["versao"] == "1.2.3"
    assert dados["til"] == "~casa"
    assert dados["nao_nulo"] == "nulo"


def test_parse_zero_a_esquerda_e_digito_nao_ascii():
    dados = fm.parse("a: 0123\nb: \u0663\nc: 0\nd: -5\ne: +7\nf: 1.5\ng: 2026-0\u0669-28\nh: 007\n")
    assert dados["a"] == "0123"  # zero à esquerda: string, o zero não se perde
    assert dados["b"] == "\u0663"  # dígito árabe: não é número
    assert dados["c"] == 0
    assert dados["d"] == -5
    assert dados["e"] == 7
    assert dados["f"] == 1.5
    assert dados["g"] == "2026-0\u0669-28"
    assert dados["h"] == "007"
    # dump não cita "007" (parse já devolve string): roundtrip simétrico
    texto = fm.dump({"instalacao_id": "0123", "run_id": "007", "n": 7})
    assert texto == "instalacao_id: 0123\nrun_id: 007\nn: 7\n"
    assert fm.parse(texto) == {"instalacao_id": "0123", "run_id": "007", "n": 7}


def test_bom_constante():
    assert len(fm.BOM) == 1 and ord(fm.BOM) == 0xFEFF
    assert fm.separar(fm.BOM + "---\na: 1\n---\n") == ("a: 1\n", "")


def test_parse_string_aspas_duplas_com_escape():
    dados = fm.parse(
        'a: "diz \\"oi\\" e barra \\\\ fim"\nb: "  com espaços  "\nc: ""\nd: "# não é comentário: [1, 2]"\n'
    )
    assert dados["a"] == 'diz "oi" e barra \\ fim'
    assert dados["b"] == "  com espaços  "
    assert dados["c"] == ""
    assert dados["d"] == "# não é comentário: [1, 2]"


def test_parse_string_aspas_simples():
    dados = fm.parse("a: 'texto: com dois-pontos'\nb: 'barra \\ literal'\nc: ''\nd: '2026-01-01'\n")
    assert dados["a"] == "texto: com dois-pontos"
    assert dados["b"] == "barra \\ literal"
    assert dados["c"] == ""
    assert dados["d"] == "2026-01-01"


def test_parse_string_nua_com_dois_pontos_no_valor():
    dados = fm.parse("titulo: Reunião: preparar pauta\nurl: https://exemplo.test/x\n")
    assert dados["titulo"] == "Reunião: preparar pauta"
    assert dados["url"] == "https://exemplo.test/x"


def test_parse_lista_inline():
    dados = fm.parse(
        "vazia: []\n"
        "espaco: [ ]\n"
        "simples: [a, b, c]\n"
        "mista: [1, 2.5, true, null, 2026-01-01, texto]\n"
        'aspas: ["c, d", \'e]f\', "g \\" h"]\n'
        "um: [só]\n"
    )
    assert dados["vazia"] == []
    assert dados["espaco"] == []
    assert dados["simples"] == ["a", "b", "c"]
    assert dados["mista"] == [1, 2.5, True, None, date(2026, 1, 1), "texto"]
    assert dados["aspas"] == ["c, d", "e]f", 'g " h']
    assert dados["um"] == ["só"]


def test_parse_null_e_til():
    dados = fm.parse("a: null\nb: ~\nc: [null, ~]\n")
    assert dados == {"a": None, "b": None, "c": [None, None]}


def test_parse_comentarios_e_linhas_em_branco():
    dados = fm.parse("# cabeçalho\n\na: 1\n   \n# outro\nb: 2\n\n")
    assert dados == {"a": 1, "b": 2}
    assert fm.parse("") == {}
    assert fm.parse("# só comentário\n") == {}


# --- parse: erros com número de linha ----------------------------------------


def test_erro_indentacao_com_linha():
    erro = _erro("a: 1\n  b: 2\n")
    assert erro.linha == 2 and "indentação" in erro.motivo
    erro = _erro("a: 1\n\tb: 2\n")
    assert erro.linha == 2
    erro = _erro("a: 1\nb: 2\n  # comentário indentado\n")
    assert erro.linha == 3


def test_erro_item_de_lista_com_linha():
    erro = _erro("a: 1\n- item\n")
    assert erro.linha == 2 and "- " in erro.motivo
    erro = _erro("a: 1\nb: 2\n-\n")
    assert erro.linha == 3


def test_erro_chave_duplicada_com_linha():
    erro = _erro("a: 1\nb: 2\na: 3\n")
    assert erro.linha == 3 and "duplicada" in erro.motivo and "'a'" in erro.motivo


def test_erro_aninhamento_com_linha():
    erro = _erro("a: 1\npai:\n  filho: 2\n")
    assert erro.linha == 2 and "aninhamento" in erro.motivo
    erro = _erro("a: 1\npai:   \n")
    assert erro.linha == 2


def test_erro_sem_espaco_apos_dois_pontos_com_linha():
    erro = _erro("a: 1\nb:2\n")
    assert erro.linha == 2 and "espaço" in erro.motivo
    erro = _erro("url:https://x\n")
    assert erro.linha == 1


def test_erro_chave_invalida_com_linha():
    for texto, linha in (
        ("Chave: 1\n", 1),
        ("a: 1\nchave-x: 2\n", 2),
        ("a: 1\n1abc: 2\n", 2),
        ("a: 1\nchave com espaço: 2\n", 2),
    ):
        erro = _erro(texto)
        assert erro.linha == linha and "chave inválida" in erro.motivo
    erro = _erro("a: 1\nsem dois pontos\n")
    assert erro.linha == 2 and "chave: valor" in erro.motivo


def test_erro_lista_aninhada_com_linha():
    erro = _erro("a: 1\nb: [x, [y, z]]\n")
    assert erro.linha == 2 and "aninhada" in erro.motivo
    erro = _erro("b: [[x]]\n")
    assert erro.linha == 1


def test_erro_lista_mal_formada_com_linha():
    erro = _erro("a: 1\nb: [x, y\n")
    assert erro.linha == 2 and "]" in erro.motivo
    erro = _erro("b: [x, , y]\n")
    assert "item vazio" in erro.motivo
    erro = _erro("b: [x,]\n")
    assert "item vazio" in erro.motivo
    erro = _erro("b: [x]y]\n")
    assert "colchete" in erro.motivo
    erro = _erro('b: ["x, y]\n')
    assert "fechamento" in erro.motivo


def test_erro_string_sem_fechamento_e_escape_invalido():
    erro = _erro('a: 1\nb: "aberta\n')
    assert erro.linha == 2 and "fechamento" in erro.motivo
    erro = _erro("b: 'aberta\n")
    assert "fechamento" in erro.motivo
    erro = _erro('a: 1\nb: "tab \\t"\n')
    assert erro.linha == 2 and "escape inválido" in erro.motivo
    erro = _erro('b: "fim \\\n')
    assert "escape" in erro.motivo
    erro = _erro('b: "x" y\n')
    assert "depois da string" in erro.motivo
    erro = _erro("b: 'x' # comentário\n")
    assert "depois da string" in erro.motivo


def test_erro_comentario_no_meio_da_linha():
    erro = _erro("a: 1\ncusto_h: 12 # horas\n")
    assert erro.linha == 2 and "comentário" in erro.motivo
    erro = _erro("a: #x\n")
    assert erro.linha == 1
    erro = _erro("a: [x, y # z]\n")
    assert "comentário" in erro.motivo


def test_erro_data_e_datetime_invalidos(agora_fixo):
    erro = _erro("a: 1\nprazo: 2026-13-01\n")
    assert erro.linha == 2 and "data inválida" in erro.motivo
    erro = _erro("a: 1\ncriado_em: 2026-09-28T25:00:00\n")
    assert erro.linha == 2 and "datetime inválido" in erro.motivo


# --- dump --------------------------------------------------------------------


def test_dump_roundtrip(agora_fixo):
    dados = {
        "id": "M01",
        "titulo": 'Reunião: preparar "pauta" #1',
        "horizonte": "trimestre",
        "prazo": date(2026, 12, 31),
        "prazo_externo": False,
        "custo_h": 40.0,
        "inteiro": 3,
        "grande": 1e20,
        "palavras_chave": ["tese", "orientador", "c, d"],
        "vazia": [],
        "status": "ativa",
        "progresso": None,
        "criado_em": datetime(2026, 9, 28, 7, 0, tzinfo=MENOS3),
        "micro": datetime(2026, 9, 28, 7, 0, 0, 123456, tzinfo=timezone.utc),
        "hora": "08:00-18:00",
        "parece_int": "007",
        "parece_data": "2026-01-01",
        "parece_bool": "true",
        "parece_nulo": "~",
        "barra": "C:\\pasta",
        "vazio": "",
        "pontas": " x ",
        "traco": "- item",
    }
    texto = fm.dump(dados)
    assert texto.endswith("\n") and "---" not in texto
    volta = fm.parse(texto)
    assert volta == dados
    assert list(volta) == list(dados)
    assert fm.dump(volta) == texto
    assert fm.dump({}) == ""


def test_dump_aspas_so_quando_necessario():
    texto = fm.dump(
        {
            "nua": "Reunião com o time",
            "id": "M01",
            "semana": "2026-W40",
            "vazia": "",
            "dois_pontos": "08:00-18:00",
            "cerquilha": "item #1",
            "colchete": "a[0]",
            "virgula": "a, b",
            "aspas": 'diz "oi"',
            "simples": "it's",
            "pontas": " x",
            "numero": "42",
            "decimal": "1.5",
            "booleano": "false",
            "nulo": "null",
            "data": "2026-01-01",
            "instante": "2026-01-01T00:00:00",
            "barra": "a\\b",
            "lista": ["x", "y z", "a,b", ""],
        }
    )
    assert texto == (
        "nua: Reunião com o time\n"
        "id: M01\n"
        "semana: 2026-W40\n"
        'vazia: ""\n'
        'dois_pontos: "08:00-18:00"\n'
        'cerquilha: "item #1"\n'
        'colchete: "a[0]"\n'
        'virgula: "a, b"\n'
        'aspas: "diz \\"oi\\""\n'
        'simples: "it\'s"\n'
        'pontas: " x"\n'
        'numero: "42"\n'
        'decimal: "1.5"\n'
        'booleano: "false"\n'
        'nulo: "null"\n'
        'data: "2026-01-01"\n'
        'instante: "2026-01-01T00:00:00"\n'
        "barra: a\\b\n"
        'lista: [x, y z, "a,b", ""]\n'
    )


def test_dump_deterministico_ordem_de_insercao():
    a = fm.dump({"z": 1, "a": 2, "m": [1, 2]})
    b = fm.dump({"z": 1, "a": 2, "m": [1, 2]})
    assert a == b == "z: 1\na: 2\nm: [1, 2]\n"
    assert fm.dump({"a": 2, "z": 1}) == "a: 2\nz: 1\n"
    assert fm.dump({"t": True, "f": False, "n": None, "x": 1.0, "d": date(2026, 1, 2)}) == (
        "t: true\nf: false\nn: null\nx: 1.0\nd: 2026-01-02\n"
    )


def test_dump_recusa_o_que_nao_representa():
    with pytest.raises(GpErro) as info:
        fm.dump({"a": "linha 1\nlinha 2"})
    assert info.value.codigo == EXIT_VALIDACAO and "quebra de linha" in info.value.mensagem
    with pytest.raises(GpErro):
        fm.dump({"a": [[1, 2]]})
    with pytest.raises(GpErro):
        fm.dump({"a": {"b": 1}})
    with pytest.raises(GpErro):
        fm.dump({"Chave": 1})
    with pytest.raises(GpErro):
        fm.dump({"a": float("inf")})


# --- arquivos ----------------------------------------------------------------


def test_dump_recusa_chave_com_quebra_de_linha():
    # RE_CHAVE com "$" casaria "a\n"; com \Z e fullmatch, não.
    for chave in ("a\n", "a\r", "ab\n", "a\nb"):
        with pytest.raises(GpErro) as exc:
            fm.dump({chave: 1, "b": 2})
        assert exc.value.codigo == EXIT_VALIDACAO
    with pytest.raises(fm.ErroFrontmatter):
        fm.parse("a\r: 1\n".replace("\r", "\x0b"))


def test_ler_e_escrever_arquivo(dados_tmp, agora_fixo):
    path = dados_tmp / "metas" / "M01.md"
    path.parent.mkdir()
    dados = {
        "id": "M01",
        "titulo": "Terminar a tese",
        "prazo": date(2026, 12, 31),
        "custo_h": 120.0,
        "palavras_chave": ["tese", "orientador"],
        "criado_em": datetime(2026, 9, 28, 7, 0, tzinfo=MENOS3),
    }
    corpo = "# Terminar a tese\n\nprosa livre com --- no meio\n"
    fm.escrever_arquivo(path, dados, corpo)
    texto = path.read_text(encoding="utf-8")
    assert texto.startswith("---\nid: M01\n")
    assert "\n---\n# Terminar a tese\n" in texto
    lidos, corpo_lido = fm.ler_arquivo(path)
    assert lidos == dados
    assert corpo_lido == corpo
    # regravar com corpo vazio
    fm.escrever_arquivo(path, {"id": "M02"}, "")
    assert fm.ler_arquivo(path) == ({"id": "M02"}, "")


def test_ler_arquivo_ausente_e_linha_do_arquivo(tmp_path):
    with pytest.raises(GpErro) as info:
        fm.ler_arquivo(tmp_path / "nao_existe.md")
    assert info.value.codigo == EXIT_IO
    path = tmp_path / "quebrado.md"
    path.write_text("---\nid: M01\nid: M02\n---\ncorpo\n", encoding="utf-8")
    with pytest.raises(ErroFrontmatter) as info:
        fm.ler_arquivo(path)
    assert info.value.linha == 3
    assert "duplicada" in info.value.motivo
    assert str(path) in info.value.mensagem and "linha 3" in info.value.mensagem
    path.write_text("sem cabeça\n", encoding="utf-8")
    with pytest.raises(ErroFrontmatter) as info:
        fm.ler_arquivo(path)
    assert info.value.linha == 1
    path.write_bytes(b"---\n\xff\xfe\n---\n")
    with pytest.raises(GpErro) as info:
        fm.ler_arquivo(path)
    assert info.value.codigo == EXIT_IO


# --- coagir ------------------------------------------------------------------

ESQUEMA_LOCAL = [
    Campo("id", "str", True),
    Campo("titulo", "str", True),
    Campo("horizonte", "enum", True, ("trimestre", "semestre", "ano")),
    Campo("prazo", "date", True),
    Campo("prazo_externo", "bool", False, default=False),
    Campo("custo_h", "float", True),
    Campo("buffer_min", "int", False, default=15),
    Campo("palavras_chave", "list", False, default=[]),
    Campo("fontes", "list", False, ("gmail", "notion"), default=[]),
    Campo("status", "enum", False, ("ativa", "pausada"), default="ativa"),
    Campo("progresso_pct", "float", False),
    Campo("criado_em", "datetime", True),
    Campo("extras", "dict", False, default={}),
]


def test_coagir_converte_tipos_e_defaults(agora_fixo):
    dados = {
        "id": 7,
        "titulo": "Tese",
        "horizonte": "ano",
        "prazo": "2026-12-31",
        "custo_h": 40,
        "buffer_min": "20",
        "status": None,
        "criado_em": "2026-09-28T07:00:00-03:00",
    }
    saida, erros = fm.coagir(dados, ESQUEMA_LOCAL)
    assert erros == []
    assert saida == {
        "id": "7",
        "titulo": "Tese",
        "horizonte": "ano",
        "prazo": date(2026, 12, 31),
        "prazo_externo": False,
        "custo_h": 40.0,
        "buffer_min": 20,
        "palavras_chave": [],
        "fontes": [],
        "status": "ativa",
        "criado_em": datetime(2026, 9, 28, 7, 0, tzinfo=MENOS3),
        "extras": {},
    }
    assert type(saida["custo_h"]) is float and type(saida["buffer_min"]) is int
    assert "progresso_pct" not in saida
    # defaults são cópias novas
    saida["palavras_chave"].append("x")
    assert ESQUEMA_LOCAL[7].default == []
    # variantes: datetime → date, date → datetime, "True" → bool, 15.0 → int, null explícito
    saida, erros = fm.coagir(
        {
            "id": "M01",
            "titulo": "t",
            "horizonte": "ano",
            "prazo": datetime(2026, 12, 31, 10, 0, tzinfo=MENOS3),
            "custo_h": "12.5",
            "prazo_externo": "True",
            "buffer_min": 15.0,
            "criado_em": date(2026, 9, 28),
            "progresso_pct": None,
        },
        ESQUEMA_LOCAL,
    )
    assert erros == []
    assert saida["prazo"] == date(2026, 12, 31)
    assert saida["custo_h"] == 12.5
    assert saida["prazo_externo"] is True
    assert saida["buffer_min"] == 15 and type(saida["buffer_min"]) is int
    assert saida["criado_em"] == datetime(2026, 9, 28, 0, 0, tzinfo=SP)
    assert saida["progresso_pct"] is None


def test_coagir_erro_de_enum():
    saida, erros = fm.coagir(_base(horizonte="decada", status="feita"), ESQUEMA_LOCAL)
    assert "horizonte: valor 'decada' fora de {trimestre, semestre, ano}" in erros
    assert any(e.startswith("status: ") and "fora de" in e for e in erros)
    assert saida["horizonte"] == "decada"
    saida, erros = fm.coagir(_base(fontes=["gmail", "drive", 3]), ESQUEMA_LOCAL)
    assert erros == ["fontes: itens 'drive', 3 fora de {gmail, notion}"]


def test_coagir_lista_com_itens_nao_str():
    # O esquema diz que list é sempre lista de strings: int/bool/date não passam nem convertidos.
    saida, erros = fm.coagir(_base(palavras_chave=[1, True, date(2026, 1, 1), "ok"]), ESQUEMA_LOCAL)
    assert erros == ["palavras_chave: itens 1, True, datetime.date(2026, 1, 1) não são str"]
    assert saida["palavras_chave"] == [1, True, date(2026, 1, 1), "ok"]
    saida, erros = fm.coagir(_base(palavras_chave=("a", "b")), ESQUEMA_LOCAL)
    assert erros == [] and saida["palavras_chave"] == ["a", "b"]
    # Com enum, o erro de enum vem primeiro (mensagem já fixada acima).
    _, erros = fm.coagir(_base(fontes=[3]), ESQUEMA_LOCAL)
    assert erros == ["fontes: itens 3 fora de {gmail, notion}"]


def test_coagir_erro_de_tipo():
    saida, erros = fm.coagir(
        _base(
            custo_h="muito",
            prazo="amanhã",
            prazo_externo="sim",
            buffer_min=1.5,
            titulo=True,
            palavras_chave="tese",
            extras=[1],
        ),
        ESQUEMA_LOCAL,
    )
    campos = sorted(e.split(":")[0] for e in erros)
    assert campos == ["buffer_min", "custo_h", "extras", "palavras_chave", "prazo", "prazo_externo", "titulo"]
    assert "custo_h: esperado float, veio str 'muito'" in erros
    assert saida["custo_h"] == "muito"
    _, erros = fm.coagir(_base(criado_em="2026-99-99T00:00:00"), ESQUEMA_LOCAL)
    assert len(erros) == 1 and erros[0].startswith("criado_em: datetime inválido")
    _, erros = fm.coagir(_base(criado_em=12), ESQUEMA_LOCAL)
    assert erros == ["criado_em: esperado datetime, veio int 12"]
    _, erros = fm.coagir(_base(prazo="2026-02-30"), ESQUEMA_LOCAL)
    assert erros == ["prazo: data inválida: '2026-02-30'"]
    _, erros = fm.coagir(_base(buffer_min=True), ESQUEMA_LOCAL)
    assert erros == ["buffer_min: esperado int, veio bool True"]


def test_coagir_obrigatorio_ausente():
    saida, erros = fm.coagir({"titulo": "t", "id": None}, ESQUEMA_LOCAL)
    assert erros == [
        "id: obrigatório",
        "horizonte: obrigatório",
        "prazo: obrigatório",
        "custo_h: obrigatório",
        "criado_em: obrigatório",
    ]
    assert saida["titulo"] == "t" and "id" not in saida
    assert saida["status"] == "ativa"


def test_coagir_campo_desconhecido_passa_com_erro():
    saida, erros = fm.coagir(dict(_base(), notas="x"), ESQUEMA_LOCAL)
    assert erros == ["notas: campo desconhecido no esquema"]
    assert saida["notas"] == "x"
    assert list(saida)[-1] == "notas"


def test_coagir_com_esquema_metas_do_schema(agora_fixo):
    texto = (
        "id: M01\ntitulo: Terminar a tese\nhorizonte: semestre\nprazo: 2026-12-31\n"
        "custo_h_semana_escolhido: 6\nsemanas_pesquisa: 20\nconfianca: usuario\n"
        "palavras_chave: [tese, orientador]\n"
        "criado_em: 2026-09-28T07:00:00-03:00\n"
    )
    saida, erros = fm.coagir(fm.parse(texto), ESQUEMAS["metas"])
    assert erros == []
    assert saida["custo_h_semana_escolhido"] == 6.0 and saida["estado"] == "ativa"
    assert saida["semanas_pesquisa"] == 20 and saida["fonte"] == ""
    assert saida["prazo_externo"] is False
    assert saida["prazo"] == date(2026, 12, 31)
    assert "custo_h_semana_min" not in saida
    assert fm.parse(fm.dump(saida)) == saida


def _base(**sobrepoe):
    dados = {
        "id": "M01",
        "titulo": "Tese",
        "horizonte": "ano",
        "prazo": date(2026, 12, 31),
        "custo_h": 40.0,
        "criado_em": datetime(2026, 9, 28, 7, 0, tzinfo=MENOS3),
    }
    dados.update(sobrepoe)
    return dados
