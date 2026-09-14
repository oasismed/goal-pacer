"""registro.json: única via de escrita (achado 2.2; CEO 4.2; D4.11; eng 1.3).

Máquina de estados dos blocos (``schema.ESTADOS`` × ``schema.ORIGENS``)::

    planejada ---> feita | movida | reagendada | apagada | nao_feita | cancelada
    sem_sinal      (transitório: janela ainda não venceu)

    origem:  inferido  --> pode ser sobrescrita por inferido, presumido, confirmado, prazo
             presumido --> idem
             confirmado --> só por confirmado ou prazo (TRANSICOES_PROIBIDAS)
             prazo      --> transição automática por data (meta vencida/arquivada)

``registrar_checkin`` aplica a regra e devolve False (sem gravar) quando a
transição é proibida; nunca levanta por isso (é o caso normal do diário
inferindo sobre um bloco já confirmado pelo usuário). ``feitas[meta]``
guarda uma entrada por bloco feito (confirmado ou presumido); só as
confirmadas abatem a demanda (quem soma é ``demanda``/``perfil``).

Arquivo anual: entradas de anos anteriores com mais de ``DIAS_ANTES_DE_ARQUIVAR`` dias saem do
``registro.json`` para ``registro-AAAA.json`` (``arquivar``, chamado pelo job). A leitura é
transparente: ``carregar`` junta os anuais (o principal vence) e devolve um ``Registro`` que lembra
o que veio deles; ``salvar`` escreve no principal só o que não está igual no arquivo anual. Assim
totais e progresso não mudam com o arquivamento e o principal para de crescer::

    registro.json            ano corrente e o que tem menos de 120 dias
    registro-2026.json       o resto de 2026 (só leitura para os modos)

Leitura tolerante: arquivo ausente = registro vazio; JSON corrompido tenta
``io.recuperar`` (restaura o ``.bak``) e, sem .bak válido, é
``GpErro(EXIT_IO)`` (classe ``RegistroCorrompido`` no runbook). Toda escrita
valida contra ``schema.validar_registro("registro")`` antes de gravar
(atômico, com .bak).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from goalpacer import base, clock, io as gpio, schema, telemetria
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

NOME_ARQUIVO = "registro.json"
NOME_LOCK = ".lock"
DIAS_NOTA_RECUSADA = 30
ESTADOS_ABERTOS = ("planejada", "sem_sinal", "movida", "reagendada")
ESTADOS_FEITA = ("feita",)
PREFIXO_ANUAL = "registro-"
DIAS_ANTES_DE_ARQUIVAR = 120


class Registro(dict):
    """``registro.json`` já com os arquivos anuais; ``arquivado`` = identidade -> entrada vinda deles."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.arquivado: dict[tuple, Any] = {}


def caminho(dados: Optional[Path] = None) -> Path:
    return (dados or base.data_dir()) / NOME_ARQUIVO


def vazio() -> dict[str, Any]:
    registro = dict(schema.defaults("registro"))
    registro["schema_version"] = schema.SCHEMA_VERSION
    return registro


# conteúdos já validados, pelo resumo do JSON lido: validar de novo o mesmo conteúdo é o maior custo de cada tela do
# painel (análise de 13/09, P3). O resumo sai do objeto que acabou de ser lido (nada de mtime), e o JSON é sempre
# relido: ninguém recebe um objeto compartilhado.
_VALIDADOS: set[bytes] = set()
TETO_VALIDADOS = 64


