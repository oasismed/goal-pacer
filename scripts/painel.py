#!/usr/bin/env python3
"""painel.py: modelos das telas do painel web, com a leitura qualitativa de coach (docs/designs/coach-qualitativo.md).

Só lê. Quem grava é o ``web.py``, pelas mesmas funções da skill. Telas::

    hoje       manchete de coach, blocos do dia, anéis de presença (hoje), ritmo (semana) e direção (mês),
               objetivos em uma linha cada, metas por estado, espaço na agenda, decisões
    objetivos  força ponderada de cada objetivo, o quanto cada meta move o objetivo, a alavanca
    metas      mapa impacto x tração (proteger, destravar, manter leve, repensar) e a lista com estado e jornada
    meta       jornada, trilha de 6 semanas, sinais em palavras, marcos, leitura de coach, ajustes e os números do balanço
    periodo    drill-down ano > semestre > trimestre > mês > semana (o dia é a tela hoje com ?data): leitura do período,
               tempo decorrido, metas do horizonte e as maiores que passam por ali, e os filhos com a leitura de cada um;
               no mês, também o espaço na agenda por semana, decisões e evidências
    checkin    blocos da última semana para confirmar, como está cada meta, decisões, nota
    status     execuções, silêncio do diário, pasta de dados, rede e aparelhos
    conexoes   provedor de IA, estado de cada conector (visto pelo doctor e pelos jobs) e fontes dos sinais do mês

Os números do backend (0 a 1) vão no JSON só para desenhar; o texto da tela sai
das chaves de leitura traduzidas por ``textos`` (grupo ``painel`` sem prefixo e
grupo ``coach`` como ``coach.<chave>``, de references/copy.pt-BR.md).
``python3 painel.py --json --tela metas`` imprime um modelo (depuração).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checkin
import status
from goalpacer import (
    balanco,
    base,
    cli,
    clock,
    coach,
    conexoes,
    copy,
    execucao,
    frontmatter,
    leitura as gpleitura,
    periodos,
    provedor,
    registro as reg,
    render,
    schema,
    whatsapp,
)
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro

ESTADOS_FORA_DO_DIA = ("cancelada", "apagada", "reagendada")
ESTADOS_CONFIRMAVEIS = ("planejada", "sem_sinal", "movida", "feita")
CORES_OBJETIVO = gpleitura.CORES_OBJETIVO
leitura = gpleitura.leitura
numero_pt = gpleitura.numero_pt
_metas_ordenadas = gpleitura.metas_ordenadas
TELAS = ("hoje", "objetivos", "metas", "meta", "periodo", "checkin", "status", "conexoes")
ATIVOS_NA_LEITURA = ("ativa", "concluida")
DIAS_CHECKIN = 7
TETO_EXECUCOES = 10


def horas_texto(horas: float) -> str:
    """``45 min``, ``2 h``, ``5 h 45`` (minutos arredondados)."""
    total = round(max(0.0, horas) * 60)
    h, m = divmod(total, 60)
    if total == 0:
        return "0 h"
    if h == 0:
        return "%d min" % m
    return "%d h" % h if m == 0 else "%d h %02d" % (h, m)


def textos() -> dict[str, str]:
    saida = {"locale": copy.texto("calendario.locale_numeros")}
    for chave, valor in copy.todas().items():
        if chave.startswith("painel."):
            saida[chave[len("painel.") :]] = valor
        elif chave.startswith("coach."):
            saida[chave] = valor
    return saida


def faixa_espaco(pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    return "folgado" if pct >= 100 else "justo" if pct >= 70 else "apertado"


def _titulo_dia(dia: date) -> str:
    return "%s, %s" % (copy.dia_longo(dia), balanco.ddmm(dia))


def _dia_curto(dia: date) -> str:
    return "%s %s" % (copy.dia_curto(dia), balanco.ddmm(dia))


def meta_resumo(l: dict[str, Any]) -> dict[str, Any]:
    return {
        k: l[k]
        for k in (
            "id",
            "rotulo",
            "titulo",
            "objetivo",
            "cor",
            "impacto",
            "peso",
            "estado",
            "estagio",
            "avanco",
            "tracao",
            "tendencia",
            "quadrante",
            "sentimento",
            "estado_arquivo",
            "prazo",
            "prazo_curto",
            "prazo_externo",
            "trilha",
            "horizonte",
            "compasso",
            "periodo_prazo",
        )
    }


def objetivo_resumo(o: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    alavanca = b["leituras"].get(o["alavanca"]) if o["alavanca"] else None
    return {
        "id": o["id"],
        "titulo": o["titulo"],
        "cor": o["cor"],
        "estado": o["estado"],
        "forca": o["forca"],
        "implicito": o["implicito"],
        "alavanca": {"id": alavanca["id"], "rotulo": alavanca["rotulo"], "titulo": alavanca["titulo"]}
        if alavanca
        else None,
        "metas": [
            {
                "id": m,
                "rotulo": b["leituras"][m]["rotulo"],
                "estado": b["leituras"][m]["estado"],
                "fatia": o["fatias"][m],
            }
            for m in o["contribuicoes"]
        ],
    }


def bloco_saida(x: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    tz = b["tz"]
    inicio, fim = x["inicio"].astimezone(tz), x["fim"].astimezone(tz)
    confirmada = x.get("estado") == "feita" and x.get("origem") == "confirmado"
    l = b["leituras"].get(x["meta"], {})
    return {
        "id": x["id"],
        "meta": x["meta"],
        "rotulo_meta": render.rotulo_meta(x["meta"]),
        "titulo_meta": l.get("titulo", ""),
        "titulo": x.get("titulo") or "",
        "dia": inicio.date().isoformat(),
        "dia_curto": _dia_curto(inicio.date()),
        "inicio": inicio.strftime("%H:%M"),
        "fim": fim.strftime("%H:%M"),
        "duracao": horas_texto(float(x.get("duracao_h") or 0.0)),
        "porque": x.get("porque") or "",
        "estado": x.get("estado"),
        "origem": x.get("origem"),
        "confirmada": confirmada,
        "presumida": x.get("estado") == "feita" and x.get("origem") == "presumido",
        "nao_feita": x.get("estado") == "nao_feita",
        "passou": fim <= b["agora"],
        "pode_confirmar": (not confirmada) and x.get("estado") in ESTADOS_CONFIRMAVEIS,
        "cor": l.get("cor"),
        "estado_meta": l.get("estado"),
    }


def _decisoes(b: dict[str, Any]) -> list[dict[str, Any]]:
    hash_plano = str((b["plano"] or {}).get("frontmatter", {}).get("hash_metas", ""))
    # no painel as saídas são botões: a frase "Saídas: ..." do plano sai do texto; a chave muda quando o
    # plano refeito traz outro texto, e o front esconde a decisão já respondida até lá
    saida = [
        dict(
            d,
            texto=d["texto"].split(" Saídas:")[0].strip(),
            rotulo=render.rotulo_meta(d["meta"]),
            titulo_card=copy.texto("painel.decisao_titulo", meta=render.rotulo_meta(d["meta"])),
            cor=b["leituras"].get(d["meta"], {}).get("cor"),
            chave="%s-%s-%s" % (hash_plano, d["meta"], hashlib.sha256(d["texto"].encode("utf-8")).hexdigest()[:8]),
        )
        for d in checkin.decisoes_pendentes(b["dados"], b["agora"])
    ]
    return saida


def _ocupacao(oferta: str, demanda: str) -> float:
    """Quanto do tempo livre da semana as metas pedem (1 = tudo), para a altura da barra."""
    livre = numero_pt(oferta)
    return 1.0 if livre <= 0 else round(min(1.0, numero_pt(demanda) / livre), 3)


def _plano_do_mes(b: dict[str, Any], mes: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if mes == b["mes"]:
        return b["plano"], b["texto_plano"]
    caminho = b["dados"] / "planos" / ("%s.md" % mes)
    if not caminho.exists():
        return None, None
    texto = caminho.read_text(encoding="utf-8")
    return balanco.ler_plano(texto), texto


def _espaco_mes(b: dict[str, Any], mes: Optional[str] = None) -> Optional[dict[str, Any]]:
    plano, _ = _plano_do_mes(b, mes or b["mes"])
    if not plano or not plano.get("mes"):
        return None
    return {
        "faixa": faixa_espaco(numero_pt(plano["mes"]["cobertura"])),
        "texto": copy.texto("painel.cobertura_texto", oferta=plano["mes"]["oferta"], demanda=plano["mes"]["demanda"]),
        "semanas": [
            {
                "semana": s["semana"],
                "curta": s["semana"][-3:],
                "faixa": faixa_espaco(s["cobertura_pct"]),
                "valor": _ocupacao(s["oferta"], s["demanda"]),
                "atual": s["semana"] == b["semana"],
                "oferta": s["oferta"],
                "demanda": s["demanda"],
            }
            for s in plano["semanas"]
        ],
    }


# --- telas ---------------------------------------------------------------------------------


def horizontes(b: dict[str, Any], blocos_hoje: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anéis concêntricos: hoje = presença ponderada pelo impacto; semana = ritmo; mês = direção dos objetivos."""
    leituras = b["leituras"]
    presenca, chave_presenca = coach.presenca_hoje(blocos_hoje, {m: l["peso"] for m, l in leituras.items()})
    # semana sem nenhum bloco vencido não tem ritmo para ler (sinal neutro não vira "em ritmo")
    ativas = [
        l for l in leituras.values() if l["estado"] not in ("pausada", "conquistada") and l["tracao_semana"] is not None
    ]
    ritmo = coach.media_ponderada((l["tracao_semana"], l["peso"]) for l in ativas)
    em_jogo = [
        o for o in b["objetivos"].values() if o["forca"] is not None and o["estado"] not in ("pausado", "conquistado")
    ]
    direcao = coach.media_ponderada((o["forca"], 1) for o in em_jogo)
    chave_direcao = coach.estado_objetivo(direcao, []) if direcao is not None else "pausado"
    return [
        {
            "nome": "hoje",
            "valor": None if presenca is None else round(presenca, 3),
            "leitura": "coach.presenca_" + chave_presenca,
        },
        {
            "nome": "semana",
            "valor": None if ritmo is None else round(ritmo, 3),
            "leitura": "coach.ritmo_" + coach.leitura_ritmo(ritmo),
        },
        {
            "nome": "mes",
            "valor": None if direcao is None else round(direcao, 3),
            "leitura": "coach.direcao_" + chave_direcao,
        },
    ]


