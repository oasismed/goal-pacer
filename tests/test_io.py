"""Testes de goalpacer.io: escrita atômica, .bak, JSON, recuperar, Lock.

O teste de dois processos usa ``subprocess`` com dois Pythons reais
disputando o mesmo lock (o segundo falha com GpErro/EEXIST).

O relógio é o ``goalpacer.clock`` real (``GP_AGORA`` vem da fixture
``agora_fixo`` do conftest; os subprocessos usam o relógio do sistema). A
idade do lock é pelo mtime do arquivo: os testes envelhecem locks com
``os.utime``, nunca com ``GP_AGORA``.
"""

from __future__ import annotations

import errno
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from goalpacer import clock, io as gio
from goalpacer.base import EXIT_IO, EXIT_VALIDACAO, GpErro

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

# Trecho comum aos scripts inline dos subprocessos: sys.path + imports.
PREAMBULO_SUBPROCESSO = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, %r)
    from goalpacer import io as gio
    from goalpacer.base import GpErro
    """
    % str(SCRIPTS)
)


def _escrever_lock(path: Path, pid: int, criado_em: datetime, run_id=None) -> None:
    path.write_text(
        json.dumps({"pid": pid, "criado_em": criado_em.isoformat(timespec="seconds"), "run_id": run_id}),
        encoding="utf-8",
    )


def _envelhecer(path: Path, segundos: float) -> None:
    """Recua o mtime de ``path`` em ``segundos`` (a idade do lock é pelo mtime)."""
    antigo = time.time() - segundos
    os.utime(path, (antigo, antigo))


def _pid_morto() -> int:
    """Pid de um filho já encerrado e colhido: ``os.kill(pid, 0)`` falha."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    assert p.wait(timeout=60) == 0
    return p.pid


# --------------------------------------------------------------- atômico


def test_escrever_atomico_conteudo_final_e_bak(tmp_path):
    p = tmp_path / "registro.json"
    bak = tmp_path / "registro.json.bak"

    gio.escrever_atomico(p, "v1\n")
    assert p.read_text(encoding="utf-8") == "v1\n"
    assert not bak.exists()

    gio.escrever_atomico(p, "v2 ação ☕\n")
    assert p.read_text(encoding="utf-8") == "v2 ação ☕\n"
    assert bak.read_text(encoding="utf-8") == "v1\n"

    gio.escrever_atomico(p, "v3\n")
    assert p.read_text(encoding="utf-8") == "v3\n"
    assert bak.read_text(encoding="utf-8") == "v2 ação ☕\n"


def test_escrever_atomico_tmp_no_mesmo_diretorio(tmp_path, monkeypatch):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    p = pasta / "x.md"
    p.write_text("antes\n", encoding="utf-8")
    dirs = []
    original = tempfile.mkstemp

    def espiao(*args, **kwargs):
        dirs.append(kwargs.get("dir"))
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", espiao)
    gio.escrever_atomico(p, "depois\n")

    assert dirs, "mkstemp não foi chamado"
    assert all(Path(d) == pasta for d in dirs)
    assert sorted(f.name for f in pasta.iterdir()) == ["x.md", "x.md.bak"]


def test_escrever_atomico_sem_bak(tmp_path):
    p = tmp_path / "a.txt"
    bak = tmp_path / "a.txt.bak"
    gio.escrever_atomico(p, "v1", bak=False)
    gio.escrever_atomico(p, "v2", bak=False)
    assert p.read_text(encoding="utf-8") == "v2"
    assert not bak.exists()

    gio.escrever_atomico(p, "v3")
    assert bak.read_text(encoding="utf-8") == "v2"
    gio.escrever_atomico(p, "v4", bak=False)
    assert p.read_text(encoding="utf-8") == "v4"
    assert bak.read_text(encoding="utf-8") == "v2"


def test_escrever_atomico_bytes(tmp_path):
    p = tmp_path / "bin.dat"
    dados = b"\x00\xff\xfe caf\xc3\xa9\n"
    gio.escrever_atomico(p, dados)
    assert p.read_bytes() == dados
    gio.escrever_atomico(p, b"outro")
    assert (tmp_path / "bin.dat.bak").read_bytes() == dados


