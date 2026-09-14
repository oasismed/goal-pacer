"""Proxy MCP burro e prosa via ``claude -p`` (eng [2]/D3.1; receita spike §4.6).

Cada chamada de ferramenta é um ``claude -p`` de até 2 turnos, com uma única
tool MCP permitida e todos os outros servidores negados, lido em
``stream-json`` para pegar o ``tool_result`` cru (o ``result`` do envelope
json é transcrição do modelo e sai corrompido acima de 8 KB). Prosa é um
``claude -p`` sem ferramentas e sem conectores. Proxies rodam sempre em
série, com cwd neutro (``base.jobs_dir()``), nunca no repo.

Fluxo de ``chamar``::

    argv_chamada(tool, args)
        |
        v
    executar(argv, timeout_s, cwd, env)  Popen(start_new_session) + killpg no timeout
        |                                 --> GpErro(EXIT_TIMEOUT)
        v
    parse_stream(stdout.split("\n"))  uma linha = um JSON; não-JSON vira aviso
        |
        +-- sem evento result ---------------------------> ProxyErro
        +-- result.subtype == error_max_turns ---------> TurnosEsgotados
        +-- result.permission_denials não vazio -------> ToolNegada
        +-- rate_limit_event limitado / api 429 -------> RateLimited
        +-- result.is_error sem tool_result -----------> ProxyErro (ex.: sem login)
        +-- init: servidor != connected ou tool ausente
        |     ou nenhum tool_use (qualquer num_turns) -> McpNaoCarregado
        |                                                 (retry único, backoff)
        +-- tool_uses > 1 ou de outra tool ------------> RespostaInvalida
        v
    extrair_tool_result(evento user)  content str ou [{type: text, text}]
        |
        v
    resolver_spill(texto, session_id)  stub "exceeds maximum allowed tokens
        |                  ... saved to" ou <persisted-output> --> lê o
        |                  arquivo, só em projects/**/tool-results/*.txt
        +-- is_error -----------------------------------> ErroConector
        v
    json.loads(texto) -> dict  (inválido --> RespostaInvalida)
        |
        v
    projecao(dict) -> dict  (opcional; ex.: projetar_eventos)

A ordem dos sinais difere de propósito da lista do AGENTS.md (exit code
primeiro): o exit code entra no registro e vira aviso quando nada
estruturado o explica, e o rate limit é conferido antes do init para não
retentar sob janela esgotada.

Nomes de tool: ``mcp__claude_ai_<Servidor>__<tool>``; só os servidores de
``SERVIDORES_USADOS`` são chamados. A lista de deny (``--disallowedTools``)
vem do parâmetro ``servidores`` (gerado de ``claude mcp list`` por
``servidores_de_mcp_list``; ``SERVIDORES`` é só o padrão observado no
spike). ``TOOLS_ESCRITA`` lista o que é negado no modo só-leitura; o modo
escrita só muda o prompt (prefixo "Ação já aprovada pelo dono da conta.")
e não nega as tools de escrita do servidor alvo. Nunca
``--append-system-prompt`` (invalida o cache de prompt, spike §4.1).

Proxies e prosa rodam em série dentro do processo (``_SERIE``): o spike
§4.6 mediu 10 a 26 % de race de startup com chamadas em paralelo.

Nada aqui importa fora da stdlib e do próprio pacote; ``base`` e ``telemetria`` são usados por
atributo (``base.jobs_dir()``, ``telemetria.log()``) para os testes os substituírem.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, NamedTuple, Optional, Union

from goalpacer import base, clock, processos, provedor, schema, telemetria
from goalpacer.base import EXIT_IO, EXIT_TIMEOUT, EXIT_VALIDACAO, GpErro
from goalpacer.schema import RE_GP_KEY

ENV_CLAUDE_BIN = "GP_CLAUDE_BIN"
NOME_CLAUDE = "claude"
# Onde o instalador nativo põe o binário, relativo ao HOME (nunca um HOME literal no código).
CLAUDE_BIN_RELATIVO = Path(".local") / "bin" / NOME_CLAUDE
ENV_BACKOFF_S = "GP_PROXY_BACKOFF_S"
BACKOFF_PADRAO_S = 5.0
TIMEOUT_PADRAO_S = 180

# Pasta de configuração do Claude Code (transcripts e arquivos derramados).
ENV_CLAUDE_CONFIG_DIR = "CLAUDE_CONFIG_DIR"
PASTA_PROJECTS = "projects"
PASTA_TOOL_RESULTS = "tool-results"
SUFIXO_SPILL = ".txt"

# Variáveis que fariam o claude -p ou o codex exec cobrar na API em vez da assinatura (AGENTS.md: sem chave de API).
ENV_CHAVES_API = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY")

# Teto de itens por página (spike §4.7: 31 KB passa, 73 KB derrama; pageSize <= 25).
PAGE_SIZE_MAX = 25
CHAVES_PAGE_SIZE = ("pageSize", "maxResults")

PREFIXO_TOOL = "mcp__claude_ai_"
SEPARADOR_TOOL = "__"
PREFIXO_PROMPT_ESCRITA = "Ação já aprovada pelo dono da conta. "
PREFIXO_NOME_CLAUDE_AI = "claude.ai "

# Servidores que o produto chama (os demais só entram no deny).
SERVIDORES_USADOS = ("Google_Calendar", "Gmail", "Notion", "Google_Drive")

# Conectores observados no spike: padrão do deny quando o caller não passa a
# lista real de ``claude mcp list`` (``servidores_de_mcp_list``).
SERVIDORES = (
    "Google_Calendar",
    "Gmail",
    "Notion",
    "Google_Drive",
    "Slack",
    "Stripe",
    "Tavily",
    "HIggsfield",
)

TOOLS_ESCRITA: dict[str, tuple[str, ...]] = {
    "Google_Calendar": ("create_event", "update_event", "delete_event", "respond_to_event"),
    "Gmail": (
        "send_message",
        "create_draft",
        "update_draft",
        "reply",
        "forward",
        "trash_message",
        "trash_thread",
        "untrash_message",
        "untrash_thread",
        "label_message",
        "label_thread",
        "unlabel_message",
        "unlabel_thread",
        "update_message_labels",
        "create_label",
        "update_label",
        "delete_label",
        "mark_message_spam",
        "mark_thread_spam",
        "unmark_message_spam",
        "unmark_thread_spam",
        "apply_sensitive_message_label",
        "apply_sensitive_thread_label",
    ),
    "Notion": (
        "notion-create-attachment",
        "notion-create-comment",
        "notion-create-database",
        "notion-create-file-upload",
        "notion-create-folder",
        "notion-create-pages",
        "notion-create-view",
        "notion-update-data-source",
        "notion-update-folder",
        "notion-update-page",
        "notion-update-view",
        "notion-move-pages",
        "notion-duplicate-page",
        "notion-spawn-session",
        "notion-send-message-to-session",
        "notion-stop-session",
        "notion-convert-page-to-skill",
    ),
    "Google_Drive": ("create_file", "update_file", "copy_file", "share_file", "trash_file"),
}

# Prefixos que caracterizam escrita no Notion (a lista acima é a expansão).
PREFIXOS_ESCRITA_NOTION = (
    "notion-create",
    "notion-update",
    "notion-move",
    "notion-duplicate",
    "notion-spawn",
    "notion-send",
    "notion-stop",
    "notion-convert",
)

# Padrões do tool_result derramado para arquivo (spike §4.7). O stub é o
# tool_result inteiro: começa com "Error: result (" ou "<persisted-output>".
PADRAO_SPILL_EXCEEDS = "exceeds maximum allowed tokens. Output has been saved to "
PADRAO_SPILL_EXCEEDS_INICIO = "Error: result ("
PADRAO_SPILL_PERSISTED = "<persisted-output>"
PADRAO_SPILL_PERSISTED_PATH = "Full output saved to: "

# Textos do conector (spike §4.7); usados só para marcar flags em ErroConector.
TEXTO_ESCOPO_INSUFICIENTE = "Insufficient scope"
TEXTO_NAO_ENCONTRADO = "could not be found or has been deleted"

# Chave estruturada dos blocos: última linha da descrição, ``gp:<task_id>/<instalacao_id>``.
# RE_GP_KEY e CAMPOS_SO_DO_METAS vêm de goalpacer.schema (fonte única dos formatos).
# Valor de `availability` que o conector manda quando o evento é livre
# (spike §2.1); `transparency` ausente = ocupado.
AVAILABILITY_LIVRE = "AVAILABILITY_FREE"
TRANSPARENCY_LIVRE = "transparent"
TRANSPARENCY_OCUPADO = "opaque"
STATUS_EVENTO_PADRAO = "confirmed"

# rate_limit_info.status que significam janela esgotada. HIPÓTESE: o spike
# só viu "allowed" (§4.3 registra overageStatus "rejected", não status) e
# nunca capturou uma janela esgotada (§4.7); os valores aqui são
# defensivos até observar o real.
STATUS_RATE_LIMITADO = ("rejected", "limited", "exceeded", "blocked")
STATUS_MCP_CONECTADO = "connected"
SUBTYPE_MAX_TURNS = "error_max_turns"
HTTP_RATE_LIMIT = 429

# Chaves do stream-json que ``parse_stream`` devolve.
CHAVES_STREAM = ("init", "tool_uses", "tool_results", "result", "rate_limit", "avisos")


class Resultado(NamedTuple):
    """Saída de uma execução de ``claude -p``."""

    stdout: str
    stderr: str
    codigo: int
    duracao_s: float


# executar(argv, *, timeout_s, cwd, env) -> Resultado
Executar = Callable[..., Resultado]
Registro = Union[list, Callable[[dict], None], None]


class ProxyErro(GpErro):
    """Base dos erros do proxy. Subclasses fixam ``codigo_padrao``."""

    codigo_padrao = EXIT_VALIDACAO

    def __init__(self, mensagem: str = "", codigo: Optional[int] = None) -> None:
        super().__init__(self.codigo_padrao if codigo is None else codigo, mensagem)


class McpNaoCarregado(ProxyErro):
    """Catálogo MCP não carregou: servidor ``pending``/ausente no init, tool
    fora de ``init.tools``, ou nenhum ``tool_use`` (race de startup, spike
    §4.7; sem tool_use não houve efeito). ``chamar`` retenta uma vez."""

    codigo_padrao = EXIT_IO


class ToolNegada(ProxyErro):
    """``permission_denials`` não vazio no evento ``result``."""

    codigo_padrao = EXIT_VALIDACAO

    def __init__(self, mensagem: str = "", denials: Optional[list] = None) -> None:
        super().__init__(mensagem)
        self.denials = list(denials or [])


class TurnosEsgotados(ProxyErro):
    """``result.subtype == "error_max_turns"``."""


class ErroConector(ProxyErro):
    """``tool_result.is_error`` verdadeiro; ``texto`` é a mensagem do conector.

    ``escopo_insuficiente`` marca "Insufficient scope" (reconectar com
    escopo de escrita); ``nao_encontrado`` marca "could not be found or has
    been deleted" (evento apagado).
    """

    def __init__(self, texto: str) -> None:
        super().__init__("erro do conector: " + texto[:200])
        self.texto = texto
        self.escopo_insuficiente = TEXTO_ESCOPO_INSUFICIENTE in texto
        self.nao_encontrado = TEXTO_NAO_ENCONTRADO in texto


class RateLimited(ProxyErro):
    """``rate_limit_event`` com status limitado ou ``api_error_status == 429``.

    ``reset_em`` vem de ``rate_limit_info.resetsAt`` (ou
    ``unifiedWindows.five_hour.resetsAt``) quando disponível.
    """

    def __init__(self, mensagem: str = "", reset_em: Optional[datetime] = None) -> None:
        super().__init__(mensagem)
        self.reset_em = reset_em


class RespostaInvalida(ProxyErro):
    """Sem ``tool_result``, mais de um ``tool_use``, ou JSON inválido no texto."""


def claude_bin_padrao() -> str:
    """``~/.local/bin/claude`` do HOME atual (instalador nativo; ``claude.exe`` no Windows)."""
    return str(Path.home() / CLAUDE_BIN_RELATIVO) + (".exe" if os.name == "nt" else "")


def claude_bin() -> str:
    """Binário do Claude Code, resolvido a cada chamada: ``GP_CLAUDE_BIN``;
    senão o ``claude`` do PATH (``shutil.which``); senão ``claude_bin_padrao()``.
    Os plists gravam o caminho absoluto em ``GP_CLAUDE_BIN`` (launchd tem PATH mínimo)."""
    env = os.environ.get(ENV_CLAUDE_BIN)
    if env:
        return env
    achado = shutil.which(NOME_CLAUDE)
    padrao = claude_bin_padrao()
    if achado and not (achado.lower().endswith((".cmd", ".bat")) and os.path.isfile(padrao)):
        return achado
    return padrao  # sem claude no PATH, ou só o claude.cmd do npm (que quebraria o prompt com quebra de linha)


def _separar_tool(tool: str) -> tuple[str, str]:
    """``mcp__claude_ai_<Servidor>__<tool>`` → ``(<Servidor>, <tool>)``."""
    if not isinstance(tool, str) or not tool.startswith(PREFIXO_TOOL):
        raise GpErro(EXIT_VALIDACAO, "nome de tool fora do padrão mcp__claude_ai_<Servidor>__<tool>: %r" % (tool,))
    servidor, sep, nome = tool[len(PREFIXO_TOOL) :].partition(SEPARADOR_TOOL)
    if not sep or not nome:
        raise GpErro(EXIT_VALIDACAO, "nome de tool sem a parte <tool>: %r" % (tool,))
    if servidor not in SERVIDORES_USADOS:
        raise GpErro(
            EXIT_VALIDACAO,
            "servidor MCP não usado pelo produto em %r (usados: %s)" % (tool, ", ".join(SERVIDORES_USADOS)),
        )
    return servidor, nome


def servidor_de(tool: str) -> str:
    """``mcp__claude_ai_<Servidor>__<tool>`` → ``<Servidor>``.

    Servidor fora de ``SERVIDORES_USADOS`` ou nome fora do padrão é
    ``GpErro(EXIT_VALIDACAO)`` (Slack, Stripe, Tavily etc. só entram no deny).
    """
    return _separar_tool(tool)[0]


RE_LINHA_MCP_LIST = re.compile(r"^(?P<nome>.+?): (?P<url>\S+) - (?P<status>.+?)\s*$")


def servidores_de_mcp_list(texto: str) -> list[str]:
    """Nomes de servidor (forma ``Google_Calendar``) a partir da saída de
    ``claude mcp list`` (spike §4.5: ``<nome>: <url> - ✔ Connected`` por linha).

    Só conectores claude.ai (``claude.ai X Y`` → ``X_Y``); outros servidores
    MCP têm outro prefixo de tool e ficam de fora. Entram todos os listados,
    qualquer status: negar um servidor que não subiu é inócuo, e um
    ``pending`` pode estar conectado na hora do proxy. Ordem da saída, sem
    repetição.
    """
    nomes: list[str] = []
    for servidor, _status in _linhas_mcp_list(texto):
        if servidor and servidor not in nomes:
            nomes.append(servidor)
    return nomes


def _linhas_mcp_list(texto: str) -> Iterator[tuple[str, str]]:
    """``(servidor, status bruto)`` de cada linha de conector claude.ai; o resto da saída é ignorado."""
    for linha in str(texto or "").split("\n"):
        m = RE_LINHA_MCP_LIST.match(linha.strip())
        nome = m.group("nome").strip() if m else ""
        if m and nome.lower().startswith(PREFIXO_NOME_CLAUDE_AI):
            yield nome[len(PREFIXO_NOME_CLAUDE_AI) :].strip().replace(" ", "_"), m.group("status").strip()


def status_de_mcp_list(texto: str) -> dict[str, str]:
    """``{servidor: status}`` dos conectores claude.ai em ``claude mcp list``
    (``✔ Connected`` vira ``Connected``; o glifo é descartado). Layout não
    reconhecido = dicionário vazio, nunca exceção (spike §4.5)."""
    estados: dict[str, str] = {}
    for servidor, bruto in _linhas_mcp_list(texto):
        sem_glifo = bruto.split(" ", 1)[1] if bruto[:1] and not bruto[:1].isalnum() and " " in bruto else bruto
        estados.setdefault(servidor, sem_glifo)
    return estados


def servidores_mcp_list(*, executar: Optional[Executar] = None, timeout_s: float = 60) -> list[str]:
    """Roda ``claude mcp list`` e devolve ``servidores_de_mcp_list(stdout)``.

    É a fonte da lista de deny em produção (AGENTS.md: nunca escrita à mão);
    ``run_job`` chama uma vez e passa o resultado em ``servidores=``. Saída
    vazia (sem conector) é ``GpErro(EXIT_IO)``.
    """
    rodar = executar if executar is not None else executar_padrao
    resultado = rodar([claude_bin(), "mcp", "list"], timeout_s=timeout_s, cwd=None, env=None)
    nomes = servidores_de_mcp_list(resultado.stdout)
    if not nomes:
        raise GpErro(EXIT_IO, "claude mcp list não listou nenhum conector claude.ai (código %d)" % resultado.codigo)
    return nomes


def eh_escrita(tool: str) -> bool:
    """True se a tool está em ``TOOLS_ESCRITA`` do seu servidor (para o
    Notion, também se o nome começa com um ``PREFIXOS_ESCRITA_NOTION``)."""
    servidor, nome = _separar_tool(tool)
    if nome in TOOLS_ESCRITA.get(servidor, ()):
        return True
    return servidor == "Notion" and nome.startswith(PREFIXOS_ESCRITA_NOTION)


def _tools_negadas(servidor: str, modo_leitura: bool, servidores: Iterable[str]) -> list[str]:
    """Itens do ``--disallowedTools``: os outros servidores inteiros e, no
    modo só-leitura, as tools de escrita do servidor alvo."""
    negadas = [PREFIXO_TOOL + outro for outro in servidores if outro != servidor]
    if modo_leitura:
        negadas.extend(PREFIXO_TOOL + servidor + SEPARADOR_TOOL + nome for nome in TOOLS_ESCRITA.get(servidor, ()))
    return negadas


def _prompt_chamada(tool: str, args: dict[str, Any], modo_leitura: bool) -> str:
    if not isinstance(args, dict):
        raise GpErro(EXIT_VALIDACAO, "args da tool %s devem ser um dict" % tool)
    try:
        args_json = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise GpErro(EXIT_VALIDACAO, "args da tool %s não serializam em JSON: %s" % (tool, exc)) from exc
    prompt = "Chame " + tool + " com exatamente estes argumentos: " + args_json + ". Depois responda apenas OK."
    if not modo_leitura:
        prompt = PREFIXO_PROMPT_ESCRITA + prompt
    return prompt


def argv_chamada(
    tool: str,
    args: dict[str, Any],
    *,
    modo_leitura: bool = True,
    modelo: str = "haiku",
    max_turns: int = 2,
    servidores: Optional[Iterable[str]] = None,
) -> list[str]:
    """argv do ``claude -p`` para uma chamada de tool, EXATAMENTE nesta ordem::

        [claude_bin(), "-p", "--output-format", "stream-json", "--verbose",
         "--max-turns", str(max_turns), "--tools", tool, "--allowedTools", tool,
         "--disallowedTools", <mcp__claude_ai_<S> de cada servidor de
                              ``servidores`` (padrão SERVIDORES) menos o alvo>
                              + (modo_leitura: tools de escrita do servidor alvo,
                                 cada uma como item separado),
         "--setting-sources", "", "--permission-prompts", "none",
         "--model", modelo, prompt]

    ``servidores`` deve vir de ``servidores_de_mcp_list`` em produção.

    prompt = "Chame <tool> com exatamente estes argumentos: <json.dumps(args,
    ensure_ascii=False)>. Depois responda apenas OK."; no modo escrita,
    prefixado com "Ação já aprovada pelo dono da conta. ". ``--model`` fica
    imediatamente antes do prompt (flags variádicos engolem o posicional).

    Tool de escrita em ``modo_leitura`` é ``GpErro(EXIT_VALIDACAO)``: o deny
    venceria o allow e a chamada seria negada de qualquer jeito.
    """
    servidor = servidor_de(tool)
    if modo_leitura and eh_escrita(tool):
        raise GpErro(EXIT_VALIDACAO, "tool de escrita %s pedida em modo só-leitura" % tool)
    argv = [
        claude_bin(),
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--tools",
        tool,
        "--allowedTools",
        tool,
        "--disallowedTools",
    ]
    argv.extend(_tools_negadas(servidor, modo_leitura, SERVIDORES if servidores is None else list(servidores)))
    argv.extend(
        [
            "--setting-sources",
            "",
            "--permission-prompts",
            "none",
            "--model",
            modelo,
            _prompt_chamada(tool, args, modo_leitura),
        ]
    )
    return argv


def argv_prosa(prompt: str, *, modelo: str = "haiku", max_turns: int = 1) -> list[str]:
    """argv do ``claude -p`` para prosa sem ferramentas::

    [CLAUDE_BIN, "-p", "--output-format", "json", "--max-turns", str(max_turns),
     "--strict-mcp-config", "--tools", "", "--setting-sources", "",
     "--permission-prompts", "none", "--model", modelo, prompt]
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise GpErro(EXIT_VALIDACAO, "prompt de prosa vazio")
    return [
        claude_bin(),
        "-p",
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--strict-mcp-config",
        "--tools",
        "",
        "--setting-sources",
        "",
        "--permission-prompts",
        "none",
        "--model",
        modelo,
        prompt,
    ]