def _resumo(conteudo: dict[str, Any]) -> bytes:
    return hashlib.blake2b(
        json.dumps(conteudo, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"), digest_size=20
    ).digest()


def _ler_validado(path: Path, rotulo: str) -> dict[str, Any]:
    try:
        registro = gpio.ler_json(path)
    except GpErro:
        if not gpio.recuperar(path):
            raise GpErro(
                EXIT_IO, "%s corrompido e sem .bak válido (RegistroCorrompido); rode registro.py recuperar" % rotulo
            ) from None
        telemetria.log("%s corrompido; restaurado do .bak" % rotulo, nivel="aviso")
        registro = gpio.ler_json(path)
    if not isinstance(registro, dict):
        raise GpErro(EXIT_VALIDACAO, "%s: esperado objeto JSON" % rotulo)
    if registro.get("schema_version") != schema.SCHEMA_VERSION:
        raise GpErro(
            EXIT_VALIDACAO,
            "%s: schema_version %r (esperado %d); rode install.sh --update"
            % (rotulo, registro.get("schema_version"), schema.SCHEMA_VERSION),
        )
    resumo = _resumo(registro)
    if resumo not in _VALIDADOS:
        erros = schema.validar_registro("registro", registro)
        if erros:
            raise GpErro(EXIT_VALIDACAO, "%s inválido: %s" % (rotulo, "; ".join(erros[:5])))
        if len(_VALIDADOS) >= TETO_VALIDADOS:
            _VALIDADOS.clear()
        _VALIDADOS.add(resumo)
    for chave, valor in schema.defaults("registro").items():
        registro.setdefault(chave, valor)
    return registro


def carregar(dados: Optional[Path] = None) -> dict[str, Any]:
    """``registro.json`` validado e somado aos ``registro-AAAA.json``; ausente = ``vazio()``; corrompido tenta o .bak."""
    path = caminho(dados)
    registro = Registro(_ler_validado(path, NOME_ARQUIVO) if path.exists() else vazio())
    for anual in caminhos_anuais(dados):
        conteudo = _ler_validado(anual, anual.name)
        for identidade, entrada in _entradas(conteudo):
            registro.arquivado[identidade] = entrada
        _fundir(registro, conteudo)
    return registro


def salvar(registro: dict[str, Any], dados: Optional[Path] = None) -> Path:
    """Valida e grava (atômico + .bak) só o que não está igual num arquivo anual. Inválido é ``GpErro(EXIT_VALIDACAO)``."""
    erros = schema.validar_registro("registro", registro)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "registro inválido, nada gravado: " + "; ".join(erros[:5]))
    principal = dict(registro)
    arquivado = getattr(registro, "arquivado", {})
    if arquivado:
        principal = _sem(principal, {i for i, e in _entradas(registro) if arquivado.get(i) == e})
    path = caminho(dados)
    gpio.escrever_json(path, principal)
    return path


# --- arquivo anual ----------------------------------------------------------------------


def caminhos_anuais(dados: Optional[Path] = None) -> list[Path]:
    pasta = dados or base.data_dir()
    return sorted(
        p
        for p in pasta.glob(PREFIXO_ANUAL + "*.json")
        if p.stem[len(PREFIXO_ANUAL) :].isdigit() and len(p.stem) == len(PREFIXO_ANUAL) + 4
    )


def _entradas(registro: dict[str, Any]):
    """``(identidade, entrada)`` de cada item arquivável; a identidade não muda quando a entrada é corrigida."""
    for run_id, geracao in (registro.get("geracoes") or {}).items():
        yield ("geracoes", run_id), geracao
    for task_id, checkin in (registro.get("checkins") or {}).items():
        yield ("checkins", task_id), checkin
    for meta, itens in (registro.get("feitas") or {}).items():
        for item in itens:
            yield ("feitas", meta, item.get("task_id")), item
    for secao, campo in (("progresso", "declarado_pct"), ("sentimentos", "valor")):
        for meta, itens in (registro.get(secao) or {}).items():
            for item in itens:
                yield (secao, meta, str(item.get("ts")), json.dumps(item.get(campo))), item
    for item in registro.get("notas_recusadas") or []:
        yield ("notas_recusadas", str(item.get("texto")), str(item.get("ts"))), item


def _data(identidade: tuple, entrada: dict[str, Any]) -> Optional[date]:
    secao = identidade[0]
    texto = (
        entrada.get("data")
        if secao == "geracoes"
        else identidade[1][2:12]
        if secao == "checkins"
        else entrada.get("ts")
    )
    try:
        return date.fromisoformat(str(texto)[:10])
    except ValueError:
        return None


def _fundir(destino: dict[str, Any], origem: dict[str, Any]) -> None:
    """Acrescenta em ``destino`` as entradas de ``origem`` que ele não tem (o destino vence)."""
    existentes = {i for i, _ in _entradas(destino)}
    for identidade, entrada in _entradas(origem):
        if identidade not in existentes:
            _colocar(destino, identidade, entrada)


