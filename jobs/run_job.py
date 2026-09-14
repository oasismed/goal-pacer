#!/usr/bin/env python3
"""run_job.py diario|mensal: o job agendado (launchd no macOS, systemd --user no Linux) (T8; eng 2.3, 3.1; CEO 2.1, 3.3, 4.2, 8.1; D4.4).

Fluxo::

    lock da pasta de dados (espera até 45 min; preso -> LockTimeout, exit 4, notificação)
      |
      +-- diario: balanco.py --precisa-mensal
      |             exit 2 -> mensal.py (teto do job passa a 40 min)       falha: aviso, segue
      |             segunda-feira sem mensal -> semanal.py                 falha: aviso, segue
      |           diario.py --email                                        (teto 20 min)
      |             falhou -> diario.py --email-falha <classe> -> falhou -> notificação
      |             email do dia falhou -> diario.py --reenviar-email até 3 vezes, com GP_RETRY_EMAIL_S
      |                                    entre elas e dentro do teto -> ainda falhou -> notificação
      +-- mensal: mensal.py
      |
    cada passo: subprocesso com GP_LOCK_HERDADO=1 e GP_RUN_ID=<run_id>-<passo>, timeout = o que
    resta do teto (killpg no estouro -> SessionTimeout, exit 5); classe lida do JSON de erro do passo;
    RateLimited -> uma nova tentativa depois de GP_RETRY_SLEEP (30 min), nunca uma terceira
      |
    registro.geracoes[<run_id>] (modo job:<modo>, classe, exit, duração, tokens e sessões dos passos)
    -> anos anteriores com mais de 120 dias vão para registro-AAAA.json (registro.arquivar)
    -> retenção: cache (calendar/ops/email) e logs com mais de 7 dias; transcripts e tool-results
       das sessões deste job em ~/.claude/projects/<cwd>/ -> liberar o lock -> exit

Sem ``--agora``: o relógio é o real (os testes fixam por ``GP_AGORA``).
Variáveis para teste: ``GP_SCRIPTS_DIR``, ``GP_TIMEOUT_JOB_S``, ``GP_LOCK_ESPERA_S``,
``GP_RETRY_SLEEP``, ``GP_RETRY_EMAIL_S``, ``GP_GRACA_EMAIL_S``, ``GP_PLATAFORMA`` e os stubs de notificação (``GP_OSASCRIPT``, ``GP_NOTIFY_SEND``).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple, Optional

APP = Path(__file__).resolve().parent.parent
# Variáveis do job (os testes encurtam as esperas e trocam a pasta dos scripts)
ENV_SCRIPTS_DIR = "GP_SCRIPTS_DIR"
ENV_TIMEOUT_JOB_S = "GP_TIMEOUT_JOB_S"
ENV_RETRY_SLEEP = "GP_RETRY_SLEEP"
ENV_RETRY_EMAIL_S = "GP_RETRY_EMAIL_S"
ENV_GRACA_EMAIL_S = "GP_GRACA_EMAIL_S"
ENV_LOCK_ESPERA_S = "GP_LOCK_ESPERA_S"
sys.path.insert(0, str(APP / "scripts"))

from goalpacer import (  # noqa: E402
    base,
    clock,
    copy,
    execucao,
    io as gpio,
    plataforma,
    processos,
    proxy,
    registro as reg,
    saude,
    telemetria,
)
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_TIMEOUT, GpErro  # noqa: E402

TETO_DIARIO_S = 20 * 60
TETO_COM_MENSAL_S = 40 * 60
ESPERA_LOCK_S = 45 * 60
RETRY_SLEEP_S = 30 * 60
RETENCAO_DIAS = 7
TENTATIVAS_EMAIL = 3
ESPERA_EMAIL_S = 2 * 60
GRACA_EMAIL_FALHA_S = 4 * 60  # o email mínimo de falha ganha tempo próprio mesmo depois de um estouro do teto
PADROES_CACHE = ("calendar-*.json", "ops-*.json", "email-*.json", "auditoria-*.jsonl", "*.json.bak")
PADROES_LOGS = ("run-*.log", "prompt-*.md", "result-*.jsonl", "launchd-*.log", "eventos-*.jsonl", "trace-*.jsonl")
ESTADOS_SEM_FALHA = ("SemOnboarding", "SemMetaAtiva")


class Passo(NamedTuple):
    nome: str
    codigo: int
    classe: Optional[str]
    saida: dict[str, Any]
    duracao_s: float
    texto: str = ""


def _env_float(nome: str, padrao: float) -> float:
    try:
        return float(os.environ.get(nome, padrao))
    except ValueError:
        return padrao


def pasta_scripts() -> Path:
    return Path(os.environ.get(ENV_SCRIPTS_DIR) or APP / "scripts")


class Job:
    def __init__(self, modo: str, *, offline: bool, agora: datetime) -> None:
        self.modo = modo
        self.offline = offline
        self.inicio = time.monotonic()
        self.agora = agora
        self.run_id = "job-%s-%s" % (modo, agora.strftime("%Y%m%d-%H%M%S"))
        self.dados = base.data_dir()
        self.logs = base.jobs_dir() / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.log_path = self.logs / ("run-%s.log" % self.run_id)
        self.teto_s = _env_float(ENV_TIMEOUT_JOB_S, TETO_DIARIO_S)
        self.espera_lock_s = 0.0
        # os passos (subprocessos) gravam os spans no trace deste job, pendurados no span do passo
        os.environ[telemetria.ENV_TRACE_ID] = self.run_id
        self.span_id = telemetria.novo_span_id()
        os.environ[telemetria.ENV_TRACE_PAI] = self.span_id
        self.passos: list[Passo] = []
        self.avisos: list[str] = []

    # --- log e notificação -----------------------------------------------------------

    def log(self, mensagem: str) -> None:
        linha = "%s [%s] %s\n" % (
            clock.agora().isoformat(timespec="seconds"),
            self.run_id,
            " ".join(str(mensagem).split()),
        )
        with open(self.log_path, "a", encoding="utf-8") as arquivo:
            arquivo.write(linha)

    def notificar(self, mensagem: str) -> None:
        problema = plataforma.atual().notificar(mensagem)
        if problema:
            self.log("notificação não saiu (%s): %s" % (problema, mensagem))

    # --- passos -----------------------------------------------------------------------

    def restante_s(self) -> float:
        return self.teto_s - (time.monotonic() - self.inicio)

    def rodar(self, script: str, *args: str, sufixo: Optional[str] = None, estado_e_resposta: bool = False) -> Passo:
        nome = Path(script).stem
        tentativa = 0
        while True:
            tentativa += 1
            passo = self._rodar_uma(script, args, sufixo or nome, estado_e_resposta)
            if passo.classe is None or not execucao.info(passo.classe).retentar or tentativa > 1:
                return passo
            espera = _env_float(ENV_RETRY_SLEEP, RETRY_SLEEP_S)
            self.log("%s: %s; nova tentativa em %.0f s" % (nome, passo.classe, espera))
            self.teto_s += espera  # a espera pela janela da assinatura não conta no teto do job
            time.sleep(espera)

    def _rodar_uma(self, script: str, args: tuple, rotulo: str, estado_e_resposta: bool = False) -> Passo:
        restante = self.restante_s()
        if restante <= 0:
            passo = Passo(rotulo, EXIT_TIMEOUT, "SessionTimeout", {}, 0.0)
            self.passos.append(passo)
            return passo
        argv = (
            [sys.executable, str(pasta_scripts() / script), "--json"]
            + (["--offline"] if self.offline else [])
            + list(args)
        )
        span_passo = telemetria.novo_span_id()
        self.log("passo %s: %s" % (rotulo, " ".join(argv[1:])))
        comeco = time.monotonic()
        # pragma: no mutate start (sem start_new_session o killpg de um mutante acertaria o mutmut)
        processo = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(base.jobs_dir()),
            env=self._ambiente_do_passo(rotulo, span_passo),
            **processos.isolamento(),
            text=True,
            encoding="utf-8",
        )
        # pragma: no mutate end
        try:
            stdout, stderr = processo.communicate(timeout=restante)
        except subprocess.TimeoutExpired:
            _matar_grupo(processo)
            processo.communicate()
            passo = Passo(rotulo, EXIT_TIMEOUT, "SessionTimeout", {}, time.monotonic() - comeco)
            self.log("passo %s: SessionTimeout depois de %.0f s" % (rotulo, passo.duracao_s))
            return self._fechar_passo(passo, span_passo)
        for linha in (stderr or "").strip().split("\n"):
            if linha.strip():
                self.log("%s stderr: %s" % (rotulo, linha[:500]))
        saida = _json_final(stdout)
        classe = _classe_do_passo(processo.returncode, saida, stdout, estado_e_resposta)
        passo = Passo(
            rotulo, processo.returncode, classe, saida, time.monotonic() - comeco, (stdout or "").strip()[:2000]
        )
        self.log(
            "passo %s: exit %d%s em %.1f s"
            % (rotulo, passo.codigo, " (%s)" % classe if classe else "", passo.duracao_s)
        )
        return self._fechar_passo(passo, span_passo)

    def _ambiente_do_passo(self, rotulo: str, span_passo: str) -> dict[str, str]:
        """O passo herda o lock e grava no trace deste job, pendurado no próprio span."""
        env = dict(os.environ)
        env.update(
            {
                reg.ENV_LOCK_HERDADO: "1",
                base.ENV_RUN_ID: "%s-%s" % (self.run_id, rotulo),
                base.ENV_DATA_DIR: str(self.dados),
                telemetria.ENV_TRACE_ID: self.run_id,
                telemetria.ENV_TRACE_PAI: span_passo,
            }
        )
        return env

    def _fechar_passo(self, passo: Passo, span_passo: str) -> Passo:
        telemetria.registrar_span(
            "passo",
            passo.duracao_s * 1000,
            span_id=span_passo,
            pai=self.span_id,
            passo=passo.nome,
            codigo=passo.codigo,
            classe=passo.classe,
        )
        self.passos.append(passo)
        return passo

    # --- modos ------------------------------------------------------------------------

    def diario(self) -> tuple[int, Optional[str]]:
        parada = self._antes_do_dia()
        if parada is not None:
            return parada
        dia = self.rodar("diario.py", "--email")
        if dia.codigo == EXIT_OK:
            email = dia.saida.get("email") or {}
            if email.get("status") == "falhou" and not self.reenviar_email():
                self.notificar(
                    "O dia foi gerado, mas o email das 7h não saiu (%s). Veja /goal-pacer status." % email.get("classe")
                )
            return EXIT_OK, None
        if dia.classe in ESTADOS_SEM_FALHA:
            self.notificar("Rode /goal-pacer onboarding para começar.")
            return dia.codigo, dia.classe
        self._email_de_falha(dia.classe or "Desconhecida")
        return dia.codigo, dia.classe

    def _antes_do_dia(self) -> Optional[tuple[int, Optional[str]]]:
        """Mensal quando o mês precisa, semanal nas segundas; devolve a parada do job, ou None para seguir ao dia."""
        precisa = self.rodar("balanco.py", "--precisa-mensal", sufixo="precisa", estado_e_resposta=True)
        if precisa.codigo == EXIT_ESTADO and precisa.texto.split("\n")[-1:] == ["sem_onboarding"]:
            self.notificar("Rode /goal-pacer onboarding para começar.")
            return EXIT_ESTADO, "SemOnboarding"
        if precisa.codigo == EXIT_ESTADO:
            return self._mensal_antes_do_dia(precisa)
        if precisa.codigo == EXIT_OK and self.agora.weekday() == 0:
            semanal = self.rodar("semanal.py")
            if semanal.codigo != EXIT_OK:
                self.avisos.append("semanal: %s" % semanal.classe)
        elif precisa.codigo != EXIT_OK:
            self.avisos.append("precisa-mensal: exit %d" % precisa.codigo)
        return None

    def _mensal_antes_do_dia(self, precisa: Passo) -> Optional[tuple[int, Optional[str]]]:
        self.log("precisa-mensal: %s" % precisa.texto)
        if ENV_TIMEOUT_JOB_S not in os.environ:
            self.teto_s = max(self.teto_s, TETO_COM_MENSAL_S)
        mensal = self.rodar("mensal.py")
        if mensal.codigo == EXIT_OK:
            return None
        self.avisos.append("mensal: %s" % mensal.classe)
        return (EXIT_TIMEOUT, "SessionTimeout") if mensal.classe == "SessionTimeout" else None

    def _email_de_falha(self, classe: str) -> None:
        """O email mínimo "hoje não gerei o seu dia", com tempo próprio; se nem ele sai, a notificação."""
        graca = _env_float(ENV_GRACA_EMAIL_S, GRACA_EMAIL_FALHA_S)
        self.teto_s = max(self.teto_s, (time.monotonic() - self.inicio) + graca)
        falha = self.rodar("diario.py", "--email-falha", classe, sufixo="email-falha")
        if falha.codigo != EXIT_OK:
            self.notificar(
                "Hoje não gerei o seu dia: %s. %s (run %s, runbook %s)"
                % (execucao.motivo(classe), execucao.acao(classe), self.run_id, execucao.info(classe).runbook)
            )

    def reenviar_email(self) -> bool:
        """Até ``TENTATIVAS_EMAIL`` novas tentativas do email do dia, espaçadas e dentro do teto do job."""
        espera = _env_float(ENV_RETRY_EMAIL_S, ESPERA_EMAIL_S)
        for tentativa in range(1, TENTATIVAS_EMAIL + 1):
            if self.restante_s() < espera + 60:
                self.log("email: sem tempo no teto para a tentativa %d" % tentativa)
                return False
            time.sleep(espera)
            passo = self.rodar("diario.py", "--reenviar-email", sufixo="email-%d" % tentativa)
            if passo.codigo == EXIT_OK and (passo.saida.get("email") or {}).get("status") in ("enviado", "ja_enviado"):
                self.log("email do dia enviado na tentativa %d" % tentativa)
                return True
        return False

    def mensal(self) -> tuple[int, Optional[str]]:
        self.teto_s = _env_float(ENV_TIMEOUT_JOB_S, TETO_COM_MENSAL_S)
        passo = self.rodar("mensal.py")
        if passo.codigo != EXIT_OK and passo.classe not in ESTADOS_SEM_FALHA:
            self.notificar(
                "O plano do mês não saiu: %s. %s (run %s)"
                % (
                    execucao.motivo(passo.classe or "Desconhecida"),
                    execucao.acao(passo.classe or "Desconhecida"),
                    self.run_id,
                )
            )
        return passo.codigo, passo.classe

    # --- fechamento -------------------------------------------------------------------

    def registrar(self, codigo: int, classe: Optional[str]) -> list[str]:
        """Grava a geração do job e devolve as sessões dos passos (para a retenção)."""
        try:
            registro = reg.carregar(self.dados)
        except GpErro as erro:
            self.log("registro não lido: %s" % erro.mensagem)
            return []
        tokens, sessoes = self._somar_passos(registro)
        geracao = self._geracao(codigo, classe, tokens, sessoes)
        try:
            reg.registrar_geracao(registro, geracao)
            self._alertas(registro, geracao)
            reg.registrar_geracao(registro, geracao)
            reg.salvar(registro, self.dados)
        except GpErro as erro:
            self.log("geração do job não gravada: %s" % erro.mensagem)
        try:
            for ano, n in reg.arquivar(self.dados, self.agora).items():
                self.log("registro-%d.json: %d entradas arquivadas" % (ano, n))
        except GpErro as erro:
            self.log("arquivo anual do registro não atualizado: %s" % erro.mensagem)
        return sessoes

    def _somar_passos(self, registro: dict[str, Any]) -> tuple[dict[str, int], list[str]]:
        """Tokens e sessões das gerações dos passos (run_id ``<job>-<passo>``)."""
        tokens = {"input": 0, "cache_read": 0, "cache_creation": 0, "output": 0}
        sessoes: list[str] = []
        passos = [g for r, g in registro.get("geracoes", {}).items() if r.startswith(self.run_id + "-")]
        for geracao in passos:
            for chave in tokens:
                tokens[chave] += int((geracao.get("tokens") or {}).get(chave, 0))
            sessoes.extend(geracao.get("sessoes") or [])
        return tokens, sessoes

    def _email_do_job(self) -> str:
        """O último envio do email do dia entre os passos: enviado, falhou ou nao_enviado."""
        email = "nao_enviado"
        for passo in self.passos:
            detalhe = passo.saida.get("email")
            if isinstance(detalhe, dict) and detalhe.get("status") in ("enviado", "falhou"):
                email = detalhe["status"]
        return email

    def _geracao(
        self, codigo: int, classe: Optional[str], tokens: dict[str, int], sessoes: list[str]
    ) -> dict[str, Any]:
        geracao: dict[str, Any] = {
            "run_id": self.run_id,
            "modo": "job:%s" % self.modo,
            "data": self.agora.date().isoformat(),
            "ts": clock.agora().isoformat(timespec="seconds"),
            "exit_code": int(codigo),
            "duracao_s": round(time.monotonic() - self.inicio, 1),
            "tokens": tokens,
            "sessoes": sessoes,
            "email": self._email_do_job(),
            "teto_s": round(self.teto_s, 1),
            "espera_lock_s": round(self.espera_lock_s, 1),
        }
        versao = "" if self.offline else _versao_claude()
        if versao:
            geracao["claude_version"] = versao
        if classe:
            info = execucao.info(classe)
            geracao.update({"classe": classe, "chave_runbook": info.runbook, "mensagem": execucao.motivo(classe)})
        return geracao

    def _alertas(self, registro: dict[str, Any], geracao: dict[str, Any]) -> None:
        """Alertas perto do limite deste job; o mesmo alerta em três jobs seguidos vira uma notificação."""
        atuais = saude.alertas(self.dados, clock.agora(), registro, so_do_job=True)
        geracao["alertas"] = [a["chave"] for a in atuais]
        repetido = saude.notificacao_repetida(registro, geracao["alertas"], run_id_atual=self.run_id)
        if repetido:
            geracao["alerta_notificado"] = repetido
            texto = next(a["texto"] for a in atuais if a["chave"] == repetido)
            self.notificar(copy.texto("saude.notificacao", texto=texto))
            telemetria.evento("alerta", chave=repetido, run_id=self.run_id)

    def reter(self, sessoes: list[str]) -> dict[str, int]:
        limite = time.time() - RETENCAO_DIAS * 86400
        raiz_projetos = (proxy.claude_config_dir() / proxy.PASTA_PROJECTS).resolve()
        return {
            "cache": _apagar_velhos(self.dados / "cache", PADROES_CACHE, limite),
            "logs": _apagar_velhos(self.logs, PADROES_LOGS, limite),
            "sessoes": sum(_apagar_sessao(sessao, raiz_projetos) for sessao in sessoes),
        }


def _matar_grupo(processo: subprocess.Popen) -> None:
    """A árvore do passo inteira (o claude -p cria netos); sem grupo, só o processo."""
    processos.matar_arvore(processo)


def _classe_do_passo(codigo: int, saida: dict[str, Any], stdout: str, estado_e_resposta: bool) -> Optional[str]:
    """Classe do erro pelo JSON do passo; exit 2 é resposta (não erro) no passo que pergunta por estado."""
    if codigo == EXIT_OK:
        return None
    classe = saida.get("classe") or execucao.classe_do_json(stdout or "")
    if classe is None and not (codigo == EXIT_ESTADO and estado_e_resposta):
        classe = "SessionTimeout" if codigo == EXIT_TIMEOUT else "Desconhecida"
    return classe


def _apagar_velhos(pasta: Path, padroes: tuple[str, ...], limite: float) -> int:
    """Arquivos (nunca links) dos ``padroes`` em ``pasta`` modificados antes de ``limite``."""
    if not pasta.is_dir():
        return 0
    velhos = {
        path: None
        for padrao in padroes
        for path in pasta.glob(padrao)
        if path.is_file() and not path.is_symlink() and path.stat().st_mtime < limite
    }  # dict: um arquivo que casa com dois padrões é apagado uma vez
    for path in velhos:
        path.unlink()
    return len(velhos)


def _apagar_sessao(sessao: str, raiz_projetos: Path) -> int:
    """Transcript e tool-results de uma sessão do job, só dentro de ``~/.claude/projects``."""
    apagados = 0
    for alvo in (
        proxy.caminho_transcript(base.jobs_dir(), sessao),
        proxy.caminho_tool_results(base.jobs_dir(), sessao),
    ):
        try:
            resolvido = alvo.resolve()
            if raiz_projetos not in resolvido.parents:
                continue
            if resolvido.is_file():
                resolvido.unlink()
                apagados += 1
            elif resolvido.is_dir() and resolvido.name == sessao:
                shutil.rmtree(resolvido)
                apagados += 1
        except (OSError, GpErro, ValueError):
            continue
    return apagados


def _json_final(stdout: str) -> dict[str, Any]:
    texto = (stdout or "").strip()
    if not texto:
        return {}
    try:
        dados = json.loads(texto)
        return dados if isinstance(dados, dict) else {}
    except ValueError:
        pass
    for linha in reversed(texto.split("\n")):
        try:
            dados = json.loads(linha)
            if isinstance(dados, dict):
                return dados
        except ValueError:
            continue
    return {}


def _versao_claude() -> str:
    try:
        resultado = subprocess.run(
            [proxy.claude_bin(), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return (resultado.stdout or "").strip().split(" ")[0][:40]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="job agendado do Goal Pacer: diario ou mensal")
    parser.add_argument("modo", choices=("diario", "mensal"))
    parser.add_argument("--offline", action="store_true", help="passos em modo offline (testes)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    agora = clock.agora()
    job = Job(args.modo, offline=args.offline, agora=agora)
    espera = _env_float(ENV_LOCK_ESPERA_S, ESPERA_LOCK_S)
    trava = gpio.Lock(job.dados / reg.NOME_LOCK, espera_s=espera, intervalo_s=min(5.0, max(0.1, espera / 10)))
    if not job.dados.is_dir():
        job.notificar("Rode /goal-pacer onboarding para começar.")
        return _sair(args, job, EXIT_ESTADO, "SemOnboarding", {})
    comeco_lock = time.monotonic()
    try:
        trava.adquirir()
        job.espera_lock_s = time.monotonic() - comeco_lock
    except GpErro as erro:
        # sem o lock nada é gravado: quem segura a pasta de dados é outro processo
        job.log(erro.mensagem)
        job.notificar("Outro job segurou a pasta de dados por tempo demais (run %s)." % job.run_id)
        return _sair(args, job, EXIT_IO, "LockTimeout", {})
    codigo, classe = EXIT_OK, None
    apagados: dict[str, int] = {}
    try:
        codigo, classe = job.diario() if args.modo == "diario" else job.mensal()
    except Exception as erro:  # noqa: BLE001 - o job nunca termina sem registro nem notificação
        codigo, classe = execucao.info("Desconhecida").codigo, "Desconhecida"
        job.log("erro inesperado: %s: %s" % (type(erro).__name__, erro))
        job.notificar("O job parou por um erro inesperado (run %s). %s" % (job.run_id, execucao.acao("Desconhecida")))
    finally:
        try:
            sessoes = job.registrar(codigo, classe)
            apagados = job.reter(sessoes)
        finally:
            trava.liberar()
    return _sair(args, job, codigo, classe, apagados)


def _sair(args: argparse.Namespace, job: Job, codigo: int, classe: Optional[str], apagados: dict[str, int]) -> int:
    job.log("fim: exit %d%s" % (codigo, " (%s)" % classe if classe else ""))
    telemetria.registrar_span(
        "job",
        (time.monotonic() - job.inicio) * 1000,
        span_id=job.span_id,
        pai="",
        modo=job.modo,
        codigo=codigo,
        classe=classe,
        espera_lock_s=round(job.espera_lock_s, 1),
    )
    if args.json:
        sys.stdout.write(
            json.dumps(
                {
                    "run_id": job.run_id,
                    "modo": job.modo,
                    "codigo": codigo,
                    "classe": classe,
                    "avisos": job.avisos,
                    "passos": [
                        {"nome": p.nome, "codigo": p.codigo, "classe": p.classe, "duracao_s": round(p.duracao_s, 1)}
                        for p in job.passos
                    ],
                    "retencao": apagados,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
