"""Renderização de ``dias/AAAA-MM-DD.md`` (design "dias/", seções de ``schema.SECOES["dia"]``).

O arquivo do dia é escrito inteiro pelo script, sempre no mesmo formato::

    ---  front-matter (esquema "dia")  ---
    # <Dia da semana>, dd/mm
    <linha-resumo>
    ## Hoje            um bloco por subseção "### <task_id> <título>" + linhas "- chave: valor"
    ## Desde <dia>     (condicional) o que o Calendar provou desde o último dia
    ## Progresso       uma linha por meta: "M1 41% (+3% feita?) · ritmo 45%"
    ## Avisos          (condicional)

O email das 7h é projeção direta deste arquivo (``--email-texto``, T30).
Ids de bloco são preservados na regeneração pelo par (meta, título) do
mesmo dia (``atribuir_ids``): só bloco novo ganha ``seq``. Toda hora leva
offset; o parser de volta é ``frontmatter.parse_blocos``.
"""

from __future__ import annotations

import html as html_mod
import re
import textwrap
from datetime import date, datetime
from typing import Any, Iterable, Optional

from goalpacer import copy, estilo, frontmatter, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

CAMPOS_BLOCO = (
    "meta",
    "semana",
    "inicio",
    "fim",
    "duracao_h",
    "porque",
    "efeito",
    "estado",
    "origem",
    "calendar_event_id",
    "calendar_id",
    "duracao_real_h",
)
TETO_TITULO = 60


def titulo_bloco(texto: str) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= TETO_TITULO else texto[: TETO_TITULO - 1].rstrip() + "…"


def rotulo_meta(meta_id: str) -> str:
    """``M01`` → ``M1`` (como o usuário lê)."""
    return "M%d" % int(meta_id[1:]) if schema.validar_id("meta", meta_id) else meta_id


