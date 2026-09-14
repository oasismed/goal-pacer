"""Balanço de horas do mês e render de ``planos/AAAA-MM.md`` (design "Balanço de horas"; CEO 2.5; D4.12; T7).

::

    cache mensal (eventos compactos de hoje ao domingo da última semana)
          |  sem os nossos blocos (alocação não é ocupação)
          v
    por dia >= hoje: horário útil - ocupações(+buffer)  -> janelas  -> oferta_h(semana)
          |
          +-- janelas - blocos já existentes naquele dia -> simulação: agenda.alocar
          |      com demanda_dia por meta (demanda da semana - horas já alocadas) / dias úteis
          v
    por semana e meta: demanda_h (demanda.demandas_do_mes), alocado_h (blocos existentes +
          simulados; feita pela duração real), feito_h (feita confirmada), cobertura = alocado/demanda
          v
    por meta no mês: cobertura = soma(min(alocado, demanda)) / soma(demanda)
          decisão: >= 100 manter · 70-99 reduzir · < 70 adiar · < 70 com prazo externo renegociar
          adiar_para = prazo + ceil(falta_h / h_semana_escolhido) semanas
          recalibrar_para: 2 últimas semanas completas com horas confirmadas > 0 e
                           |h - escolhido| / escolhido > 30% nas duas -> média arredondada a 0,5
    mês apertado: demanda das semanas não encerradas - feito > oferta

O plano é escrito inteiro pelo script; o modelo só preenche os blocos de
prosa (``<!-- prosa:resumo -->`` e ``<!-- prosa:m01 -->``...). ``hash_numeros``
no front-matter é o hash do corpo sem o texto desses blocos: o validador
recalcula e acusa números alterados fora do balanço (NumerosAlterados).
"""

from __future__ import annotations

import hashlib
import itertools
import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable, Iterator, NamedTuple, Optional

from goalpacer import agenda, clock, copy, demanda, frontmatter, render, schema
from goalpacer.agenda import Janela
from goalpacer.base import GpErro

ESTADOS_ALOCADOS = ("planejada", "sem_sinal", "movida", "reagendada", "feita")
LIMIAR_MANTER = 100.0
LIMIAR_REDUZIR = 70.0
DIVERGENCIA_RECALIBRAR = 0.30


# --- formatação -------------------------------------------------------------------


def horas(valor: float) -> str:
    """``12,5`` / ``4`` (separador decimal do idioma, sem zeros à direita)."""
    texto = ("%.1f" % round(float(valor), 1)).rstrip("0").rstrip(".")
    return texto.replace(".", copy.texto("calendario.decimal")) if texto else "0"


def pct(valor: float) -> str:
    return "%d%%" % round(float(valor))


def mes_e_ano(mes: str) -> str:
    """``outubro/2026`` (o nome do mês sozinho é ``copy.nome_mes``)."""
    return "%s/%s" % (copy.nome_mes(int(mes[5:7])), mes[:4])


def ddmm(dia: date) -> str:
    """Data curta no formato do idioma: ``28/09`` / ``Sep 28``."""
    return copy.data_curta(dia)


# --- datas do mês -------------------------------------------------------------------


def semanas(mes: str) -> list[str]:
    return demanda.semanas_do_mes(mes)


def ultimo_dia_do_mes(mes: str) -> date:
    ano, numero = int(mes[:4]), int(mes[5:7])
    proximo = date(ano + (numero == 12), 1 if numero == 12 else numero + 1, 1)
    return proximo - timedelta(days=1)


def janela_leitura(mes: str, agora: datetime, tz) -> tuple[datetime, datetime]:
    """De hoje (ou da segunda da primeira semana, se for depois) ao fim do domingo da última semana."""
    lista = semanas(mes)
    primeira = clock.dias_da_semana(lista[0])[0]
    ultima = clock.dias_da_semana(lista[-1])[-1]
    hoje = agora.astimezone(tz).date()
    inicio = datetime.combine(max(primeira, hoje), time.min, tzinfo=tz)
    fim = datetime.combine(ultima + timedelta(days=1), time.min, tzinfo=tz)
    return inicio, max(inicio, fim)


