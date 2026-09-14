"""Raízes da instalação, códigos de saída e erro comum: a camada de baixo do pacote.

Implementa os achados 5.1 (pacote stdlib) e 1.4 (raiz única) do plano e os códigos de saída fixados no AGENTS.md.
Não importa nenhum outro módulo do ``goalpacer`` (tests/test_arquitetura.py): o log mora em ``telemetria``,
os argumentos comuns dos CLIs em ``cli`` e a regra das pastas protegidas do macOS em ``plataforma``.

Layout da raiz (env ``GP_RAIZ`` sobrepõe ``~/.goal-pacer``)::

    RAIZ/
      app/     clone do repo; ~/.claude/skills/goal-pacer aponta para cá
      dados/   DATA_DIR padrão (env GP_DATA_DIR sobrepõe); nunca em pasta TCC
      jobs/    cwd neutro dos jobs e dos proxies, settings, plists, logs

Códigos de saída dos CLIs: 0 ok; 2 estado esperado (``sem_onboarding``,
``sem_meta_ativa``); 3 validação/negação/auth; 4 IO/lock; 5 timeout.

As raízes são funções, não constantes: leem o ambiente a cada chamada, para
que ``--dados``, ``GP_RAIZ`` e as fixtures dos testes valham depois do import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

VERSAO_APP = "0.6.3"  # a versão publicada; sobe junto com o CHANGELOG.md e a tag assinada (dev/release.py)

EXIT_OK = 0
EXIT_ESTADO = 2
EXIT_VALIDACAO = 3
EXIT_IO = 4
EXIT_TIMEOUT = 5

ENV_RAIZ = "GP_RAIZ"
ENV_DATA_DIR = "GP_DATA_DIR"
ENV_RUN_ID = "GP_RUN_ID"

NOME_RAIZ = ".goal-pacer"
NOME_APP = "app"
NOME_DADOS = "dados"
NOME_JOBS = "jobs"
NOME_INSTALACAO = "instalacao.json"  # em jobs/: o que o instalador gravou (caminhos, provedor, revisão)


class GpErro(Exception):
    """Erro com código de saída.

    ``codigo`` é um dos ``EXIT_*``; ``mensagem`` é o texto para o usuário
    (stderr), sem dados de terceiros. ``classe`` (opcional) fixa a classe do
    runbook (``execucao.CLASSES``) sem depender do texto, que muda com o idioma.
    """

    def __init__(self, codigo: int, mensagem: str = "", classe: Optional[str] = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.classe = classe

    def __str__(self) -> str:
        return self.mensagem or self.__class__.__name__


def _path_do_env(nome: str) -> Optional[Path]:
    """``Path`` da variável ``nome`` com ``~`` expandido; ``None`` se vazia."""
    valor = os.environ.get(nome, "")
    if not valor:
        return None
    return Path(valor).expanduser()


def raiz_padrao() -> Path:
    """``~/.goal-pacer`` do HOME atual (função, não constante: o HOME muda nos testes)."""
    return Path.home() / NOME_RAIZ


def raiz() -> Path:
    """Raiz da instalação: ``GP_RAIZ`` ou ``raiz_padrao()``.

    Lê o ambiente a cada chamada (os testes trocam as variáveis).
    """
    env = _path_do_env(ENV_RAIZ)
    if env is not None:
        return env
    return raiz_padrao()


def app_dir() -> Path:
    """``raiz()/app``."""
    return raiz() / NOME_APP


def data_dir() -> Path:
    """Pasta de dados: ``GP_DATA_DIR`` ou ``raiz()/dados``.

    Não cria a pasta nem valida TCC (isso é do install/doctor).
    """
    env = _path_do_env(ENV_DATA_DIR)
    if env is not None:
        return env
    return raiz() / NOME_DADOS


def jobs_dir() -> Path:
    """``raiz()/jobs``: cwd neutro dos jobs e dos proxies."""
    return raiz() / NOME_JOBS


def _dentro(base: Path, alvo: Path) -> bool:
    return alvo == base or base in alvo.parents


def caminho_dados(*partes: str) -> Path:
    """Caminho dentro de ``data_dir()``.

    Recusa qualquer parte que suba acima da pasta de dados (``..``, parte
    absoluta fora dela) com ``GpErro(EXIT_IO)``. Aceita partes absolutas que
    já estejam dentro de ``data_dir()``. Duas checagens: lexical
    (``abspath``) e real (``realpath``, seguindo symlinks do trecho que
    existe): a própria pasta de dados pode ser um link, mas um symlink
    dentro dela apontando para fora (``dados/planos -> ~/Documents/x``,
    ``dados/registro.json -> /etc/hosts``) é recusado. O alvo pode não
    existir.
    """
    base = data_dir()
    alvo = base.joinpath(*partes)
    if ".." in alvo.parts:
        raise GpErro(EXIT_IO, "caminho de dados não pode conter '..': %s" % alvo)
    if not _dentro(Path(os.path.abspath(base)), Path(os.path.abspath(alvo))):
        raise GpErro(EXIT_IO, "caminho fora da pasta de dados: %s" % alvo)
    if not _dentro(Path(os.path.realpath(base)), Path(os.path.realpath(alvo))):
        raise GpErro(EXIT_IO, "caminho de dados aponta (por symlink) para fora da pasta de dados: %s" % alvo)
    return alvo


def numero(valor: object) -> Optional[float]:
    """Número de uma resposta (int, float ou texto com vírgula ou ponto); bool, vazio e o resto = ``None``."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        try:
            return float(valor.strip().replace(",", "."))
        except ValueError:
            return None
    return None