def atribuir_ids(
    novos: Iterable[dict[str, Any]],
    anteriores: Iterable[dict[str, Any]],
    dia: date,
    reservados: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Dá ``id`` a blocos novos (``meta``, ``titulo``, ``inicio``, ``fim``...):
    reaproveita o id (e ``calendar_event_id``/``calendar_id``) do bloco
    anterior do mesmo dia com mesmo ``meta`` e ``titulo`` ainda não usado;
    o resto ganha o próximo ``seq`` livre da data, pulando ``reservados``
    (ids de blocos que ficam no dia sem serem reatribuídos: feitos, movidos,
    cancelados)."""
    livres = [b for b in anteriores if isinstance(b.get("id"), str)]
    usados: set[str] = set(reservados) | {b["id"] for b in livres}
    prefixo = "D-%s-" % dia.isoformat()
    proximo = 1
    saida: list[dict[str, Any]] = []
    for novo in sorted(novos, key=lambda b: (b["inicio"], b["meta"])):
        bloco = dict(novo)
        if not _herdar_do_anterior(bloco, livres):
            while "%s%02d" % (prefixo, proximo) in usados:
                proximo += 1
            if proximo > 99:
                raise GpErro(EXIT_VALIDACAO, "mais de 99 blocos em %s" % dia.isoformat())
            bloco["id"] = "%s%02d" % (prefixo, proximo)
            usados.add(bloco["id"])
        saida.append(bloco)
    return saida


def _herdar_do_anterior(bloco: dict[str, Any], livres: list[dict[str, Any]]) -> bool:
    """O primeiro anterior livre com a mesma meta e o mesmo título empresta o id e o evento; sai da lista."""
    casado = next(
        (a for a in livres if a.get("meta") == bloco.get("meta") and a.get("titulo") == bloco.get("titulo")), None
    )
    if casado is None:
        return False
    livres.remove(casado)
    bloco["id"] = casado["id"]
    for chave in ("calendar_event_id", "calendar_id"):
        if casado.get(chave) and not bloco.get(chave):
            bloco[chave] = casado[chave]
    return True


def render_bloco(bloco: dict[str, Any]) -> str:
    """Subseção ``### <id> <título>`` + linhas ``- chave: valor`` (só campos presentes)."""
    linhas = [("### %s %s" % (bloco["id"], titulo_bloco(bloco.get("titulo") or ""))).rstrip()]
    for chave in CAMPOS_BLOCO:
        valor = bloco.get(chave)
        if valor is None or valor == "":
            continue
        linhas.append("- %s: %s" % (chave, frontmatter.render_valor(valor, chave)))
    return "\n".join(linhas) + "\n"


def render_dia(
    dia: date,
    run_id: str,
    blocos: list[dict[str, Any]],
    *,
    resumo_linha: str,
    progresso: Optional[dict[str, Any]],
    desde: Optional[tuple[str, str, list[str]]] = None,
    avisos: Iterable[str] = (),
    decisao_pendente: Optional[str] = None,
    motivo: Optional[str] = None,
    contagens: Optional[dict[str, int]] = None,
) -> str:
    """Texto completo de ``dias/<dia>.md``; valida o front-matter antes de devolver.

    ``contagens`` (``confirmadas``, ``presumidas``, ``movidas``) resume o que
    aconteceu desde o último dia; sem ela, conta pelos blocos do próprio dia. ``progresso`` é o
    ``leitura.resumo_coach``: a manchete da semana e as linhas de objetivos e metas, em palavras."""
    fm = _frontmatter_do_dia(dia, run_id, blocos, contagens, decisao_pendente, motivo)
    ordenados = sorted(blocos, key=lambda b: (b["inicio"], b["id"]))
    partes = ["---\n", frontmatter.dump(fm), "---\n", "\n"]
    partes.append("# %s, %s\n\n" % (copy.dia_longo(dia), copy.data_curta(dia)))
    partes.append(resumo_linha.strip() + "\n\n")
    partes.append("## Hoje\n\n")
    if ordenados:
        partes.append("\n".join(render_bloco(b) for b in ordenados) + "\n")
    else:
        partes.append(copy.texto("diario.sem_blocos_md") + "\n\n")
    partes.extend(_secao_desde(desde))
    partes.extend(_secao_progresso(progresso))
    avisos = [a for a in avisos if a]
    if avisos:
        partes.append("## Avisos\n\n")
        partes.append("".join("- %s\n" % a for a in avisos) + "\n")
    return "".join(partes).rstrip("\n") + "\n"


def _frontmatter_do_dia(
    dia: date,
    run_id: str,
    blocos: list[dict[str, Any]],
    contagens: Optional[dict[str, int]],
    decisao_pendente: Optional[str],
    motivo: Optional[str],
) -> dict[str, Any]:
    """Front-matter do dia validado, e cada bloco validado no esquema ``task``."""
    if contagens is None:
        estados = [(b.get("estado"), b.get("origem")) for b in blocos]
        contagens = {
            "confirmadas": estados.count(("feita", "confirmado")),
            "presumidas": estados.count(("feita", "presumido")),
            "movidas": sum(1 for e, _ in estados if e in ("movida", "reagendada")),
        }
    fm: dict[str, Any] = {
        "data": dia,
        "run_id": run_id,
        "resumo_confirmadas": int(contagens.get("confirmadas", 0)),
        "resumo_presumidas": int(contagens.get("presumidas", 0)),
        "resumo_movidas": int(contagens.get("movidas", 0)),
    }
    if decisao_pendente:
        fm["decisao_pendente"] = decisao_pendente
    if motivo:
        fm["motivo"] = motivo
    erros = schema.validar_registro("dia", fm)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "dia inválido: " + "; ".join(erros))
    _validar_blocos(blocos)
    return fm


def _validar_blocos(blocos: list[dict[str, Any]]) -> None:
    campos_task = {c.nome for c in schema.ESQUEMAS["task"]}
    for bloco in blocos:
        erros = schema.validar_registro("task", {k: v for k, v in bloco.items() if k in campos_task})
        if erros:
            raise GpErro(EXIT_VALIDACAO, "bloco %s inválido: %s" % (bloco.get("id"), "; ".join(erros)))


