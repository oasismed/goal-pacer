"""Leitura de exports do WhatsApp (CEO 2.4, 3.4; design "Integrações: WhatsApp").

Roda fora de qualquer sessão ``claude -p``. Formatos (primeiras 20 linhas)::

    ios      [28/09/2026, 14:03:22] Nome: texto      (colchetes; vírgula e segundos opcionais)
    android  28/09/2026 14:03 - Nome: texto          (hífen; vírgula opcional)
    ordem    dd/mm (padrão pt-BR) ou mm/dd: decide pelo primeiro campo > 12 (dd/mm) ou segundo > 12 (mm/dd)

Regras:

- ``.zip`` é aberto em memória; só entradas ``.txt`` cujo nome não tem
  componente ``..``, não é absoluto e não é link; nunca extrai nada.
- Lê linha a linha e para em ``LIMITE_BYTES`` (20 MB): ``status: truncado``.
- Formato não reconhecido: ``status: nao_reconhecido`` e só a FORMA das 3
  primeiras linhas (dígito vira 9, letra vira a), nunca o texto.
- Última mensagem com mais de ``VALIDADE_DIAS`` (7): ``status: stale``, sem trechos.
- Trechos: mensagens dos últimos ``JANELA_DIAS`` (30) com alguma palavra-chave
  da meta (sem acento, sem caixa), sem autor, até ``TETO_TRECHOS`` por meta e
  ``TETO_CHARS`` caracteres cada. Ficam só em ``cache/whatsapp-AAAA-MM.json``
  e são apagados logo depois do ``mensal-ler``.
"""

from __future__ import annotations

import io as stdio
import re
import unicodedata
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Optional

LIMITE_BYTES = 20 * 1024 * 1024
LINHAS_DETECCAO = 20
VALIDADE_DIAS = 7
JANELA_DIAS = 30
TETO_TRECHOS = 10
TETO_CHARS = 280
MARCA_LTR = "‎"

RE_IOS = re.compile(
    r"^\[(?P<d>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<h>\d{1,2}:\d{2}(?::\d{2})?)(?:\s?(?P<ampm>[AaPp]\.?\s?[Mm]\.?))?\]\s?(?P<resto>.*)$"
)
RE_ANDROID = re.compile(
    r"^(?P<d>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<h>\d{1,2}:\d{2}(?::\d{2})?)(?:\s?(?P<ampm>[AaPp]\.?\s?[Mm]\.?))?\s+-\s+(?P<resto>.*)$"
)
MIDIA = (
    "<mídia oculta>",
    "<midia oculta>",
    "imagem ocultada",
    "vídeo omitido",
    "video omitido",
    "figurinha omitida",
    "áudio ocultado",
    "audio ocultado",
    "(arquivo anexado)",
    "documento omitido",
    "gif omitido",
    "<media omitted>",
)


def _norm(texto: str) -> str:
    return unicodedata.normalize("NFC", texto.replace(MARCA_LTR, "").replace(" ", " ").replace(" ", " ")).strip()


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def forma(linha: str) -> str:
    """Forma de uma linha sem o conteúdo: dígito → 9, letra → a (só os 25 primeiros caracteres)."""
    saida = []
    for c in linha[:25]:
        if c.isdigit():
            saida.append("9")
        elif c.isalpha():
            saida.append("a")
        else:
            saida.append(c)
    return "".join(saida)


def detectar(linhas: list[str]) -> Optional[dict[str, str]]:
    """``{"formato": "ios"|"android", "ordem": "dd/mm"|"mm/dd"}`` ou None."""
    contagem = {"ios": 0, "android": 0}
    ordem = None
    for linha_bruta in linhas[:LINHAS_DETECCAO]:
        linha = _norm(linha_bruta)
        for nome, regex in (("ios", RE_IOS), ("android", RE_ANDROID)):
            m = regex.match(linha)
            if not m:
                continue
            contagem[nome] += 1
            a, b, _ = m.group("d").split("/")
            if ordem is None and int(a) > 12:
                ordem = "dd/mm"
            elif ordem is None and int(b) > 12:
                ordem = "mm/dd"
    if not any(contagem.values()):
        return None
    formato = "ios" if contagem["ios"] >= contagem["android"] else "android"
    return {"formato": formato, "ordem": ordem or "dd/mm"}