def test_escrever_atomico_cria_pasta_pai(tmp_path):
    p = tmp_path / "dias" / "2026-09-28.md"
    gio.escrever_atomico(p, "ok\n")
    assert p.read_text(encoding="utf-8") == "ok\n"


def test_escrever_atomico_recusa_symlink(tmp_path):
    externo = tmp_path / "externo.txt"
    externo.write_text("fora\n", encoding="utf-8")
    dados = tmp_path / "dados"
    dados.mkdir()
    link = dados / "registro.json"
    link.symlink_to(externo)
    with pytest.raises(GpErro) as exc:
        gio.escrever_atomico(link, "novo\n")
    assert exc.value.codigo == EXIT_IO
    assert "symlink" in exc.value.mensagem
    # Nem o alvo nem a pasta de dados foram tocados (sem .bak com conteúdo externo).
    assert externo.read_text(encoding="utf-8") == "fora\n"
    assert sorted(f.name for f in dados.iterdir()) == ["registro.json"]
    # Link quebrado também é recusado.
    quebrado = dados / "x.md"
    quebrado.symlink_to(tmp_path / "nao-existe")
    with pytest.raises(GpErro):
        gio.escrever_atomico(quebrado, "x")


def test_escrever_atomico_recusa_tipo_errado(tmp_path):
    p = tmp_path / "a.txt"
    for ruim in (5, None, ["x"], {"a": 1}):
        with pytest.raises(TypeError):
            gio.escrever_atomico(p, ruim)  # type: ignore[arg-type]
    assert not p.exists()
    gio.escrever_atomico(p, bytearray(b"ba"))
    gio.escrever_atomico(p, memoryview(b"mv"))
    assert p.read_bytes() == b"mv"
    assert (tmp_path / "a.txt.bak").read_bytes() == b"ba"