def _secao_desde(desde: Optional[tuple[str, str, list[str]]]) -> list[str]:
    if not desde or not (desde[1] or desde[2]):
        return []
    partes = ["## Desde %s\n\n" % desde[0]]
    if desde[1]:
        partes.append(desde[1].strip() + "\n\n")
    if desde[2]:
        partes.append("".join("- %s\n" % linha for linha in desde[2]) + "\n")
    return partes


def _secao_progresso(progresso: Optional[dict[str, Any]]) -> list[str]:
    if not (progresso and progresso.get("linhas")):
        return ["## Progresso\n\n", "- %s\n\n" % copy.texto("email.comecando")]
    partes = ["## Progresso\n\n"]
    if progresso.get("manchete"):
        partes.append(progresso["manchete"].strip() + "\n\n")
    partes.append("".join("- %s\n" % linha for linha in progresso["linhas"]) + "\n")
    return partes


def hora_curta(instante: datetime) -> str:
    return instante.strftime("%Hh%M").replace("h00", "h")


# --- email das 7h (references/email.md) ---------------------------------------------------

TETO_EMAIL_BLOCOS = 6
TETO_EMAIL_DESDE = 6
TETO_EMAIL_METAS = 5
TETO_EMAIL_AVISOS = 3
URL_DIA = "https://calendar.google.com/calendar/r/day/%04d/%02d/%02d"


def _secoes(corpo: str) -> tuple[str, str, dict[str, list[str]]]:
    """``(titulo, resumo, {"## Seção": linhas})`` do corpo de ``dias/``."""
    titulo = ""
    resumo = ""
    secoes: dict[str, list[str]] = {}
    atual: Optional[str] = None
    for bruta in corpo.split("\n"):
        linha = bruta.rstrip("\r")
        if linha.startswith("# ") and not titulo:
            titulo = linha[2:].strip()
            continue
        if linha.startswith("## "):
            atual = linha.strip()
            secoes[atual] = []
            continue
        if atual is None:
            if linha.strip() and not resumo and titulo:
                resumo = linha.strip()
            continue
        if linha.strip():
            secoes[atual].append(linha.strip())
    return titulo, resumo, secoes


def ler_dia(texto: str) -> dict[str, Any]:
    """Modelo do dia a partir de ``dias/<data>.md`` (o email é projeção deste arquivo)."""
    fm_texto, corpo = frontmatter.separar(texto)
    fm = frontmatter.parse(fm_texto)
    titulo, resumo, secoes = _secoes(corpo)
    desde_titulo = next((s for s in secoes if schema.casa_secao("## Desde <dia>", s)), None)
    desde_linhas = secoes.get(desde_titulo, []) if desde_titulo else []
    progresso = secoes.get("## Progresso", [])
    return {
        "data": fm["data"] if isinstance(fm["data"], date) else date.fromisoformat(str(fm["data"])),
        "fm": fm,
        "titulo": titulo,
        "resumo": resumo,
        "blocos": sorted(_blocos_validos(corpo), key=lambda b: (b["inicio"], b["id"])),
        "desde_dia": desde_titulo[len("## Desde ") :] if desde_titulo else None,
        "desde_contagem": _cabeca(desde_linhas),
        "desde": _itens(desde_linhas),
        "progresso": _itens(progresso),
        "progresso_manchete": _cabeca(progresso),
        "avisos": _itens(secoes.get("## Avisos", [])),
    }


def _blocos_validos(corpo: str) -> list[dict[str, Any]]:
    blocos = []
    for bruto in frontmatter.parse_blocos(corpo):
        bruto.pop("_linha", None)
        coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["task"])
        if erros:
            raise GpErro(EXIT_VALIDACAO, "bloco %s: %s" % (bruto.get("id"), "; ".join(erros)))
        blocos.append(coagido)
    return blocos


def _itens(linhas: list[str]) -> list[str]:
    return [linha[2:] for linha in linhas if linha.startswith("- ")]


def _cabeca(linhas: list[str]) -> str:
    """A primeira linha da seção que não é item (contagem do Desde, manchete do Progresso)."""
    return next((linha for linha in linhas if not linha.startswith("- ")), "")