def _instante_do_export(data: str, hora: str, ampm: Optional[str], ordem: str, tz) -> Optional[datetime]:
    try:
        a, b, ano = data.split("/")
        dia, mes = (int(a), int(b)) if ordem == "dd/mm" else (int(b), int(a))
        ano_int = int(ano) + (2000 if len(ano) <= 2 else 0)
        partes = [int(p) for p in hora.split(":")]
        horas, minutos = partes[0], partes[1]
        segundos = partes[2] if len(partes) > 2 else 0
        if ampm:
            pm = ampm.lower().startswith("p")
            horas = (horas % 12) + (12 if pm else 0)
        return datetime.combine(date(ano_int, mes, dia), time(horas, minutos, segundos), tzinfo=tz)
    except (ValueError, IndexError):
        return None


def entradas_txt(path: Path) -> list[str]:
    """Nomes das entradas ``.txt`` seguras de um zip (sem ``..``, sem absoluto, sem link)."""
    seguras = []
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            nome = info.filename
            partes = PurePosixPath(nome.replace("\\", "/")).parts
            if not nome.lower().endswith(".txt") or nome.startswith(("/", "\\")) or ".." in partes or info.is_dir():
                continue
            modo = (info.external_attr >> 16) & 0o170000
            if modo == 0o120000:
                continue
            seguras.append(nome)
    return seguras


def _linhas_do_arquivo(path: Path) -> Iterator[tuple[str, int]]:
    """``(linha, bytes)`` de um .txt ou do primeiro .txt seguro de um .zip, sem extrair."""
    if path.suffix.lower() == ".zip":
        nomes = entradas_txt(path)
        if not nomes:
            return
        with zipfile.ZipFile(path) as zf, zf.open(nomes[0]) as bruto:
            for linha in stdio.TextIOWrapper(bruto, encoding="utf-8", errors="replace"):
                yield linha, len(linha.encode("utf-8"))
        return
    with open(path, encoding="utf-8", errors="replace") as arquivo:
        for linha in arquivo:
            yield linha, len(linha.encode("utf-8"))


def ler_export(
    path: Path,
    palavras_por_meta: dict[str, list[str]],
    *,
    agora: datetime,
    limite_bytes: int = LIMITE_BYTES,
) -> dict[str, Any]:
    """Resultado do export (ver docstring do módulo)."""
    leitura = _Leitura(palavras_por_meta, agora)
    lidos = 0
    for linha, tamanho in _linhas_do_arquivo(path):
        lidos += tamanho
        if lidos > limite_bytes:
            leitura.resultado["status"] = "truncado"
            break
        if not leitura.alimentar(linha):
            break
    if leitura.deteccao is None and leitura.primeiras:
        leitura.detectar()
    leitura.fechar(leitura.atual)
    return _serializar(leitura.concluir(path.name))


class _Leitura:
    """Uma leitura do export: formato detectado nas primeiras linhas com texto, mensagem corrente (as linhas sem
    data continuam a anterior) e os trechos por meta dentro da janela."""

    def __init__(self, palavras_por_meta: dict[str, list[str]], agora: datetime) -> None:
        self.agora = agora
        self.tz = agora.tzinfo
        self.metas = list(palavras_por_meta)
        self.chaves = {m: [sem_acento(p) for p in ps if p.strip()] for m, ps in palavras_por_meta.items()}
        self.limite_trechos = agora - timedelta(days=JANELA_DIAS)
        self.primeiras: list[str] = []
        self.deteccao: Optional[dict[str, str]] = None
        self.atual: Optional[dict[str, Any]] = None
        self.resultado: dict[str, Any] = {
            "status": "ok",
            "formato": None,
            "ordem": None,
            "ultima_mensagem": None,
            "mensagens": 0,
            "vistos": 0,
            "trechos": {m: [] for m in self.metas},
            "formas": [],
        }

    def alimentar(self, linha: str) -> bool:
        """Processa uma linha; ``False`` quando as primeiras linhas não têm formato conhecido (a leitura para)."""
        if self.deteccao is not None:
            self.atual = _processar(linha.rstrip("\r\n"), self.deteccao, self.tz, self.atual, self.fechar)
            return True
        if linha.strip():
            self.primeiras.append(linha.rstrip("\r\n"))
        return len(self.primeiras) < LINHAS_DETECCAO or self.detectar()

    def detectar(self) -> bool:
        self.deteccao = detectar(self.primeiras)
        if self.deteccao is None:
            return False
        self.resultado.update(self.deteccao)
        for guardada in self.primeiras:
            self.atual = _processar(guardada, self.deteccao, self.tz, self.atual, self.fechar)
        return True

    def fechar(self, msg: Optional[dict[str, Any]]) -> None:
        if msg is None:
            return
        self.resultado["mensagens"] += 1
        if self.resultado["ultima_mensagem"] is None or msg["ts"] > self.resultado["ultima_mensagem"]:
            self.resultado["ultima_mensagem"] = msg["ts"]
        if msg["ts"] < self.limite_trechos or not msg["texto"] or msg["sistema"]:
            return
        if any(m in msg["texto"].lower() for m in MIDIA):
            return
        normal = sem_acento(msg["texto"])
        casadas = [meta_id for meta_id, palavras in self.chaves.items() if any(p in normal for p in palavras)]
        for meta_id in casadas:
            lista = self.resultado["trechos"][meta_id]
            if len(lista) < TETO_TRECHOS:
                texto = " ".join(msg["texto"].split())
                lista.append({"ts": msg["ts"].isoformat(timespec="minutes"), "texto": texto[:TETO_CHARS]})
        if casadas:
            self.resultado["vistos"] += 1

    def concluir(self, arquivo: str) -> dict[str, Any]:
        """Não reconhecido guarda só a forma das 3 primeiras linhas; export velho não entrega trechos."""
        resultado: dict[str, Any] = {"arquivo": arquivo, **self.resultado}
        if self.deteccao is None:
            resultado.update(
                status="nao_reconhecido",
                formas=[forma(_norm(l)) for l in self.primeiras[:3]],
                trechos={m: [] for m in self.metas},
            )
            return resultado
        ultima = resultado["ultima_mensagem"]
        if resultado["status"] == "ok" and (ultima is None or ultima < self.agora - timedelta(days=VALIDADE_DIAS)):
            resultado.update(status="stale", trechos={m: [] for m in self.metas}, vistos=0)
        return resultado


