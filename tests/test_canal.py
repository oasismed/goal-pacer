"""goalpacer/canal.py e o aviso de versão nova: ``release/canal``, ``ultima.json`` assinado, teto de download e a
pergunta de uma vez por dia (acoes_locais.versao_nova). Rede nunca: o canal é um dicionário servido em memória."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import acoes_locais
from goalpacer import assinatura, base, canal
from goalpacer.base import GpErro

tem_ssh_keygen = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="sem ssh-keygen")
BASE = "https://versoes.exemplo.test/goal-pacer/"


class _Resposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def servidor(arquivos: dict[str, bytes]):
    pedidos: list[str] = []

    def abrir(url, timeout):
        pedidos.append(url)
        nome = url[len(BASE) :]
        if nome not in arquivos:
            raise OSError("404 %s" % nome)
        return _Resposta(arquivos[nome])

    return abrir, pedidos


def _app(tmp_path: Path, versao: str = "0.4.1", endereco: str = BASE) -> tuple[Path, Path]:
    app = tmp_path / "app"
    (app / "release").mkdir(parents=True)
    (app / "scripts" / "goalpacer").mkdir(parents=True)
    (app / "scripts" / "goalpacer" / "base.py").write_text('VERSAO_APP = "%s"\n' % versao, encoding="utf-8")
    (app / "release" / "canal").write_text(endereco + "\n", encoding="utf-8")
    chave = tmp_path / "chave"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(chave)], check=True, capture_output=True)
    tipo, publica = Path(str(chave) + ".pub").read_text(encoding="utf-8").split()[:2]
    (app / "release" / "assinantes").write_text(
        'p@x.test namespaces="goal-pacer-release" %s %s\n' % (tipo, publica), encoding="utf-8"
    )
    return app, chave


def _assinado(tmp_path: Path, chave: Path, nome: str, dados: bytes) -> tuple[bytes, bytes]:
    arquivo = tmp_path / nome
    arquivo.write_bytes(dados)
    subprocess.run(
        ["ssh-keygen", "-q", "-Y", "sign", "-f", str(chave), "-n", assinatura.ESPACO_ZIP, str(arquivo)],
        check=True,
        capture_output=True,
    )
    return dados, Path(str(arquivo) + ".sig").read_bytes()


def test_endereco_so_com_https(tmp_path):
    app = tmp_path / "app"
    assert canal.endereco(app) is None
    (app / "release").mkdir(parents=True)
    for texto, esperado in (
        ("", None),
        ("http://inseguro.test", None),
        ("https://a.test/x", "https://a.test/x/"),
        ("https://a b", None),
    ):
        (app / "release" / "canal").write_text(texto, encoding="utf-8")
        assert canal.endereco(app) == esperado


@tem_ssh_keygen
def test_ultima_conferida_e_zip_baixado(tmp_path):
    app, chave = _app(tmp_path)
    ultima, selo = _assinado(
        tmp_path, chave, "ultima.json", json.dumps({"versao": "0.5.0", "zip": "goal-pacer-v0.5.0.zip"}).encode()
    )
    abrir, pedidos = servidor(
        {
            "ultima.json": ultima,
            "ultima.json.sig": selo,
            "goal-pacer-v0.5.0.zip": b"zip",
            "goal-pacer-v0.5.0.zip.sig": b"sig",
        }
    )
    pasta = tmp_path / "baixados"
    pasta.mkdir()
    dados = canal.ultima(app, pasta, abrir=abrir)
    assert dados["versao_tupla"] == (0, 5, 0) and pedidos == [BASE + "ultima.json", BASE + "ultima.json.sig"]
    zip_baixado = canal.baixar_zip(app, dados, pasta, abrir=abrir)
    assert zip_baixado.read_bytes() == b"zip" and (pasta / "goal-pacer-v0.5.0.zip.sig").read_bytes() == b"sig"
    trocado = {"ultima.json": ultima.replace(b"0.5.0", b"9.9.9"), "ultima.json.sig": selo}
    outra = tmp_path / "outra"
    outra.mkdir()
    with pytest.raises(GpErro, match="não confere"):
        canal.ultima(app, outra, abrir=servidor(trocado)[0])
    with pytest.raises(GpErro, match="não consegui baixar"):
        canal.ultima(app, tmp_path / "vazia-inexistente", abrir=servidor({})[0])
    grande = tmp_path / "grande"
    grande.mkdir()
    with pytest.raises(GpErro, match="passou de"):
        canal.baixar(BASE + "x", grande / "x", 10, abrir=servidor({"x": b"0" * 11})[0])


@tem_ssh_keygen
def test_ultima_fora_do_formato(tmp_path):
    app, chave = _app(tmp_path)
    for i, corpo in enumerate(
        (
            b"nao json",
            json.dumps({"versao": "0.5", "zip": "a.zip"}).encode(),
            json.dumps({"versao": "0.5.0", "zip": "../a.zip"}).encode(),
        )
    ):
        dados, selo = _assinado(tmp_path, chave, "u%d.json" % i, corpo)
        pasta = tmp_path / ("p%d" % i)
        pasta.mkdir()
        with pytest.raises(GpErro, match=r"ultima\.json do canal"):
            canal.ultima(app, pasta, abrir=servidor({"ultima.json": dados, "ultima.json.sig": selo})[0])


@tem_ssh_keygen
def test_versao_nova_pergunta_uma_vez_por_dia(tmp_path, monkeypatch, agora_fixo):
    app, chave = _app(tmp_path)
    monkeypatch.setenv("GP_RAIZ", str(tmp_path / "raiz"))
    monkeypatch.setattr(acoes_locais, "_instalacao", lambda: {"app": str(app), "modo": "copia"})
    ultima, selo = _assinado(tmp_path, chave, "ultima.json", json.dumps({"versao": "0.5.0", "zip": "g.zip"}).encode())
    abrir, pedidos = servidor({"ultima.json": ultima, "ultima.json.sig": selo})
    base.jobs_dir().mkdir(parents=True)
    assert acoes_locais.versao_nova(abrir=abrir) == "0.5.0"
    assert (
        acoes_locais.versao_nova(abrir=abrir) == "0.5.0" and len(pedidos) == 2
    )  # a segunda vez vem do jobs/canal.json
    (app / "scripts" / "goalpacer" / "base.py").write_text('VERSAO_APP = "0.5.0"\n', encoding="utf-8")
    assert acoes_locais.versao_nova(abrir=abrir) is None  # já instalada
    (base.jobs_dir() / acoes_locais.NOME_CANAL).unlink()
    assert acoes_locais.versao_nova(abrir=servidor({})[0]) is None  # sem rede: nada, sem erro
    (app / "release" / "canal").unlink()
    assert acoes_locais.versao_nova(abrir=abrir) is None