def modelo(dados: Path, agora: datetime, dia: Optional[date] = None) -> dict[str, Any]:
    """Tela Hoje."""
    b = leitura(dados, agora)
    dia = dia or b["agora"].date()
    blocos_hoje = sorted(
        (
            x
            for x in b["blocos"].values()
            if x.get("_dia") == dia.isoformat() and x.get("estado") not in ESTADOS_FORA_DO_DIA
        ),
        key=lambda x: (x["inicio"], x["id"]),
    )
    caminho_dia = dados / "dias" / ("%s.md" % dia.isoformat())
    lido = render.ler_dia(caminho_dia.read_text(encoding="utf-8")) if caminho_dia.exists() else {}
    aneis = horizontes(b, blocos_hoje)
    alavanca = coach.alavanca(list(b["leituras"].values()))
    decisoes = _decisoes(b)
    repetidos = {copy.texto("email.decisao_pendente_aviso", meta=d["rotulo"]) for d in decisoes}
    return {
        "tela": "hoje",
        "agenda_google": conexoes.usa_agenda(b["contexto"]),
        "data": dia.isoformat(),
        "titulo_dia": _titulo_dia(dia),
        "semana_numero": int(b["semana"][-2:]),
        "e_hoje": dia == b["agora"].date(),
        "trilha": _trilha("dia", dia.isoformat())[:-1],
        "anterior": periodos.vizinho("dia", dia.isoformat(), -1),
        "proximo": periodos.vizinho("dia", dia.isoformat(), 1),
        "mes_nome": balanco.mes_e_ano(b["mes"]).split("/")[0].capitalize(),
        "manchete": _manchete(b, aneis, alavanca),
        "sub": _sub_manchete(blocos_hoje),
        "alavanca": meta_resumo(b["leituras"][alavanca]) if alavanca else None,
        "silencio": status.aviso_de_silencio(dados, b["agora"]),
        "blocos": [bloco_saida(x, b) for x in blocos_hoje],
        "horizontes": aneis,
        "desde": {"dia": lido["desde_dia"], "contagem": lido["desde_contagem"]} if lido.get("desde_dia") else None,
        "objetivos": [objetivo_resumo(o, b) for o in b["objetivos"].values()],
        "metas": [meta_resumo(l) for l in _metas_ordenadas(b) if l["estado_arquivo"] == "ativa"],
        "espaco": _espaco_mes(b),
        "decisoes": decisoes,
        "avisos": [a for a in lido.get("avisos", []) if a not in repetidos],
        "textos": textos(),
    }


