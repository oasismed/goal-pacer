"""seguranca.py: as permissões que protegem os dados e o código que os jobs rodam.

Usado pelo ``status --doctor`` (item "permissões") e pelo instalador (``endurecer``)::

    pastas privadas   raiz, jobs/, jobs/logs/, dados/          nada para grupo e outros (0700)
    arquivos privados jobs/instalacao.json, painel-aparelhos    nada para grupo e outros (0600)
    código dos jobs   app/ inteiro (.git incluso: um hook      só o dono altera (sem g+w/o+w)
                      alterável vira código no próximo pull)   e o dono é você
    agendador         plists do launchd / unidades do systemd  só o dono altera
    skill             ~/.claude/skills/goal-pacer              aponta para o app instalado

Tudo por ``lstat`` (symlink não é seguido, exceto a pasta de dados, que pode ser um link
escolhido na instalação); nunca muda nada sozinho: ``endurecer`` só roda no instalador.

No Windows os bits de modo não dizem quem acessa (quem decide é a ACL do NTFS, e a pasta do usuário já é só dele):
as conferências de modo não acusam nada e ``endurecer`` não mexe em nada lá.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable, NamedTuple, Optional

WINDOWS = os.name == "nt"
MODO_PASTA_PRIVADA = 0o700
MODO_ARQUIVO_PRIVADO = 0o600
ABERTO_PARA_OUTROS = 0o077
ALTERAVEL_POR_OUTROS = 0o022


class Problema(NamedTuple):
    tipo: (
        str  # pasta_aberta | arquivo_aberto | codigo_alteravel | codigo_de_outro | agendador_alteravel | skill_desviada
    )
    caminho: Path
    modo: str = ""
    quantos: int = 1
    alvo: str = ""


def _modo(estado: os.stat_result) -> str:
    return "%04o" % stat.S_IMODE(estado.st_mode)


def _uid() -> Optional[int]:
    return os.getuid() if hasattr(os, "getuid") else None


def pastas_privadas(pastas: Iterable[Path]) -> list[Problema]:
    if WINDOWS:
        return []
    problemas = []
    for pasta in pastas:
        try:
            estado = os.stat(str(pasta))
        except OSError:
            continue
        if stat.S_ISDIR(estado.st_mode) and estado.st_mode & ABERTO_PARA_OUTROS:
            problemas.append(Problema("pasta_aberta", pasta, _modo(estado)))
    return problemas


def arquivos_privados(arquivos: Iterable[Path]) -> list[Problema]:
    if WINDOWS:
        return []
    problemas = []
    for arquivo in arquivos:
        try:
            estado = os.lstat(str(arquivo))
        except OSError:
            continue
        if stat.S_ISREG(estado.st_mode) and estado.st_mode & ABERTO_PARA_OUTROS:
            problemas.append(Problema("arquivo_aberto", arquivo, _modo(estado)))
    return problemas


def _arvore(raiz: Path) -> Iterable[tuple[Path, os.stat_result]]:
    for pasta, subpastas, nomes in os.walk(str(raiz)):
        for nome in subpastas + nomes:
            caminho = Path(pasta) / nome
            try:
                yield caminho, os.lstat(str(caminho))
            except OSError:
                continue
    try:
        yield raiz, os.lstat(str(raiz))
    except OSError:
        return


def codigo_protegido(app: Path) -> list[Problema]:
    """Um problema por tipo, com o primeiro exemplo e quantos caminhos caem nele."""
    if WINDOWS:
        return []
    uid = _uid()
    alteraveis: list[Path] = []
    de_outro: list[Path] = []
    for caminho, estado in _arvore(app):
        if stat.S_ISLNK(estado.st_mode):
            continue
        if estado.st_mode & ALTERAVEL_POR_OUTROS:
            alteraveis.append(caminho)
        if uid is not None and estado.st_uid != uid:
            de_outro.append(caminho)
    problemas = []
    if alteraveis:
        problemas.append(Problema("codigo_alteravel", min(alteraveis), quantos=len(alteraveis)))
    if de_outro:
        problemas.append(Problema("codigo_de_outro", min(de_outro), quantos=len(de_outro)))
    return problemas


def agendador_protegido(arquivos: Iterable[Path]) -> list[Problema]:
    if WINDOWS:
        return []
    uid = _uid()
    problemas = []
    for arquivo in arquivos:
        try:
            estado = os.lstat(str(arquivo))
        except OSError:
            continue
        if estado.st_mode & ALTERAVEL_POR_OUTROS or (uid is not None and estado.st_uid != uid):
            problemas.append(Problema("agendador_alteravel", arquivo, _modo(estado)))
    return problemas


def skill_aponta_para(link: Path, app: Path) -> list[Problema]:
    if not link.is_symlink():
        return []
    alvo = os.readlink(str(link))
    if Path(os.path.abspath(link.parent / alvo)) != Path(os.path.abspath(app)):
        return [Problema("skill_desviada", link, alvo=alvo)]
    return []


def endurecer(app: Path, pastas: Iterable[Path] = (), arquivos: Iterable[Path] = ()) -> int:
    """Tira escrita de grupo e outros do código, fecha pastas (0700) e arquivos (0600); devolve quantos mudaram."""
    if WINDOWS:
        return 0
    mudados = 0
    for caminho, estado in _arvore(app):
        if not stat.S_ISLNK(estado.st_mode) and estado.st_mode & ALTERAVEL_POR_OUTROS:
            os.chmod(str(caminho), stat.S_IMODE(estado.st_mode) & ~ALTERAVEL_POR_OUTROS)
            mudados += 1
    for alvo, modo in [(p, MODO_PASTA_PRIVADA) for p in pastas] + [(a, MODO_ARQUIVO_PRIVADO) for a in arquivos]:
        try:
            estado = os.lstat(str(alvo))
        except OSError:
            continue
        if not stat.S_ISLNK(estado.st_mode) and stat.S_IMODE(estado.st_mode) & ABERTO_PARA_OUTROS:
            os.chmod(str(alvo), modo)
            mudados += 1
    return mudados
