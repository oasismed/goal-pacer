"""tls.py: HTTPS do painel na rede de casa, com certificado autoassinado gerado na própria máquina.

A stdlib serve TLS (``ssl``) mas não gera chave, então o certificado sai do ``openssl`` do sistema (o LibreSSL do
macOS, o OpenSSL do Linux; ``GP_OPENSSL`` aponta outro). Sem ``openssl``, ou se a geração falhar, o painel na rede
segue em HTTP como antes e o cartão avisa. O certificado fica em ``~/.goal-pacer/jobs/painel-tls/`` (pasta 0700,
chave 0600) e vale 825 dias; perto do fim, é gerado outro na abertura seguinte do painel.

Não há autoridade que confirme o certificado: o celular mostra um aviso na primeira abertura. A impressão digital
(sha256 do certificado, a mesma que o navegador mostra nos detalhes) aparece no cartão do computador para a pessoa
conferir antes de aceitar.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import ssl
import subprocess
import time
from pathlib import Path
from typing import NamedTuple, Optional

ENV_OPENSSL = "GP_OPENSSL"
NOME_PASTA = "painel-tls"
NOME_CERTIFICADO = "certificado.pem"
NOME_CHAVE = "chave.pem"
DIAS_VALIDADE = 825
DIAS_RENOVAR = 800  # certificado mais velho que isso é refeito (pela idade do arquivo)
TIMEOUT_OPENSSL_S = 60
PRIMEIRO_BYTE_TLS = 0x16  # registro de handshake: todo ClientHello começa assim


class Tls(NamedTuple):
    contexto: ssl.SSLContext
    impressao: str


def openssl() -> Optional[str]:
    return os.environ.get(ENV_OPENSSL) or shutil.which("openssl")


def impressao(certificado: Path) -> str:
    """sha256 do certificado em DER, em pares hexadecimais separados por dois-pontos."""
    der = ssl.PEM_cert_to_DER_cert(certificado.read_text(encoding="utf-8"))
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def _valido(certificado: Path, chave: Path) -> bool:
    try:
        idade_dias = (time.time() - certificado.stat().st_mtime) / 86400
        return chave.is_file() and idade_dias < DIAS_RENOVAR
    except OSError:
        return False


def _gerar(pasta: Path, certificado: Path, chave: Path) -> bool:
    binario = openssl()
    if not binario:
        return False
    pasta.mkdir(parents=True, exist_ok=True)
    os.chmod(pasta, 0o700)
    temporaria, cert_tmp = pasta / (NOME_CHAVE + ".tmp"), pasta / (NOME_CERTIFICADO + ".tmp")
    argv = [
        binario,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-sha256",
        "-days",
        str(DIAS_VALIDADE),
        "-subj",
        "/CN=Goal Pacer",
        "-keyout",
        str(temporaria),
        "-out",
        str(cert_tmp),
    ]
    velho = os.umask(0o077)  # a chave nasce 0600
    try:
        proc = subprocess.run(
            argv, capture_output=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_OPENSSL_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        os.umask(velho)
    if proc.returncode != 0 or not temporaria.is_file() or not cert_tmp.is_file():
        for resto in (temporaria, cert_tmp):
            resto.unlink(missing_ok=True)
        return False
    os.chmod(temporaria, 0o600)
    os.replace(temporaria, chave)
    os.replace(cert_tmp, certificado)
    return True


def do_painel(jobs: Path) -> Optional[Tls]:
    """Contexto TLS do painel na rede e a impressão digital; None quando não há como servir HTTPS."""
    pasta = jobs / NOME_PASTA
    certificado, chave = pasta / NOME_CERTIFICADO, pasta / NOME_CHAVE
    try:
        if not _valido(certificado, chave) and not _gerar(pasta, certificado, chave):
            return None
        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        contexto.load_cert_chain(str(certificado), str(chave))
        return Tls(contexto, impressao(certificado))
    except (OSError, ValueError, ssl.SSLError):
        return None
