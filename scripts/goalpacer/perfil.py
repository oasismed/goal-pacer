"""perfil.json: estatísticas determinísticas de registro.json (eng 1.3, T17; design "Progresso" e "Perfil").

Só ``origem: confirmado`` e sinais explícitos entram nos pesos::

    feita confirmado                 -> conta como 1 na célula da janela e nas horas
    apagada / nao_feita / movida /
    reagendada (inferido|confirmado) -> conta como 0 na célula da janela original
    presumido                        -> só no progresso EXIBIDO (progresso_presumido_pct), nunca nos pesos
    sem_sinal / planejada            -> fora

Por meta (``perfil_meta``)::

    custo_total_h        = custo_h_semana_escolhido * semanas_pesquisa
    horas_confirmadas    = soma(duracao_real_h ou duracao_h) das feitas confirmadas
    progresso_esforco    = horas_confirmadas / custo_total_h
    progresso_pct        = max(progresso_esforco, ultimo declarado_pct)         (0..100+)
    progresso_presumido  = horas presumidas dos ultimos 14 dias / custo_total_h
    horas_presumidas_nao_contadas = presumidas com mais de 14 dias
    ritmo_esperado_pct   = min(100, semanas desde criado_em / semanas ate o prazo)
    delta                = progresso_pct - ritmo_esperado_pct
    fator_duracao        = mediana(duracao_real_h / duracao_h) com >= 5 confirmadas, senão 1.0
    h_semana_real        = media das horas confirmadas nas 4 ultimas semanas ISO

Janelas: célula ``<dia>-<faixa>`` (``seg-manha``: manha < 12h, tarde
12h-18h, noite >= 18h, no fuso do bloco) com ``taxa_conclusao`` e ``n``; o
consumidor (``agenda``) só usa células com ``n >= MINIMO_OBSERVACOES``.
"""

from __future__ import annotations

import hashlib
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from goalpacer import base, clock, frontmatter, io as gpio, registro as reg, schema
from goalpacer.base import EXIT_VALIDACAO, GpErro

NOME_ARQUIVO = "perfil.json"
MINIMO_OBSERVACOES = 5
DIAS_PRESUNCAO = 14
SEMANAS_MEDIA_MOVEL = 4
FAIXAS = ((12, "manha"), (18, "tarde"), (24, "noite"))
ESTADOS_NAO_FEITA = ("apagada", "nao_feita", "movida", "reagendada")
BUCKETS_DURACAO = ((1.0, "ate_1h"), (2.0, "1h_2h"), (float("inf"), "mais_2h"))


def caminho(dados: Optional[Path] = None) -> Path:
    return (dados or base.data_dir()) / NOME_ARQUIVO


def faixa_de(instante: datetime) -> str:
    """``seg-manha`` etc. no fuso do próprio instante."""
    dia = schema.DIAS_SEMANA[instante.weekday()]
    hora = instante.hour
    for limite, nome in FAIXAS:
        if hora < limite:
            return "%s-%s" % (dia, nome)
    return "%s-noite" % dia


def bucket_duracao(horas: float) -> str:
    for limite, nome in BUCKETS_DURACAO:
        if horas <= limite:
            return nome
    return BUCKETS_DURACAO[-1][1]


def _ler_metas(dados: Path) -> dict[str, dict[str, Any]]:
    metas: dict[str, dict[str, Any]] = {}
    pasta = dados / "metas"
    if not pasta.is_dir():
        return metas
    for path in sorted(pasta.glob("M*.md")):
        if not schema.validar_id("meta", path.stem):
            continue
        bruto, _ = frontmatter.ler_arquivo(path)
        coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])
        if erros:
            raise GpErro(EXIT_VALIDACAO, "%s: %s" % (path.name, "; ".join(erros)))
        metas[coagido["id"]] = coagido
    return metas


# blocos já lidos e coagidos por arquivo de dia, pelo resumo do texto do arquivo (o arquivo é sempre relido; só
# o parse e a coerção são poupados); cada chamada recebe cópias
_BLOCOS_POR_DIA: dict[str, tuple[bytes, list[dict[str, Any]]]] = {}
TETO_CACHE_DIAS = 4000


