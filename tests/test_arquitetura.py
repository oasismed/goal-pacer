"""Regras de arquitetura como teste (o import-linter e as fitness functions do manual de qualidade, sem dependência).

Lê o código com ``ast``, nunca importa os módulos. Cada regra diz o motivo e o que fazer quando falha.
"""

from __future__ import annotations

import ast
import re
import sys
from functools import cache
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / "scripts"
PACOTE = SCRIPTS / "goalpacer"
RUN_JOB = RAIZ / "jobs" / "run_job.py"
MODULOS = {p.stem for p in PACOTE.glob("*.py") if p.stem != "__init__"}
CLIS = {p.stem for p in SCRIPTS.glob("*.py")}
RE_VARIAVEL = re.compile(r"GP_[A-Z0-9_]+\Z")


def _codigo_do_app() -> list[Path]:
    return [*sorted(SCRIPTS.rglob("*.py")), RUN_JOB]


@cache
def _arvore(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports_do_pacote(path: Path) -> set[str]:
    """Módulos do ``goalpacer`` importados por ``path``, no topo ou dentro de função."""
    nomes: set[str] = set()
    for no in ast.walk(_arvore(path)):
        if isinstance(no, ast.ImportFrom) and no.module == "goalpacer":
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.module.startswith("goalpacer."):
            nomes.add(no.module.split(".")[1])
        elif isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[1] for a in no.names if a.name.startswith("goalpacer."))
    return (nomes & MODULOS) - {path.stem}


def _imports_absolutos(path: Path) -> set[str]:
    raizes: set[str] = set()
    for no in ast.walk(_arvore(path)):
        if isinstance(no, ast.Import):
            raizes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and not no.level:
            raizes.add(no.module.split(".")[0])
    return raizes


def _chamadas(path: Path) -> list[tuple[ast.Call, str]]:
    """Cada chamada com o nome da função que a contém (``""`` no nível do módulo)."""
    saida: list[tuple[ast.Call, str]] = []

    def visitar(no: ast.AST, funcao: str) -> None:
        for filho in ast.iter_child_nodes(no):
            dentro = filho.name if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)) else funcao
            if isinstance(filho, ast.Call):
                saida.append((filho, dentro))
            visitar(filho, dentro)

    visitar(_arvore(path), "")
    return saida


def _nome_chamado(chamada: ast.Call) -> tuple[str, str]:
    """``(dono, atributo)``: ``subprocess.run`` → ``("subprocess", "run")``; ``open`` → ``("", "open")``."""
    funcao = chamada.func
    if isinstance(funcao, ast.Name):
        return "", funcao.id
    if isinstance(funcao, ast.Attribute):
        dono = funcao.value.id if isinstance(funcao.value, ast.Name) else ""
        return dono, funcao.attr
    return "", ""


def _tem_argumento(chamada: ast.Call, nome: str) -> bool:
    return any(k.arg == nome for k in chamada.keywords)


# --- camadas ---------------------------------------------------------------------------------------------------------


def test_pacote_nunca_importa_clis():
    """O pacote é a biblioteca; os CLIs de scripts/ são adaptadores. Quando o pacote precisa de algo de um CLI,
    o CLI injeta (``respostas_email.aplicar(confirmar=)``, ``migracoes.migrar(conferir=)``)."""
    violacoes = []
    for path in sorted(PACOTE.glob("*.py")):
        arvore = _arvore(path)
        for no in ast.walk(arvore):
            nomes = (
                [a.name.split(".")[0] for a in no.names]
                if isinstance(no, ast.Import)
                else [no.module.split(".")[0]]
                if isinstance(no, ast.ImportFrom) and no.module and not no.level
                else []
            )
            violacoes += ["%s:%d importa %s" % (path.name, no.lineno, n) for n in nomes if n in CLIS]
    assert not violacoes, violacoes


def test_base_e_a_camada_de_baixo():
    """``base`` (raízes, códigos de saída, GpErro) não importa nenhum módulo do pacote: log mora em telemetria,
    argumentos comuns em cli e as pastas protegidas do macOS em plataforma."""
    assert _imports_do_pacote(PACOTE / "base.py") == set()


def test_imports_do_pacote_sem_ciclo():
    """Nem no topo nem dentro de função: import tardio para fugir de ciclo esconde camada trocada."""
    grafo = {m: _imports_do_pacote(PACOTE / (m + ".py")) for m in MODULOS}
    ciclos = []
    estado: dict[str, int] = {}

    def descer(modulo: str, caminho: list[str]) -> None:
        estado[modulo] = 1
        for dep in sorted(grafo[modulo]):
            if estado.get(dep) == 1:
                ciclos.append(" -> ".join([*caminho[caminho.index(dep) :], dep]))
            elif dep not in estado:
                descer(dep, [*caminho, dep])
        estado[modulo] = 2

    for modulo in sorted(MODULOS):
        if modulo not in estado:
            descer(modulo, [modulo])
    assert not ciclos, ciclos