def _intervalo(bloco: dict[str, Any]) -> str:
    return "%s-%s" % (hora_curta(bloco["inicio"]), hora_curta(bloco["fim"]))


def modelo_email(
    dia: dict[str, Any], *, primeiro_dia: bool = False, decisao: Optional[tuple[str, str]] = None
) -> dict[str, Any]:
    """Modelo único do email (ordem 1-8 de references/email.md) com os tetos aplicados."""
    data: date = dia["data"]
    abertos = [b for b in dia["blocos"] if b.get("estado") in ("planejada", "sem_sinal")]
    comecando = {copy.texto("email.comecando", idioma) for idioma in copy.disponiveis()}
    progresso = [linha for linha in dia["progresso"] if linha not in comecando][: TETO_EMAIL_METAS + 3]
    return {
        "data": data,
        "assunto": _assunto_email(data, len(abertos), decisao),
        "titulo": dia["titulo"] or "%s, %s" % (copy.dia_longo(data), copy.data_curta(data)),
        "resumo": dia["resumo"],
        "decisao": {"meta": decisao[0], "texto": decisao[1]} if decisao else None,
        "hoje": [_bloco_do_email(b) for b in abertos[:TETO_EMAIL_BLOCOS]],
        "hoje_mais": max(0, len(abertos) - TETO_EMAIL_BLOCOS),
        "desde": _desde_do_email(dia, primeiro_dia),
        "progresso": progresso,
        "progresso_manchete": dia.get("progresso_manchete") or "",
        "comecando": primeiro_dia or not progresso,
        "avisos": dia["avisos"][:TETO_EMAIL_AVISOS],
        "primeiro_dia": primeiro_dia,
        "link": URL_DIA % (data.year, data.month, data.day),
    }


def _assunto_email(data: date, n: int, decisao: Optional[tuple[str, str]]) -> str:
    chave = "email.blocos_zero" if n == 0 else "email.blocos_um" if n == 1 else "email.blocos_n"
    dia_txt = "%s %s" % (copy.dia_curto(data).capitalize(), copy.data_curta(data))
    assunto = copy.texto("email.assunto", dia=dia_txt, blocos=copy.texto(chave, n=n))
    return assunto + copy.texto("email.assunto_decisao", meta=decisao[0]) if decisao else assunto


def _bloco_do_email(b: dict[str, Any]) -> dict[str, str]:
    return {
        "hora": "%s · %s" % (_intervalo(b), copy.texto("email.numero_bloco", n=b["id"][-2:])),
        "titulo": "%s (%s)" % (b.get("titulo") or "", rotulo_meta(b["meta"])),
        "porque": b.get("porque") or "",
        "efeito": b.get("efeito") or "",
    }


def _desde_do_email(dia: dict[str, Any], primeiro_dia: bool) -> Optional[dict[str, Any]]:
    if primeiro_dia or not (dia["desde"] or dia["desde_contagem"]):
        return None
    return {"dia": dia["desde_dia"] or "", "contagem": dia["desde_contagem"], "linhas": dia["desde"][:TETO_EMAIL_DESDE]}


def _embrulhar(texto: str, colunas: int) -> list[str]:
    linhas: list[str] = []
    for paragrafo in texto.split("\n"):
        if not paragrafo.strip():
            linhas.append("")
            continue
        linhas.extend(textwrap.wrap(paragrafo, width=colunas, break_long_words=True, break_on_hyphens=False) or [""])
    return linhas


def email_texto(modelo: dict[str, Any]) -> tuple[str, str]:
    """``(assunto, corpo)`` do email em texto puro, até ``colunas_email_texto`` colunas."""
    colunas = estilo.inteiro("colunas_email_texto")
    partes: list[str] = [modelo["titulo"], modelo["resumo"], ""]
    for secao in SECOES_TEXTO:
        partes += secao(modelo)
    corpo = "\n".join(linha for parte in partes for linha in _embrulhar(parte, colunas))
    while "\n\n\n" in corpo:
        corpo = corpo.replace("\n\n\n", "\n\n")
    return modelo["assunto"], corpo.strip("\n") + "\n"


