"""migracoes.py: migrações de esquema da pasta de dados, com backup e volta atrás automática.

Uma migração é ``Migracao(de, para, descricao, aplicar)``. ``aplicar(dados)`` recebe a pasta
na versão ``de`` e deixa os arquivos na forma de ``para``; lê e grava bruto (JSON e
front-matter sem coagir), porque o esquema do código já é o novo. O executor::

    versão da pasta (contexto.md, registro.json, registro-AAAA.json e perfil.json concordam;
                     divergentes ou mais nova que o código = recusa, nunca rebaixa)
      -> cadeia de MIGRACOES até schema.SCHEMA_VERSION (sem buraco, senão recusa)
      -> backup zip de tudo menos inbox/ e backups/ (pasta 0700, arquivo 0600)
      -> cada passo e o schema_version novo em todos os arquivos versionados
      -> conferência com o código novo: validar grafo e carregar o registro
      -> qualquer erro: restaura o zip (inclusive apagando o que a migração criou) e devolve o erro
      -> sucesso: mantém os MANTER_BACKUPS backups mais novos

Quem chama segura o lock da pasta (``migrar.py --aplicar`` pega o lock; no job ele é herdado).
Mudança compatível (campo novo com padrão, valor novo de enum) não sobe a versão e não precisa
de migração: o leitor aplica os padrões.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional

from goalpacer import clock, frontmatter, io as gpio, schema
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

PASTA_BACKUPS = "backups"
MANTER_BACKUPS = 5
FORA_DO_BACKUP = ("backups", "inbox")


class Migracao(NamedTuple):
    de: int
    para: int
    descricao: str
    aplicar: Callable[[Path], list[str]]


# Em ordem. Vazio enquanto o esquema só teve mudanças compatíveis (v1).
MIGRACOES: tuple = ()


# --- versão ---------------------------------------------------------------------------------


def arquivos_versionados(dados: Path) -> list[Path]:
    candidatos = [dados / schema.CAMINHOS["contexto"], dados / "registro.json", dados / "perfil.json"]
    candidatos += sorted(dados.glob("registro-[0-9][0-9][0-9][0-9].json"))
    return [p for p in candidatos if p.exists()]


def _ler_versao(path: Path) -> Any:
    if path.suffix == ".md":
        return frontmatter.ler_arquivo(path)[0].get("schema_version")
    return gpio.ler_json(path).get("schema_version")


def versao_da_pasta(dados: Path) -> Optional[int]:
    """Versão comum dos arquivos versionados; ``None`` numa pasta sem onboarding."""
    versoes = {}
    for path in arquivos_versionados(dados):
        try:
            versoes[path.name] = int(str(_ler_versao(path)))
        except (ValueError, GpErro):
            raise GpErro(EXIT_VALIDACAO, "%s sem schema_version legível" % path.name) from None
    if not versoes:
        return None
    if len(set(versoes.values())) > 1:
        raise GpErro(
            EXIT_VALIDACAO,
            "versões misturadas na pasta de dados (%s); restaure o último backup em %s/"
            % (", ".join("%s v%d" % par for par in sorted(versoes.items())), PASTA_BACKUPS),
        )
    return next(iter(versoes.values()))


def plano(de: int, para: int, migracoes: Optional[tuple] = None) -> list[Migracao]:
    migracoes = MIGRACOES if migracoes is None else migracoes
    if de > para:
        raise GpErro(
            EXIT_VALIDACAO,
            "a pasta de dados está no esquema v%d, mais novo que o deste app (v%d); atualize o app com ./install.sh --update"
            % (de, para),
        )
    passos, atual = [], de
    while atual < para:
        passo = next((m for m in migracoes if m.de == atual), None)
        if passo is None or passo.para <= atual:
            raise GpErro(EXIT_VALIDACAO, "sem migração do esquema v%d para v%d neste app" % (atual, para))
        passos.append(passo)
        atual = passo.para
    return passos


def _gravar_versao(dados: Path, versao: int) -> None:
    for path in arquivos_versionados(dados):
        if path.suffix == ".md":
            bruto, corpo = frontmatter.ler_arquivo(path)
            bruto["schema_version"] = versao
            frontmatter.escrever_arquivo(path, bruto, corpo)
        else:
            conteudo = gpio.ler_json(path)
            conteudo["schema_version"] = versao
            gpio.escrever_json(path, conteudo)


# --- backup ---------------------------------------------------------------------------------


def _arquivos_da_pasta(dados: Path) -> list[Path]:
    saida = []
    for raiz, pastas, nomes in os.walk(dados):
        relativo = Path(raiz).relative_to(dados)
        if relativo.parts and relativo.parts[0] in FORA_DO_BACKUP:
            pastas[:] = []
            continue
        pastas[:] = [p for p in pastas if not (not relativo.parts and p in FORA_DO_BACKUP)]
        for nome in nomes:
            path = Path(raiz) / nome
            if nome != ".lock" and path.is_file() and not path.is_symlink():
                saida.append(path)
    return sorted(saida)


def fazer_backup(dados: Path, rotulo: str, agora: datetime) -> Path:
    pasta = dados / PASTA_BACKUPS
    pasta.mkdir(exist_ok=True)
    os.chmod(str(pasta), 0o700)
    destino = pasta / ("%s-%s.zip" % (agora.strftime("%Y%m%d-%H%M%S"), rotulo))
    temporario = destino.with_name(destino.name + ".parcial")
    with zipfile.ZipFile(str(temporario), "w", compression=zipfile.ZIP_DEFLATED) as arquivo:
        for path in _arquivos_da_pasta(dados):
            arquivo.write(str(path), path.relative_to(dados).as_posix())
    os.chmod(str(temporario), 0o600)
    os.replace(str(temporario), str(destino))
    return destino


def restaurar_backup(dados: Path, zip_path: Path) -> None:
    """Deixa a pasta exatamente como no zip (fora inbox/ e backups/), recusando nomes que saiam da pasta."""
    raiz = dados.resolve()
    with zipfile.ZipFile(str(zip_path)) as arquivo:
        nomes = arquivo.namelist()
        _conferir_nomes_do_zip(raiz, nomes)
        guardados = set(nomes)
        for path in _arquivos_da_pasta(dados):
            if path.relative_to(dados).as_posix() not in guardados:
                path.unlink()
        for nome in nomes:
            alvo = raiz / nome
            alvo.parent.mkdir(parents=True, exist_ok=True)
            gpio.escrever_atomico(alvo, arquivo.read(nome), bak=False)
    _apagar_pastas_vazias(dados, {Path(nome).parent.as_posix() for nome in nomes} - {"."})


def _conferir_nomes_do_zip(raiz: Path, nomes: list[str]) -> None:
    for nome in nomes:
        alvo = (raiz / nome).resolve()
        if nome.startswith("/") or ".." in Path(nome).parts or raiz not in alvo.parents:
            raise GpErro(EXIT_IO, "backup com caminho fora da pasta de dados: %r" % nome)


def _apagar_pastas_vazias(dados: Path, pastas_do_zip: set[str]) -> None:
    """Pastas vazias criadas depois do backup (pela migração) somem; inbox/, backups/ e as do zip ficam."""
    for pasta_atual, _subpastas, _arquivos in os.walk(dados, topdown=False):
        relativo = Path(pasta_atual).relative_to(dados)
        if not relativo.parts or relativo.parts[0] in FORA_DO_BACKUP or relativo.as_posix() in pastas_do_zip:
            continue
        if not any(Path(pasta_atual).iterdir()):
            Path(pasta_atual).rmdir()


def podar_backups(dados: Path) -> None:
    zips = sorted((dados / PASTA_BACKUPS).glob("*.zip"))
    for antigo in zips[:-MANTER_BACKUPS]:
        antigo.unlink()


# --- executor -------------------------------------------------------------------------------


def migrar(
    dados: Path,
    *,
    simular: bool = False,
    agora: Optional[datetime] = None,
    migracoes: Optional[tuple] = None,
    conferir: Callable[[Path], None],
) -> dict[str, Any]:
    """Leva a pasta até ``schema.SCHEMA_VERSION``. ``conferir`` roda com o código novo depois dos passos e, se
    levantar, a pasta volta ao backup; quem chama injeta (o ``migrar.py`` confere grafo e registro), assim o pacote
    não depende dos CLIs."""
    para = schema.SCHEMA_VERSION
    de = versao_da_pasta(dados)
    if de is None:
        return {"de": None, "para": para, "passos": [], "backup": None, "mudancas": [], "estado": "sem_onboarding"}
    passos = plano(de, para, migracoes)
    resultado: dict[str, Any] = {
        "de": de,
        "para": para,
        "passos": ["v%d -> v%d: %s" % (m.de, m.para, m.descricao) for m in passos],
        "backup": None,
        "mudancas": [],
        "estado": "em_dia" if not passos else ("simulado" if simular else "migrado"),
    }
    if not passos or simular:
        return resultado
    agora = agora or clock.agora()
    zip_path = fazer_backup(dados, "v%d-para-v%d" % (de, para), agora)
    resultado["backup"] = str(zip_path)
    try:
        for passo in passos:
            resultado["mudancas"] += list(passo.aplicar(dados) or [])
            _gravar_versao(dados, passo.para)
        conferir(dados)
    except Exception as erro:
        restaurar_backup(dados, zip_path)
        mensagem = erro.mensagem if isinstance(erro, GpErro) else "%s: %s" % (type(erro).__name__, erro)
        raise GpErro(
            EXIT_VALIDACAO,
            "migração v%d -> v%d desfeita, pasta restaurada do backup %s: %s" % (de, para, zip_path.name, mensagem),
        ) from erro
    podar_backups(dados)
    return resultado


def resumo_json(resultado: dict[str, Any]) -> str:
    return json.dumps(resultado, ensure_ascii=False)
