#!/usr/bin/env python3
"""web.py [--porta 8765] [--abrir] [--demo] [--local | --rede [--sem-https] [--manter-acordado]] [--esquecer-aparelhos]: painel no navegador.

Servidor stdlib. Lê a pasta de dados pelo ``painel.py`` e grava só pelas mesmas
funções da skill, sob o lock da pasta::

    GET  /                       painel com o token desta execução (ou a tela de pareamento, na rede)
    GET  /app.css /app.js ...    arquivos de web/ (lista fechada, sem caminho vindo da URL)
    GET  /api/painel             tela Hoje (?data=AAAA-MM-DD)
    GET  /api/objetivos /api/metas /api/checkin /api/status, /api/meta?id=M01   demais telas (painel.py)
    GET  /api/periodo?nivel=trimestre&id=2026-T4   drill-down ano > semestre > trimestre > mês > semana (sem id: o atual)
    POST /api/confirmar          {"task_id"}                              -> checkin.confirmar(feitas)
    POST /api/nao-feita          {"task_id"}                              -> checkin.confirmar(nao_feitas)
    POST /api/decisao            {"meta", "saida", "custo"|"prazo"}       -> checkin.confirmar(decisoes)
    POST /api/checkin            {"feitas", "nao_feitas", "sentimentos", "nota"}  -> checkin.confirmar
    POST /api/sentimento         {"meta", "valor"}                        -> checkin.confirmar(sentimentos)
    POST /api/meta/ajustar       {"meta", "custo"|"prazo"|"impacto"|"objetivo"|"estado"}  -> metas.ajustar
    POST /api/meta/marco         {"meta", "indice", "feito"}              -> metas.marcar_marco
    GET  /api/pareamento         só no Mac: endereço na rede, código e aparelhos pareados
    GET  /api/comecar            só no computador: tela Começar (onboarding pela tela, acoes_locais.modelo)
    POST /api/comecar/detectar   só no computador: onboarding.py detectar (conta Google, calendário Metas, fontes)
    POST /api/comecar/rascunho   {"respostas"}: só no computador, rascunho do onboarding
    POST /api/comecar/gravar     só no computador: grava o rascunho (400 com "erros" por campo recusado)
    POST /api/comecar/primeiro-dia  só no computador: dispara o job diário no agendador
    POST /api/doctor             só no computador: status.py --doctor --json
    POST /api/atualizar          só no computador: instalar.py --update em segundo plano; GET /api/atualizacao lê o log
    POST /api/esquecer-aparelhos só no Mac: revoga todos os aparelhos
    POST /api/parear             {"codigo"}: na rede, troca o código por um cookie de aparelho
    POST /api/erro-front         {"mensagem", "arquivo", "linha", "coluna", "tela"}: erro de JavaScript da tela (só registro local)

Observabilidade (``goalpacer/telemetria.py``, só no computador): cada pedido vira uma linha em
``jobs/logs/eventos-AAAA-MM-DD.jsonl`` com método, rota conhecida (nunca a query nem o corpo), status,
milissegundos, bytes e origem (local, aparelho, rede); exceção inesperada responde 500 em JSON com a
classe ``Desconhecida`` e vira ``painel_erro``. Conexão parada por 15 s cai; acima de 32 conexões
simultâneas a nova é fechada na hora (o celular na rede não prende o processo).

Sem ``--rede`` escuta só em 127.0.0.1. Com ``--rede`` escuta em todas as
interfaces para o celular no mesmo Wi-Fi::

    pedido do próprio Mac (cliente e Host em 127.0.0.1/localhost)  -> como antes, sem pareamento
    pedido da rede (Host = IP do Mac ou <nome>.local)              -> precisa do cookie gp_aparelho
        sem cookie válido: GET / devolve a tela de pareamento; /api/* devolve 403
        POST /api/parear com o código de 6 dígitos (novo a cada abertura, só visível no Mac)
            certo  -> cookie HttpOnly, SameSite=Strict, 90 dias; o servidor guarda só o sha256
            errado -> 403 e meio segundo de espera; 10 erros travam o pareamento até reiniciar

Proteções em todos os modos: ``Host`` só dos nomes acima (DNS rebinding); toda
rota ``/api`` de dados exige ``X-GP-Token`` igual ao token desta execução, que
só a página servida conhece; POST com ``Origin`` de outro lugar é recusado;
corpo JSON até 16 KB; CSP ``default-src 'self'``. O painel não chama conector: só as
ações locais rodam, em subprocesso, os mesmos CLIs da skill que leem a conta (``detectar`` e ``doctor``) ou
disparam o job (``acoes_locais.py``), e só a partir do próprio computador. Sem onboarding o painel abre na tela
Começar em vez de sair. Na rede, com ``openssl`` na máquina, o painel responde em HTTPS na mesma porta
(``goalpacer/tls.py``: certificado autoassinado, impressão digital no cartão do computador; o servidor olha o
primeiro byte da conexão e só embrulha em TLS quem chega em TLS); pedido HTTP da rede é mandado para o HTTPS, o
cookie do aparelho ganha ``Secure`` e o próprio computador segue em HTTP. Sem ``openssl`` (ou com ``--sem-https``)
a rede fica em HTTP, pensada para o Wi-Fi de casa. Aparelhos pareados ficam em ``~/.goal-pacer/jobs/painel-aparelhos.json`` (0600).

``--demo`` monta numa pasta temporária os dados de exemplo de ``demo_painel.py``
(três objetivos, cinco metas, cinco semanas de histórico; offline, zero tokens,
relógio fixo em 28/09/2026 09:50) e serve esse painel; a pasta some ao fechar. ``--manter-acordado`` segura o sono do Mac
enquanto o painel roda (``caffeinate`` no macOS, ``systemd-inhibit`` no Linux).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timedelta
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contextlib

import acoes_locais
import checkin
import onboarding
import painel
from goalpacer import (
    base,
    cli,
    clock,
    conexoes,
    copy,
    execucao,
    io as gpio,
    metas as gpmetas,
    plataforma,
    registro as reg,
    render,
    schema,
    telemetria,
    tls,
)
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_VALIDACAO, GpErro

PORTA_PADRAO = 8765
TETO_CORPO = 16 * 1024
ENV_ENDERECO_ESCUTA = "GP_ENDERECO_ESCUTA"  # testes: endereço de escuta (nunca fora de 127.0.0.1)
ENV_IP_REDE = "GP_IP_REDE"  # testes: IP da rede local mostrado no pareamento
ENV_NOME_LOCAL = "GP_NOME_LOCAL"  # testes: nome .local mostrado no pareamento
TIMEOUT_CONEXAO_S = 15
TETO_CONEXOES = 32
TETO_ERROS_FRONT_MIN = 20
PASTA_WEB = Path(__file__).resolve().parent.parent / "web"
ESTATICOS = {
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/parear.js": ("parear.js", "text/javascript; charset=utf-8"),
    "/icone-180.png": ("icone-180.png", "image/png"),
    "/icone-192.png": ("icone-192.png", "image/png"),
    "/icone-512.png": ("icone-512.png", "image/png"),
    "/fonts/plus-jakarta-sans-latin.woff2": ("fonts/plus-jakarta-sans-latin.woff2", "font/woff2"),
}
# módulos do front (web/js/**/*.js): a lista é lida uma vez, na carga; caminho só casa com um arquivo que existe
ESTATICOS.update(
    {
        "/" + p.relative_to(PASTA_WEB).as_posix(): (
            p.relative_to(PASTA_WEB).as_posix(),
            "text/javascript; charset=utf-8",
        )
        for p in sorted((PASTA_WEB / "js").rglob("*.js"))
    }
)
CSP = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
COOKIE = "gp_aparelho"
DIAS_APARELHO = 90
TETO_APARELHOS = 10
TETO_ERROS_PAREAMENTO = 10
ESPERA_ERRO_S = 0.5
NOME_APARELHOS = "painel-aparelhos.json"
TELAS_GET = {
    "/api/objetivos": painel.modelo_objetivos,
    "/api/metas": painel.modelo_metas,
    "/api/checkin": painel.modelo_checkin,
    "/api/status": painel.modelo_status,
    "/api/conexoes": painel.modelo_conexoes,
}
ESTADOS_AJUSTE = ("ativa", "pausada", "concluida")
TETO_CUSTO_H = 40.0
TETO_NOTA = 280


def ip_na_rede() -> Optional[str]:
    """IPv4 deste computador na rede local (``GP_IP_REDE`` sobrepõe). O ``connect`` de UDP não manda pacote."""
    forcado = os.environ.get(ENV_IP_REDE)
    if forcado:
        return forcado
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


def nome_local() -> Optional[str]:
    """``<nome>.local`` do mDNS: LocalHostName do Bonjour no macOS, hostname no Linux (Avahi). ``GP_NOME_LOCAL`` sobrepõe."""
    forcado = os.environ.get(ENV_NOME_LOCAL)
    if forcado:
        return forcado.lower()
    if plataforma.nome_atual() == "linux":
        nome = socket.gethostname().split(".")[0].strip()
        return (nome + ".local").lower() if nome else None
    try:
        r = subprocess.run(
            ["/usr/sbin/scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    nome = (r.stdout or "").strip()
    return (nome + ".local").lower() if r.returncode == 0 and nome else None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Aparelhos:
    """Aparelhos pareados: só o sha256 do cookie, com validade; arquivo 0600 em jobs/."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._trava = threading.Lock()

    def _ler(self) -> list[dict[str, Any]]:
        try:
            dados = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        itens = dados.get("aparelhos") if isinstance(dados, dict) else None
        agora = clock.instante_real().isoformat(timespec="seconds")
        return [
            i
            for i in (itens or [])
            if isinstance(i, dict) and str(i.get("expira_em", "")) > agora and isinstance(i.get("hash"), str)
        ]

    def _gravar(self, itens: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        gpio.escrever_atomico(
            self.path, json.dumps({"aparelhos": itens}, ensure_ascii=False, indent=2) + "\n", bak=False
        )
        os.chmod(str(self.path), 0o600)

    def quantos(self) -> int:
        return len(self._ler())

    def valido(self, token: Optional[str]) -> bool:
        if not token:
            return False
        alvo = _hash(token)
        return any(hmac.compare_digest(i["hash"], alvo) for i in self._ler())

    def novo(self, nome: str) -> str:
        token = secrets.token_urlsafe(32)
        agora = clock.instante_real()
        with self._trava:
            itens = self._ler()
            itens.append(
                {
                    "hash": _hash(token),
                    "nome": nome[:60],
                    "criado_em": agora.isoformat(timespec="seconds"),
                    "expira_em": (agora + timedelta(days=DIAS_APARELHO)).isoformat(timespec="seconds"),
                }
            )
            self._gravar(itens[-TETO_APARELHOS:])
        return token

    def esquecer(self) -> None:
        with self._trava:
            self._gravar([])


class Painel(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, porta: int, dados: Path, *, rede: bool = False, https: bool = True) -> None:
        # GP_ENDERECO_ESCUTA só para testes: modo rede sem abrir a porta para a rede de verdade
        escuta = os.environ.get(ENV_ENDERECO_ESCUTA) or ("0.0.0.0" if rede else "127.0.0.1")
        super().__init__((escuta, porta), Tratador)
        self.token = secrets.token_urlsafe(24)
        self.dados = dados
        self.rede = rede
        self.demo = False
        self.offline = False  # --offline: o detectar e o doctor da tela leem as fixtures
        self.deteccao: Optional[dict[str, Any]] = None  # o último detectar da tela Começar
        self.login: Optional[Any] = None  # o claude auth login esperando o código (acoes_locais.Login)
        self.porta = self.server_address[1]
        self.hosts_locais = {"127.0.0.1:%d" % self.porta, "localhost:%d" % self.porta}
        self.hosts_rede: set[str] = set()
        self.ip = ip_na_rede() if rede else None
        if rede:
            for nome in (self.ip, nome_local()):
                if nome:
                    self.hosts_rede.add("%s:%d" % (nome, self.porta))
        self.hosts = self.hosts_locais | self.hosts_rede
        self.tls = tls.do_painel(base.jobs_dir()) if rede and https else None
        self.origens = {"http://" + h for h in self.hosts} | {"https://" + h for h in self.hosts_rede}
        self.codigo = "%06d" % secrets.randbelow(10**6) if rede else None
        self.erros_pareamento = 0
        self.trava_pareamento = threading.Lock()
        self.aparelhos = Aparelhos(base.jobs_dir() / NOME_APARELHOS)
        self.vagas = threading.BoundedSemaphore(TETO_CONEXOES)
        self.erros_front: list[float] = []
        self.trava_front = threading.Lock()

    def process_request(self, request: Any, client_address: Any) -> None:
        """Acima de ``TETO_CONEXOES`` conexões abertas a nova é fechada na hora, sem thread."""
        if not self.vagas.acquire(blocking=False):
            telemetria.evento("painel_recusa", motivo="conexoes")
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.vagas.release()
            raise

    def finish_request(self, request: Any, client_address: Any) -> None:
        """Na rede com HTTPS, a conexão que começa com um handshake TLS é embrulhada antes de virar pedido."""
        conexao = self._conexao(request)
        if conexao is None:
            return
        try:
            super().finish_request(conexao, client_address)
        finally:
            if conexao is not request:
                with contextlib.suppress(OSError):
                    conexao.close()

    def _conexao(self, request: Any) -> Optional[Any]:
        if self.tls is None:
            return request
        try:
            request.settimeout(TIMEOUT_CONEXAO_S)
            primeiro = request.recv(1, socket.MSG_PEEK)
            if not primeiro or primeiro[0] != tls.PRIMEIRO_BYTE_TLS:
                return request
            return self.tls.contexto.wrap_socket(request, server_side=True)
        except (OSError, ssl.SSLError):  # handshake recusado (certificado não aceito no celular) ou conexão parada
            return None

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.vagas.release()

    @property
    def endereco(self) -> str:
        return "http://127.0.0.1:%d/" % self.porta

    @property
    def endereco_rede(self) -> Optional[str]:
        esquema = "https" if self.tls else "http"
        return "%s://%s:%d/" % (esquema, self.ip, self.porta) if self.ip else None


class ConsultaInvalida(ValueError):
    """Parâmetro de consulta de uma tela com forma errada (400)."""


class Tratador(BaseHTTPRequestHandler):
    server: Painel
    server_version = "goal-pacer"
    sys_version = ""
    timeout = TIMEOUT_CONEXAO_S  # conexão parada cai (StreamRequestHandler aplica no socket)

    # a assinatura é a da classe base; o registro do pedido é o evento do painel (_atender)
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002
        return None

    def send_response(self, code: int, message: Optional[str] = None) -> None:
        self._status = code
        super().send_response(code, message)

    def send_header(self, keyword: str, value: str) -> None:
        if keyword.lower() == "content-length":
            with contextlib.suppress(ValueError):
                self._bytes = int(value)
        super().send_header(keyword, value)

    def _atender(self, metodo: Any) -> None:
        """Roda o método, responde 500 em JSON se algo inesperado escapar e registra o pedido."""
        self._status, self._bytes, self._classe = None, 0, None
        comeco = time.monotonic()
        rota = urlsplit(self.path).path
        try:
            metodo()
        except (BrokenPipeError, ConnectionResetError):
            self._classe = "ConexaoFechada"
        except Exception as erro:  # noqa: BLE001 - nada escapa sem resposta nem registro
            self._classe = "Desconhecida"
            telemetria.evento(
                "painel_erro",
                metodo=self.command,
                rota=rota if rota in ROTAS_CONHECIDAS else "outra",
                erro=type(erro).__name__,
                detalhe=str(erro),
            )
            if self._status is None:
                with contextlib.suppress(OSError):
                    self._erro(
                        500, "%s: %s" % (execucao.motivo("Desconhecida"), execucao.acao("Desconhecida")), "Desconhecida"
                    )
        finally:
            origem = (
                "local"
                if self._local()
                else ("aparelho" if self.server.rede and self.server.aparelhos.valido(self._cookie()) else "rede")
            )
            telemetria.evento(
                "painel",
                metodo=self.command,
                rota=rota if rota in ROTAS_CONHECIDAS else "outra",
                status=self._status,
                ms=round((time.monotonic() - comeco) * 1000, 1),
                bytes=self._bytes,
                origem=origem,
                classe=self._classe,
            )

    def do_GET(self) -> None:
        if not self._para_https():
            self._atender(self._get)

    def do_POST(self) -> None:
        if not self._para_https():
            self._atender(self._post)

    # --- respostas ---------------------------------------------------------------------

    def _cabecalhos(self, codigo: int, tipo: str, tamanho: int) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(tamanho))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()

    def _json(self, codigo: int, corpo: dict[str, Any]) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self._cabecalhos(codigo, "application/json; charset=utf-8", len(dados))
        self.wfile.write(dados)

    def _erro(self, codigo: int, mensagem: str, classe: Optional[str] = None) -> None:
        self._classe = classe or self._classe
        self._json(codigo, {"ok": False, "erro": mensagem, "classe": classe})

    # --- guardas -----------------------------------------------------------------------

    def _host(self) -> str:
        return (self.headers.get("Host") or "").lower()

    def _em_tls(self) -> bool:
        return isinstance(self.connection, ssl.SSLSocket)

    def _para_https(self) -> bool:
        """Pedido HTTP da rede quando o painel tem HTTPS: vai para o mesmo caminho em https (308 mantém o método)."""
        if self.server.tls is None or self._em_tls() or self._local() or not self._host_ok():
            return False
        self.send_response(308)
        self.send_header("Location", "https://%s%s" % (self._host(), self.path))
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def _host_ok(self) -> bool:
        return self._host() in self.server.hosts

    def _local(self) -> bool:
        """Pedido do próprio Mac: cliente em loopback e Host local. Qualquer outro caminho passa pelo pareamento."""
        return self.client_address[0] in LOOPBACK and self._host() in self.server.hosts_locais

    def _cookie(self) -> Optional[str]:
        try:
            biscoito = SimpleCookie(self.headers.get("Cookie") or "")
        except CookieError:
            return None
        return biscoito[COOKIE].value if COOKIE in biscoito else None

    def _autorizado(self) -> bool:
        return self._local() or (self.server.rede and self.server.aparelhos.valido(self._cookie()))

    def _token_ok(self) -> bool:
        return hmac.compare_digest(self.headers.get("X-GP-Token") or "", self.server.token)

    def _origem_ok(self) -> bool:
        origem = self.headers.get("Origin")
        return origem is None or origem in self.server.origens

    # --- GET ---------------------------------------------------------------------------

    def _pagina(self, nome: str, trocas: dict[str, str]) -> None:
        html = (PASTA_WEB / nome).read_text(encoding="utf-8")
        for chave, valor in trocas.items():
            html = html.replace("{{%s}}" % chave, valor)
        dados = html.encode("utf-8")
        self._cabecalhos(200, "text/html; charset=utf-8", len(dados))
        self.wfile.write(dados)

    def _get(self) -> None:
        if not self._host_ok():
            return self._erro(403, "host recusado")
        partes = urlsplit(self.path)
        rota = partes.path
        if rota in ESTATICOS:
            return self._estatico(*ESTATICOS[rota])
        livres = {"/": self._raiz, "/api/pareamento": self._pareamento, "/manifest.webmanifest": self._manifesto}
        if rota in livres:
            return livres[rota]()
        if rota in LEITURAS_LOCAIS:
            return self._leitura_local(rota)
        if rota not in ("/api/painel", "/api/meta", "/api/periodo") and rota not in TELAS_GET:
            return self._erro(404, "não encontrado")
        if not self._autorizado() or not self._token_ok():
            return self._erro(403, "token ausente ou inválido")
        # antes do onboarding as telas abrem vazias (uma pasta só com o contexto mínimo), nunca com dados de exemplo
        vazio = not acoes_locais.configurado(self.server.dados)
        try:
            return self._tela(
                rota, parse_qs(partes.query), acoes_locais.pasta_vazia() if vazio else self.server.dados, vazio
            )
        except ConsultaInvalida as erro:
            return self._erro(400, str(erro))
        except GpErro as erro:
            return self._falha(erro)

    def _leitura_local(self, rota: str) -> None:
        if not (self._local() and self._token_ok()):
            return self._erro(403, "só no computador")
        if rota == "/api/comecar":
            modelo = acoes_locais.modelo(self.server.dados, clock.agora(), self.server.deteccao)
        else:
            modelo = acoes_locais.estado_da_atualizacao()
        return self._json(
            200, {"ok": True, "modelo": modelo, "endereco": self.server.endereco, "demo": self.server.demo}
        )

    def _estatico(self, nome: str, tipo: str) -> None:
        dados = (PASTA_WEB / nome).read_bytes()
        self._cabecalhos(200, tipo, len(dados))
        self.wfile.write(dados)

    def _raiz(self) -> None:
        if not self._autorizado():
            textos = {chave: escape(valor) for chave, valor in painel.textos().items()}
            return self._pagina(
                "parear.html", dict({"T:" + chave: valor for chave, valor in textos.items()}, IDIOMA=copy.atual())
            )
        return self._pagina("index.html", {"TOKEN": self.server.token, "IDIOMA": copy.atual()})

    def _pareamento(self) -> None:
        if not (self._local() and self._token_ok()):
            return self._erro(403, "só no Mac")
        return self._json(
            200,
            {
                "ok": True,
                "rede": self.server.rede,
                "endereco_rede": self.server.endereco_rede,
                "codigo": self.server.codigo,
                "impressao": self.server.tls.impressao if self.server.tls else None,
                "aparelhos": self.server.aparelhos.quantos() if self.server.rede else 0,
            },
        )

    def _manifesto(self) -> None:
        manifesto = json.loads((PASTA_WEB / "manifest.webmanifest").read_text(encoding="utf-8"))
        manifesto["lang"] = copy.atual()  # o idioma do ícone na tela inicial é o da instalação
        dados = json.dumps(manifesto, ensure_ascii=False, indent=2).encode("utf-8")
        self._cabecalhos(200, "application/manifest+json; charset=utf-8", len(dados))
        self.wfile.write(dados)

    def _tela(self, rota: str, consulta: dict[str, list[str]], dados: Path, vazio: bool) -> None:
        """Modelo de uma tela autorizada; ConsultaInvalida = consulta malformada (400), GpErro = falha da pasta de dados."""
        agora = clock.agora()
        if rota == "/api/painel":
            valor = consulta.get("data", [None])[0]
            try:
                dia = date.fromisoformat(valor) if valor else None
            except ValueError:
                raise ConsultaInvalida("data inválida: use AAAA-MM-DD") from None
            modelo = painel.modelo(dados, agora, dia)
        elif rota == "/api/meta":
            modelo = painel.modelo_meta(dados, agora, consulta.get("id", [""])[0])
        elif rota == "/api/periodo":
            modelo = painel.modelo_periodo(
                dados, agora, consulta.get("nivel", ["ano"])[0], consulta.get("id", [None])[0]
            )
        else:
            modelo = TELAS_GET[rota](dados, agora)
        if rota == "/api/status":
            modelo.update(
                {
                    "rede": self.server.rede,
                    "local": self._local(),
                    "versao": base.VERSAO_APP,
                    "janela": acoes_locais.janela_instalada(),
                    "plataforma": plataforma.nome_atual(),
                    "versao_nova": acoes_locais.versao_nova() if self._local() else None,
                    "aparelhos": self.server.aparelhos.quantos() if self.server.rede else 0,
                }
            )
        return self._json(
            200,
            {"ok": True, "modelo": modelo, "endereco": self.server.endereco, "demo": self.server.demo, "vazio": vazio},
        )

    # --- POST --------------------------------------------------------------------------

    def _corpo(self) -> Optional[dict[str, Any]]:
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            self._erro(415, "use application/json")
            return None
        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            tamanho = -1
        if tamanho < 0 or tamanho > TETO_CORPO:
            self._erro(413, "corpo grande demais")
            return None
        try:
            corpo = json.loads(self.rfile.read(tamanho).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            self._erro(400, "JSON inválido")
            return None
        if not isinstance(corpo, dict):
            self._erro(400, "esperado objeto JSON")
            return None
        return corpo

    def _falha(self, erro: GpErro) -> None:
        classe = execucao.classe_de(erro)
        if erro.codigo == EXIT_IO and "lock" in erro.mensagem:
            return self._erro(409, copy.texto("painel.job_em_andamento"), "LockTimeout")
        codigo = {EXIT_ESTADO: 409, EXIT_VALIDACAO: 400}.get(erro.codigo, 500)
        mensagem = erro.mensagem if codigo == 400 else "%s: %s" % (execucao.motivo(classe), execucao.acao(classe))
        return self._erro(codigo, mensagem, classe)

    def _parear(self) -> None:
        if not self.server.rede or self._local():
            return self._erro(404, "não encontrado")
        corpo = self._corpo()
        if corpo is None:
            return None
        codigo = str(corpo.get("codigo") or "").strip()
        with self.server.trava_pareamento:  # contagem e checagem juntas: rajada em paralelo não passa do teto
            if self.server.erros_pareamento >= TETO_ERROS_PAREAMENTO:
                return self._erro(429, copy.texto("painel.parear_bloqueado"))
            certo = len(codigo) == 6 and hmac.compare_digest(codigo, self.server.codigo or "")
            if not certo:
                self.server.erros_pareamento += 1
                bloqueou = self.server.erros_pareamento >= TETO_ERROS_PAREAMENTO
        if not certo:
            time.sleep(ESPERA_ERRO_S)
            if bloqueou:
                return self._erro(429, copy.texto("painel.parear_bloqueado"))
            return self._erro(403, copy.texto("painel.parear_errado"))
        token = self.server.aparelhos.novo((self.headers.get("User-Agent") or "aparelho")[:60])
        dados = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Set-Cookie",
            "%s=%s; Max-Age=%d; Path=/; HttpOnly; SameSite=Strict%s"
            % (COOKIE, token, DIAS_APARELHO * 86400, "; Secure" if self._em_tls() else ""),
        )
        self.end_headers()
        self.wfile.write(dados)
        return None

    def _erro_front(self) -> None:
        """Erro de JavaScript da tela: só forma e local, com teto por minuto; nada da tela nem do usuário."""
        corpo = self._corpo()
        if corpo is None:
            return None
        agora = time.monotonic()
        with self.server.trava_front:
            self.server.erros_front = [t for t in self.server.erros_front if agora - t < 60] + [agora]
            demais = len(self.server.erros_front) > TETO_ERROS_FRONT_MIN
        if demais:
            return self._erro(429, "muitos erros por minuto")
        tela = str(corpo.get("tela") or "")
        linha, coluna = corpo.get("linha"), corpo.get("coluna")
        telemetria.evento(
            "erro_front",
            mensagem=str(corpo.get("mensagem") or "")[:300],
            arquivo=str(corpo.get("arquivo") or "")[:120],
            linha=linha if isinstance(linha, int) and not isinstance(linha, bool) else 0,
            coluna=coluna if isinstance(coluna, int) and not isinstance(coluna, bool) else 0,
            tela=tela if re.match(r"^[a-z]{1,12}\Z", tela) else "outra",
        )
        return self._json(200, {"ok": True})

    def _post(self) -> None:
        if not self._host_ok() or not self._origem_ok():
            return self._erro(403, "origem recusada")
        rota = urlsplit(self.path).path
        if rota == "/api/parear":
            return self._parear()
        if not self._autorizado() or not self._token_ok():
            return self._erro(403, "token ausente ou inválido")
        if rota == "/api/erro-front":
            return self._erro_front()
        if rota == "/api/esquecer-aparelhos":
            if not self._local():
                return self._erro(403, "só no Mac")
            self.server.aparelhos.esquecer()
            return self._json(200, {"ok": True, "mensagem": copy.texto("painel.rede_esquecidos")})
        if rota in ACOES_LOCAIS:
            return self._acao_local(rota)
        if rota not in ROTAS_ESCRITA:
            return self._erro(404, "não encontrado")
        corpo = self._corpo()
        if corpo is None:
            return None
        dados = self.server.dados
        agora = clock.agora()
        try:
            pedido = PEDIDOS[rota](rota, corpo)
        except ValueError as erro:
            return self._erro(400, str(erro))
        try:
            trava = reg.lock(dados)
            try:
                mensagem = pedido(dados, agora)
            finally:
                trava.liberar()
            resposta: dict[str, Any] = {"ok": True, "mensagem": mensagem, "endereco": self.server.endereco}
            if rota in ("/api/confirmar", "/api/decisao"):
                resposta["modelo"] = painel.modelo(dados, agora, None)
        except GpErro as erro:
            return self._falha(erro)
        return self._json(200, resposta)

    def _acao_local(self, rota: str) -> None:
        """Ações que só valem no próprio computador (acoes_locais.py); nunca no painel de exemplo."""
        if not self._local():
            return self._erro(403, "só no computador")
        if self.server.demo:
            return self._erro(409, copy.texto("painel.acao_no_exemplo"))
        corpo = self._corpo()
        if corpo is None:
            return None
        try:
            resposta = ACOES_LOCAIS[rota](self.server, corpo)
        except onboarding.RespostaInvalida as erro:
            return self._json(400, {"ok": False, "erro": copy.texto("painel.comecar_corrigir"), "erros": erro.erros})
        except ValueError as erro:
            return self._erro(400, str(erro))
        except GpErro as erro:
            if erro.codigo == EXIT_IO and "lock" in erro.mensagem:
                return self._erro(409, copy.texto("painel.job_em_andamento"), "LockTimeout")
            return self._erro({EXIT_ESTADO: 409, EXIT_VALIDACAO: 400}.get(erro.codigo, 500), erro.mensagem)
        return self._json(200, dict(resposta, ok=True))