def _texto_decisao(modelo: dict[str, Any]) -> list[str]:
    if not modelo["decisao"]:
        return []
    return [
        copy.texto("email.titulo_decisao", meta=modelo["decisao"]["meta"]).upper(),
        modelo["decisao"]["texto"],
        copy.texto("email.decisao_resposta"),
        "",
    ]


def _texto_hoje(modelo: dict[str, Any]) -> list[str]:
    partes = [copy.texto("email.titulo_hoje").upper()] + ([] if modelo["hoje"] else [modelo["resumo"]])
    for bloco in modelo["hoje"]:
        partes += [bloco["hora"], bloco["titulo"]] + [bloco[c] for c in ("porque", "efeito") if bloco[c]] + [""]
    if modelo["hoje_mais"]:
        partes += [copy.texto("email.mais_blocos", n=modelo["hoje_mais"]), ""]
    return partes


def _texto_desde(modelo: dict[str, Any]) -> list[str]:
    desde = modelo["desde"]
    if not desde:
        return []
    cabeca = [copy.texto("email.titulo_desde", dia=desde["dia"]).upper()]
    return cabeca + ([desde["contagem"]] if desde["contagem"] else []) + ["- " + l for l in desde["linhas"]] + [""]


def _texto_progresso(modelo: dict[str, Any]) -> list[str]:
    partes = [copy.texto("email.titulo_progresso").upper()]
    if modelo["comecando"] and not modelo["progresso"]:
        partes.append(copy.texto("email.comecando"))
    if modelo["progresso"] and modelo["progresso_manchete"]:
        partes += [modelo["progresso_manchete"], ""]
    return partes + ["- " + linha for linha in modelo["progresso"]] + [""]


def _texto_fim(modelo: dict[str, Any]) -> list[str]:
    """Como funciona (primeiro dia), avisos e o rodapé com o link, os comandos, a resposta e os gestos."""
    partes: list[str] = []
    if modelo["primeiro_dia"]:
        partes += [copy.texto("email.titulo_como_funciona").upper(), copy.texto("email.gestos"), ""]
    if modelo["avisos"]:
        partes += [copy.texto("email.titulo_avisos").upper()] + ["- " + a for a in modelo["avisos"]] + [""]
    partes += [copy.texto("email.link_texto") + ":", modelo["link"], copy.texto("email.rodape_comandos")]
    if modelo["hoje"]:
        partes.append(copy.texto("email.responder"))
    if not modelo["primeiro_dia"]:
        partes.append(copy.texto("email.gestos"))
    return partes


SECOES_TEXTO = (_texto_decisao, _texto_hoje, _texto_desde, _texto_progresso, _texto_fim)


def _esc(texto: Any) -> str:
    return html_mod.escape(str(texto), quote=True)


def email_html(modelo: dict[str, Any]) -> str:
    """HTML do mesmo modelo: uma coluna, tabelas, estilo inline dos tokens."""
    s = _estilos_html()
    partes = ['<div style="%s">' % s["pagina"]]
    partes.append('<h1 style="%s">%s</h1>' % (s["h1"], _esc(modelo["titulo"])))
    partes.append('<p style="margin:0;%s">%s</p>' % (s["sec"], _esc(modelo["resumo"])))
    for secao in SECOES_HTML:
        partes += secao(modelo, s)
    partes.append("</div></div>")
    return "\n".join(partes) + "\n"