@pytest.mark.skipif(
    sys.version_info < (3, 10), reason="sys.stdlib_module_names chegou no 3.10 (a suíte roda também no 3.13)"
)
def test_runtime_so_com_a_biblioteca_padrao():
    """O app roda com o Python do sistema, sem pip: todo import é da stdlib, do pacote ou de um CLI do repo."""
    permitidos = set(sys.stdlib_module_names) | {"goalpacer", "__future__"} | CLIS | {"run_job"}
    fora = {
        "%s: %s" % (path.relative_to(RAIZ), nome)
        for path in _codigo_do_app()
        for nome in _imports_absolutos(path)
        if nome not in permitidos
    }
    assert not fora, sorted(fora)


# --- chamadas com regra ------------------------------------------------------------------------------------------------

PROCESSOS_LONGOS = {
    "manter_acordado",  # caffeinate e systemd-inhibit vivem enquanto o painel está no ar
    "iniciar_atualizacao",  # o update pedido pelo painel sobrevive ao reinício do agente do painel (log e pid em jobs/logs)
    "subir_painel",  # Windows: o lançador do painel fica no ar depois que o instalador (ou a janela) termina
    "servir_painel",  # Windows: o lançador espera o web.py enquanto o painel está no ar e o sobe outra vez se cair
    "abrir_no_navegador",  # Windows: a janela do navegador em modo app é da pessoa, não do lançador
    "instalar_claude",  # o instalador oficial do Claude Code segue quando o painel reinicia (log e pid em jobs/logs)
    "iniciar_login",  # o claude auth login espera o código que a pessoa cola na tela Começar (teto de 15 min)
    "iniciar_desinstalacao",  # a desinstalação pelo painel encerra o próprio painel e segue sozinha (log em jobs/logs)
}


def test_subprocesso_sempre_com_timeout():
    """Todo processo filho tem teto: ``run``/``check_output`` com ``timeout=``; ``Popen`` só com
    ``communicate(timeout=)`` na mesma função ou nos processos longos declarados."""
    sem_teto = []
    for path in _codigo_do_app():
        chamadas = _chamadas(path)
        com_communicate = {
            funcao for c, funcao in chamadas if _nome_chamado(c)[1] == "communicate" and _tem_argumento(c, "timeout")
        }
        for chamada, funcao in chamadas:
            dono, nome = _nome_chamado(chamada)
            if dono != "subprocess":
                continue
            if nome in {"run", "check_output", "check_call", "call"} and not _tem_argumento(chamada, "timeout"):
                sem_teto.append("%s:%d subprocess.%s" % (path.name, chamada.lineno, nome))
            if nome == "Popen" and funcao not in com_communicate and funcao not in PROCESSOS_LONGOS:
                sem_teto.append("%s:%d subprocess.Popen em %s" % (path.name, chamada.lineno, funcao))
    assert not sem_teto, sem_teto