def test_escrever_atomico_falha_mantem_anterior_e_limpa_tmp(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    gio.escrever_atomico(p, "v1")
    gio.escrever_atomico(p, "v2")

    def replace_falha(src, dst):
        raise OSError(errno.EIO, "disco simulado")

    monkeypatch.setattr(os, "replace", replace_falha)
    with pytest.raises(GpErro) as exc:
        gio.escrever_atomico(p, "v3")
    assert exc.value.codigo == EXIT_IO
    assert p.read_text(encoding="utf-8") == "v2"
    assert (tmp_path / "r.json.bak").read_text(encoding="utf-8") == "v1"
    assert sorted(f.name for f in tmp_path.iterdir()) == ["r.json", "r.json.bak"]


# --------------------------------------------------------------------- JSON


def test_json_unicode_sem_escape(tmp_path):
    p = tmp_path / "perfil.json"
    obj = {"título": "Ação ☕ 🇧🇷", "lista": ["ç", "ã"]}
    gio.escrever_json(p, obj)
    texto = p.read_text(encoding="utf-8")
    assert "Ação ☕ 🇧🇷" in texto
    assert "\\u" not in texto
    assert gio.ler_json(p) == obj


def test_json_sort_keys_indent_newline_final(tmp_path):
    p = tmp_path / "x.json"
    gio.escrever_json(p, {"b": 1, "a": [1, 2], "c": {"z": None, "y": True}})
    esperado = '{\n  "a": [\n    1,\n    2\n  ],\n  "b": 1,\n  "c": {\n    "y": true,\n    "z": null\n  }\n}\n'
    assert p.read_text(encoding="utf-8") == esperado


def test_json_escrever_gera_bak(tmp_path):
    p = tmp_path / "registro.json"
    gio.escrever_json(p, {"v": 1})
    gio.escrever_json(p, {"v": 2})
    assert gio.ler_json(p) == {"v": 2}
    assert gio.ler_json(tmp_path / "registro.json.bak") == {"v": 1}


def test_escrever_json_recusa_nan_e_infinity(tmp_path):
    p = tmp_path / "perfil.json"
    gio.escrever_json(p, {"ok": 1})
    for ruim in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(GpErro) as exc:
            gio.escrever_json(p, {"taxa_conclusao_por_janela": {"seg-manha": ruim}})
        assert exc.value.codigo == EXIT_VALIDACAO
        assert "finito" in exc.value.mensagem
    # Nada foi gravado: arquivo e ausência de .bak novo.
    assert gio.ler_json(p) == {"ok": 1}
    assert not (tmp_path / "perfil.json.bak").exists()
    texto = p.read_text(encoding="utf-8")
    assert "NaN" not in texto and "Infinity" not in texto


def test_ler_json_ausente_ou_invalido_erro(tmp_path):
    with pytest.raises(GpErro) as exc:
        gio.ler_json(tmp_path / "nao_existe.json")
    assert exc.value.codigo == EXIT_IO

    p = tmp_path / "quebrado.json"
    p.write_text('{"a": 1, "b": [1, 2', encoding="utf-8")
    with pytest.raises(GpErro) as exc:
        gio.ler_json(p)
    assert exc.value.codigo == EXIT_IO
    assert "quebrado.json" in exc.value.mensagem


# ---------------------------------------------------------------- recuperar


def test_recuperar_restaura_bak_quando_corrompido(tmp_path):
    p = tmp_path / "registro.json"
    gio.escrever_json(p, {"schema_version": 1, "tasks": {}})
    # Segunda gravação truncada: o .bak guarda a versão boa.
    gio.escrever_atomico(p, '{"schema_version": 1, "tasks": {"D-2026-09-28-01": {"meta": "M01"')
    with pytest.raises(GpErro):
        gio.ler_json(p)

    assert gio.recuperar(p) is True
    assert gio.ler_json(p) == {"schema_version": 1, "tasks": {}}


def test_recuperar_sem_bak_devolve_false(tmp_path):
    p = tmp_path / "registro.json"
    p.write_text("{truncado", encoding="utf-8")
    assert gio.recuperar(p) is False
    assert p.read_text(encoding="utf-8") == "{truncado"
    assert not (tmp_path / "registro.json.bak").exists()


def test_recuperar_bak_tambem_corrompido_devolve_false(tmp_path):
    p = tmp_path / "registro.json"
    p.write_text("{truncado", encoding="utf-8")
    bak = tmp_path / "registro.json.bak"
    bak.write_text("[tambem", encoding="utf-8")
    assert gio.recuperar(p) is False
    assert p.read_text(encoding="utf-8") == "{truncado"
    assert bak.read_text(encoding="utf-8") == "[tambem"


def test_recuperar_nunca_apaga_bak(tmp_path):
    p = tmp_path / "registro.json"
    gio.escrever_json(p, {"v": 1})
    gio.escrever_atomico(p, "{corrompido")
    bak = tmp_path / "registro.json.bak"
    conteudo_bak = bak.read_bytes()

    assert gio.recuperar(p) is True
    assert bak.exists()
    assert bak.read_bytes() == conteudo_bak
    assert gio.ler_json(p) == {"v": 1}
    # Recuperar de novo é inócuo: arquivo válido, .bak intacto.
    assert gio.recuperar(p) is False
    assert bak.read_bytes() == conteudo_bak


def test_recuperar_arquivo_ausente_com_bak_valido(tmp_path):
    p = tmp_path / "perfil.json"
    (tmp_path / "perfil.json.bak").write_text('{"n": 3}\n', encoding="utf-8")
    assert gio.recuperar(p) is True
    assert gio.ler_json(p) == {"n": 3}


def test_recuperar_arquivo_valido_devolve_false(tmp_path):
    p = tmp_path / "registro.json"
    gio.escrever_json(p, {"v": 1})
    gio.escrever_json(p, {"v": 2})
    ino = p.stat().st_ino
    assert gio.recuperar(p) is False
    assert p.stat().st_ino == ino
    assert gio.ler_json(p) == {"v": 2}


# --------------------------------------------------------------------- Lock


def test_lock_adquirir_grava_pid_criado_em_run_id(tmp_path, agora_fixo, monkeypatch):
    monkeypatch.setenv("GP_RUN_ID", "run-teste-01")
    p = tmp_path / ".lock"
    lock = gio.Lock(p)
    lock.adquirir()
    try:
        assert lock.adquirido is True
        dados = json.loads(p.read_text(encoding="utf-8"))
        assert dados == {
            "pid": os.getpid(),
            "criado_em": "2026-09-28T10:00:00+00:00",
            "run_id": "run-teste-01",
        }
    finally:
        lock.liberar()
    assert not p.exists()
    assert lock.adquirido is False


def test_lock_adquirir_sem_run_id_grava_null(tmp_path, monkeypatch):
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    p = tmp_path / ".lock"
    with gio.Lock(p) as lock:
        assert lock.info()["run_id"] is None
        assert lock.info()["criado_em"].endswith("+00:00")


def test_lock_dois_processos_reais(tmp_path):
    p = tmp_path / ".lock"
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}

    # Processo A: adquire, avisa, segura até receber uma linha no stdin.
    script_a = PREAMBULO_SUBPROCESSO + textwrap.dedent(
        """
        lock = gio.Lock(%r)
        lock.adquirir()
        print("adquirido", flush=True)
        sys.stdin.readline()
        lock.liberar()
        print("liberado", flush=True)
        """
        % str(p)
    )
    # Processo B: tenta o Lock (GpErro) e o O_EXCL cru (EEXIST) e relata.
    script_b = PREAMBULO_SUBPROCESSO + textwrap.dedent(
        """
        import errno, json, os
        saida = {}
        try:
            gio.Lock(%r).adquirir()
            saida["lock"] = "adquiriu"
        except GpErro as e:
            saida["lock"] = "GpErro"
            saida["codigo"] = e.codigo
            saida["mensagem"] = e.mensagem
        try:
            os.open(%r, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            saida["excl"] = "criou"
        except FileExistsError as e:
            saida["excl"] = errno.errorcode[e.errno]
        print(json.dumps(saida), flush=True)
        """
        % (str(p), str(p))
    )

    a = subprocess.Popen(
        [sys.executable, "-c", script_a],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=ambiente,
    )
    try:
        linha = a.stdout.readline().strip()
        assert linha == "adquirido", a.stderr.read()
        pid_a = json.loads(p.read_text(encoding="utf-8"))["pid"]
        assert pid_a == a.pid

        b = subprocess.run(
            [sys.executable, "-c", script_b],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=ambiente,
            timeout=60,
        )
        assert b.returncode == 0, b.stderr
        saida = json.loads(b.stdout)
        assert saida["lock"] == "GpErro"
        assert saida["codigo"] == EXIT_IO
        assert re.fullmatch(r"lock preso há \d+ min \(pid %d\)" % a.pid, saida["mensagem"])
        assert saida["excl"] == "EEXIST"

        # O segundo processo não mexeu no lock do primeiro.
        assert json.loads(p.read_text(encoding="utf-8"))["pid"] == a.pid

        stdout_a, stderr_a = a.communicate("solta\n", timeout=60)
        assert a.returncode == 0, stderr_a
        assert stdout_a.strip().splitlines()[-1] == "liberado"
    finally:
        if a.poll() is None:
            a.kill()
            a.communicate()

    assert not p.exists()
    with gio.Lock(p) as lock:
        assert lock.info()["pid"] == os.getpid()