def _colocar(destino: dict[str, Any], identidade: tuple, entrada: Any) -> None:
    secao = identidade[0]
    if secao in ("geracoes", "checkins"):
        destino.setdefault(secao, {})[identidade[1]] = entrada
    elif secao == "notas_recusadas":
        destino.setdefault(secao, []).append(entrada)
    else:
        destino.setdefault(secao, {}).setdefault(identidade[1], []).append(entrada)


def _sem(registro: dict[str, Any], identidades: set) -> dict[str, Any]:
    saida = dict(registro)
    for secao in ("geracoes", "checkins"):
        saida[secao] = {k: v for k, v in (registro.get(secao) or {}).items() if (secao, k) not in identidades}
    saida["feitas"] = _listas_sem(registro, "feitas", lambda m, i: ("feitas", m, i.get("task_id")), identidades)
    for secao, campo in (("progresso", "declarado_pct"), ("sentimentos", "valor")):
        saida[secao] = _listas_sem(
            registro,
            secao,
            lambda m, i, s=secao, c=campo: (s, m, str(i.get("ts")), json.dumps(i.get(c))),
            identidades,
        )
    saida["notas_recusadas"] = [
        i
        for i in registro.get("notas_recusadas") or []
        if ("notas_recusadas", str(i.get("texto")), str(i.get("ts"))) not in identidades
    ]
    return saida


def _listas_sem(
    registro: dict[str, Any], secao: str, identidade: Callable[[str, dict[str, Any]], tuple], identidades: set
) -> dict[str, list[dict[str, Any]]]:
    """``{meta: itens}`` sem os itens cuja identidade está em ``identidades``; meta que fica vazia sai."""
    filtradas = {
        meta: [item for item in itens if identidade(meta, item) not in identidades]
        for meta, itens in (registro.get(secao) or {}).items()
    }
    return {meta: itens for meta, itens in filtradas.items() if itens}


def arquivar(
    dados: Optional[Path] = None, agora: Optional[datetime] = None, dias: int = DIAS_ANTES_DE_ARQUIVAR
) -> dict[int, int]:
    """Move para ``registro-AAAA.json`` as entradas de anos anteriores com mais de ``dias`` dias.

    Quem chama segura o lock. Ordem segura contra queda no meio: primeiro o anual (atômico, a
    entrada fica nos dois e a leitura desduplica), depois o principal sem elas. Idempotente."""
    pasta = dados or base.data_dir()
    path = caminho(pasta)
    if not path.exists():
        return {}
    hoje = (agora or clock.agora()).date()
    limite = min(date(hoje.year, 1, 1), hoje - timedelta(days=dias))
    principal = _ler_validado(path, NOME_ARQUIVO)
    por_ano: dict[int, dict[str, Any]] = {}
    mover = set()
    for identidade, entrada in _entradas(principal):
        quando = _data(identidade, entrada)
        if quando is not None and quando < limite:
            mover.add(identidade)
            _colocar(por_ano.setdefault(quando.year, {"schema_version": schema.SCHEMA_VERSION}), identidade, entrada)
    if not mover:
        return {}
    contagem = {
        ano: _gravar_anual(pasta / ("%s%d.json" % (PREFIXO_ANUAL, ano)), novo) for ano, novo in sorted(por_ano.items())
    }
    gpio.escrever_json(path, _sem(principal, mover))
    return contagem


def _gravar_anual(anual_path: Path, novo: dict[str, Any]) -> int:
    """Funde ``novo`` no ``registro-AAAA.json`` (a versão do principal substitui a arquivada); devolve quantas entram."""
    anual = _ler_validado(anual_path, anual_path.name) if anual_path.exists() else dict(vazio())
    antes = sum(1 for _ in _entradas(anual))
    anual = _sem(anual, {i for i, _ in _entradas(novo)})
    anual["schema_version"] = schema.SCHEMA_VERSION
    _fundir(anual, novo)
    erros = schema.validar_registro("registro", anual)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "%s inválido, nada arquivado: %s" % (anual_path.name, "; ".join(erros[:3])))
    gpio.escrever_json(anual_path, anual)
    return max(0, sum(1 for _ in _entradas(anual)) - antes)