def _processar(
    linha: str, deteccao: dict[str, str], tz, atual: Optional[dict[str, Any]], fechar
) -> Optional[dict[str, Any]]:
    normal = _norm(linha)
    if not normal:
        return atual
    regex = RE_IOS if deteccao["formato"] == "ios" else RE_ANDROID
    m = regex.match(normal) or (RE_ANDROID if regex is RE_IOS else RE_IOS).match(normal)
    if m:
        instante = _instante_do_export(m.group("d"), m.group("h"), m.group("ampm"), deteccao["ordem"], tz)
        if instante is None:
            return atual
        fechar(atual)
        resto = m.group("resto")
        if ": " in resto:
            return {"ts": instante, "texto": resto.split(": ", 1)[1], "sistema": False}
        return {"ts": instante, "texto": resto, "sistema": True}
    if atual is not None:
        atual["texto"] += " " + normal
    return atual


def _serializar(resultado: dict[str, Any]) -> dict[str, Any]:
    if isinstance(resultado.get("ultima_mensagem"), datetime):
        resultado["ultima_mensagem"] = resultado["ultima_mensagem"].isoformat(timespec="minutes")
    return resultado


def exports(pasta: Path) -> list[Path]:
    """Exports em ``inbox/whatsapp/`` (``.txt``/``.zip``), mais recente primeiro, sem links."""
    if not pasta.is_dir():
        return []
    arquivos = [
        p for p in pasta.iterdir() if p.suffix.lower() in (".txt", ".zip") and p.is_file() and not p.is_symlink()
    ]
    return sorted(arquivos, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def juntar(resultados: Iterable[dict[str, Any]], metas: Iterable[str]) -> dict[str, Any]:
    """Vários exports num resultado só (status do melhor, trechos somados até o teto)."""
    lista = list(resultados)
    metas = list(metas)
    if not lista:
        return {
            "status": "sem_export",
            "arquivos": [],
            "ultima_mensagem": None,
            "vistos": 0,
            "trechos": {m: [] for m in metas},
        }
    ordem_status = ("ok", "truncado", "stale", "nao_reconhecido")
    status = min((r["status"] for r in lista), key=ordem_status.index)
    trechos = {
        meta_id: sorted((t for r in lista for t in r["trechos"].get(meta_id, [])), key=lambda t: t["ts"], reverse=True)[
            :TETO_TRECHOS
        ]
        for meta_id in metas
    }
    ultimas = [r["ultima_mensagem"] for r in lista if r.get("ultima_mensagem")]
    return {
        "status": status,
        "arquivos": [
            {
                "arquivo": r["arquivo"],
                "status": r["status"],
                "formato": r["formato"],
                "ordem": r["ordem"],
                "formas": r["formas"],
            }
            for r in lista
        ],
        "ultima_mensagem": max(ultimas) if ultimas else None,
        "vistos": sum(r["vistos"] for r in lista),
        "trechos": trechos,
    }