# --- cálculo --------------------------------------------------------------------------


def _sem_nossos(eventos: Iterable[dict[str, Any]], instalacao_id: str) -> list[dict[str, Any]]:
    sufixo = "/" + instalacao_id
    return [
        e
        for e in eventos
        if isinstance(e, dict) and not (isinstance(e.get("gp_key"), str) and e["gp_key"].endswith(sufixo))
    ]


def _subtrair(janelas: list[Janela], intervalos: list[Janela]) -> list[Janela]:
    minimo = timedelta(minutes=agenda.MINIMO_MIN)
    saida: list[Janela] = []
    for janela in janelas:
        pedacos = [janela]
        for corte in intervalos:
            pedacos = [resto for p in pedacos for resto in _sem_o_corte(p, corte)]
        saida.extend(p for p in pedacos if p.fim - p.inicio >= minimo)
    return sorted(saida)


def _sem_o_corte(janela: Janela, corte: Janela) -> list[Janela]:
    """O que sobra de ``janela`` fora de ``corte``: ela inteira, um pedaço de cada lado ou nada."""
    if corte.fim <= janela.inicio or corte.inicio >= janela.fim:
        return [janela]
    restos = []
    if corte.inicio > janela.inicio:
        restos.append(Janela(janela.inicio, corte.inicio))
    if corte.fim < janela.fim:
        restos.append(Janela(corte.fim, janela.fim))
    return restos


def _horas_bloco(bloco: dict[str, Any]) -> float:
    if bloco.get("estado") == "feita" and bloco.get("duracao_real_h"):
        return float(bloco["duracao_real_h"])
    return float(bloco.get("duracao_h", 0.0))


def _horas_confirmadas_semana(registro: dict[str, Any], meta_id: str, semana: str) -> list[float]:
    total = 0.0
    for item in registro.get("feitas", {}).get(meta_id, []):
        if item.get("origem") != "confirmado":
            continue
        task_id = str(item.get("task_id", ""))
        try:
            dia = date.fromisoformat(task_id[2:12])
        except ValueError:
            continue
        if clock.semana_iso(dia) == semana:
            total += float(item.get("duracao_real_h") or item.get("duracao_h") or 0.0)
    return [total]


def recalibracao(meta: dict[str, Any], registro: dict[str, Any], hoje: date) -> Optional[float]:
    """Novo h/semana sugerido, ou None (ver diagrama do módulo)."""
    escolhido = float(meta["custo_h_semana_escolhido"])
    segunda_atual = hoje - timedelta(days=hoje.weekday())
    semanas_passadas = [clock.semana_iso(segunda_atual - timedelta(days=7 * k)) for k in (2, 1)]
    inicio = clock.dias_da_semana(semanas_passadas[0])[0]
    criado = meta["criado_em"].date() if isinstance(meta.get("criado_em"), datetime) else hoje
    if criado > inicio or escolhido <= 0:
        return None
    valores = [_horas_confirmadas_semana(registro, meta["id"], s)[0] for s in semanas_passadas]
    if any(v <= 0 for v in valores):
        return None
    if all(abs(v - escolhido) / escolhido > DIVERGENCIA_RECALIBRAR for v in valores):
        media = sum(valores) / len(valores)
        return max(0.5, round(media * 2) / 2)
    return None


def decidir(cobertura: float, prazo_externo: bool) -> str:
    if cobertura >= LIMIAR_MANTER:
        return "manter"
    if cobertura >= LIMIAR_REDUZIR:
        return "reduzir"
    return "renegociar" if prazo_externo else "adiar"


class _Mes(NamedTuple):
    """O que a simulação e o resumo do mês leem, calculado uma vez."""

    mes: str
    contexto: dict[str, Any]
    tz: Any
    agora: datetime
    hoje: date
    externos: list[dict[str, Any]]
    ativas: dict[str, dict[str, Any]]
    registro: dict[str, Any]
    perfil: dict[str, Any]
    demandas_mes: dict[str, dict[str, float]]


