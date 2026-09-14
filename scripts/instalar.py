#!/usr/bin/env python3
"""instalar.py: instalação, --check, --update e --uninstall do Goal Pacer (T9/T18; CEO 1.1, 3.4, 9.1; eng 1.4, 3.3).

Chamado por ``install.sh`` (macOS e Linux) ou por ``Instalar Goal Pacer.cmd`` (Windows), que escolhem o Python.
Raiz única ``GP_RAIZ`` ou ``~/.goal-pacer``::

    app/     clone da origem (git clone) ou cópia da árvore de trabalho (--copiar)
             ~/.claude/skills/goal-pacer -> app/ (symlink; junção no Windows)
    bin/     goal-pacer (comando único; ~/.local/bin/goal-pacer -> bin/goal-pacer quando a pasta existe;
             goal-pacer.cmd no Windows)
    dados/   pasta de dados; com --dados fora da raiz, dados/ vira symlink (junção) para ela
    vendor/  só no Windows: tzdata, a base de fusos IANA que o Python de lá não traz
    jobs/    arquivos do agendador renderizados, logs/, instalacao.json (cwd dos claude -p)

Instalar::

    valida caminhos (absolutos, sem aspas nem quebra de linha; no macOS, raiz e dados fora de Desktop/Downloads/Documents)
    -> app (clone ou cópia) -> symlink da skill -> dados/ (0700) -> jobs agendados pela plataforma
       (goalpacer.plataforma: launchd no macOS, systemd --user no Linux, Agendador de Tarefas no Windows; arquivos
       conferidos depois de renderizados) -> janela (Goal Pacer.app no macOS, atalho no menu Iniciar no Windows)
    -> instalacao.json -> --check

Sem o Claude Code, instala do mesmo jeito e avisa: os jobs apontam para onde o instalador oficial põe o ``claude``, e
a tela Começar do painel mostra o que falta. ``--instalar-ou-atualizar`` é o clique duplo no instalador: sem
instalação, instala; com instalação, atualiza (clone: as tags do remoto; cópia: a pasta baixada, que precisa ser uma
versão publicada, com ``release/manifesto.json`` assinado) e, já em dia, só reaplica o que falta.

``--check``: python3 e Xcode CLT, claude, conectores (claude mcp list; calendário
Metas e sonda de escrita só depois do onboarding e com ``--sondar-escrita``).
``--update`` é tudo ou nada::

    lock da pasta de dados -> app sem mudanças locais?
    -> versão publicada: clone = maior tag vX.Y.Z acima da instalada, assinada por alguém de release/assinantes
       (a lista da versão instalada), com o HEAD dentro dela; cópia = zip com .sig conferido, pasta de uma versão
       publicada (manifesto assinado; só os arquivos listados, com sha256 conferido) ou, em desenvolvimento, a árvore
       de trabalho com --copiar (sem assinatura, com aviso)
    -> nenhuma versão nova: nada muda -> backup zip dos dados (backups/, os 5 mais novos)
    -> git checkout da tag (ou nova cópia, com a anterior guardada em app.anterior)
    -> autoteste.py do código novo (offline, sem tokens) -> migrar.py --aplicar
    -> falhou até aqui: o app volta ao commit (ou à cópia) anterior e os jobs seguem na versão de antes
    -> instalar.py --reaplicar da versão nova (comando, permissões, agendador, janela) -> status --doctor ``--uninstall``:
descarrega os jobs, remove os arquivos do agendador e o symlink, ``diario.py --desinstalar``
(blocos só desta instalação, com confirmação ou ``--apagar-blocos``),
``--apagar-cache`` apaga cache/ e sinais/; metas, planos e registro ficam.

O job ``painel`` deixa o painel sempre no ar: ``web.py --local`` por padrão (o endereço fixo
http://127.0.0.1:8765/, que o navegador instala como app), ``--painel-rede`` troca por ``web.py --rede``
(o celular no Wi-Fi de casa) e ``--sem-painel`` desliga o job; ``--update`` mantém a escolha gravada.

Variáveis para teste: ``GP_RAIZ``, ``HOME``, ``CLAUDE_CONFIG_DIR``, ``GP_PLATAFORMA``, ``GP_LAUNCHCTL``,
``GP_SYSTEMCTL``, ``GP_CLAUDE_BIN``, ``GP_GIT``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import (
    assinatura,
    atalhos,
    base,
    canal,
    clock,
    copy,
    janela,
    migracoes,
    plataforma,
    processos,
    provedor,
    proxy,
    registro as reg,
    schema,
    seguranca,
)
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_VALIDACAO, GpErro

ENV_GIT = "GP_GIT"  # testes: git de mentira
NOME_SKILL = "goal-pacer"
NOME_COMANDO = "goal-pacer"
NOME_INSTALACAO = base.NOME_INSTALACAO
# Quebram plist, shell, .cmd ou PowerShell. No Windows a barra invertida é o separador, e o % expande no .cmd.
CARACTERES_PROIBIDOS = ('"', "'", "\n", "\r", "\t", "`", "$") + (("%",) if processos.WINDOWS else ("\\",))
ENDERECO_PAINEL = "http://127.0.0.1:8765/"
# tzdata com hash fixo (pip --require-hashes): o Python do Windows não traz a base de fusos que o zoneinfo lê
TZDATA = "tzdata==2026.4 --hash=sha256:c2169a8b0a7a5e9674da5a135ccdfb2b3e671b333ed9fed17b41f73c34476e81"
FUSO_DE_PROVA = "America/Sao_Paulo"
IGNORAR_EM_TODO_LUGAR = shutil.ignore_patterns(
    ".git", "__pycache__", "*.pyc", ".pytest_cache", ".DS_Store", ".run.lock", "*.bak*"
)
IGNORAR_NA_RAIZ = {
    "dados",
    "inbox",
    "logs",
}  # dados de usuário e logs nunca vão para o app (mesmo que existam na origem)
# ficam no repositório, nunca na instalação: sondagens do spike (evidência) e ferramentas de desenvolvimento
IGNORAR_RELATIVO = {("jobs", "spike"), ("dev",)}
ESPARSO = (
    "/*",
    "!/jobs/spike/",
    "!/dev/",
)  # o clone instalado usa sparse-checkout com os mesmos cortes (o git status segue limpo)


def ignorar_copia(origem: Path):
    raiz = origem.resolve()

    def filtro(pasta: str, nomes: list[str]) -> set[str]:
        ignorados = set(IGNORAR_EM_TODO_LUGAR(pasta, nomes))
        relativo = Path(pasta).resolve().relative_to(raiz).parts
        if not relativo:
            ignorados |= IGNORAR_NA_RAIZ & set(nomes)
        for caminho in IGNORAR_RELATIVO:
            if tuple(relativo) == caminho[:-1] and caminho[-1] in nomes:
                ignorados.add(caminho[-1])
        return ignorados

    return filtro


def dizer(chave: str, **valores: Any) -> None:
    print(copy.texto("instalar." + chave, **valores))


def _rodar3(
    argv: list[str], *, cwd: Optional[Path] = None, timeout_s: float = 120, env: Optional[dict] = None
) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else None,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return -1, "", str(erro)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _rodar(
    argv: list[str], *, cwd: Optional[Path] = None, timeout_s: float = 120, env: Optional[dict] = None
) -> tuple[int, str]:
    codigo, saida, erro = _rodar3(argv, cwd=cwd, timeout_s=timeout_s, env=env)
    return codigo, "\n".join(p for p in (saida, erro) if p)


def git() -> str:
    return os.environ.get(ENV_GIT) or shutil.which("git") or "/usr/bin/git"


def git_disponivel() -> bool:
    """git que roda de verdade (no macOS sem Command Line Tools o /usr/bin/git só abre o instalador da Apple)."""
    binario = git()
    if not os.path.isfile(binario):
        return False
    if binario == "/usr/bin/git" and plataforma.atual().precisa_xcode:
        xcode = os.environ.get(plataforma.ENV_XCODE_SELECT) or "/usr/bin/xcode-select"
        if _rodar([xcode, "-p"])[0] != 0:
            return False
    return _rodar([binario, "--version"])[0] == 0


# --- caminhos -----------------------------------------------------------------------------


def validar_caminho(path: Path, rotulo: str, *, tcc: bool = True) -> Path:
    """Absoluto (sem resolver symlinks), sem caracteres que quebram plist/shell, fora das pastas TCC."""
    absoluto = Path(os.path.abspath(Path(path).expanduser()))
    texto = str(absoluto)
    ruins = [c for c in CARACTERES_PROIBIDOS if c in texto] + [c for c in texto if ord(c) < 32]
    if ruins:
        proibido = "%" if processos.WINDOWS else "barra invertida"
        raise GpErro(
            EXIT_VALIDACAO, "%s não pode ter aspas, %s, $, crase ou quebra de linha: %r" % (rotulo, proibido, texto)
        )
    if tcc and plataforma.dir_tcc_proibido(absoluto):
        raise GpErro(EXIT_VALIDACAO, "%s não pode ficar em %s: %s" % (rotulo, "/".join(plataforma.PASTAS_TCC), texto))
    return absoluto


def link_comando() -> Path:
    return Path.home() / ".local" / "bin" / NOME_COMANDO


def _texto_do_cmd(raiz: Path, app: Path, python3: str) -> tuple[str, str]:
    """``(conteúdo, encoding)`` do ``goal-pacer.cmd``. O cmd lê o arquivo na página de código do console: caminho
    fora do ASCII (usuário com acento) troca a página para UTF-8 antes da linha que o usa."""
    script = (
        r"%~dp0..\app\scripts\goal_pacer.py" if app == raiz / base.NOME_APP else str(app / "scripts" / "goal_pacer.py")
    )
    linhas = ["@echo off", "rem gerado pelo instalador do Goal Pacer", 'set "PYTHONUTF8=1"']
    if not python3.isascii() or not script.isascii():
        linhas.append("chcp 65001 >nul")
    linhas.append('"%s" "%s" %%*' % (python3, script))
    return "\r\n".join(linhas) + "\r\n", "utf-8"


def _no_path(pasta: Path) -> bool:
    normalizar = os.path.normcase if processos.WINDOWS else str
    return normalizar(str(pasta)) in {normalizar(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p}


def instalar_comando(raiz: Path, app: Path, python3: str) -> str:
    """``raiz/bin/goal-pacer`` (``goal-pacer.cmd`` no Windows) chama ``scripts/goal_pacer.py`` com o Python escolhido;
    devolve como chamar."""
    if processos.WINDOWS:
        shim = raiz / "bin" / (NOME_COMANDO + ".cmd")
        shim.parent.mkdir(parents=True, exist_ok=True)
        texto, codificacao = _texto_do_cmd(raiz, app, python3)
        with open(shim, "w", encoding=codificacao, newline="") as arquivo:
            arquivo.write(texto)
        if _no_path(shim.parent):
            dizer("comando", pasta=shim.parent)
            return NOME_COMANDO
        dizer("comando_fora_do_path", shim=shim, pasta=shim.parent)
        return str(shim)
    shim = raiz / "bin" / NOME_COMANDO
    shim.parent.mkdir(parents=True, exist_ok=True)
    # caminhos já passaram por validar_caminho: sem aspas, $, crase nem barra invertida
    shim.write_text(
        '#!/bin/sh\n# gerado pelo install.sh do Goal Pacer\nexec "%s" "%s" "$@"\n'
        % (python3, app / "scripts" / "goal_pacer.py"),
        encoding="utf-8",
    )
    os.chmod(str(shim), 0o755)  # noqa: S103 - executável; só o dono altera (sem escrita de grupo e outros)
    link = link_comando()
    nosso = link.is_symlink() and os.readlink(str(link)) == str(shim)
    if link.parent.is_dir() and (nosso or not (link.exists() or link.is_symlink())):
        if nosso:
            link.unlink()
        link.symlink_to(shim)
        if _no_path(link.parent):
            dizer("comando", pasta=link.parent)
            return NOME_COMANDO
    dizer("comando_fora_do_path", shim=shim, pasta=shim.parent)
    return str(shim)


def remover_comando(raiz: Path) -> None:
    shim = raiz / "bin" / NOME_COMANDO
    link = link_comando()
    if link.is_symlink() and os.readlink(str(link)) == str(shim):
        link.unlink()
    removidos = [p for p in (shim, shim.with_name(NOME_COMANDO + ".cmd")) if p.exists()]
    for path in removidos:
        path.unlink()
    if removidos:
        dizer("uninstall_comando", comando=NOME_COMANDO)
    if shim.parent.is_dir() and not any(shim.parent.iterdir()):
        shim.parent.rmdir()


def link_skill() -> Path:
    return proxy.claude_config_dir() / "skills" / NOME_SKILL


def caminho_instalacao() -> Path:
    return base.jobs_dir() / NOME_INSTALACAO


def ler_instalacao() -> Optional[dict[str, Any]]:
    path = caminho_instalacao()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


# --- app e skill --------------------------------------------------------------------------


def eh_repo_git(path: Path) -> bool:
    return (path / ".git").exists()


def preparar_app(origem: str, app: Path, *, copiar: bool, recopiar: bool = False) -> str:
    """Clona ou copia a origem para ``app``; devolve o modo (``clone``/``copia``).

    Pasta local sem ``.git`` (zip baixado do GitHub) ou máquina sem git vira cópia sozinha:
    instalar nunca depende de ter git; só o ``--update`` por pull depende."""
    local = Path(origem).expanduser()
    if not copiar and local.is_dir() and not (eh_repo_git(local) and git_disponivel()):
        publicada = (local / assinatura.ARQUIVO_MANIFESTO).is_file()
        dizer("origem_publicada" if publicada else "origem_sem_git", origem=local.resolve())
        copiar = True
    if copiar:
        return _copiar_app(origem, local, app, recopiar=recopiar)
    if app.exists():
        dizer("app_existente", app=app)
        return "clone" if eh_repo_git(app) else "copia"
    _clonar_app(origem, local, app)
    return "clone"


def _copiar_app(origem: str, local: Path, app: Path, *, recopiar: bool) -> str:
    if not local.is_dir():
        raise GpErro(EXIT_VALIDACAO, "--copiar pede uma pasta local: %s" % origem)
    if app.exists() and not recopiar:
        dizer("app_existente", app=app)
        return "copia"
    app.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(local.resolve()), str(app), ignore=ignorar_copia(local), dirs_exist_ok=True, symlinks=True)
    dizer("app_copiado", origem=local.resolve(), app=app)
    return "copia"


def _clonar_app(origem: str, local: Path, app: Path) -> None:
    """Clone sem checkout, sparse-checkout sem o spike e o dev/ (git antigo: clone completo) e checkout."""
    fonte = str(local.resolve()) if local.is_dir() else origem
    if local.is_dir():
        codigo, saida = _rodar([git(), "-C", fonte, "status", "--porcelain"])
        if codigo == 0 and saida:
            dizer("origem_suja", origem=fonte)
    app.parent.mkdir(parents=True, exist_ok=True)
    codigo, saida = _rodar([git(), "clone", "--quiet", "--no-checkout", fonte, str(app)], timeout_s=600)
    if codigo != 0:
        raise GpErro(EXIT_IO, "git clone de %s não concluiu: %s" % (fonte, saida[-300:]))
    if _rodar([git(), "-C", str(app), "sparse-checkout", "set", "--no-cone", *ESPARSO])[0] != 0:
        _rodar([git(), "-C", str(app), "sparse-checkout", "disable"])  # git antigo: clone completo, só mais arquivos
    codigo, saida = _rodar([git(), "-C", str(app), "checkout", "--quiet"], timeout_s=600)
    if codigo != 0:
        raise GpErro(EXIT_IO, "git checkout em %s não concluiu: %s" % (app, saida[-300:]))
    remoto = _remoto_da_origem(local)
    if remoto:
        _rodar([git(), "-C", str(app), "remote", "set-url", "origin", remoto])
    dizer("app_clonado", origem=remoto or fonte, app=app)


def _remoto_da_origem(local: Path) -> str:
    """URL do ``origin`` do clone de onde o app veio (o GitHub, para quem clonou de lá): o ``--update`` busca as
    versões ali, e não na pasta baixada, que não muda sozinha. Pasta sem remoto (desenvolvimento) fica como está."""
    if not local.is_dir():
        return ""
    codigo, saida = _rodar([git(), "-C", str(local), "remote", "get-url", "origin"])
    return saida.strip() if codigo == 0 else ""


def ligar_skill(app: Path) -> Path:
    link = link_skill()
    link.parent.mkdir(parents=True, exist_ok=True)
    if plataforma.eh_ligacao(link):
        plataforma.desligar(link)
    elif link.exists():
        raise GpErro(
            EXIT_VALIDACAO, "%s já existe e não é um symlink do Goal Pacer; mova ou apague antes de instalar" % link
        )
    plataforma.ligar_pasta(link, app)
    dizer("skill", link=link, app=app)
    return link


def preparar_dados(raiz: Path, dados: Path) -> Path:
    padrao = raiz / base.NOME_DADOS
    dados.mkdir(parents=True, exist_ok=True)
    if Path(os.path.abspath(dados)) != Path(os.path.abspath(padrao)):
        if plataforma.eh_ligacao(padrao):
            plataforma.desligar(padrao)
        elif padrao.exists():
            if any(padrao.iterdir()):
                raise GpErro(EXIT_VALIDACAO, "%s já tem dados; para usar %s mova o conteúdo antes" % (padrao, dados))
            padrao.rmdir()
        plataforma.ligar_pasta(padrao, dados)
    for sub in ("inbox/whatsapp",):
        (dados / sub).mkdir(parents=True, exist_ok=True)
    dizer("dados", dados=dados)
    return dados


# --- agendador (launchd no macOS, systemd --user no Linux) -------------------------------


def gerar_agendamento(
    app: Path, raiz: Path, dados: Path, python3: str, claude: str, *, modo_painel: str = "local"
) -> dict[str, list[Path]]:
    jobs = raiz / base.NOME_JOBS
    (jobs / "logs").mkdir(parents=True, exist_ok=True)
    valores = {
        "PYTHON3": python3,
        "APP": str(app),
        "JOBS": str(jobs),
        "RAIZ": str(raiz),
        "DADOS": str(dados),
        "CLAUDE": claude,
    }
    gerados = plataforma.atual().agendador.gerar(app, jobs, valores, modo_painel)
    dizer("agendamento", arquivos=", ".join(str(p) for paths in gerados.values() for p in paths))
    return gerados


def carregar_agendamento(arquivos: dict[str, list[Path]]) -> list[str]:
    agendador = plataforma.atual().agendador
    falhas = agendador.carregar(arquivos)
    for label in falhas:
        dizer("agendador_aviso", agendador=agendador.nome, label=label)
    if not falhas:
        dizer("agendador_ok", agendador=agendador.nome, labels=", ".join(arquivos))
    return falhas


def descarregar_agendamento(jobs: tuple = (*plataforma.JOBS, plataforma.PAINEL)) -> list[str]:
    agendador = plataforma.atual().agendador
    return agendador.descarregar([agendador.label(j) for j in jobs], base.jobs_dir())


# --- modos --------------------------------------------------------------------------------


def provedor_escolhido(nome: str) -> str:
    """O provedor pedido em ``--provedor``; um provedor sem conectores não instala (o app não roda o dia sem eles)."""
    escolhido = provedor.por_nome(nome)
    if not escolhido.conectores:
        raise GpErro(
            EXIT_VALIDACAO,
            "--provedor %s: Calendar e Gmail pelo %s dependem do spike dos conectores; "
            "hoje o Codex só escreve a prosa, com GP_PROVEDOR=%s" % (nome, escolhido.rotulo, escolhido.nome),
        )
    return escolhido.nome


def claude_encontrado(caminho: str) -> bool:
    return os.path.isabs(caminho) and os.path.isfile(caminho) and os.access(caminho, os.X_OK)


def claude_para_agendar(anterior: str = "") -> str:
    """O ``claude`` que os jobs vão chamar. Sem o Claude Code, instala do mesmo jeito: vale o caminho onde o
    instalador oficial põe o binário, com um aviso (a tela Começar e o doctor mostram o que falta)."""
    for caminho in (anterior, proxy.claude_bin()):
        if caminho and claude_encontrado(caminho):
            return caminho
    esperado = proxy.claude_bin_padrao()
    dizer("claude_ausente", caminho=esperado)
    return esperado


def garantir_fusos(raiz: Path, python3: str) -> None:
    """No Windows o Python não traz a base de fusos IANA: ``pip install tzdata`` (hash fixo) em ``raiz/vendor``, que
    o ``goalpacer`` põe no ``sys.path``. Nos outros sistemas, ou com a base já presente, nada acontece."""
    if not processos.WINDOWS or _fusos_ok():
        return
    vendor = raiz / "vendor"
    with tempfile.TemporaryDirectory(prefix="goal-pacer-fusos-") as pasta:
        requisitos = Path(pasta) / "requisitos.txt"
        requisitos.write_text(TZDATA + "\n", encoding="utf-8")
        argv = [python3, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--quiet"]
        argv += [
            "--only-binary",
            ":all:",
            "--require-hashes",
            "--upgrade",
            "--target",
            str(vendor),
            "-r",
            str(requisitos),
        ]
        codigo, saida = _rodar(argv, timeout_s=600)
    if str(vendor) not in sys.path:
        sys.path.append(str(vendor))
    if codigo != 0 or not _fusos_ok():
        raise GpErro(EXIT_IO, copy.texto("instalar.fusos_erro", erro=(saida.strip().split("\n") or [""])[-1][:200]))
    dizer("fusos_ok", pasta=vendor)


def _fusos_ok() -> bool:
    import importlib

    importlib.invalidate_caches()
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(FUSO_DE_PROVA)
    except Exception:  # noqa: BLE001 - ZoneInfoNotFoundError ou a base incompleta: sem fusos
        return False
    return True


def revisao(app: Path) -> str:
    if not eh_repo_git(app):
        return "copia"
    codigo, saida = _rodar([git(), "-C", str(app), "rev-parse", "--short", "HEAD"])
    return saida if codigo == 0 else "?"


def gravar_instalacao(dados: dict[str, Any]) -> None:
    path = caminho_instalacao()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(str(path), seguranca.MODO_ARQUIVO_PRIVADO)


def endurecer(raiz: Path, app: Path, dados: Path) -> None:
    """Código só alterável pelo dono; raiz, jobs, logs e dados 0700; arquivos de jobs com segredo 0600."""
    jobs = raiz / base.NOME_JOBS
    seguranca.endurecer(app, [raiz, jobs, jobs / "logs", dados], [caminho_instalacao(), jobs / "painel-aparelhos.json"])


def instalar(args: argparse.Namespace) -> int:
    raiz = validar_caminho(base.raiz(), "a raiz da instalação")
    dizer("inicio", raiz=raiz)
    app = raiz / base.NOME_APP
    padrao = raiz / base.NOME_DADOS
    escolhido = args.dados
    if escolhido is None and not args.nao_interativo:
        resposta = input(copy.texto("instalar.pergunta_dados", padrao=padrao) + " ").strip()
        escolhido = Path(resposta) if resposta else None
    dados = validar_caminho(escolhido or padrao, "a pasta de dados")
    nome_provedor = provedor_escolhido(args.provedor)
    python3 = validar_caminho(Path(python_para_jobs(raiz, args.de_app)), "o caminho do python3", tcc=False)
    if tuple(sys.version_info[:2]) < (3, 9):
        raise GpErro(EXIT_VALIDACAO, "python3 %d.%d é antigo: use 3.9 ou mais novo" % sys.version_info[:2])
    claude = str(validar_caminho(Path(claude_para_agendar()), "o caminho do claude", tcc=False))
    origem = args.origem or args.origem_padrao or str(Path(__file__).resolve().parent.parent)
    garantir_fusos(raiz, str(python3))
    modo = preparar_app(origem, app, copiar=args.copiar, recopiar=args.copiar)
    ligar_skill(app)
    comando = instalar_comando(raiz, app, str(python3))
    preparar_dados(raiz, dados)
    modo_painel = "" if args.sem_painel else "rede" if args.painel_rede else "local"
    arquivos = gerar_agendamento(app, raiz, dados, str(python3), claude, modo_painel=modo_painel)
    endurecer(raiz, app, dados)
    avisos = _agendar(args, arquivos, modo_painel)
    janela_do_app = args.de_app if args.de_app and plataforma.nome_atual() == "macos" else ""
    caminho_janela = instalar_janela(app, raiz, str(python3), sem_janela=args.sem_janela, janela_do_app=janela_do_app)
    gravar_instalacao(
        {
            "raiz": str(raiz),
            "app": str(app),
            "dados": str(dados),
            "jobs": str(raiz / base.NOME_JOBS),
            "python3": str(python3),
            "claude": claude,
            "provedor": nome_provedor,
            "origem": origem,
            "modo": modo,
            "revisao": revisao(app),
            "versao": _texto_versao(assinatura.versao_instalada(app)),
            "plataforma": plataforma.nome_atual(),
            "labels": list(arquivos),
            "painel_rede": modo_painel == "rede",
            "painel": modo_painel,
            "janela": caminho_janela,
            "janela_do_app": janela_do_app,
            "de_app": args.de_app,
            "sem_janela": bool(args.sem_janela),
            "agendado": not args.sem_agendar and not avisos,
            "schema_version": schema.SCHEMA_VERSION,
            "instalado_em": clock.agora().isoformat(timespec="seconds"),
        }
    )
    codigo = checar(args, dados=dados)
    dizer("pronto", comando=comando)
    # pelo clique duplo, o que o --check acusa (Claude Code, conectores) a tela Começar mostra com o caminho de cada um
    return EXIT_OK if codigo == EXIT_OK or args.instalar_ou_atualizar else codigo


def instalar_janela(app: Path, raiz: Path, python3: str, *, sem_janela: bool, janela_do_app: str = "") -> str:
    """A janela própria do painel; devolve o caminho (app ou atalho), ou vazio sem janela. Faltar o compilador, o
    PowerShell ou falhar a montagem só avisa: o painel segue no navegador. Instalado pelo Goal Pacer.app do .dmg, o
    próprio app é a janela (nada a compilar)."""
    sistema = plataforma.atual()
    if sem_janela or not sistema.janela_nativa:
        return ""
    if janela_do_app and Path(janela_do_app).is_dir():
        dizer("janela_ok", app=janela_do_app)
        return janela_do_app
    try:
        destino = _janela_windows(app, raiz, python3) if sistema.nome == "windows" else _janela_mac(app)
    except GpErro as erro:
        dizer("janela_erro", erro=erro.mensagem)
        return ""
    if destino is not None:
        dizer("janela_ok_windows" if sistema.nome == "windows" else "janela_ok", app=destino)
    return str(destino or "")


def _janela_mac(app: Path) -> Optional[Path]:
    """O Goal Pacer.app compilado aqui (goalpacer/janela.py); o mesmo app já montado desta fonte fica como está."""
    if not janela.compilador_disponivel():
        dizer("janela_sem_swift")
        return None
    info = janela.info_plist(
        versao=_texto_versao(assinatura.versao_instalada(app)),
        endereco=ENDERECO_PAINEL,
        agente=plataforma.atual().agendador.label(plataforma.PAINEL),
        idioma=copy.atual(),
        textos={chave: copy.texto("janela." + chave) for chave in janela.CHAVES_TEXTOS},
        fonte=janela.impressao_da_fonte(app),
    )
    destino = janela.destino_padrao()
    if janela.montado_com(destino, info):
        return destino
    return janela.construir(app, destino, info)


def _janela_windows(app: Path, raiz: Path, python3: str) -> Path:
    """Atalho Goal Pacer no menu Iniciar: ``pythonw lancador.py janela``, com o ícone do painel em ``jobs/``."""
    import icones_painel

    jobs = raiz / base.NOME_JOBS
    icone = jobs / atalhos.NOME_ICONE
    icone.write_bytes(atalhos.ico({lado: icones_painel.png(lado) for lado in (16, 32, 48, 256)}))
    return atalhos.criar(
        atalhos.pasta_menu_iniciar() / atalhos.NOME_JANELA,
        atalhos.pythonw(python3),
        [str(app / "scripts" / "lancador.py"), "janela"],
        str(jobs),
        icone=str(icone),
    )


def remover_janela(raiz: Path, janela_do_app: str = "") -> None:
    """A janela compilada, o app do .dmg (quando é ele que foi instalado), os atalhos do Windows e a cópia do Python."""
    for app in (janela.destino_padrao(), Path(janela_do_app) if janela_do_app.endswith(".app") else None):
        if app is not None and janela.remover(app):
            dizer("uninstall_janela", app=app)
    shutil.rmtree(str(raiz / PASTA_RUNTIME), ignore_errors=True)
    atalho = atalhos.pasta_menu_iniciar() / atalhos.NOME_JANELA
    if atalhos.remover(atalho):
        dizer("uninstall_janela", app=atalho)
    icone = raiz / base.NOME_JOBS / atalhos.NOME_ICONE
    if icone.is_file():
        icone.unlink()


def abrir_o_app(caminho_janela: str) -> None:
    """Depois do clique duplo: a janela (app no macOS, atalho no Windows) ou o painel no navegador na tela Começar."""
    sistema = plataforma.atual()
    if caminho_janela and Path(caminho_janela).exists():
        sistema.abrir_url(caminho_janela)
        return
    for _ in range(40):  # o agente do painel acabou de subir: até 20 s para responder
        try:
            with urllib.request.urlopen(ENDERECO_PAINEL, timeout=1):
                break
        except urllib.error.HTTPError:
            break
        except (OSError, ValueError):
            time.sleep(0.5)
    sistema.abrir_url(ENDERECO_PAINEL + "#/comecar")


def _agendar(args: argparse.Namespace, arquivos: dict[str, list[Path]], modo_painel: str) -> list[str]:
    """Carrega os jobs (ou só avisa, com ``--sem-agendar``) e diz onde o painel ficou; devolve os que não carregaram."""
    avisos: list[str] = []
    if not modo_painel and descarregar_agendamento((plataforma.PAINEL,)):
        dizer("painel_desligado")
    if args.sem_agendar:
        dizer("sem_agendar", agendador=plataforma.atual().agendador.nome)
    else:
        avisos = carregar_agendamento(arquivos)
    if modo_painel == "rede":
        dizer("painel_rede", porta=8765)
    elif modo_painel == "local" and not args.sem_agendar:
        dizer("painel_local", endereco="http://127.0.0.1:8765/")
    return avisos


def checar(args: argparse.Namespace, *, dados: Optional[Path] = None) -> int:
    import status

    agora = clock.agora()
    dados = dados or base.data_dir()
    contexto = None
    if (dados / schema.CAMINHOS["contexto"]).exists():
        _item, contexto = status.item_dados(dados)
    itens = [
        status.item_python(),
        status.item_provedor(),
        status.item_conectores(contexto, agora, modo_offline=args.offline, sondar=args.sondar),
    ]
    print()
    print(copy.texto("instalar.check_titulo"))
    texto = status.render_doctor(itens, agora, cor=status.usar_cor())
    print("\n".join(texto.split("\n")[2:]).rstrip("\n"))
    return EXIT_OK if all(i.ok for i in itens) else EXIT_VALIDACAO


def atualizar(args: argparse.Namespace, *, reparar_em_dia: bool = False) -> int:
    """Tudo ou nada: recusa app sujo, faz backup dos dados, traz a versão nova, roda o autoteste e a migração do
    código novo e, se qualquer passo falha, volta o app ao que era. O doctor roda depois, fora do lock. Com
    ``reparar_em_dia`` (clique duplo no instalador), a instalação em dia só reaplica agendador, comando e janela."""
    instalacao = ler_instalacao()
    raiz = base.raiz()
    if instalacao is None:
        dizer("update_sem_instalacao", raiz=raiz)
        return EXIT_ESTADO
    app = Path(instalacao["app"])
    dados = Path(instalacao["dados"])
    try:
        trava = reg.lock(dados)
    except GpErro as erro:
        dizer("update_lock", erro=erro.mensagem)
        return EXIT_IO
    try:
        codigo = _aplicar_update(args, instalacao, raiz, app, dados)
    finally:
        trava.liberar()
    if codigo is None:
        return reaplicar(args) if reparar_em_dia else EXIT_OK  # em dia: nada mudou e o doctor fica para quando mudar
    if codigo != EXIT_OK:
        return codigo
    argv = [instalacao["python3"], str(app / "scripts" / "status.py"), "--doctor"] + (
        ["--offline"] if args.offline else []
    )
    _codigo, saida = _rodar(argv, env=dict(os.environ, GP_DATA_DIR=str(dados)), timeout_s=600)
    print(saida)
    return EXIT_OK


def _aplicar_update(
    args: argparse.Namespace, instalacao: dict[str, Any], raiz: Path, app: Path, dados: Path
) -> Optional[int]:
    """Código de saída do update, ou None quando a instalação já está na versão mais nova publicada."""
    clone = eh_repo_git(app)
    recusa, anterior = _recusa_do_update(args, app, clone)
    if recusa is not None:
        return recusa
    with tempfile.TemporaryDirectory(prefix="goal-pacer-update-") as temporaria:
        try:
            alvo = _tag_publicada(app, Path(temporaria)) if clone else _pasta_da_versao(args, app, Path(temporaria))
        except GpErro as erro:
            dizer("update_recusado", motivo=erro.mensagem)
            return erro.codigo
        if alvo is None:
            dizer("update_em_dia", versao=_texto_versao(assinatura.versao_instalada(app)))
            return None
        if dados.is_dir():
            backup = migracoes.fazer_backup(dados, "antes-do-update", clock.agora())
            migracoes.podar_backups(dados)
            dizer("update_backup", backup=backup)
        voltar = _trazer_versao_nova(app, anterior, alvo) if clone else _copiar_versao_nova(alvo, app)
    if voltar is None:
        return EXIT_IO
    falha = _conferir_versao_nova(instalacao, app, dados, voltar)
    if falha is not None:
        return falha
    return _concluir_update(args, instalacao, raiz, app)


def _texto_versao(versao: assinatura.Versao) -> str:
    return "%d.%d.%d" % versao


def _tag_publicada(app: Path, temporaria: Path) -> Optional[str]:
    """A maior tag de versão acima da instalada, conferida: assinatura de alguém da lista da versão instalada e o
    commit atual do app dentro dela (commit local fora da versão nunca some num checkout). None = já está em dia."""
    codigo, saida = _rodar([git(), "-C", str(app), "fetch", "--tags", "--quiet", "origin"], timeout_s=600)
    if codigo != 0:
        raise GpErro(EXIT_IO, "git fetch em %s não concluiu (%s)" % (app, saida.split("\n")[-1][:160]))
    _, tags = _rodar([git(), "-C", str(app), "tag", "--list", "v*"])
    tag = assinatura.maior_tag_nova(tags.split("\n"), assinatura.versao_instalada(app))
    if tag is None:
        return None
    assinatura.verificar_tag(git(), app, tag, assinatura.copiar_assinantes(app, temporaria))
    if _rodar([git(), "-C", str(app), "merge-base", "--is-ancestor", "HEAD", tag])[0] != 0:
        raise GpErro(EXIT_IO, "o app em %s tem commits que não estão em %s" % (app, tag))
    dizer("update_tag", tag=tag)
    return tag


def _pasta_da_versao(args: argparse.Namespace, app: Path, temporaria: Path) -> Optional[str]:
    """Zip da versão: ``.sig`` conferido com a lista da versão instalada e extraído à parte. Pasta de uma versão
    publicada (o zip já descompactado): manifesto assinado conferido, só os arquivos dele copiados à parte, com o
    sha256 de cada um; None quando a pasta não é mais nova que a instalação. Pasta sem manifesto: só em
    desenvolvimento (``--copiar``), sem assinatura, com aviso. Sem origem e com ``release/canal``: o zip da versão nova
    baixado do canal (None quando o canal diz que não há versão nova)."""
    texto = args.origem or _zip_do_canal(app, temporaria)
    if texto is None:
        return None
    origem = Path(texto).expanduser()
    if origem.is_dir() and (origem / assinatura.ARQUIVO_MANIFESTO).is_file():
        return _pasta_publicada(origem, app, temporaria)
    if origem.suffix.lower() != ".zip":
        dizer("update_sem_assinatura", origem=origem)
        return str(origem)
    quem = assinatura.verificar_arquivo(origem, assinatura.copiar_assinantes(app, temporaria))
    dizer("update_zip_assinado", arquivo=origem.name, assinante=quem)
    extraido = temporaria / "zip"
    extraido.mkdir()
    return str(assinatura.extrair_zip(origem, extraido))


def _zip_do_canal(app: Path, temporaria: Path) -> Optional[str]:
    baixados = temporaria / "canal"
    baixados.mkdir()
    dados = canal.ultima(app, baixados)
    if dados is None or dados["versao_tupla"] <= assinatura.versao_instalada(app):
        return None
    dizer("update_canal", versao="%d.%d.%d" % dados["versao_tupla"])
    return str(canal.baixar_zip(app, dados, baixados))


def _pasta_publicada(origem: Path, app: Path, temporaria: Path) -> Optional[str]:
    instalada = assinatura.versao_instalada(app)
    versao = assinatura.versao_do_manifesto(origem)
    if versao is not None and versao <= instalada:
        if versao < instalada:
            dizer("update_pasta_antiga", versao=_texto_versao(versao), instalada=_texto_versao(instalada))
        return None
    copia = temporaria / "versao"
    versao, quem = assinatura.copiar_versao(origem, copia, assinatura.copiar_assinantes(app, temporaria))
    if versao <= instalada:
        return None
    dizer("update_pasta_assinada", versao=_texto_versao(versao), assinante=quem)
    return str(copia)


def _recusa_do_update(args: argparse.Namespace, app: Path, clone: bool) -> tuple[Optional[int], str]:
    """``(código da recusa ou None, commit atual)``: clone com mudança fora de commit ou cópia sem origem não seguem."""
    if not clone:
        publicada = bool(args.origem) and (Path(args.origem).expanduser() / assinatura.ARQUIVO_MANIFESTO).is_file()
        pelo_canal = not args.origem and canal.endereco(app) is not None
        if not (
            pelo_canal or (args.origem and (args.copiar or publicada or str(args.origem).lower().endswith(".zip")))
        ):
            dizer("update_copia_sem_origem")
            return EXIT_VALIDACAO, ""
        return None, ""
    codigo, sujeira = _rodar([git(), "-C", str(app), "status", "--porcelain", "--untracked-files=no"])
    if codigo != 0 or sujeira:
        dizer("update_app_sujo", app=app)
        return EXIT_VALIDACAO, ""
    _, anterior = _rodar([git(), "-C", str(app), "rev-parse", "HEAD"])
    return None, anterior


def _trazer_versao_nova(app: Path, anterior: str, tag: str) -> Optional[Callable[[], None]]:
    """``git checkout`` da tag já conferida; devolve como voltar ao commit anterior, ou None quando não aplicou."""
    codigo, saida = _rodar([git(), "-C", str(app), "checkout", "--quiet", "--detach", tag], timeout_s=600)
    if codigo != 0:
        dizer("update_git", app=app, tag=tag, erro=saida.split("\n")[-1][:160])
        return None

    def voltar() -> None:
        _rodar([git(), "-C", str(app), "checkout", "--quiet", "--detach", anterior])

    return voltar


def _copiar_versao_nova(origem: str, app: Path) -> Callable[[], None]:
    """O app atual vira ``app.anterior`` e a origem é copiada; se a cópia falha, o anterior volta na hora."""
    reserva = app.with_name(app.name + ".anterior")
    if reserva.exists():
        shutil.rmtree(str(reserva))
    os.replace(str(app), str(reserva))

    def voltar() -> None:
        shutil.rmtree(str(app), ignore_errors=True)
        os.replace(str(reserva), str(app))

    try:
        preparar_app(origem, app, copiar=True, recopiar=True)
    except BaseException:
        voltar()
        raise
    return voltar


def _conferir_versao_nova(
    instalacao: dict[str, Any], app: Path, dados: Path, voltar: Callable[[], None]
) -> Optional[int]:
    """Autoteste do código novo (fora da pasta de dados) e migração; na falha, volta o app e devolve o código."""
    ambiente_limpo = {k: v for k, v in os.environ.items() if k not in (base.ENV_DATA_DIR, base.ENV_RAIZ)}
    codigo, saida = _rodar(
        [instalacao["python3"], str(app / "scripts" / "autoteste.py")], env=ambiente_limpo, timeout_s=300
    )
    if codigo != 0:
        voltar()
        ultima = saida.split("\n")[-1][:200]
        # exit 3 é a reprovação do próprio autoteste (já diz o passo); outro código é o código novo quebrando antes dele
        dizer(
            "update_desfeito",
            motivo=ultima if codigo == EXIT_VALIDACAO else copy.texto("instalar.autoteste_erro", erro=ultima),
        )
        return EXIT_VALIDACAO
    codigo, saida = _rodar(
        [instalacao["python3"], str(app / "scripts" / "migrar.py"), "--aplicar"],
        env=dict(os.environ, GP_DATA_DIR=str(dados), GP_LOCK_HERDADO="1"),
    )
    if codigo != 0:
        voltar()
        dizer("update_migrar", erro=saida)
        dizer("update_desfeito", motivo=saida.split("\n")[-1][:200])
        return codigo if codigo > 0 else EXIT_IO
    return None


def _concluir_update(args: argparse.Namespace, instalacao: dict[str, Any], raiz: Path, app: Path) -> int:
    """O resto do update roda com o instalador da versão NOVA (``--reaplicar``): comando, permissões, agendador,
    janela e o que mais a versão nova passar a instalar. O instalador que conduz o update é o da versão antiga e
    não sabe o que surgiu depois dele."""
    dizer("update_autoteste")
    reserva = app.with_name(app.name + ".anterior")
    if reserva.exists():
        shutil.rmtree(str(reserva), ignore_errors=True)
    argv = [instalacao["python3"], str(app / "scripts" / "instalar.py"), "--reaplicar", "--nao-interativo"]
    argv += ["--painel-rede"] if args.painel_rede else []
    argv += ["--sem-agendar"] if args.sem_agendar else []
    codigo, saida = _rodar(argv, env=dict(os.environ, **{base.ENV_RAIZ: str(raiz)}), timeout_s=900)
    if saida:
        print(saida)
    if codigo != EXIT_OK:
        dizer("update_reaplicar", erro=(saida.strip().split("\n") or [""])[-1][:200])
        return codigo if codigo > 0 else EXIT_IO
    return EXIT_OK


def reaplicar(args: argparse.Namespace) -> int:
    """Com o código novo já no lugar: comando, permissões, agendador (painel incluso), janela e instalacao.json."""
    instalacao = ler_instalacao()
    if instalacao is None:
        dizer("update_sem_instalacao", raiz=base.raiz())
        return EXIT_ESTADO
    raiz, app, dados = Path(instalacao.get("raiz") or base.raiz()), Path(instalacao["app"]), Path(instalacao["dados"])
    garantir_fusos(raiz, instalacao["python3"])
    instalar_comando(raiz, app, instalacao["python3"])
    endurecer(raiz, app, dados)
    modo_painel = "rede" if args.painel_rede or instalacao.get("painel_rede") else instalacao.get("painel", "local")
    instalacao["claude"] = claude_para_agendar(instalacao.get("claude") or "")  # o Claude Code pode ter vindo depois
    arquivos = gerar_agendamento(app, raiz, dados, instalacao["python3"], instalacao["claude"], modo_painel=modo_painel)
    instalacao["painel_rede"] = modo_painel == "rede"
    instalacao["painel"] = modo_painel
    instalacao["janela"] = instalar_janela(
        app,
        raiz,
        instalacao["python3"],
        sem_janela=bool(instalacao.get("sem_janela")),
        janela_do_app=instalacao.get("janela_do_app") or "",
    )
    limpar_runtimes(raiz, instalacao["python3"])
    instalacao["labels"] = list(arquivos)
    if instalacao.get("agendado", True) and not args.sem_agendar:
        carregar_agendamento(arquivos)
    instalacao.update(
        {
            "revisao": revisao(app),
            "versao": _texto_versao(assinatura.versao_instalada(app)),
            "schema_version": schema.SCHEMA_VERSION,
            "atualizado_em": clock.agora().isoformat(timespec="seconds"),
        }
    )
    gravar_instalacao(instalacao)
    dizer("update_ok", app_versao=instalacao["versao"], revisao=instalacao["revisao"], versao=schema.SCHEMA_VERSION)
    return EXIT_OK


def instalar_ou_atualizar(args: argparse.Namespace) -> int:
    """O clique duplo no instalador: sem instalação, instala; com ela, atualiza a partir desta pasta (cópia) ou das
    tags do remoto (clone) e, já em dia, reaplica o que faltar. Com ``--abrir``, abre o app no fim."""
    instalacao = ler_instalacao()
    if instalacao is None or not Path(str(instalacao.get("app") or "")).is_dir():
        codigo = instalar(args)
    else:
        if instalacao.get("modo") != "clone" and not args.origem:
            args.origem = args.origem_padrao
        if args.de_app:
            _trocar_runtime(instalacao, args.de_app)
        codigo = atualizar(args, reparar_em_dia=True)
    if codigo == EXIT_OK and args.de_app and processos.WINDOWS:
        limpar_versoes_do_setup(Path(args.de_app))
    if codigo == EXIT_OK and args.abrir:
        abrir_o_app(str((ler_instalacao() or {}).get("janela") or ""))
    return codigo


PASTA_RUNTIME = "runtime"


def python_para_jobs(raiz: Path, de_app: Optional[str]) -> str:
    """O Python que os jobs vão usar. Pelo terminal, o que rodou o instalador. Pelo app do .dmg (``--de-app``), uma
    cópia do Python embutido em ``raiz/runtime/python-X.Y.Z``: o app pode mudar de lugar ou ser trocado, e os jobs não
    podem depender dele. No Windows, o Python que o Setup.exe põe na pasta da versão já fica num lugar estável."""
    if not de_app or processos.WINDOWS:
        return sys.executable
    origem = Path(sys.executable).resolve().parents[1]
    destino = raiz / PASTA_RUNTIME / ("python-%d.%d.%d" % sys.version_info[:3])
    python = destino / "bin" / "python3"
    if not python.exists():
        novo = destino.with_name(destino.name + ".novo")
        shutil.rmtree(str(novo), ignore_errors=True)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(origem), str(novo), symlinks=True)
        os.replace(str(novo), str(destino))
        dizer("runtime_copiado", pasta=destino)
    return str(python)


def _trocar_runtime(instalacao: dict[str, Any], de_app: str) -> None:
    """Update pelo app de uma versão nova: os jobs passam para o Python que veio com ela (o autoteste e o
    ``--reaplicar`` já rodam nele), e o próprio app vira a janela."""
    raiz = Path(instalacao.get("raiz") or base.raiz())
    instalacao["python3"] = python_para_jobs(raiz, de_app)
    instalacao["de_app"] = de_app
    if plataforma.nome_atual() == "macos":
        instalacao["janela_do_app"] = de_app
    gravar_instalacao(instalacao)


def limpar_runtimes(raiz: Path, python3: str) -> None:
    """Tira as cópias de Python de versões anteriores (``raiz/runtime``) que os jobs não usam mais."""
    pasta = raiz / PASTA_RUNTIME
    atual = Path(python3)
    for velho in sorted(pasta.iterdir()) if pasta.is_dir() else []:
        if velho.is_dir() and velho not in atual.parents:
            shutil.rmtree(str(velho), ignore_errors=True)


def limpar_versoes_do_setup(versao_atual: Path) -> None:
    """Windows: o Setup.exe põe cada versão numa pasta própria; as anteriores saem quando os jobs já apontam para a
    nova (arquivo ainda aberto por um processo antigo fica para a próxima vez)."""
    for irma in versao_atual.parent.iterdir() if versao_atual.parent.is_dir() else []:
        if irma.is_dir() and irma != versao_atual and assinatura.versao_de(irma.name) is not None:
            shutil.rmtree(str(irma), ignore_errors=True)


def perguntar(chave: str, args: argparse.Namespace, **valores: Any) -> bool:
    if args.nao_interativo:
        return False
    return input(copy.texto("instalar." + chave, **valores) + " ").strip().lower() in ("s", "sim", "y", "yes")


def desinstalar(args: argparse.Namespace) -> int:
    instalacao = ler_instalacao() or {}
    app = Path(instalacao.get("app") or base.app_dir())
    dados = Path(instalacao.get("dados") or base.data_dir())
    raiz = Path(instalacao.get("raiz") or base.raiz())
    _tirar_agendamento_skill_e_comando(raiz)
    remover_janela(raiz, str(instalacao.get("janela_do_app") or ""))
    diario = app / "scripts" / "diario.py"
    if (dados / schema.CAMINHOS["contexto"]).exists() and diario.exists():
        _blocos_do_metas(args, [instalacao.get("python3") or sys.executable, str(diario)], dados)
    if args.apagar_cache or perguntar("uninstall_cache_pergunta", args):
        _apagar_cache_e_sinais(dados)
    aparelhos = base.jobs_dir() / "painel-aparelhos.json"
    if aparelhos.exists():
        aparelhos.unlink()
    dizer("uninstall_fim", dados=dados, app=app)
    return EXIT_OK


def _apagar_cache_e_sinais(dados: Path) -> None:
    for sub in ("cache", "sinais"):
        alvo = dados / sub
        if alvo.is_dir() and not alvo.is_symlink():
            shutil.rmtree(alvo)
    dizer("uninstall_cache")


def _tirar_agendamento_skill_e_comando(raiz: Path) -> None:
    removidos = descarregar_agendamento()
    agendador = plataforma.atual().agendador.nome
    if removidos:
        dizer("uninstall_agendador", agendador=agendador, labels=", ".join(removidos))
    else:
        dizer("uninstall_sem_agendador", agendador=agendador)
    link = link_skill()
    if plataforma.eh_ligacao(link):
        plataforma.desligar(link)
        dizer("uninstall_skill", link=link)
    remover_comando(raiz)


def _json_do_diario(codigo: int, saida: str) -> Optional[dict[str, Any]]:
    if codigo != 0:
        return None
    try:
        return json.loads(saida)
    except ValueError:
        return None


def _ultima_linha(erro: str, saida: str) -> str:
    """Última linha com texto do erro (ou da saída): um erro que termina em quebra de linha não vira mensagem vazia."""
    return (erro or saida).strip().split("\n")[-1][:120]


def _blocos_do_metas(args: argparse.Namespace, diario: list[str], dados: Path) -> None:
    """Lista os blocos desta instalação no Metas e, com confirmação, apaga pelo diário (--desinstalar)."""
    env = dict(os.environ, GP_DATA_DIR=str(dados))
    extra = ["--offline"] if args.offline else []
    codigo, saida, erro = _rodar3([*diario, "--json", "--desinstalar", *extra], env=env, timeout_s=900)
    listados = _json_do_diario(codigo, saida)
    blocos = listados.get("blocos", []) if listados is not None else None
    if blocos is None:
        dizer("uninstall_blocos_erro", erro=_ultima_linha(erro, saida))
        return
    if not blocos:
        return
    if not (args.apagar_blocos or perguntar("uninstall_blocos_pergunta", args, n=len(blocos))):
        dizer("uninstall_blocos_mantidos")
        return
    codigo, saida, erro = _rodar3([*diario, "--json", "--desinstalar", "--confirmar", *extra], env=env, timeout_s=900)
    resultado = _json_do_diario(codigo, saida)
    if resultado is not None and not resultado.get("erros"):
        dizer("uninstall_blocos", n=len(resultado.get("blocos", [])))
    elif resultado is not None:
        dizer(
            "uninstall_blocos_erro",
            erro=copy.texto("instalar.uninstall_nao_apagados", ids=", ".join(resultado["erros"])),
        )
    else:
        dizer("uninstall_blocos_erro", erro=_ultima_linha(erro, saida))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="instala, confere, atualiza ou remove o Goal Pacer")
    parser.add_argument("--origem-padrao", dest="origem_padrao", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--from",
        dest="origem",
        default=None,
        metavar="ORIGEM",
        help="pasta do repo ou URL git (padrão: o repo deste install.sh)",
    )
    parser.add_argument(
        "--copiar", action="store_true", help="copia a árvore de trabalho em vez de clonar (desenvolvimento)"
    )
    parser.add_argument(
        "--dados", type=Path, default=None, metavar="PASTA", help="pasta de dados (padrão: ~/.goal-pacer/dados)"
    )
    parser.add_argument(
        "--nao-interativo",
        dest="nao_interativo",
        action="store_true",
        help="não pergunta nada; usa os padrões e as flags",
    )
    parser.add_argument(
        "--sem-agendar",
        "--sem-launchd",
        dest="sem_agendar",
        action="store_true",
        help="gera os arquivos do agendador sem carregar os jobs",
    )
    parser.add_argument(
        "--provedor",
        choices=sorted(provedor.PROVEDORES),
        default=provedor.PADRAO,
        help="IA da instalação pelo login que você já tem: claude (Claude Code) ou openai (Codex)",
    )
    parser.add_argument("--offline", action="store_true", help="checagens e desinstalação sem conectores (testes)")
    parser.add_argument(
        "--sondar-escrita",
        dest="sondar",
        action="store_true",
        help="com --check: cria e apaga sondas no Metas e no Gmail",
    )
    painel_alcance = parser.add_mutually_exclusive_group()
    painel_alcance.add_argument(
        "--painel-rede",
        dest="painel_rede",
        action="store_true",
        help="mantém o painel no ar para o celular no mesmo Wi-Fi",
    )
    parser.add_argument(
        "--sem-janela",
        dest="sem_janela",
        action="store_true",
        help="no macOS, não monta o Goal Pacer.app (o painel fica só no navegador)",
    )
    painel_alcance.add_argument(
        "--sem-painel",
        dest="sem_painel",
        action="store_true",
        help="não deixa o painel no ar (sem o agente do login)",
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--check", action="store_true")
    modo.add_argument("--update", action="store_true")
    modo.add_argument("--uninstall", action="store_true")
    modo.add_argument("--reaplicar", action="store_true", help=argparse.SUPPRESS)  # o update chama na versão nova
    modo.add_argument(
        "--instalar-ou-atualizar",
        dest="instalar_ou_atualizar",
        action="store_true",
        help="o clique duplo no instalador: instala, ou atualiza a instalação que já existe a partir desta pasta",
    )
    parser.add_argument("--abrir", action="store_true", help="abre o Goal Pacer no fim (janela ou navegador)")
    parser.add_argument("--de-app", dest="de_app", default="", help=argparse.SUPPRESS)  # o app do .dmg ou o Setup.exe
    parser.add_argument("--sem-abrir", dest="abrir", action="store_false", help=argparse.SUPPRESS)
    parser.add_argument(
        "--apagar-blocos",
        dest="apagar_blocos",
        action="store_true",
        help="com --uninstall: apaga os blocos desta instalação sem perguntar",
    )
    parser.add_argument(
        "--apagar-cache",
        dest="apagar_cache",
        action="store_true",
        help="com --uninstall: apaga cache/ e sinais/ sem perguntar",
    )
    args = parser.parse_args(argv)
    try:
        if args.check:
            return checar(args)
        if args.update:
            return atualizar(args)
        if args.uninstall:
            return desinstalar(args)
        if args.reaplicar:
            return reaplicar(args)
        if args.instalar_ou_atualizar:
            return instalar_ou_atualizar(args)
        instalado = instalar(args)
        if instalado == EXIT_OK and args.abrir:
            abrir_o_app(str((ler_instalacao() or {}).get("janela") or ""))
        return instalado
    except GpErro as erro:
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    except (KeyboardInterrupt, EOFError):
        print(file=sys.stderr)
        return EXIT_ESTADO


if __name__ == "__main__":
    raise SystemExit(main())