def _estilos_html() -> dict[str, str]:
    t = estilo.token
    base = "font-family:%s;font-size:%s;line-height:%s;color:%s;" % (
        t("fonte"),
        t("tamanho_corpo"),
        t("altura_linha"),
        t("cor_texto"),
    )
    return {
        "pagina": "max-width:%s;margin:0 auto;background:%s;%s" % (t("largura_max"), t("cor_fundo"), base),
        "h1": "font-size:%s;margin:0 0 4px 0;" % t("tamanho_titulo"),
        "secao": "border-top:1px solid %s;padding-top:%s;margin-top:%s;"
        % (t("cor_linha"), t("espaco_secao"), t("espaco_secao")),
        "h2": "font-size:%s;font-weight:600;color:%s;margin:0 0 6px 0;" % (t("tamanho_corpo"), t("cor_texto")),
        "meta": "font-size:%s;color:%s;" % (t("tamanho_meta"), t("cor_terciaria")),
        "sec": "color:%s;" % t("cor_secundaria"),
        "link": "display:inline-block;min-height:%s;line-height:%s;color:%s;text-decoration:underline;"
        % (t("area_toque"), t("area_toque"), t("cor_texto")),
        "mono": "font-family:%s;" % t("fonte_mono"),
    }


def _abre_secao(s: dict[str, str], titulo: str) -> str:
    return '<div style="%s"><p style="%s">%s</p>' % (s["secao"], s["h2"], _esc(titulo))


def _html_decisao(modelo: dict[str, Any], s: dict[str, str]) -> list[str]:
    if not modelo["decisao"]:
        return []
    return [
        '<div style="%s"><p style="%s">%s</p><p style="margin:0 0 6px 0;">%s</p><p style="margin:0;%s">%s</p></div>'
        % (
            s["secao"],
            s["h2"],
            _esc(copy.texto("email.titulo_decisao", meta=modelo["decisao"]["meta"])),
            _esc(modelo["decisao"]["texto"]),
            s["sec"],
            _esc(copy.texto("email.decisao_resposta")),
        )
    ]


def _html_hoje(modelo: dict[str, Any], s: dict[str, str]) -> list[str]:
    partes = [_abre_secao(s, copy.texto("email.titulo_hoje"))]
    if not modelo["hoje"]:
        partes.append('<p style="margin:0;">%s</p>' % _esc(modelo["resumo"]))
    partes.extend(
        '<table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:0 0 10px 0;"><tr><td>'
        '<div style="%s">%s</div><div style="font-weight:600;">%s</div>%s%s</td></tr></table>'
        % (
            s["meta"],
            _esc(bloco["hora"]),
            _esc(bloco["titulo"]),
            '<div style="%s">%s</div>' % (s["sec"], _esc(bloco["porque"])) if bloco["porque"] else "",
            '<div style="%s">%s</div>' % (s["meta"], _esc(bloco["efeito"])) if bloco["efeito"] else "",
        )
        for bloco in modelo["hoje"]
    )
    if modelo["hoje_mais"]:
        partes.append(
            '<p style="margin:0;%s">%s</p>' % (s["sec"], _esc(copy.texto("email.mais_blocos", n=modelo["hoje_mais"])))
        )
    return [*partes, "</div>"]


def _html_desde(modelo: dict[str, Any], s: dict[str, str]) -> list[str]:
    desde = modelo["desde"]
    if not desde:
        return []
    partes = [_abre_secao(s, copy.texto("email.titulo_desde", dia=desde["dia"]))]
    if desde["contagem"]:
        partes.append('<p style="margin:0 0 6px 0;%s">%s</p>' % (s["sec"], _esc(desde["contagem"])))
    partes.extend('<p style="margin:0;">%s</p>' % _esc(l) for l in desde["linhas"])
    return [*partes, "</div>"]


def _html_progresso(modelo: dict[str, Any], s: dict[str, str]) -> list[str]:
    partes = [_abre_secao(s, copy.texto("email.titulo_progresso"))]
    if modelo["comecando"] and not modelo["progresso"]:
        partes.append('<p style="margin:0;">%s</p>' % _esc(copy.texto("email.comecando")))
    if modelo["progresso"] and modelo["progresso_manchete"]:
        partes.append('<p style="margin:0 0 8px 0;font-weight:bold;">%s</p>' % _esc(modelo["progresso_manchete"]))
    partes.extend('<p style="margin:0 0 4px 0;">%s</p>' % _esc(linha) for linha in modelo["progresso"])
    return [*partes, "</div>"]