def calcular(
    *,
    mes: str,
    contexto: dict[str, Any],
    metas: dict[str, dict[str, Any]],
    registro: dict[str, Any],
    perfil: dict[str, Any],
    blocos: dict[str, dict[str, Any]],
    eventos: list[dict[str, Any]],
    agora: datetime,
) -> dict[str, Any]:
    """Balanço do mês (dicts serializáveis). ``blocos``: ``perfil.blocos_com_registro``."""
    tz = clock.fuso(contexto["timezone"])
    agora = agora.astimezone(tz)
    m = _Mes(
        mes=mes,
        contexto=contexto,
        tz=tz,
        agora=agora,
        hoje=agora.date(),
        externos=_sem_nossos(eventos, contexto["instalacao_id"]),
        ativas={i: meta for i, meta in metas.items() if meta.get("estado", "ativa") == "ativa"},
        registro=registro,
        perfil=perfil,
        demandas_mes={i: demanda.demandas_do_mes(meta, registro, mes) for i, meta in metas.items()},
    )
    trabalho = {tid: dict(b) for tid, b in blocos.items() if isinstance(b.get("inicio"), datetime)}
    oferta_semana = _simular_mes(m, trabalho, {b.get("_dia") for b in blocos.values()})
    resultado_semanas = [
        _resultado_semana(m, semana, metas, trabalho, oferta_semana[semana]) for semana in semanas(mes)
    ]
    resultado_metas = {meta_id: _resultado_meta(m, meta_id, meta, resultado_semanas) for meta_id, meta in metas.items()}
    abertas = [s for s in resultado_semanas if date.fromisoformat(s["fim"]) >= m.hoje]
    demanda_aberta = sum(
        max(0.0, s["metas"][i]["demanda_h"] - s["metas"][i]["feito_h"]) for s in abertas for i in m.ativas
    )
    oferta_total = sum(s["oferta_h"] for s in resultado_semanas)
    return {
        "mes": mes,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "hoje": m.hoje.isoformat(),
        "ultimo_dia": ultimo_dia_do_mes(mes).isoformat(),
        "semanas": resultado_semanas,
        "metas": resultado_metas,
        "oferta_mes_h": round(oferta_total, 2),
        "demanda_mes_h": round(sum(x["demanda_mes_h"] for x in resultado_metas.values()), 2),
        "demanda_aberta_h": round(demanda_aberta, 2),
        "apertado": demanda_aberta > oferta_total + 1e-9,
    }


def _simular_mes(m: _Mes, trabalho: dict[str, dict[str, Any]], dias_com_md: set) -> dict[str, float]:
    """Oferta livre de cada semana, de hoje em diante; aloca em ``trabalho`` os blocos simulados dos dias à frente
    (hoje só quando o diário ainda não gerou o dia)."""
    oferta_semana = dict.fromkeys(semanas(m.mes), 0.0)
    ids_simulados = itertools.count(1)
    for semana in oferta_semana:
        for dia in clock.dias_da_semana(semana):
            janelas = _janelas_futuras(m, dia)
            if janelas is None:
                continue
            oferta_semana[semana] += sum(j.horas for j in janelas)
            if dia == m.hoje and m.hoje.isoformat() in dias_com_md:
                continue  # o dia de hoje já foi gerado pelo diário
            _simular_dia(m, dia, semana, janelas, trabalho, ids_simulados)
    return oferta_semana


def _janelas_futuras(m: _Mes, dia: date) -> Optional[list[Janela]]:
    """Janelas livres de um dia que ainda tem horário útil pela frente; ``None`` para dia passado ou sem horário."""
    horario = agenda.horario_util(m.contexto, dia, m.tz) if dia >= m.hoje else None
    if horario is None:
        return None
    if dia == m.hoje:
        if m.agora >= horario.fim:
            return None
        horario = Janela(max(horario.inicio, m.agora), horario.fim)
    ocupado = agenda.ocupacoes(
        m.externos,
        dia,
        m.tz,
        calendar_id_metas=m.contexto.get("calendar_id_metas") or "",
        instalacao_id=m.contexto["instalacao_id"],
    )
    return agenda.janelas_livres(horario, ocupado, int(m.contexto.get("buffer_min", 10)))


