"""Strings de superfície (design 7.2): tudo o que o usuário lê vem de
``references/copy.<idioma>.md``, nunca solto em código ou prompt.

Formato do arquivo: seções ``## <grupo>`` e, dentro delas, ``### <chave>``
seguida do texto (até a próxima ``###``/``##``). A chave completa é
``grupo.chave``. O texto aceita ``{variavel}`` (``str.format``); chaves de
formatação ausentes viram ``KeyError`` (erro de programação). O carregador
lê ``references/`` do próprio pacote (``app_dir()`` não é usado: o repo em
dev e o clone instalado têm o mesmo layout relativo a este arquivo).

Idioma (um arquivo por idioma, nada mais a mexer)::

    GP_IDIOMA (--idioma, teste, demo)  >  copy.usar(...)  >  contexto.md "idioma" da pasta de dados  >  pt-BR
      -> só vale um idioma com references/copy.<idioma>.md; outro valor cai no padrão
      -> chave que falte num idioma cai no texto pt-BR (o teste de paridade impede isso no repo)

Nomes de dia e mês, data curta e as regras de tom por idioma também moram no copy
(grupos ``calendario`` e ``tom``); a estrutura dos arquivos de dados (títulos de seção
de ``dias/`` e ``planos/``, chaves de front-matter) é contrato e não muda com o idioma.
"""

from __future__ import annotations

import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from goalpacer.base import EXIT_VALIDACAO, GpErro

IDIOMA_PADRAO = "pt-BR"
ENV_IDIOMA = "GP_IDIOMA"
RE_IDIOMA = re.compile(r"^[a-z]{2}(-[A-Z]{2})?\Z")
RE_GRUPO = re.compile(r"^## ([a-z][a-z0-9_]*)\s*$")
RE_CHAVE = re.compile(r"^### ([a-z][a-z0-9_]*)\s*$")


def pasta_references() -> Path:
    """``references/`` do pacote instalado ou do repo (irmã de ``scripts/``)."""
    return Path(__file__).resolve().parent.parent.parent / "references"


def caminho(idioma: str = IDIOMA_PADRAO) -> Path:
    if RE_IDIOMA.match(idioma) is None:
        raise GpErro(EXIT_VALIDACAO, "idioma inválido: %r" % (idioma,))
    return pasta_references() / ("copy.%s.md" % idioma)


def parse(texto: str) -> dict[str, str]:
    """``grupo.chave → texto`` (texto sem as linhas em branco das pontas)."""
    strings: dict[str, str] = {}
    grupo = ""
    chave = ""
    linhas: list[str] = []

    def fechar() -> None:
        if chave:
            strings["%s.%s" % (grupo, chave)] = "\n".join(linhas).strip("\n")

    for linha in texto.split("\n"):
        m_grupo = RE_GRUPO.match(linha)
        m_chave = RE_CHAVE.match(linha)
        if m_grupo:
            fechar()
            grupo, chave, linhas = m_grupo.group(1), "", []
        elif m_chave:
            fechar()
            chave, linhas = m_chave.group(1), []
        elif chave:
            linhas.append(linha.rstrip("\r"))
    fechar()
    return strings


@lru_cache(maxsize=4)
def carregar(idioma: str = IDIOMA_PADRAO) -> dict[str, str]:
    path = caminho(idioma)
    if not path.exists():
        raise GpErro(EXIT_VALIDACAO, "arquivo de strings não encontrado: %s" % path)
    return parse(path.read_text(encoding="utf-8"))


def disponiveis() -> tuple[str, ...]:
    """Idiomas com arquivo de strings, o padrão primeiro (lista refeita só quando a pasta references/ muda)."""
    pasta = pasta_references()
    try:
        marca = pasta.stat().st_mtime_ns
    except OSError:
        marca = 0
    return _disponiveis(str(pasta), marca)


@lru_cache(maxsize=4)
def _disponiveis(pasta: str, _marca: int) -> tuple[str, ...]:
    achados = sorted(p.name[len("copy.") : -len(".md")] for p in Path(pasta).glob("copy.*.md"))
    validos = [i for i in achados if RE_IDIOMA.match(i)]
    return tuple(sorted(validos, key=lambda i: (i != IDIOMA_PADRAO, i)))


_ESCOLHIDO: Optional[str] = None
_PASTA: Optional[Path] = None
_DO_CONTEXTO: dict[tuple[str, int], Optional[str]] = {}


def usar(idioma: Optional[str]) -> None:
    """Fixa o idioma do processo (``None`` volta a seguir o ambiente e o contexto)."""
    global _ESCOLHIDO
    _ESCOLHIDO = idioma


def seguir_pasta(dados: Optional[Path]) -> None:
    """Lê o idioma do ``contexto.md`` desta pasta em vez da de ``GP_DATA_DIR`` (painel, demo)."""
    global _PASTA
    _PASTA = Path(dados) if dados else None