def _manchete(b: dict[str, Any], aneis: list[dict[str, Any]], alavanca: Optional[str]) -> str:
    """Manchete do dia pelo ritmo da semana; ritmo ou atenção sem alavanca não tem o que apontar (sem sinal)."""
    ritmo = aneis[1]["leitura"][len("coach.ritmo_") :]
    chave = ritmo if ritmo in ("florescendo", "ritmo", "atencao") else "sem_sinal"
    if chave in ("ritmo", "atencao") and not alavanca:
        chave = "sem_sinal"
    lida = b["leituras"][alavanca] if alavanca else None
    return copy.texto("coach.manchete_" + chave, meta="%s (%s)" % (lida["titulo"], lida["rotulo"]) if lida else "")


def _sub_manchete(blocos_hoje: list[dict[str, Any]]) -> str:
    n = len(blocos_hoje)
    if n == 0:
        return copy.texto("painel.manchete_zero")
    sub = copy.texto("painel.manchete_um") if n == 1 else copy.texto("painel.manchete_n", n=n)
    confirmados = sum(1 for x in blocos_hoje if x.get("estado") == "feita" and x.get("origem") == "confirmado")
    if not confirmados:
        return sub
    if confirmados >= n:
        return sub + " " + copy.texto("painel.manchete_todos")
    if confirmados == 1:
        return sub + " " + copy.texto("painel.manchete_feitos_um")
    return sub + " " + copy.texto("painel.manchete_feitos_n", n=confirmados)


def modelo_objetivos(dados: Path, agora: datetime) -> dict[str, Any]:
    b = leitura(dados, agora)
    saida = []
    for o in b["objetivos"].values():
        membros = [
            dict(meta_resumo(b["leituras"][m]), contribuicao=c, fatia=o["fatias"][m])
            for m, c in o["contribuicoes"].items()
        ]
        membros.sort(key=lambda m: (-m["peso"], m["id"]))
        saida.append(
            dict(objetivo_resumo(o, b), por_que=o["por_que"], como_vou_saber=o["como_vou_saber"], metas=membros)
        )
    return {
        "tela": "objetivos",
        "objetivos": saida,
        "tem_implicitos": any(o["implicito"] for o in saida),
        "textos": textos(),
    }


def modelo_metas(dados: Path, agora: datetime) -> dict[str, Any]:
    b = leitura(dados, agora)
    return {
        "tela": "metas",
        "metas": [meta_resumo(l) for l in _metas_ordenadas(b)],
        "objetivos": {
            o["id"]: {"titulo": o["titulo"], "cor": o["cor"], "implicito": o["implicito"]}
            for o in b["objetivos"].values()
        },
        "textos": textos(),
    }


