#!/usr/bin/env python3
"""demo_painel.py: pasta de dados de exemplo, rica o bastante para navegar no painel (``web.py --demo``).

Tudo sintético e determinístico (``random.Random(7)``), gerado offline e sem tokens::

    objetivos  O01 Mudar de carreira para dados · O02 Energia para a família · O03 Ser lido pelo que escrevo
    metas      M01 curso (O01, trimestre, essencial) presença alta, energia, dois marcos -> florescendo
               M02 corrida (O02, essencial) prazo externo, blocos movidos há 2 semanas -> pede atenção
               M03 artigos (O03, essencial) nada feito há quase duas semanas          -> travada
               M04 portfólio (O01, importante) presença média, evidência no email      -> ganhando ritmo
               M05 telas às 22h30 (O02, apoio) hábito diário quase sempre cumprido     -> florescendo
               M06 primeira vaga (O01, ano, essencial) conversas às sextas             -> meta do ano no drill-down
    histórico  cinco semanas de dias/ com estados finais no registro, sentimentos e progresso declarado
    hoje       plano de outubro e o dia 28/09 gerados pelos scripts de verdade; dois blocos da manhã confirmados;
               agenda útil 07:00-11:00 deixa outubro justo e o balanço pede uma decisão sobre M01
    status     uma semana de execuções do job diário (uma parada por limite de uso)

A pasta nasce da fixture ``tests/fixtures/mensal`` (contexto, agenda offline, export do WhatsApp).
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import shutil
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, clock, frontmatter, offline as offline_mod, registro as reg, render, schema

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mensal"
TZ = ZoneInfo("America/Sao_Paulo")
HOJE = date(2026, 9, 28)
AGORA_JOB = "2026-09-28T07:00:00-03:00"
AGORA_PAINEL = "2026-09-28T09:50:00-03:00"
METAS_ID = "metas-fixture@group.calendar.google.com"

OBJETIVOS = {
    "O01": (
        "Mudar de carreira para dados",
        "Quero trabalhar com análise de dados até o meio do ano que vem, com um trabalho que me dê orgulho.",
        "Uma proposta de vaga ou um projeto pago usando o que aprendi.",
    ),
    "O02": (
        "Ter energia para a família",
        "Chegar ao fim do dia com disposição para brincar com as crianças e dormir bem.",
        "Correr 10 km na prova de março e acordar descansado na maioria dos dias.",
    ),
    "O03": (
        "Ser lido pelo que escrevo",
        "Escrever me ajuda a pensar e abre portas; quero que as pessoas certas me encontrem.",
        "Quatro artigos publicados e uma conversa nova que veio de um deles.",
    ),
}

METAS: dict[str, dict[str, Any]] = {
    "M01": {
        "objetivo": "O01",
        "impacto": "essencial",
        "marcos": [
            ("Módulos 1 e 2 concluídos", True),
            ("Lista de exercícios do módulo 3", True),
            ("Projeto final com dados reais", False),
            ("Prova de certificação", False),
        ],
    },
    "M02": {
        "objetivo": "O02",
        "impacto": "essencial",
        "custo": 5,
        "marcos": [("Correr 5 km sem parar", True), ("Correr 7 km", False), ("Prova de 10 km em 01/03", False)],
    },
    "M03": {
        "objetivo": "O03",
        "impacto": "essencial",
        "titulo": "Publicar quatro artigos técnicos",
        "estado": "ativa",
        "custo": 3,
        "semanas": 12,
        "horizonte": "semestre",
        "prazo": "2027-01-31",
        "marcos": [
            ("Primeiro artigo publicado", True),
            ("Segundo artigo", False),
            ("Terceiro artigo", False),
            ("Quarto artigo", False),
        ],
    },
}
NOVAS: dict[str, dict[str, Any]] = {
    "M04": {
        "titulo": "Portfólio com três projetos de dados",
        "horizonte": "semestre",
        "prazo": "2027-02-28",
        "custo": 2,
        "semanas": 20,
        "objetivo": "O01",
        "impacto": "importante",
        "palavras": ["portfólio", "projeto"],
        "marcos": [
            ("Projeto 1: análise de vendas", True),
            ("Projeto 2: painel de indicadores", False),
            ("Projeto 3: modelo preditivo", False),
        ],
    },
    "M05": {
        "titulo": "Desligar as telas às 22h30",
        "horizonte": "trimestre",
        "prazo": "2026-12-20",
        "custo": 1,
        "semanas": 12,
        "objetivo": "O02",
        "impacto": "apoio",
        "palavras": ["sono"],
        "marcos": [("Duas semanas seguidas", True), ("Um mês seguido", False)],
    },
    "M06": {
        "titulo": "Conseguir a primeira vaga em dados",
        "horizonte": "ano",
        "prazo": "2027-08-31",
        "custo": 1,
        "semanas": 48,
        "objetivo": "O01",
        "impacto": "essencial",
        "palavras": ["vaga", "entrevista"],
        "marcos": [
            ("Currículo e LinkedIn refeitos", True),
            ("Dez conversas com pessoas da área", False),
            ("Três processos seletivos", False),
            ("Proposta aceita", False),
        ],
    },
}

# meta -> (dias da semana 0=seg, hora, minutos de duração, função de probabilidade de feita por semana 0..4)
AGENDA = {
    "M01": ((0, 2, 4), time(8, 0), 45, lambda _semana: 0.88),
    "M02": ((1, 3, 5), time(7, 0), 45, lambda semana: 0.85 if semana < 3 else 0.2),
    "M03": ((2, 5), time(19, 0), 60, lambda semana: 0.8 if semana < 3 else 0.0),
    "M04": ((1, 3), time(19, 30), 60, lambda _semana: 0.6),
    "M05": ((0, 1, 2, 3, 4, 5), time(22, 30), 30, lambda _semana: 0.9),
    "M06": ((4,), time(12, 30), 45, lambda semana: 0.5 if semana < 2 else 0.75),
}
SENTIMENTOS = {
    "M01": ("energia", 3),
    "M02": ("pesada", 4),
    "M03": ("pesada", 13),
    "M04": ("firme", 6),
    "M05": ("firme", 9),
    "M06": ("energia", 5),
}
EVIDENCIAS_EXTRA = [
    {"meta": "M01", "fonte": "gmail", "data": "2026-09-15", "resumo": "nota 9,2 na lista de exercícios do módulo 3"},
    {
        "meta": "M04",
        "fonte": "gmail",
        "data": "2026-09-22",
        "resumo": "recrutadora comentou o projeto de análise de vendas no portfólio",
    },
    {
        "meta": "M03",
        "fonte": "gmail",
        "data": "2026-09-02",
        "resumo": "leitor respondeu ao primeiro artigo pedindo continuação",
    },
]


def _ler_meta(path: Path) -> tuple[dict, str]:
    bruto, corpo = frontmatter.ler_arquivo(path)
    return frontmatter.coagir(bruto, schema.ESQUEMAS["metas"])[0], corpo


def _corpo_meta(por_que: str, marcos: list[tuple[str, bool]]) -> str:
    linhas = ["", "## Por que esta meta", "", por_que, "", "## Marcos", ""]
    linhas += ["- [%s] %s" % ("x" if feito else " ", texto) for texto, feito in marcos]
    return "\n".join(linhas) + "\n"


def _metas(dados: Path) -> None:
    porques = {
        "M01": "É a base técnica da mudança de carreira.",
        "M02": "Correr me dá energia e a prova de março já está paga.",
        "M03": "Escrever organiza o que aprendo e me torna visível.",
        "M04": "Mostra o que sei fazer com dados de verdade.",
        "M05": "Sem telas tarde, durmo melhor e o dia seguinte rende.",
        "M06": "É a mudança de carreira acontecendo de fato.",
    }
    for meta_id, ajuste in METAS.items():
        path = dados / "metas" / ("%s.md" % meta_id)
        meta, _ = _ler_meta(path)
        meta.update({"objetivo": ajuste["objetivo"], "impacto": ajuste["impacto"]})
        for chave, campo in (
            ("titulo", "titulo"),
            ("estado", "estado"),
            ("custo", "custo_h_semana_escolhido"),
            ("semanas", "semanas_pesquisa"),
            ("horizonte", "horizonte"),
        ):
            if chave in ajuste:
                meta[campo] = ajuste[chave]
        if "prazo" in ajuste:
            meta["prazo"] = date.fromisoformat(ajuste["prazo"])
        frontmatter.escrever_arquivo(
            path, frontmatter.coagir(meta, schema.ESQUEMAS["metas"])[0], _corpo_meta(porques[meta_id], ajuste["marcos"])
        )
    for meta_id, nova in NOVAS.items():
        meta = {
            "id": meta_id,
            "titulo": nova["titulo"],
            "horizonte": nova["horizonte"],
            "prazo": date.fromisoformat(nova["prazo"]),
            "estado": "ativa",
            "custo_h_semana_escolhido": float(nova["custo"]),
            "semanas_pesquisa": nova["semanas"],
            "confianca": "usuario",
            "palavras_chave": nova["palavras"],
            "criado_em": datetime(2026, 8, 20, 10, 0, tzinfo=TZ),
            "objetivo": nova["objetivo"],
            "impacto": nova["impacto"],
        }
        frontmatter.escrever_arquivo(
            dados / "metas" / ("%s.md" % meta_id),
            frontmatter.coagir(meta, schema.ESQUEMAS["metas"])[0],
            _corpo_meta(porques[meta_id], nova["marcos"]),
        )


def _objetivos(dados: Path) -> None:
    pasta = dados / "objetivos"
    pasta.mkdir(exist_ok=True)
    for oid, (titulo, por_que, saber) in OBJETIVOS.items():
        fm = {"id": oid, "titulo": titulo, "estado": "ativo", "criado_em": datetime(2026, 8, 20, 9, 30, tzinfo=TZ)}
        frontmatter.escrever_arquivo(
            pasta / ("%s.md" % oid), fm, "\n## Por que\n\n%s\n\n## Como vou saber\n\n%s\n" % (por_que, saber)
        )


def _historico(dados: Path) -> None:
    sorteio = random.Random(7)
    for path in (dados / "dias").glob("*.md"):
        path.unlink()
    registro = reg.vazio()
    titulos = {m: _ler_meta(dados / "metas" / ("%s.md" % m))[0]["titulo"] for m in AGENDA}
    inicio = HOJE - timedelta(days=35)
    for n in range(35):
        dia = inicio + timedelta(days=n)
        blocos = _blocos_sinteticos(dia, n // 7, sorteio, titulos, registro)
        if blocos:
            texto = render.render_dia(
                dia, "demo-%s" % dia.isoformat(), blocos, resumo_linha="Blocos do dia.", progresso={}
            )
            (dados / "dias" / ("%s.md" % dia.isoformat())).write_text(texto, encoding="utf-8")
    agora = datetime.combine(HOJE, time(7, 0), tzinfo=TZ)
    for meta_id, (valor, dias_atras) in SENTIMENTOS.items():
        reg.registrar_sentimento(registro, meta_id, valor, ts=agora - timedelta(days=dias_atras))
    reg.declarar_progresso(registro, "M02", 30, ts=agora - timedelta(days=7))
    reg.salvar(registro, dados)


def _blocos_sinteticos(
    dia: date, semana_idx: int, sorteio: random.Random, titulos: dict[str, str], registro: dict
) -> list[dict[str, Any]]:
    """Os blocos da agenda sintética no dia, com o check-in e a feita de cada um já no registro."""
    blocos = []
    for meta_id in sorted(AGENDA, key=lambda m: AGENDA[m][1]):
        dias, hora, minutos, chance = AGENDA[meta_id]
        if dia.weekday() not in dias:
            continue
        ini = datetime.combine(dia, hora, tzinfo=TZ)
        fim = ini + timedelta(minutes=minutos)
        estado, origem = _estado_sorteado(sorteio, chance(semana_idx))
        task_id = "D-%s-%02d" % (dia.isoformat(), len(blocos) + 1)
        blocos.append(
            {
                "id": task_id,
                "titulo": render.titulo_bloco(titulos[meta_id]),
                "meta": meta_id,
                "semana": clock.semana_iso(dia),
                "inicio": ini,
                "fim": fim,
                "duracao_h": round(minutos / 60, 2),
                "porque": "",
                "efeito": "",
                "estado": estado,
                "origem": origem,
                "calendar_event_id": "demo-%s" % task_id,
                "calendar_id": METAS_ID,
            }
        )
        ts = fim + timedelta(hours=1)
        reg.registrar_checkin(
            registro, task_id, estado, origem, ts=ts, calendar_id=METAS_ID, calendar_event_id="demo-%s" % task_id
        )
        if estado == "feita":
            reg.registrar_feita(registro, meta_id, task_id, round(minutos / 60, 2), origem, ts=ts)
    return blocos


def _estado_sorteado(sorteio: random.Random, chance: float) -> tuple[str, str]:
    """Feita (70% confirmada) com a ``chance`` da semana; senão movida, apagada ou não feita."""
    if sorteio.random() < chance:
        return "feita", ("confirmado" if sorteio.random() < 0.7 else "presumido")
    return sorteio.choice([("movida", "inferido"), ("apagada", "inferido"), ("nao_feita", "confirmado")])


def _execucoes(registro: dict) -> None:
    """Uma semana de jobs diários sintéticos para a tela Status (tokens na ordem do golden run); o de hoje embrulha os passos gerados."""
    sorteio = random.Random(11)
    for n in range(8):
        dia = HOJE - timedelta(days=n)
        if dia.weekday() == 6:
            continue
        fim = datetime.combine(dia, time(7, 3), tzinfo=TZ)
        geracao = {
            "run_id": "job-diario-%s" % dia.strftime("%Y%m%d"),
            "modo": "job:diario",
            "data": dia.isoformat(),
            "ts": fim.isoformat(),
            "exit_code": 0,
            "duracao_s": float(150 + sorteio.randint(0, 60)),
            "email": "enviado",
            "tokens": {
                "input": 5200 + sorteio.randint(0, 900),
                "cache_read": 0,
                "cache_creation": 0,
                "output": 1500 + sorteio.randint(0, 400),
            },
        }
        if n == 3:  # limite de uso nas duas tentativas: sem dia gerado, o de sábado volta ao normal
            geracao.update(
                {
                    "exit_code": 3,
                    "classe": "RateLimited",
                    "email": "nao_enviado",
                    "duracao_s": 1860.0,
                    "ts": (fim + timedelta(minutes=31)).isoformat(),
                }
            )
        reg.registrar_geracao(registro, geracao)


def _offline(destino: Path) -> Path:
    offline = destino / "offline"
    shutil.copytree(str(FIXTURE / "offline"), str(offline))
    (offline / "prosa_plano.txt").unlink()
    leitura = json.loads((offline / "mensal_ler.json").read_text(encoding="utf-8"))
    leitura["evidencias"] = [
        e
        for e in leitura["evidencias"]
        if e["meta"] in ("M01", "M02") and e["resumo"].strip() and e["fonte"] != "notion" and e["data"] >= "2026-09-01"
    ]
    leitura["evidencias"] += EVIDENCIAS_EXTRA
    (offline / "mensal_ler.json").write_text(json.dumps(leitura, ensure_ascii=False), encoding="utf-8")
    return offline


def ambiente(destino: Path) -> dict[str, str]:
    """Variáveis com que o painel serve o demo montado em ``destino``: pasta, raiz, fixtures offline, relógio e fuso."""
    return {
        base.ENV_DATA_DIR: str(destino / "dados"),
        base.ENV_RAIZ: str(destino / "raiz"),
        offline_mod.ENV_OFFLINE_DIR: str(destino / "offline"),
        clock.ENV_AGORA: AGORA_PAINEL,
        clock.ENV_TZ: str(TZ),
    }


@contextlib.contextmanager
def _ambiente_temporario(valores: dict[str, str]) -> Iterator[None]:
    antes = {nome: os.environ.get(nome) for nome in valores}
    os.environ.update(valores)
    try:
        yield
    finally:
        for nome, valor in antes.items():
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor


def preparar(destino: Path) -> Path:
    """Monta a pasta em ``destino/dados``. O ambiente do processo sai como entrou: quem serve o demo aplica
    ``ambiente(destino)`` (o ``web.py --demo``; os testes, pelo monkeypatch)."""
    dados = destino / "dados"
    shutil.copytree(str(FIXTURE / "dados"), str(dados))
    contexto = dados / "contexto.md"
    contexto.write_text(
        contexto.read_text(encoding="utf-8").replace(
            "horario_util_seg_sex: 08:00-10:00", "horario_util_seg_sex: 07:00-11:00"
        ),
        encoding="utf-8",
    )
    _offline(destino)
    with _ambiente_temporario(dict(ambiente(destino), **{clock.ENV_AGORA: AGORA_JOB})):
        _gerar(dados)
    _conexoes(destino / "raiz" / base.NOME_JOBS)
    return dados


def _conexoes(jobs: Path) -> None:
    """Estado sintético da tela Conexões: o que o doctor da véspera e o job das 7h teriam gravado."""
    jobs.mkdir(parents=True, exist_ok=True)
    doctor, job = "2026-09-27T21:10:00-03:00", AGORA_JOB
    estado = {
        "doctor_em": doctor,
        "metas_encontrado": True,
        "escrita_testada_em": doctor,
        "servidores": {
            "Google_Calendar": {"estado": "conectado", "visto_em": doctor, "uso_ok_em": job},
            "Gmail": {"estado": "conectado", "visto_em": doctor, "uso_ok_em": job},
            "Notion": {"estado": "reconectar", "visto_em": doctor},
            "Google_Drive": {"estado": "desconectado", "visto_em": doctor},
        },
    }
    (jobs / "conexoes.json").write_text(json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _gerar(dados: Path) -> None:
    import diario
    import mensal

    _objetivos(dados)
    _metas(dados)
    _historico(dados)
    agora = clock.agora()
    mensal.gerar(dados, modo_offline=True, agora=agora, run_id="job-diario-%s-mensal" % HOJE.strftime("%Y%m%d"))
    diario.gerar(
        dados,
        dia=HOJE,
        modo_offline=True,
        sem_inferir=False,
        agora=agora,
        run_id="job-diario-%s-diario" % HOJE.strftime("%Y%m%d"),
        enviar_email=True,
    )
    registro = reg.carregar(dados)
    blocos = sorted(
        (
            b
            for b in frontmatter.parse_blocos(frontmatter.ler_arquivo(dados / "dias" / ("%s.md" % HOJE.isoformat()))[1])
        ),
        key=lambda b: b["inicio"],
    )
    painel_agora = clock.parse_iso(AGORA_PAINEL)
    for bruto in blocos[:2]:
        coagido = frontmatter.coagir({k: v for k, v in bruto.items() if k != "_linha"}, schema.ESQUEMAS["task"])[0]
        if coagido["fim"] <= painel_agora:
            reg.registrar_checkin(registro, coagido["id"], "feita", "confirmado", ts=painel_agora - timedelta(hours=2))
            reg.registrar_feita(
                registro,
                coagido["meta"],
                coagido["id"],
                coagido["duracao_h"],
                "confirmado",
                ts=painel_agora - timedelta(hours=2),
            )
    _execucoes(registro)
    reg.salvar(registro, dados)


if __name__ == "__main__":
    import tempfile

    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="gp-demo-"))
    print(preparar(pasta))