def _blocos_do_dia(path: Path) -> list[dict[str, Any]]:
    try:
        texto = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        texto = None
    resumo = hashlib.blake2b(texto.encode("utf-8"), digest_size=20).digest() if texto is not None else None
    guardado = _BLOCOS_POR_DIA.get(str(path))
    if resumo is not None and guardado is not None and guardado[0] == resumo:
        return [dict(b) for b in guardado[1]]
    try:
        if texto is None:
            raise GpErro(EXIT_VALIDACAO, "")
        bruto_fm, corpo = frontmatter.separar(texto)  # o mesmo texto do resumo: o cache nunca guarda outra versão
        frontmatter.parse(bruto_fm)
    except GpErro:
        _, corpo = frontmatter.ler_arquivo(path)  # repete a leitura só para levantar o erro com arquivo e linha
        resumo = None
    lidos = []
    for bruto in frontmatter.parse_blocos(corpo):
        bruto.pop("_linha", None)
        coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["task"])
        if erros:
            raise GpErro(EXIT_VALIDACAO, "%s: bloco %s: %s" % (path.name, bruto.get("id"), "; ".join(erros)))
        coagido["_dia"] = path.stem
        lidos.append(coagido)
    if resumo is not None:
        if len(_BLOCOS_POR_DIA) > TETO_CACHE_DIAS:
            _BLOCOS_POR_DIA.clear()
        _BLOCOS_POR_DIA[str(path)] = (resumo, lidos)
    return [dict(b) for b in lidos]


def ler_blocos(dados: Path) -> dict[str, dict[str, Any]]:
    """``task_id → bloco`` (coagido) de todos os ``dias/*.md``; ids repetidos: o
    arquivo mais recente vence (blocos reagendados são reimportados). Arquivo de dia
    sem mudança não é lido de novo (cache por mtime e tamanho; cópias a cada chamada)."""
    blocos: dict[str, dict[str, Any]] = {}
    pasta = dados / "dias"
    if not pasta.is_dir():
        return blocos
    for path in sorted(pasta.glob("*.md")):
        if not schema.validar_id("dia", path.stem):
            continue
        for bloco in _blocos_do_dia(path):
            blocos[bloco["id"]] = bloco
    return blocos


def blocos_com_registro(
    dados: Path, registro: dict[str, Any], *, lidos: Optional[dict[str, dict[str, Any]]] = None
) -> dict[str, dict[str, Any]]:
    """``ler_blocos`` com o estado/origem (e a janela nova, quando movida ou
    reagendada) de ``registro.checkins`` por cima: o registro é a verdade;
    ``dias/`` é regenerado pelo diário. ``lidos``: o ``ler_blocos`` que quem chama já tem (é copiado, não mudado)."""
    blocos = {tid: dict(b) for tid, b in lidos.items()} if lidos is not None else ler_blocos(dados)
    checkins = registro.get("checkins", {})
    for task_id, bloco in blocos.items():
        if checkins.get(task_id):
            _aplicar_checkin(bloco, checkins[task_id])
    return blocos


def _aplicar_checkin(bloco: dict[str, Any], checkin: dict[str, Any]) -> None:
    bloco["estado"] = checkin["estado"]
    bloco["origem"] = checkin["origem"]
    if checkin.get("duracao_real_h") is not None:
        bloco["duracao_real_h"] = checkin["duracao_real_h"]
    for chave in ("calendar_id", "calendar_event_id"):
        if checkin.get(chave):
            bloco[chave] = checkin[chave]
    if checkin.get("inicio") and checkin.get("fim"):
        try:
            bloco["inicio"] = clock.parse_iso(str(checkin["inicio"]))
            bloco["fim"] = clock.parse_iso(str(checkin["fim"]))
        except GpErro:
            pass


def _horas(item: dict[str, Any]) -> float:
    valor = item.get("duracao_real_h")
    if valor is None:
        valor = item.get("duracao_h", 0.0)
    return float(valor or 0.0)


