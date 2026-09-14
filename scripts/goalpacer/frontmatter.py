"""Subconjunto plano de YAML para o front-matter dos markdowns (achado 5.2).

Parser ESTRITO, sem PyYAML. Gramática aceita::

    ---                          primeira linha, obrigatória
    chave: valor                 chave ^[a-z][a-z0-9_]*$; ": " separa
    outra: "texto com \\" e \\\\"  string entre aspas duplas (escapes \\" e \\\\)
    mais: 'texto'                string entre aspas simples (sem escapes)
    lista: [a, 2, "c d", true]   lista inline; itens com as mesmas regras
    vazio: null                  null ou ~ vira None
    # comentário                 só em linha inteira
                                 linha em branco ignorada
    ---                          fechamento, obrigatório

Valor nu é string, salvo se casar inteiro, decimal, true/false, null, data
AAAA-MM-DD ou datetime ISO (com ``T``). Só dígitos ASCII contam como número
e inteiro com zero à esquerda (``007``) é string (o zero se perderia;
``dump`` não o cita, então ``parse(dump(d)) == d``). Tudo depois do
primeiro ": " é o valor; espaços nas pontas são descartados.

Qualquer outra coisa (indentação, "- item", chave duplicada, dois-pontos sem
espaço, ``chave:`` sem valor, lista dentro de lista, comentário no meio da
linha, escape desconhecido) é ``ErroFrontmatter(linha, motivo)``.

Numeração das linhas: ``parse`` conta a partir do texto recebido (1 = sua
primeira linha); ``separar`` e ``ler_arquivo`` contam a partir do arquivo
(1 = o ``---`` inicial), e ``ler_arquivo`` prefixa a mensagem com o caminho.

``coagir`` usa ``schema.Campo`` para converter e validar os tipos declarados.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from goalpacer import clock, io as gpio, schema
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro
from goalpacer.schema import RE_LINHA_CAMPO_BLOCO, RE_SUBSECAO_TASK, Campo

DELIMITADOR = "---"
BOM = "\ufeff"

# Todas com \Z e fullmatch: "a\n" não pode passar por chave nem por número.
RE_CHAVE = re.compile(r"^[a-z][a-z0-9_]*\Z")
RE_INT = re.compile(r"^[+-]?[0-9]+\Z")
RE_ZERO_ESQUERDA = re.compile(r"^[+-]?0[0-9]+\Z")
RE_FLOAT = re.compile(r"^[+-]?([0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)([eE][+-]?[0-9]+)?\Z")
RE_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
RE_DATETIME = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?([Zz]|[+-][0-9]{2}:?[0-9]{2})?\Z"
)

NULOS = ("null", "~")
BOOLS = {"true": True, "false": False}

# Caracteres que obrigam aspas numa string ao gravar (além de "parecer outro tipo").
CHARS_ASPAS = ":#[],\"'"


class ErroFrontmatter(GpErro):
    """Erro de sintaxe no front-matter, com a linha (1-based) e o motivo."""

    def __init__(self, linha: int, motivo: str) -> None:
        super().__init__(EXIT_VALIDACAO, "front-matter, linha %d: %s" % (linha, motivo))
        self.linha = linha
        self.motivo = motivo


# --- leitura -----------------------------------------------------------------


def separar(texto: str) -> tuple[str, str]:
    """Divide um markdown em (front-matter sem os ``---``, corpo).

    Exige ``---`` na primeira linha e um ``---`` de fechamento; senão
    ``ErroFrontmatter`` (linha 1). O front-matter devolvido termina em
    ``\\n`` quando não é vazio; o corpo começa na linha seguinte ao
    fechamento. Aceita BOM e CRLF.
    """
    texto = texto.removeprefix(BOM)
    linhas = texto.split("\n")
    if linhas[0].rstrip() != DELIMITADOR:
        raise ErroFrontmatter(1, "esperado '%s' na primeira linha" % DELIMITADOR)
    for i in range(1, len(linhas)):
        if linhas[i].rstrip() == DELIMITADOR:
            fm = "\n".join(linhas[1:i])
            if fm:
                fm += "\n"
            return fm, "\n".join(linhas[i + 1 :])
    raise ErroFrontmatter(1, "faltou o '%s' de fechamento" % DELIMITADOR)


def parse(texto_fm: str) -> dict[str, Any]:
    """Front-matter (sem os ``---``) → dict na ordem do arquivo.

    Tipos devolvidos: str, int, float, bool, None, ``datetime.date``,
    ``datetime.datetime`` (consciente, via ``clock.parse_iso``), list.
    Erros de sintaxe são ``ErroFrontmatter`` com a linha do texto recebido.
    """
    return _parse_linhas(texto_fm.split("\n"), 0)


def _parse_linhas(linhas: list[str], deslocamento: int) -> dict[str, Any]:
    """Percorre as linhas; ``deslocamento`` soma à numeração dos erros."""
    dados: dict[str, Any] = {}
    for numero, bruta in enumerate(linhas, start=1 + deslocamento):
        par = _chave_e_resto(bruta.rstrip("\r"), numero)
        if par is None:
            continue
        chave, resto = par
        if chave in dados:
            raise ErroFrontmatter(numero, "chave duplicada: %r" % chave)
        dados[chave] = _valor(resto.strip(), numero)
    return dados


def _chave_e_resto(linha: str, numero: int) -> Optional[tuple[str, str]]:
    """``(chave, resto)`` de uma linha ``chave: valor``; ``None`` para linha vazia ou comentário."""
    if linha.strip() == "" or linha.startswith("#"):
        return None
    if linha[0] in " \t":
        raise ErroFrontmatter(numero, "indentação não permitida")
    if linha == "-" or linha.startswith("- "):
        raise ErroFrontmatter(numero, "item de lista ('- ') não permitido; use lista inline [a, b]")
    chave, sep, resto = linha.partition(":")
    if not sep:
        raise ErroFrontmatter(numero, "esperado 'chave: valor'")
    if not RE_CHAVE.fullmatch(chave):
        raise ErroFrontmatter(numero, "chave inválida: %r (esperado [a-z][a-z0-9_]*)" % chave)
    if resto.strip() == "":
        raise ErroFrontmatter(numero, "valor ausente depois de ':' (aninhamento não permitido; use null)")
    if not resto.startswith(" "):
        raise ErroFrontmatter(numero, "faltou espaço depois de ':'")
    return chave, resto


def render_valor(valor: Any, chave: str = "") -> str:
    """Um valor no subconjunto, como ``dump`` o escreveria depois de ``chave: ``
    (aspas só quando necessário, datas ISO, listas inline)."""
    return _render(valor, chave, em_lista=False)


def parse_blocos(corpo: str, deslocamento: int = 0) -> list[dict[str, Any]]:
    """Blocos de ``dias/*.md``: cada ``### D-AAAA-MM-DD-<ss> <título>``
    seguido de linhas ``- chave: valor`` (mesma gramática de valores do
    front-matter, chaves ``[a-z][a-z0-9_]*``, sem repetição). Devolve um
    dict por bloco com ``id`` e ``titulo`` do título mais os campos das
    linhas, e ``_linha`` (número da linha do título no corpo, somado a
    ``deslocamento``). Dentro de um bloco, linha ``- `` que não é
    ``- chave: valor``, chave repetida ou ``id``/``titulo`` nas linhas são
    ``ErroFrontmatter``. Qualquer outra linha (prosa, seção ``##``) encerra
    o bloco corrente; fora de um bloco tudo é ignorado (listas de prosa em
    ``## Progresso`` são legítimas).
    """
    blocos: list[dict[str, Any]] = []
    atual: Optional[dict[str, Any]] = None
    for numero, bruta in enumerate(corpo.split("\n"), start=1 + deslocamento):
        linha = bruta.rstrip("\r")
        titulo = RE_SUBSECAO_TASK.match(linha)
        if titulo is not None:
            atual = {"id": titulo.group(1), "titulo": (titulo.group(2) or "").strip(), "_linha": numero}
            blocos.append(atual)
        elif atual is not None:
            atual = _linha_do_bloco(atual, linha, numero)
    return blocos


def _linha_do_bloco(atual: dict[str, Any], linha: str, numero: int) -> Optional[dict[str, Any]]:
    """Grava o campo da linha no bloco; devolve o bloco que segue aberto (``None`` quando a linha o encerra)."""
    campo = RE_LINHA_CAMPO_BLOCO.match(linha)
    if campo is None:
        if linha.startswith("- "):
            raise ErroFrontmatter(numero, "esperado '- chave: valor' dentro do bloco %s" % atual["id"])
        return None if linha.strip() else atual
    chave, resto = campo.groups()
    if chave in ("id", "titulo", "_linha"):
        raise ErroFrontmatter(numero, "%r vem do título do bloco, não das linhas" % chave)
    if chave in atual:
        raise ErroFrontmatter(numero, "chave duplicada no bloco: %r" % chave)
    if resto.strip() == "":
        raise ErroFrontmatter(numero, "valor ausente depois de ':' (use null)")
    atual[chave] = _valor(resto.strip(), numero)
    return atual


def _valor(texto: str, linha: int) -> Any:
    """Um valor já sem espaços nas pontas: lista inline ou escalar."""
    if texto.startswith("["):
        return _lista(texto, linha)
    return _escalar(texto, linha)


def _escalar(texto: str, linha: int) -> Any:
    if texto[0] == '"':
        valor, resto = _string_aspas_duplas(texto, linha)
    elif texto[0] == "'":
        valor, resto = _string_aspas_simples(texto, linha)
    else:
        return _escalar_nu(texto, linha)
    if resto.strip():
        raise ErroFrontmatter(linha, "conteúdo depois da string entre aspas")
    return valor


def _classificar_nu(texto: str) -> str:
    """Tipo que um valor nu assume: null, bool, int, float, date, datetime ou str."""
    if texto in NULOS:
        return "null"
    if texto in BOOLS:
        return "bool"
    if RE_INT.fullmatch(texto):
        return "str" if RE_ZERO_ESQUERDA.fullmatch(texto) else "int"
    if RE_FLOAT.fullmatch(texto):
        return "float"
    if RE_DATA.fullmatch(texto):
        return "date"
    if RE_DATETIME.fullmatch(texto):
        return "datetime"
    return "str"


def _escalar_nu(texto: str, linha: int) -> Any:
    if texto.startswith("#") or " #" in texto:
        raise ErroFrontmatter(linha, "comentário só em linha inteira; use aspas")
    tipo = _classificar_nu(texto)
    if tipo == "null":
        return None
    if tipo == "bool":
        return BOOLS[texto]
    if tipo == "int":
        return int(texto)
    if tipo == "float":
        return float(texto)
    if tipo == "date":
        try:
            return date.fromisoformat(texto)
        except ValueError:
            raise ErroFrontmatter(linha, "data inválida: %r" % texto) from None
    if tipo == "datetime":
        try:
            return clock.parse_iso(texto)
        except GpErro as erro:
            raise ErroFrontmatter(linha, "datetime inválido: %r (%s)" % (texto, erro.mensagem)) from None
    return texto


def _string_aspas_duplas(texto: str, linha: int) -> tuple[str, str]:
    """Lê ``"..."`` no início de ``texto``; devolve (valor, resto)."""
    partes: list[str] = []
    i, n = 1, len(texto)
    while i < n:
        c = texto[i]
        if c == "\\":
            if i + 1 >= n:
                raise ErroFrontmatter(linha, "escape incompleto no fim da string")
            prox = texto[i + 1]
            if prox not in '"\\':
                raise ErroFrontmatter(linha, "escape inválido: '\\%s' (só \\\" e \\\\)" % prox)
            partes.append(prox)
            i += 2
            continue
        if c == '"':
            return "".join(partes), texto[i + 1 :]
        partes.append(c)
        i += 1
    raise ErroFrontmatter(linha, "string sem aspas duplas de fechamento")


def _string_aspas_simples(texto: str, linha: int) -> tuple[str, str]:
    fim = texto.find("'", 1)
    if fim < 0:
        raise ErroFrontmatter(linha, "string sem aspas simples de fechamento")
    return texto[1:fim], texto[fim + 1 :]


def _lista(texto: str, linha: int) -> list:
    if not texto.endswith("]"):
        raise ErroFrontmatter(linha, "lista sem ']' de fechamento")
    interior = texto[1:-1]
    if interior.strip() == "":
        return []
    itens = []
    for bruto in _dividir_itens(interior, linha):
        item = bruto.strip()
        if item == "":
            raise ErroFrontmatter(linha, "item vazio na lista")
        if item.startswith("["):
            raise ErroFrontmatter(linha, "lista aninhada não permitida")
        if item[0] not in "\"'" and ("[" in item or "]" in item):
            raise ErroFrontmatter(linha, "colchete dentro de item da lista; use aspas")
        itens.append(_escalar(item, linha))
    return itens


def _dividir_itens(interior: str, linha: int) -> list[str]:
    """Separa por vírgulas fora de aspas (respeita ``\\"`` nas aspas duplas)."""
    itens: list[str] = []
    atual: list[str] = []
    aspas: Optional[str] = None
    caracteres = iter(interior)
    for c in caracteres:
        if aspas is not None:
            atual.append(c)
            if aspas == '"' and c == "\\":
                atual.append(next(caracteres, ""))  # o escapado entra como está (inclusive a aspa)
            elif c == aspas:
                aspas = None
        elif c == ",":
            itens.append("".join(atual))
            atual = []
        else:
            if c in "\"'" and not "".join(atual).strip():
                aspas = c
            atual.append(c)
    if aspas is not None:
        raise ErroFrontmatter(linha, "string sem aspas de fechamento dentro da lista")
    itens.append("".join(atual))
    return itens


# --- escrita -----------------------------------------------------------------


def dump(dados: dict[str, Any]) -> str:
    """dict → texto de front-matter determinístico, SEM os ``---``.

    Ordem de inserção; strings com aspas duplas só quando necessário
    (vazias, com ``:``, ``#``, ``[``, ``]``, ``,``, aspas, espaços nas
    pontas ou que pareceriam outro tipo); date/datetime em ISO; listas
    inline; None → ``null``; bool → ``true``/``false``. ``parse(dump(d)) ==
    d`` para datetimes conscientes. Chave inválida, quebra de linha numa
    string, lista aninhada ou tipo sem representação é
    ``GpErro(EXIT_VALIDACAO)``.
    """
    linhas = []
    for chave, valor in dados.items():
        if not isinstance(chave, str) or not RE_CHAVE.fullmatch(chave):
            raise GpErro(EXIT_VALIDACAO, "front-matter: chave inválida: %r" % (chave,))
        linhas.append("%s: %s\n" % (chave, _render(valor, chave, em_lista=False)))
    return "".join(linhas)


def _render(valor: Any, chave: str, *, em_lista: bool) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise GpErro(EXIT_VALIDACAO, "front-matter: %s: número não finito" % chave)
        return repr(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, str):
        return _render_str(valor, chave)
    if isinstance(valor, (list, tuple)):
        if em_lista:
            raise GpErro(EXIT_VALIDACAO, "front-matter: %s: lista aninhada não suportada" % chave)
        return "[" + ", ".join(_render(item, chave, em_lista=True) for item in valor) + "]"
    raise GpErro(
        EXIT_VALIDACAO,
        "front-matter: %s: tipo %s sem representação" % (chave, type(valor).__name__),
    )


def _render_str(texto: str, chave: str) -> str:
    if "\n" in texto or "\r" in texto:
        raise GpErro(EXIT_VALIDACAO, "front-matter: %s: quebra de linha não suportada" % chave)
    if _precisa_aspas(texto):
        return '"' + texto.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return texto


def _precisa_aspas(texto: str) -> bool:
    if texto == "" or texto != texto.strip():
        return True
    if any(c in texto for c in CHARS_ASPAS):
        return True
    if texto.startswith("- ") or texto == "-":
        return True
    return _classificar_nu(texto) != "str"


# --- arquivos ----------------------------------------------------------------


def ler_arquivo(path: Path) -> tuple[dict[str, Any], str]:
    """Lê um markdown (UTF-8) e devolve ``(parse(fm), corpo)``.

    Arquivo ausente, ilegível ou fora de UTF-8 é ``GpErro(EXIT_IO)``;
    sintaxe é ``ErroFrontmatter`` com a linha do arquivo e a mensagem
    prefixada pelo caminho.
    """
    path = Path(path)
    try:
        texto = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise GpErro(EXIT_IO, "arquivo não encontrado: %s" % path) from None
    except UnicodeDecodeError:
        raise GpErro(EXIT_IO, "arquivo não é UTF-8: %s" % path) from None
    except OSError as erro:
        raise GpErro(EXIT_IO, "erro ao ler %s: %s" % (path, erro)) from None
    try:
        fm, corpo = separar(texto)
        dados = _parse_linhas(fm.split("\n"), 1)
    except ErroFrontmatter as erro:
        novo = ErroFrontmatter(erro.linha, erro.motivo)
        novo.mensagem = "%s: %s" % (path, novo.mensagem)
        raise novo from None
    return dados, corpo


def escrever_arquivo(path: Path, dados: dict[str, Any], corpo: str) -> None:
    """Grava ``---\\n<dump(dados)>---\\n<corpo>`` via ``io.escrever_atomico``."""
    texto = DELIMITADOR + "\n" + dump(dados) + DELIMITADOR + "\n" + corpo
    gpio.escrever_atomico(Path(path), texto)


# --- coerção pelo esquema ----------------------------------------------------


def coagir(dados: dict[str, Any], esquema_arquivo: list[Campo]) -> tuple[dict[str, Any], list[str]]:
    """Converte e valida ``dados`` contra uma lista de ``schema.Campo``.

    Converte str → int/float/bool/date/datetime quando o esquema pede,
    valida enums e listas, aplica defaults (não nulos) de campos ausentes
    ou ``null``. Devolve ``(dict_coagido, erros)`` com erros no formato
    ``"campo: motivo"``; nunca levanta por valor inválido (o valor original
    fica no dict). Campos fora do esquema são erro e passam inalterados.
    O dict sai na ordem do esquema, seguido dos campos desconhecidos.
    """
    saida: dict[str, Any] = {}
    erros: list[str] = []
    conhecidos = set()
    for campo in esquema_arquivo:
        conhecidos.add(campo.nome)
        valor = dados.get(campo.nome)
        if valor is None:
            if campo.obrigatorio:
                erros.append("%s: obrigatório" % campo.nome)
            elif campo.default is not None:
                saida[campo.nome] = copy.deepcopy(campo.default)
            elif campo.nome in dados:
                saida[campo.nome] = None
            continue
        convertido, motivo = _coagir_valor(valor, campo)
        if motivo:
            erros.append("%s: %s" % (campo.nome, motivo))
            saida[campo.nome] = valor
        else:
            saida[campo.nome] = convertido
    for chave, valor in dados.items():
        if chave not in conhecidos:
            erros.append("%s: campo desconhecido no esquema" % chave)
            saida[chave] = valor
    return saida, erros


def _coagir_valor(valor: Any, campo: Campo) -> tuple[Any, Optional[str]]:
    """Devolve (valor convertido, None) ou (valor original, motivo)."""
    coagir_tipo = COERCOES.get(campo.tipo)
    if coagir_tipo is None:
        return valor, "tipo %r desconhecido no esquema" % campo.tipo
    return coagir_tipo(valor, campo)


def _coagir_str(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, str):
        return valor, None
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor), None
    return valor, _esperado("str", valor)


def _coagir_int(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor, None
    if isinstance(valor, float) and valor.is_integer():
        return int(valor), None
    if isinstance(valor, str) and RE_INT.fullmatch(valor.strip()):
        return int(valor.strip()), None
    return valor, _esperado("int", valor)


def _coagir_float(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor), None
    if isinstance(valor, str) and RE_FLOAT.fullmatch(valor.strip()):
        return float(valor.strip()), None
    return valor, _esperado("float", valor)


def _coagir_bool(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, bool):
        return valor, None
    if isinstance(valor, str) and valor.strip().lower() in BOOLS:
        return BOOLS[valor.strip().lower()], None
    return valor, _esperado("bool", valor)


def _coagir_date(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, datetime):
        return valor.date(), None
    if isinstance(valor, date):
        return valor, None
    if not (isinstance(valor, str) and RE_DATA.fullmatch(valor.strip())):
        return valor, _esperado("date", valor)
    try:
        return date.fromisoformat(valor.strip()), None
    except ValueError:
        return valor, "data inválida: %r" % valor


def _coagir_datetime(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, datetime):
        return valor, None
    if isinstance(valor, date):
        valor = valor.isoformat()
    if not isinstance(valor, str):
        return valor, _esperado("datetime", valor)
    try:
        return clock.parse_iso(valor.strip()), None
    except GpErro as erro:
        return valor, "datetime inválido: %r (%s)" % (valor, erro.mensagem)


def _coagir_enum(valor: Any, campo: Campo) -> tuple[Any, Optional[str]]:
    if not campo.enum:
        return valor, "esquema sem valores de enum"
    if isinstance(valor, str) and valor in campo.enum:
        return valor, None
    return valor, "valor %s fora de {%s}" % (_curto(valor), ", ".join(campo.enum))


def _coagir_list(valor: Any, campo: Campo) -> tuple[Any, Optional[str]]:
    if not isinstance(valor, (list, tuple)):
        return valor, _esperado("list", valor)
    fora = [item for item in valor if not (isinstance(item, str) and item in campo.enum)] if campo.enum else []
    if fora:
        return valor, "itens %s fora de {%s}" % (", ".join(_curto(item) for item in fora), ", ".join(campo.enum or ()))
    # O esquema diz que list é sempre lista de strings (schema.TIPOS).
    nao_str = [item for item in valor if not isinstance(item, str)]
    if nao_str:
        return valor, "itens %s não são str" % ", ".join(_curto(item) for item in nao_str)
    return list(valor), None


def _coagir_dict(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    return (valor, None) if isinstance(valor, dict) else (valor, _esperado("dict", valor))


def _coagir_list_dict(valor: Any, _campo: Campo) -> tuple[Any, Optional[str]]:
    if isinstance(valor, list) and all(isinstance(item, dict) for item in valor):
        return list(valor), None
    return valor, _esperado("list_dict", valor)


# Uma coerção por tipo do esquema (schema.TIPOS).
COERCOES: dict[str, Callable[[Any, Campo], tuple[Any, Optional[str]]]] = {
    "str": _coagir_str,
    "int": _coagir_int,
    "float": _coagir_float,
    "bool": _coagir_bool,
    "date": _coagir_date,
    "datetime": _coagir_datetime,
    "enum": _coagir_enum,
    "list": _coagir_list,
    "dict": _coagir_dict,
    "list_dict": _coagir_list_dict,
}


def _esperado(tipo: str, valor: Any) -> str:
    return "esperado %s, veio %s %s" % (tipo, type(valor).__name__, _curto(valor))


def _curto(valor: Any) -> str:
    texto = repr(valor)
    return texto if len(texto) <= 40 else texto[:37] + "..."


def ler_contexto(dados: Path) -> dict[str, Any]:
    """``contexto.md`` coagido e validado (a leitura única que diário, mensal, status e painel usam)."""
    bruto, _ = ler_arquivo(Path(dados) / schema.CAMINHOS["contexto"])
    coagido, erros = coagir(bruto, schema.ESQUEMAS["contexto"])
    erros = erros or schema.validar_registro("contexto", coagido)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "contexto.md: " + "; ".join(erros[:5]))
    return coagido