def modelo_meta(dados: Path, agora: datetime, meta_id: str) -> dict[str, Any]:
    if not isinstance(meta_id, str) or not schema.validar_id("meta", meta_id):
        raise GpErro(EXIT_VALIDACAO, "meta inválida: %r" % (meta_id,))
    b = leitura(dados, agora)
    if meta_id not in b["leituras"]:
        raise GpErro(EXIT_VALIDACAO, "meta %s não existe" % meta_id)
    l = b["leituras"][meta_id]
    objetivo = b["objetivos"].get(l["objetivo"]) if l["objetivo"] else None
    recentes, proximos = _blocos_da_meta(b, meta_id)
    semanas = [
        clock.semana_iso((b["agora"] - timedelta(days=7 * k)).date()) for k in range(coach.SEMANAS_TRILHA - 1, -1, -1)
    ]
    return {
        "tela": "meta",
        "meta": dict(l, trilha_semanas=["S%d" % int(s[-2:]) for s in semanas]),
        "objetivo": objetivo_resumo(objetivo, b) if objetivo else None,
        "leitura": _leitura_da_meta(l),
        "sinais": [
            {"nome": k, "nivel": v["nivel"], "valor": v["valor"], "frase": _frase_do_sinal(l, k)}
            for k, v in l["sinais"].items()
        ],
        "numeros": _numeros_da_meta(b, l),
        "evidencias": [
            {"data": balanco.ddmm(date.fromisoformat(d)), "fonte": f, "resumo": r}
            for d, f, m, r in sorted(b["evidencias"], reverse=True)
            if m == meta_id
        ],
        "recentes": [bloco_saida(x, b) for x in recentes],
        "proximos": [bloco_saida(x, b) for x in proximos],
        "objetivos_opcoes": [
            {"id": o["id"], "titulo": o["titulo"]} for o in b["objetivos"].values() if not o["implicito"]
        ],
        "textos": textos(),
    }