def _semanas(delta: timedelta) -> float:
    return max(delta.total_seconds(), 0.0) / (7 * 24 * 3600)


def _perfil_meta(
    meta: dict[str, Any],
    feitas: list[dict[str, Any]],
    registro: dict[str, Any],
    agora: datetime,
) -> dict[str, Any]:
    custo_total = float(meta["custo_h_semana_escolhido"]) * int(meta["semanas_pesquisa"])
    confirmadas = [f for f in feitas if f.get("origem") == "confirmado"]
    horas_confirmadas = sum(_horas(f) for f in confirmadas)
    presumidas_recentes, presumidas_antigas = _horas_presumidas(
        feitas, clock.para_utc(agora) - timedelta(days=DIAS_PRESUNCAO)
    )
    esforco = 100.0 * horas_confirmadas / custo_total if custo_total > 0 else 0.0
    declarado = reg.ultimo_progresso_declarado(registro, meta["id"])
    progresso = max(esforco, declarado or 0.0)
    ritmo = _ritmo_esperado(meta, agora)
    recentes = _horas_desde(confirmadas, clock.para_utc(agora) - timedelta(weeks=SEMANAS_MEDIA_MOVEL))
    return {
        "progresso_pct": round(progresso, 1),
        "progresso_presumido_pct": round(100.0 * presumidas_recentes / custo_total, 1) if custo_total > 0 else 0.0,
        "ritmo_esperado_pct": round(ritmo, 1),
        "delta": round(progresso - ritmo, 1),
        "horas_confirmadas": round(horas_confirmadas, 2),
        "horas_presumidas_nao_contadas": round(presumidas_antigas, 2),
        "fator_duracao": round(float(_fator_duracao(confirmadas)), 2),
        "h_semana_real": round(recentes / SEMANAS_MEDIA_MOVEL, 2),
    }


def _quando(feita: dict[str, Any]) -> Optional[datetime]:
    try:
        return clock.para_utc(clock.parse_iso(str(feita.get("ts"))))
    except GpErro:
        return None


def _horas_desde(feitas: list[dict[str, Any]], inicio: datetime) -> float:
    """Horas das feitas com data legível a partir de ``inicio`` (média móvel do h/semana real)."""
    total = 0.0
    for feita in feitas:
        quando = _quando(feita)
        if quando is not None and quando >= inicio:
            total += _horas(feita)
    return total


def _horas_presumidas(feitas: list[dict[str, Any]], limite: datetime) -> tuple[float, float]:
    """``(recentes, antigas)`` das presumidas; sem data legível conta como recente (no limite)."""
    recentes = antigas = 0.0
    for feita in feitas:
        if feita.get("origem") != "presumido":
            continue
        if (_quando(feita) or limite) >= limite:
            recentes += _horas(feita)
        else:
            antigas += _horas(feita)
    return recentes, antigas


def _ritmo_esperado(meta: dict[str, Any], agora: datetime) -> float:
    """Quanto do prazo já passou (em semanas), de 0 a 100; prazo sem semanas conta como 100."""
    criado_em = meta["criado_em"]
    prazo = datetime.combine(meta["prazo"], datetime.min.time(), tzinfo=criado_em.tzinfo)
    total = _semanas(prazo - criado_em)
    decorridas = _semanas(agora.astimezone(criado_em.tzinfo) - criado_em)
    return min(100.0, 100.0 * decorridas / total) if total > 0 else 100.0


def _fator_duracao(confirmadas: list[dict[str, Any]]) -> float:
    razoes = [
        float(f["duracao_real_h"]) / float(f["duracao_h"])
        for f in confirmadas
        if f.get("duracao_real_h") and f.get("duracao_h")
    ]
    return statistics.median(razoes) if len(razoes) >= MINIMO_OBSERVACOES else 1.0