def test_lock_obsoleto_por_pid_morto(tmp_path, monkeypatch):
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    p = tmp_path / ".lock"
    _escrever_lock(p, _pid_morto(), datetime.now(timezone.utc), run_id="antigo")
    lock = gio.Lock(p)
    lock.adquirir()
    try:
        info = lock.info()
        assert info["pid"] == os.getpid()
        assert info["run_id"] is None
    finally:
        lock.liberar()
    assert not p.exists()


def test_lock_obsoleto_por_idade(tmp_path, agora_fixo):
    p = tmp_path / ".lock"
    agora = datetime.fromisoformat(agora_fixo)
    # Dono vivo (este processo), mas com 50 min pelo mtime: acima do padrão de 45.
    _escrever_lock(p, os.getpid(), agora - timedelta(minutes=50))
    _envelhecer(p, 50 * 60)
    assert gio.Lock(p).idade() == pytest.approx(50 * 60, abs=5)

    lock = gio.Lock(p)
    lock.adquirir()
    try:
        # criado_em segue o clock (informativo); a idade é real e recém-criada.
        assert lock.info()["criado_em"] == "2026-09-28T10:00:00+00:00"
        assert 0 <= lock.idade() < 5
    finally:
        lock.liberar()

    # Com obsoleto_s maior, o mesmo lock conta como preso.
    _escrever_lock(p, os.getpid(), agora - timedelta(minutes=50))
    _envelhecer(p, 50 * 60)
    with pytest.raises(GpErro) as exc:
        gio.Lock(p, obsoleto_s=60 * 60).adquirir()
    assert exc.value.mensagem == "lock preso há 50 min (pid %d)" % os.getpid()