ENV_LOCK_HERDADO = "GP_LOCK_HERDADO"


class LockHerdado:
    """Lock já segurado pelo processo pai (``run_job.py``): não adquire nem libera."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.adquirido = False

    def liberar(self) -> None:
        return None


def lock(dados: Optional[Path] = None, *, espera_s: float = 0):
    """Lock único da pasta de dados (``DATA_DIR/.lock``), já adquirido.

    Com ``GP_LOCK_HERDADO=1`` e o lock gravado pelo processo pai (pid do
    arquivo == ``os.getppid()``), devolve um ``LockHerdado``: os passos de um
    job rodam sob o lock do ``run_job.py`` sem disputá-lo."""
    import os

    path = (dados or base.data_dir()) / NOME_LOCK
    if os.environ.get(ENV_LOCK_HERDADO) == "1":
        info = gpio.Lock(path).info()
        if info and info.get("pid") == os.getppid():
            return LockHerdado(path)
    trava = gpio.Lock(path, espera_s=espera_s)
    trava.adquirir()
    return trava


_iso = clock.iso


def transicao_permitida(origem_atual: Optional[str], origem_nova: str) -> bool:
    if origem_atual is None:
        return True
    return (origem_atual, origem_nova) not in schema.TRANSICOES_PROIBIDAS


def registrar_checkin(
    registro: dict[str, Any],
    task_id: str,
    estado: str,
    origem: str,
    *,
    ts: Optional[datetime] = None,
    duracao_real_h: Optional[float] = None,
    inicio: Optional[datetime] = None,
    fim: Optional[datetime] = None,
    calendar_id: Optional[str] = None,
    calendar_event_id: Optional[str] = None,
) -> bool:
    """Grava ``checkins[task_id]`` respeitando a máquina de estados.

    Devolve False sem alterar nada quando a origem atual é ``confirmado`` e
    a nova é ``inferido``/``presumido``. ``inicio``/``fim`` guardam a nova
    janela de um bloco movido/reagendado (o diário a importa);
    ``calendar_id``/``calendar_event_id`` dizem onde o evento está.
    ``estado``/``origem`` fora dos enums é ``GpErro(EXIT_VALIDACAO)``.
    """
    if estado not in schema.ESTADOS or origem not in schema.ORIGENS:
        raise GpErro(EXIT_VALIDACAO, "checkin inválido: estado=%r origem=%r" % (estado, origem))
    if not schema.validar_id("task", task_id):
        raise GpErro(EXIT_VALIDACAO, "task_id inválido: %r" % (task_id,))
    atual = registro.setdefault("checkins", {}).get(task_id)
    if atual is not None and not transicao_permitida(atual.get("origem"), origem):
        return False
    anterior = atual or {}
    entrada: dict[str, Any] = {"estado": estado, "origem": origem, "ts": _iso(ts or clock.agora())}
    if duracao_real_h is not None:
        entrada["duracao_real_h"] = float(duracao_real_h)
    elif anterior.get("duracao_real_h") is not None and estado in ESTADOS_FEITA:
        entrada["duracao_real_h"] = anterior["duracao_real_h"]
    entrada.update(_janela_do_checkin(anterior, estado, inicio, fim))
    for chave, valor in (("calendar_id", calendar_id), ("calendar_event_id", calendar_event_id)):
        if valor or anterior.get(chave):
            entrada[chave] = valor or anterior[chave]
    registro["checkins"][task_id] = entrada
    return True


def _janela_do_checkin(
    anterior: dict[str, Any], estado: str, inicio: Optional[datetime], fim: Optional[datetime]
) -> dict[str, str]:
    """A janela nova de um bloco movido ou reagendado; ela sobrevive às transições seguintes (sem_sinal, feita...)
    e some quando o bloco é apagado ou cancelado."""
    if inicio is not None and fim is not None and estado in ("movida", "reagendada"):
        return {"inicio": _iso(inicio), "fim": _iso(fim)}
    if anterior.get("inicio") and anterior.get("fim") and estado not in ("apagada", "cancelada"):
        return {"inicio": anterior["inicio"], "fim": anterior["fim"]}
    return {}


def registrar_feita(
    registro: dict[str, Any],
    meta: str,
    task_id: str,
    duracao_h: float,
    origem: str,
    *,
    duracao_real_h: Optional[float] = None,
    ts: Optional[datetime] = None,
) -> None:
    """Uma entrada por bloco em ``feitas[meta]`` (substitui a anterior do mesmo bloco)."""
    if not schema.validar_id("meta", meta):
        raise GpErro(EXIT_VALIDACAO, "meta inválida: %r" % (meta,))
    lista = registro.setdefault("feitas", {}).setdefault(meta, [])
    lista[:] = [item for item in lista if item.get("task_id") != task_id]
    entrada: dict[str, Any] = {
        "task_id": task_id,
        "duracao_h": float(duracao_h),
        "origem": origem,
        "ts": _iso(ts or clock.agora()),
    }
    if duracao_real_h is not None:
        entrada["duracao_real_h"] = float(duracao_real_h)
    lista.append(entrada)


def remover_feita(registro: dict[str, Any], task_id: str) -> None:
    """Tira o bloco de ``feitas`` (bloco que deixou de ser feita: nao_feita, apagada...)."""
    for lista in registro.get("feitas", {}).values():
        lista[:] = [item for item in lista if item.get("task_id") != task_id]


def declarar_progresso(registro: dict[str, Any], meta: str, pct: float, *, ts: Optional[datetime] = None) -> None:
    if not schema.validar_id("meta", meta):
        raise GpErro(EXIT_VALIDACAO, "meta inválida: %r" % (meta,))
    valor = float(pct)
    if not 0 <= valor <= 100:
        raise GpErro(EXIT_VALIDACAO, "progresso declarado fora de 0 a 100: %r" % (pct,))
    registro.setdefault("progresso", {}).setdefault(meta, []).append(
        {"declarado_pct": valor, "ts": _iso(ts or clock.agora())}
    )


def registrar_sentimento(registro: dict[str, Any], meta: str, valor: str, *, ts: Optional[datetime] = None) -> None:
    """Como a pessoa está com a meta (energia, firme, pesada), perguntado no check-in."""
    if not schema.validar_id("meta", meta):
        raise GpErro(EXIT_VALIDACAO, "meta inválida: %r" % (meta,))
    if valor not in schema.SENTIMENTOS:
        raise GpErro(EXIT_VALIDACAO, "sentimento %r fora de %s" % (valor, "|".join(schema.SENTIMENTOS)))
    registro.setdefault("sentimentos", {}).setdefault(meta, []).append(
        {"valor": valor, "ts": _iso(ts or clock.agora())}
    )


def ultimo_progresso_declarado(registro: dict[str, Any], meta: str) -> Optional[float]:
    itens = registro.get("progresso", {}).get(meta) or []
    if not itens:
        return None
    return float(max(itens, key=lambda item: str(item.get("ts")))["declarado_pct"])


def registrar_geracao(registro: dict[str, Any], geracao: dict[str, Any]) -> None:
    erros = schema.validar_registro("geracao", geracao)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "geracao inválida: " + "; ".join(erros))
    registro.setdefault("geracoes", {})[geracao["run_id"]] = dict(geracao)


def recusar_nota(registro: dict[str, Any], texto: str, *, ts: Optional[datetime] = None) -> None:
    registro.setdefault("notas_recusadas", []).append({"texto": texto.strip(), "ts": _iso(ts or clock.agora())})


def nota_recusada_recente(
    registro: dict[str, Any], texto: str, agora: Optional[datetime] = None, dias: int = DIAS_NOTA_RECUSADA
) -> bool:
    """True se a mesma nota foi recusada nos últimos ``dias`` (não repetir, design 7.2)."""
    agora = agora or clock.agora()
    limite = clock.para_utc(agora) - timedelta(days=dias)
    alvo = " ".join(texto.lower().split())
    for item in registro.get("notas_recusadas", []):
        if " ".join(str(item.get("texto", "")).lower().split()) != alvo:
            continue
        try:
            quando = clock.para_utc(clock.parse_iso(str(item.get("ts"))))
        except GpErro:
            continue
        if quando >= limite:
            return True
    return False