def _simular_dia(
    m: _Mes,
    dia: date,
    semana: str,
    janelas: list[Janela],
    trabalho: dict[str, dict[str, Any]],
    ids_simulados: Iterator[int],
) -> None:
    existentes = [
        Janela(b["inicio"].astimezone(m.tz), b["fim"].astimezone(m.tz))
        for b in trabalho.values()
        if b.get("estado") in ESTADOS_ALOCADOS and b["inicio"].astimezone(m.tz).date() == dia
    ]
    tem_util = agenda.tem_horario_util(m.contexto)
    demandas_dia: dict[str, float] = {}
    cobertura_dia: dict[str, float] = {}
    for meta_id, meta in m.ativas.items():
        fora = demanda.horas_na_semana(trabalho, meta_id, semana, excluir_data=dia)
        demandas_dia[meta_id] = demanda.demanda_dia(meta, m.registro, dia, fora, tem_util)
        pedida = m.demandas_mes[meta_id].get(semana, 0.0)
        cobertura_dia[meta_id] = fora / pedida if pedida > 0 else 0.0
    alocados = agenda.alocar(
        _subtrair(janelas, existentes),
        m.ativas,
        demandas_dia,
        dia=dia,
        tz=m.tz,
        cobertura=cobertura_dia,
        perfil=m.perfil,
        restricoes=m.contexto.get("restricoes_horario") or [],
    )
    for alocado in alocados:
        trabalho["sim-%04d" % next(ids_simulados)] = {
            "meta": alocado.meta,
            "inicio": alocado.inicio,
            "fim": alocado.fim,
            "duracao_h": alocado.duracao_h,
            "estado": "planejada",
            "origem": "inferido",
            "_simulado": True,
        }


def _resultado_semana(
    m: _Mes, semana: str, metas: dict[str, dict[str, Any]], trabalho: dict[str, dict[str, Any]], oferta: float
) -> dict[str, Any]:
    linhas: dict[str, dict[str, float]] = {}
    for meta_id in metas:
        pedida = m.demandas_mes[meta_id].get(semana, 0.0)
        alocado = demanda.horas_na_semana(trabalho, meta_id, semana)
        feito = sum(
            _horas_bloco(b)
            for b in trabalho.values()
            if b.get("meta") == meta_id
            and b.get("estado") == "feita"
            and b.get("origem") == "confirmado"
            and clock.semana_iso(b["inicio"].astimezone(m.tz).date()) == semana
        )
        cobertura = 100.0 if pedida <= 0 else min(100.0, 100.0 * alocado / pedida)
        linhas[meta_id] = {
            "demanda_h": round(pedida, 2),
            "alocado_h": round(alocado, 2),
            "feito_h": round(feito, 2),
            "cobertura_pct": round(cobertura, 1),
        }
    dias = clock.dias_da_semana(semana)
    return {
        "semana": semana,
        "inicio": dias[0].isoformat(),
        "fim": dias[-1].isoformat(),
        "oferta_h": round(oferta, 2),
        "metas": linhas,
    }