def _valido(idioma: Any) -> Optional[str]:
    if isinstance(idioma, str) and RE_IDIOMA.match(idioma) and caminho(idioma).exists():
        return idioma
    return None


def _idioma_do_contexto() -> Optional[str]:
    from goalpacer import base, schema

    try:
        path = (_PASTA or base.data_dir()) / schema.CAMINHOS["contexto"]
        estado = path.stat()
    except (OSError, GpErro):
        return None
    chave = (str(path), estado.st_mtime_ns)
    if chave not in _DO_CONTEXTO:
        from goalpacer import frontmatter

        try:
            valor = frontmatter.ler_arquivo(path)[0].get("idioma")
        except (GpErro, OSError, ValueError):
            valor = None
        _DO_CONTEXTO.clear()
        _DO_CONTEXTO[chave] = valor if isinstance(valor, str) else None
    return _DO_CONTEXTO[chave]


def atual() -> str:
    """Idioma das superfícies deste processo (ver a ordem no topo do módulo)."""
    for candidato in (os.environ.get(ENV_IDIOMA), _ESCOLHIDO, _idioma_do_contexto()):
        valido = _valido(candidato)
        if valido:
            return valido
    return IDIOMA_PADRAO


def todas(idioma: Optional[str] = None) -> dict[str, str]:
    """Todas as strings do idioma, com o pt-BR preenchendo o que faltar."""
    idioma = idioma or atual()
    if idioma == IDIOMA_PADRAO:
        return dict(carregar(IDIOMA_PADRAO))
    return dict(carregar(IDIOMA_PADRAO), **carregar(idioma))


def texto(chave: str, idioma: Optional[str] = None, **valores: Any) -> str:
    """Texto de ``grupo.chave`` no idioma atual com ``{variaveis}`` substituídas.

    Chave ausente no idioma usa o pt-BR; ausente também no pt-BR é
    ``GpErro(EXIT_VALIDACAO)`` (erro de programação)."""
    idioma = idioma or atual()
    strings = carregar(idioma)
    if chave not in strings:
        strings = carregar(IDIOMA_PADRAO)
        if chave not in strings:
            raise GpErro(EXIT_VALIDACAO, "string %r não existe em copy.%s.md" % (chave, IDIOMA_PADRAO))
    return strings[chave].format(**valores) if valores else strings[chave]


def lista(chave: str, idioma: Optional[str] = None) -> list[str]:
    """Texto de ``grupo.chave`` separado por vírgula (nomes de dia, meses, palavras)."""
    return [parte.strip() for parte in texto(chave, idioma).split(",") if parte.strip()]


def casar(chave: str, texto_lido: str, grupos: dict[str, str]) -> Optional[dict[str, str]]:
    """Lê de volta uma linha escrita a partir de ``grupo.chave`` em qualquer idioma disponível.

    Cada ``{variavel}`` de ``grupos`` vira um grupo com a regex dada; as outras casam qualquer
    texto. Devolve os grupos da primeira tradução que casar a linha inteira, ou ``None``.
    Assim um arquivo de dados gerado num idioma continua legível depois de trocar o idioma."""
    for idioma in disponiveis():
        padrao = _padrao_de(chave, idioma, tuple(sorted(grupos.items())))
        achado = padrao.match(texto_lido.strip()) if padrao is not None else None
        if achado:
            return achado.groupdict()
    return None


@lru_cache(maxsize=64)
def _padrao_de(chave: str, idioma: str, grupos: tuple) -> Optional[re.Pattern[str]]:
    molde = carregar(idioma).get(chave)
    if not molde:
        return None
    nomes = dict(grupos)
    partes = re.split(r"(\{[a-z_]+\})", molde)
    padrao = "".join(
        ("(?P<%s>%s)" % (p[1:-1], nomes[p[1:-1]]) if p[1:-1] in nomes else ".*?")
        if p.startswith("{") and p.endswith("}")
        else re.escape(p)
        for p in partes
    )
    return re.compile(r"^%s$" % padrao)


# --- calendário ------------------------------------------------------------------------------


def dia_longo(dia: date, idioma: Optional[str] = None) -> str:
    """``Segunda`` / ``Monday``."""
    return lista("calendario.dias_longos", idioma)[dia.weekday()]


def dia_curto(dia: date, idioma: Optional[str] = None) -> str:
    """``seg`` / ``Mon``."""
    return lista("calendario.dias_curtos", idioma)[dia.weekday()]


def nome_mes(numero: int, idioma: Optional[str] = None) -> str:
    """``outubro`` / ``October`` (1..12)."""
    return lista("calendario.meses", idioma)[numero - 1]


def data_curta(dia: date, idioma: Optional[str] = None) -> str:
    """``28/09`` / ``Sep 28``."""
    return texto(
        "calendario.data_curta",
        idioma,
        dd="%02d" % dia.day,
        mm="%02d" % dia.month,
        d=dia.day,
        mes_curto=lista("calendario.meses_curtos", idioma)[dia.month - 1],
    )
