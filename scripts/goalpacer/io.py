"""Escrita atômica com .bak, JSON e lock único da pasta de dados.

Implementa os achados 2.2 (atômico + .bak + recuperar) e 4.2 (lock único em
``DATA_DIR/.lock``, espera com polling, lock obsoleto) do plano, com as
primitivas provadas no spike (§4.4): ``mkstemp`` no mesmo diretório +
``fsync`` + ``os.replace``; ``os.open(O_CREAT | O_EXCL)``.

Ciclo do lock::

    adquirir()
       |
       v
    O_CREAT|O_EXCL ok? --sim--> grava {pid, criado_em, run_id} --> segura
       |                                                             |
      não (EEXIST)                                                   v
       |                                                        liberar()
       v                                                    (só se pid == os.getpid())
    lê o arquivo: pid vivo? idade (mtime) <= obsoleto_s?
       |                     |
      não (obsoleto)        sim (preso)
       |                     |
       v                     v
    renomeia para nome     espera até espera_s (polling a cada intervalo_s)
    único, confere inode     |
    e mtime, apaga, tenta    v
    de novo (uma vez)   GpErro(EXIT_IO, "lock preso há N min (pid P)")

A idade do lock é medida pelo mtime do arquivo contra ``time.time()``
(relógio de parede real): ``--agora``/``GP_AGORA`` fixam o instante
simulado do produto, não o tempo de vida de um processo, e um lock vivo
não pode ser roubado por causa deles. ``criado_em`` no arquivo é só
informação (vem de ``clock.agora``).

Atenção ao nome: este módulo se chama ``io`` dentro do pacote; a stdlib
``io`` continua acessível por importação absoluta. Nunca rode Python com
``scripts/goalpacer/`` como cwd ou em ``sys.path``.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from goalpacer import clock, processos
from goalpacer.base import ENV_RUN_ID, EXIT_IO, EXIT_VALIDACAO, GpErro

SUFIXO_BAK = ".bak"
LOCK_OBSOLETO_S = 45 * 60

# Um lock com conteúdo ilegível só é descartado quando seu mtime tem mais
# que isto: entre o O_CREAT|O_EXCL de outro processo e a gravação do JSON o
# arquivo existe vazio por um instante, e não pode ser roubado nesse meio.
LOCK_GRACA_S = 10.0


def caminho_bak(path: Path) -> Path:
    """``<nome>.bak`` ao lado de ``path`` (``registro.json`` → ``registro.json.bak``)."""
    path = Path(path)
    return path.with_name(path.name + SUFIXO_BAK)


def _substituir(path: Path, dados: bytes) -> None:
    """Grava ``dados`` em ``path`` via temporário no mesmo diretório + fsync +
    ``os.replace``. Em falha, o temporário é removido e a exceção propaga."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        _trocar(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


TENTATIVAS_TROCA_WINDOWS = 20


