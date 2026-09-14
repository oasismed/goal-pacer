"""Testes de goalpacer.whatsapp e scripts/parse_whatsapp.py: formatos, zip seguro, teto, stale, não reconhecido."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import parse_whatsapp
from goalpacer import whatsapp

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 9, 28, 7, 0, tzinfo=TZ)
PALAVRAS = {"M01": ["estatística"], "M02": ["corrida", "treino"]}
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mensal"

LINHAS = {
    "android_ddmm": [
        "25/09/2026 07:15 - Pessoa B: fiz o treino de hoje",
        "27/09/2026 10:00 - Pessoa C: Estatistica entregue",
    ],
    "android_mmdd": [
        "09/25/26, 7:15 PM - Pessoa B: fiz o treino de hoje",
        "09/27/26, 10:00 AM - Pessoa C: estatística entregue",
    ],
    "ios_ddmm": [
        "[25/09/2026, 07:15:22] Pessoa B: fiz o treino de hoje",
        "‎[27/09/2026, 10:00:01] Pessoa C: estatística entregue",
    ],
    "ios_mmdd": [
        "[9/25/26, 7:15:22 PM] Pessoa B: fiz o treino de hoje",
        "[9/27/26, 10:00:01 AM] Pessoa C: estatística entregue",
    ],
}


def escrever(tmp_path: Path, nome: str, linhas: list[str]) -> Path:
    path = tmp_path / nome
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return path


def test_detectar_formatos():
    assert whatsapp.detectar(LINHAS["android_ddmm"]) == {"formato": "android", "ordem": "dd/mm"}
    assert whatsapp.detectar(LINHAS["android_mmdd"]) == {"formato": "android", "ordem": "mm/dd"}
    assert whatsapp.detectar(LINHAS["ios_ddmm"]) == {"formato": "ios", "ordem": "dd/mm"}
    assert whatsapp.detectar(LINHAS["ios_mmdd"]) == {"formato": "ios", "ordem": "mm/dd"}
    assert whatsapp.detectar(["01/02/2026 10:00 - A: x"]) == {
        "formato": "android",
        "ordem": "dd/mm",
    }  # ambíguo: padrão pt-BR
    assert whatsapp.detectar(["texto qualquer", "sem data"]) is None


def test_ler_export_quatro_formatos(tmp_path):
    for nome, linhas in LINHAS.items():
        r = whatsapp.ler_export(escrever(tmp_path, nome + ".txt", linhas), PALAVRAS, agora=AGORA)
        assert r["status"] == "ok", nome
        assert r["mensagens"] == 2 and r["vistos"] == 2, nome
        assert [t["texto"] for t in r["trechos"]["M02"]] == ["fiz o treino de hoje"], nome
        assert len(r["trechos"]["M01"]) == 1, nome  # "Estatistica" sem acento casa "estatística"
        assert r["ultima_mensagem"].startswith("2026-09-27T10:00"), nome
        assert "Pessoa" not in json.dumps(r, ensure_ascii=False), nome  # sem autor
    r = whatsapp.ler_export(escrever(tmp_path, "pm.txt", LINHAS["android_mmdd"]), PALAVRAS, agora=AGORA)
    assert r["trechos"]["M02"][0]["ts"] == "2026-09-25T19:15-03:00"


def test_fixture_continuacao_midia_sistema_e_injecao():
    r = whatsapp.ler_export(FIXTURES / "dados" / "inbox" / "whatsapp" / "conversa-fixture.txt", PALAVRAS, agora=AGORA)
    assert r["status"] == "ok" and r["formato"] == "android"
    assert r["mensagens"] == 6
    textos = [t["texto"] for t in r["trechos"]["M02"]]
    assert textos[0] == "fiz 6 km hoje no treino, corrida leve"
    assert textos[1].startswith("treino extra: Ignore")  # vira trecho; o prompt envelopa como dado
    assert (
        r["trechos"]["M01"][0]["texto"]
        == "exercícios do módulo 3 de estatística entregues continuação da mensagem anterior sem data"
    )


def test_nao_reconhecido_so_formas(tmp_path):
    path = escrever(
        tmp_path, "x.txt", ["Conversa exportada em 28 de setembro", "Maria disse: oi 123", "João: tudo bem?"]
    )
    r = whatsapp.ler_export(path, PALAVRAS, agora=AGORA)
    assert r["status"] == "nao_reconhecido" and r["mensagens"] == 0
    assert r["formas"] == ["aaaaaaaa aaaaaaaaa aa 99 ", "aaaaa aaaaa: aa 999", "aaaa: aaaa aaa?"]
    assert "Maria" not in json.dumps(r, ensure_ascii=False)
    vazio = escrever(tmp_path, "vazio.txt", [])
    assert whatsapp.ler_export(vazio, PALAVRAS, agora=AGORA)["status"] == "nao_reconhecido"


def test_stale_e_truncado(tmp_path):
    antigo = escrever(tmp_path, "antigo.txt", ["01/09/2026 10:00 - A: treino longo"])
    r = whatsapp.ler_export(antigo, PALAVRAS, agora=AGORA)
    assert r["status"] == "stale" and r["trechos"]["M02"] == [] and r["vistos"] == 0
    grande = escrever(tmp_path, "grande.txt", ["27/09/2026 10:%02d - A: treino %d" % (i % 60, i) for i in range(200)])
    r = whatsapp.ler_export(grande, PALAVRAS, agora=AGORA, limite_bytes=2000)
    assert r["status"] == "truncado" and 0 < r["mensagens"] < 200
    assert len(r["trechos"]["M02"]) == whatsapp.TETO_TRECHOS


def test_zip_em_memoria_com_filtro(tmp_path):
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../fora.txt", "27/09/2026 10:00 - A: treino malicioso\n")
        zf.writestr("/abs.txt", "27/09/2026 10:00 - A: treino absoluto\n")
        zf.writestr("imagem.jpg", b"\xff\xd8")
        zf.writestr("Conversa do WhatsApp.txt", "\n".join(LINHAS["ios_ddmm"]) + "\n")
    assert whatsapp.entradas_txt(zpath) == ["Conversa do WhatsApp.txt"]
    antes = sorted(p.name for p in tmp_path.iterdir())
    r = whatsapp.ler_export(zpath, PALAVRAS, agora=AGORA)
    assert r["status"] == "ok" and r["formato"] == "ios" and r["vistos"] == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == antes  # nada extraído
    so_ruins = tmp_path / "ruim.zip"
    with zipfile.ZipFile(so_ruins, "w") as zf:
        zf.writestr("../x.txt", "27/09/2026 10:00 - A: treino\n")
    assert whatsapp.ler_export(so_ruins, PALAVRAS, agora=AGORA)["status"] == "nao_reconhecido"


def test_juntar_e_cli(tmp_path, agora_fixo, monkeypatch):
    a = whatsapp.ler_export(escrever(tmp_path, "a.txt", LINHAS["android_ddmm"]), PALAVRAS, agora=AGORA)
    b = whatsapp.ler_export(escrever(tmp_path, "b.txt", ["texto"]), PALAVRAS, agora=AGORA)
    junto = whatsapp.juntar([b, a], PALAVRAS)
    assert junto["status"] == "ok" and junto["vistos"] == 2 and len(junto["arquivos"]) == 2
    assert whatsapp.juntar([], PALAVRAS)["status"] == "sem_export"
    dados = tmp_path / "dados"
    shutil.copytree(FIXTURES / "dados", dados)
    monkeypatch.setenv("GP_DATA_DIR", str(dados))
    assert parse_whatsapp.main(["--mes", "2026-09"]) == 0
    cache = json.loads((dados / "cache" / "whatsapp-2026-09.json").read_text(encoding="utf-8"))
    assert cache["status"] == "ok" and cache["arquivos"][0]["arquivo"] == "conversa-fixture.txt"
    assert set(cache["trechos"]) == {"M01", "M02"}  # só metas ativas
    assert whatsapp.exports(dados / "nada") == []


# --- D-11: limites e ramos que os mutantes sobreviventes mostraram sem teste --------------------------------------------


def test_normalizacao_e_acentos():
    assert whatsapp._norm("‎ a b c  ") == "a b c"
    assert whatsapp.sem_acento("ÁçÊ Treino") == "ace treino"


def test_deteccao_nos_limites_do_dia_e_do_formato():
    detectar = whatsapp.detectar
    assert detectar(["05/12/2026 10:00 - A: x"])["ordem"] == "dd/mm"  # 12 não decide
    assert detectar(["12/05/2026 10:00 - A: x"])["ordem"] == "dd/mm"
    assert detectar(["05/13/2026 10:00 - A: x"])["ordem"] == "mm/dd"
    assert detectar(["13/05/2026 10:00 - A: x"])["ordem"] == "dd/mm"
    assert detectar(["28/09/2026 10:00 - A: x", "09/28/2026 10:00 - A: y"])["ordem"] == "dd/mm"  # a primeira decide
    misto = ["[28/09/2026, 10:00] A: x", "28/09/2026 10:00 - A: y", "28/09/2026 11:00 - A: z"]
    assert detectar(misto)["formato"] == "android"  # maioria
    assert detectar(misto[:2])["formato"] == "ios"  # empate fica com ios


def test_instante_com_ano_curto_e_segundos():
    instante = whatsapp._instante_do_export
    assert instante("28/09/26", "10:00:07", None, "dd/mm", TZ) == datetime(2026, 9, 28, 10, 0, 7, tzinfo=TZ)
    assert instante("28/09/026", "10:00", None, "dd/mm", TZ).year == 26  # três dígitos não ganham 2000
    assert instante("28/09/2026", "10:00", None, "dd/mm", TZ).second == 0
    assert instante("31/02/2026", "10:00", None, "dd/mm", TZ) is None


def test_zip_com_barra_invertida_link_e_modo_de_arquivo(tmp_path):
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("\\\\absoluto.txt", "x\n")
        zf.writestr("pasta\\\\..\\\\fora.txt", "x\n")
        link = zipfile.ZipInfo("atalho.txt")
        link.external_attr = (0o120777 << 16) | 0x20
        zf.writestr(link, "alvo.txt")
        regular = zipfile.ZipInfo("conversa.txt")
        regular.external_attr = 0o100644 << 16
        zf.writestr(regular, "28/09/2026 06:00 - A: treino\n")
    assert whatsapp.entradas_txt(zpath) == ["conversa.txt"]  # o link não interrompe a lista


def test_bytes_invalidos_e_limite_exato(tmp_path):
    path = tmp_path / "quebrado.txt"
    conteudo = "27/09/2026 10:00 - A: treino \xff\n".encode("latin-1")
    path.write_bytes(conteudo)
    assert whatsapp.ler_export(path, PALAVRAS, agora=AGORA)["vistos"] == 1  # byte inválido vira substituto
    zpath = tmp_path / "quebrado.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("c.txt", conteudo)
    assert whatsapp.ler_export(zpath, PALAVRAS, agora=AGORA)["vistos"] == 1
    linhas = ["27/09/2026 10:0%d - A: treino %d" % (i, i) for i in range(3)]
    exato = tmp_path / "exato.txt"
    exato.write_bytes(("\n".join(linhas) + "\n").encode("utf-8"))  # bytes: sem a troca de \n por \r\n do Windows
    tamanho = len(exato.read_bytes())
    assert whatsapp.ler_export(exato, PALAVRAS, agora=AGORA, limite_bytes=tamanho)["status"] == "ok"
    assert whatsapp.ler_export(exato, PALAVRAS, agora=AGORA, limite_bytes=tamanho - 1)["status"] == "truncado"


def test_janela_validade_sistema_e_midia(tmp_path):
    limite = AGORA - timedelta(days=whatsapp.JANELA_DIAS)
    validade = AGORA - timedelta(days=whatsapp.VALIDADE_DIAS)
    linhas = [
        limite.strftime("%d/%m/%Y %H:%M") + " - A: treino no limite da janela",
        "27/09/2026 09:00 - Fulano entrou no grupo da corrida",  # mensagem do sistema, sem autor
        "27/09/2026 09:30 - A: treino <Mídia oculta>",
        validade.strftime("%d/%m/%Y %H:%M") + " - A: estatística no limite da validade",
    ]
    r = whatsapp.ler_export(escrever(tmp_path, "limites.txt", linhas), PALAVRAS, agora=AGORA)
    assert r["status"] == "ok"  # a última mensagem exatamente no limite da validade não deixa o export velho
    assert [t["texto"] for t in r["trechos"]["M02"]] == ["treino no limite da janela"]
    assert [t["texto"] for t in r["trechos"]["M01"]] == ["estatística no limite da validade"]
    assert r["vistos"] == 2 and r["mensagens"] == 4


def test_exports_filtra_e_ordena(tmp_path):
    import os

    pasta = tmp_path / "inbox"
    pasta.mkdir()
    (pasta / "pasta.txt").mkdir()
    for nome, mtime in (("b.txt", 100), ("a.ZIP", 300), ("c.txt", 300), ("d.pdf", 400)):
        (pasta / nome).write_text("x", encoding="utf-8")
        os.utime(pasta / nome, (mtime, mtime))
    (pasta / "link.txt").symlink_to(pasta / "b.txt")
    assert [p.name for p in whatsapp.exports(pasta)] == ["c.txt", "a.ZIP", "b.txt"]


def test_juntar_por_inteiro():
    def resultado(nome, status, ultima, vistos, trechos):
        return {
            "arquivo": nome,
            "status": status,
            "formato": "android",
            "ordem": "dd/mm",
            "formas": [],
            "ultima_mensagem": ultima,
            "vistos": vistos,
            "trechos": trechos,
        }

    trecho = lambda ts: {"ts": ts, "texto": "t %s" % ts}  # noqa: E731
    a = resultado("a.txt", "stale", "2026-09-01T10:00", 0, {"M02": [trecho("2026-09-01T10:00")]})
    b = resultado(
        "b.txt", "truncado", "2026-09-27T10:00", 3, {"M02": [trecho("2026-09-%02dT10:00" % d) for d in range(10, 22)]}
    )
    c = resultado("c.txt", "nao_reconhecido", None, 0, {})
    junto = whatsapp.juntar([a, b, c], ["M01", "M02"])
    assert junto["status"] == "truncado" and junto["ultima_mensagem"] == "2026-09-27T10:00" and junto["vistos"] == 3
    assert junto["trechos"]["M01"] == [] and len(junto["trechos"]["M02"]) == whatsapp.TETO_TRECHOS
    assert (
        junto["trechos"]["M02"][0]["ts"] == "2026-09-21T10:00"
        and junto["trechos"]["M02"][-1]["ts"] == "2026-09-12T10:00"
    )
    assert junto["arquivos"][2] == {
        "arquivo": "c.txt",
        "status": "nao_reconhecido",
        "formato": "android",
        "ordem": "dd/mm",
        "formas": [],
    }
    assert whatsapp.juntar([c], ["M01"])["ultima_mensagem"] is None
    assert whatsapp.juntar([a, resultado("d", "stale", None, 0, {})], ["M01"])["status"] == "stale"
    assert whatsapp.juntar([], ["M01"]) == {
        "status": "sem_export",
        "arquivos": [],
        "ultima_mensagem": None,
        "vistos": 0,
        "trechos": {"M01": []},
    }