def _resultado_meta(
    m: _Mes, meta_id: str, meta: dict[str, Any], resultado_semanas: list[dict[str, Any]]
) -> dict[str, Any]:
    linhas = [s["metas"][meta_id] for s in resultado_semanas]
    pedida = sum(x["demanda_h"] for x in linhas)
    coberta = sum(min(x["alocado_h"], x["demanda_h"]) for x in linhas)
    cobertura = 100.0 if pedida <= 0 else 100.0 * coberta / pedida
    do_perfil = m.perfil.get("metas", {}).get(meta_id, {})
    item: dict[str, Any] = {
        "titulo": meta["titulo"],
        "estado": meta.get("estado", "ativa")
        if meta["prazo"] >= m.hoje or meta.get("estado") != "ativa"
        else "vencida",
        "prazo": meta["prazo"].isoformat(),
        "prazo_externo": bool(meta.get("prazo_externo")),
        "custo_h_semana": float(meta["custo_h_semana_escolhido"]),
        "semanas_pesquisa": int(meta["semanas_pesquisa"]),
        "custo_total_h": round(demanda.custo_total_h(meta), 2),
        "restante_h": round(demanda.restante_h(meta, m.registro), 2),
        "confianca": meta.get("confianca"),
        "demanda_mes_h": round(pedida, 2),
        "alocado_mes_h": round(sum(x["alocado_h"] for x in linhas), 2),
        "feito_mes_h": round(sum(x["feito_h"] for x in linhas), 2),
        "cobertura_pct": round(cobertura, 1),
        "decisao": None,
        "adiar_para": None,
        "recalibrar_para": None,
        "progresso_pct": float(do_perfil.get("progresso_pct", 0.0)),
        "progresso_presumido_pct": float(do_perfil.get("progresso_presumido_pct", 0.0)),
        "ritmo_esperado_pct": float(do_perfil.get("ritmo_esperado_pct", 0.0)),
    }
    if meta.get("estado", "ativa") == "ativa" and meta["prazo"] >= m.hoje:
        item["decisao"] = decidir(cobertura, bool(meta.get("prazo_externo")))
        if item["decisao"] != "manter" and pedida > 0:
            extras = math.ceil(max(0.0, pedida - coberta) / float(meta["custo_h_semana_escolhido"]))
            item["adiar_para"] = (meta["prazo"] + timedelta(days=7 * max(1, extras))).isoformat()
        item["recalibrar_para"] = recalibracao(meta, m.registro, m.hoje)
    return item


# --- prosa ------------------------------------------------------------------------------


def nomes_blocos_prosa(res: dict[str, Any]) -> list[str]:
    return ["resumo"] + [m.lower() for m in sorted(res["metas"])]


def extrair_prosa(texto: str) -> dict[str, str]:
    """``nome → texto`` dos blocos de prosa de um markdown (sem os marcadores, sem brancos nas pontas)."""
    return {m.group(2): m.group(3).strip() for m in schema.RE_BLOCO_PROSA.finditer(texto)}


def precisa_regerar(texto: Optional[str]) -> bool:
    return texto is None or not texto.strip() or schema.MARCADOR_ATUALIZAR in texto


def texto_decisao(meta_id: str, item: dict[str, Any], res: dict[str, Any]) -> str:
    fim = ddmm(date.fromisoformat(res["ultimo_dia"]))
    adiar = ddmm(date.fromisoformat(item["adiar_para"])) if item.get("adiar_para") else fim
    saida = (
        copy.texto("plano.saida_renegociar")
        if item["decisao"] == "renegociar"
        else copy.texto("plano.saida_adiar", data=adiar)
    )
    return copy.texto(
        "plano.decisao", fim=fim, pct=pct(item["cobertura_pct"]), meta=render.rotulo_meta(meta_id), saida=saida
    )


def prosa_template(res: dict[str, Any]) -> dict[str, str]:
    """Prosa determinística (offline e fallback quando a prosa viva viola o tom)."""
    blocos = {}
    if res["apertado"]:
        blocos["resumo"] = copy.texto(
            "plano.resumo_apertado",
            mes=mes_e_ano(res["mes"]),
            oferta=horas(res["oferta_mes_h"]),
            demanda=horas(res["demanda_aberta_h"]),
        )
    else:
        blocos["resumo"] = copy.texto(
            "plano.resumo_folgado",
            mes=mes_e_ano(res["mes"]),
            oferta=horas(res["oferta_mes_h"]),
            demanda=horas(res["demanda_aberta_h"]),
        )
    for meta_id, item in res["metas"].items():
        if item["decisao"] is None:
            texto = copy.texto("plano.meta_fora", meta=render.rotulo_meta(meta_id), estado=item["estado"])
        elif item["decisao"] == "manter":
            texto = copy.texto(
                "plano.meta_coberta", meta=render.rotulo_meta(meta_id), demanda=horas(item["demanda_mes_h"])
            )
        else:
            texto = texto_decisao(meta_id, item, res)
        blocos[meta_id.lower()] = texto
    return blocos


# --- render ---------------------------------------------------------------------------


