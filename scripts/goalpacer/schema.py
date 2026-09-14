"""Fonte única do esquema dos arquivos de dados (eng 2.1, T19, T36; D4.12).

Declara, por arquivo, os campos do front-matter/JSON (nome, tipo,
obrigatório, enum, default, ``no_hash``), os estados e origens dos blocos,
as regexes dos ids, as seções fixas de ``dias/`` e ``planos/`` e os
marcadores de prosa. ``frontmatter``, ``validar.py``, ``render.py``,
``registro.py`` e ``proxy.projetar_eventos`` leem daqui;
``python3 -m goalpacer.schema --md`` gera a seção de esquemas de
``references/dados.md``. A pasta de dados está descrita no design doc
(seção "Pasta de dados do usuário"); este módulo é a tradução dela.

Arquivos de front-matter (markdown): ``metas`` (metas/M<nn>.md),
``contexto`` (contexto.md), ``plano`` (planos/AAAA-MM.md), ``semana``
(semanas/AAAA-Www.md, espelho), ``dia`` (dias/AAAA-MM-DD.md). ``task`` é um
bloco no corpo de ``dias/`` (uma subseção ``### <task_id>`` com pares
``chave: valor``). Arquivos JSON: ``registro`` (registro.json, com os
sub-esquemas ``geracao``, ``checkin``, ``feita``, ``progresso_declarado``
e ``nota_recusada``), ``perfil`` (perfil.json, com ``perfil_meta``,
``perfil_janela`` e ``perfil_preferencias``), ``cache_calendar``
(cache/calendar-<modo>-<data>.json, com ``calendario`` e ``evento``: o
compacto que ``proxy.projetar_eventos`` produz), ``ops``
(cache/ops-<run_id>.json, com ``op``) e ``rascunho_onboarding``
(cache/onboarding-rascunho.json).

Ids: ``M<nn>`` meta; ``AAAA-MM`` mês; ``AAAA-Www`` semana ISO; ``AAAA-MM-DD``
dia; ``D-AAAA-MM-DD-<ss>`` task; ``gp:<task_id>/<instalacao_id>`` é a chave
que vai na última linha da descrição de cada bloco no Calendar (``gp_key``).

Estados do bloco e origens (máquina de estados aplicada por ``registro.py``)::

    planejada --> feita | movida | reagendada | apagada | nao_feita | cancelada
    sem_sinal: só enquanto a janela do bloco ainda não venceu (D4.11)
    origem: inferido | confirmado | presumido | prazo
    inferido/presumido nunca sobrescrevem confirmado (TRANSICOES_PROIBIDAS)

``hash_metas`` cobre só ``id``, ``titulo``, ``horizonte``, ``prazo`` e
``prazo_externo`` (design doc: custo e estado ficam fora); os demais campos
de ``metas`` têm ``no_hash=True``, ``campos_hash("metas")`` lista os que
entram e ``hash_metas(metas)`` calcula o valor gravado em ``planos/``.

Tipos: os oito do plano mais ``dict`` (mapa ou objeto, com regra em
``REGRAS_DICT``) e ``list_dict`` (lista de objetos de um sub-esquema, em
``REGRAS_LISTA``); ``list`` é sempre lista de strings.

Valores de data/hora: ``validar_registro`` aceita ``date``/``datetime``
nativos (front-matter) ou strings ISO 8601 (JSON), normalizadas por
``clock.normalizar_iso`` (``Z``, fração de qualquer largura, ``+0000``;
formato básico recusado), o mesmo em 3.9 e 3.13. ``NaN``/``Infinity`` são
recusados em todo int/float.

Este módulo importa só a stdlib, ``goalpacer.base`` e ``goalpacer.clock``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime
from typing import Any, Callable, Iterable, NamedTuple, Optional

from goalpacer import clock
from goalpacer.base import EXIT_OK, EXIT_VALIDACAO, GpErro

SCHEMA_VERSION = 1

TIPOS = ("str", "int", "float", "bool", "date", "datetime", "list", "enum", "dict", "list_dict")

ESTADOS = (
    "planejada",
    "feita",
    "movida",
    "reagendada",
    "apagada",
    "nao_feita",
    "sem_sinal",
    "cancelada",
)
ORIGENS = ("inferido", "confirmado", "presumido", "prazo")

# Pares (origem_atual, origem_nova) que registro.py rejeita.
TRANSICOES_PROIBIDAS = (
    ("confirmado", "inferido"),
    ("confirmado", "presumido"),
)

HORIZONTES = ("trimestre", "semestre", "ano")
ESTADOS_META = ("ativa", "pausada", "concluida", "vencida", "arquivada")
CONFIANCAS = ("alta", "media", "baixa", "usuario")
FONTES = ("gmail", "whatsapp", "notion", "drive")
LEMBRETES = ("sim", "nao")
EMAIL_STATUS = ("enviado", "falhou", "nao_enviado")
OPS = ("create", "update", "delete")
STATUS_OP = ("ok", "erro")
IMPACTOS = ("essencial", "importante", "apoio")
PESO_IMPACTO = {"essencial": 3, "importante": 2, "apoio": 1}
ESTADOS_OBJETIVO = ("ativo", "conquistado", "pausado")
SENTIMENTOS = ("energia", "firme", "pesada")
DIAS_SEMANA = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")
FAIXAS_HORA = ("manha", "tarde", "noite")

TETO_PALAVRAS_CHAVE = 3
TETO_PORQUE_CHARS = 90
HASH_METAS_CAMPOS = ("titulo", "prazo", "prazo_externo", "horizonte")
HASH_METAS_TAMANHO = 16

RE_META = re.compile(r"^M[0-9]{2}\Z")
RE_OBJETIVO = re.compile(r"^O[0-9]{2}\Z")
RE_MES = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])\Z")
RE_SEMANA = re.compile(r"^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])\Z")
RE_DIA_ID = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\Z")
RE_TASK_ID = re.compile(r"^D-[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])-[0-9]{2}\Z")
RE_INSTALACAO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


def gp_key(task_id: str, instalacao_id: str) -> str:
    """Última linha da descrição de um bloco: ``gp:<task_id>/<instalacao_id>`` (casa ``RE_GP_KEY``)."""
    return "gp:%s/%s" % (task_id, instalacao_id)


RE_GP_KEY = re.compile(r"^gp:(D-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2})/([A-Za-z0-9][A-Za-z0-9._-]{0,63})\Z")
RE_HORARIO_UTIL = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]-([01][0-9]|2[0-3]):[0-5][0-9]\Z")
RE_JANELA_PERFIL = re.compile(r"^(%s)-(%s)\Z" % ("|".join(DIAS_SEMANA), "|".join(FAIXAS_HORA)))
RE_NOME_CAMPO = re.compile(r"^[a-z][a-z0-9_]*\Z")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+\Z")

REGEX_POR_TIPO_ID = {
    "meta": RE_META,
    "objetivo": RE_OBJETIVO,
    "mes": RE_MES,
    "semana": RE_SEMANA,
    "dia": RE_DIA_ID,
    "task": RE_TASK_ID,
}

# Formatos de string além dos ids (mesma mecânica de validar_id). Todas as
# regexes terminam em \Z, não $: "M01\n" não pode casar.
REGEX_POR_FORMATO = dict(REGEX_POR_TIPO_ID)
REGEX_POR_FORMATO["horario_util"] = RE_HORARIO_UTIL
REGEX_POR_FORMATO["email"] = RE_EMAIL
REGEX_POR_FORMATO["instalacao_id"] = RE_INSTALACAO_ID
REGEX_POR_FORMATO["gp_key"] = RE_GP_KEY
REGEX_POR_FORMATO["janela_perfil"] = RE_JANELA_PERFIL
STATUS_WHATSAPP = ("ok", "stale", "nao_reconhecido", "truncado", "sem_export")
REGEX_POR_FORMATO["status_whatsapp"] = re.compile(r"^(%s)\Z" % "|".join(STATUS_WHATSAPP))
# Fronteira de privacidade do Calendar: fora do calendário Metas estes campos chegam null ao cache (proxy.projetar_evento).
CAMPOS_SO_DO_METAS = ("summary", "description")

EXEMPLOS_ID = {
    "meta": "M01",
    "objetivo": "O01",
    "mes": "2026-09",
    "semana": "2026-W40",
    "dia": "2026-09-28",
    "task": "D-2026-09-28-01",
}


class Campo(NamedTuple):
    """Um campo do esquema.

    ``tipo`` é um de ``TIPOS``; ``enum`` restringe o valor (ou os itens, se
    ``tipo == "list"``); ``default`` vale quando o campo é opcional e está
    ausente; ``no_hash`` exclui o campo do ``hash_metas`` do plano.
    """

    nome: str
    tipo: str
    obrigatorio: bool = True
    enum: Optional[tuple] = None
    default: Any = None
    no_hash: bool = False
    descricao: str = ""


# Onde cada arquivo mora dentro de DATA_DIR (documentação e validar.py).
CAMINHOS = {
    "metas": "metas/M<nn>.md",
    "objetivo": "objetivos/O<nn>.md",
    "fonte_pesquisa": "fontes/M<nn>.md",
    "contexto": "contexto.md",
    "plano": "planos/AAAA-MM.md",
    "sinais": "sinais/AAAA-MM-DD.md",
    "semana": "semanas/AAAA-Www.md",
    "dia": "dias/AAAA-MM-DD.md",
    "task": "dias/AAAA-MM-DD.md, um bloco `### <task_id>` no corpo",
    "registro": "registro.json",
    "geracao": "registro.json, uma entrada de geracoes",
    "checkin": "registro.json, uma entrada de checkins",
    "feita": "registro.json, um item de feitas[meta]",
    "progresso_declarado": "registro.json, um item de progresso[meta]",
    "sentimento": "registro.json, um item de sentimentos[meta]",
    "nota_recusada": "registro.json, um item de notas_recusadas",
    "perfil": "perfil.json",
    "perfil_meta": "perfil.json, uma entrada de metas",
    "perfil_janela": "perfil.json, uma entrada de janelas",
    "perfil_preferencias": "perfil.json, o objeto preferencias",
    "cache_calendar": "cache/calendar-<modo>-<data>.json",
    "calendario": "cache/calendar-*.json, um item de calendarios",
    "evento": "cache/calendar-*.json, um item de eventos (projeção de privacidade)",
    "ops": "cache/ops-<run_id>.json",
    "op": "cache/ops-*.json, um item de ops",
    "rascunho_onboarding": "cache/onboarding-rascunho.json",
}

# Arquivos gravados como front-matter (chaves planas, sem dict/list_dict).
ARQUIVOS_FRONTMATTER = ("metas", "objetivo", "fonte_pesquisa", "contexto", "plano", "sinais", "semana", "dia", "task")

ESTADOS_PESQUISA = ("ok", "sem_numero", "pendente")

ESQUEMAS: dict[str, list[Campo]] = {
    "metas": [
        Campo("id", "str", True, descricao="`M<nn>`, igual ao nome do arquivo, nunca reutilizado"),
        Campo("titulo", "str", True, descricao="título humano da meta"),
        Campo("horizonte", "enum", True, HORIZONTES, descricao="trimestre, semestre ou ano"),
        Campo("prazo", "date", True, descricao="data limite"),
        Campo(
            "prazo_externo",
            "bool",
            False,
            default=False,
            descricao="prazo imposto por terceiros (muda a decisão sugerida)",
        ),
        Campo(
            "estado",
            "enum",
            False,
            ESTADOS_META,
            default="ativa",
            no_hash=True,
            descricao="ativa, pausada (sai do plano e volta quando reativada), concluida, vencida ou arquivada (remoção é arquivada)",
        ),
        Campo(
            "custo_h_semana_min", "float", False, no_hash=True, descricao="piso de horas/semana encontrado na pesquisa"
        ),
        Campo(
            "custo_h_semana_max", "float", False, no_hash=True, descricao="teto de horas/semana encontrado na pesquisa"
        ),
        Campo(
            "custo_h_semana_escolhido",
            "float",
            True,
            no_hash=True,
            descricao="horas/semana confirmadas pelo usuário (> 0); entra no balanço",
        ),
        Campo(
            "semanas_pesquisa",
            "int",
            True,
            no_hash=True,
            descricao="semanas de duração estimadas (> 0); custo_total_h = escolhido × semanas",
        ),
        Campo(
            "confianca",
            "enum",
            True,
            CONFIANCAS,
            no_hash=True,
            descricao="alta, media, baixa (pesquisa) ou usuario (número dado à mão)",
        ),
        Campo(
            "fonte",
            "str",
            False,
            default="",
            no_hash=True,
            descricao="`fontes/M<nn>.md`, URL ou vazio quando o número é do usuário",
        ),
        Campo(
            "palavras_chave", "list", False, default=[], no_hash=True, descricao="até 3 termos para buscar evidências"
        ),
        Campo("criado_em", "datetime", True, no_hash=True, descricao="instante do onboarding"),
        Campo(
            "objetivo",
            "str",
            False,
            default="",
            no_hash=True,
            descricao="`O<nn>` do objetivo final que esta meta serve; vazio = a meta é o próprio objetivo",
        ),
        Campo(
            "impacto",
            "enum",
            False,
            IMPACTOS,
            default="importante",
            no_hash=True,
            descricao="peso no objetivo: essencial (3), importante (2) ou apoio (1)",
        ),
    ],
    "objetivo": [
        Campo("id", "str", True, descricao="`O<nn>`, igual ao nome do arquivo"),
        Campo("titulo", "str", True, descricao="o que a pessoa quer que mude, em palavras dela"),
        Campo("estado", "enum", False, ESTADOS_OBJETIVO, default="ativo", descricao="ativo, conquistado ou pausado"),
        Campo("criado_em", "datetime", False, descricao="quando o objetivo foi cadastrado"),
    ],
    "fonte_pesquisa": [
        Campo("id", "str", True, descricao="`M<nn>` da meta"),
        Campo("pesquisado_em", "datetime", True, descricao="quando a pesquisa (ou a estimativa manual) foi feita"),
        Campo(
            "estado",
            "enum",
            False,
            ESTADOS_PESQUISA,
            default="ok",
            descricao="ok, sem_numero (busca sem número) ou pendente (titulo/horizonte/prazo mudaram)",
        ),
        Campo("busca", "str", False, default="", descricao="a consulta feita, ou vazio se o número foi dado à mão"),
        Campo("urls", "list", False, default=[], descricao="páginas de onde o número saiu"),
        Campo("trecho", "str", False, default="", descricao="trecho literal citado; sem trecho a confiança é baixa"),
        Campo("custo_h_semana_min", "float", False, descricao="piso encontrado"),
        Campo("custo_h_semana_max", "float", False, descricao="teto encontrado"),
        Campo("semanas_pesquisa", "int", False, descricao="duração encontrada, em semanas"),
        Campo(
            "hash_meta",
            "str",
            False,
            default="",
            descricao="hash dos campos da meta na pesquisa (titulo, horizonte, prazo); diferente = pendente",
        ),
    ],
    "contexto": [
        Campo("schema_version", "int", True, descricao="versão do esquema gravada no onboarding (9.1)"),
        Campo("instalacao_id", "str", True, descricao="id desta instalação; vai na `gp_key` de cada bloco (D4.9)"),
        Campo(
            "idioma", "str", False, default="pt-BR", descricao="idioma das superfícies (`references/copy.<idioma>.md`)"
        ),
        Campo("timezone", "str", True, descricao="nome IANA validado no onboarding"),
        Campo(
            "horario_util_seg_sex", "str", False, default="08:00-19:00", descricao="`HH:MM-HH:MM`; vazio = sem janela"
        ),
        Campo("horario_util_sab", "str", False, default="09:00-13:00", descricao="`HH:MM-HH:MM`; vazio = sem janela"),
        Campo("horario_util_dom", "str", False, default="", descricao="`HH:MM-HH:MM`; vazio = sem janela"),
        Campo(
            "buffer_min", "int", False, default=10, descricao="minutos de folga antes e depois de cada evento ocupado"
        ),
        Campo(
            "calendar_id_metas",
            "str",
            False,
            default="",
            descricao="único calendário com escrita (criado à mão); vazio = sem Google Calendar (blocos só no app)",
        ),
        Campo(
            "calendar_id_primario",
            "str",
            False,
            default="",
            descricao="calendário cujo id é o e-mail do usuário; obrigatório junto com o Metas",
        ),
        Campo(
            "calendarios_lidos",
            "list",
            False,
            default=[],
            descricao="ids lidos para as janelas; vazio = todos; primário e Metas sempre entram",
        ),
        Campo(
            "email_proprio",
            "str",
            False,
            default="",
            descricao="único destinatário do email das 7h; vazio = sem Gmail (sem email, o dia fica no app)",
        ),
        Campo(
            "email_alias", "list", False, default=[], descricao="endereços send-as excluídos da busca do Gmail (D4.8)"
        ),
        Campo(
            "fontes_ativas", "list", False, FONTES, default=[], descricao="fontes de evidência desta instalação (9.2)"
        ),
        Campo(
            "lembretes",
            "enum",
            False,
            LEMBRETES,
            default="nao",
            descricao="lembretes do Google nos blocos; nao = overrideReminders vazio",
        ),
        Campo("tetos_gmail_threads", "int", False, default=15, descricao="threads Gmail por meta no mensal-ler (7.1)"),
        Campo("tetos_gmail_threads_inteiras", "int", False, default=3, descricao="threads abertas inteiras por meta"),
        Campo("tetos_notion_paginas", "int", False, default=5, descricao="páginas Notion por meta"),
        Campo("tetos_drive_arquivos", "int", False, default=5, descricao="arquivos Drive por meta"),
        Campo("tetos_drive_caracteres", "int", False, default=4000, descricao="caracteres lidos por arquivo Drive"),
        Campo(
            "restricoes_horario",
            "list",
            False,
            default=[],
            descricao="`M<nn> HH:MM-HH:MM` por meta, vindas de notas confirmadas no checkin",
        ),
        Campo(
            "pessoas",
            "list",
            False,
            default=[],
            descricao="nomes que o usuário quer ver reconhecidos na prosa (opcional)",
        ),
    ],
    "plano": [
        Campo("mes", "str", True, descricao="`AAAA-MM`"),
        Campo("hash_metas", "str", True, descricao="`hash_metas()` das metas na geração"),
        Campo(
            "hash_numeros",
            "str",
            True,
            descricao="hash do corpo sem o texto dos blocos de prosa; diferente = números alterados fora do balanço",
        ),
        Campo("fontes", "list", False, FONTES, default=[], descricao="fontes que entraram neste mensal"),
        Campo("gerado_em", "datetime", True, descricao="instante da geração"),
        Campo("run_id", "str", True, descricao="execução que gerou"),
    ],
    "sinais": [
        Campo("data", "date", True, descricao="dia da leitura das fontes"),
        Campo("run_id", "str", True, descricao="execução do mensal-ler"),
        Campo("fontes", "list", False, FONTES, default=[], descricao="fontes lidas nesta execução"),
        Campo("gmail_vistos", "int", False, default=0, descricao="threads vistas (assunto + trecho)"),
        Campo("gmail_abertos", "int", False, default=0, descricao="threads abertas inteiras"),
        Campo("notion_vistos", "int", False, default=0, descricao="páginas encontradas"),
        Campo("notion_abertos", "int", False, default=0, descricao="páginas lidas"),
        Campo("drive_vistos", "int", False, default=0, descricao="arquivos encontrados"),
        Campo("drive_abertos", "int", False, default=0, descricao="arquivos lidos"),
        Campo("whatsapp_vistos", "int", False, default=0, descricao="mensagens com palavra-chave no export"),
        Campo("whatsapp_abertos", "int", False, default=0, descricao="trechos enviados à leitura"),
        Campo(
            "whatsapp_status", "str", False, default="", descricao="ok, stale, nao_reconhecido, truncado ou sem_export"
        ),
        Campo("whatsapp_ultima_mensagem", "datetime", False, descricao="última mensagem do export"),
    ],
    "semana": [
        Campo("semana", "str", True, descricao="`AAAA-Www`"),
        Campo("mes", "str", True, descricao="`AAAA-MM` do plano de origem (mês da quinta-feira)"),
        Campo("gerado_em", "datetime", True, descricao="instante da geração do espelho"),
        Campo("run_id", "str", False, descricao="execução que gerou o espelho"),
    ],
    "dia": [
        Campo("data", "date", True, descricao="`AAAA-MM-DD`"),
        Campo("run_id", "str", True, descricao="execução que gerou"),
        Campo("resumo_confirmadas", "int", False, default=0, descricao="blocos confirmados desde o último dia"),
        Campo("resumo_presumidas", "int", False, default=0, descricao="blocos feita? (presumidos) ainda exibidos"),
        Campo("resumo_movidas", "int", False, default=0, descricao="blocos movidos ou reagendados"),
        Campo(
            "decisao_pendente",
            "str",
            False,
            descricao="`M<nn>` da meta com decisão pendente; ausente ou vazio = nenhuma",
        ),
        Campo("motivo", "str", False, descricao="`sem_janela` quando o dia não tem bloco; vazio caso contrário"),
    ],
    "task": [
        Campo("id", "str", True, descricao="`D-AAAA-MM-DD-<ss>`; a data é a do dia em que nasceu"),
        Campo("titulo", "str", True, descricao="título humano do bloco (sem `[GP]`), até 60 caracteres"),
        Campo("meta", "str", True, descricao="`M<nn>`"),
        Campo("semana", "str", True, descricao="`AAAA-Www` da seção do plano que o bloco serve"),
        Campo("inicio", "datetime", True, descricao="início planejado, hora local com offset"),
        Campo("fim", "datetime", True, descricao="fim planejado (> inicio)"),
        Campo("duracao_h", "float", True, descricao="horas planejadas (> 0)"),
        Campo(
            "porque", "str", False, default="", descricao="por que este bloco hoje (meta → semana), até 90 caracteres"
        ),
        Campo("efeito", "str", False, default="", descricao="`se feita: M3 41% → 44%`"),
        Campo("estado", "enum", True, ESTADOS, descricao="estado atual"),
        Campo("origem", "enum", True, ORIGENS, descricao="quem definiu o estado"),
        Campo(
            "calendar_event_id",
            "str",
            False,
            descricao="id do evento no Calendar (vem do `tool_result` do create_event)",
        ),
        Campo(
            "calendar_id",
            "str",
            False,
            descricao="calendário onde o evento está (Metas, ou o primário se o usuário o moveu)",
        ),
        Campo("duracao_real_h", "float", False, descricao="horas confirmadas pelo usuário no checkin"),
        Campo("atualizado_em", "datetime", False, descricao="última mudança de estado"),
    ],
    "registro": [
        Campo("schema_version", "int", True, descricao="versão do esquema (9.1)"),
        Campo("geracoes", "dict", False, default={}, descricao="run_id → `geracao` (8.1)"),
        Campo(
            "checkins",
            "dict",
            False,
            default={},
            descricao="task_id → `checkin` (último estado confirmado ou inferido)",
        ),
        Campo(
            "feitas",
            "dict",
            False,
            default={},
            descricao="`M<nn>` → lista de `feita`; só origem confirmado abate a demanda",
        ),
        Campo("progresso", "dict", False, default={}, descricao="`M<nn>` → lista de `progresso_declarado`"),
        Campo(
            "notas_recusadas",
            "list_dict",
            False,
            default=[],
            descricao="notas de aprendizado recusadas (não voltam por 30 dias)",
        ),
        Campo(
            "sentimentos",
            "dict",
            False,
            default={},
            descricao="`M<nn>` → lista de `sentimento` (como a pessoa está com a meta)",
        ),
        Campo(
            "respostas_email",
            "list",
            False,
            default=[],
            descricao="ids das respostas ao email das 7h já aplicadas como check-in (nunca o texto)",
        ),
    ],
    "geracao": [
        Campo("run_id", "str", True, descricao="mesmo id do log e da notificação"),
        Campo("modo", "str", True, descricao="diario, mensal, semanal, checkin, onboarding, ..."),
        Campo("data", "date", True, descricao="dia a que a execução se refere"),
        Campo("ts", "datetime", True, descricao="instante do fim da execução"),
        Campo("exit_code", "int", True, descricao="código de saída do job"),
        Campo("duracao_s", "float", False, descricao="duração de parede em segundos"),
        Campo("classe", "str", False, descricao="classe do erro, se houve"),
        Campo("chave_runbook", "str", False, descricao="seção do runbook no README"),
        Campo("mensagem", "str", False, descricao="texto da notificação, se houve erro (eng 2.3)"),
        Campo("tokens", "dict", False, default={}, descricao="input, cache_read, cache_creation, output"),
        Campo(
            "sessoes", "list", False, default=[], descricao="session_id de cada `claude -p` (retenção dos transcripts)"
        ),
        Campo("claude_version", "str", False, descricao="versão do `claude` usada"),
        Campo("email", "enum", False, EMAIL_STATUS, default="nao_enviado", descricao="resultado do envio"),
        Campo("hash_metas", "str", False, descricao="hash das metas na execução"),
        Campo(
            "teto_s",
            "float",
            False,
            descricao="teto de tempo do job nesta execução (20 ou 40 min, mais a espera de limite de uso)",
        ),
        Campo("espera_lock_s", "float", False, descricao="quanto o job esperou pelo lock da pasta de dados"),
        Campo(
            "alertas",
            "list",
            False,
            default=[],
            descricao="chaves dos alertas perto do limite vistos nesta execução (goalpacer/saude.py)",
        ),
        Campo("alerta_notificado", "str", False, descricao="chave do alerta que virou notificação nesta execução"),
    ],
    "checkin": [
        Campo("estado", "enum", True, ESTADOS, descricao="estado registrado"),
        Campo("origem", "enum", True, ORIGENS, descricao="quem definiu o estado"),
        Campo("ts", "datetime", True, descricao="instante do registro"),
        Campo("duracao_real_h", "float", False, descricao="horas confirmadas pelo usuário"),
        Campo("inicio", "datetime", False, descricao="nova janela quando movida/reagendada (do evento)"),
        Campo("fim", "datetime", False, descricao="fim da nova janela"),
        Campo("calendar_id", "str", False, descricao="calendário onde o evento está agora"),
        Campo("calendar_event_id", "str", False, descricao="id do evento encontrado"),
    ],
    "feita": [
        Campo("task_id", "str", True, descricao="`D-AAAA-MM-DD-<ss>`"),
        Campo("duracao_h", "float", True, descricao="horas planejadas do bloco (> 0)"),
        Campo("duracao_real_h", "float", False, descricao="horas confirmadas, quando informadas"),
        Campo("origem", "enum", True, ORIGENS, descricao="confirmado abate a demanda; presumido só é exibido"),
        Campo("ts", "datetime", False, descricao="instante do registro"),
    ],
    "progresso_declarado": [
        Campo("declarado_pct", "float", True, descricao="0 a 100, declarado pelo usuário"),
        Campo("ts", "datetime", True, descricao="instante da declaração"),
    ],
    "sentimento": [
        Campo("valor", "enum", True, SENTIMENTOS, descricao="energia, firme ou pesada"),
        Campo("ts", "datetime", True, descricao="instante da resposta no check-in"),
    ],
    "nota_recusada": [
        Campo("texto", "str", True, descricao="a nota proposta que o usuário recusou"),
        Campo("ts", "datetime", True, descricao="instante da recusa"),
    ],
    "perfil": [
        Campo("schema_version", "int", True, descricao="versão do esquema"),
        Campo("gerado_em", "datetime", True, descricao="instante da geração por perfil.py"),
        Campo("n_confirmadas", "int", False, default=0, descricao="observações com origem confirmado"),
        Campo("metas", "dict", False, default={}, descricao="`M<nn>` → `perfil_meta`"),
        Campo("janelas", "dict", False, default={}, descricao="`<dia>-<faixa>` → `perfil_janela` (ex.: seg-manha)"),
        Campo("preferencias", "dict", False, default={}, descricao="`perfil_preferencias` derivadas só de confirmadas"),
    ],
    "perfil_meta": [
        Campo(
            "progresso_pct",
            "float",
            False,
            default=0.0,
            descricao="max(horas confirmadas ÷ custo total, último declarado)",
        ),
        Campo(
            "progresso_presumido_pct",
            "float",
            False,
            default=0.0,
            descricao="presumidas dos últimos 14 dias ÷ custo total",
        ),
        Campo("ritmo_esperado_pct", "float", False, default=0.0, descricao="semanas decorridas ÷ semanas até o prazo"),
        Campo("delta", "float", False, default=0.0, descricao="progresso_pct − ritmo_esperado_pct (pode ser negativo)"),
        Campo("horas_confirmadas", "float", False, default=0.0, descricao="Σ duracao_h das feitas confirmadas"),
        Campo("horas_presumidas_nao_contadas", "float", False, default=0.0, descricao="presumidas com mais de 14 dias"),
        Campo(
            "fator_duracao",
            "float",
            False,
            default=1.0,
            descricao="mediana de duracao_real_h ÷ duracao_h (default 1,0)",
        ),
        Campo("h_semana_real", "float", False, default=0.0, descricao="média móvel de 4 semanas de horas confirmadas"),
    ],
    "perfil_janela": [
        Campo("taxa_conclusao", "float", True, descricao="0 a 1"),
        Campo("n", "int", True, descricao="observações confirmadas na célula (mínimo 5 para influenciar)"),
    ],
    "perfil_preferencias": [
        Campo("bloco_medio_h", "float", False, descricao="duração média dos blocos confirmados"),
        Campo("taxa_por_duracao", "dict", False, default={}, descricao="faixa de duração → taxa de conclusão"),
    ],
    "cache_calendar": [
        Campo("calendar_id_metas", "str", True, descricao="calendário Metas na geração (define a projeção)"),
        Campo("janela_inicio", "datetime", True, descricao="início do período lido"),
        Campo("janela_fim", "datetime", True, descricao="fim do período lido"),
        Campo("gerado_em", "datetime", True, descricao="instante da leitura"),
        Campo("run_id", "str", False, descricao="execução que leu"),
        Campo("calendarios", "list_dict", False, default=[], descricao="lista de `calendario` lidos"),
        Campo("eventos", "list_dict", False, default=[], descricao="lista de `evento` projetados"),
    ],
    "calendario": [
        Campo("id", "str", True, descricao="id do calendário (o primário tem o e-mail como id)"),
        Campo("summary", "str", False, default="", descricao="nome do calendário"),
        Campo("time_zone", "str", False, default="", descricao="fuso do calendário"),
    ],
    "evento": [
        Campo("id", "str", True, descricao="id do evento (instância expandida: `<base>_<ts>`)"),
        Campo("calendar_id", "str", True, descricao="calendário de origem"),
        Campo("start", "str", True, descricao="ISO com offset, ou `AAAA-MM-DD` se dia inteiro"),
        Campo("end", "str", True, descricao="ISO com offset, ou `AAAA-MM-DD` se dia inteiro"),
        Campo("all_day", "bool", False, default=False, descricao="true quando start é só data"),
        Campo("created", "datetime", False, descricao="criação no Google"),
        Campo("updated", "datetime", False, descricao="última alteração no Google"),
        Campo("status", "str", False, default="confirmed", descricao="confirmed, tentative ou cancelled"),
        Campo(
            "transparency", "str", False, default="opaque", descricao="transparent = livre; ausente no Google = ocupado"
        ),
        Campo(
            "self_response", "str", False, default="", descricao="attendees[].self.responseStatus; vazio = sem convite"
        ),
        Campo(
            "event_type", "str", False, default="", descricao="default, outOfOffice, workingLocation, fromGmail, ..."
        ),
        Campo("recurring_event_id", "str", False, default="", descricao="id da série, se instância recorrente"),
        Campo("summary", "str", False, descricao="só para eventos do Metas; null fora dele"),
        Campo("description", "str", False, descricao="só para eventos do Metas; null fora dele"),
        Campo("gp_key", "str", False, descricao="`gp:<task_id>/<instalacao_id>` da última linha da descrição, ou null"),
    ],
    "ops": [
        Campo("run_id", "str", True, descricao="execução que planejou as ops"),
        Campo("calendar_id_metas", "str", True, descricao="único calendário onde se cria"),
        Campo("gerado_em", "datetime", True, descricao="instante do planejamento"),
        Campo("ops", "list_dict", False, default=[], descricao="lista de `op` na ordem de execução"),
    ],
    "op": [
        Campo("op", "enum", True, OPS, descricao="create, update ou delete"),
        Campo("task_id", "str", True, descricao="bloco a que a op pertence"),
        Campo("calendar_id", "str", True, descricao="calendário alvo (create só no Metas)"),
        Campo("calendar_event_id", "str", False, descricao="obrigatório em update e delete"),
        Campo(
            "corpo",
            "dict",
            False,
            default={},
            descricao="argumentos do proxy (summary, description, start, end, timeZone, ...)",
        ),
        Campo(
            "status",
            "enum",
            False,
            STATUS_OP,
            descricao="ok ou erro depois de executar; ausente = não rodou (= falhou)",
        ),
        Campo("mensagem", "str", False, descricao="texto do erro do conector, quando status = erro"),
        Campo("event_id_resultado", "str", False, descricao="id devolvido pelo create_event"),
    ],
    "rascunho_onboarding": [
        Campo("versao", "int", True, descricao="versão do formato do rascunho"),
        Campo("atualizado_em", "datetime", True, descricao="última resposta gravada"),
        Campo("respostas", "dict", False, default={}, descricao="respostas coletadas até aqui (livre)"),
    ],
}


class RegraDict(NamedTuple):
    """Como validar um campo ``dict``.

    Exatamente um de: ``valor_tipo`` (mapa chave → escalar de ``TIPOS``),
    ``valor_esquema`` (mapa chave → objeto de ``ESQUEMAS``),
    ``valor_lista_esquema`` (mapa chave → lista de objetos de ``ESQUEMAS``),
    ``objeto_esquema`` (o próprio dict é um objeto de ``ESQUEMAS``) ou
    ``livre`` (qualquer conteúdo com chaves str). ``chave_formato`` é uma
    chave de ``REGEX_POR_FORMATO`` (só para mapas); ``campo_chave`` é o
    campo do valor que deve repetir a chave.
    """

    chave_formato: Optional[str] = None
    valor_tipo: Optional[str] = None
    valor_esquema: Optional[str] = None
    valor_lista_esquema: Optional[str] = None
    objeto_esquema: Optional[str] = None
    livre: bool = False
    campo_chave: Optional[str] = None


REGRAS_DICT: dict[tuple[str, str], RegraDict] = {
    ("registro", "geracoes"): RegraDict(None, valor_esquema="geracao", campo_chave="run_id"),
    ("registro", "checkins"): RegraDict("task", valor_esquema="checkin"),
    ("registro", "feitas"): RegraDict("meta", valor_lista_esquema="feita"),
    ("registro", "progresso"): RegraDict("meta", valor_lista_esquema="progresso_declarado"),
    ("registro", "sentimentos"): RegraDict("meta", valor_lista_esquema="sentimento"),
    ("geracao", "tokens"): RegraDict(None, valor_tipo="int"),
    ("perfil", "metas"): RegraDict("meta", valor_esquema="perfil_meta"),
    ("perfil", "janelas"): RegraDict("janela_perfil", valor_esquema="perfil_janela"),
    ("perfil", "preferencias"): RegraDict(None, objeto_esquema="perfil_preferencias"),
    ("perfil_preferencias", "taxa_por_duracao"): RegraDict(None, valor_tipo="float"),
    ("op", "corpo"): RegraDict(None, livre=True),
    ("rascunho_onboarding", "respostas"): RegraDict(None, livre=True),
}

# (arquivo, campo list_dict) → esquema de cada item.
REGRAS_LISTA: dict[tuple[str, str], str] = {
    ("registro", "notas_recusadas"): "nota_recusada",
    ("cache_calendar", "calendarios"): "calendario",
    ("cache_calendar", "eventos"): "evento",
    ("ops", "ops"): "op",
}

# (arquivo, campo) → formato de string exigido (chave de REGEX_POR_FORMATO).
# String vazia em campo opcional escapa da checagem.
FORMATOS: dict[tuple[str, str], str] = {
    ("metas", "id"): "meta",
    ("metas", "objetivo"): "objetivo",
    ("objetivo", "id"): "objetivo",
    ("fonte_pesquisa", "id"): "meta",
    ("contexto", "instalacao_id"): "instalacao_id",
    ("contexto", "email_proprio"): "email",
    ("contexto", "horario_util_seg_sex"): "horario_util",
    ("contexto", "horario_util_sab"): "horario_util",
    ("contexto", "horario_util_dom"): "horario_util",
    ("plano", "mes"): "mes",
    ("sinais", "whatsapp_status"): "status_whatsapp",
    ("semana", "semana"): "semana",
    ("semana", "mes"): "mes",
    ("dia", "decisao_pendente"): "meta",
    ("task", "id"): "task",
    ("task", "meta"): "meta",
    ("task", "semana"): "semana",
    ("feita", "task_id"): "task",
    ("evento", "gp_key"): "gp_key",
    ("op", "task_id"): "task",
}

# Todo int/float do esquema é >= 0 salvo CAMPOS_NEGATIVOS_OK; estes precisam ser > 0.
CAMPOS_POSITIVOS = ("custo_h_semana_escolhido", "custo_h_semana_max", "semanas_pesquisa", "duracao_h")
CAMPOS_NEGATIVOS_OK = ("delta",)
FAIXAS = {"declarado_pct": (0, 100), "taxa_conclusao": (0, 1)}
# (arquivo, campo) → tamanho máximo do texto.
TETOS_TEXTO = {("task", "porque"): TETO_PORQUE_CHARS, ("task", "titulo"): 60}

# Seções fixas, na ordem em que render.py escreve e validar.py confere.
# "<dia>" é um espaço reservado (ex.: "## Desde sáb"); ver casa_secao.
SECOES = {
    "dia": ("## Hoje", "## Desde <dia>", "## Progresso", "## Avisos"),
    "plano": ("## Balanço", "## Metas", "## Semanas", "## Evidências", "## Decisões"),
}
SECOES_CONDICIONAIS = {
    "dia": ("## Desde <dia>", "## Avisos"),
    "plano": ("## Evidências", "## Decisões"),
}

# Subseções: "### M<nn> <título>" em "## Metas" e "### AAAA-Www" em
# "## Semanas" do plano (design 7.1); "### D-AAAA-MM-DD-<ss> <título>" é um
# bloco em "## Hoje" de dias/ (os campos do bloco vêm em linhas
# "- chave: valor" logo abaixo, no mesmo subconjunto do front-matter).
RE_SUBSECAO_META = re.compile(r"^### (M[0-9]{2})(?: (.+))?\Z")
RE_SUBSECAO_SEMANA = re.compile(r"^### ([0-9]{4}-W(?:0[1-9]|[1-4][0-9]|5[0-3]))\Z")
RE_SUBSECAO_TASK = re.compile(r"^### (D-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2})(?: (.+))?\Z")
RE_LINHA_CAMPO_BLOCO = re.compile(r"^- ([a-z][a-z0-9_]*): ?(.*)\Z")
SUBSECOES = {
    "plano": {"## Metas": RE_SUBSECAO_META, "## Semanas": RE_SUBSECAO_SEMANA},
    "dia": {"## Hoje": RE_SUBSECAO_TASK},
}
RE_ESPACO_RESERVADO = re.compile(r"<([a-z_]+)>")

# Blocos de prosa que o modelo preenche (2.5); um bloco abre com
# "<!-- prosa:nome -->" e fecha com "<!-- /prosa:nome -->"; "atualizar"
# marca um bloco para regeneração (D4.12).
MARCADORES_PROSA = ("<!-- prosa:marcos -->", "<!-- prosa:atualizar -->")
RE_MARCADOR_PROSA = re.compile(r"<!-- prosa:([a-z][a-z0-9_]*) -->")
RE_MARCADOR_PROSA_FIM = re.compile(r"<!-- /prosa:([a-z][a-z0-9_]*) -->")
RE_BLOCO_PROSA = re.compile(r"(<!-- prosa:([a-z][a-z0-9_]*) -->)(.*?)(<!-- /prosa:\2 -->)", re.DOTALL)
MARCADOR_ATUALIZAR = "<!-- prosa:atualizar -->"
RE_EVIDENCIA_SINAL = re.compile(r"^- evidencia: ([0-9]{4}-[0-9]{2}-[0-9]{2}) (gmail|whatsapp|notion|drive): (.+)\Z")

MARCADOR_MD_INICIO = "<!-- schema:inicio -->"
MARCADOR_MD_FIM = "<!-- schema:fim -->"


def _esquema(arquivo: str) -> list[Campo]:
    if arquivo not in ESQUEMAS:
        raise GpErro(EXIT_VALIDACAO, "arquivo desconhecido no esquema: %r" % (arquivo,))
    return ESQUEMAS[arquivo]


def validar_id(tipo: str, valor: Any) -> bool:
    """True se ``valor`` é uma string que casa a regex do ``tipo``.

    ``tipo`` é uma chave de ``REGEX_POR_TIPO_ID``; tipo desconhecido é
    ``GpErro(EXIT_VALIDACAO)``.
    """
    if tipo not in REGEX_POR_TIPO_ID:
        raise GpErro(EXIT_VALIDACAO, "tipo de id desconhecido: %r" % (tipo,))
    return isinstance(valor, str) and REGEX_POR_TIPO_ID[tipo].fullmatch(valor) is not None


def _nome_tipo(valor: Any) -> str:
    """Nome do tipo de ``valor`` no vocabulário do esquema."""
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "bool"
    if isinstance(valor, datetime):
        return "datetime"
    if isinstance(valor, date):
        return "date"
    return type(valor).__name__


def _parse_date(texto: str) -> Optional[date]:
    if RE_DIA_ID.fullmatch(texto) is None:
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _parse_datetime(texto: str) -> Optional[datetime]:
    """``datetime`` de uma string ISO com data e hora (via
    ``clock.normalizar_iso``); None se inválida ou só data."""
    try:
        normalizado = clock.normalizar_iso(texto)
    except GpErro:
        return None
    if len(normalizado) <= 10:
        return None
    try:
        return datetime.fromisoformat(normalizado)
    except ValueError:
        return None


def _nao_finito(valor: Any) -> bool:
    """True para NaN/Infinity (int nunca é)."""
    return isinstance(valor, float) and not math.isfinite(valor)


def _janela_invertida(valor: str) -> bool:
    """True se ``HH:MM-HH:MM`` (já validado pela regex) não tem fim depois do início."""
    inicio, fim = valor.split("-")
    return fim <= inicio


def _como_datetime(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str):
        return _parse_datetime(valor)
    return None


def _validar_tipo(campo: Campo, valor: Any) -> Optional[str]:
    """Motivo do erro de tipo/enum de ``valor`` para ``campo``, ou None."""
    conferir = CONFERENCIA_DE_TIPO.get(campo.tipo)
    if conferir is None:
        raise GpErro(EXIT_VALIDACAO, "tipo desconhecido no esquema: %r" % (campo.tipo,))
    return conferir(campo, valor)


def _esperado(tipo: str, valor: Any) -> str:
    return "esperado %s, veio %s" % (tipo, _nome_tipo(valor))


def _tipo_str(_campo: Campo, valor: Any) -> Optional[str]:
    return None if isinstance(valor, str) else _esperado("str", valor)


def _tipo_int(_campo: Campo, valor: Any) -> Optional[str]:
    return None if isinstance(valor, int) and not isinstance(valor, bool) else _esperado("int", valor)


def _tipo_float(_campo: Campo, valor: Any) -> Optional[str]:
    return None if isinstance(valor, (int, float)) and not isinstance(valor, bool) else _esperado("float", valor)


def _tipo_bool(_campo: Campo, valor: Any) -> Optional[str]:
    return None if isinstance(valor, bool) else _esperado("bool", valor)


def _tipo_date(_campo: Campo, valor: Any) -> Optional[str]:
    if isinstance(valor, datetime):
        return "esperado date, veio datetime"
    if isinstance(valor, str):
        return "data inválida (AAAA-MM-DD): %r" % (valor,) if _parse_date(valor) is None else None
    return None if isinstance(valor, date) else _esperado("date", valor)


def _tipo_datetime(_campo: Campo, valor: Any) -> Optional[str]:
    if isinstance(valor, str):
        return "datetime inválido (ISO 8601 com hora): %r" % (valor,) if _parse_datetime(valor) is None else None
    return None if isinstance(valor, datetime) else _esperado("datetime", valor)


def _tipo_list(campo: Campo, valor: Any) -> Optional[str]:
    if not isinstance(valor, list):
        return _esperado("list", valor)
    for item in valor:
        if not isinstance(item, str):
            return "item %r não é str" % (item,)
        if campo.enum is not None and item not in campo.enum:
            return "item %r fora de %s" % (item, ", ".join(campo.enum))
    return "itens repetidos" if len(set(valor)) != len(valor) else None


def _tipo_enum(campo: Campo, valor: Any) -> Optional[str]:
    if not isinstance(valor, str):
        return _esperado("str", valor)
    if campo.enum is None or valor not in campo.enum:
        return "%r fora de %s" % (valor, ", ".join(campo.enum or ()))
    return None


def _tipo_dict(_campo: Campo, valor: Any) -> Optional[str]:
    if not isinstance(valor, dict):
        return _esperado("dict", valor)
    return next(("chave %r não é str" % (chave,) for chave in valor if not isinstance(chave, str)), None)


def _tipo_list_dict(_campo: Campo, valor: Any) -> Optional[str]:
    return None if isinstance(valor, list) else _esperado("list", valor)


# Um ramo por tipo do esquema (TIPOS); verificar_esquemas confere que as duas listas andam juntas.
CONFERENCIA_DE_TIPO: dict[str, Callable[[Campo, Any], Optional[str]]] = {
    "str": _tipo_str,
    "int": _tipo_int,
    "float": _tipo_float,
    "bool": _tipo_bool,
    "date": _tipo_date,
    "datetime": _tipo_datetime,
    "list": _tipo_list,
    "enum": _tipo_enum,
    "dict": _tipo_dict,
    "list_dict": _tipo_list_dict,
}


def _validar_regras(arquivo: str, campo: Campo, valor: Any) -> list[str]:
    """Regras além do tipo: string vazia, formato, faixas numéricas, tetos."""
    if campo.tipo == "str":
        return _regras_de_texto(arquivo, campo, valor)
    if campo.tipo in ("int", "float"):
        return _regras_de_numero(campo, valor)
    if campo.tipo == "list" and campo.nome == "palavras_chave" and len(valor) > TETO_PALAVRAS_CHAVE:
        return ["no máximo %d itens" % TETO_PALAVRAS_CHAVE]
    return []


def _regras_de_texto(arquivo: str, campo: Campo, valor: str) -> list[str]:
    motivos: list[str] = []
    if campo.obrigatorio and not valor.strip():
        motivos.append("vazio")
    formato = FORMATOS.get((arquivo, campo.nome))
    if formato is not None and valor and REGEX_POR_FORMATO[formato].fullmatch(valor) is None:
        motivos.append("%r não tem o formato %s" % (valor, formato))
    if formato == "horario_util" and valor and not motivos and _janela_invertida(valor):
        motivos.append("fim deve ser depois do início")
    teto = TETOS_TEXTO.get((arquivo, campo.nome))
    if teto is not None and len(valor) > teto:
        motivos.append("no máximo %d caracteres" % teto)
    return motivos


def _regras_de_numero(campo: Campo, valor: float) -> list[str]:
    if _nao_finito(valor):
        return ["não é número finito"]
    motivos: list[str] = []
    if campo.nome in CAMPOS_POSITIVOS:
        if valor <= 0:
            motivos.append("deve ser > 0")
    elif valor < 0 and campo.nome not in CAMPOS_NEGATIVOS_OK:
        motivos.append("não pode ser negativo")
    faixa = FAIXAS.get(campo.nome)
    if faixa is not None and not (faixa[0] <= valor <= faixa[1]):
        motivos.append("fora de %s a %s" % faixa)
    return motivos


def _validar_escalar_mapa(regra: RegraDict, sub: str, item: Any) -> list[str]:
    motivo = _validar_tipo(Campo(sub, regra.valor_tipo or "str"), item)
    if motivo is not None:
        return ["%s: %s" % (sub, motivo)]
    if regra.valor_tipo in ("int", "float"):
        if _nao_finito(item):
            return ["%s: não é número finito" % sub]
        if item < 0:
            return ["%s: não pode ser negativo" % sub]
    return []


def _validar_objeto(esquema: str, sub: str, item: Any) -> list[str]:
    if not isinstance(item, dict):
        return ["%s: esperado dict, veio %s" % (sub, _nome_tipo(item))]
    return _validar(esquema, item, sub + ".")


def _validar_dict(arquivo: str, campo: Campo, valor: dict, rotulo: str) -> list[str]:
    """Erros das chaves e dos valores de um campo ``dict`` com regra."""
    regra = REGRAS_DICT.get((arquivo, campo.nome))
    if regra is None or regra.livre:
        return []
    if regra.objeto_esquema is not None:
        return _validar(regra.objeto_esquema, valor, rotulo + ".")
    erros: list[str] = []
    for chave in sorted(valor):
        sub = "%s.%s" % (rotulo, chave)
        if regra.chave_formato is not None and REGEX_POR_FORMATO[regra.chave_formato].fullmatch(chave) is None:
            erros.append("%s: chave não tem o formato %s" % (sub, regra.chave_formato))
        erros.extend(_erros_do_valor(regra, sub, chave, valor[chave]))
    return erros


def _erros_do_valor(regra: RegraDict, sub: str, chave: str, item: Any) -> list[str]:
    """Um valor do mapa: objeto de um esquema (com a chave espelhada), lista de objetos ou escalar."""
    if regra.valor_esquema is not None:
        erros = _validar_objeto(regra.valor_esquema, sub, item)
        espelho = regra.campo_chave
        if not erros and espelho is not None and espelho in item and item[espelho] != chave:
            erros.append("%s.%s: difere da chave %r" % (sub, espelho, chave))
        return erros
    if regra.valor_lista_esquema is not None:
        if not isinstance(item, list):
            return ["%s: esperado list, veio %s" % (sub, _nome_tipo(item))]
        esquema = regra.valor_lista_esquema
        return [e for i, elemento in enumerate(item) for e in _validar_objeto(esquema, "%s[%d]" % (sub, i), elemento)]
    return _validar_escalar_mapa(regra, sub, item)


def _validar_lista(arquivo: str, campo: Campo, valor: list, rotulo: str) -> list[str]:
    """Erros dos itens de um campo ``list_dict``."""
    esquema = REGRAS_LISTA.get((arquivo, campo.nome))
    if esquema is None:
        return []
    erros: list[str] = []
    for i, item in enumerate(valor):
        erros.extend(_validar_objeto(esquema, "%s[%d]" % (rotulo, i), item))
    return erros


def _regras_cruzadas(arquivo: str, dados: dict[str, Any], prefixo: str) -> list[str]:
    """Regras que envolvem mais de um campo do mesmo arquivo."""
    regra = REGRAS_CRUZADAS.get(arquivo)
    return regra(dados, prefixo) if regra else []


def _cruzadas_task(dados: dict[str, Any], prefixo: str) -> list[str]:
    inicio, fim = _como_datetime(dados.get("inicio")), _como_datetime(dados.get("fim"))
    if inicio is None or fim is None:
        return []
    try:
        return ["%sfim: deve ser depois de inicio" % prefixo] if fim <= inicio else []
    except TypeError:
        return ["%sfim: inicio e fim precisam ter o mesmo tipo de fuso" % prefixo]


def _cruzadas_metas(dados: dict[str, Any], prefixo: str) -> list[str]:
    minimo, maximo = dados.get("custo_h_semana_min"), dados.get("custo_h_semana_max")
    numeros = (
        isinstance(minimo, (int, float))
        and isinstance(maximo, (int, float))
        and not isinstance(minimo, bool)
        and math.isfinite(minimo)
        and math.isfinite(maximo)
    )
    return ["%scusto_h_semana_min: maior que custo_h_semana_max" % prefixo] if numeros and minimo > maximo else []


def _cruzadas_evento(dados: dict[str, Any], prefixo: str) -> list[str]:
    erros = []
    for nome in ("start", "end"):
        valor = dados.get(nome)
        if not isinstance(valor, str) or not valor:
            continue
        eh_data = _parse_date(valor) is not None
        if not eh_data and _parse_datetime(valor) is None:
            erros.append("%s%s: nem data AAAA-MM-DD nem datetime ISO: %r" % (prefixo, nome, valor))
        elif nome == "start" and bool(dados.get("all_day", False)) != eh_data:
            erros.append(
                "%sall_day: deve ser %s quando start é %s"
                % (prefixo, "true" if eh_data else "false", "só data" if eh_data else "datetime")
            )
    return erros


def _cruzadas_op(dados: dict[str, Any], prefixo: str) -> list[str]:
    if dados.get("op") in ("update", "delete") and not dados.get("calendar_event_id"):
        return ["%scalendar_event_id: obrigatório em update e delete" % prefixo]
    return []


def _cruzadas_ops(dados: dict[str, Any], prefixo: str) -> list[str]:
    metas = dados.get("calendar_id_metas")
    return [
        "%sops[%d].calendar_id: create só no calendário Metas" % (prefixo, i)
        for i, op in enumerate(dados.get("ops") or [])
        if isinstance(op, dict)
        and op.get("op") == "create"
        and isinstance(metas, str)
        and op.get("calendar_id") != metas
    ]


def _cruzadas_cache_calendar(dados: dict[str, Any], prefixo: str) -> list[str]:
    metas = dados.get("calendar_id_metas")
    if not isinstance(metas, str):
        return []
    return [
        "%seventos[%d].%s: deve ser null fora do calendário Metas" % (prefixo, i, nome)
        for i, evento in enumerate(dados.get("eventos") or [])
        if isinstance(evento, dict) and evento.get("calendar_id") != metas
        for nome in CAMPOS_SO_DO_METAS
        if evento.get(nome) is not None
    ]


REGRAS_CRUZADAS: dict[str, Callable[[dict[str, Any], str], list[str]]] = {
    "task": _cruzadas_task,
    "metas": _cruzadas_metas,
    "evento": _cruzadas_evento,
    "op": _cruzadas_op,
    "ops": _cruzadas_ops,
    "cache_calendar": _cruzadas_cache_calendar,
}


def _validar(arquivo: str, dados: dict[str, Any], prefixo: str) -> list[str]:
    erros: list[str] = []
    campos = _esquema(arquivo)
    for campo in campos:
        erros.extend(_erros_do_campo(arquivo, campo, dados.get(campo.nome), prefixo + campo.nome))
    nomes = {campo.nome for campo in campos}
    erros.extend(
        "%s%s: campo desconhecido em %s" % (prefixo, chave, arquivo)
        for chave in sorted(str(k) for k in dados if k not in nomes)
    )
    versao = dados.get("schema_version")
    numero = isinstance(versao, int) and not isinstance(versao, bool)
    if "schema_version" in nomes and numero and versao != SCHEMA_VERSION:
        erros.append("%sschema_version: esperado %d, veio %d" % (prefixo, SCHEMA_VERSION, versao))
    erros.extend(_regras_cruzadas(arquivo, dados, prefixo))
    return erros


def _erros_do_campo(arquivo: str, campo: Campo, valor: Any, rotulo: str) -> list[str]:
    """Obrigatório, tipo, regras e o conteúdo de ``dict``/``list_dict``; tipo errado para as outras checagens."""
    if valor is None:
        return ["%s: obrigatório" % rotulo] if campo.obrigatorio else []
    motivo = _validar_tipo(campo, valor)
    if motivo is not None:
        return ["%s: %s" % (rotulo, motivo)]
    erros = ["%s: %s" % (rotulo, m) for m in _validar_regras(arquivo, campo, valor)]
    if campo.tipo == "dict":
        erros.extend(_validar_dict(arquivo, campo, valor, rotulo))
    elif campo.tipo == "list_dict":
        erros.extend(_validar_lista(arquivo, campo, valor, rotulo))
    return erros


def validar_registro(arquivo: str, dados: dict[str, Any]) -> list[str]:
    """Valida ``dados`` contra ``ESQUEMAS[arquivo]``.

    Confere obrigatórios (``None`` conta como ausente), tipos, enums (valor
    ou itens de lista), formatos (ids, ``HH:MM-HH:MM``, e-mail, ``gp_key``),
    faixas numéricas, tetos de texto e de ``palavras_chave``,
    ``schema_version``, campos desconhecidos, os campos ``dict`` e
    ``list_dict`` com regra (``registro.geracoes`` valida cada geração como
    ``geracoes.<run_id>.<campo>``; listas como ``eventos[3].start``) e as
    regras cruzadas (``fim > inicio``, ``min <= max``, ``all_day`` × ``start``,
    ``update``/``delete`` com ``calendar_event_id``, ``create`` só no Metas,
    ``summary``/``description`` nulos fora do Metas). Devolve erros
    ``"campo: motivo"`` em ordem determinística (vazio = ok); ``arquivo``
    desconhecido é ``GpErro(EXIT_VALIDACAO)``.
    """
    _esquema(arquivo)
    if not isinstance(dados, dict):
        return ["(raiz): esperado dict, veio %s" % _nome_tipo(dados)]
    return _validar(arquivo, dados, "")


def defaults(arquivo: str) -> dict[str, Any]:
    """Dict com os defaults dos campos opcionais de ``arquivo`` que têm
    default (cópias novas de listas e dicts); ``arquivo`` desconhecido é
    ``GpErro(EXIT_VALIDACAO)``."""
    return {
        campo.nome: copy.deepcopy(campo.default)
        for campo in _esquema(arquivo)
        if not campo.obrigatorio and campo.default is not None
    }


def campos_hash(arquivo: str = "metas") -> list[str]:
    """Nomes dos campos de ``arquivo`` que entram no ``hash_metas`` (sem
    ``no_hash``), na ordem do esquema."""
    return [campo.nome for campo in _esquema(arquivo) if not campo.no_hash]


def _valor_para_hash(valor: Any) -> Any:
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def hash_metas(metas: Iterable[dict[str, Any]]) -> str:
    """Hash curto e determinístico das metas: só ``campos_hash("metas")``
    (``id`` como chave de ordenação e ``titulo``, ``horizonte``, ``prazo``,
    ``prazo_externo``), ordenadas por ``id``; custo, estado, confiança e
    palavras-chave não mudam o valor. Meta nova ou removida muda."""
    itens = [{nome: _valor_para_hash(meta.get(nome)) for nome in campos_hash("metas")} for meta in metas]
    itens.sort(key=lambda item: str(item.get("id")))
    texto = json.dumps(itens, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:HASH_METAS_TAMANHO]


PESQUISA_CAMPOS = ("titulo", "horizonte", "prazo")


def hash_meta_pesquisa(meta: dict[str, Any]) -> str:
    """Hash curto de ``titulo``, ``horizonte`` e ``prazo`` de UMA meta: gravado
    em ``fontes/M<nn>.md`` (``hash_meta``); diferente do atual = a pesquisa
    fica ``pendente`` (design doc: validade de ``fontes/``)."""
    itens = {nome: _valor_para_hash(meta.get(nome)) for nome in PESQUISA_CAMPOS}
    texto = json.dumps(itens, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:HASH_METAS_TAMANHO]


def titulo_secao(modelo: str, **valores: str) -> str:
    """Preenche os espaços reservados de um título de seção: ``titulo_secao("##
    Desde <dia>", dia="sáb")`` → ``"## Desde sáb"``. Espaço sem valor é
    ``KeyError``."""
    return RE_ESPACO_RESERVADO.sub(lambda m: valores[m.group(1)], modelo)


def casa_secao(modelo: str, linha: str) -> bool:
    """True se ``linha`` é o título ``modelo`` com os espaços reservados
    preenchidos por texto não vazio."""
    padrao = "".join(
        ".+" if i % 2 else re.escape(parte)
        for i, parte in enumerate(RE_ESPACO_RESERVADO.split(modelo))
        if i % 2 or parte
    )
    return re.fullmatch(padrao, linha.rstrip("\n")) is not None


def _regra_valida(regra: RegraDict) -> bool:
    modos = (
        regra.valor_tipo is not None,
        regra.valor_esquema is not None,
        regra.valor_lista_esquema is not None,
        regra.objeto_esquema is not None,
        regra.livre,
    )
    return sum(1 for m in modos if m) == 1


def verificar_esquemas() -> list[str]:
    """Consistência interna das tabelas declarativas (teste e ``--md``)."""
    erros: list[str] = []
    if set(CONFERENCIA_DE_TIPO) != set(TIPOS):
        erros.append("CONFERENCIA_DE_TIPO: tipos diferentes de TIPOS")
    for arquivo, campos in ESQUEMAS.items():
        erros.extend(_problemas_do_esquema(arquivo, campos))
    for (arquivo, nome), regra in REGRAS_DICT.items():
        erros.extend(
            "REGRAS_DICT %s.%s: %s" % (arquivo, nome, m) for m in _problemas_da_regra_dict(arquivo, nome, regra)
        )
    erros.extend(_problemas_das_tabelas_de_campo())
    erros.extend(
        "SECOES_CONDICIONAIS %s: %r não está em SECOES" % (arquivo, secao)
        for arquivo, secoes in SECOES.items()
        for secao in SECOES_CONDICIONAIS.get(arquivo, ())
        if secao not in secoes
    )
    erros.extend(
        "HASH_METAS_CAMPOS: %s está marcado no_hash" % nome
        for nome in HASH_METAS_CAMPOS
        if nome not in campos_hash("metas")
    )
    return erros


def _problemas_do_esquema(arquivo: str, campos: list[Campo]) -> list[str]:
    erros = [] if arquivo in CAMINHOS else ["%s: sem caminho em CAMINHOS" % arquivo]
    vistos: set[str] = set()
    for campo in campos:
        if campo.nome in vistos:
            erros.append("%s.%s: repetido" % (arquivo, campo.nome))
        vistos.add(campo.nome)
        erros.extend("%s.%s: %s" % (arquivo, campo.nome, m) for m in _problemas_do_campo(arquivo, campo))
    return erros


def _problemas_das_tabelas_de_campo() -> list[str]:
    """REGRAS_LISTA, FORMATOS e TETOS_TEXTO apontam para campos que existem, com o tipo certo."""
    erros = []
    for (arquivo, nome), esquema in REGRAS_LISTA.items():
        if not _tem_campo(arquivo, nome, "list_dict"):
            erros.append("REGRAS_LISTA %s.%s: não é campo list_dict" % (arquivo, nome))
        if esquema not in ESQUEMAS:
            erros.append("REGRAS_LISTA %s.%s: esquema desconhecido %r" % (arquivo, nome, esquema))
    for (arquivo, nome), formato in FORMATOS.items():
        if not _tem_campo(arquivo, nome, "str"):
            erros.append("FORMATOS %s.%s: não é campo str" % (arquivo, nome))
        if formato not in REGEX_POR_FORMATO:
            erros.append("FORMATOS %s.%s: formato desconhecido" % (arquivo, nome))
    erros.extend(
        "TETOS_TEXTO %s.%s: não é campo str" % (arquivo, nome)
        for arquivo, nome in TETOS_TEXTO
        if not _tem_campo(arquivo, nome, "str")
    )
    return erros


def _tem_campo(arquivo: str, nome: str, tipo: str) -> bool:
    return any(c.nome == nome and c.tipo == tipo for c in ESQUEMAS.get(arquivo, []))


def _problemas_do_campo(arquivo: str, campo: Campo) -> list[str]:
    """O que está errado na declaração de um campo, na ordem em que o verificar sempre listou."""
    checagens = (
        (RE_NOME_CAMPO.fullmatch(campo.nome) is None, "nome inválido para front-matter"),
        (campo.tipo not in TIPOS, "tipo desconhecido %r" % (campo.tipo,)),
        (
            arquivo in ARQUIVOS_FRONTMATTER and campo.tipo in ("dict", "list_dict"),
            "%s não cabe em front-matter plano" % campo.tipo,
        ),
        (campo.tipo == "enum" and not campo.enum, "enum sem valores"),
        (campo.enum is not None and campo.tipo not in ("enum", "list"), "enum só vale para enum ou list"),
        (campo.enum is not None and len(set(campo.enum)) != len(campo.enum), "enum com valores repetidos"),
        (campo.obrigatorio and campo.default is not None, "obrigatório não tem default"),
    )
    problemas = [motivo for falhou, motivo in checagens if falhou]
    if campo.default is not None and campo.tipo in TIPOS:
        motivo = _validar_tipo(campo, campo.default)
        if motivo is not None:
            problemas.append("default inválido (%s)" % motivo)
    if campo.tipo == "dict" and (arquivo, campo.nome) not in REGRAS_DICT:
        problemas.append("dict sem regra em REGRAS_DICT")
    if campo.tipo == "list_dict" and (arquivo, campo.nome) not in REGRAS_LISTA:
        problemas.append("list_dict sem esquema em REGRAS_LISTA")
    return problemas


def _problemas_da_regra_dict(arquivo: str, nome: str, regra: RegraDict) -> list[str]:
    checagens = (
        (not _tem_campo(arquivo, nome, "dict"), "não é campo dict"),
        (
            regra.chave_formato is not None and regra.chave_formato not in REGEX_POR_FORMATO,
            "formato de chave desconhecido",
        ),
        (
            not _regra_valida(regra),
            "exatamente um modo (valor_tipo, valor_esquema, valor_lista_esquema, objeto_esquema, livre)",
        ),
        (regra.valor_tipo is not None and regra.valor_tipo not in TIPOS, "valor_tipo desconhecido"),
    )
    problemas = [motivo for falhou, motivo in checagens if falhou]
    problemas.extend(
        "esquema desconhecido %r" % (esquema,)
        for esquema in (regra.valor_esquema, regra.valor_lista_esquema, regra.objeto_esquema)
        if esquema is not None and esquema not in ESQUEMAS
    )
    if regra.objeto_esquema is not None and regra.chave_formato is not None:
        problemas.append("objeto não tem formato de chave")
    return problemas


def _celula(texto: str) -> str:
    """Texto seguro para uma célula de tabela markdown."""
    return " ".join(str(texto).split()).replace("|", "\\|")


def _formatar_valor(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, str):
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, list):
        return "[%s]" % ", ".join(_formatar_valor(item) for item in valor)
    if isinstance(valor, dict):
        return "{}" if not valor else json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return str(valor)


def _descricao_regra(arquivo: str, campo: Campo) -> str:
    """Texto da coluna enum/default para dict e list_dict."""
    if campo.tipo == "list_dict":
        return "itens: `%s`" % REGRAS_LISTA.get((arquivo, campo.nome), "?")
    regra = REGRAS_DICT.get((arquivo, campo.nome))
    if regra is None:
        return ""
    if regra.livre:
        return "conteúdo livre"
    if regra.objeto_esquema is not None:
        return "objeto `%s`" % regra.objeto_esquema
    chave = "chave: %s" % regra.chave_formato if regra.chave_formato else "chave: texto"
    if regra.valor_tipo is not None:
        return "%s; valor: %s" % (chave, regra.valor_tipo)
    if regra.valor_esquema is not None:
        return "%s; valor: `%s`" % (chave, regra.valor_esquema)
    return "%s; valor: lista de `%s`" % (chave, regra.valor_lista_esquema)


def _enum_default(arquivo: str, campo: Campo) -> str:
    partes = []
    if campo.enum is not None:
        rotulo = "itens" if campo.tipo == "list" else "enum"
        partes.append("%s: %s" % (rotulo, ", ".join(campo.enum)))
    regra = _descricao_regra(arquivo, campo)
    if regra:
        partes.append(regra)
    if campo.default is not None:
        partes.append("default: %s" % _formatar_valor(campo.default))
    formato = FORMATOS.get((arquivo, campo.nome))
    if formato is not None:
        partes.append("formato: %s" % formato)
    return "; ".join(partes)


def gerar_md() -> str:
    """Seção de esquemas de ``references/dados.md``, determinística.

    Entre ``MARCADOR_MD_INICIO`` e ``MARCADOR_MD_FIM``: uma tabela por
    arquivo (campo | tipo | obrigatório | enum/default | descrição), mais
    estados, origens, transições proibidas, ids, seções e marcadores.
    """
    linhas = [
        MARCADOR_MD_INICIO,
        "",
        "Gerado por `python3 -m goalpacer.schema --md`; não edite à mão. `schema_version`: %d." % SCHEMA_VERSION,
        "",
    ]
    for arquivo, campos in ESQUEMAS.items():
        linhas.append("### `%s` (`%s`)" % (arquivo, CAMINHOS[arquivo]))
        linhas.append("")
        linhas.append("| campo | tipo | obrigatório | enum/default | descrição |")
        linhas.append("|---|---|---|---|---|")
        for campo in campos:
            descricao = campo.descricao
            if campo.no_hash:
                descricao += " (fora do `hash_metas`)"
            linhas.append(
                "| %s | %s | %s | %s | %s |"
                % (
                    _celula(campo.nome),
                    campo.tipo,
                    "sim" if campo.obrigatorio else "não",
                    _celula(_enum_default(arquivo, campo)),
                    _celula(descricao),
                )
            )
        linhas.append("")
    linhas.append("### Estados e origens dos blocos")
    linhas.append("")
    linhas.append("- estados: %s" % ", ".join("`%s`" % e for e in ESTADOS))
    linhas.append("- origens: %s" % ", ".join("`%s`" % o for o in ORIGENS))
    linhas.append(
        "- transições proibidas (origem atual → nova): %s"
        % ", ".join("`%s` → `%s`" % par for par in TRANSICOES_PROIBIDAS)
    )
    linhas.append("- estados de meta: %s" % ", ".join("`%s`" % e for e in ESTADOS_META))
    linhas.append(
        "- campos do `hash_metas`: %s (sha256, %d caracteres)"
        % (", ".join("`%s`" % c for c in campos_hash("metas")), HASH_METAS_TAMANHO)
    )
    linhas.append("")
    linhas.append("### Ids e formatos")
    linhas.append("")
    linhas.append("| formato | regex | exemplo |")
    linhas.append("|---|---|---|")
    for tipo, regex in REGEX_POR_TIPO_ID.items():
        linhas.append("| %s | `%s` | `%s` |" % (tipo, _celula(regex.pattern), EXEMPLOS_ID[tipo]))
    linhas.append("| gp_key | `%s` | `gp:D-2026-09-28-01/inst01` |" % _celula(RE_GP_KEY.pattern))
    linhas.append("| horario_util | `%s` | `08:00-19:00` |" % _celula(RE_HORARIO_UTIL.pattern))
    linhas.append("| janela_perfil | `%s` | `seg-manha` |" % _celula(RE_JANELA_PERFIL.pattern))
    linhas.append("")
    linhas.append("### Seções fixas")
    linhas.append("")
    for arquivo, secoes in SECOES.items():
        condicionais = SECOES_CONDICIONAIS.get(arquivo, ())
        itens = []
        for secao in secoes:
            sufixo = " (condicional)" if secao in condicionais else ""
            itens.append("`%s`%s" % (secao, sufixo))
        linhas.append("- `%s`: %s" % (CAMINHOS[arquivo], " → ".join(itens)))
    linhas.append("- subseções de `planos/`: `### M<nn> <título>` em `## Metas`; `### AAAA-Www` em `## Semanas`")
    linhas.append(
        "- blocos de `dias/`: `### D-AAAA-MM-DD-<ss> <título>` em `## Hoje`, seguido de linhas `- chave: valor` com os campos de `task`"
    )
    linhas.append("")
    linhas.append("### Marcadores de prosa")
    linhas.append("")
    linhas.append("- %s" % ", ".join("`%s`" % m for m in MARCADORES_PROSA))
    linhas.append("- um bloco abre com `<!-- prosa:nome -->` e fecha com `<!-- /prosa:nome -->`")
    linhas.append("")
    linhas.append(MARCADOR_MD_FIM)
    return "\n".join(linhas) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: ``--md`` imprime ``gerar_md()``; ``--versao`` imprime ``SCHEMA_VERSION``."""
    parser = argparse.ArgumentParser(
        prog="python3 -m goalpacer.schema",
        description="fonte única do esquema dos arquivos de dados do Goal Pacer",
    )
    parser.add_argument("--md", action="store_true", help="imprime a seção de esquemas de references/dados.md")
    parser.add_argument("--versao", action="store_true", help="imprime SCHEMA_VERSION")
    args = parser.parse_args(argv)
    if not (args.md or args.versao):
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    if args.versao:
        print(SCHEMA_VERSION)
    if args.md:
        sys.stdout.write(gerar_md())
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
