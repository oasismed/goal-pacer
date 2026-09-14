"""leitura.py: a leitura de coach da pasta de dados, lida uma vez e usada por painel, email e status.

``leitura(dados, agora)`` junta contexto, metas, objetivos, blocos, plano do mês, evidências e
perfil, e calcula por meta os sinais, a tração, o estado, a jornada, o compasso até o prazo e a
trilha, e por objetivo a força, o estado e a alavanca (regras em ``coach.py``). ``resumo_coach``
traduz isso em frases curtas para superfícies de texto (email das 7h e ``status``)::

    O que mais move esta semana: Publicar quatro artigos técnicos (M3).
    - Mudar de carreira para dados: avançando firme
    - M1 Terminar o curso de estatística: florescendo, com folga para o prazo

Só lê; nenhum número vira texto de superfície.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, NamedTuple, Optional

from goalpacer import (
    balanco,
    clock,
    coach,
    copy,
    frontmatter,
    leitor,
    metas as gpmetas,
    objetivos as gpobjetivos,
    perfil as prf,
    periodos,
    registro as reg,
    render,
)

# cores de identidade dos objetivos, todas na família do verde do painel (pedido do usuário): sálvia, folha, pinho, oliva, mar, musgo
CORES_OBJETIVO = ("#2F6B55", "#4E9A77", "#1E4A3B", "#6F8F55", "#2F7470", "#5E7A68")
ORDEM_ESTADOS = {"travada": 0, "atencao": 1, "ritmo": 2, "florescendo": 3, "conquistada": 4, "pausada": 5}
NIVEL_SENTIMENTO = {"energia": "alto", "firme": "medio", "pesada": "baixo"}
TETO_LINHAS_OBJETIVOS = 3
TETO_LINHAS_METAS = 5


contexto = frontmatter.ler_contexto


def numero_pt(texto: Any) -> float:
    try:
        return float(str(texto).replace(",", ".").rstrip("%"))
    except ValueError:
        return 0.0


def _secao(corpo: str, titulo: str) -> str:
    linhas, dentro = [], False
    for linha in corpo.split("\n"):
        if linha.startswith("## "):
            dentro = linha.strip() == titulo
            continue
        if dentro and linha.strip():
            linhas.append(linha.strip())
    return " ".join(linhas)


# --- leitura --------------------------------------------------------------------------


def leitura(dados: Path, agora: datetime) -> dict[str, Any]:
    """Tudo o que as telas usam, lido uma vez: contexto, blocos, plano, evidências e as leituras de coach por meta e objetivo."""
    ctx = contexto(dados)
    tz = clock.fuso(ctx["timezone"])
    agora = agora.astimezone(tz)
    registro = reg.carregar(dados)
    todas_as_metas = prf._ler_metas(dados)
    metas = {k: v for k, v in todas_as_metas.items() if v.get("estado", "ativa") != "arquivada"}
    objetivos = gpobjetivos.com_implicitos(gpobjetivos.ler(dados), metas)
    lidos = prf.ler_blocos(dados)  # uma leitura de dias/ por tela: o perfil usa os mesmos blocos crus
    blocos = prf.blocos_com_registro(dados, registro, lidos=lidos)
    semana = clock.semana_iso(agora.date())
    mes = clock.mes_da_semana(semana)
    caminho_plano = dados / "planos" / ("%s.md" % mes)
    texto_plano = caminho_plano.read_text(encoding="utf-8") if caminho_plano.exists() else None
    plano = balanco.ler_plano(texto_plano) if texto_plano else None
    evidencias, _ = leitor.ler_sinais(dados, agora)
    ordem_objetivos = sorted(objetivos, key=lambda o: (objetivos[o]["implicito"], o))
    base_meta = _BaseDaMeta(
        dados=dados,
        agora=agora,
        registro=registro,
        blocos=blocos,
        metas_do_plano=(plano or {}).get("metas", {}),
        perfil=prf.calcular(dados, agora, registro=registro, metas=todas_as_metas, blocos=lidos)
        if metas
        else {"metas": {}},
        evidencias=evidencias,
        objetivos=objetivos,
        cores={oid: CORES_OBJETIVO[i % len(CORES_OBJETIVO)] for i, oid in enumerate(ordem_objetivos)},
    )
    leituras = {meta_id: _leitura_da_meta(base_meta, meta_id, meta) for meta_id, meta in sorted(metas.items())}
    leituras_objetivo = {}
    for oid in ordem_objetivos:
        membros = [leituras[m] for m in sorted(leituras) if leituras[m]["objetivo"] == oid]
        if membros or not objetivos[oid]["implicito"]:
            leituras_objetivo[oid] = _leitura_do_objetivo(oid, objetivos[oid], membros, base_meta.cores[oid])
    return {
        "dados": dados,
        "contexto": ctx,
        "tz": tz,
        "agora": agora,
        "registro": registro,
        "metas": metas,
        "blocos": blocos,
        "semana": semana,
        "mes": mes,
        "plano": plano,
        "texto_plano": texto_plano,
        "evidencias": evidencias,
        "leituras": leituras,
        "objetivos": leituras_objetivo,
        "perfil": base_meta.perfil,
    }


class _BaseDaMeta(NamedTuple):
    """O que a leitura de cada meta consulta, lido uma vez por tela."""

    dados: Path
    agora: datetime
    registro: dict[str, Any]
    blocos: dict[str, dict[str, Any]]
    metas_do_plano: dict[str, dict[str, Any]]
    perfil: dict[str, Any]
    evidencias: list[tuple[str, str, str, str]]
    objetivos: dict[str, dict[str, Any]]
    cores: dict[str, str]


def _leitura_da_meta(b: _BaseDaMeta, meta_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    corpo = frontmatter.ler_arquivo(b.dados / "metas" / ("%s.md" % meta_id))[1]
    marcos = gpmetas.marcos(corpo)
    dos_blocos = [x for x in b.blocos.values() if x.get("meta") == meta_id]
    info_plano = b.metas_do_plano.get(meta_id, {})
    cobertura = int(numero_pt(info_plano["cobertura"])) if info_plano.get("cobertura") else None
    progresso = float(b.perfil["metas"].get(meta_id, {}).get("progresso_pct", 0.0))
    sentimentos = b.registro.get("sentimentos", {}).get(meta_id, [])
    sinais, vencidos, semana_7 = _sinais_da_meta(b, meta_id, meta, dos_blocos, sentimentos, cobertura)
    valor_tracao = coach.tracao(sinais)
    valor_avanco = coach.avanco(marcos, progresso)
    dias_sem = coach.dias_desde_feito(dos_blocos, b.agora)
    estado = coach.estado_meta(meta, sinais, valor_tracao, marcos, dias_sem, vencidos)
    sentimento = coach.ultimo_sentimento(sentimentos)
    forte, fraco = coach.forte_e_fraco(sinais)
    objetivo = gpobjetivos.objetivo_da_meta(meta, b.objetivos)
    criado = meta["criado_em"].astimezone(b.agora.tzinfo).date()
    return {
        "id": meta_id,
        "rotulo": render.rotulo_meta(meta_id),
        "titulo": meta["titulo"],
        "estado_arquivo": meta.get("estado", "ativa"),
        "objetivo": objetivo if objetivo in b.objetivos else None,
        "cor": b.cores.get(objetivo, "#6B7280"),
        "impacto": meta.get("impacto") or "importante",
        "peso": coach.peso(meta),
        "estado": estado,
        "estagio": coach.estagio(valor_avanco),
        "avanco": round(valor_avanco, 3),
        "tracao": round(valor_tracao, 3),
        "tracao_semana": None if semana_7 is None else round(coach.tracao(dict(sinais, **semana_7)), 3),
        "tendencia": coach.tendencia(dos_blocos, b.agora),
        "trilha": coach.trilha(dos_blocos, b.agora),
        "sinais": _sinais_com_nivel(sinais, sentimento),
        "forte": forte,
        "fraco": fraco,
        "marcos": marcos,
        "sentimento": sentimento,
        "dias_sem_feito": None if dias_sem is None else int(dias_sem),
        "quadrante": coach.quadrante(valor_tracao, coach.peso(meta)),
        "prazo": meta["prazo"].isoformat(),
        "prazo_curto": balanco.ddmm(meta["prazo"]) + "/" + str(meta["prazo"].year),
        "prazo_externo": bool(meta.get("prazo_externo")),
        "cobertura_pct": cobertura,
        "decisao": info_plano.get("decisao"),
        "por_que": _secao(corpo, "## Por que esta meta"),
        "custo_h_semana": float(meta["custo_h_semana_escolhido"]),
        "semanas": int(meta["semanas_pesquisa"]),
        "progresso_pct": progresso,
        "horizonte": meta["horizonte"],
        "criado": criado.isoformat(),
        "periodo_prazo": periodos.do_dia(meta["horizonte"], meta["prazo"]),
        "compasso": coach.compasso(valor_avanco, criado, meta["prazo"], b.agora.date())
        if estado not in ("pausada", "conquistada")
        else None,
    }


def _sinais_da_meta(
    b: _BaseDaMeta,
    meta_id: str,
    meta: dict[str, Any],
    dos_blocos: list[dict[str, Any]],
    sentimentos: list[dict[str, Any]],
    cobertura: Optional[int],
) -> tuple[dict[str, Optional[float]], Any, Optional[dict[str, Optional[float]]]]:
    """``(sinais, vencidos, presença e fluidez dos últimos 7 dias ou None)``."""
    presenca, fluidez, vencidos = coach.presenca_fluidez(dos_blocos, b.agora)
    presenca_7, fluidez_7, _ = coach.presenca_fluidez(dos_blocos, b.agora, coach.JANELA_SEMANA_DIAS)
    datas = [date.fromisoformat(d) for d, _, m, _ in b.evidencias if m == meta_id]
    sinais = {
        "presenca": presenca,
        "fluidez": fluidez,
        "energia": coach.energia(sentimentos, b.agora),
        "evidencia": coach.evidencia(datas, b.agora.date()),
        "espaco": coach.espaco(cobertura, bool(meta.get("prazo_externo"))),
    }
    semana_7 = None if presenca_7 is None else {"presenca": presenca_7, "fluidez": fluidez_7}
    return sinais, vencidos, semana_7


def _sinais_com_nivel(sinais: dict[str, Optional[float]], sentimento: Optional[str]) -> dict[str, dict[str, Any]]:
    niveis = {k: coach.nivel(v) for k, v in sinais.items()}
    if sinais["energia"] is not None and sentimento in NIVEL_SENTIMENTO:
        niveis["energia"] = NIVEL_SENTIMENTO[sentimento]  # a frase repete o que a pessoa marcou
    return {k: {"valor": None if v is None else round(v, 3), "nivel": niveis[k]} for k, v in sinais.items()}


def _leitura_do_objetivo(oid: str, objetivo: dict[str, Any], membros: list[dict[str, Any]], cor: str) -> dict[str, Any]:
    forca = coach.forca_objetivo(membros)
    ativas = [m for m in membros if m["estado"] != "pausada"]
    total = sum(m["peso"] for m in ativas) or 1
    estado = objetivo.get("estado", "ativo")
    return {
        "id": oid,
        "titulo": objetivo["titulo"],
        "por_que": objetivo.get("por_que", ""),
        "como_vou_saber": objetivo.get("como_vou_saber", ""),
        "implicito": objetivo["implicito"],
        "cor": cor,
        "forca": None if forca is None else round(forca, 3),
        "estado": coach.estado_objetivo(forca, membros) if estado == "ativo" else estado,
        "alavanca": coach.alavanca(membros),
        "contribuicoes": {
            m["id"]: (round(m["peso"] * (0.6 * m["tracao"] + 0.4 * m["avanco"]) / total, 3) if m in ativas else 0.0)
            for m in membros
        },
        "fatias": {m["id"]: (round(m["peso"] / total, 3) if m in ativas else 0.0) for m in membros},
    }


def _metas_ordenadas(b: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(b["leituras"].values(), key=lambda l: (ORDEM_ESTADOS.get(l["estado"], 9), -l["peso"], l["id"]))


def metas_ordenadas(b: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(b["leituras"].values(), key=lambda l: (ORDEM_ESTADOS.get(l["estado"], 9), -l["peso"], l["id"]))


def _minuscula(texto: str) -> str:
    return texto[:1].lower() + texto[1:] if texto else texto


def resumo_coach(b: dict[str, Any]) -> dict[str, Any]:
    """Manchete (a meta que mais move a semana) e as linhas de objetivos e metas ativas, em palavras."""
    ativas = [l for l in metas_ordenadas(b) if l["estado_arquivo"] == "ativa"]
    alavanca = coach.alavanca(ativas)
    manchete = (
        copy.texto(
            "coach.periodo_alavanca_semana",
            meta="%s (%s)" % (b["leituras"][alavanca]["titulo"], b["leituras"][alavanca]["rotulo"]),
        )
        if alavanca
        else None
    )
    linhas = [
        copy.texto(
            "email.linha_objetivo",
            objetivo=o["titulo"],
            leitura=_minuscula(copy.texto("coach.objetivo_" + o["estado"])),
        )
        for o in [o for o in b["objetivos"].values() if not o["implicito"]][:TETO_LINHAS_OBJETIVOS]
    ]
    for l in ativas[:TETO_LINHAS_METAS]:
        compasso = (", " + copy.texto("coach.compasso_" + l["compasso"])) if l.get("compasso") else ""
        linhas.append(
            copy.texto(
                "email.linha_meta",
                rotulo=l["rotulo"],
                titulo=l["titulo"],
                leitura=_minuscula(copy.texto("coach.estado_" + l["estado"])) + compasso,
            )
        )
    return {"manchete": manchete, "linhas": linhas}


def efeito_do_bloco(b: dict[str, Any], meta_id: str) -> str:
    """Linha de efeito de um bloco: o objetivo que ele move e o peso da meta nele (vazio sem objetivo cadastrado)."""
    l = b["leituras"].get(meta_id)
    objetivo = b["objetivos"].get(l["objetivo"]) if l and l.get("objetivo") else None
    if not objetivo or objetivo["implicito"]:
        return ""
    return copy.texto(
        "diario.efeito", objetivo=objetivo["titulo"], impacto=_minuscula(copy.texto("coach.impacto_" + l["impacto"]))
    )
