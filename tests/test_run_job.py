"""jobs/run_job.py (T8/T22): fluxo do job com passos de verdade (--offline) e com stubs.

Os stubs ficam num ``GP_SCRIPTS_DIR`` temporário: cada ``<script>.py`` lê o
comportamento de ``comportamento.json`` (lista consumida em ordem por
passo: exit, stdout, sleep, neto, geracao), grava a chamada em
``chamadas.jsonl`` e diz se recebeu o lock herdado. ``osascript`` é um stub
que grava o script recebido. Nada chama ``claude`` nem o launchd.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from goalpacer import registro as reg

RAIZ_REPO = Path(__file__).resolve().parent.parent
RUN_JOB = RAIZ_REPO / "jobs" / "run_job.py"
SCRIPTS_REAIS = RAIZ_REPO / "scripts"
FIXTURE_MENSAL = Path(__file__).resolve().parent / "fixtures" / "mensal"
SEGUNDA = "2026-09-28T07:00:00-03:00"
TERCA = "2026-09-29T07:00:00-03:00"

STUB = r"""#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["GP_TESTE_REAIS"])
from goalpacer import registro as reg

pasta = Path(os.environ["GP_STUB_DIR"])
nome = Path(sys.argv[0]).stem
if "--precisa-mensal" in sys.argv:
    nome += "-precisa"
if "--email-falha" in sys.argv:
    nome += "-email-falha"
if "--reenviar-email" in sys.argv:
    nome += "-reenviar"
