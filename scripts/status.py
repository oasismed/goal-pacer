#!/usr/bin/env python3
"""status.py [--doctor [--sondar-escrita]] [--silencio] [--progresso M01=40] [--json]: o painel do terminal (T12/T32; design 1.4, 3.2, 8.2).

``status`` (80 colunas, só texto, ordem fixa)::

    cabeçalho
    silêncio (último diário há mais de 2 dias) ou "Nenhum diário por aqui" ou próximo diário
    Pendências     decisões do plano do mês, custos com pesquisa pendente, "feita?" dos últimos 14 dias, último job com erro
    Progresso      "M1 41% (+3% feita?) · ritmo 45%  título" por meta ativa (perfil.calcular, sem gravar)
    Cobertura      linha do mês e uma por meta, lidas do plano (balanco.py é quem escreve os números)
    Perfil         "baseado em N confirmadas", horas presumidas não contadas, faixas com n >= 5, fator de duração
    Evidências     sinais/ dos últimos 30 dias (resumos, nunca mensagens)
    Execuções      as 7 gerações mais recentes: quando, modo, ok ou classe, tokens, run_id

``--doctor``: 8 itens, cada um ``OK`` ou ``FALHOU: <o que fazer>`` (dados e
schema_version · lock · jobs no launchd · claude · python3 e Xcode CLT ·
conectores e calendário Metas, com sonda de escrita só em
``--sondar-escrita`` · último job). Exit 0 com tudo OK, 3 com algum FALHOU.
Cor só em terminal e sem ``NO_COLOR``; a palavra vem sempre escrita.

Variáveis para teste: ``GP_LAUNCHCTL``, ``GP_XCODE_SELECT``, ``GP_CLAUDE_BIN``, ``GP_OFFLINE_DIR``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, NamedTuple, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import diario
import validar
from goalpacer import (
    balanco,
    base,
    calendar_ops,
    cli,
    clock,
    codex,
    conexoes,
    copy,
    estilo,
    execucao,
    frontmatter,
    io as gpio,
    leitor,
    leitura as gpleitura,
    metas as gpmetas,
    offline,
    perfil as prf,
    plataforma,
    provedor,
    proxy,
    registro as reg,
    render,
    saude,
    schema,
    seguranca,
)
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro

DIAS_SILENCIO = 2
TETO_EXECUCOES = 7
TETO_PRESUMIDAS_IDS = 3
HORA_JOB = time(7, 0)
DIAS_JOB = (0, 1, 2, 3, 4, 5)  # seg a sáb, como o plist
PYTHON_MINIMO = (3, 9)
SERVIDORES_OBRIGATORIOS = conexoes.OBRIGATORIOS
VERDE, VERMELHO, NORMAL = "\033[32m", "\033[31m", "\033[0m"


# --- utilidades de texto -----------------------------------------------------------------


def colunas() -> int:
    return estilo.inteiro("colunas_terminal")


RE_CONTROLE_TERMINAL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def embrulhar(texto: str, recuo: str = "  ") -> list[str]:
    """Quebra em 80 colunas; caracteres de controle (escapes ANSI vindos de arquivos editáveis) viram espaço."""
    largura = colunas()
    texto = RE_CONTROLE_TERMINAL.sub(" ", texto)
    return textwrap.wrap(
        texto,
        width=largura,
        initial_indent=recuo,
        subsequent_indent=recuo + "  ",
        break_long_words=True,
        break_on_hyphens=False,
    ) or [recuo.rstrip()]


def celula(chave: str) -> str:
    """``qua-noite`` (célula do perfil) no idioma: ``qua-noite`` / ``Wed evening``."""
    dia, _, faixa = chave.partition("-")
    if dia not in schema.DIAS_SEMANA or faixa not in schema.FAIXAS_HORA:
        return chave
    return copy.texto(
        "status.celula",
        dia=copy.lista("calendario.dias_celula")[schema.DIAS_SEMANA.index(dia)],
        faixa=copy.lista("calendario.faixas")[schema.FAIXAS_HORA.index(faixa)],
    )


def quando_curto(instante: datetime) -> str:
    return "%s %s %s" % (copy.dia_curto(instante.date()), balanco.ddmm(instante.date()), instante.strftime("%H:%M"))


def idade_texto(segundos: float) -> str:
    segundos = max(0.0, segundos)
    if segundos < 3600:
        return "%d min" % int(segundos // 60)
    if segundos < 2 * 86400:
        return "%d h" % int(segundos // 3600)
    return "%d dias" % int(segundos // 86400)


def tokens_texto(tokens: dict[str, Any]) -> str:
    total = sum(int(v or 0) for v in (tokens or {}).values())
    if total >= 1_000_000:
        return "%s M tok" % balanco.horas(total / 1_000_000)
    if total >= 1000:
        return "%d k tok" % round(total / 1000)
    return "%d tok" % total


def proximo_job(agora: datetime) -> datetime:
    """Próximo disparo do plist diário (seg a sáb, 07:00 local)."""
    dia = agora.date()
    for _ in range(8):
        instante = datetime.combine(dia, HORA_JOB, tzinfo=agora.tzinfo)
        if dia.weekday() in DIAS_JOB and instante > agora:
            return instante
        dia += timedelta(days=1)
    return datetime.combine(dia, HORA_JOB, tzinfo=agora.tzinfo)


def _ts(geracao: dict[str, Any]) -> Optional[datetime]:
    try:
        return clock.parse_iso(str(geracao.get("ts")))
    except GpErro:
        return None


# --- status ------------------------------------------------------------------------------


def _diarios(registro: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        g
        for g in registro.get("geracoes", {}).values()
        if g.get("modo") in ("diario", "job:diario") and g.get("exit_code") == 0
    ]


def _plano(dados: Path, mes: str) -> Optional[dict[str, Any]]:
    """Números do plano do mês lidos do markdown gerado por ``balanco.py``."""
    path = dados / "planos" / ("%s.md" % mes)
    if not path.exists():
        return None
    return balanco.ler_plano(path.read_text(encoding="utf-8"))


def coletar(dados: Path, agora: datetime) -> dict[str, Any]:
    """Modelo do painel (dados já prontos para texto; nada é gravado)."""
    registro = reg.carregar(dados)
    metas = prf._ler_metas(dados)
    ativas = {k: v for k, v in metas.items() if v.get("estado", "ativa") == "ativa"}
    alertas = saude.alertas(dados, agora, registro)
    mes = clock.mes_da_semana(clock.semana_iso(agora.date()))
    leitura = gpleitura.leitura(dados, agora) if ativas else None
    perfil = (
        leitura["perfil"]
        if leitura
        else (prf.calcular(dados, agora, registro=registro, metas=metas) if metas else None)
    )
    return {
        "quando": quando_curto(agora),
        "aviso": _aviso(registro, agora),
        "pendencias": _pendencias(dados, registro, metas, ativas, agora),
        "progresso": _progresso(leitura) if leitura else [],
        "cobertura": _cobertura(_plano(dados, mes), mes, ativas),
        "perfil": _linhas_perfil(perfil, ativas) if perfil is not None else [],
        "evidencias": _evidencias(dados, agora),
        "execucoes": _execucoes(registro, agora),
        "saude": {
            "alertas": [a["texto"] for a in alertas],
            "chaves": [a["chave"] for a in alertas],
            "metricas": saude.metricas(dados),
        },
    }


def _aviso(registro: dict[str, Any], agora: datetime) -> str:
    diarios = [t for t in (_ts(g) for g in _diarios(registro)) if t is not None]
    if not diarios:
        return copy.texto("status.nunca_rodou", proximo=quando_curto(proximo_job(agora)))
    ultimo = max(diarios)
    dias = (agora - ultimo).total_seconds() / 86400
    if dias > DIAS_SILENCIO:
        return copy.texto("status.silencio", dias=int(dias), quando=quando_curto(ultimo.astimezone(agora.tzinfo)))
    return copy.texto("status.proximo", proximo=quando_curto(proximo_job(agora)))


def _presumidas_recentes(registro: dict[str, Any], agora: datetime) -> list[str]:
    limite = clock.para_utc(agora) - timedelta(days=prf.DIAS_PRESUNCAO)
    presumidas = []
    for task_id, item in sorted(registro.get("checkins", {}).items()):
        if item.get("estado") != "feita" or item.get("origem") != "presumido":
            continue
        try:
            if clock.para_utc(clock.parse_iso(str(item.get("ts")))) >= limite:
                presumidas.append(task_id)
        except GpErro:
            continue
    return presumidas


def _jobs(registro: dict[str, Any]) -> list[dict[str, Any]]:
    return [g for g in registro.get("geracoes", {}).values() if str(g.get("modo", "")).startswith("job:")]


def _pendencias(
    dados: Path, registro: dict[str, Any], metas: dict[str, Any], ativas: dict[str, Any], agora: datetime
) -> list[str]:
    _, decisoes = diario.plano_do_dia(dados, agora.date())
    pendencias = [
        copy.texto("status.decisao", meta=render.rotulo_meta(meta_id), texto=texto)
        for meta_id, texto in decisoes
        if meta_id in ativas
    ]
    pendencias += diario.custos_pendentes(dados, metas)
    presumidas = _presumidas_recentes(registro, agora)
    if presumidas:
        ids = ", ".join(presumidas[:TETO_PRESUMIDAS_IDS]) + (" …" if len(presumidas) > TETO_PRESUMIDAS_IDS else "")
        pendencias.append(copy.texto("status.presumidas", n=len(presumidas), ids=ids))
    jobs = _jobs(registro)
    ultimo_job = max(jobs, key=lambda g: str(g.get("ts"))) if jobs else {}
    if ultimo_job.get("exit_code") != 0 and ultimo_job.get("classe"):
        classe = ultimo_job["classe"]
        pendencias.append(copy.texto("status.ultimo_job", motivo=execucao.motivo(classe), acao=execucao.acao(classe)))
    return pendencias


def _progresso(leitura: dict[str, Any]) -> list[str]:
    resumo = gpleitura.resumo_coach(leitura)
    return ([resumo["manchete"]] if resumo["manchete"] else []) + resumo["linhas"]


def _cobertura(plano: Optional[dict[str, Any]], mes: str, ativas: dict[str, Any]) -> dict[str, Any]:
    titulo = copy.texto("status.titulo_cobertura", mes=balanco.mes_e_ano(mes))
    if plano is None:
        return {"titulo": titulo, "linhas": [copy.texto("status.sem_plano", mes=balanco.mes_e_ano(mes))]}
    linhas = [copy.texto("status.cobertura_mes", **plano["mes"])] if plano["mes"] else []
    for meta_id in sorted(plano["metas"]):
        info = plano["metas"][meta_id]
        if meta_id not in ativas or not info.get("cobertura"):
            continue
        decisao = info.get("decisao") if info.get("decisao") in gpmetas.SAIDAS else "manter"
        linhas.append(
            copy.texto(
                "status.cobertura_meta",
                meta=render.rotulo_meta(meta_id),
                cobertura=info["cobertura"],
                decisao=copy.texto("status.decisao_" + decisao),
            )
        )
    return {"titulo": titulo, "linhas": linhas}


def _linhas_perfil(perfil: dict[str, Any], ativas: dict[str, Any]) -> list[str]:
    linhas = [copy.texto("status.perfil_base", n=perfil["n_confirmadas"])]
    antigas = {
        m: i["horas_presumidas_nao_contadas"]
        for m, i in perfil["metas"].items()
        if i.get("horas_presumidas_nao_contadas")
    }
    if antigas:
        linhas.append(
            copy.texto(
                "status.perfil_presumidas",
                horas=balanco.horas(sum(antigas.values())),
                metas=", ".join(
                    "%s %s h" % (render.rotulo_meta(m), balanco.horas(h)) for m, h in sorted(antigas.items())
                ),
            )
        )
    faixas = prf.janelas_confiaveis(perfil)
    if faixas:
        linhas.append(
            copy.texto(
                "status.perfil_janelas",
                faixas=" · ".join("%s %s" % (celula(c), balanco.pct(100 * t)) for c, t in sorted(faixas.items())),
            )
        )
    for meta_id in sorted(ativas):
        fator = float(perfil["metas"].get(meta_id, {}).get("fator_duracao", 1.0))
        if abs(fator - 1.0) >= 0.05:
            linhas.append(
                copy.texto("status.perfil_fator", meta=render.rotulo_meta(meta_id), fator=balanco.horas(fator))
            )
    return linhas


def _evidencias(dados: Path, agora: datetime) -> list[str]:
    evidencias, _ = leitor.ler_sinais(dados, agora)
    return [
        "%s %s %s: %s" % (balanco.ddmm(date.fromisoformat(d)), f, render.rotulo_meta(m), r)
        for d, f, m, r in sorted(evidencias, reverse=True)
    ]


def _linha_execucao(g: dict[str, Any], agora: datetime) -> str:
    instante = _ts(g)
    resultado = (
        copy.texto("status.execucao_ok")
        if g.get("exit_code") == 0
        else (g.get("classe") or "exit %s" % g.get("exit_code"))
    )
    local = instante.astimezone(agora.tzinfo) if instante else None
    quando = "%s %s" % (balanco.ddmm(local.date()), local.strftime("%H:%M")) if local else "?"
    return "%s %-11s %-18s %-9s %s" % (
        quando,
        g.get("modo"),
        resultado,
        tokens_texto(g.get("tokens") or {}),
        g.get("run_id"),
    )


def execucoes_de_topo(registro: dict[str, Any]) -> list[dict[str, Any]]:
    """Gerações que não são passo de um job: os passos (run_id ``<job>-<passo>``) entram nos tokens do job."""
    ids_jobs = {g["run_id"] for g in _jobs(registro)}
    return [
        g
        for g in registro.get("geracoes", {}).values()
        if not any(str(g.get("run_id")).startswith(j + "-") for j in ids_jobs)
    ]


def _execucoes(registro: dict[str, Any], agora: datetime) -> list[str]:
    topo = execucoes_de_topo(registro)
    return [
        _linha_execucao(g, agora) for g in sorted(topo, key=lambda g: str(g.get("ts")), reverse=True)[:TETO_EXECUCOES]
    ]


def aviso_de_silencio(dados: Path, agora: datetime) -> Optional[str]:
    """Linha de abertura dos modos interativos (design 8.2): só quando o último diário tem mais de 2 dias.

    Sem nenhum diário ainda não avisa (o onboarding e o primeiro diário cuidam disso)."""
    try:
        registro = reg.carregar(dados)
    except GpErro:
        return None
    diarios = [t for g in _diarios(registro) for t in [_ts(g)] if t is not None]
    if not diarios:
        return None
    ultimo = max(diarios)
    dias = (agora - ultimo).total_seconds() / 86400
    if dias <= DIAS_SILENCIO:
        return None
    return copy.texto("status.silencio", dias=int(dias), quando=quando_curto(ultimo.astimezone(agora.tzinfo)))


def render_status(modelo: dict[str, Any]) -> str:
    linhas = [copy.texto("status.cabecalho", quando=modelo["quando"])]
    if modelo["aviso"]:
        linhas += embrulhar(modelo["aviso"], "")
    secoes = [(copy.texto("status.titulo_pendencias"), modelo["pendencias"] or [copy.texto("status.sem_pendencias")])]
    if (modelo.get("saude") or {}).get("alertas"):
        secoes.append((copy.texto("saude.titulo"), modelo["saude"]["alertas"]))
    secoes.append((copy.texto("status.titulo_progresso"), modelo["progresso"] or [copy.texto("status.sem_metas")]))
    if modelo["cobertura"]:
        secoes.append((modelo["cobertura"]["titulo"], modelo["cobertura"]["linhas"]))
    if modelo["perfil"]:
        secoes.append((copy.texto("status.titulo_perfil"), modelo["perfil"]))
    secoes.append(
        (copy.texto("status.titulo_evidencias"), modelo["evidencias"] or [copy.texto("status.sem_evidencias")])
    )
    secoes.append((copy.texto("status.titulo_execucoes"), modelo["execucoes"] or [copy.texto("status.sem_execucoes")]))
    for titulo, itens in secoes:
        linhas += ["", titulo]
        for item in itens:
            linhas += embrulhar(item)
    return "\n".join(linhas) + "\n"


# --- doctor ------------------------------------------------------------------------------


class Item(NamedTuple):
    nome: str
    ok: bool
    detalhe: str


def _rodar(argv: list[str], timeout_s: float = 30) -> tuple[int, str]:
    try:
        resultado = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return -1, str(erro)
    return resultado.returncode, (resultado.stdout or "") + (resultado.stderr or "")


def curto(path: Any) -> str:
    """Caminho com ``~`` no lugar da pasta pessoal (linhas mais curtas no terminal)."""
    texto = str(path)
    casa = str(Path.home())
    return "~" + texto[len(casa) :] if texto == casa or texto.startswith(casa + os.sep) else texto


def item_dados(dados: Path) -> tuple[Item, Optional[dict[str, Any]]]:
    nome = copy.texto("doctor.item_dados")
    if not dados.is_dir():
        return Item(nome, False, copy.texto("doctor.dados_sem_pasta", pasta=curto(dados))), None
    if not (dados / schema.CAMINHOS["contexto"]).exists():
        return Item(nome, False, copy.texto("doctor.dados_sem_contexto", pasta=curto(dados))), None
    try:
        bruto, _ = frontmatter.ler_arquivo(dados / schema.CAMINHOS["contexto"])
        if str(bruto.get("schema_version")) != str(schema.SCHEMA_VERSION):
            return Item(
                nome,
                False,
                copy.texto("doctor.dados_versao", atual=bruto.get("schema_version"), esperado=schema.SCHEMA_VERSION),
            ), None
        contexto = diario._contexto(dados)
    except GpErro as erro:
        return Item(nome, False, copy.texto("doctor.dados_invalidos", erro=erro.mensagem)), None
    if contexto.get("schema_version") != schema.SCHEMA_VERSION:
        return Item(
            nome,
            False,
            copy.texto("doctor.dados_versao", atual=contexto.get("schema_version"), esperado=schema.SCHEMA_VERSION),
        ), contexto
    try:
        reg.carregar(dados)
    except GpErro as erro:
        if "schema_version" in erro.mensagem:
            return Item(
                nome, False, copy.texto("doctor.dados_versao", atual="?", esperado=schema.SCHEMA_VERSION)
            ), contexto
        return Item(nome, False, copy.texto("doctor.dados_registro", erro=erro.mensagem)), contexto
    grafo = validar.validar_grafo(dados)
    if grafo.erros:
        return Item(nome, False, copy.texto("doctor.dados_invalidos", erro=grafo.erros[0])), contexto
    return Item(nome, True, copy.texto("doctor.dados_ok", pasta=curto(dados), versao=schema.SCHEMA_VERSION)), contexto


def item_lock(dados: Path) -> Item:
    nome = copy.texto("doctor.item_lock")
    path = dados / reg.NOME_LOCK
    situacao, info, idade = gpio.Lock(path).estado()
    if situacao == "livre":
        return Item(nome, True, copy.texto("doctor.lock_livre"))
    pid = (info or {}).get("pid", "?")
    minutos = int((idade or 0) // 60)
    if situacao == "ativo":
        return Item(nome, True, copy.texto("doctor.lock_ativo", pid=pid, minutos=minutos))
    return Item(nome, False, copy.texto("doctor.lock_obsoleto", pid=pid, minutos=minutos, caminho=curto(path)))


def item_jobs() -> Item:
    nome = copy.texto("doctor.item_jobs")
    sistema = plataforma.atual()
    agendador = sistema.agendador
    labels = [agendador.label(job) for job in plataforma.JOBS]
    carregados, erro = agendador.carregados()
    if carregados is None:
        return Item(nome, False, copy.texto("doctor.jobs_sem_agendador", agendador=agendador.nome, erro=erro or "?"))
    faltando = [label for label in labels if label not in carregados]
    if faltando:
        return Item(
            nome, False, copy.texto("doctor.jobs_faltando", labels=", ".join(faltando), agendador=agendador.nome)
        )
    if getattr(agendador, "linger", None) and agendador.linger() is False:
        return Item(
            nome, True, copy.texto("doctor.jobs_sem_linger", labels=", ".join(labels), agendador=agendador.nome)
        )
    return Item(nome, True, copy.texto("doctor.jobs_ok", labels=", ".join(labels), agendador=agendador.nome))


# provedor -> (chave do nome do item, binário, chave de "não encontrado")
BINARIOS_DO_PROVEDOR = {
    "claude": ("doctor.item_claude", proxy.claude_bin, "doctor.claude_ausente"),
    "openai": ("doctor.item_codex", codex.codex_bin, "doctor.codex_ausente"),
}


def item_provedor() -> Item:
    """O CLI do provedor da instalação: caminho absoluto, executável e respondendo a ``--version``."""
    chave_nome, binario, chave_ausente = BINARIOS_DO_PROVEDOR[provedor.ativo().nome]
    nome = copy.texto(chave_nome)
    caminho = binario()
    if not os.path.isabs(caminho):
        return Item(nome, False, copy.texto("doctor.claude_relativo", caminho=curto(caminho)))
    if not (os.path.isfile(caminho) and os.access(caminho, os.X_OK)):
        return Item(nome, False, copy.texto(chave_ausente, caminho=curto(caminho)))
    codigo, saida = _rodar([caminho, "--version"])
    if codigo != 0:
        return Item(nome, False, copy.texto(chave_ausente, caminho=curto(caminho)))
    return Item(
        nome, True, copy.texto("doctor.claude_ok", caminho=curto(caminho), versao=saida.strip().split("\n")[0][:40])
    )


def item_seguranca(dados: Path) -> Item:
    """Permissões dos dados, dos logs, do código dos jobs, do agendador e da skill (goalpacer/seguranca.py)."""
    import json as _json

    nome = copy.texto("doctor.item_seguranca")
    instalacao_path = base.jobs_dir() / base.NOME_INSTALACAO
    instalacao = {}
    if instalacao_path.is_file():
        try:
            instalacao = _json.loads(instalacao_path.read_text(encoding="utf-8"))
        except ValueError:
            instalacao = {}
    pastas = [dados]
    arquivos = []
    problemas = []
    if instalacao:
        jobs = base.jobs_dir()
        pastas = [base.raiz(), jobs, jobs / "logs", dados]
        arquivos = [instalacao_path, jobs / "painel-aparelhos.json"]
    problemas += seguranca.pastas_privadas(pastas) + seguranca.arquivos_privados(arquivos)
    app = Path(instalacao["app"]) if instalacao.get("app") else None
    if app is not None and app.is_dir():
        problemas += seguranca.codigo_protegido(app)
        agendador = plataforma.atual().agendador
        problemas += seguranca.agendador_protegido(agendador.instalados((*plataforma.JOBS, plataforma.PAINEL)))
        problemas += seguranca.skill_aponta_para(proxy.claude_config_dir() / "skills" / "goal-pacer", app)
    if not problemas:
        return Item(nome, True, copy.texto("doctor.seguranca_ok"))
    textos = [
        copy.texto(
            "doctor.seguranca_" + p.tipo,
            caminho=curto(p.caminho),
            modo=p.modo,
            quantos=p.quantos,
            alvo=p.alvo,
            app=curto(app) if app else "",
        )
        for p in problemas
    ]
    detalhe = "; ".join(textos[:2]) + (
        copy.texto("doctor.seguranca_mais", n=len(textos) - 2) if len(textos) > 2 else ""
    )
    return Item(nome, False, detalhe)


def item_python() -> Item:
    nome = copy.texto("doctor.item_python")
    caminho = sys.executable
    versao = "%d.%d.%d" % sys.version_info[:3]
    if tuple(sys.version_info[:2]) < PYTHON_MINIMO:
        return Item(nome, False, copy.texto("doctor.python_velho", caminho=curto(caminho), versao=versao))
    if not plataforma.atual().precisa_xcode:
        return Item(nome, True, copy.texto("doctor.python_ok", caminho=curto(caminho), versao=versao, extra=""))
    binario = os.environ.get(plataforma.ENV_XCODE_SELECT) or "/usr/bin/xcode-select"
    codigo, saida = _rodar([binario, "-p"])
    if codigo != 0:
        return Item(nome, False, copy.texto("doctor.python_sem_xcode", caminho=curto(caminho), versao=versao))
    return Item(
        nome,
        True,
        copy.texto(
            "doctor.python_ok",
            caminho=curto(caminho),
            versao=versao,
            extra=copy.texto("doctor.python_xcode", caminho=saida.strip().split("\n")[0]),
        ),
    )


def _chamar(
    tool: str, args: dict[str, Any], *, modo_offline: bool, modo_leitura: bool, servidores: Optional[list[str]]
) -> dict[str, Any]:
    if modo_offline:
        return offline.chamar(tool, args)
    return proxy.chamar(tool, args, modo_leitura=modo_leitura, servidores=servidores)


def _id_resposta(resposta: dict[str, Any], *chaves: str) -> Optional[str]:
    for chave in chaves:
        atual: Any = resposta
        for parte in chave.split("."):
            atual = atual.get(parte) if isinstance(atual, dict) else None
        if isinstance(atual, str) and atual:
            return atual
    return None


def sondar_escrita(
    contexto: dict[str, Any], agora: datetime, *, modo_offline: bool, servidores: Optional[list[str]]
) -> Optional[str]:
    """Cria e apaga um evento de sonda no Metas e um rascunho no Gmail. None = escrita ok; senão o texto de FALHOU."""
    titulo = copy.texto("doctor.sonda_titulo")
    inicio = datetime.combine(agora.date() + timedelta(days=1), time(3, 0), tzinfo=agora.tzinfo)
    args = {
        "calendarId": contexto["calendar_id_metas"],
        "summary": titulo,
        "description": copy.texto("doctor.sonda_descricao"),
        "start": inicio.isoformat(timespec="seconds"),
        "end": (inicio + timedelta(minutes=15)).isoformat(timespec="seconds"),
        "timeZone": contexto["timezone"],
        "overrideReminders": [],
        "notificationLevel": calendar_ops.NOTIFICACAO_NENHUMA,
    }
    try:
        criado = _chamar(
            calendar_ops.TOOL_CREATE, args, modo_offline=modo_offline, modo_leitura=False, servidores=servidores
        )
    except GpErro as erro:
        return copy.texto("doctor.escrita_escopo", servidor="Calendar", erro=execucao.classe_de(erro))
    evento = _id_resposta(criado, "id") or ("off-sonda" if modo_offline else None)
    if evento is None:
        return copy.texto("doctor.escrita_escopo", servidor="Calendar", erro="resposta sem id")
    try:
        _chamar(
            calendar_ops.TOOL_DELETE,
            calendar_ops.args_delete(contexto["calendar_id_metas"], evento),
            modo_offline=modo_offline,
            modo_leitura=False,
            servidores=servidores,
        )
    except GpErro as erro:
        return copy.texto("doctor.escrita_sobra", servidor="Calendar", erro=execucao.classe_de(erro), titulo=titulo)
    if not conexoes.usa_email(contexto):
        return None  # sem Gmail, só a escrita no Calendar importa
    rascunho = {
        "to": [contexto["email_proprio"]],
        "subject": copy.texto("doctor.sonda_assunto"),
        "body": copy.texto("doctor.sonda_corpo"),
    }
    try:
        criado = _chamar(
            "mcp__claude_ai_Gmail__create_draft",
            rascunho,
            modo_offline=modo_offline,
            modo_leitura=False,
            servidores=servidores,
        )
    except GpErro as erro:
        return copy.texto("doctor.escrita_escopo", servidor="Gmail", erro=execucao.classe_de(erro))
    mensagem = _id_resposta(criado, "message.id", "messageId")
    thread = _id_resposta(criado, "threadId", "message.threadId")
    try:
        if mensagem:
            _chamar(
                "mcp__claude_ai_Gmail__trash_message",
                {"messageId": mensagem},
                modo_offline=modo_offline,
                modo_leitura=False,
                servidores=servidores,
            )
        elif thread:
            _chamar(
                "mcp__claude_ai_Gmail__trash_thread",
                {"threadId": thread},
                modo_offline=modo_offline,
                modo_leitura=False,
                servidores=servidores,
            )
        elif not modo_offline:
            return copy.texto(
                "doctor.escrita_sobra", servidor="Gmail", erro="resposta sem id", titulo=rascunho["subject"]
            )
    except GpErro as erro:
        return copy.texto(
            "doctor.escrita_sobra", servidor="Gmail", erro=execucao.classe_de(erro), titulo=rascunho["subject"]
        )
    return None


def _estados_mcp(modo_offline: bool) -> dict[str, str]:
    """Estado de cada servidor em ``claude mcp list`` (fixture no --offline)."""
    if modo_offline:
        texto = offline.texto("mcp_list.txt")
    else:
        _codigo, texto = _rodar([proxy.claude_bin(), "mcp", "list"], timeout_s=90)
    return proxy.status_de_mcp_list(texto)


def _conectores_sem_leitura(nome: str, contexto: Optional[dict[str, Any]], estados: dict[str, str]) -> Optional[Item]:
    """O item quando não é preciso ler a agenda: conectores são opcionais e falta só o que a instalação escolheu usar
    (Calendar para a agenda, Gmail para o email). None = a instalação usa o Calendar e o Metas precisa ser conferido."""
    fora = [s for s in conexoes.exigidos(contexto) if "connected" not in estados.get(s, "").lower()]
    if fora:
        servidores = ", ".join(s.replace("_", " ") for s in fora)
        return Item(nome, False, copy.texto("doctor.conectores_mcp", servidores=servidores))
    if contexto is None:
        # antes do onboarding não há calendário Metas para conferir; o item da pasta de dados já pede o onboarding
        conectados = all("connected" in estados.get(s, "").lower() for s in SERVIDORES_OBRIGATORIOS)
        return Item(
            nome, True, copy.texto("doctor.conectores_sem_onboarding" if conectados else "doctor.conectores_opcionais")
        )
    if not conexoes.usa_agenda(contexto):
        chave = "doctor.conectores_so_email" if conexoes.usa_email(contexto) else "doctor.conectores_nenhum"
        return Item(nome, True, copy.texto(chave))
    return None


def item_conectores(contexto: Optional[dict[str, Any]], agora: datetime, *, modo_offline: bool, sondar: bool) -> Item:
    nome = copy.texto("doctor.item_conectores")
    if not provedor.ativo().conectores:
        return Item(nome, False, copy.texto("doctor.conectores_provedor", provedor=provedor.ativo().rotulo))
    estados = _estados_mcp(modo_offline)
    if not estados and conexoes.exigidos(contexto):  # sem conector nenhum só é problema se a instalação usa algum
        return Item(nome, False, copy.texto("doctor.conectores_formato"))
    conexoes.registrar_doctor(estados, agora, simulado=modo_offline)
    sem_leitura = _conectores_sem_leitura(nome, contexto, estados)
    if sem_leitura is not None:
        return sem_leitura
    contexto = contexto or {}  # com contexto None o item já saiu acima
    servidores = list(estados)
    try:
        calendarios = _chamar(
            diario.TOOL_LIST_CALENDARS, {}, modo_offline=modo_offline, modo_leitura=True, servidores=servidores
        )
    except GpErro as erro:
        return Item(
            nome,
            False,
            copy.texto(
                "doctor.conectores_leitura",
                erro="%s; %s" % (execucao.classe_de(erro), execucao.acao(execucao.classe_de(erro))),
            ),
        )
    ids = {str(c.get("id")) for c in (calendarios.get("calendars") or []) if isinstance(c, dict)}
    conexoes.registrar_doctor(
        estados, agora, metas_encontrado=contexto["calendar_id_metas"] in ids, simulado=modo_offline
    )
    if contexto["calendar_id_metas"] not in ids:
        return Item(nome, False, copy.texto("doctor.conectores_sem_metas", id=contexto["calendar_id_metas"]))
    escrita = copy.texto("doctor.escrita_nao_testada")
    if sondar:
        problema = sondar_escrita(contexto, agora, modo_offline=modo_offline, servidores=servidores)
        if problema:
            return Item(nome, False, problema)
        conexoes.registrar_doctor(estados, agora, metas_encontrado=True, escrita_ok=True, simulado=modo_offline)
        escrita = copy.texto("doctor.escrita_ok")
    return Item(nome, True, copy.texto("doctor.conectores_ok", escrita=escrita))


def item_ultimo(dados: Path, agora: datetime) -> Item:
    nome = copy.texto("doctor.item_ultimo")
    try:
        registro = reg.carregar(dados)
    except GpErro as erro:
        return Item(nome, False, copy.texto("doctor.dados_registro", erro=erro.mensagem))
    jobs = [
        (t, g)
        for g in registro.get("geracoes", {}).values()
        if str(g.get("modo", "")).startswith("job:")
        for t in [_ts(g)]
        if t is not None
    ]
    if not jobs:
        return Item(
            nome,
            False,
            copy.texto("doctor.ultimo_nenhum", comando=plataforma.atual().agendador.comando_agora("diario")),
        )
    instante, geracao = max(jobs, key=lambda par: par[0])
    idade = idade_texto((agora - instante).total_seconds())
    if geracao.get("exit_code") != 0:
        classe = geracao.get("classe") or "Desconhecida"
        return Item(
            nome,
            False,
            copy.texto(
                "doctor.ultimo_erro",
                run_id=geracao["run_id"],
                classe=classe,
                codigo=geracao.get("exit_code"),
                idade=idade,
                acao=execucao.acao(classe),
            ),
        )
    if (agora - instante).total_seconds() > DIAS_SILENCIO * 86400:
        return Item(
            nome,
            False,
            copy.texto(
                "doctor.ultimo_velho",
                run_id=geracao["run_id"],
                idade=idade,
                comando=plataforma.atual().agendador.comando_agora("diario"),
            ),
        )
    return Item(nome, True, copy.texto("doctor.ultimo_ok", run_id=geracao["run_id"], idade=idade))


def doctor(dados: Path, agora: datetime, *, modo_offline: bool, sondar: bool) -> list[Item]:
    dados_item, contexto = item_dados(dados)
    itens = [
        dados_item,
        item_lock(dados)
        if dados.is_dir()
        else Item(copy.texto("doctor.item_lock"), True, copy.texto("doctor.lock_livre")),
        item_seguranca(dados),
        item_jobs(),
        item_provedor(),
        item_python(),
    ]
    itens.append(item_conectores(contexto, agora, modo_offline=modo_offline, sondar=sondar))
    itens.append(
        item_ultimo(dados, agora)
        if dados.is_dir()
        else Item(
            copy.texto("doctor.item_ultimo"),
            False,
            copy.texto("doctor.ultimo_nenhum", comando=plataforma.atual().agendador.comando_agora("diario")),
        )
    )
    return itens


def usar_cor() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def render_doctor(itens: list[Item], agora: datetime, *, cor: bool = False) -> str:
    linhas = [copy.texto("doctor.titulo", quando=quando_curto(agora)), ""]
    for item in itens:
        estado = copy.texto("doctor.ok") if item.ok else copy.texto("doctor.falhou")
        if cor:
            estado = (VERDE if item.ok else VERMELHO) + estado + NORMAL
        cabeca = "%s %s" % (estado, item.nome)
        texto = "%s: %s" % (cabeca, item.detalhe)
        largura = colunas() + (len(VERDE) + len(NORMAL) if cor else 0)
        partes = textwrap.wrap(
            texto, width=largura, subsequent_indent="    ", break_long_words=True, break_on_hyphens=False
        )
        linhas += partes
    falhas = sum(1 for i in itens if not i.ok)
    linhas += [
        "",
        copy.texto("doctor.resumo_acao", n=falhas) if falhas else copy.texto("doctor.resumo_ok", n=len(itens)),
    ]
    return "\n".join(linhas) + "\n"


# --- CLI ---------------------------------------------------------------------------------


def declarar(dados: Path, pares: list[str], agora: datetime) -> list[str]:
    registro = reg.carregar(dados)
    metas = prf._ler_metas(dados)
    feitos = []
    erros = []
    for par in pares:
        meta_id, _, valor = par.partition("=")
        if meta_id not in metas:
            erros.append("%s: meta não existe" % meta_id)
            continue
        try:
            reg.declarar_progresso(registro, meta_id, float(valor.replace(",", ".")), ts=agora)
            feitos.append(
                copy.texto(
                    "status.progresso_declarado",
                    meta=render.rotulo_meta(meta_id),
                    pct=balanco.horas(float(valor.replace(",", "."))),
                )
            )
        except (GpErro, ValueError) as erro:
            erros.append("%s: %s" % (meta_id, getattr(erro, "mensagem", erro)))
    if erros:
        raise GpErro(EXIT_VALIDACAO, "\n".join(erros))
    reg.salvar(registro, dados)
    prf.gravar(dados, prf.calcular(dados, agora))
    return feitos


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("painel do Goal Pacer: status ou --doctor")
    parser.add_argument("--doctor", action="store_true", help="checa os 8 itens da instalação")
    parser.add_argument(
        "--sondar-escrita",
        dest="sondar",
        action="store_true",
        help="com --doctor: cria e apaga uma sonda no Metas e no Gmail",
    )
    parser.add_argument(
        "--silencio",
        action="store_true",
        help="só a linha de aviso quando o último diário tem mais de 2 dias (abertura dos modos interativos)",
    )
    parser.add_argument(
        "--progresso", action="append", default=[], metavar="M01=40", help="declara o progresso de uma meta (0 a 100)"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        agora = clock.agora()
        if args.silencio:
            return _cli_silencio(dados, agora)
        if args.doctor:
            return _cli_doctor(args, dados, agora)
        return _cli_status(args, dados, agora)
    except GpErro as erro:
        if args.json:
            sys.stdout.write(json.dumps(execucao.erro_json(erro), ensure_ascii=False) + "\n")
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo


def _cli_silencio(dados: Path, agora: datetime) -> int:
    aviso = aviso_de_silencio(dados, agora) if (dados / schema.CAMINHOS["contexto"]).exists() else None
    if aviso:
        sys.stdout.write(aviso + "\n")
    return EXIT_OK


def _cli_doctor(args: Any, dados: Path, agora: datetime) -> int:
    itens = doctor(dados, agora, modo_offline=args.offline, sondar=args.sondar)
    if args.json:
        corpo = {"ok": all(i.ok for i in itens), "itens": [i._asdict() for i in itens]}
        sys.stdout.write(json.dumps(corpo, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(render_doctor(itens, agora, cor=usar_cor()))
    return EXIT_OK if all(i.ok for i in itens) else EXIT_VALIDACAO


def _cli_status(args: Any, dados: Path, agora: datetime) -> int:
    if not (dados / schema.CAMINHOS["contexto"]).exists():
        sys.stdout.write(
            copy.texto("falhas.semonboarding_motivo") + ": " + copy.texto("falhas.semonboarding_acao") + "\n"
        )
        return base.EXIT_ESTADO
    if args.progresso:
        trava = reg.lock(dados)
        try:
            for linha in declarar(dados, args.progresso, agora):
                sys.stdout.write(linha + "\n")
        finally:
            trava.liberar()
    modelo = coletar(dados, agora)
    sys.stdout.write(json.dumps(modelo, ensure_ascii=False) + "\n" if args.json else render_status(modelo))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