LIMITE_ARGUMENTO_WINDOWS = 24_000  # a linha de comando do Windows para em cerca de 32 mil caracteres, com as flags


def prompt_pela_entrada(argv: list[str]) -> tuple[list[str], Optional[str]]:
    """No Windows, o prompt longo (sempre o último argumento das receitas) sai da linha de comando e vai pela entrada
    padrão, que o ``claude -p`` lê quando não recebe o prompt como argumento. Nos outros sistemas, nada muda."""
    if not processos.WINDOWS or len(argv) < 2 or len(argv[-1]) <= LIMITE_ARGUMENTO_WINDOWS:
        return argv, None
    return argv[:-1], argv[-1]


def _matar_grupo(processo: subprocess.Popen) -> None:
    """A árvore do filho inteira (o ``claude -p`` cria netos), no macOS, no Linux e no Windows."""
    processos.matar_arvore(processo)


def executar_padrao(
    argv: list[str],
    *,
    timeout_s: float,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
) -> Resultado:
    """Roda ``argv`` com ``subprocess.Popen`` e devolve ``Resultado``.

    ``stdin=DEVNULL`` (no Windows, prompt acima de ``LIMITE_ARGUMENTO_WINDOWS`` vai pela entrada padrão), stdout/stderr
    capturados em UTF-8,
    ``start_new_session=True``; ``communicate(timeout=timeout_s)``. Em
    ``TimeoutExpired``: ``os.killpg(os.getpgid(pid), SIGKILL)``,
    ``communicate()`` e ``GpErro(EXIT_TIMEOUT)``. ``cwd`` padrão =
    ``base.jobs_dir()`` (criado se não existir; nunca o repo); ``env`` padrão
    = ``os.environ``, sempre sem ``ENV_CHAVES_API`` (o claude -p cobraria na
    API em vez da assinatura). Binário ausente é ``GpErro(EXIT_IO)``.
    """
    pasta = Path(cwd) if cwd is not None else base.jobs_dir()
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise GpErro(EXIT_IO, "não consegui criar o cwd do proxy %s: %s" % (pasta, exc)) from exc
    ambiente = dict(os.environ if env is None else env)
    for chave in ENV_CHAVES_API:
        ambiente.pop(chave, None)
    inicio = time.monotonic()
    argv, entrada = prompt_pela_entrada(argv)
    try:
        # pragma: no mutate start (sem start_new_session o killpg de um mutante acertaria o mutmut)
        processo = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL if entrada is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(pasta),
            env=ambiente,
            **processos.isolamento(),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # pragma: no mutate end
    except OSError as exc:
        raise GpErro(
            EXIT_IO,
            "não consegui executar %s: %s (defina %s com o caminho do claude)"
            % (argv[0] if argv else "?", exc, ENV_CLAUDE_BIN),
        ) from exc
    try:
        stdout, stderr = processo.communicate(input=entrada, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _matar_grupo(processo)
        processo.communicate()
        raise GpErro(EXIT_TIMEOUT, "timeout de %g s em %s" % (timeout_s, argv[0] if argv else "?")) from None
    return Resultado(stdout or "", stderr or "", processo.returncode, time.monotonic() - inicio)


def _blocos(evento: dict[str, Any]) -> list[dict[str, Any]]:
    """Blocos de ``message.content`` de um evento assistant/user (lista, ou
    vazia quando o content é texto puro)."""
    mensagem = evento.get("message")
    if not isinstance(mensagem, dict):
        return []
    conteudo = mensagem.get("content")
    if not isinstance(conteudo, list):
        return []
    return [bloco for bloco in conteudo if isinstance(bloco, dict)]


def parse_stream(linhas: Iterable[str]) -> dict[str, Any]:
    """Linhas de ``stream-json`` → ``{"init", "tool_uses", "tool_results",
    "result", "rate_limit", "avisos"}``.

    Cada linha é um JSON; vazias são puladas e não-JSON vão para ``avisos``
    (lista de str). ``init`` é o evento ``system/init`` (ou None);
    ``tool_uses`` os blocos ``tool_use`` dos eventos ``assistant``;
    ``tool_results`` os eventos ``user`` com ``tool_result``; ``result`` o
    evento final; ``rate_limit`` o último ``rate_limit_event`` (ou None).
    """
    saida: dict[str, Any] = dict.fromkeys(CHAVES_STREAM)
    saida["tool_uses"] = []
    saida["tool_results"] = []
    saida["avisos"] = []
    for numero, linha_bruta in enumerate(linhas, 1):
        linha = linha_bruta.strip()
        evento = _evento_da_linha(linha, numero, saida["avisos"]) if linha else None
        if evento is not None:
            _guardar_evento(saida, evento)
    return saida


def _evento_da_linha(linha: str, numero: int, avisos: list[str]) -> Optional[dict[str, Any]]:
    try:
        evento = json.loads(linha)
    except ValueError:
        avisos.append("linha %d do stream não é JSON (%d chars)" % (numero, len(linha)))
        return None
    if not isinstance(evento, dict):
        avisos.append("linha %d do stream não é um objeto JSON" % numero)
        return None
    return evento


def _guardar_evento(saida: dict[str, Any], evento: dict[str, Any]) -> None:
    tipo = evento.get("type")
    if tipo == "system" and evento.get("subtype") == "init":
        saida["init"] = evento
    elif tipo == "assistant":
        saida["tool_uses"].extend(bloco for bloco in _blocos(evento) if bloco.get("type") == "tool_use")
    elif tipo == "user" and any(bloco.get("type") == "tool_result" for bloco in _blocos(evento)):
        saida["tool_results"].append(evento)
    elif tipo in EVENTOS_FINAIS:
        saida[EVENTOS_FINAIS[tipo]] = evento


EVENTOS_FINAIS = {
    "result": "result",
    "rate_limit_event": "rate_limit",
}  # tipo do evento -> chave do stream (o último vale)


def extrair_tool_result(evento_user: dict[str, Any]) -> tuple[str, bool]:
    """Evento ``user`` → ``(texto, is_error)``.

    ``content`` do ``tool_result`` pode ser str ou lista de blocos
    ``{"type": "text", "text": ...}`` (concatenados). Sem ``tool_result`` é
    ``RespostaInvalida``.
    """
    for bloco in _blocos(evento_user):
        if bloco.get("type") != "tool_result":
            continue
        conteudo = bloco.get("content")
        if isinstance(conteudo, str):
            texto = conteudo
        elif isinstance(conteudo, list):
            texto = "".join(
                item.get("text", "")
                for item in conteudo
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
            )
        elif conteudo is None:
            texto = ""
        else:
            texto = json.dumps(conteudo, ensure_ascii=False)
        return texto, bool(bloco.get("is_error"))
    raise RespostaInvalida("evento user sem bloco tool_result")


def _resto_da_linha(texto: str) -> str:
    """``texto`` até a primeira quebra de linha, sem espaços nem ponto final
    (o caminho derramado pode ter espaços: HOME ou CLAUDE_CONFIG_DIR)."""
    return texto.split("\n", 1)[0].strip().rstrip(".").strip()


def _caminho_spill(texto: str) -> Optional[str]:
    """Caminho do arquivo derramado quando ``texto`` é um dos stubs; senão None.

    Só reconhece o stub no início do texto: um JSON de conector que contenha
    a frase no meio (conteúdo de terceiros) não pode mandar ler um arquivo.
    """
    inicio = texto.lstrip()
    if inicio.startswith(PADRAO_SPILL_EXCEEDS_INICIO) and PADRAO_SPILL_EXCEEDS in inicio:
        return _resto_da_linha(inicio.split(PADRAO_SPILL_EXCEEDS, 1)[1]) or None
    if inicio.startswith(PADRAO_SPILL_PERSISTED) and PADRAO_SPILL_PERSISTED_PATH in inicio:
        return _resto_da_linha(inicio.split(PADRAO_SPILL_PERSISTED_PATH, 1)[1]) or None
    return None


def claude_config_dir() -> Path:
    """Pasta de configuração do Claude Code: ``CLAUDE_CONFIG_DIR`` ou ``~/.claude``."""
    bruto = os.environ.get(ENV_CLAUDE_CONFIG_DIR)
    return Path(bruto).expanduser() if bruto else Path.home() / ".claude"


def resolver_spill(texto: str, *, session_id: Optional[str] = None) -> str:
    """Se ``texto`` é o stub de resposta derramada, lê o arquivo apontado
    (``expanduser``) e devolve seu conteúdo; senão devolve ``texto``.

    Stubs: "Error: result (N characters) exceeds maximum allowed tokens.
    Output has been saved to <path>" e "<persisted-output> ... Full output
    saved to: <path>". O caminho vem do ``tool_result`` (dado não confiável),
    então só vale um arquivo ``.txt`` dentro de
    ``claude_config_dir()/projects/`` com uma pasta ``tool-results`` no
    caminho (onde o Claude Code derrama, spike §4.7) e, quando
    ``session_id`` é dado, com essa sessão no caminho; ``.credentials.json``,
    settings, transcripts de outras sessões e qualquer coisa fora dali é
    ``RespostaInvalida``, assim como arquivo ilegível.
    """
    caminho = _caminho_spill(texto)
    if caminho is None:
        return texto
    arquivo = Path(caminho).expanduser()
    raiz = claude_config_dir() / PASTA_PROJECTS
    try:
        real = arquivo.resolve()
        dentro = real.is_relative_to(raiz.resolve())
    except OSError as exc:
        raise RespostaInvalida("arquivo derramado %s não resolve: %s" % (arquivo, exc)) from exc
    partes = real.parts
    if not dentro or PASTA_TOOL_RESULTS not in partes or real.suffix != SUFIXO_SPILL:
        raise RespostaInvalida(
            "arquivo derramado %s fora de %s/**/%s/*%s" % (arquivo, raiz, PASTA_TOOL_RESULTS, SUFIXO_SPILL)
        )
    if session_id and session_id not in partes:
        raise RespostaInvalida("arquivo derramado %s não é da sessão %s" % (arquivo, session_id))
    try:
        return arquivo.read_text(encoding="utf-8")
    except OSError as exc:
        raise RespostaInvalida("arquivo derramado %s ilegível: %s" % (arquivo, exc)) from exc


def _slug_cwd(cwd: Path) -> str:
    """Codificação do cwd usada pelo Claude Code em ``~/.claude/projects``."""
    absoluto = str(Path(cwd).expanduser().resolve())
    return "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in absoluto)


def caminho_transcript(cwd: Path, session_id: str) -> Path:
    """Transcript que o Claude Code grava para uma sessão:
    ``<claude_config_dir()>/projects/<slug>/<session_id>.jsonl``.

    O slug é o cwd absoluto com ``/``, ``.``, ``_`` (e qualquer outro
    caractere que não seja letra, dígito ou ``-``) trocados por ``-``, o que
    dá o prefixo ``-``. É heurística observada no spike (Claude Code
    2.1.270), não contrato; quem apaga transcripts deve tolerar arquivo
    ausente. ``session_id`` só aceita letras, dígitos e ``-``.
    """
    _validar_session_id(session_id)
    return claude_config_dir() / PASTA_PROJECTS / _slug_cwd(cwd) / (session_id + ".jsonl")


def caminho_tool_results(cwd: Path, session_id: str) -> Path:
    """Pasta da sessão onde o Claude Code derrama os ``tool_result`` grandes
    (JSON completo de terceiros): ``<claude_config_dir()>/projects/<slug>/<session_id>``
    (os arquivos ficam em ``tool-results/`` dentro dela). A retenção remove o
    ``.jsonl`` de ``caminho_transcript`` e esta pasta. Mesma heurística do slug."""
    _validar_session_id(session_id)
    return claude_config_dir() / PASTA_PROJECTS / _slug_cwd(cwd) / session_id


def _validar_session_id(session_id: Any) -> None:
    if not isinstance(session_id, str) or not session_id or not all(ch.isalnum() or ch == "-" for ch in session_id):
        raise GpErro(EXIT_VALIDACAO, "session_id inválido: %r" % (session_id,))


def _backoff_s() -> float:
    bruto = os.environ.get(ENV_BACKOFF_S)
    if bruto is None or bruto == "":
        return BACKOFF_PADRAO_S
    try:
        return max(0.0, float(bruto))
    except ValueError:
        return BACKOFF_PADRAO_S


def _registrar(registro: Registro, entrada: dict[str, Any]) -> None:
    _span_da_chamada(entrada)
    if registro is None:
        return
    if isinstance(registro, list):
        registro.append(entrada)
    elif callable(registro):
        registro(entrada)
    else:
        raise GpErro(EXIT_VALIDACAO, "registro deve ser lista ou callable")


def somar_tokens(registro_proxies: list) -> dict[str, int]:
    """Tokens de todas as chamadas registradas numa execução (input, cache_read, cache_creation, output)."""
    total = {"input": 0, "cache_read": 0, "cache_creation": 0, "output": 0}
    for entrada in registro_proxies:
        uso = entrada.get("usage") or {}
        total["input"] += int(uso.get("input_tokens") or 0)
        total["cache_read"] += int(uso.get("cache_read_input_tokens") or 0)
        total["cache_creation"] += int(uso.get("cache_creation_input_tokens") or 0)
        total["output"] += int(uso.get("output_tokens") or 0)
    return total


def _span_da_chamada(entrada: dict[str, Any]) -> None:
    """Toda chamada de conector ou de prosa vira um span local (tempo, tentativa, tokens), sem prompt nem resposta."""
    lido = entrada.get("usage")
    usage: dict[str, Any] = lido if isinstance(lido, dict) else {}
    tokens = sum(
        int(usage.get(k) or 0)
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    ferramenta = str(entrada.get("tool") or "")
    telemetria.registrar_span(
        "prosa" if ferramenta == "prosa" else "conector",
        float(entrada.get("duracao_s") or 0) * 1000,
        ferramenta=ferramenta.rsplit("__", 1)[-1],
        servidor=ferramenta.split("__")[1] if ferramenta.count("__") >= 2 else "",
        tentativa=entrada.get("tentativa"),
        codigo=entrada.get("codigo"),
        subtype=entrada.get("subtype"),
        is_error=entrada.get("is_error"),
        turnos=entrada.get("num_turns"),
        tokens=tokens,
    )


def _entrada_registro(
    tool: str,
    envelope: Optional[dict[str, Any]],
    init: Optional[dict[str, Any]],
    resultado: Resultado,
    tentativa: int,
    cwd: Path,
) -> dict[str, Any]:
    envelope = envelope or {}
    session_id = envelope.get("session_id") or (init or {}).get("session_id")
    return {
        "tool": tool,
        "session_id": session_id,
        "duracao_s": resultado.duracao_s,
        "codigo": resultado.codigo,
        "subtype": envelope.get("subtype"),
        "is_error": bool(envelope.get("is_error")),
        "num_turns": envelope.get("num_turns"),
        "usage": envelope.get("usage"),
        "total_cost_usd": envelope.get("total_cost_usd"),
        "tentativa": tentativa,
        "cwd": str(cwd),
    }


def _parse_reset_em(valor: Any) -> Optional[datetime]:
    """``resetsAt`` (epoch em s ou ms, ou ISO 8601) → datetime UTC, ou None."""
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        segundos = float(valor)
        if segundos > 1e11:
            segundos = segundos / 1000.0
        try:
            return datetime.fromtimestamp(segundos, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(valor, str):
        try:
            return clock.parse_iso(valor, tz_padrao=timezone.utc)
        except GpErro:
            return None
    return None


def _checar_rate_limit(stream: dict[str, Any], envelope: dict[str, Any]) -> None:
    """``RateLimited`` por sinal estruturado (nunca por string, spike 5.2)."""
    evento = stream.get("rate_limit")
    info = evento.get("rate_limit_info") if isinstance(evento, dict) else None
    if isinstance(info, dict) and str(info.get("status", "")).lower() in STATUS_RATE_LIMITADO:
        reset = _parse_reset_em(info.get("resetsAt"))
        if reset is None:
            janelas = info.get("unifiedWindows")
            if isinstance(janelas, dict) and isinstance(janelas.get("five_hour"), dict):
                reset = _parse_reset_em(janelas["five_hour"].get("resetsAt"))
        raise RateLimited(
            "rate limit (%s, status %s)" % (info.get("rateLimitType", "?"), info.get("status")),
            reset_em=reset,
        )
    if envelope.get("api_error_status") == HTTP_RATE_LIMIT:
        raise RateLimited("api_error_status 429")


def _nome_servidor_init(nome: Any) -> str:
    """Nome do servidor no ``init`` ("claude.ai Google Calendar",
    "claude_ai_Google_Calendar", "mcp__claude_ai_Google_Calendar") →
    forma comparável a ``SERVIDORES`` em minúsculas."""
    texto = str(nome or "").strip()
    for prefixo in (PREFIXO_TOOL, "claude_ai_", "claude.ai "):
        if texto.lower().startswith(prefixo.lower()):
            texto = texto[len(prefixo) :]
            break
    return texto.replace(" ", "_").lower()


def _checar_init(tool: str, servidor: str, stream: dict[str, Any], envelope: dict[str, Any]) -> None:
    """``McpNaoCarregado`` quando o catálogo MCP não subiu (spike §4.7)."""
    init = stream.get("init")
    if not isinstance(init, dict):
        raise McpNaoCarregado("sem evento system/init no stream")
    status = None
    for item in init.get("mcp_servers") or []:
        if isinstance(item, dict) and _nome_servidor_init(item.get("name")) == servidor.lower():
            status = str(item.get("status", ""))
            break
    if status != STATUS_MCP_CONECTADO:
        raise McpNaoCarregado("servidor %s %s no init" % (servidor, status or "ausente"))
    itens = init.get("tools")
    nomes = [
        item if isinstance(item, str) else item.get("name")
        for item in (itens if isinstance(itens, list) else [])
        if isinstance(item, (str, dict))
    ]
    if tool not in nomes:
        raise McpNaoCarregado("tool %s ausente do catálogo do init (%d tools)" % (tool, len(nomes)))
    if not stream["tool_uses"]:
        # Sem tool_use não houve efeito algum: retentar é seguro mesmo em
        # modo escrita (spike §4.6: "sem tool_use → descartar e reexecutar").
        raise McpNaoCarregado("nenhum tool_use (num_turns=%s): race de startup" % (envelope.get("num_turns"),))


def _texto_erro_envelope(envelope: dict[str, Any]) -> str:
    erros = envelope.get("errors")
    if isinstance(erros, list) and erros:
        return "; ".join(str(erro) for erro in erros)[:200]
    resultado = envelope.get("result")
    return (resultado if isinstance(resultado, str) else "")[:200]


def _session_id(stream: dict[str, Any]) -> Optional[str]:
    for evento in (stream.get("result"), stream.get("init")):
        if isinstance(evento, dict) and isinstance(evento.get("session_id"), str) and evento["session_id"]:
            return evento["session_id"]
    return None


def _interpretar(tool: str, servidor: str, stream: dict[str, Any], resultado: Resultado) -> dict[str, Any]:
    """Aplica as verificações do fluxo do módulo a um stream já parseado."""
    _conferir_envelope(tool, servidor, stream, resultado)
    texto, is_error = extrair_tool_result(_tool_result_do_uso(tool, stream))
    resolvido = resolver_spill(texto, session_id=_session_id(stream))
    if is_error and resolvido is texto:
        raise ErroConector(texto)
    try:
        dados = json.loads(resolvido)
    except ValueError as exc:
        raise RespostaInvalida("tool_result de %s não é JSON (%d chars): %s" % (tool, len(resolvido), exc)) from exc
    if not isinstance(dados, dict):
        raise RespostaInvalida("tool_result de %s não é um objeto JSON" % tool)
    if resultado.codigo != 0:
        telemetria.log(
            "proxy %s: claude -p saiu com código %d apesar do tool_result válido" % (tool, resultado.codigo),
            nivel="aviso",
        )
    return dados


def _conferir_envelope(tool: str, servidor: str, stream: dict[str, Any], resultado: Resultado) -> None:
    """Sinais do envelope na ordem do spike: sem result, turnos, negação, limite de uso, is_error, init."""
    envelope = stream.get("result")
    if not isinstance(envelope, dict):
        raise ProxyErro(
            "claude -p terminou sem evento result (código %d): %s" % (resultado.codigo, resultado.stderr.strip()[:200]),
            codigo=EXIT_IO,
        )
    if envelope.get("subtype") == SUBTYPE_MAX_TURNS:
        raise TurnosEsgotados("turnos esgotados em %s (num_turns=%s)" % (tool, envelope.get("num_turns")))
    denials = envelope.get("permission_denials")
    if denials:
        nomes = sorted({str(d.get("tool_name", "?")) for d in denials if isinstance(d, dict)})
        raise ToolNegada("tool negada: %s" % ", ".join(nomes), denials=denials)
    _checar_rate_limit(stream, envelope)
    if envelope.get("is_error") and not stream["tool_results"]:
        raise ProxyErro("claude -p com is_error em %s: %s" % (tool, _texto_erro_envelope(envelope)))
    _checar_init(tool, servidor, stream, envelope)


def _tool_result_do_uso(tool: str, stream: dict[str, Any]) -> dict[str, Any]:
    """Exatamente um tool_use da tool pedida e o evento user com o tool_result dele (o primeiro, se nenhum casa)."""
    tool_uses = stream["tool_uses"]
    if len(tool_uses) != 1:
        raise RespostaInvalida("esperado exatamente 1 tool_use em %s, houve %d" % (tool, len(tool_uses)))
    if tool_uses[0].get("name") != tool:
        raise RespostaInvalida("tool_use de %s em vez de %s" % (tool_uses[0].get("name"), tool))
    if not stream["tool_results"]:
        raise RespostaInvalida("sem tool_result para %s" % tool)
    uso_id = tool_uses[0].get("id")
    return next(
        (e for e in stream["tool_results"] if any(b.get("tool_use_id") == uso_id for b in _blocos(e))),
        stream["tool_results"][0],
    )


# Proxies e prosa em série dentro do processo (spike §4.6).
_SERIE = threading.Lock()

Projecao = Optional[Callable[[dict[str, Any]], dict[str, Any]]]


def _avisar_page_size(tool: str, args: dict[str, Any]) -> None:
    for chave in CHAVES_PAGE_SIZE:
        valor = args.get(chave)
        if isinstance(valor, int) and not isinstance(valor, bool) and valor > PAGE_SIZE_MAX:
            telemetria.log(
                "proxy %s: %s=%d acima de %d; a resposta pode derramar (spike §4.7)"
                % (tool, chave, valor, PAGE_SIZE_MAX),
                nivel="aviso",
            )


def chamar(
    tool: str,
    args: dict[str, Any],
    *,
    modo_leitura: bool = True,
    modelo: str = "haiku",
    timeout_s: float = TIMEOUT_PADRAO_S,
    executar: Optional[Executar] = None,
    tentativas: int = 2,
    registro: Registro = None,
    servidores: Optional[Iterable[str]] = None,
    projecao: Projecao = None,
) -> dict[str, Any]:
    """Chama uma tool MCP pelo proxy e devolve o JSON do ``tool_result``
    (cru, ou passado por ``projecao`` quando dada; ex.: ``projetar_eventos``).

    Monta ``argv_chamada`` (``servidores`` = lista de deny, de
    ``servidores_de_mcp_list``), executa (``executar_padrao`` por padrão;
    testes injetam um callable com a mesma assinatura) sob ``_SERIE``,
    percorre o stream (linhas separadas só por ``\n``: ``splitlines`` quebraria
    em U+2028/U+2029/U+0085, que o JSON do Node não escapa) e aplica as
    verificações do diagrama do módulo, nesta ordem: ``error_max_turns`` →
    ``permission_denials`` → rate limit → init/tool_use → tool_result.
    ``McpNaoCarregado`` é retentado até ``tentativas`` com backoff
    ``GP_PROXY_BACKOFF_S`` (padrão 5 s; 0 nos testes). Os demais erros e o
    timeout não são retentados. ``pageSize``/``maxResults`` acima de
    ``PAGE_SIZE_MAX`` em ``args`` só gera aviso.

    ``registro`` (lista ou callable) recebe, por execução, ``{"tool",
    "session_id", "duracao_s", "codigo", "subtype", "is_error", "num_turns",
    "usage", "total_cost_usd", "tentativa", "cwd"}``; o ``session_id`` serve
    para apagar o transcript (``caminho_transcript``) e a pasta de
    ``caminho_tool_results`` depois.
    """
    provedor.exigir_conectores(tool)
    servidor = servidor_de(tool)
    argv = argv_chamada(tool, args, modo_leitura=modo_leitura, modelo=modelo, servidores=servidores)
    _avisar_page_size(tool, args)
    rodar = executar if executar is not None else executar_padrao
    cwd = base.jobs_dir()
    total = max(1, int(tentativas))
    backoff = _backoff_s()
    ultimo: Optional[McpNaoCarregado] = None
    for tentativa in range(1, total + 1):
        if tentativa > 1 and backoff > 0:
            time.sleep(backoff)
        with _SERIE:
            resultado = rodar(argv, timeout_s=timeout_s, cwd=cwd, env=None)
        stream = parse_stream(resultado.stdout.split("\n"))
        for aviso in stream["avisos"]:
            telemetria.log("proxy %s: %s" % (tool, aviso), nivel="aviso")
        _registrar(
            registro, _entrada_registro(tool, stream.get("result"), stream.get("init"), resultado, tentativa, cwd)
        )
        try:
            dados = _interpretar(tool, servidor, stream, resultado)
            return projecao(dados) if projecao is not None else dados
        except McpNaoCarregado as exc:
            ultimo = exc
            if tentativa < total:
                telemetria.log(
                    "proxy %s: tentativa %d/%d falhou (%s); nova tentativa em %g s"
                    % (tool, tentativa, total, exc, backoff),
                    nivel="aviso",
                )
    assert ultimo is not None
    raise ultimo


def chamar_paginado(
    tool: str,
    args: dict[str, Any],
    *,
    chave_lista: str,
    chave_token: str = "nextPageToken",  # noqa: S107 - nome do campo de paginação, não senha
    chave_token_pedido: str = "pageToken",  # noqa: S107 - idem
    chave_page_size: str = "pageSize",
    page_size: int = 25,
    max_paginas: int = 40,
    **kw: Any,
) -> list[Any]:
    """Segue ``nextPageToken`` e concatena ``resposta[chave_lista]``.

    Injeta ``args[chave_page_size] = page_size`` (1 a ``PAGE_SIZE_MAX`` = 25:
    acima disso o ``tool_result`` derrama, spike §4.7; fora da faixa é
    ``GpErro(EXIT_VALIDACAO)``) e, da 2.ª página em diante,
    ``args[chave_token_pedido] = <token da página anterior>``; resposta SEM
    ``chave_lista`` conta como página vazia; para em ``max_paginas`` com
    ``GpErro(EXIT_VALIDACAO)``. ``kw`` vai para ``chamar`` (inclusive
    ``projecao``, aplicada a cada página antes de extrair a lista).
    """
    if not isinstance(args, dict):
        raise GpErro(EXIT_VALIDACAO, "args da tool %s devem ser um dict" % tool)
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= PAGE_SIZE_MAX:
        raise GpErro(
            EXIT_VALIDACAO, "page_size de %s deve ficar entre 1 e %d, veio %r" % (tool, PAGE_SIZE_MAX, page_size)
        )
    itens: list[Any] = []
    token: Optional[str] = None
    for _ in range(max(1, int(max_paginas))):
        args_pagina = dict(args)
        args_pagina[chave_page_size] = page_size
        if token:
            args_pagina[chave_token_pedido] = token
        else:
            args_pagina.pop(chave_token_pedido, None)
        resposta = chamar(tool, args_pagina, **kw)
        lista = resposta.get(chave_lista)
        if lista is None:
            lista = []
        if not isinstance(lista, list):
            raise RespostaInvalida("%s: %r não é lista na resposta de %s" % (tool, chave_lista, tool))
        itens.extend(lista)
        token = resposta.get(chave_token)
        if not token:
            return itens
        if not isinstance(token, str):
            raise RespostaInvalida("%s: %r não é texto" % (tool, chave_token))
    raise GpErro(EXIT_VALIDACAO, "paginação de %s passou de %d páginas" % (tool, max_paginas))


def gp_key_de(descricao: Any) -> Optional[str]:
    """``gp:<task_id>/<instalacao_id>`` quando a ÚLTIMA linha não vazia de
    ``descricao`` casa ``RE_GP_KEY`` inteira; senão None. Só a chave, nunca
    o resto do texto (conteúdo não confiável)."""
    if not isinstance(descricao, str):
        return None
    linhas = [linha.strip() for linha in descricao.split("\n") if linha.strip()]
    if not linhas:
        return None
    m = RE_GP_KEY.match(linhas[-1])
    return m.group(0) if m else None


def _inicio_fim_google(valor: Any) -> tuple[str, bool]:
    """``(texto, dia_inteiro)`` de um ``start``/``end`` do Google: dict com
    ``dateTime`` (datetime com offset) ou ``date`` (dia inteiro), ou uma
    string já pronta. Sem valor → ``("", False)``."""
    if isinstance(valor, dict):
        if valor.get("dateTime"):
            return str(valor["dateTime"]), False
        if valor.get("date"):
            return str(valor["date"]), True
        return "", False
    if isinstance(valor, str):
        return valor, len(valor) == 10
    return "", False


def _texto_ou_vazio(valor: Any) -> str:
    return valor if isinstance(valor, str) else ""


def _self_response(evento: dict[str, Any]) -> str:
    """``responseStatus`` do convidado marcado ``self`` (vazio se o usuário
    não é convidado, ex.: calendário compartilhado)."""
    for convidado in evento.get("attendees") or []:
        if isinstance(convidado, dict) and convidado.get("self"):
            return _texto_ou_vazio(convidado.get("responseStatus"))
    return ""


def _transparency(evento: dict[str, Any]) -> str:
    valor = evento.get("transparency")
    if isinstance(valor, str) and valor:
        return valor
    if evento.get("availability") == AVAILABILITY_LIVRE:
        return TRANSPARENCY_LIVRE
    return TRANSPARENCY_OCUPADO


def projetar_evento(evento: dict[str, Any], calendar_id: str, calendar_id_metas: str) -> dict[str, Any]:
    """Um evento cru do conector → o ``evento`` compacto de ``schema.py``
    (design doc, seção do proxy): só os campos declarados, ``start``/``end``
    como texto (``all_day`` quando só data), ``self_response`` de
    ``attendees[].self``, ``transparency`` ausente = ocupado, ``gp_key`` de
    ``gp_key_de(description)`` para qualquer calendário e ``summary``/
    ``description`` só quando ``calendar_id == calendar_id_metas`` (fora do
    Metas ficam ``None``). Tudo o mais (attendees, location, htmlLink,
    creator, ...) fica de fora: conteúdo de terceiros nunca entra no cache."""
    start, all_day = _inicio_fim_google(evento.get("start"))
    end, _ = _inicio_fim_google(evento.get("end"))
    dentro = calendar_id == calendar_id_metas
    return {
        "id": _texto_ou_vazio(evento.get("id")),
        "calendar_id": calendar_id,
        "start": start,
        "end": end,
        "all_day": all_day,
        "created": _texto_ou_vazio(evento.get("created")) or None,
        "updated": _texto_ou_vazio(evento.get("updated")) or None,
        "status": _texto_ou_vazio(evento.get("status")) or STATUS_EVENTO_PADRAO,
        "transparency": _transparency(evento),
        "self_response": _self_response(evento),
        "event_type": _texto_ou_vazio(evento.get("eventType")),
        "recurring_event_id": _texto_ou_vazio(evento.get("recurringEventId")),
        **{campo: (_texto_ou_vazio(evento.get(campo)) if dentro else None) for campo in schema.CAMPOS_SO_DO_METAS},
        "gp_key": gp_key_de(evento.get("description")),
    }


def projetar_eventos(resposta: dict[str, Any], calendar_id: str, calendar_id_metas: str) -> dict[str, Any]:
    """Projeção de privacidade de uma resposta de ``list_events``: cada item
    de ``events`` passa por ``projetar_evento`` (itens que não são dict saem
    da lista); as chaves de topo (``nextPageToken``, ``summary`` do
    calendário, ``timeZone``, ``accessRole``) ficam. Devolve um dict novo;
    resposta sem ``events`` volta igual. Use como ``projecao`` de
    ``chamar``/``chamar_paginado`` via ``functools.partial``."""
    saida = dict(resposta)
    eventos = resposta.get("events")
    if not isinstance(eventos, list):
        return saida
    saida["events"] = [
        projetar_evento(evento, calendar_id, calendar_id_metas) for evento in eventos if isinstance(evento, dict)
    ]
    return saida


def _envelope_prosa(resultado: Resultado) -> dict[str, Any]:
    """stdout do ``--output-format json`` → dict (aceita lixo antes do JSON
    final, tomando a última linha não vazia; separador só ``\n``)."""
    texto = resultado.stdout.strip()
    candidatos = [texto]
    linhas = [linha for linha in texto.split("\n") if linha.strip()]
    if linhas:
        candidatos.append(linhas[-1].strip())
    for candidato in candidatos:
        try:
            envelope = json.loads(candidato)
        except ValueError:
            continue
        if isinstance(envelope, dict):
            return envelope
    raise RespostaInvalida(
        "prosa: stdout não é o envelope JSON (código %d): %s" % (resultado.codigo, resultado.stderr.strip()[:200])
    )


def prosa(
    prompt: str,
    *,
    modelo: str = "haiku",
    curta: bool = True,
    timeout_s: float = TIMEOUT_PADRAO_S,
    executar: Optional[Executar] = None,
    registro: Registro = None,
) -> str:
    """Prosa sem ferramentas: devolve ``result`` do envelope json (aqui sim,
    o texto é o dado).

    ``curta=True`` passa ``MAX_THINKING_TOKENS=0`` no env do subprocesso.
    ``is_error`` é ``ProxyErro``; ``error_max_turns`` é ``TurnosEsgotados``;
    ``api_error_status == 429`` é ``RateLimited``; ``registro`` como em
    ``chamar`` (com ``"tool": "prosa"``).
    """
    argv = argv_prosa(prompt, modelo=modelo)
    rodar = executar if executar is not None else executar_padrao
    cwd = base.jobs_dir()
    env: Optional[dict[str, str]] = None
    if curta:
        env = dict(os.environ)
        env["MAX_THINKING_TOKENS"] = "0"
    with _SERIE:
        resultado = rodar(argv, timeout_s=timeout_s, cwd=cwd, env=env)
    envelope = _envelope_prosa(resultado)
    _registrar(registro, _entrada_registro("prosa", envelope, None, resultado, 1, cwd))
    if envelope.get("subtype") == SUBTYPE_MAX_TURNS:
        raise TurnosEsgotados("prosa: turnos esgotados (num_turns=%s)" % envelope.get("num_turns"))
    if envelope.get("permission_denials"):
        raise ToolNegada("prosa: tool negada", denials=envelope.get("permission_denials"))
    if envelope.get("api_error_status") == HTTP_RATE_LIMIT:
        raise RateLimited("api_error_status 429")
    if envelope.get("is_error"):
        raise ProxyErro("prosa com is_error: " + _texto_erro_envelope(envelope))
    texto = envelope.get("result")
    if not isinstance(texto, str):
        raise RespostaInvalida("prosa: result do envelope não é texto")
    return texto