def test_lock_vivo_nao_e_roubado_com_agora_fixado(tmp_path, monkeypatch):
    """--agora/GP_AGORA no futuro (golden run, depuração) não pode roubar o
    lock de um job vivo: a idade é pelo mtime, não pelo relógio simulado."""
    p = tmp_path / ".lock"
    _escrever_lock(p, os.getpid(), datetime.now(timezone.utc))
    monkeypatch.setenv("GP_AGORA", "2027-01-01T00:00:00+00:00")
    monkeypatch.setattr(clock, "_AGORA_FIXADO", None, raising=False)
    assert clock.agora().astimezone(timezone.utc).year == 2027
    assert gio.Lock(p).idade() < 5
    with pytest.raises(GpErro) as exc:
        gio.Lock(p).adquirir()
    assert exc.value.mensagem == "lock preso há 0 min (pid %d)" % os.getpid()
    assert json.loads(p.read_text(encoding="utf-8"))["pid"] == os.getpid()
    # Lock gravado por um processo com --agora no futuro tampouco fica "negativo" ou obsoleto.
    _escrever_lock(p, os.getpid(), datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert gio.Lock(p).idade() >= 0
    with pytest.raises(GpErro):
        gio.Lock(p).adquirir()


def test_lock_remover_obsoleto_nao_apaga_lock_trocado(tmp_path):
    """TOCTOU: entre julgar o lock obsoleto e apagá-lo, outro processo pode
    ter criado um lock novo no mesmo caminho; a remoção confere inode e mtime."""
    p = tmp_path / ".lock"
    _escrever_lock(p, _pid_morto(), datetime.now(timezone.utc))
    lock = gio.Lock(p)
    identidade = lock._obsoleto()
    assert identidade is not None
    # Outro processo "venceu": lock novo (inode e mtime diferentes) com dono vivo.
    p.unlink()
    _escrever_lock(p, os.getpid(), datetime.now(timezone.utc))
    assert lock._remover_obsoleto(identidade) is False
    assert json.loads(p.read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert sorted(f.name for f in tmp_path.iterdir()) == [".lock"]
    # E o lock novo é preso para quem tentar adquirir.
    with pytest.raises(GpErro):
        gio.Lock(p).adquirir()
    # Sem troca, a remoção acontece e não deixa o arquivo renomeado para trás.
    p.unlink()
    _escrever_lock(p, _pid_morto(), datetime.now(timezone.utc))
    identidade = lock._obsoleto()
    assert lock._remover_obsoleto(identidade) is True
    assert list(tmp_path.iterdir()) == []
    # Lock que sumiu no meio: False sem erro.
    assert lock._remover_obsoleto(identidade) is False


def test_lock_obsoleto_dois_processos_so_um_adquire(tmp_path):
    """Dois processos reais partem juntos sobre um lock obsoleto (pid morto,
    2 h de idade): exatamente um adquire; o outro vê o lock novo como preso."""
    p = tmp_path / ".lock"
    _escrever_lock(p, _pid_morto(), datetime.now(timezone.utc) - timedelta(hours=2))
    _envelhecer(p, 2 * 3600)
    largada = tmp_path / "largada"
    script = PREAMBULO_SUBPROCESSO + textwrap.dedent(
        """
        import json, os, time
        while not os.path.exists(%r):
            time.sleep(0.001)
        lock = gio.Lock(%r)
        try:
            lock.adquirir()
            print(json.dumps({"resultado": "adquiriu", "pid": os.getpid()}), flush=True)
            time.sleep(1.5)
            lock.liberar()
        except GpErro as e:
            print(json.dumps({"resultado": "GpErro", "mensagem": e.mensagem}), flush=True)
        """
        % (str(largada), str(p))
    )
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("GP_") or k == "GP_PLATAFORMA"}
    processos = [
        subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=ambiente,
        )
        for _ in range(2)
    ]
    try:
        time.sleep(0.5)  # os dois já esperam na largada
        largada.write_text("vai", encoding="utf-8")
        saidas = []
        for proc in processos:
            stdout, stderr = proc.communicate(timeout=60)
            assert proc.returncode == 0, stderr
            saidas.append(json.loads(stdout))
    finally:
        for proc in processos:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
    resultados = sorted(s["resultado"] for s in saidas)
    assert resultados == ["GpErro", "adquiriu"], saidas
    vencedor = next(s for s in saidas if s["resultado"] == "adquiriu")
    perdedor = next(s for s in saidas if s["resultado"] == "GpErro")
    # "pid ?" quando o perdedor leu o lock novo antes de o vencedor gravar o JSON.
    assert re.fullmatch(r"lock preso há 0 min \(pid (%d|\?)\)" % vencedor["pid"], perdedor["mensagem"])
    assert not p.exists()
    assert list(tmp_path.iterdir()) == [largada]