def hash_numeros(corpo: str) -> str:
    """Hash do corpo com o texto dos blocos de prosa removido (marcadores ficam)."""
    sem_prosa = schema.RE_BLOCO_PROSA.sub(lambda m: m.group(1) + m.group(4), corpo.replace("\r\n", "\n").lstrip("\n"))
    return hashlib.sha256(sem_prosa.encode("utf-8")).hexdigest()[:16]


def _tabela_semana(semana: dict[str, Any], metas: dict[str, dict[str, Any]]) -> list[str]:
    linhas = ["| meta | demanda_h | alocado_h | feito_h | cobertura |", "|---|---|---|---|---|"]
    for meta_id in sorted(metas):
        valores = semana["metas"][meta_id]
        linhas.append(
            "| %s | %s | %s | %s | %s |"
            % (
                render.rotulo_meta(meta_id),
                horas(valores["demanda_h"]),
                horas(valores["alocado_h"]),
                horas(valores["feito_h"]),
                pct(valores["cobertura_pct"]),
            )
        )
    linhas.append("")
    linhas.append(
        copy.texto(
            "plano.oferta_semana",
            oferta=horas(semana["oferta_h"]),
            inicio=ddmm(date.fromisoformat(semana["inicio"])),
            fim=ddmm(date.fromisoformat(semana["fim"])),
        )
    )
    return linhas


def render_corpo(
    res: dict[str, Any], prosa: dict[str, str], evidencias: list[tuple[str, str, str, str]], notas: Iterable[str] = ()
) -> str:
    """Corpo de ``planos/AAAA-MM.md`` (sem front-matter). ``evidencias``: (data, fonte, meta, resumo)."""
    partes = [
        "# " + copy.texto("plano.titulo", mes=mes_e_ano(res["mes"])),
        "",
        "<!-- prosa:resumo -->",
        prosa.get("resumo", "").strip(),
        "<!-- /prosa:resumo -->",
        "",
        *_secao_balanco(res),
        "## Metas",
        "",
    ]
    for meta_id in sorted(res["metas"]):
        partes += _secao_meta(meta_id, res["metas"][meta_id], prosa)
    partes += ["## Semanas", ""]
    for semana in res["semanas"]:
        partes += ["### %s" % semana["semana"], "", *_tabela_semana(semana, res["metas"]), ""]
    partes += _secao_evidencias(evidencias, [n for n in notas if n])
    decisoes = [(m, i) for m, i in sorted(res["metas"].items()) if i["decisao"] in ("reduzir", "adiar", "renegociar")]
    if decisoes:
        partes += ["## Decisões", ""]
        partes += ["- %s: %s" % (meta_id, texto_decisao(meta_id, item, res)) for meta_id, item in decisoes]
        partes.append("")
    return "\n".join(partes).rstrip("\n") + "\n"


def _secao_balanco(res: dict[str, Any]) -> list[str]:
    partes = ["## Balanço", "", "| semana | oferta_h | demanda_h | alocado_h | cobertura |", "|---|---|---|---|---|"]
    for semana in res["semanas"]:
        valores = semana["metas"].values()
        pedida = sum(v["demanda_h"] for v in valores)
        alocada = sum(min(v["alocado_h"], v["demanda_h"]) for v in valores)
        cobertura = 100.0 if pedida <= 0 else 100.0 * alocada / pedida
        partes.append(
            "| %s | %s | %s | %s | %s |"
            % (
                semana["semana"],
                horas(semana["oferta_h"]),
                horas(pedida),
                horas(sum(v["alocado_h"] for v in valores)),
                pct(cobertura),
            )
        )
    coberto = sum(min(m["alocado_mes_h"], m["demanda_mes_h"]) for m in res["metas"].values())
    cobertura_mes = 100.0 if res["demanda_mes_h"] <= 0 else 100.0 * coberto / res["demanda_mes_h"]
    partes.append(
        "| mês | %s | %s | %s | %s |"
        % (
            horas(res["oferta_mes_h"]),
            horas(res["demanda_mes_h"]),
            horas(sum(m["alocado_mes_h"] for m in res["metas"].values())),
            pct(cobertura_mes),
        )
    )
    aperto = copy.texto(
        "plano.apertado" if res["apertado"] else "plano.folgado",
        oferta=horas(res["oferta_mes_h"]),
        demanda=horas(res["demanda_aberta_h"]),
    )
    return [*partes, "", aperto, ""]