def _blocos_da_meta(b: dict[str, Any], meta_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(últimos 6 que já terminaram, próximos 4)``; cancelados não entram e fora do dia não conta como próximo."""
    dela = [x for x in b["blocos"].values() if x.get("meta") == meta_id and x.get("estado") != "cancelada"]
    recentes = sorted((x for x in dela if x["fim"] <= b["agora"]), key=lambda x: x["fim"], reverse=True)[:6]
    proximos = sorted(
        (x for x in dela if x["fim"] > b["agora"] and x.get("estado") not in ESTADOS_FORA_DO_DIA),
        key=lambda x: x["inicio"],
    )[:4]
    return recentes, proximos


def _numeros_da_meta(b: dict[str, Any], l: dict[str, Any]) -> dict[str, Any]:
    """Os números da meta ficam na seção de detalhes; só horas confirmadas contam como feito."""
    feito = sum(
        float(f.get("duracao_real_h") or f.get("duracao_h") or 0.0)
        for f in b["registro"].get("feitas", {}).get(l["id"], [])
        if f.get("origem") == "confirmado"
    )
    return {
        "custo": horas_texto(l["custo_h_semana"]),
        "semanas": l["semanas"],
        "total": horas_texto(l["custo_h_semana"] * l["semanas"]),
        "feito": horas_texto(feito),
        "cobertura": ("%d%%" % l["cobertura_pct"]) if l["cobertura_pct"] is not None else None,
        "decisao": l["decisao"],
    }


def _frase_do_sinal(l: dict[str, Any], sinal: Optional[str]) -> str:
    return copy.texto("coach.%s_%s" % (sinal, l["sinais"][sinal]["nivel"])) if sinal else ""


def _leitura_da_meta(l: dict[str, Any]) -> dict[str, str]:
    """O que funciona, o atrito, o próximo passo e a parada, em palavras (nada de porcentagem na tela)."""
    return {
        "funcionando": copy.texto("coach.funcionando", frase=_frase_do_sinal(l, l["forte"])) if l["forte"] else "",
        "atrito": copy.texto("coach.atrito", frase=_frase_do_sinal(l, l["fraco"]))
        if l["fraco"]
        else copy.texto("coach.sem_atrito"),
        "passo": copy.texto("coach.passo_" + l["estado"]),
        "parada": copy.texto("coach.dias_sem_feito", n=l["dias_sem_feito"])
        if l["dias_sem_feito"] is not None
        else copy.texto("coach.sem_feito"),
    }


# --- drill-down ------------------------------------------------------------------------------


def rotulo_periodo(nivel: str, pid: str, curto: bool = False) -> str:
    ano = pid[:4]
    if nivel == "ano":
        return ano
    if nivel in ("semestre", "trimestre"):
        return copy.texto("painel.periodo_%s%s" % (nivel, "_curto" if curto else ""), n=pid[-1], ano=ano)
    if nivel == "mes":
        nome = copy.nome_mes(int(pid[5:7])).capitalize()
        return nome[:3] if curto else copy.texto("painel.periodo_mes", mes=nome, ano=ano)
    if nivel == "semana":
        return copy.texto("painel.periodo_semana%s" % ("_curto" if curto else ""), n=int(pid[-2:]), ano=ano)
    dia = date.fromisoformat(pid)
    return _dia_curto(dia) if curto else _titulo_dia(dia)


def _intervalo_texto(nivel: str, pid: str) -> str:
    if nivel in ("trimestre", "semestre", "ano"):
        lista = periodos.meses(nivel, pid)
        return copy.texto(
            "painel.periodo_intervalo", de=copy.nome_mes(int(lista[0][5:7])), ate=copy.nome_mes(int(lista[-1][5:7]))
        )
    inicio, fim = periodos.intervalo(nivel, pid)
    return copy.texto("painel.periodo_intervalo", de=balanco.ddmm(inicio), ate=balanco.ddmm(fim))


def _trilha(nivel: str, pid: str) -> list[dict[str, str]]:
    return [{"nivel": n, "id": i, "rotulo": rotulo_periodo(n, i, curto=True)} for n, i in periodos.trilha(nivel, pid)]


def _ritmo_janela(b: dict[str, Any], meta_id: str, inicio: date, fim: date) -> Optional[float]:
    """Presença e fluidez dos blocos da meta dentro do período, até agora; ``None`` sem bloco vencido."""
    de = datetime.combine(inicio, time.min, tzinfo=b["tz"])
    ate = min(datetime.combine(fim + timedelta(days=1), time.min, tzinfo=b["tz"]), b["agora"])
    if ate <= de:
        return None
    blocos = [x for x in b["blocos"].values() if x.get("meta") == meta_id and x["inicio"] >= de]
    presenca, fluidez, n = coach.presenca_fluidez(blocos, ate, (ate - de).days + 1)
    return coach.ritmo(presenca, fluidez) if n else None


def leitura_periodo(b: dict[str, Any], nivel: str, pid: str) -> dict[str, Any]:
    """Leitura qualitativa de um período.

    mês, semana e dia (derivados)  ritmo dos blocos no período, ponderado pelo impacto -> florescendo, ritmo, atenção
    trimestre, semestre e ano       atual: 0,6 ritmo no período + 0,4 avanço no compasso do prazo -> firme, construção, foco
                                    encerrado: só o ritmo que houve; à frente: sem leitura, com os prazos que caem ali
    """
    hoje = b["agora"].date()
    inicio, fim = periodos.intervalo(nivel, pid)
    fase = periodos.fase(nivel, pid, hoje)
    em_jogo = [
        l
        for l in _metas_ordenadas(b)
        if periodos.sobrepoe(date.fromisoformat(l["criado"]), date.fromisoformat(l["prazo"]), inicio, fim)
    ]
    saida = {
        "fase": fase,
        "valor": None,
        "leitura": "fase_futuro",
        "prazos": [l["id"] for l in em_jogo if inicio <= date.fromisoformat(l["prazo"]) <= fim],
        "em_jogo": [l["id"] for l in em_jogo],
    }
    if fase == "futuro":
        return saida
    so_ritmo = nivel in periodos.DERIVADOS or fase == "passado"
    itens = [
        item
        for l in em_jogo
        if l["estado_arquivo"] in ATIVOS_NA_LEITURA
        for item in [_item_da_leitura(b, l, inicio, fim, hoje, so_ritmo=so_ritmo)]
        if item is not None
    ]
    valor = coach.media_ponderada(itens)
    if valor is None:
        saida["leitura"] = "coach.ritmo_sem_sinal"
    elif nivel in periodos.DERIVADOS:
        saida["leitura"] = "coach.ritmo_" + coach.leitura_ritmo(valor)
    else:
        saida["leitura"] = "coach.direcao_" + coach.estado_objetivo(valor, [])
    saida["valor"] = None if valor is None else round(valor, 3)
    return saida


def _item_da_leitura(
    b: dict[str, Any], l: dict[str, Any], inicio: date, fim: date, hoje: date, *, so_ritmo: bool
) -> Optional[tuple[float, int]]:
    """``(valor, peso)`` de uma meta: só o ritmo nos derivados e no passado; senão ritmo e compasso do prazo."""
    valor_ritmo = _ritmo_janela(b, l["id"], inicio, fim)
    if so_ritmo:
        return None if valor_ritmo is None else (valor_ritmo, l["peso"])
    relativo = coach.avanco_relativo(l["avanco"], date.fromisoformat(l["criado"]), date.fromisoformat(l["prazo"]), hoje)
    return (relativo if valor_ritmo is None else 0.6 * valor_ritmo + 0.4 * relativo, l["peso"])


def modelo_periodo(dados: Path, agora: datetime, nivel: str = "ano", pid: Optional[str] = None) -> dict[str, Any]:
    """Um nível do drill-down. Sem ``pid``, o período desse nível que contém hoje."""
    if nivel not in periodos.NIVEIS or nivel == "dia":
        raise GpErro(EXIT_VALIDACAO, "nível inválido: %r (use semana, mes, trimestre, semestre ou ano)" % (nivel,))
    b = leitura(dados, agora)
    hoje = b["agora"].date()
    pid = _periodo_pedido(nivel, pid, hoje)
    inicio, fim = periodos.intervalo(nivel, pid)
    propria = leitura_periodo(b, nivel, pid)
    do_nivel, acima, abaixo = _metas_por_horizonte(b, nivel, propria["em_jogo"])
    # a alavanca sai das metas do próprio horizonte; sem elas, das maiores e depois das menores que passam por ali
    derivado = nivel in periodos.DERIVADOS
    candidatas = [l for l in (acima if derivado else do_nivel or acima or abaixo) if l["estado_arquivo"] == "ativa"]
    alavanca = coach.alavanca(candidatas) if propria["fase"] == "atual" else None
    alavanca_resumo = meta_resumo(b["leituras"][alavanca]) if alavanca else None

    def com_compasso(l: dict[str, Any]) -> dict[str, Any]:
        return dict(meta_resumo(l), prazo_aqui=inicio <= date.fromisoformat(l["prazo"]) <= fim)

    saida: dict[str, Any] = {
        "tela": "periodo",
        "nivel": nivel,
        "id": pid,
        "titulo": rotulo_periodo(nivel, pid),
        "intervalo": _intervalo_texto(nivel, pid),
        "trilha": _trilha(nivel, pid)[:-1],
        "hoje": hoje.isoformat(),
        "niveis": [
            {"nivel": n, "id": periodos.do_dia(n, max(inicio, min(fim, hoje)))} for n in reversed(periodos.NIVEIS)
        ],
        "anterior": periodos.vizinho(nivel, pid, -1),
        "proximo": periodos.vizinho(nivel, pid, 1),
        "fase": propria["fase"],
        "tempo": round(periodos.decorrido(nivel, pid, hoje), 3),
        "leitura": {
            "valor": propria["valor"],
            "chave": propria["leitura"],
            "frase": _frase_do_periodo(b, nivel, propria, alavanca),
        },
        "alavanca": alavanca_resumo,
        "metas_nivel": [com_compasso(l) for l in do_nivel],
        "metas_acima": [com_compasso(l) for l in acima],
        "metas_abaixo": [com_compasso(l) for l in abaixo],
        "filhos": [
            _filho_do_periodo(b, filho_nivel, filho_id, hoje) for filho_nivel, filho_id in periodos.filhos(nivel, pid)
        ],
        "espaco": None,
        "resumo": "",
        "decisoes": [],
        "evidencias": [],
        "textos": textos(),
    }
    if nivel == "mes":
        saida.update(_detalhes_do_mes(b, pid, inicio, fim))
    return saida


def _periodo_pedido(nivel: str, pid: Optional[str], hoje: date) -> str:
    """O id pedido, ou o período do nível que contém hoje; id com forma errada é ``GpErro`` de validação."""
    pid = pid or periodos.do_dia(nivel, hoje)
    if not periodos.validar(nivel, pid):
        raise GpErro(EXIT_VALIDACAO, "%s inválido: %r" % (nivel, pid))
    return pid


def _metas_por_horizonte(
    b: dict[str, Any], nivel: str, em_jogo_ids: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """``(do nível, acima, abaixo)``: nos níveis derivados (semana, mês) toda meta em jogo conta como acima."""
    em_jogo = [b["leituras"][m] for m in em_jogo_ids]
    if nivel in periodos.DERIVADOS:
        return [], em_jogo, []
    ordem = periodos.NIVEIS.index(nivel)
    do_nivel = [l for l in em_jogo if l["horizonte"] == nivel]
    acima = [l for l in em_jogo if periodos.NIVEIS.index(l["horizonte"]) > ordem]
    abaixo = [l for l in em_jogo if periodos.NIVEIS.index(l["horizonte"]) < ordem]
    return do_nivel, acima, abaixo


def _frase_do_periodo(b: dict[str, Any], nivel: str, propria: dict[str, Any], alavanca: Optional[str]) -> str:
    if propria["fase"] == "atual":
        if not alavanca:
            return copy.texto("coach.periodo_sem_alavanca")
        lida = b["leituras"][alavanca]
        return copy.texto("coach.periodo_alavanca_" + nivel, meta="%s (%s)" % (lida["titulo"], lida["rotulo"]))
    if propria["fase"] == "passado":
        return copy.texto("coach.periodo_passado")
    n = len(propria["prazos"])
    if n == 0:
        return copy.texto("coach.periodo_futuro_livre")
    return copy.texto("coach.periodo_futuro_um") if n == 1 else copy.texto("coach.periodo_futuro_n", n=n)


def _filho_do_periodo(b: dict[str, Any], nivel: str, pid: str, hoje: date) -> dict[str, Any]:
    lf = leitura_periodo(b, nivel, pid)
    filho = {
        "nivel": nivel,
        "id": pid,
        "rotulo": rotulo_periodo(nivel, pid, curto=True),
        "fase": lf["fase"],
        "intervalo": _intervalo_texto(nivel, pid) if nivel != "dia" else "",
        "valor": lf["valor"],
        "leitura": lf["leitura"],
        "prazos": len(lf["prazos"]),
        "hoje": nivel == "dia" and pid == hoje.isoformat(),
    }
    if nivel == "dia":
        # todos os blocos do dia, também os movidos e apagados, porque eles entram na leitura (fluidez)
        do_dia = sorted(
            (x for x in b["blocos"].values() if x.get("_dia") == pid and x.get("estado") != "cancelada"),
            key=lambda x: x["inicio"],
        )
        filho["blocos"] = [
            {
                "rotulo_meta": render.rotulo_meta(x["meta"]),
                "cor": b["leituras"].get(x["meta"], {}).get("cor"),
                "feita": x.get("estado") == "feita",
            }
            for x in do_dia
        ]
    return filho


def _detalhes_do_mes(b: dict[str, Any], pid: str, inicio: date, fim: date) -> dict[str, Any]:
    """Espaço do mês, resumo e decisões do plano e as evidências que caem no mês."""
    _, texto_plano = _plano_do_mes(b, pid)
    return {
        "espaco": _espaco_mes(b, pid),
        "resumo": balanco.extrair_prosa(texto_plano).get("resumo", "") if texto_plano else "",
        "sem_plano": None if texto_plano else copy.texto("painel.sem_plano", mes=balanco.mes_e_ano(pid)),
        "decisoes": _decisoes(b) if pid == b["mes"] else [],
        "evidencias": [
            {
                "data": balanco.ddmm(date.fromisoformat(d)),
                "fonte": f,
                "meta": m,
                "rotulo": render.rotulo_meta(m),
                "resumo": r,
                "cor": b["leituras"].get(m, {}).get("cor"),
            }
            for d, f, m, r in sorted(b["evidencias"], reverse=True)
            if inicio <= date.fromisoformat(d) <= fim
        ],
    }


def modelo_checkin(dados: Path, agora: datetime) -> dict[str, Any]:
    b = leitura(dados, agora)
    limite = b["agora"] - timedelta(days=DIAS_CHECKIN)
    pendentes = [
        bloco_saida(x, b)
        for x in sorted(b["blocos"].values(), key=lambda x: x["inicio"])
        if limite <= x["fim"] <= b["agora"]
        and x.get("origem") != "confirmado"
        and x.get("estado") not in ESTADOS_FORA_DO_DIA
    ]
    return {
        "tela": "checkin",
        "pendentes": pendentes,
        "metas": [meta_resumo(l) for l in _metas_ordenadas(b) if l["estado_arquivo"] == "ativa"],
        "decisoes": _decisoes(b),
        "textos": textos(),
    }


def modelo_status(dados: Path, agora: datetime) -> dict[str, Any]:
    b = leitura(dados, agora)
    topo = sorted(status.execucoes_de_topo(b["registro"]), key=lambda g: str(g.get("ts")), reverse=True)
    execucoes = [e for e in (_execucao(g, b["tz"]) for g in topo[:TETO_EXECUCOES]) if e is not None]
    contexto = b["contexto"]
    return {
        "tela": "status",
        "silencio": status.aviso_de_silencio(dados, b["agora"]),
        "execucoes": execucoes,
        "proximo": status.quando_curto(status.proximo_job(b["agora"])),
        "fuso": contexto["timezone"],
        "fontes": list(contexto.get("fontes_ativas") or []),
        "horario": [
            {"dias": rotulo, "faixa": contexto.get(chave)}
            for rotulo, chave in (
                ("seg a sex", "horario_util_seg_sex"),
                ("sáb", "horario_util_sab"),
                ("dom", "horario_util_dom"),
            )
            if contexto.get(chave)
        ],
        "n_metas": len([l for l in b["leituras"].values() if l["estado_arquivo"] == "ativa"]),
        "n_objetivos": len([o for o in b["objetivos"].values() if not o["implicito"]]),
        "textos": textos(),
    }


def _execucao(g: dict[str, Any], tz: Any) -> Optional[dict[str, Any]]:
    try:
        instante = clock.parse_iso(str(g.get("ts"))).astimezone(tz)
    except GpErro:
        return None
    classe = g.get("classe")
    return {
        "quando": "%s %s" % (_dia_curto(instante.date()), instante.strftime("%H:%M")),
        "modo": g.get("modo"),
        "ok": g.get("exit_code") == 0,
        "classe": classe,
        "motivo": status.execucao.motivo(classe) if classe else "",
        "acao": status.execucao.acao(classe) if classe else "",
        "tokens": sum(int(v or 0) for v in (g.get("tokens") or {}).values()),
        "duracao": int(float(g.get("duracao_s") or 0)),
        "email": g.get("email"),
        "run_id": g.get("run_id"),
    }


# --- conexões ----------------------------------------------------------------------------

# (id da conexão, servidor MCP ou None, fonte de sinais ou None, usada todo dia)
CONEXOES = (
    ("calendar", "Google_Calendar", None, True),
    ("gmail", "Gmail", "gmail", True),
    ("notion", "Notion", "notion", False),
    ("drive", "Google_Drive", "drive", False),
    ("whatsapp", None, "whatsapp", False),
)
TETO_SINAIS_LIDOS = 12


def modelo_conexoes(dados: Path, _agora: datetime) -> dict[str, Any]:
    """As datas vêm do que o doctor e os jobs gravaram; o relógio da tela não entra."""
    contexto = frontmatter.ler_contexto(dados)
    tz = clock.fuso(contexto["timezone"])
    estado = conexoes.ler()
    ativo = provedor.ativo()
    ativas = set(contexto.get("fontes_ativas") or [])
    lidas = _ultima_leitura_por_fonte(dados)
    cartoes = []
    for id_conexao, servidor, fonte, diaria in CONEXOES:
        cartao = _conexao_servidor(servidor, estado, ativo, tz) if servidor else _conexao_whatsapp(dados, tz)
        if fonte:
            cartao["linhas"].append(_linha_leitura(lidas.get(fonte)))
        papel = "obrigatoria_fonte" if diaria and fonte else "obrigatoria" if diaria else "fonte"
        cartao.update(
            {
                "id": id_conexao,
                "nome": copy.texto("painel.conexao_" + id_conexao),
                "papel": copy.texto("painel.papel_" + papel),
                "estado_texto": copy.texto("painel.estado_" + cartao["estado"]),
                "fonte": fonte,
                "ativa": fonte in ativas if fonte else None,
            }
        )
        cartoes.append(cartao)
    return {
        "tela": "conexoes",
        "provedor": copy.texto("painel.provedor_texto", provedor=ativo.rotulo),
        "onde": copy.texto("painel.onde_" + ativo.nome),
        "verificado": _quando_verificado(estado.get("doctor_em"), tz),
        "problema": _problema_de_conexao(dados, tz),
        "conexoes": cartoes,
        "textos": textos(),
    }


def _data_de(instante: Any, tz: Any) -> Optional[str]:
    try:
        return balanco.ddmm(clock.parse_iso(str(instante)).astimezone(tz).date()) if instante else None
    except GpErro:
        return None


def _conexao_servidor(servidor: str, estado: dict[str, Any], ativo: provedor.Provedor, tz: Any) -> dict[str, Any]:
    if not ativo.conectores:
        return {"estado": "provedor", "linhas": [copy.texto("painel.linha_provedor", provedor=ativo.rotulo)]}
    info = estado["servidores"].get(servidor) or {}
    linhas = []
    for campo, chave in (("visto_em", "painel.linha_visto"), ("uso_ok_em", "painel.linha_uso")):
        data = _data_de(info.get(campo), tz)
        if data:
            linhas.append(copy.texto(chave, data=data))
    if servidor == "Google_Calendar" and estado.get("metas_encontrado") is not None:
        linhas.append(
            copy.texto("painel.linha_metas_ok" if estado["metas_encontrado"] else "painel.linha_metas_ausente")
        )
    escrita = _data_de(estado.get("escrita_testada_em"), tz)
    if escrita and servidor in conexoes.OBRIGATORIOS:
        linhas.append(copy.texto("painel.linha_escrita", data=escrita))
    situacao = info.get("estado") if info.get("estado") in conexoes.ESTADOS else "sem_verificacao"
    return {"estado": situacao, "linhas": linhas}


def _conexao_whatsapp(dados: Path, tz: Any) -> dict[str, Any]:
    arquivos = whatsapp.exports(dados / "inbox" / "whatsapp")
    if not arquivos:
        return {"estado": "sem_export", "linhas": [copy.texto("painel.linha_sem_export")]}
    ultimo = datetime.fromtimestamp(arquivos[0].stat().st_mtime, tz).date()
    return {
        "estado": "com_export",
        "linhas": [copy.texto("painel.linha_export", data=balanco.ddmm(ultimo), n=len(arquivos))],
    }


def _linha_leitura(dia: Optional[date]) -> str:
    return copy.texto("painel.linha_lida", data=balanco.ddmm(dia)) if dia else copy.texto("painel.linha_nao_lida")


def _ultima_leitura_por_fonte(dados: Path) -> dict[str, date]:
    """Dia do sinais/*.md mais recente em que cada fonte entrou (só o front-matter, nunca os resumos)."""
    lidas: dict[str, date] = {}
    arquivos = sorted((dados / "sinais").glob("*.md"), reverse=True) if (dados / "sinais").is_dir() else []
    for path in [p for p in arquivos if schema.validar_id("dia", p.stem)][:TETO_SINAIS_LIDOS]:
        try:
            bruto, _ = frontmatter.ler_arquivo(path)
        except GpErro:
            continue
        for fonte in bruto.get("fontes") or []:
            lidas.setdefault(str(fonte), date.fromisoformat(path.stem))
    return lidas


def _quando_verificado(instante: Any, tz: Any) -> str:
    data = _data_de(instante, tz)
    return copy.texto("painel.verificado_em", data=data) if data else copy.texto("painel.nunca_verificado")


def _problema_de_conexao(dados: Path, tz: Any) -> Optional[str]:
    """O último job pediu reconexão (e nenhum job terminou bem depois dele)."""
    jobs = [g for g in reg.carregar(dados).get("geracoes", {}).values() if str(g.get("modo", "")).startswith("job:")]
    if not jobs:
        return None
    ultimo = max(jobs, key=lambda g: str(g.get("ts")))
    classe = ultimo.get("classe")
    if ultimo.get("exit_code") == 0 or classe not in conexoes.CLASSES_DE_RECONEXAO:
        return None
    return copy.texto(
        "painel.problema_reconexao",
        data=_data_de(ultimo.get("ts"), tz) or "",
        classe=classe,
        acao=execucao.acao(classe),
    )


MODELOS = {
    "hoje": modelo,
    "objetivos": modelo_objetivos,
    "metas": modelo_metas,
    "checkin": modelo_checkin,
    "status": modelo_status,
    "conexoes": modelo_conexoes,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("modelos das telas do painel web (só leitura)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--tela", choices=TELAS, default="hoje")
    parser.add_argument("--meta", default="M01", help="com --tela meta")
    parser.add_argument("--data", type=date.fromisoformat, default=None, help="com --tela hoje")
    parser.add_argument("--nivel", choices=periodos.NIVEIS[1:], default="ano", help="com --tela periodo")
    parser.add_argument("--id", default=None, help="com --tela periodo: 2026, 2026-S2, 2026-T4, 2026-10 ou 2026-W40")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
        dados, agora = base.data_dir(), clock.agora()
        if args.tela == "meta":
            saida = modelo_meta(dados, agora, args.meta)
        elif args.tela == "hoje":
            saida = modelo(dados, agora, args.data)
        elif args.tela == "periodo":
            saida = modelo_periodo(dados, agora, args.nivel, args.id)
        else:
            saida = MODELOS[args.tela](dados, agora)
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    saida.pop("textos", None)
    sys.stdout.write(json.dumps(saida, ensure_ascii=False, indent=2) + "\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