def calcular(
    dados: Path,
    agora: Optional[datetime] = None,
    *,
    registro: Optional[dict[str, Any]] = None,
    metas: Optional[dict[str, dict[str, Any]]] = None,
    blocos: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """``perfil.json`` inteiro, sem gravar. ``registro``, ``metas`` (todas, com as arquivadas) e ``blocos`` (o
    ``ler_blocos`` cru, sem o registro por cima) evitam reler a pasta quando quem chama já leu (uma tela do painel)."""
    agora = agora or clock.agora()
    registro = registro if registro is not None else reg.carregar(dados)
    metas = metas if metas is not None else _ler_metas(dados)
    blocos = blocos if blocos is not None else ler_blocos(dados)
    feitas_por_meta = registro.get("feitas", {})
    perfil: dict[str, Any] = {
        "schema_version": schema.SCHEMA_VERSION,
        "gerado_em": agora.isoformat(timespec="seconds"),
        "n_confirmadas": 0,
        "metas": {},
        "janelas": {},
        "preferencias": {},
    }
    for id_meta, meta in metas.items():
        perfil["metas"][id_meta] = _perfil_meta(meta, feitas_por_meta.get(id_meta, []), registro, agora)
    perfil["n_confirmadas"], perfil["janelas"], perfil["preferencias"] = _janelas_e_preferencias(registro, blocos)
    erros = schema.validar_registro("perfil", perfil)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "perfil calculado inválido: " + "; ".join(erros))
    return perfil


def _resultado_do_checkin(checkin: dict[str, Any]) -> Optional[int]:
    """1 feita confirmada, 0 não feita (apagada, movida, reagendada, não feita); ``None`` para o que não ensina nada:
    presumido, prazo, feita que não foi confirmada e estados abertos."""
    origem, estado = checkin.get("origem"), checkin.get("estado")
    if origem in {"presumido", "prazo"} or (estado == "feita" and origem != "confirmado"):
        return None
    if estado == "feita":
        return 1
    return 0 if estado in ESTADOS_NAO_FEITA else None


def _janelas_e_preferencias(
    registro: dict[str, Any], blocos: dict[str, dict[str, Any]]
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Por checkin que ensina, com o bloco para saber a célula: ``(confirmadas, janelas, preferências)``."""
    celulas: dict[str, list[int]] = {}
    buckets: dict[str, list[int]] = {}
    duracoes: list[float] = []
    for task_id, checkin in registro.get("checkins", {}).items():
        resultado = _resultado_do_checkin(checkin)
        bloco = blocos.get(task_id)
        if resultado is None or bloco is None:
            continue
        if resultado == 1:
            duracoes.append(float(bloco["duracao_h"]))
        celulas.setdefault(faixa_de(bloco["inicio"]), []).append(resultado)
        buckets.setdefault(bucket_duracao(float(bloco["duracao_h"])), []).append(resultado)
    janelas = {
        celula: {"taxa_conclusao": round(sum(r) / len(r), 2), "n": len(r)} for celula, r in sorted(celulas.items())
    }
    preferencias: dict[str, Any] = {"taxa_por_duracao": {}}
    if duracoes:
        preferencias["bloco_medio_h"] = round(sum(duracoes) / len(duracoes), 2)
    for nome, resultados in sorted(buckets.items()):
        preferencias["taxa_por_duracao"][nome] = round(sum(resultados) / len(resultados), 2)
    return len(duracoes), janelas, preferencias


def gravar(dados: Path, perfil: dict[str, Any]) -> Path:
    path = caminho(dados)
    gpio.escrever_json(path, perfil)
    return path


def carregar(dados: Optional[Path] = None) -> Optional[dict[str, Any]]:
    path = caminho(dados)
    if not path.exists():
        return None
    perfil = gpio.ler_json(path)
    if not isinstance(perfil, dict) or schema.validar_registro("perfil", perfil):
        return None
    return perfil


def janelas_confiaveis(perfil: Optional[dict[str, Any]]) -> dict[str, float]:
    """``celula → taxa`` só das células com ``n >= MINIMO_OBSERVACOES``."""
    if not perfil:
        return {}
    return {
        celula: float(item["taxa_conclusao"])
        for celula, item in perfil.get("janelas", {}).items()
        if int(item.get("n", 0)) >= MINIMO_OBSERVACOES
    }