def test_lock_conteudo_ilegivel_recente_nao_e_roubado(tmp_path):
    p = tmp_path / ".lock"
    p.write_text("", encoding="utf-8")
    with pytest.raises(GpErro) as exc:
        gio.Lock(p).adquirir()
    assert exc.value.codigo == EXIT_IO
    assert p.read_text(encoding="utf-8") == ""


def test_lock_conteudo_ilegivel_antigo_e_removido(tmp_path):
    p = tmp_path / ".lock"
    p.write_text("lixo", encoding="utf-8")
    antigo = time.time() - gio.LOCK_GRACA_S - 60
    os.utime(p, (antigo, antigo))
    with gio.Lock(p) as lock:
        assert lock.info()["pid"] == os.getpid()


def test_lock_preso_espera_e_falha_com_mensagem(tmp_path):
    p = tmp_path / ".lock"
    _escrever_lock(p, os.getpid(), datetime.now(timezone.utc) - timedelta(minutes=3))
    _envelhecer(p, 3 * 60)
    lock = gio.Lock(p, espera_s=0.3, intervalo_s=0.05)
    inicio = time.monotonic()
    with pytest.raises(GpErro) as exc:
        lock.adquirir()
    decorrido = time.monotonic() - inicio
    assert decorrido >= 0.3
    assert exc.value.codigo == EXIT_IO
    assert exc.value.mensagem == "lock preso há 3 min (pid %d)" % os.getpid()
    assert lock.adquirido is False
    assert json.loads(p.read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_lock_espera_ate_o_dono_soltar(tmp_path, monkeypatch):
    p = tmp_path / ".lock"
    _escrever_lock(p, os.getpid(), datetime.now(timezone.utc))
    vezes = []

    def sleep_solta(s):
        # Simula o dono liberando durante o polling.
        vezes.append(s)
        p.unlink()

    monkeypatch.setattr(time, "sleep", sleep_solta)
    lock = gio.Lock(p, espera_s=5, intervalo_s=0.05)
    lock.adquirir()
    lock.liberar()
    assert vezes == [0.05]
    assert not p.exists()


def test_lock_liberar_so_do_proprio_pid(tmp_path):
    p = tmp_path / ".lock"
    _escrever_lock(p, os.getpid() + 1, datetime.now(timezone.utc))
    gio.Lock(p).liberar()
    assert p.exists()
    assert json.loads(p.read_text(encoding="utf-8"))["pid"] == os.getpid() + 1

    p.unlink()
    lock = gio.Lock(p)
    lock.adquirir()
    lock.liberar()
    assert not p.exists()
    lock.liberar()  # idempotente sem arquivo


def test_lock_with(tmp_path):
    p = tmp_path / ".lock"
    with gio.Lock(p) as lock:
        assert lock is not None
        assert lock.adquirido is True
        assert p.exists()
    assert not p.exists()
    assert lock.adquirido is False

    with pytest.raises(RuntimeError), gio.Lock(p):
        raise RuntimeError("dentro")
    assert not p.exists()


def test_lock_info_e_idade(tmp_path, agora_fixo, monkeypatch):
    monkeypatch.setenv("GP_RUN_ID", "r7")
    p = tmp_path / ".lock"
    lock = gio.Lock(p)
    assert lock.info() is None
    assert lock.idade() is None

    with lock:
        info = lock.info()
        assert info == {"pid": os.getpid(), "criado_em": "2026-09-28T10:00:00+00:00", "run_id": "r7"}
        assert 0 <= lock.idade() < 5

    # A idade vem do mtime: existe mesmo com conteúdo ilegível ou criado_em inválido.
    p.write_text("nao é json", encoding="utf-8")
    assert lock.info() is None
    assert 0 <= lock.idade() < 5

    p.write_text(json.dumps({"pid": 1, "criado_em": "ontem"}), encoding="utf-8")
    assert lock.info() == {"pid": 1, "criado_em": "ontem"}
    _envelhecer(p, 120)
    assert lock.idade() == pytest.approx(120, abs=5)


def test_pid_vivo_pid_impossivel(tmp_path, monkeypatch):
    monkeypatch.delenv("GP_RUN_ID", raising=False)
    assert gio._pid_vivo(2**40) is False
    assert gio._pid_vivo(os.getpid()) is True
    for ruim in (0, -1, True, "12", None, 1.5):
        assert gio._pid_vivo(ruim) is False
    # Um .lock corrompido com pid impossível conta como dono morto, não como traceback.
    p = tmp_path / ".lock"
    _escrever_lock(p, 2**40, datetime.now(timezone.utc))
    with gio.Lock(p) as lock:
        assert lock.info()["pid"] == os.getpid()


def test_lock_pasta_inexistente_erro_io(tmp_path):
    with pytest.raises(GpErro) as exc:
        gio.Lock(tmp_path / "nao" / "existe" / ".lock").adquirir()
    assert exc.value.codigo == EXIT_IO


def test_lock_no_windows_tenta_de_novo_quando_outro_processo_le_o_arquivo(monkeypatch):
    """Windows: rename/unlink de um arquivo aberto por outro processo dá PermissionError passageiro."""
    from goalpacer import processos

    tentativas = []

    def ocupado(*caminhos):
        tentativas.append(caminhos)
        if len(tentativas) < 3:
            raise PermissionError("[WinError 32] arquivo em uso")

    monkeypatch.setattr(gio, "PAUSA_WINDOWS_S", 0)
    monkeypatch.setattr(processos, "WINDOWS", True)
    gio._mexer(ocupado, "a", "b")
    assert tentativas == [("a", "b")] * 3

    def sempre(*_caminhos):
        raise PermissionError("em uso")

    with pytest.raises(PermissionError):
        gio._mexer(sempre, "a")
    monkeypatch.setattr(processos, "WINDOWS", False)
    tentativas.clear()
    with pytest.raises(PermissionError):
        gio._mexer(ocupado, "a")  # fora do Windows, sem nova tentativa
    assert len(tentativas) == 1