def _secao_meta(meta_id: str, item: dict[str, Any], prosa: dict[str, str]) -> list[str]:
    progresso = "%s %s" % (render.rotulo_meta(meta_id), pct(item["progresso_pct"]))
    if item["progresso_presumido_pct"] >= 0.5:
        progresso += copy.texto("plano.progresso_presumido", pct=pct(item["progresso_presumido_pct"]))
    linhas = [
        copy.texto(
            "plano.linha_custo",
            h=horas(item["custo_h_semana"]),
            semanas=item["semanas_pesquisa"],
            total=horas(item["custo_total_h"]),
            confianca=item["confianca"] or "usuario",
        ),
        copy.texto(
            "plano.linha_prazo",
            restante=horas(item["restante_h"]),
            prazo=ddmm(date.fromisoformat(item["prazo"])),
            externo=copy.texto("plano.sim" if item["prazo_externo"] else "plano.nao"),
            estado=item["estado"],
        ),
        copy.texto(
            "plano.linha_mes",
            demanda=horas(item["demanda_mes_h"]),
            alocado=horas(item["alocado_mes_h"]),
            feito=horas(item["feito_mes_h"]),
            cobertura=pct(item["cobertura_pct"]),
        ),
        copy.texto("plano.linha_progresso", progresso=progresso, ritmo=pct(item["ritmo_esperado_pct"])),
    ]
    if item["decisao"]:
        linhas.append(copy.texto("plano.linha_decisao", decisao=item["decisao"]))
    if item.get("recalibrar_para"):
        linhas.append(
            copy.texto("plano.linha_recalibrar", meta=render.rotulo_meta(meta_id), h=horas(item["recalibrar_para"]))
        )
    marcador = meta_id.lower()
    return [
        "### %s %s" % (meta_id, item["titulo"]),
        "",
        *("- " + linha for linha in linhas),
        "",
        "<!-- prosa:%s -->" % marcador,
        prosa.get(marcador, "").strip(),
        "<!-- /prosa:%s -->" % marcador,
        "",
    ]


def _secao_evidencias(evidencias: list[tuple[str, str, str, str]], notas: list[str]) -> list[str]:
    if not evidencias and not notas:
        return []
    return [
        "## Evidências",
        "",
        *("- evidencia: %s %s %s: %s" % item for item in sorted(evidencias)),
        *("- nota: %s" % nota for nota in notas),
        "",
    ]


def render_plano(
    res: dict[str, Any],
    prosa: dict[str, str],
    evidencias: list[tuple[str, str, str, str]],
    *,
    hash_metas: str,
    fontes: list[str],
    run_id: str,
    notas: Iterable[str] = (),
) -> str:
    corpo = render_corpo(res, prosa, evidencias, notas)
    fm = {
        "mes": res["mes"],
        "hash_metas": hash_metas,
        "hash_numeros": hash_numeros(corpo),
        "fontes": [f for f in schema.FONTES if f in set(fontes)],
        "gerado_em": clock.parse_iso(res["gerado_em"]),
        "run_id": run_id,
    }
    erros = schema.validar_registro("plano", fm)
    if erros:
        raise ValueError("front-matter do plano inválido: " + "; ".join(erros))
    return "---\n" + frontmatter.dump(fm) + "---\n\n" + corpo


def render_semana(res: dict[str, Any], semana: dict[str, Any], run_id: str) -> str:
    fm = {
        "semana": semana["semana"],
        "mes": res["mes"],
        "gerado_em": clock.parse_iso(res["gerado_em"]),
        "run_id": run_id,
    }
    inicio = ddmm(date.fromisoformat(semana["inicio"]))
    fim = ddmm(date.fromisoformat(semana["fim"]))
    corpo = [
        "# " + copy.texto("plano.titulo_semana", semana=semana["semana"], inicio=inicio, fim=fim),
        "",
        copy.texto("plano.espelho", mes=res["mes"]),
        "",
        *_tabela_semana(semana, res["metas"]),
    ]
    return "---\n" + frontmatter.dump(fm) + "---\n\n" + "\n".join(corpo).rstrip("\n") + "\n"


