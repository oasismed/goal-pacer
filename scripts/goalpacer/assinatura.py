"""Versões publicadas e assinadas: o que o ``--update`` aceita trazer para o computador de quem instalou.

Uma versão é uma tag anotada ``v<maior>.<menor>.<correção>`` assinada com uma chave SSH listada em
``release/assinantes`` (formato ``allowed_signers`` do OpenSSH). O zip da versão vem com ``<zip>.sig``, assinado com a
mesma chave no espaço de nomes ``goal-pacer-release``. Quem confere usa sempre o arquivo de assinantes da versão JÁ
instalada, copiado antes de qualquer checkout: a versão nova não consegue trocar a lista que vai julgá-la. Trocar de
chave é publicar, assinada pela chave antiga, uma versão com a chave nova na lista.

O zip também leva ``release/manifesto.json`` (versão, sha256, tamanho e bit de execução de cada arquivo) e
``release/manifesto.json.sig``: a pasta do zip já descompactado é uma versão conferível sem o zip. É o que permite
atualizar com um clique duplo no instalador da versão nova (``copiar_versao``: confere a assinatura do manifesto e copia
só os arquivos listados, cada um com o sha256 conferido nos bytes copiados).

Sem git 2.34 ou ``ssh-keygen -Y`` (OpenSSH 8.1, o do Windows 10) não há conferência, e sem conferência não há update:
nunca se pula a assinatura em silêncio. Quem assinou sai da própria lista (``principais``), sem o ``find-principals``,
que só existe a partir do OpenSSH 8.2.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional

from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

ARQUIVO_ASSINANTES = Path("release") / "assinantes"
ARQUIVO_MANIFESTO = Path("release") / "manifesto.json"
FORMATO_MANIFESTO = 1
ESPACO_ZIP = "goal-pacer-release"
RE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
RE_VERSAO_APP = re.compile(r'^VERSAO_APP = "(\d+\.\d+\.\d+)"', re.MULTILINE)
GIT_MINIMO = (2, 34)
TIMEOUT_S = 120
LIMITE_ZIP_BYTES = 200 * 1024 * 1024

Versao = tuple[int, int, int]


def versao_de(texto: str) -> Optional[Versao]:
    """``"0.1.0"`` ou ``"v0.1.0"`` → ``(0, 1, 0)``; qualquer outra forma → None."""
    m = RE_TAG.match(texto if texto.startswith("v") else "v" + texto)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def versao_instalada(app: Path) -> Versao:
    """``VERSAO_APP`` lido do código do app instalado, sem importá-lo; instalação anterior às versões conta como 0.0.0."""
    try:
        texto = (app / "scripts" / "goalpacer" / "base.py").read_text(encoding="utf-8")
    except OSError:
        return (0, 0, 0)
    m = RE_VERSAO_APP.search(texto)
    lida = versao_de(m.group(1)) if m else None
    return lida or (0, 0, 0)


def maior_tag_nova(tags: Iterable[str], atual: Versao) -> Optional[str]:
    """A tag de versão mais alta acima de ``atual``; nomes fora de ``vX.Y.Z`` são ignorados."""
    candidatas = [(versao_de(t), t) for t in tags if RE_TAG.match(t)]
    novas = [(v, t) for v, t in candidatas if v is not None and v > atual]
    return max(novas)[1] if novas else None


def copiar_assinantes(app: Path, destino: Path) -> Path:
    """Copia a lista de assinantes da versão instalada para ``destino`` (fora do app); sem lista, não há update."""
    origem = app / ARQUIVO_ASSINANTES
    if not origem.is_file():
        raise GpErro(
            EXIT_VALIDACAO,
            "o app instalado não tem %s: sem lista de assinantes não dá para conferir a versão nova; "
            "reinstale a partir do zip ou do clone de uma versão publicada" % ARQUIVO_ASSINANTES.as_posix(),
        )
    copia = destino / "assinantes"
    shutil.copyfile(str(origem), str(copia))
    return copia


def _rodar(argv: list[str], *, entrada: Optional[Path] = None) -> tuple[int, str]:
    try:
        if entrada is None:
            proc = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
                check=False,
            )
        else:
            with open(entrada, "rb") as arquivo:
                proc = subprocess.run(
                    argv, stdin=arquivo, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
                )
    except (OSError, subprocess.TimeoutExpired) as erro:
        return 127, str(erro)
    return proc.returncode, "\n".join(p.strip() for p in (proc.stdout, proc.stderr) if p.strip())


def conferir_git(git: str) -> None:
    """Recusa git sem assinatura SSH (anterior a 2.34)."""
    codigo, saida = _rodar([git, "--version"])
    m = re.search(r"(\d+)\.(\d+)", saida)
    if codigo != 0 or m is None or (int(m.group(1)), int(m.group(2))) < GIT_MINIMO:
        raise GpErro(
            EXIT_VALIDACAO,
            "o git desta máquina (%s) não confere tag assinada com chave SSH (precisa de %d.%d ou mais novo); "
            "atualize o git ou atualize pelo zip assinado" % (saida or git, *GIT_MINIMO),
        )


def verificar_tag(git: str, repo: Path, tag: str, assinantes: Path) -> None:
    """``git verify-tag`` só com a chave SSH da lista; tag sem assinatura ou de outra chave é ``GpErro``."""
    conferir_git(git)
    codigo, saida = _rodar(
        [
            git,
            "-C",
            str(repo),
            "-c",
            "gpg.format=ssh",
            "-c",
            "gpg.ssh.allowedSignersFile=%s" % assinantes,
            "verify-tag",
            tag,
        ]
    )
    if codigo != 0:
        ultima = saida.split("\n")[-1][:200] if saida else "sem saída"
        raise GpErro(EXIT_VALIDACAO, "a tag %s não tem assinatura de quem publica o Goal Pacer (%s)" % (tag, ultima))


def _ssh_keygen() -> str:
    return shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"


def principais(assinantes: Path) -> list[str]:
    """Identidades da lista ``allowed_signers`` (primeiro campo, separado por vírgula, aspas opcionais), sem padrões
    com ``*``/``?`` nem negações: são os nomes que o ``ssh-keygen -Y verify -I`` aceita."""
    try:
        linhas = assinantes.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    nomes = [nome for linha in linhas for nome in _identidades(linha.strip())]
    return list(dict.fromkeys(nomes))


def _identidades(linha: str) -> list[str]:
    if not linha or linha.startswith("#"):
        return []
    campo = linha[1 : linha.find('"', 1)] if linha.startswith('"') else linha.split()[0]
    partes = [parte.strip() for parte in campo.split(",")]
    return [nome for nome in partes if nome and not nome.startswith("!") and "*" not in nome and "?" not in nome]


def _conferir_assinatura(arquivo: Path, assinatura: Path, assinantes: Path) -> str:
    """Quem da lista assinou ``arquivo`` (espaço ``goal-pacer-release``); ninguém é ``GpErro``."""
    ultima = ""
    for nome in principais(assinantes):
        argv = [
            _ssh_keygen(),
            "-Y",
            "verify",
            "-f",
            str(assinantes),
            "-I",
            nome,
            "-n",
            ESPACO_ZIP,
            "-s",
            str(assinatura),
        ]
        codigo, saida = _rodar(argv, entrada=arquivo)
        if codigo == 0:
            return nome
        if codigo == 127:
            raise GpErro(
                EXIT_VALIDACAO,
                "sem o ssh-keygen do OpenSSH não dá para conferir %s (%s); no Windows, ative o Cliente OpenSSH em "
                "Configurações > Sistema > Recursos opcionais" % (arquivo.name, saida[:120]),
            )
        ultima = saida
    raise GpErro(
        EXIT_VALIDACAO,
        "%s não foi assinado por quem publica o Goal Pacer, ou mudou depois de assinado (a assinatura não confere: %s)"
        % (arquivo.name, (ultima or "lista sem assinantes")[:160]),
    )


def verificar_arquivo(arquivo: Path, assinantes: Path) -> str:
    """Confere ``<arquivo>.sig`` contra a lista (espaço ``goal-pacer-release``); devolve quem assinou."""
    assinatura = arquivo.with_name(arquivo.name + ".sig")
    if not assinatura.is_file():
        raise GpErro(
            EXIT_VALIDACAO, "falta %s ao lado do zip: baixe os dois arquivos da página da versão" % assinatura.name
        )
    return _conferir_assinatura(arquivo, assinatura, assinantes)


# --- manifesto da versão ---------------------------------------------------------------------


def manifesto(versao: str, arquivos: dict[str, bytes], executaveis: Iterable[str]) -> bytes:
    """O manifesto de uma versão (bytes do JSON, determinístico): sha256, tamanho e bit de execução por arquivo."""
    marcados = set(executaveis)
    corpo = {
        "formato": FORMATO_MANIFESTO,
        "versao": versao,
        "arquivos": {
            nome: {"sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados), "executavel": nome in marcados}
            for nome, dados in sorted(arquivos.items())
        },
    }
    return (json.dumps(corpo, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def versao_do_manifesto(pasta: Path) -> Optional[Versao]:
    """A versão que o manifesto da pasta diz ser, sem conferir nada (só para decidir se vale conferir)."""
    try:
        dados = json.loads((pasta / ARQUIVO_MANIFESTO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return versao_de(str(dados.get("versao") or "")) if isinstance(dados, dict) else None


def _relativo_seguro(nome: Any) -> PurePosixPath:
    caminho = PurePosixPath(nome) if isinstance(nome, str) else PurePosixPath("/")
    partes = caminho.parts
    if (
        not partes
        or caminho.is_absolute()
        or any(p in ("", ".", "..") for p in partes)
        or "\\" in str(nome)
        or ":" in partes[0]
    ):
        raise GpErro(EXIT_VALIDACAO, "o manifesto tem um caminho fora da pasta: %r" % (nome,))
    return caminho


def _ler_manifesto(bruto: bytes) -> tuple[Versao, dict[str, dict[str, Any]]]:
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise GpErro(EXIT_VALIDACAO, "manifesto da versão ilegível: %s" % erro) from erro
    versao = versao_de(str(dados.get("versao") or "")) if isinstance(dados, dict) else None
    arquivos = dados.get("arquivos") if isinstance(dados, dict) else None
    if dados.get("formato") != FORMATO_MANIFESTO or versao is None or not isinstance(arquivos, dict) or not arquivos:
        raise GpErro(EXIT_VALIDACAO, "manifesto da versão fora do formato %d" % FORMATO_MANIFESTO)
    if sum(int(info.get("bytes") or 0) for info in arquivos.values() if isinstance(info, dict)) > LIMITE_ZIP_BYTES:
        raise GpErro(EXIT_VALIDACAO, "a versão passa de %d MB" % (LIMITE_ZIP_BYTES >> 20))
    return versao, arquivos


def copiar_versao(pasta: Path, destino: Path, assinantes: Path) -> tuple[Versao, str]:
    """Confere o manifesto assinado de ``pasta`` e copia para ``destino`` só os arquivos dele, cada um com sha256 e
    tamanho conferidos nos bytes copiados (nada é lido duas vezes). Devolve a versão e quem assinou."""
    origem = pasta / ARQUIVO_MANIFESTO
    selo = origem.with_name(origem.name + ".sig")
    if not origem.is_file() or not selo.is_file():
        raise GpErro(
            EXIT_VALIDACAO,
            "%s não tem %s e %s.sig: baixe o zip da página de versões"
            % (pasta.name, ARQUIVO_MANIFESTO.as_posix(), origem.name),
        )
    destino.mkdir(parents=True, exist_ok=True)
    conferido = destino / ARQUIVO_MANIFESTO
    conferido.parent.mkdir(parents=True, exist_ok=True)
    conferido.write_bytes(origem.read_bytes())
    shutil.copyfile(str(selo), str(conferido) + ".sig")
    quem = _conferir_assinatura(conferido, Path(str(conferido) + ".sig"), assinantes)
    versao, arquivos = _ler_manifesto(conferido.read_bytes())
    for nome, info in sorted(arquivos.items()):
        relativo = _relativo_seguro(nome)
        if relativo == PurePosixPath(ARQUIVO_MANIFESTO.as_posix()):
            continue
        try:
            dados = (pasta / relativo).read_bytes()
        except OSError as erro:
            raise GpErro(EXIT_VALIDACAO, "falta %s na pasta da versão: baixe o zip outra vez" % nome) from erro
        if (
            not isinstance(info, dict)
            or len(dados) != info.get("bytes")
            or hashlib.sha256(dados).hexdigest() != info.get("sha256")
        ):
            raise GpErro(EXIT_VALIDACAO, "%s não confere com o manifesto assinado: baixe o zip outra vez" % nome)
        alvo = destino / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        if info.get("executavel") and os.name != "nt":
            alvo.chmod(0o755)
    return versao, quem


def _conferir_membros(arquivo: Path, membros: list[zipfile.ZipInfo], raiz: Path) -> None:
    """Tamanho total no teto e cada membro dentro de ``raiz``: nem caminho absoluto, nem ``..``, nem link."""
    if sum(m.file_size for m in membros) > LIMITE_ZIP_BYTES:
        raise GpErro(EXIT_VALIDACAO, "%s passa de %d MB descompactado" % (arquivo.name, LIMITE_ZIP_BYTES >> 20))
    for membro in membros:
        alvo = (raiz / membro.filename).resolve()
        eh_link = (membro.external_attr >> 16) & 0o170000 == 0o120000
        if membro.filename.startswith("/") or eh_link or not (alvo == raiz or raiz in alvo.parents):
            raise GpErro(EXIT_VALIDACAO, "%s tem um caminho fora da pasta: %s" % (arquivo.name, membro.filename))


def extrair_zip(arquivo: Path, destino: Path) -> Path:
    """Extrai o zip da versão sem sair de ``destino`` e devolve a pasta de cima (``goal-pacer-vX.Y.Z/``), com o bit de
    execução de cada arquivo (o ``zipfile`` não o aplica sozinho)."""
    raiz = destino.resolve()
    try:
        with zipfile.ZipFile(str(arquivo)) as pacote:
            membros = pacote.infolist()
            _conferir_membros(arquivo, membros, raiz)
            pacote.extractall(str(raiz))
            for membro in membros:
                modo = (membro.external_attr >> 16) & 0o777
                if modo and not membro.is_dir():
                    (raiz / membro.filename).chmod(modo & 0o755)
    except zipfile.BadZipFile as erro:
        raise GpErro(EXIT_VALIDACAO, "%s não é um zip válido: %s" % (arquivo.name, erro)) from erro
    except OSError as erro:
        raise GpErro(EXIT_IO, "não consegui extrair %s: %s" % (arquivo.name, erro)) from erro
    pastas = [p for p in destino.iterdir() if p.is_dir()]
    if len(pastas) != 1 or not (pastas[0] / "install.sh").is_file():
        raise GpErro(EXIT_VALIDACAO, "%s não tem a pasta do Goal Pacer com o install.sh" % arquivo.name)
    return pastas[0]