# --- ações só do computador: primeiros passos, doctor e atualizar (acoes_locais.py) ---------------------------------


def _sob_lock(servidor: Painel, gravar: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    trava = reg.lock(servidor.dados)
    try:
        return gravar()
    finally:
        trava.liberar()


def _acao_detectar(servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    servidor.deteccao = acoes_locais.detectar(offline=servidor.offline)
    return {"deteccao": servidor.deteccao}


def _acao_rascunho(servidor: Painel, corpo: dict[str, Any]) -> dict[str, Any]:
    return {"rascunho": _sob_lock(servidor, lambda: acoes_locais.salvar_rascunho(corpo.get("respostas")))}


def _acao_gravar(servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    saida = _sob_lock(servidor, lambda: acoes_locais.gravar(servidor.dados, clock.agora()))
    return {"mensagem": copy.texto("painel.comecar_gravado"), "avisos": saida["avisos"]}


def _acao_primeiro_dia(_servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    return {"mensagem": acoes_locais.primeiro_dia()}


def _acao_conta(servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    return {"conta": acoes_locais.estado_da_conta(offline=servidor.offline)}


def _acao_instalar_claude(_servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    return {"mensagem": acoes_locais.instalar_claude()}


def _acao_login_claude(servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    return {"url": acoes_locais.iniciar_login(servidor)}


def _acao_login_codigo(servidor: Painel, corpo: dict[str, Any]) -> dict[str, Any]:
    return {"mensagem": acoes_locais.enviar_codigo(servidor, corpo.get("codigo"))}


def _acao_doctor(servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    resultado = acoes_locais.doctor(offline=servidor.offline)
    return {"tudo_certo": resultado["ok"], "itens": resultado["itens"]}


def _acao_desinstalar(_servidor: Painel, corpo: dict[str, Any]) -> dict[str, Any]:
    if corpo.get("confirmar") is not True:
        raise ValueError("confirmar: esperado true")
    return {"mensagem": acoes_locais.iniciar_desinstalacao()}


def _acao_atualizar(_servidor: Painel, _corpo: dict[str, Any]) -> dict[str, Any]:
    return {"mensagem": acoes_locais.iniciar_atualizacao()}


ACOES_LOCAIS: dict[str, Callable[[Painel, dict[str, Any]], dict[str, Any]]] = {
    "/api/comecar/detectar": _acao_detectar,
    "/api/comecar/rascunho": _acao_rascunho,
    "/api/comecar/gravar": _acao_gravar,
    "/api/comecar/primeiro-dia": _acao_primeiro_dia,
    "/api/comecar/conta": _acao_conta,
    "/api/comecar/instalar-claude": _acao_instalar_claude,
    "/api/comecar/login-claude": _acao_login_claude,
    "/api/comecar/login-codigo": _acao_login_codigo,
    "/api/doctor": _acao_doctor,
    "/api/atualizar": _acao_atualizar,
    "/api/desinstalar": _acao_desinstalar,
}
LEITURAS_LOCAIS = ("/api/comecar", "/api/atualizacao")


# --- escrita: validação da forma aqui, das regras nas funções da skill ------------------------------------------------

Pedido = Callable[[Path, datetime], str]  # roda sob o lock da pasta de dados e devolve a mensagem da tela


def _meta_do_corpo(corpo: dict[str, Any]) -> str:
    meta = corpo.get("meta")
    if not isinstance(meta, str) or not schema.validar_id("meta", meta):
        raise ValueError("meta inválida")
    return meta


def _tasks(valor: Any, campo: str) -> list[str]:
    if valor is None:
        return []
    if (
        not isinstance(valor, list)
        or len(valor) > 60
        or not all(isinstance(v, str) and schema.validar_id("task", v) for v in valor)
    ):
        raise ValueError("%s inválido: lista de ids de bloco" % campo)
    return valor


def _pelo_checkin(respostas: dict[str, Any], mensagem: str) -> Pedido:
    def gravar(dados: Path, agora: datetime) -> str:
        checkin.confirmar(dados, respostas, agora=agora)
        return mensagem

    return gravar


def _pedido_bloco(rota: str, corpo: dict[str, Any]) -> Pedido:
    task_id = corpo.get("task_id")
    if not isinstance(task_id, str) or not schema.validar_id("task", task_id):
        raise ValueError("task_id inválido")
    if rota == "/api/confirmar":
        return _pelo_checkin({"feitas": [{"task_id": task_id}]}, copy.texto("painel.confirmada"))
    return _pelo_checkin({"nao_feitas": [task_id]}, copy.texto("painel.nao_feita_ok"))


def _pedido_decisao(_rota: str, corpo: dict[str, Any]) -> Pedido:
    meta, saida = _meta_do_corpo(corpo), corpo.get("saida")
    if saida not in gpmetas.SAIDAS:
        raise ValueError("decisão inválida")
    decisao: dict[str, Any] = {"saida": saida}
    if saida == "reduzir":
        decisao["custo"] = corpo.get("custo")
    if saida in ("adiar", "renegociar"):
        decisao["prazo"] = corpo.get("prazo")
    chave = "painel.decisao_mantida" if saida == "manter" else "painel.decisao_aplicada"
    return _pelo_checkin({"decisoes": {meta: decisao}}, copy.texto(chave, meta=render.rotulo_meta(meta)))


def _pedido_sentimento(_rota: str, corpo: dict[str, Any]) -> Pedido:
    meta, valor = _meta_do_corpo(corpo), corpo.get("valor")
    if valor not in schema.SENTIMENTOS:
        raise ValueError("sentimento inválido")
    return _pelo_checkin(
        {"sentimentos": {meta: valor}}, copy.texto("painel.sentimento_ok", meta=render.rotulo_meta(meta))
    )


def _sentimentos(valor: Any) -> dict[str, str]:
    sentimentos = valor or {}
    if not isinstance(sentimentos, dict) or not all(
        isinstance(k, str) and schema.validar_id("meta", k) and v in schema.SENTIMENTOS for k, v in sentimentos.items()
    ):
        raise ValueError("sentimentos inválidos")
    return sentimentos


def _pedido_checkin(_rota: str, corpo: dict[str, Any]) -> Pedido:
    feitas, nao_feitas = _tasks(corpo.get("feitas"), "feitas"), _tasks(corpo.get("nao_feitas"), "nao_feitas")
    sentimentos = _sentimentos(corpo.get("sentimentos"))
    nota = corpo.get("nota") or ""
    if not isinstance(nota, str) or len(nota) > TETO_NOTA:
        raise ValueError("nota inválida (até %d caracteres)" % TETO_NOTA)
    respostas: dict[str, Any] = {
        "feitas": [{"task_id": x} for x in feitas],
        "nao_feitas": nao_feitas,
        "sentimentos": sentimentos,
    }
    if nota.strip():
        respostas["nota"] = {"texto": nota, "aceita": True}
    if not (feitas or nao_feitas or sentimentos or nota.strip()):
        raise ValueError(copy.texto("painel.checkin_vazio"))
    return _pelo_checkin(respostas, copy.texto("painel.checkin_ok"))


def _pedido_marco(_rota: str, corpo: dict[str, Any]) -> Pedido:
    meta, indice, feito = _meta_do_corpo(corpo), corpo.get("indice"), corpo.get("feito")
    if not isinstance(indice, int) or isinstance(indice, bool) or indice < 0 or not isinstance(feito, bool):
        raise ValueError("marco inválido")

    def marcar(dados: Path, _agora: datetime) -> str:
        gpmetas.marcar_marco(dados, meta, indice, feito)
        return copy.texto("painel.marco_feito" if feito else "painel.marco_aberto")

    return marcar


def _ajuste_custo(valor: Any) -> tuple[str, Any]:
    if not isinstance(valor, (int, float)) or isinstance(valor, bool) or not 0 < valor <= TETO_CUSTO_H:
        raise ValueError("horas por semana inválidas (entre 0 e %d)" % TETO_CUSTO_H)
    return "custo_h_semana_escolhido", float(valor)


def _ajuste_prazo(valor: Any) -> tuple[str, Any]:
    try:
        return "prazo", date.fromisoformat(str(valor))
    except ValueError:
        raise ValueError("prazo inválido: use AAAA-MM-DD") from None


def _ajuste_impacto(valor: Any) -> tuple[str, Any]:
    if valor not in schema.IMPACTOS:
        raise ValueError("impacto inválido")
    return "impacto", valor


def _ajuste_objetivo(valor: Any) -> tuple[str, Any]:
    if not isinstance(valor, str) or (valor and not schema.RE_OBJETIVO.match(valor)):
        raise ValueError("objetivo inválido")
    return "objetivo", valor


def _ajuste_estado(valor: Any) -> tuple[str, Any]:
    if valor not in ESTADOS_AJUSTE:
        raise ValueError("estado inválido")
    return "estado", valor


# campo do corpo -> validação que devolve (campo da meta, valor); a ordem é a das mensagens de erro
AJUSTES: tuple[tuple[str, Callable[[Any], tuple[str, Any]]], ...] = (
    ("custo", _ajuste_custo),
    ("prazo", _ajuste_prazo),
    ("impacto", _ajuste_impacto),
    ("objetivo", _ajuste_objetivo),
    ("estado", _ajuste_estado),
)


def _pedido_ajuste(_rota: str, corpo: dict[str, Any]) -> Pedido:
    meta = _meta_do_corpo(corpo)
    mudancas = dict(validar(corpo[campo]) for campo, validar in AJUSTES if campo in corpo)
    if not mudancas:
        raise ValueError("nada para ajustar")

    def ajustar(dados: Path, _agora: datetime) -> str:
        objetivo = mudancas.get("objetivo")
        if objetivo and not (dados / schema.CAMINHOS["objetivo"].replace("O<nn>", objetivo)).exists():
            raise GpErro(EXIT_VALIDACAO, "objetivo %s não existe" % objetivo)
        feito = gpmetas.ajustar(dados, meta, mudancas)
        return copy.texto("painel.ajuste_ok" if feito else "painel.ajuste_igual", meta=render.rotulo_meta(meta))

    return ajustar


def _pedido_fonte(_rota: str, corpo: dict[str, Any]) -> Pedido:
    fonte, ativa = corpo.get("fonte"), corpo.get("ativa")
    if fonte not in schema.FONTES or not isinstance(ativa, bool):
        raise ValueError("fonte inválida")

    def ajustar(dados: Path, _agora: datetime) -> str:
        mudou = conexoes.ajustar_fonte(dados, fonte, ativa)
        chave = "painel.fonte_igual" if not mudou else "painel.fonte_entra" if ativa else "painel.fonte_sai"
        return copy.texto(chave, fonte=copy.texto("painel.conexao_" + fonte))

    return ajustar


# Uma rota de gravação por função; ValueError = pedido malformado (400). As chaves são ROTAS_ESCRITA.
PEDIDOS: dict[str, Callable[[str, dict[str, Any]], Pedido]] = {
    "/api/confirmar": _pedido_bloco,
    "/api/nao-feita": _pedido_bloco,
    "/api/decisao": _pedido_decisao,
    "/api/checkin": _pedido_checkin,
    "/api/sentimento": _pedido_sentimento,
    "/api/meta/ajustar": _pedido_ajuste,
    "/api/meta/marco": _pedido_marco,
    "/api/fonte": _pedido_fonte,
}
ROTAS_ESCRITA = tuple(PEDIDOS)
# rotas que o registro local do painel guarda pelo nome (as outras viram "outra": nada de caminho arbitrário no log)
ROTAS_CONHECIDAS = frozenset(
    [
        "/",
        "/manifest.webmanifest",
        "/api/painel",
        "/api/meta",
        "/api/periodo",
        "/api/pareamento",
        "/api/parear",
        "/api/esquecer-aparelhos",
        "/api/erro-front",
        *LEITURAS_LOCAIS,
        *ACOES_LOCAIS,
        *TELAS_GET,
        *ROTAS_ESCRITA,
        *ESTATICOS,
    ]
)


def servir(porta: int, dados: Path, *, rede: bool = False, https: bool = True) -> Painel:
    return Painel(porta, dados, rede=rede, https=https)


def preparar_demo(destino: Path) -> Path:
    """Pasta de dados de exemplo em ``destino`` (``demo_painel.preparar``: offline, sintética, relógio fixo)."""
    import demo_painel

    if not demo_painel.FIXTURE.is_dir():
        raise GpErro(EXIT_ESTADO, "fixtures de exemplo ausentes em %s" % demo_painel.FIXTURE)
    return demo_painel.preparar(destino)


def main(argv: Optional[list[str]] = None) -> int:
    parser = cli.parser_base("painel no navegador, só neste Mac")
    parser.add_argument("--porta", type=int, default=PORTA_PADRAO)
    parser.add_argument("--abrir", action="store_true", help="abre o painel no navegador padrão")
    parser.add_argument(
        "--demo", action="store_true", help="painel com o dia de exemplo das fixtures, numa pasta temporária"
    )
    alcance = parser.add_mutually_exclusive_group()
    alcance.add_argument(
        "--rede", action="store_true", help="aceita o celular no mesmo Wi-Fi, com código de pareamento"
    )
    alcance.add_argument(
        "--local", action="store_true", help="só neste computador (o padrão; é a forma do agente do login)"
    )
    parser.add_argument(
        "--sem-https", dest="sem_https", action="store_true", help="na rede, fica em HTTP mesmo com openssl"
    )
    parser.add_argument(
        "--manter-acordado", dest="acordado", action="store_true", help="impede o sono do Mac enquanto o painel roda"
    )
    parser.add_argument(
        "--esquecer-aparelhos", dest="esquecer", action="store_true", help="revoga todos os aparelhos pareados e sai"
    )
    args = parser.parse_args(argv)
    temporaria: list[str] = []  # a pasta do demo, quando houver: some em qualquer saída
    try:
        cli.aplicar_args_base(args)
        if args.esquecer:
            Aparelhos(base.jobs_dir() / NOME_APARELHOS).esquecer()
            print(copy.texto("painel.rede_esquecidos"))
            return EXIT_OK
        dados = _pasta_do_painel(args, temporaria)
        copy.seguir_pasta(dados)  # o idioma das telas é o do contexto servido (o demo inclusive)
        servidor = servir(args.porta, dados, rede=args.rede, https=not args.sem_https)
        servidor.demo = bool(args.demo)
        servidor.offline = bool(args.offline)
    except OSError as erro:
        _apagar(temporaria)
        print("erro: porta %d indisponível (%s); use --porta" % (args.porta, erro), file=sys.stderr)
        return EXIT_IO
    except GpErro as erro:
        _apagar(temporaria)
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    _anunciar(servidor)
    _servir_ate_fechar(servidor, args, temporaria)
    return EXIT_OK


def _pasta_do_painel(args: argparse.Namespace, temporaria: list[str]) -> Path:
    """A pasta de dados servida: a da instalação ou, com ``--demo``, um exemplo sintético numa pasta temporária."""
    if not args.demo:
        return base.data_dir()
    temporaria.append(tempfile.mkdtemp(prefix="gp-demo-"))
    os.environ.setdefault(telemetria.ENV_LOGS, str(Path(temporaria[0]) / "logs"))  # o registro do demo some com ele
    dados = preparar_demo(Path(temporaria[0]))
    import demo_painel

    os.environ.update(demo_painel.ambiente(Path(temporaria[0])))  # processo dedicado ao demo: relógio e pasta dele
    return dados


def _apagar(temporaria: list[str]) -> None:
    for pasta in temporaria:
        shutil.rmtree(pasta, ignore_errors=True)


def _anunciar(servidor: Painel) -> None:
    print(copy.texto("painel.rodape", endereco=servidor.endereco))
    if servidor.rede:
        if servidor.endereco_rede:
            print(copy.texto("painel.rede_terminal", endereco=servidor.endereco_rede, codigo=servidor.codigo))
        else:
            print(copy.texto("painel.rede_sem_endereco"))
        if servidor.tls:
            print(copy.texto("painel.rede_impressao", impressao=servidor.tls.impressao))
        else:
            print(copy.texto("painel.rede_aviso"))
    print("Ctrl+C para fechar.")
    sys.stdout.flush()


def _servir_ate_fechar(servidor: Painel, args: argparse.Namespace, temporaria: list[str]) -> None:
    sistema = plataforma.atual()
    if args.acordado:
        sistema.manter_acordado(os.getpid())
    if args.abrir:
        threading.Timer(0.3, lambda: sistema.abrir_url(servidor.endereco)).start()

    def encerrar(_sinal: int, _quadro: Any) -> None:
        # SIGTERM (launchctl, kill) e Ctrl+C fecham do mesmo jeito e apagam a pasta do demo. Nada de exceção lançada
        # do handler: ela cairia no meio de um accept ou do start da thread de um pedido e o processo não saía. O
        # shutdown roda noutra thread e o serve_forever termina na volta seguinte do laço.
        threading.Thread(target=servidor.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, encerrar)
    signal.signal(signal.SIGINT, encerrar)
    try:
        servidor.serve_forever()
    finally:
        servidor.server_close()
        _apagar(temporaria)


if __name__ == "__main__":
    raise SystemExit(main())