def _trocar(tmp: str, path: Path) -> None:
    """``os.replace``; no Windows, o arquivo aberto por outro processo (o painel lendo) recusa a troca por instantes:
    tenta outra vez por até um segundo antes de desistir."""
    for _ in range((TENTATIVAS_TROCA_WINDOWS if processos.WINDOWS else 1) - 1):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def escrever_atomico(path: Path, conteudo: Union[str, bytes], *, bak: bool = True) -> None:
    """Grava ``conteudo`` em ``path`` de forma atômica.

    Cria um temporário no MESMO diretório (``mkstemp``), escreve (texto em
    UTF-8), ``fsync``, ``os.replace``. Antes disso, com ``bak=True`` e o
    arquivo já existente, copia a versão anterior para ``<nome>.bak`` (também
    de forma atômica). A pasta pai é criada se não existir.
    Falha de IO é ``GpErro(EXIT_IO)``; o temporário é removido. ``path``
    que é um symlink é recusado com ``GpErro(EXIT_IO)`` (o .bak copiaria
    conteúdo de fora e o replace trocaria o link). ``conteudo`` só aceita
    ``str``, ``bytes``, ``bytearray`` ou ``memoryview`` (outro tipo é
    ``TypeError``: ``bytes(5)`` gravaria cinco zeros).
    """
    path = Path(path)
    if isinstance(conteudo, str):
        dados = conteudo.encode("utf-8")
    elif isinstance(conteudo, (bytes, bytearray, memoryview)):
        dados = bytes(conteudo)
    else:
        raise TypeError("escrever_atomico: conteúdo deve ser str ou bytes, veio %s" % type(conteudo).__name__)
    if path.is_symlink():
        raise GpErro(EXIT_IO, "não gravo em symlink: %s" % path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if bak and path.is_file():
            _substituir(caminho_bak(path), path.read_bytes())
        _substituir(path, dados)
    except OSError as e:
        raise GpErro(EXIT_IO, "falha ao gravar %s: %s" % (path, e)) from e


def ler_json(path: Path) -> Any:
    """Lê JSON em UTF-8. Arquivo ausente ou inválido é ``GpErro(EXIT_IO)``."""
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise GpErro(EXIT_IO, "não foi possível ler %s: %s" % (path, e)) from e
    except ValueError as e:
        raise GpErro(EXIT_IO, "JSON inválido em %s: %s" % (path, e)) from e


def escrever_json(path: Path, obj: Any) -> None:
    """Grava JSON determinístico (``ensure_ascii=False``, ``indent=2``,
    ``sort_keys=True``, newline final) via ``escrever_atomico`` com .bak.
    ``NaN``/``Infinity`` não são JSON (``JSON.parse`` recusa): ``allow_nan=False``,
    e o ``ValueError`` vira ``GpErro(EXIT_VALIDACAO)``."""
    try:
        texto = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except ValueError as e:
        raise GpErro(EXIT_VALIDACAO, "JSON de %s com número não finito: %s" % (path, e)) from e
    escrever_atomico(path, texto, bak=True)


def _json_valido(path: Path) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
    except (OSError, ValueError):
        return False
    return True


def recuperar(path: Path) -> bool:
    """Restaura ``path`` a partir de ``<path>.bak`` quando o JSON não parseia.

    Devolve True se restaurou; False se o arquivo já era válido ou não há
    .bak utilizável (ausente ou também inválido). Nunca apaga o .bak: a
    restauração grava ``path`` sem gerar um novo .bak.
    """
    path = Path(path)
    if _json_valido(path):
        return False
    bak = caminho_bak(path)
    if not _json_valido(bak):
        return False
    escrever_atomico(path, bak.read_bytes(), bak=False)  # falha de IO já sai como GpErro(EXIT_IO)
    return True


def _pid_vivo(pid: Any) -> bool:
    """True se existe um processo com ``pid`` (``processos.vivo``: no Windows ``os.kill(pid, 0)`` encerraria o processo).
    Valores que não são pid positivo contam como mortos."""
    return processos.vivo(pid)


def _agora_utc() -> datetime:
    return clock.agora().astimezone(timezone.utc)


TENTATIVAS_WINDOWS = 20
PAUSA_WINDOWS_S = 0.05


def _mexer(operacao: Any, *caminhos: Any) -> None:
    """``os.rename``/``os.unlink`` no arquivo de lock. No Windows, outro processo lendo o lock no mesmo instante (o
    ``open`` de lá não compartilha a exclusão) dá ``PermissionError`` passageiro: tenta de novo por até um segundo."""
    for tentativa in range(TENTATIVAS_WINDOWS):
        try:
            operacao(*caminhos)
            return
        except PermissionError:
            if not processos.WINDOWS or tentativa == TENTATIVAS_WINDOWS - 1:
                raise
            time.sleep(PAUSA_WINDOWS_S)


def _identidade(st: os.stat_result, path: Optional[Path] = None) -> tuple:
    """(inode, mtime em ns, tamanho, conteúdo): identifica um arquivo de lock concreto.

    Só inode e mtime não bastam no Linux: um lock apagado e recriado no mesmo tique do
    relógio pode reaproveitar o inode e o mtime. O conteúdo (pid e instante do dono) desempata."""
    conteudo = b""
    if path is not None:
        try:
            with open(path, "rb") as arquivo:
                conteudo = arquivo.read(4096)
        except OSError:
            conteudo = b""
    return (st.st_ino, st.st_mtime_ns, st.st_size, conteudo)


class Lock:
    """Lock de arquivo com dono (pid), idade e detecção de obsoleto.

    ``espera_s`` limita a espera por um lock preso (0 = falha imediata);
    ``obsoleto_s`` é a idade (mtime, relógio real) a partir da qual um lock
    é descartado mesmo com pid vivo; ``intervalo_s`` é o passo do polling.
    Suporta ``with``.
    """

    def __init__(
        self,
        path: Path,
        *,
        espera_s: float = 0,
        obsoleto_s: float = LOCK_OBSOLETO_S,
        intervalo_s: float = 1.0,
    ) -> None:
        self.path = Path(path)
        self.espera_s = espera_s
        self.obsoleto_s = obsoleto_s
        self.intervalo_s = intervalo_s
        self.adquirido = False

    def adquirir(self) -> None:
        """Cria o lock ou falha com ``GpErro(EXIT_IO, "lock preso há N min (pid P)")``.

        Grava ``{"pid", "criado_em" (ISO UTC), "run_id"}``. Em EEXIST lê o
        arquivo; lock obsoleto (pid inexistente via ``os.kill(pid, 0)`` →
        ``ProcessLookupError``, ou idade > ``obsoleto_s`` pelo mtime, ou
        conteúdo ilegível) é removido por ``_remover_obsoleto`` e a criação é
        tentada de novo uma vez; senão espera até ``espera_s`` antes de
        falhar.
        """
        inicio = time.monotonic()
        tentou_remover = False
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                pass
            except OSError as e:
                raise GpErro(EXIT_IO, "não foi possível criar o lock %s: %s" % (self.path, e)) from e
            else:
                self._gravar(fd)
                self.adquirido = True
                return

            if not tentou_remover:
                identidade = self._obsoleto()
                if identidade is not None:
                    tentou_remover = True
                    self._remover_obsoleto(identidade)
                    continue

            restante = self.espera_s - (time.monotonic() - inicio)
            if restante <= 0:
                raise GpErro(EXIT_IO, self._mensagem_preso())
            time.sleep(max(0.0, min(self.intervalo_s, restante)))

    def _gravar(self, fd: int) -> None:
        conteudo = {
            "pid": os.getpid(),
            "criado_em": _agora_utc().isoformat(timespec="seconds"),
            "run_id": os.environ.get(ENV_RUN_ID) or None,
        }
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(conteudo, f, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            with contextlib.suppress(OSError):
                os.unlink(self.path)
            raise GpErro(EXIT_IO, "não foi possível gravar o lock %s: %s" % (self.path, e)) from e

    def _obsoleto(self) -> Optional[tuple]:
        """Identidade (``_identidade``) do lock se ele pode ser descartado:
        dono morto, velho demais (mtime) ou conteúdo ilegível há mais que
        ``LOCK_GRACA_S``. None se está preso ou já sumiu."""
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        identidade = _identidade(st, self.path)
        idade = max(0.0, time.time() - st.st_mtime)
        info = self.info()
        if info is None:
            return identidade if idade > LOCK_GRACA_S else None
        if not _pid_vivo(info.get("pid")):
            return identidade
        return identidade if idade > self.obsoleto_s else None

    def _remover_obsoleto(self, identidade: tuple) -> bool:
        """Apaga o lock obsoleto sem apagar um lock novo criado no mesmo
        instante por outro processo (TOCTOU entre ``_obsoleto`` e o unlink).

        Renomeia o arquivo para um nome único (atômico: só um dos processos
        que julgaram o lock obsoleto consegue) e confere que o renomeado tem
        a ``identidade`` examinada; se outro processo já o removeu, devolve
        False; se o arquivo no caminho mudou (lock novo), devolve False sem
        apagar e devolve o lock ao lugar quando foi ele o renomeado.
        """
        destino = self.path.with_name(self.path.name + ".obsoleto.%d" % os.getpid())
        try:
            if _identidade(os.stat(self.path), self.path) != identidade:
                return False
            _mexer(os.rename, self.path, destino)
        except FileNotFoundError:
            return False
        except OSError as e:
            raise GpErro(EXIT_IO, "não foi possível remover lock obsoleto %s: %s" % (self.path, e)) from e
        try:
            if _identidade(os.stat(destino), destino) != identidade:
                _mexer(os.rename, destino, self.path)
                return False
            _mexer(os.unlink, destino)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise GpErro(EXIT_IO, "não foi possível remover lock obsoleto %s: %s" % (destino, e)) from e
        return True

    def _mensagem_preso(self) -> str:
        info = self.info() or {}
        idade = self.idade()
        minutos = int(idade // 60) if idade is not None and idade >= 0 else 0
        return "lock preso há %d min (pid %s)" % (minutos, info.get("pid", "?"))

    def liberar(self) -> None:
        """Remove o lock só se o pid gravado for o próprio processo."""
        self.adquirido = False
        info = self.info()
        if info is None or info.get("pid") != os.getpid():
            return
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise GpErro(EXIT_IO, "não foi possível remover o lock %s: %s" % (self.path, e)) from e

    def info(self) -> Optional[dict]:
        """Conteúdo do lock (``pid``, ``criado_em``, ``run_id``) ou None
        (ausente, ilegível ou sem a forma esperada)."""
        try:
            with open(self.path, encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(dados, dict):
            return None
        return dados

    def idade(self) -> Optional[float]:
        """Segundos desde a criação do arquivo (mtime contra ``time.time()``;
        o lock é gravado uma vez) ou None se não existe. Independe de
        ``--agora``/``GP_AGORA`` e do ``criado_em`` gravado."""
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            return None
        return max(0.0, time.time() - mtime)

    def estado(self) -> tuple:
        """``(situacao, info, idade_s)`` para o ``status --doctor``: situação
        ``livre`` (sem arquivo), ``ativo`` (dono vivo e dentro de
        ``obsoleto_s``) ou ``obsoleto`` (o que ``adquirir`` descartaria)."""
        idade = self.idade()
        if idade is None:
            return "livre", None, None
        return ("obsoleto" if self._obsoleto() is not None else "ativo"), self.info(), idade

    def __enter__(self) -> Lock:
        self.adquirir()
        return self

    def __exit__(self, *_excecao: object) -> None:
        self.liberar()