def test_relogio_so_pelo_clock():
    """``datetime.now()``/``date.today()`` fora do clock ignoram ``--agora`` e quebram a reprodutibilidade;
    o relógio real (telemetria, validade de credenciais) é ``clock.instante_real()``."""
    fora = [
        "%s:%d %s.%s" % (path.name, chamada.lineno, *_nome_chamado(chamada))
        for path in _codigo_do_app()
        if path.name != "clock.py"
        for chamada, _ in _chamadas(path)
        if _nome_chamado(chamada)
        in {("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("date", "today")}
    ]
    assert not fora, fora


def test_texto_sempre_com_encoding():
    """Sem ``encoding=`` o Python usa o locale do processo, e o launchd roda sem LANG."""
    sem_encoding = []
    for path in _codigo_do_app():
        for chamada, _ in _chamadas(path):
            _, nome = _nome_chamado(chamada)
            if nome == "open" and isinstance(chamada.func, ast.Name):
                modo = chamada.args[1] if len(chamada.args) > 1 else None
                modo = next((k.value for k in chamada.keywords if k.arg == "mode"), modo)
                binario = isinstance(modo, ast.Constant) and "b" in str(modo.value)
                if not binario and not _tem_argumento(chamada, "encoding"):
                    sem_encoding.append("%s:%d open" % (path.name, chamada.lineno))
            if nome in {"read_text", "write_text"} and not _tem_argumento(chamada, "encoding"):
                posicionais = 0 if nome == "read_text" else 1
                if len(chamada.args) <= posicionais:
                    sem_encoding.append("%s:%d %s" % (path.name, chamada.lineno, nome))
    assert not sem_encoding, sem_encoding


def test_pacote_nao_imprime():
    """Biblioteca não escreve na tela: quem imprime são os CLIs. Exceções: ``telemetria.log`` (a linha de log)
    e o ``main`` de ``schema`` (``python3 -m goalpacer.schema --md``)."""
    permitidos = {("telemetria.py", "log"), ("schema.py", "main")}
    fora = [
        "%s:%d em %s" % (path.name, chamada.lineno, funcao or "<módulo>")
        for path in sorted(PACOTE.glob("*.py"))
        for chamada, funcao in _chamadas(path)
        if _nome_chamado(chamada) == ("", "print") and (path.name, funcao) not in permitidos
    ]
    assert not fora, fora


def test_prosa_so_pelo_ponto_unico():
    """A prosa passa por ``ia.prosa``, que escolhe o provedor da instalação; chamar ``proxy.prosa`` ou ``codex.prosa``
    direto ignoraria o login que a pessoa escolheu (claude ou openai)."""
    permitidos = {"ia.py", "proxy.py", "codex.py"}
    fora = [
        "%s:%d %s.prosa" % (path.name, chamada.lineno, dono)
        for path in _codigo_do_app()
        if path.name not in permitidos
        for chamada, _ in _chamadas(path)
        for dono, nome in [_nome_chamado(chamada)]
        if nome == "prosa" and dono in {"proxy", "codex"}
    ]
    assert not fora, fora


# --- duplicação ------------------------------------------------------------------------------------------------------

JANELA_DUPLICACAO = 4  # comandos seguidos
TAMANHO_MINIMO_DUPLICACAO = 60  # nós de AST na janela: abaixo disso é idioma do código, não bloco copiado


class _Anonimo(ast.NodeTransformer):
    """Troca nomes, argumentos e literais por marcadores: o mesmo bloco com variáveis renomeadas também é cópia."""

    def visit_Name(self, no: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_", ctx=no.ctx), no)

    def visit_arg(self, no: ast.arg) -> ast.AST:
        no.arg = "_"
        return no

    def visit_Constant(self, no: ast.Constant) -> ast.AST:
        return ast.copy_location(ast.Constant(value="s" if isinstance(no.value, str) else 0), no)


def _janelas(path: Path):
    for no in ast.walk(_arvore(path)):
        for campo in ("body", "orelse", "finalbody"):
            bloco = getattr(no, campo, None)
            if not isinstance(bloco, list) or not all(isinstance(s, ast.stmt) for s in bloco):
                continue
            for i in range(len(bloco) - JANELA_DUPLICACAO + 1):
                janela = bloco[i : i + JANELA_DUPLICACAO]
                if sum(1 for s in janela for _ in ast.walk(s)) >= TAMANHO_MINIMO_DUPLICACAO:
                    yield janela


def test_sem_bloco_copiado():
    """D-10: quatro comandos seguidos iguais (com nomes e literais trocados) em dois lugares viram uma função.
    Duplicação é mais barata que a abstração errada: o limiar pega só blocos grandes."""
    vistos: dict[str, list[str]] = {}
    for path in _codigo_do_app():
        for janela in _janelas(path):
            forma = "|".join(ast.dump(_Anonimo().visit(ast.parse(ast.unparse(s)).body[0])) for s in janela)
            vistos.setdefault(forma, []).append("%s:%d" % (path.relative_to(RAIZ), janela[0].lineno))
    copias = sorted({tuple(onde) for onde in vistos.values() if len(onde) > 1})
    assert not copias, copias


# --- configuração pelo ambiente --------------------------------------------------------------------------------------


def _variaveis() -> tuple[dict[str, list[str]], list[str]]:
    """``({GP_X: [onde é declarada]}, [literais soltos])``: declaração = ``ENV_ALGO = "GP_X"`` no nível do módulo."""
    declaradas: dict[str, list[str]] = {}
    soltas: list[str] = []
    for path in _codigo_do_app():
        arvore = _arvore(path)
        constantes = set()
        for no in arvore.body:
            if (
                isinstance(no, ast.Assign)
                and len(no.targets) == 1
                and isinstance(no.targets[0], ast.Name)
                and no.targets[0].id.startswith("ENV_")
                and isinstance(no.value, ast.Constant)
                and isinstance(no.value.value, str)
                and RE_VARIAVEL.match(no.value.value)
            ):
                declaradas.setdefault(no.value.value, []).append("%s:%d" % (path.name, no.lineno))
                constantes.add(id(no.value))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Constant)
                and isinstance(no.value, str)
                and RE_VARIAVEL.match(no.value)
                and id(no) not in constantes
            ):
                soltas.append("%s:%d %s" % (path.name, no.lineno, no.value))
    return declaradas, soltas


def test_variavel_de_ambiente_declarada_uma_vez():
    """Cada ``GP_*`` nasce numa constante ``ENV_*`` de um módulo só; o resto do código usa a constante."""
    declaradas, soltas = _variaveis()
    duplicadas = {nome: onde for nome, onde in declaradas.items() if len(onde) > 1}
    assert not soltas, soltas
    assert not duplicadas, duplicadas


def test_variaveis_de_ambiente_documentadas_no_readme():
    """A tabela "Variáveis de ambiente" de docs/referencia.md é a referência única da configuração: nem sobra nem falta."""
    declaradas, _ = _variaveis()
    readme = (RAIZ / "docs" / "referencia.md").read_text(encoding="utf-8")
    secao = readme.split("### Variáveis de ambiente", 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]
    documentadas = set(re.findall(r"`(GP_[A-Z0-9_]+)`", secao))
    assert sorted(set(declaradas) - documentadas) == [], "faltam em docs/referencia.md"
    assert sorted(documentadas - set(declaradas)) == [], "docs/referencia.md cita variáveis que o código não lê"