def _html_fim(modelo: dict[str, Any], s: dict[str, str]) -> list[str]:
    """Como funciona (primeiro dia), avisos e o rodapé com o único link do email."""
    partes: list[str] = []
    if modelo["primeiro_dia"]:
        partes.append(
            '<div style="%s"><p style="%s">%s</p><p style="margin:0;">%s</p></div>'
            % (s["secao"], s["h2"], _esc(copy.texto("email.titulo_como_funciona")), _esc(copy.texto("email.gestos")))
        )
    if modelo["avisos"]:
        partes.append(
            '<div style="%s"><p style="%s">%s</p>%s</div>'
            % (
                s["secao"],
                s["h2"],
                _esc(copy.texto("email.titulo_avisos")),
                "".join('<p style="margin:0;">%s</p>' % _esc(a) for a in modelo["avisos"]),
            )
        )
    partes.append('<div style="%s">' % s["secao"])
    partes.append(
        '<a href="%s" style="%s">%s</a>' % (_esc(modelo["link"]), s["link"], _esc(copy.texto("email.link_texto")))
    )
    partes.append(
        '<p style="margin:6px 0 0 0;%s%s">%s</p>' % (s["mono"], s["meta"], _esc(copy.texto("email.rodape_comandos")))
    )
    if not modelo["primeiro_dia"]:
        partes.append('<p style="margin:6px 0 0 0;%s">%s</p>' % (s["meta"], _esc(copy.texto("email.gestos"))))
    return partes


SECOES_HTML = (_html_decisao, _html_hoje, _html_desde, _html_progresso, _html_fim)


PROIBIDOS_HTML = ("position:", "gradient", "display:grid", "grid-template", "<img", "<script", "<style", "float:")
RE_FONT_SIZE = re.compile(r"font-size:\s*([0-9]+)px")
RE_COR = re.compile(r"#[0-9a-fA-F]{3,6}\b")


def lint_html(documento: str) -> list[str]:
    """Problemas do HTML do email contra ``estilo.md`` (vazio = ok)."""
    baixo = documento.lower()
    problemas: list[str] = ["proibido: %s" % proibido for proibido in PROIBIDOS_HTML if proibido in baixo]
    minimo = estilo.inteiro("tamanho_meta")
    problemas.extend(
        "fonte abaixo de %dpx: %spx" % (minimo, m.group(1))
        for m in RE_FONT_SIZE.finditer(documento)
        if int(m.group(1)) < minimo
    )
    permitidas = {v.lower() for k, v in estilo.tokens().items() if k.startswith("cor_")}
    problemas.extend(
        "cor fora dos tokens: %s" % m.group(0)
        for m in RE_COR.finditer(documento)
        if m.group(0).lower() not in permitidas
    )
    if baixo.count("<a ") != 1:
        problemas.append("esperado exatamente 1 link, veio %d" % baixo.count("<a "))
    return problemas


def email_falha(data: date, classe_motivo: str, classe_acao: str) -> tuple[str, str, str]:
    """``(assunto, texto, html)`` do email mínimo de falha (design 2.2)."""
    dia_txt = "%s %s" % (copy.dia_curto(data).capitalize(), copy.data_curta(data))
    assunto = copy.texto("email.assunto_falha", dia=dia_txt)
    corpo = copy.texto("email.falha_corpo", motivo=classe_motivo, acao=classe_acao)
    texto = "\n".join(_embrulhar(corpo, estilo.inteiro("colunas_email_texto"))) + "\n"
    t = estilo.token
    html = (
        '<div style="max-width:%s;margin:0 auto;font-family:%s;font-size:%s;line-height:%s;color:%s;"><p style="margin:0;">%s</p><a href="%s" style="display:inline-block;min-height:%s;line-height:%s;color:%s;">%s</a></div>\n'
        % (
            t("largura_max"),
            t("fonte"),
            t("tamanho_corpo"),
            t("altura_linha"),
            t("cor_texto"),
            _esc(corpo),
            _esc(URL_DIA % (data.year, data.month, data.day)),
            t("area_toque"),
            t("area_toque"),
            t("cor_texto"),
            _esc(copy.texto("email.link_texto")),
        )
    )
    return assunto, texto, html