def secao_semana_existe(texto_plano: str, semana: str) -> bool:
    return any(linha.rstrip("\r") == "### %s" % semana for linha in texto_plano.split("\n"))


RE_PLANO_LINHA_SEMANA = re.compile(
    r"^\| ([0-9]{4}-W[0-9]{2}) \| ([0-9.,]+) \| ([0-9.,]+) \| ([0-9.,]+) \| ([0-9]+)% \|$"
)
RE_PLANO_LINHA_MES = re.compile(r"^\| mês \| ([0-9.,]+) \| ([0-9.,]+) \| [0-9.,]+ \| ([0-9]+%) \|$")
RE_PLANO_META = re.compile(r"^### (M[0-9]{2}) ")
RE_PLANO_DECISAO = re.compile(r"^- (M[0-9]{2}): (.+)$")


def ler_plano(texto: str) -> dict[str, Any]:
    """Leitura de volta de ``planos/AAAA-MM.md`` (para ``status`` e ``checkin``).

    ``{"frontmatter", "mes": {oferta, demanda, cobertura} | None,
    "metas": {Mxx: {cobertura, decisao}}, "decisoes": [(Mxx, texto)],
    "semanas": [{semana, oferta, demanda, alocado, cobertura_pct}]}``;
    os números saem como texto já formatado (quem escreve é ``render_plano``).
    """
    try:
        bruto, corpo = frontmatter.separar(texto)
        fm = frontmatter.parse(bruto)
    except GpErro:  # plano ilegível: sem números, sem decisões
        return {"frontmatter": {}, "mes": None, "metas": {}, "decisoes": [], "semanas": []}
    plano: dict[str, Any] = {"frontmatter": fm, "mes": None, "metas": {}, "decisoes": [], "semanas": []}
    secao, meta = None, None
    for linha in corpo.split("\n"):
        if linha.startswith("## "):
            secao, meta = linha.strip()[3:], None
        elif secao == "Balanço":
            _ler_linha_do_balanco(plano, linha.strip())
        elif secao == "Metas":
            meta = _ler_linha_de_meta(plano, meta, linha)
        elif secao == "Decisões":
            m = RE_PLANO_DECISAO.match(linha.strip())
            if m:
                plano["decisoes"].append((m.group(1), m.group(2)))
    return plano


def _ler_linha_do_balanco(plano: dict[str, Any], limpa: str) -> None:
    m = RE_PLANO_LINHA_MES.match(limpa)
    if m:
        plano["mes"] = {"oferta": m.group(1), "demanda": m.group(2), "cobertura": m.group(3)}
    m = RE_PLANO_LINHA_SEMANA.match(limpa)
    if m:
        plano["semanas"].append(
            {
                "semana": m.group(1),
                "oferta": m.group(2),
                "demanda": m.group(3),
                "alocado": m.group(4),
                "cobertura_pct": int(m.group(5)),
            }
        )


def _ler_linha_de_meta(plano: dict[str, Any], meta: Optional[str], linha: str) -> Optional[str]:
    """Devolve a meta da subseção corrente; as linhas do copy são lidas em qualquer idioma (trocar o idioma não apaga
    o plano do mês)."""
    m = RE_PLANO_META.match(linha)
    if m:
        plano["metas"].setdefault(m.group(1), {})
        return m.group(1)
    limpa = linha.strip()
    if meta is None or not limpa.startswith("- "):
        return meta
    lido = copy.casar("plano.linha_mes", limpa[2:], {"cobertura": r"[0-9]+%"})
    if lido:
        plano["metas"][meta]["cobertura"] = lido["cobertura"]
    lido = copy.casar("plano.linha_decisao", limpa[2:], {"decisao": r"[a-z]+"})
    if lido:
        plano["metas"][meta]["decisao"] = lido["decisao"]
    return meta
