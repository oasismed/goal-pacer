"""acoes_locais.py: o que o painel só faz no próprio computador, nunca pelo celular na rede.

Primeiros passos (o onboarding pela tela, sem terminal), doctor e atualizar. O web.py confere a origem local e o
token antes de chegar aqui; este módulo não imprime e não conhece HTTP::

    modelo(dados, agora, deteccao)  tela Começar: rascunho, o que o detectar achou, se já está configurado e instalado
    detectar(offline)               onboarding.py --json detectar em subprocesso (conta Google, calendário Metas, fontes)
    salvar_rascunho(respostas)      só as chaves conhecidas das respostas, no rascunho do onboarding
    gravar(dados, agora)            metas completadas (horizonte e semanas pelo prazo) -> onboarding.gravar_respostas
    primeiro_dia()                  dispara o job diário no agendador (o painel não chama conector: o job chama)
    doctor(offline)                 status.py --doctor --json em subprocesso
    estado_da_conta(offline)        Claude Code instalado e logado (claude auth status) e cada conector (claude mcp list),
                                    sem tokens: a tela Começar confere sozinha enquanto a pessoa conecta
    instalar_claude()               o instalador oficial do Claude Code (claude.ai/install.sh ou install.ps1) em sessão
                                    própria, com log; o botão da tela Começar
    iniciar_login / enviar_codigo   claude auth login sem terminal: o navegador faz o login e a tela recebe o código
    iniciar_atualizacao()           instalar.py --update em sessão própria, com a saída num log: o update recarrega o
                                    agente do painel, que morre no meio; o update segue e o painel volta na versão nova
    estado_da_atualizacao()         últimas linhas desse log e se o processo ainda roda

A conta Google só é lida pelo ``detectar`` e pelo ``doctor``, os mesmos CLIs da skill, em subprocesso e com teto.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import onboarding
import painel
from goalpacer import (
    assinatura,
    atalhos,
    base,
    canal,
    clock,
    conexoes,
    copy,
    frontmatter,
    io as gpio,
    plataforma,
    processos,
    proxy,
    schema,
)
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_VALIDACAO, GpErro

SCRIPTS = Path(__file__).resolve().parent
TIMEOUT_DETECTAR_S = 300
TIMEOUT_DOCTOR_S = 240
NOME_LOG_ATUALIZAR = "atualizar-pelo-painel.log"
NOME_LOG_CLAUDE = "instalar-claude.log"
NOME_PID_CLAUDE = "instalar-claude.pid"
TIMEOUT_CONTA_S = 30
# o instalador oficial do Claude Code (https://code.claude.com/docs/en/setup): tudo no HOME, sem administrador
INSTALAR_CLAUDE_POSIX = ["/bin/bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]
INSTALAR_CLAUDE_WINDOWS = "irm https://claude.ai/install.ps1 | iex"
SERVIDORES_DA_CONTA = ("Google_Calendar", "Gmail", "Notion", "Google_Drive")
NOME_PID_ATUALIZAR = "atualizar-pelo-painel.pid"
LINHAS_DO_LOG = 12
CHAVES_RESPOSTAS = frozenset(
    {
        "objetivos",
        "metas",
        "horario_util",
        "calendar_id_metas",
        "calendar_id_primario",
        "calendarios_lidos",
        "lembretes",
        "fontes_ativas",
        "email_proprio",
        "email_alias",
        "timezone",
        "idioma",
        "pessoas",
    }
)


def _instalacao() -> Optional[dict[str, Any]]:
    caminho = base.jobs_dir() / base.NOME_INSTALACAO
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def janela_instalada() -> bool:
    """A janela que o instalador montou ainda está no lugar (Goal Pacer.app no macOS, atalho no Windows)."""
    caminho = (_instalacao() or {}).get("janela")
    return bool(caminho) and Path(caminho).exists()


def claude_encontrado() -> bool:
    """O ``claude`` que os jobs chamam existe: o da instalação, senão o que o ambiente acha."""
    for caminho in ((_instalacao() or {}).get("claude"), proxy.claude_bin()):
        if caminho and os.path.isabs(caminho) and os.path.isfile(caminho):
            return True
    return False


_PASTA_VAZIA: list[Path] = []


def pasta_vazia() -> Path:
    """Pasta temporária só com o contexto mínimo (fuso do sistema, idioma atual, nenhuma meta): as telas do painel
    antes do onboarding mostram valores vazios, nunca dados de exemplo. Uma por processo, apagada na saída."""
    if _PASTA_VAZIA and (_PASTA_VAZIA[0] / schema.CAMINHOS["contexto"]).is_file():
        return _PASTA_VAZIA[0]
    pasta = Path(tempfile.mkdtemp(prefix="goal-pacer-vazio-"))
    atexit.register(shutil.rmtree, str(pasta), True)
    contexto = {
        "schema_version": schema.SCHEMA_VERSION,
        "instalacao_id": "vazio",
        "timezone": getattr(clock.fuso(), "key", "") or "UTC",
        "idioma": copy.atual(),
    }
    gpio.escrever_atomico(
        pasta / schema.CAMINHOS["contexto"], "---\n" + frontmatter.dump(contexto) + "---\n", bak=False
    )
    _PASTA_VAZIA[:] = [pasta]
    return pasta


def _usa_agenda(dados: Path) -> Optional[bool]:
    """Com metas gravadas: se os blocos vão para o Google Calendar; antes disso, ninguém sabe (None)."""
    try:
        contexto, _ = frontmatter.ler_arquivo(dados / schema.CAMINHOS["contexto"])
    except (GpErro, OSError, ValueError):
        return None
    return conexoes.usa_agenda(contexto)


def configurado(dados: Path) -> bool:
    return (dados / schema.CAMINHOS["contexto"]).is_file()


def modelo(dados: Path, agora: datetime, deteccao: Optional[dict[str, Any]]) -> dict[str, Any]:
    instalacao = _instalacao()
    return {
        "textos": painel.textos(),
        "rascunho": onboarding.resumo_rascunho(onboarding.ler_rascunho()),
        "deteccao": deteccao,
        "configurado": configurado(dados),
        "agenda_google": _usa_agenda(dados),
        "instalado": instalacao is not None,
        "janela": janela_instalada(),
        "plataforma": plataforma.nome_atual(),
        "claude": claude_encontrado(),
        "modo_instalacao": (instalacao or {}).get("modo"),
        "versao": base.VERSAO_APP,
        "hoje": agora.date().isoformat(),
        "idioma": copy.atual(),
        "impactos": list(schema.IMPACTOS),
        "teto_metas": onboarding.TETO_METAS,
        "teto_objetivos": onboarding.TETO_OBJETIVOS,
    }


def _rodar_json(argv: list[str], timeout_s: float) -> tuple[int, dict[str, Any]]:
    """Roda um CLI do app com ``--json`` e devolve ``(código, último objeto JSON da saída)``."""
    try:
        proc = subprocess.run(
            [sys.executable, *argv],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_s,
            env=dict(os.environ),
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        raise GpErro(EXIT_IO, "%s passou de %d s" % (Path(argv[0]).name, timeout_s)) from erro
    except OSError as erro:
        raise GpErro(EXIT_IO, "não consegui rodar %s: %s" % (Path(argv[0]).name, erro)) from erro
    corpo = _objeto_json(proc.stdout.strip())
    if not corpo and proc.returncode != 0:
        ultima = (proc.stderr.strip().split("\n") or [""])[-1][:200]
        raise GpErro(proc.returncode if proc.returncode > 0 else EXIT_IO, ultima or "%s falhou" % Path(argv[0]).name)
    return proc.returncode, corpo


def _objeto_json(texto: str) -> dict[str, Any]:
    """A saída inteira como objeto JSON ou, com aviso antes, a última linha que começa com ``{``; senão vazio."""
    candidatos = [texto, *[linha for linha in reversed(texto.split("\n")) if linha.strip().startswith("{")][:1]]
    for candidato in candidatos:
        try:
            corpo = json.loads(candidato)
        except ValueError:
            continue
        return corpo if isinstance(corpo, dict) else {}
    return {}


def detectar(*, offline: bool) -> dict[str, Any]:
    argv = [str(SCRIPTS / "onboarding.py"), "--json", *(["--offline"] if offline else []), "detectar"]
    _codigo, corpo = _rodar_json(argv, TIMEOUT_DETECTAR_S)
    return corpo


def salvar_rascunho(respostas: Any) -> dict[str, Any]:
    if not isinstance(respostas, dict) or not respostas:
        raise ValueError("respostas: esperado objeto com ao menos uma resposta")
    desconhecidas = sorted(set(respostas) - CHAVES_RESPOSTAS)
    if desconhecidas:
        raise ValueError("respostas desconhecidas: %s" % ", ".join(desconhecidas))
    return onboarding.resumo_rascunho(onboarding.salvar_rascunho(respostas))


def gravar(dados: Path, agora: datetime) -> dict[str, Any]:
    """Grava o rascunho. ``onboarding.RespostaInvalida`` sobe com a lista de campos recusados."""
    rascunho = onboarding.ler_rascunho()
    if rascunho is None:
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_sem_rascunho"))
    respostas = dict(rascunho.get("respostas") or {})
    hoje = agora.date()
    respostas["metas"] = [
        onboarding.completar_meta(meta, hoje) if isinstance(meta, dict) else meta
        for meta in respostas.get("metas") or []
    ]
    return onboarding.gravar_respostas(respostas, dados)


def primeiro_dia() -> str:
    if _instalacao() is None:
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_sem_instalacao"))
    erro = plataforma.atual().agendador.iniciar(plataforma.JOBS[0])
    if erro:
        raise GpErro(EXIT_IO, copy.texto("painel.comecar_primeiro_dia_erro", erro=erro))
    return copy.texto("painel.comecar_primeiro_dia_ok")


def doctor(*, offline: bool) -> dict[str, Any]:
    argv = [str(SCRIPTS / "status.py"), "--doctor", "--json", *(["--offline"] if offline else [])]
    _codigo, corpo = _rodar_json(argv, TIMEOUT_DOCTOR_S)
    if "itens" not in corpo:
        raise GpErro(EXIT_IO, "o doctor não devolveu a lista de itens")
    return {"ok": bool(corpo.get("ok")), "itens": corpo["itens"]}


def _pid_vivo(caminho: Path) -> bool:
    try:
        pid = int(caminho.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return processos.vivo(pid)


def iniciar_atualizacao() -> str:
    instalacao = _instalacao()
    if instalacao is None:
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_sem_instalacao"))
    app = Path(str(instalacao.get("app") or ""))
    if instalacao.get("modo") != "clone" and canal.endereco(app) is None:
        raise GpErro(EXIT_VALIDACAO, copy.texto("painel.atualizar_pelo_zip"))
    logs = base.jobs_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    marca = logs / NOME_PID_ATUALIZAR
    if _pid_vivo(marca):
        return copy.texto("painel.atualizar_em_andamento")
    with open(logs / NOME_LOG_ATUALIZAR, "w", encoding="utf-8") as saida:
        processo = subprocess.Popen(
            [sys.executable, str(SCRIPTS / "instalar.py"), "--update", "--nao-interativo"],
            stdin=subprocess.DEVNULL,
            stdout=saida,
            stderr=subprocess.STDOUT,
            env=dict(os.environ),
            **processos.desligado(),  # o reload do agente do painel mata o grupo do painel, não este processo
        )
    marca.write_text(str(processo.pid), encoding="utf-8")
    return copy.texto("painel.atualizar_iniciado")


def _caminho_do_claude() -> Optional[str]:
    for caminho in ((_instalacao() or {}).get("claude"), proxy.claude_bin(), proxy.claude_bin_padrao()):
        if caminho and os.path.isabs(caminho) and os.path.isfile(caminho):
            return caminho
    return None


def _rodar_texto(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_CONTA_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return -1, str(erro)
    return proc.returncode, proc.stdout


def estado_da_conta(*, offline: bool) -> dict[str, Any]:
    """O que a tela Começar mostra sem gastar token: Claude Code (instalado, logado, plano) e o estado de cada conector
    do claude.ai. Conector desconectado não é erro: conectar é opcional."""
    logs = base.jobs_dir() / "logs"
    claude: dict[str, Any] = {
        "instalado": False,
        "logado": False,
        "plano": None,
        "instalando": _pid_vivo(logs / NOME_PID_CLAUDE),
    }
    conectores = dict.fromkeys(SERVIDORES_DA_CONTA, "desconectado")
    caminho = "offline" if offline else _caminho_do_claude()
    if caminho is None:
        return {"claude": claude, "conectores": conectores}
    if offline:
        auth, lista = {"loggedIn": True, "subscriptionType": "max"}, offline_texto("mcp_list.txt")
    else:
        codigo, saida = _rodar_texto([caminho, "auth", "status", "--json"])
        auth = _objeto_json(saida) if codigo in (0, 1) else {}
        lista = _rodar_texto([caminho, "mcp", "list"])[1] if auth.get("loggedIn") else ""
    claude.update(instalado=True, logado=bool(auth.get("loggedIn")), plano=auth.get("subscriptionType"))
    for servidor, bruto in proxy.status_de_mcp_list(lista).items():
        if servidor in conectores:
            conectores[servidor] = "conectado" if "connected" in bruto.lower() else "reconectar"
    return {"claude": claude, "conectores": conectores}


def offline_texto(nome: str) -> str:
    from goalpacer import offline

    return offline.texto(nome)


def instalar_claude() -> str:
    """Roda o instalador oficial em sessão própria (sobrevive ao painel), com a saída num log em jobs/logs."""
    if _caminho_do_claude():
        return copy.texto("painel.comecar_claude_ok")
    logs = base.jobs_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    marca = logs / NOME_PID_CLAUDE
    if _pid_vivo(marca):
        return copy.texto("painel.comecar_claude_instalando")
    argv = INSTALAR_CLAUDE_POSIX
    if processos.WINDOWS:
        argv = [atalhos.powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", INSTALAR_CLAUDE_WINDOWS]
    with open(logs / NOME_LOG_CLAUDE, "w", encoding="utf-8") as saida:
        processo = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT, **processos.desligado()
        )
    marca.write_text(str(processo.pid), encoding="utf-8")
    return copy.texto("painel.comecar_claude_instalando")


RE_URL_LOGIN = re.compile(r"https://\S+/oauth/authorize\?\S+")
RE_CODIGO_LOGIN = re.compile(r"[A-Za-z0-9._~#-]{8,512}")
RE_URL_QUALQUER = re.compile(r"https?://\S+")
ESPERA_URL_S = 10.0
ESPERA_CODIGO_S = 90.0
TETO_LOGIN_S = 15 * 60


class Login:
    """``claude auth login`` sem terminal. O Claude Code abre o navegador (e escreve o endereço, que a tela mostra
    também) e espera, pela entrada padrão, o código que a página de login mostra depois de entrar; a tela Começar tem
    o campo onde a pessoa cola esse código. O código nunca é guardado nem registrado."""

    def __init__(self, processo: subprocess.Popen) -> None:
        self.processo = processo
        self.comeco = time.monotonic()
        self.saida = ""
        self.url: Optional[str] = None
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self) -> None:
        fluxo = self.processo.stdout
        while fluxo is not None:
            pedaco = os.read(fluxo.fileno(), 4096)
            if not pedaco:
                return
            self.saida += pedaco.decode("utf-8", errors="replace")
            achado = RE_URL_LOGIN.search(self.saida)
            if achado and self.url is None:
                self.url = achado.group(0)

    def vivo(self) -> bool:
        return self.processo.poll() is None and time.monotonic() - self.comeco < TETO_LOGIN_S

    def encerrar(self) -> None:
        if self.processo.poll() is None:
            self.processo.kill()


def iniciar_login(servidor: Any) -> Optional[str]:
    """Começa (ou retoma) o login do Claude Code e devolve o endereço da página de login, quando o Claude Code o
    escreveu a tempo."""
    caminho = _caminho_do_claude()
    if caminho is None:
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_claude_falta"))
    atual: Optional[Login] = getattr(servidor, "login", None)
    if atual is None or not atual.vivo():
        if atual is not None:
            atual.encerrar()
        processo = subprocess.Popen(
            [caminho, "auth", "login", "--claudeai"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        atual = Login(processo)
        servidor.login = atual
    limite = time.monotonic() + ESPERA_URL_S
    while atual.url is None and atual.processo.poll() is None and time.monotonic() < limite:
        time.sleep(0.1)
    return atual.url


def enviar_codigo(servidor: Any, codigo: Any) -> str:
    """Entrega ao ``claude auth login`` o código colado na tela e espera a resposta."""
    atual: Optional[Login] = getattr(servidor, "login", None)
    if atual is None or not atual.vivo():
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_login_expirado"))
    texto = codigo.strip() if isinstance(codigo, str) else ""
    if not RE_CODIGO_LOGIN.fullmatch(texto):
        raise ValueError(copy.texto("painel.comecar_login_codigo_invalido"))
    stdin = atual.processo.stdin
    if stdin is None:
        raise GpErro(EXIT_IO, copy.texto("painel.comecar_login_expirado"))
    stdin.write((texto + "\n").encode("utf-8"))
    stdin.flush()
    try:
        codigo_saida = atual.processo.wait(timeout=ESPERA_CODIGO_S)
    except subprocess.TimeoutExpired:
        atual.encerrar()
        codigo_saida = -1
    servidor.login = None
    if codigo_saida == 0:
        return copy.texto("painel.comecar_login_ok")
    linhas = [RE_URL_QUALQUER.sub("", linha).strip() for linha in atual.saida.splitlines()]
    detalhe = next((linha for linha in reversed(linhas) if linha), "")[:160]
    raise GpErro(EXIT_VALIDACAO, copy.texto("painel.comecar_login_recusado", erro=detalhe or "sem resposta"))


NOME_LOG_DESINSTALAR = "desinstalar-pelo-painel.log"


def iniciar_desinstalacao() -> str:
    """Remove o Goal Pacer deste computador sem terminal: jobs, painel, atalhos e janela; metas e registro ficam.
    No Windows instalado pelo Setup.exe, roda o desinstalador dele (que também tira o registro em Aplicativos)."""
    instalacao = _instalacao()
    if instalacao is None:
        raise GpErro(EXIT_ESTADO, copy.texto("painel.comecar_sem_instalacao"))
    logs = base.jobs_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    desinstalador = Path(str(instalacao.get("de_app") or "")).parent / "Desinstalar Goal Pacer.exe"
    if processos.WINDOWS and desinstalador.is_file():
        argv = [str(desinstalador), "/S"]
    else:
        python = str(instalacao.get("python3") or sys.executable)
        argv = [
            python,
            str(Path(str(instalacao["app"])) / "scripts" / "instalar.py"),
            "--uninstall",
            "--nao-interativo",
        ]
    with open(logs / NOME_LOG_DESINSTALAR, "w", encoding="utf-8") as saida:
        subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT, **processos.desligado()
        )
    return copy.texto("painel.manutencao_removendo", dados=instalacao.get("dados") or "")


NOME_CANAL = "canal.json"


def versao_nova(*, abrir: Any = None) -> Optional[str]:
    """A versão nova que o canal anuncia (assinatura conferida), perguntando no máximo uma vez por dia; sem canal, sem
    instalação ou sem rede, None. Guarda só a data e a versão em jobs/canal.json."""
    instalacao = _instalacao() or {}
    app = Path(str(instalacao.get("app") or ""))
    if not instalacao or canal.endereco(app) is None:
        return None
    marca = base.jobs_dir() / NOME_CANAL
    hoje = clock.agora().date().isoformat()
    try:
        guardado = json.loads(marca.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        guardado = {}
    if not isinstance(guardado, dict) or guardado.get("verificado_em") != hoje:
        guardado = {"verificado_em": hoje, "versao": _perguntar_ao_canal(app, abrir)}
        gpio.escrever_atomico(marca, json.dumps(guardado) + "\n", bak=False)
    anunciada = assinatura.versao_de(str(guardado.get("versao") or ""))
    return guardado["versao"] if anunciada and anunciada > assinatura.versao_instalada(app) else None


def _perguntar_ao_canal(app: Path, abrir: Any) -> Optional[str]:
    with tempfile.TemporaryDirectory(prefix="goal-pacer-canal-") as pasta:
        try:
            dados = canal.ultima(app, Path(pasta), **({"abrir": abrir} if abrir else {}))
        except GpErro:
            return None
    return "%d.%d.%d" % dados["versao_tupla"] if dados else None


def estado_da_atualizacao() -> dict[str, Any]:
    logs = base.jobs_dir() / "logs"
    try:
        linhas = (logs / NOME_LOG_ATUALIZAR).read_text(encoding="utf-8").strip().split("\n")
    except OSError:
        linhas = []
    return {
        "rodando": _pid_vivo(logs / NOME_PID_ATUALIZAR),
        "linhas": [linha for linha in linhas if linha.strip()][-LINHAS_DO_LOG:],
        "versao": (_instalacao() or {}).get("versao") or base.VERSAO_APP,
    }