comportamentos = json.loads((pasta / "comportamento.json").read_text(encoding="utf-8"))
contador = pasta / ("n-" + nome)
n = int(contador.read_text()) if contador.exists() else 0
contador.write_text(str(n + 1))
lista = comportamentos.get(nome) or [{}]
item = lista[min(n, len(lista) - 1)]
trava = reg.lock(Path(os.environ["GP_DATA_DIR"]))
herdado = type(trava).__name__
trava.liberar()
with open(pasta / "chamadas.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"nome": nome, "argv": sys.argv[1:], "run_id": os.environ.get("GP_RUN_ID"), "lock": herdado}) + "\n")
if item.get("geracao"):
    registro = reg.carregar()
    geracao = {"run_id": os.environ["GP_RUN_ID"], "modo": nome, "data": "2026-09-28", "ts": "2026-09-28T07:00:00-03:00", "exit_code": 0}
    geracao.update(item["geracao"])
    reg.registrar_geracao(registro, geracao)
    reg.salvar(registro)
if item.get("neto"):
    neto = subprocess.Popen(["sleep", "60"])
    (pasta / "neto.pid").write_text(str(neto.pid))
if item.get("sleep"):
    time.sleep(item["sleep"])
sys.stdout.write(item.get("stdout", ""))
raise SystemExit(item.get("exit", 0))
"""

OSASCRIPT = r"""#!/usr/bin/env python3
import os, sys
with open(os.environ["GP_STUB_DIR"] + "/notificacoes.txt", "a", encoding="utf-8") as f:
    f.write(sys.argv[-1] + "\n")
"""


class Ambiente:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.raiz = tmp_path / "raiz"
        self.dados = tmp_path / "dados"
        self.stubs = tmp_path / "stubs"
        self.claude = tmp_path / "claude-config"
        for pasta in (self.raiz, self.dados, self.stubs, self.claude):
            pasta.mkdir(exist_ok=True)
        for nome in ("balanco.py", "mensal.py", "semanal.py", "diario.py"):
            (self.stubs / nome).write_text(STUB, encoding="utf-8")
        osascript = self.stubs / "osascript"
        osascript.write_text(OSASCRIPT, encoding="utf-8")
        osascript.chmod(0o755)
        self.comportamento({})

    def comportamento(self, dados: dict) -> None:
        (self.stubs / "comportamento.json").write_text(json.dumps(dados), encoding="utf-8")

    def env(self, **extra: str) -> dict:
        base_env = {
            k: v
            for k, v in os.environ.items()
            if (not k.startswith("GP_") or k == "GP_PLATAFORMA") and k != "CLAUDE_CONFIG_DIR"
        }
        base_env.update(
            {
                "GP_RAIZ": str(self.raiz),
                "GP_DATA_DIR": str(self.dados),
                "GP_SCRIPTS_DIR": str(self.stubs),
                "GP_STUB_DIR": str(self.stubs),
                "GP_TESTE_REAIS": str(SCRIPTS_REAIS),
                "GP_OSASCRIPT": str(self.stubs / "osascript"),
                "GP_AGORA": SEGUNDA,
                "GP_TZ": "America/Sao_Paulo",
                "GP_RETRY_SLEEP": "0",
                "GP_RETRY_EMAIL_S": "0",
                "CLAUDE_CONFIG_DIR": str(self.claude),
            }
        )
        base_env.update(extra)
        return base_env

    def rodar(
        self, modo: str = "diario", *, offline: bool = True, timeout: float = 60, **extra: str
    ) -> tuple[subprocess.CompletedProcess, dict]:
        args = [sys.executable, str(RUN_JOB), modo, "--json"] + (["--offline"] if offline else [])
        proc = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", env=self.env(**extra), timeout=timeout
        )
        saida = json.loads(proc.stdout.strip().split("\n")[-1]) if proc.stdout.strip() else {}
        return proc, saida

    def chamadas(self) -> list[dict]:
        path = self.stubs / "chamadas.jsonl"
        if not path.exists():
            return []
        return [json.loads(linha) for linha in path.read_text(encoding="utf-8").splitlines() if linha.strip()]

    def notificacoes(self) -> list[str]:
        path = self.stubs / "notificacoes.txt"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


@pytest.fixture
def amb(tmp_path: Path) -> Ambiente:
    return Ambiente(tmp_path)


def nomes(amb: Ambiente) -> list[str]:
    return [c["nome"] for c in amb.chamadas()]


def test_encadeia_mensal_quando_precisa_e_herda_lock(amb):
    amb.comportamento(
        {
            "balanco-precisa": [{"exit": 2, "stdout": "sem plano de 2026-10\n"}],
            "diario": [{"stdout": json.dumps({"email": {"status": "enviado"}})}],
        }
    )
    proc, saida = amb.rodar()
    assert proc.returncode == 0, proc.stderr
    assert nomes(amb) == ["balanco-precisa", "mensal", "diario"]
    assert {c["lock"] for c in amb.chamadas()} == {"LockHerdado"}
    assert [c["run_id"] for c in amb.chamadas()] == [
        "%s-%s" % (saida["run_id"], p) for p in ("precisa", "mensal", "diario")
    ]
    assert "--email" in amb.chamadas()[2]["argv"]
    assert [p["classe"] for p in saida["passos"]] == [None, None, None]
    assert not (amb.dados / ".lock").exists()
    geracao = reg.carregar(amb.dados)["geracoes"][saida["run_id"]]
    assert geracao["modo"] == "job:diario" and geracao["exit_code"] == 0 and geracao["email"] == "enviado"
    assert amb.notificacoes() == []


def test_segunda_sem_mensal_roda_semanal_e_terca_nao(amb):
    proc, _ = amb.rodar()
    assert proc.returncode == 0 and nomes(amb) == ["balanco-precisa", "semanal", "diario"]
    (amb.stubs / "chamadas.jsonl").unlink()
    proc, _ = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 0 and nomes(amb) == ["balanco-precisa", "diario"]


def test_sem_onboarding_nao_chama_mensal_e_notifica(amb):
    amb.comportamento({"balanco-precisa": [{"exit": 2, "stdout": "sem_onboarding\n"}]})
    proc, saida = amb.rodar()
    assert proc.returncode == 2 and saida["classe"] == "SemOnboarding"
    assert nomes(amb) == ["balanco-precisa"]
    assert any("onboarding" in n for n in amb.notificacoes())


def test_pasta_de_dados_ausente(amb):
    shutil.rmtree(amb.dados)
    proc, saida = amb.rodar()
    assert proc.returncode == 2 and saida["classe"] == "SemOnboarding" and nomes(amb) == []
    assert not amb.dados.exists()


def test_rate_limited_retenta_uma_vez(amb):
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "RateLimited"})
    amb.comportamento({"diario": [{"exit": 3, "stdout": erro}, {"stdout": "{}"}]})
    proc, _saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 0, proc.stderr
    assert nomes(amb) == ["balanco-precisa", "diario", "diario"]


def test_rate_limited_duas_vezes_nao_tenta_terceira_e_manda_email_de_falha(amb):
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "RateLimited"})
    amb.comportamento({"diario": [{"exit": 3, "stdout": erro}]})
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 3 and saida["classe"] == "RateLimited"
    assert nomes(amb) == ["balanco-precisa", "diario", "diario", "diario-email-falha"]
    falha = amb.chamadas()[-1]["argv"]
    assert falha[falha.index("--email-falha") + 1] == "RateLimited"
    assert amb.notificacoes() == []
    geracao = reg.carregar(amb.dados)["geracoes"][saida["run_id"]]
    assert geracao["classe"] == "RateLimited" and geracao["chave_runbook"] and geracao["exit_code"] == 3


def test_email_de_falha_falhou_notifica(amb):
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "EscopoInsuficiente"})
    amb.comportamento({"diario": [{"exit": 3, "stdout": erro}], "diario-email-falha": [{"exit": 3, "stdout": erro}]})
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 3 and saida["classe"] == "EscopoInsuficiente"
    notas = amb.notificacoes()
    assert len(notas) == 1 and saida["run_id"] in notas[0] and "Hoje não gerei o seu dia" in notas[0]


def test_email_do_dia_falhou_tenta_tres_vezes_e_notifica(amb):
    amb.comportamento(
        {
            "diario": [{"stdout": json.dumps({"email": {"status": "falhou", "classe": "EscopoInsuficiente"}})}],
            "diario-reenviar": [
                {"exit": 3, "stdout": json.dumps({"ok": False, "codigo": 3, "classe": "EscopoInsuficiente"})}
            ],
        }
    )
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 0 and nomes(amb) == [
        "balanco-precisa",
        "diario",
        "diario-reenviar",
        "diario-reenviar",
        "diario-reenviar",
    ]
    assert [p["nome"] for p in saida["passos"]][-3:] == ["email-1", "email-2", "email-3"]
    assert len(amb.notificacoes()) == 1 and "email" in amb.notificacoes()[0]
    assert reg.carregar(amb.dados)["geracoes"][saida["run_id"]]["email"] == "falhou"


def test_email_do_dia_sai_na_segunda_tentativa_sem_notificar(amb):
    amb.comportamento(
        {
            "diario": [{"stdout": json.dumps({"email": {"status": "falhou", "classe": "ErroConector"}})}],
            "diario-reenviar": [
                {"exit": 3, "stdout": json.dumps({"ok": False, "codigo": 3, "classe": "ErroConector"})},
                {"stdout": json.dumps({"email": {"status": "enviado", "id": "m1"}})},
            ],
        }
    )
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 0 and nomes(amb).count("diario-reenviar") == 2 and amb.notificacoes() == []
    assert reg.carregar(amb.dados)["geracoes"][saida["run_id"]]["email"] == "enviado"


def test_sem_tempo_no_teto_nao_tenta_o_email(amb):
    amb.comportamento({"diario": [{"stdout": json.dumps({"email": {"status": "falhou", "classe": "ErroConector"}})}]})
    proc, _ = amb.rodar(GP_AGORA=TERCA, GP_RETRY_EMAIL_S="3600")
    assert proc.returncode == 0 and "diario-reenviar" not in nomes(amb) and len(amb.notificacoes()) == 1


def test_timeout_mata_o_grupo_do_passo(amb):
    amb.comportamento({"diario": [{"sleep": 30, "neto": True}]})
    inicio = time.monotonic()
    proc, saida = amb.rodar(GP_AGORA=TERCA, GP_TIMEOUT_JOB_S="3")
    assert time.monotonic() - inicio < 20
    assert proc.returncode == 5 and saida["classe"] == "SessionTimeout"
    neto = int((amb.stubs / "neto.pid").read_text())
    for _ in range(50):
        try:
            os.kill(neto, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("processo neto do passo sobreviveu ao timeout")
    # o email mínimo de falha ganha a graça própria mesmo depois do estouro
    assert nomes(amb) == ["balanco-precisa", "diario", "diario-email-falha"]
    falha = amb.chamadas()[-1]["argv"]
    assert falha[falha.index("--email-falha") + 1] == "SessionTimeout"
    assert amb.notificacoes() == []


def test_lock_preso_vira_lock_timeout(amb):
    dono = subprocess.Popen(["sleep", "30"])
    try:
        (amb.dados / ".lock").write_text(
            json.dumps({"pid": dono.pid, "criado_em": "2026-09-28T09:59:00+00:00", "run_id": "outro"}), encoding="utf-8"
        )
        proc, saida = amb.rodar(GP_LOCK_ESPERA_S="0.5")
        assert proc.returncode == 4 and saida["classe"] == "LockTimeout"
        assert nomes(amb) == []
        assert len(amb.notificacoes()) == 1
        assert json.loads((amb.dados / ".lock").read_text(encoding="utf-8"))["pid"] == dono.pid
    finally:
        dono.kill()
        dono.wait()


def test_modo_mensal_so_roda_o_mensal(amb):
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "ErroConector"})
    amb.comportamento({"mensal": [{"exit": 3, "stdout": erro}]})
    proc, _saida = amb.rodar("mensal")
    assert proc.returncode == 3 and nomes(amb) == ["mensal"]
    assert len(amb.notificacoes()) == 1 and "plano do mês" in amb.notificacoes()[0]


def test_tokens_sessoes_e_retencao(amb):
    sessao, outra = "11111111-aaaa-bbbb-cccc-000000000001", "22222222-aaaa-bbbb-cccc-000000000002"
    amb.comportamento(
        {
            "diario": [
                {
                    "stdout": "{}",
                    "geracao": {
                        "tokens": {"input": 10, "output": 5, "cache_read": 100, "cache_creation": 1},
                        "sessoes": [sessao],
                    },
                }
            ]
        }
    )
    cache = amb.dados / "cache"
    cache.mkdir()
    velho = time.time() - 8 * 86400
    for nome in ("calendar-diario-2026-09-01.json", "ops-x.json", "email-x.json", "rascunho-velho.json"):
        (cache / nome).write_text("{}", encoding="utf-8")
        os.utime(cache / nome, (velho, velho))
    (cache / "calendar-diario-2026-09-27.json").write_text("{}", encoding="utf-8")
    logs = amb.raiz / "jobs" / "logs"
    logs.mkdir(parents=True)
    (logs / "run-antigo.log").write_text("x", encoding="utf-8")
    os.utime(logs / "run-antigo.log", (velho, velho))
    slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in str((amb.raiz / "jobs").resolve()))
    projeto = amb.claude / "projects" / slug
    (projeto / sessao / "tool-results").mkdir(parents=True)
    (projeto / (sessao + ".jsonl")).write_text("{}", encoding="utf-8")
    (projeto / (sessao) / "tool-results" / "a.txt").write_text("x", encoding="utf-8")
    (projeto / (outra + ".jsonl")).write_text("{}", encoding="utf-8")
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 0, proc.stderr
    geracao = reg.carregar(amb.dados)["geracoes"][saida["run_id"]]
    assert geracao["tokens"] == {"input": 10, "output": 5, "cache_read": 100, "cache_creation": 1}
    assert geracao["sessoes"] == [sessao]
    assert sorted(p.name for p in cache.iterdir()) == ["calendar-diario-2026-09-27.json", "rascunho-velho.json"]
    assert not (logs / "run-antigo.log").exists() and (logs / ("run-%s.log" % saida["run_id"])).exists()
    assert not (projeto / (sessao + ".jsonl")).exists() and not (projeto / sessao).exists()
    assert (projeto / (outra + ".jsonl")).exists()
    assert saida["retencao"] == {"cache": 3, "logs": 1, "sessoes": 2}


def test_job_offline_de_verdade_duas_vezes(tmp_path):
    """Passos reais em --offline: 1ª execução gera o plano de outubro, o dia e o email;
    a 2ª (mesma manhã) não refaz o mensal, roda o semanal de segunda e não manda o email de novo."""
    amb = Ambiente(tmp_path)
    shutil.rmtree(amb.dados)
    shutil.copytree(FIXTURE_MENSAL / "dados", amb.dados)
    extra = {"GP_SCRIPTS_DIR": str(SCRIPTS_REAIS), "GP_OFFLINE_DIR": str(FIXTURE_MENSAL / "offline")}
    proc, saida = amb.rodar(**extra)
    assert proc.returncode == 0, proc.stderr
    assert [p["nome"] for p in saida["passos"]] == ["precisa", "mensal", "diario"]
    assert (amb.dados / "planos" / "2026-10.md").exists() and (amb.dados / "dias" / "2026-09-28.md").exists()
    assert (amb.dados / "cache" / ("email-%s-diario.json" % saida["run_id"])).exists()
    assert not (amb.dados / ".lock").exists()
    dia = (amb.dados / "dias" / "2026-09-28.md").read_text(encoding="utf-8")
    time.sleep(1.1)
    proc, segunda = amb.rodar(**extra)
    assert proc.returncode == 0, proc.stderr
    assert segunda["run_id"] == saida["run_id"]  # relógio fixo: mesmo id, a geração é sobrescrita
    assert [p["nome"] for p in segunda["passos"]] == ["precisa", "semanal", "diario"]
    emails = sorted(p.name for p in (amb.dados / "cache").glob("email-*.json"))
    assert emails == ["email-%s-diario.json" % saida["run_id"]]
    import re

    assert re.sub(
        r"^run_id: .*$", "", (amb.dados / "dias" / "2026-09-28.md").read_text(encoding="utf-8"), flags=re.MULTILINE
    ) == re.sub(r"^run_id: .*$", "", dia, flags=re.MULTILINE)


def test_lock_preso_nao_grava_registro(amb):
    dono = subprocess.Popen(["sleep", "30"])
    try:
        (amb.dados / ".lock").write_text(
            json.dumps({"pid": dono.pid, "criado_em": "2026-09-28T09:59:00+00:00"}), encoding="utf-8"
        )
        proc, _saida = amb.rodar(GP_LOCK_ESPERA_S="0.3")
        assert proc.returncode == 4 and not (amb.dados / "registro.json").exists()
    finally:
        dono.kill()
        dono.wait()


def test_espera_do_rate_limited_nao_conta_no_teto(amb):
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "RateLimited"})
    amb.comportamento({"diario": [{"exit": 3, "stdout": erro}, {"stdout": "{}"}]})
    proc, _saida = amb.rodar(GP_AGORA=TERCA, GP_TIMEOUT_JOB_S="3", GP_RETRY_SLEEP="3.5")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert nomes(amb) == ["balanco-precisa", "diario", "diario"]


def test_exit_2_sem_classe_fora_do_precisa_vira_desconhecida(amb):
    amb.comportamento({"diario": [{"exit": 2, "stdout": "saída sem json"}]})
    proc, saida = amb.rodar(GP_AGORA=TERCA)
    assert proc.returncode == 2 and saida["classe"] == "Desconhecida"
    falha = amb.chamadas()[-1]
    assert falha["nome"] == "diario-email-falha" and "Desconhecida" in falha["argv"]


def test_erro_inesperado_registra_e_libera_lock(amb, monkeypatch, guardar_env):
    guardar_env("GP_TRACE_ID", "GP_TRACE_PAI")
    sys.path.insert(0, str(RUN_JOB.parent))
    import run_job

    for chave, valor in amb.env(GP_AGORA=TERCA).items():
        if (chave.startswith("GP_") and chave != "GP_PLATAFORMA") or chave == "CLAUDE_CONFIG_DIR":
            monkeypatch.setenv(chave, valor)
    from goalpacer import clock

    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)

    def explode(self):
        raise RuntimeError("disco sumiu")

    monkeypatch.setattr(run_job.Job, "diario", explode)
    assert run_job.main(["diario", "--offline"]) == 3
    geracoes = reg.carregar(amb.dados)["geracoes"]
    job = next(g for g in geracoes.values() if g["modo"] == "job:diario")
    assert job["classe"] == "Desconhecida" and job["exit_code"] == 3
    assert not (amb.dados / ".lock").exists()
    assert len(amb.notificacoes()) == 1 and "erro inesperado" in amb.notificacoes()[0]


def test_trace_do_job_liga_passos_ao_job_e_guarda_teto_e_lock(amb):
    """O2 (análise de 13/09): um trace por job, com o span de cada passo pendurado no do job."""
    amb.comportamento(
        {"balanco-precisa": [{"exit": 0}], "diario": [{"stdout": json.dumps({"email": {"status": "enviado"}})}]}
    )
    proc, saida = amb.rodar()
    assert proc.returncode == 0, proc.stderr
    linhas = [
        json.loads(l)
        for l in (amb.raiz / "jobs" / "logs" / ("trace-%s.jsonl" % saida["run_id"]))
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    job = [l for l in linhas if l["nome"] == "job"]
    passos = [l for l in linhas if l["nome"] == "passo"]
    assert len(job) == 1 and job[0]["pai"] is None and job[0]["codigo"] == 0
    assert [p["passo"] for p in passos] == ["precisa", "semanal", "diario"] and all(
        p["pai"] == job[0]["span_id"] for p in passos
    )
    geracao = reg.carregar(amb.dados)["geracoes"][saida["run_id"]]
    assert geracao["teto_s"] == 1200.0 and geracao["espera_lock_s"] >= 0


def test_alerta_perto_do_teto_em_tres_jobs_seguidos_vira_uma_notificacao(amb):
    """O6 (análise de 13/09): o alerta vai para o registro em cada job e vira notificação na terceira vez seguida, uma vez."""
    amb.comportamento(
        {
            "balanco-precisa": [{"exit": 0}],
            # 4,4 s num teto de 6 s: passa dos 70% do alerta e ainda sobra 1,6 s para a partida dos processos (no CI,
            # sob cobertura, a sobra de 0,4 s do teto de 2 s estourava e o job saía por timeout)
            "diario": [{"sleep": 4.4, "stdout": json.dumps({"email": {"status": "enviado"}})}],
        }
    )
    dias = (
        "2026-09-29T07:00:00-03:00",
        "2026-09-30T07:00:00-03:00",
        "2026-10-01T07:00:00-03:00",
        "2026-10-02T07:00:00-03:00",
    )
    saidas = []
    for dia in dias:
        proc, saida = amb.rodar(GP_AGORA=dia, GP_TIMEOUT_JOB_S="6")
        assert proc.returncode == 0, proc.stderr
        saidas.append(saida)
    geracoes = reg.carregar(amb.dados)["geracoes"]
    assert all("job_perto_do_teto" in geracoes[s["run_id"]]["alertas"] for s in saidas)
    assert [geracoes[s["run_id"]].get("alerta_notificado") for s in saidas] == [None, None, "job_perto_do_teto", None]
    notificacoes = amb.notificacoes()
    assert len(notificacoes) == 1 and "Goal Pacer, três jobs seguidos: O job de qui 01/10 levou" in notificacoes[0]


def _pasta(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_ramos_de_falha_do_mensal_semanal_e_precisa(amb):
    """T2 (análise de 13/09): falhas dos passos anteriores ao diário não derrubam o dia, só avisam; mensal estourado encerra."""
    tempo = json.dumps({"ok": False, "codigo": 5, "classe": "SessionTimeout"})
    amb.comportamento(
        {"balanco-precisa": [{"exit": 2, "stdout": "sem plano\n"}], "mensal": [{"exit": 5, "stdout": tempo}]}
    )
    proc, saida = amb.rodar()
    assert proc.returncode == 5 and saida["classe"] == "SessionTimeout" and nomes(amb) == ["balanco-precisa", "mensal"]
    amb2 = Ambiente(_pasta(amb.tmp / "segunda"))
    erro = json.dumps({"ok": False, "codigo": 3, "classe": "CacheInvalido"})
    amb2.comportamento(
        {
            "balanco-precisa": [{"exit": 0}],
            "semanal": [{"exit": 3, "stdout": erro}],
            "diario": [{"stdout": json.dumps({"email": {"status": "enviado"}})}],
        }
    )
    proc, saida = amb2.rodar()
    assert (
        proc.returncode == 0
        and saida["avisos"] == ["semanal: CacheInvalido"]
        and nomes(amb2) == ["balanco-precisa", "semanal", "diario"]
    )
    amb3 = Ambiente(_pasta(amb.tmp / "terca"))
    amb3.comportamento(
        {"balanco-precisa": [{"exit": 4}], "diario": [{"stdout": json.dumps({"email": {"status": "enviado"}})}]}
    )
    proc, saida = amb3.rodar(GP_AGORA="2026-09-29T07:00:00-03:00")
    assert proc.returncode == 0 and saida["avisos"] == ["precisa-mensal: exit 4"]
    amb4 = Ambiente(_pasta(amb.tmp / "sem-meta"))
    sem_meta = json.dumps({"ok": False, "codigo": 2, "classe": "SemMetaAtiva"})
    amb4.comportamento({"balanco-precisa": [{"exit": 0}], "diario": [{"exit": 2, "stdout": sem_meta}]})
    proc, saida = amb4.rodar(GP_AGORA="2026-09-29T07:00:00-03:00")
    assert (
        proc.returncode == 2
        and saida["classe"] == "SemMetaAtiva"
        and len(amb4.notificacoes()) == 1
        and "Rode /goal-pacer onboarding para começar." in amb4.notificacoes()[0]
    )


def test_teto_esgotado_antes_do_passo_e_registro_ilegivel_nao_travam_o_fim(amb):
    """T2: sem tempo o passo nem começa (SessionTimeout); registro corrompido sem .bak vira log, e o lock é liberado."""
    amb.comportamento({"balanco-precisa": [{"exit": 0, "sleep": 0.3}]})
    proc, saida = amb.rodar(GP_TIMEOUT_JOB_S="0.2", GP_AGORA="2026-09-29T07:00:00-03:00")
    diario = next(p for p in saida["passos"] if p["nome"] == "diario")
    assert proc.returncode == 5 and diario["classe"] == "SessionTimeout" and diario["duracao_s"] == 0.0
    (amb.dados / "registro.json").write_text("{quebrado", encoding="utf-8")
    amb.comportamento(
        {"balanco-precisa": [{"exit": 0}], "diario": [{"stdout": json.dumps({"email": {"status": "enviado"}})}]}
    )
    proc, saida = amb.rodar(GP_AGORA="2026-09-30T07:00:00-03:00")
    log = (amb.raiz / "jobs" / "logs" / ("run-%s.log" % saida["run_id"])).read_text(encoding="utf-8")
    assert "registro não lido" in log and not (amb.dados / ".lock").exists()
