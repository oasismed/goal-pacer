#!/usr/bin/env python3
"""validar.py grafo | cache <arquivo> | ops <arquivo>: valida a pasta de dados.

Códigos de saída (goalpacer.base): 0 ok (pode haver avisos); 2 estado
esperado (``sem_onboarding``: sem contexto.md ou sem metas/M<nn>.md;
``sem_meta_ativa``: nenhuma meta com ``estado: ativa``); 3 inválido
(front-matter, esquema, ``schema_version`` diferente: "rode install.sh
--update"); 4 IO (registro.json corrompido sem .bak que o salve, pasta
inexistente).

``grafo`` lê DATA_DIR inteira: contexto.md, metas/, registro.json (se
existir; JSON corrompido tenta ``io.recuperar`` e avisa), planos/*.md e
dias/*.md (front-matter e blocos ``### D-...`` validados como ``task``);
referência a meta inexistente é AVISO (exit 0), como manda o achado 4.1.
Plano com números alterados fora do balanço (``hash_numeros`` diferente
do corpo sem prosa, achado 2.5) é erro; ``sinais/*.md`` têm o front-matter
validado (esquema ``sinais``).

``cache`` valida um ``cache/calendar-*.json`` compacto (esquema
``cache_calendar``: summary/description nulos fora do Metas, gp_key,
datas); ``ops`` valida um ``cache/ops-*.json`` (esquema ``ops``; sem
``--planejadas``, op sem status conta como falha, achado 2.3).

Saída humana em stderr, uma linha por problema (``<arquivo>: <campo>:
<motivo>``); ``--json`` grava em stdout ``{ok, codigo, estado, erros,
avisos}``. Nunca imprime conteúdo de terceiros (só nomes de campo e ids).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import base, cli, clock, copy, frontmatter, io as gpio, schema
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_VALIDACAO, GpErro

ESTADO_SEM_ONBOARDING = "sem_onboarding"
ESTADO_SEM_META_ATIVA = "sem_meta_ativa"
ESTADO_SCHEMA = "schema_mismatch"
ESTADO_REGISTRO = "registro_corrompido"
MENSAGEM_ONBOARDING = "rode /goal-pacer onboarding"
MENSAGEM_UPDATE = "rode install.sh --update"
SUFIXO_MD = ".md"


class Resultado:
    """Acumula erros e avisos; ``codigo`` e ``estado`` saem de ``fechar``."""

    def __init__(self) -> None:
        self.erros: list[str] = []
        self.avisos: list[str] = []
        self.estado: Optional[str] = None
        self.codigo_forcado: Optional[int] = None

    def erro(self, arquivo: str, texto: str) -> None:
        self.erros.append("%s: %s" % (arquivo, texto))

    def erros_de(self, arquivo: str, lista: list[str]) -> None:
        for texto in lista:
            self.erro(arquivo, texto)

    def aviso(self, arquivo: str, texto: str) -> None:
        self.avisos.append("%s: %s" % (arquivo, texto))

    def estado_esperado(self, estado: str, mensagem: str) -> None:
        """Estado de exit 2 (só vale se não houver erro de validação)."""
        if self.estado is None:
            self.estado = estado
            self.avisos.append("%s: %s" % (estado, mensagem))

    @property
    def codigo(self) -> int:
        if self.codigo_forcado is not None:
            return self.codigo_forcado
        if self.erros:
            return EXIT_VALIDACAO
        if self.estado in (ESTADO_SEM_ONBOARDING, ESTADO_SEM_META_ATIVA):
            return EXIT_ESTADO
        return EXIT_OK

    def como_dict(self) -> dict[str, Any]:
        return {
            "ok": self.codigo == EXIT_OK,
            "codigo": self.codigo,
            "estado": self.estado,
            "erros": list(self.erros),
            "avisos": list(self.avisos),
        }


# --- leitura de arquivos --------------------------------------------------


def _relativo(path: Path, dados: Path) -> str:
    try:
        return path.relative_to(dados).as_posix()  # o mesmo texto em qualquer sistema
    except ValueError:
        return str(path)


def _ler_markdown(
    path: Path, arquivo_esquema: str, rotulo: str, r: Resultado, *, checar_versao: bool = False
) -> Optional[tuple[dict[str, Any], str]]:
    """Front-matter coagido e validado contra ``ESQUEMAS[arquivo_esquema]`` +
    corpo; None se inválido. Com ``checar_versao``, ``schema_version``
    diferente vira o erro "rode install.sh --update" (estado
    ``schema_mismatch``) e o resto não é validado."""
    try:
        bruto, corpo = frontmatter.ler_arquivo(path)
    except frontmatter.ErroFrontmatter as erro:
        r.erro(rotulo, "linha %d: %s" % (erro.linha, erro.motivo))
        return None
    except GpErro as erro:
        r.erro(rotulo, erro.mensagem)
        return None
    coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS[arquivo_esquema])
    if checar_versao and coagido.get("schema_version") != schema.SCHEMA_VERSION:
        _checar_schema_version(coagido, rotulo, r)
        return None
    if erros:
        r.erros_de(rotulo, erros)
        return None
    erros = schema.validar_registro(arquivo_esquema, coagido)
    if erros:
        r.erros_de(rotulo, erros)
        return None
    return coagido, corpo


def _ler_json(path: Path, rotulo: str, r: Resultado) -> Optional[Any]:
    try:
        return gpio.ler_json(path)
    except GpErro as erro:
        r.erro(rotulo, erro.mensagem)
        return None


def _checar_schema_version(dados: dict[str, Any], rotulo: str, r: Resultado) -> None:
    versao = dados.get("schema_version")
    if versao != schema.SCHEMA_VERSION:
        r.estado = ESTADO_SCHEMA
        r.erro(rotulo, "schema_version: esperado %d, veio %r; %s" % (schema.SCHEMA_VERSION, versao, MENSAGEM_UPDATE))


# --- grafo ----------------------------------------------------------------


def _ler_contexto(dados: Path, r: Resultado) -> Optional[dict[str, Any]]:
    path = dados / schema.CAMINHOS["contexto"]
    rotulo = _relativo(path, dados)
    lido = _ler_markdown(path, "contexto", rotulo, r, checar_versao=True)
    if lido is None:
        return None
    contexto, _ = lido
    try:
        clock.fuso(contexto["timezone"])
    except GpErro as erro:
        r.erro(rotulo, "timezone: %s" % erro.mensagem)
    if contexto.get("idioma") and contexto["idioma"] not in copy.disponiveis():
        r.aviso(
            rotulo,
            "idioma: %r sem references/copy.%s.md; as superfícies saem em %s"
            % (contexto["idioma"], contexto["idioma"], copy.IDIOMA_PADRAO),
        )
    _conferir_conectores(contexto, rotulo, r)
    return contexto


def _conferir_conectores(contexto: dict[str, Any], rotulo: str, r: Resultado) -> None:
    """Calendar e Gmail são opcionais, mas coerentes: Metas e primário vêm juntos e separados; a fonte gmail precisa
    do e-mail próprio para a busca não achar os emails do próprio app."""
    metas, primario = (str(contexto.get(nome) or "").strip() for nome in ("calendar_id_metas", "calendar_id_primario"))
    if bool(metas) != bool(primario):
        r.erro(
            rotulo,
            "%s: vazio (Metas e primário vêm juntos)" % ("calendar_id_primario" if metas else "calendar_id_metas"),
        )
    if metas and metas == primario:
        r.erro(rotulo, "calendar_id_metas: igual ao primário (o Metas precisa ser um calendário separado)")
    if "gmail" in (contexto.get("fontes_ativas") or []) and not str(contexto.get("email_proprio") or "").strip():
        r.erro(rotulo, "email_proprio: vazio (a fonte gmail precisa dele)")


def _registros_da_pasta(
    dados: Path, pasta: str, tipo_id: str, esquema: str, esperado: str, r: Resultado
) -> Iterator[dict[str, Any]]:
    """Os registros válidos de ``<pasta>/<id>.md`` cujo ``id`` é o nome do arquivo; erros vão para ``r``."""
    caminho = dados / pasta
    for path in sorted(caminho.glob("*")) if caminho.is_dir() else []:
        rotulo = _relativo(path, dados)
        if path.name.startswith(".") or path.is_dir() or path.name.endswith(gpio.SUFIXO_BAK):
            continue  # .bak é a cópia da escrita atômica anterior (io.escrever_atomico)
        if path.suffix != SUFIXO_MD or not schema.validar_id(tipo_id, path.stem):
            r.erro(rotulo, "nome de arquivo inválido (esperado %s)" % esperado)
            continue
        lido = _ler_markdown(path, esquema, rotulo, r)
        if lido is not None and lido[0]["id"] != path.stem:
            r.erro(rotulo, "id: %r difere do nome do arquivo" % lido[0]["id"])
        elif lido is not None:
            yield lido[0]


def _ler_metas(dados: Path, r: Resultado) -> dict[str, dict[str, Any]]:
    """``id → meta`` das metas válidas; erros vão para ``r``."""
    return {meta["id"]: meta for meta in _registros_da_pasta(dados, "metas", "meta", "metas", "M<nn>.md", r)}


def _validar_objetivos(dados: Path, metas: dict[str, dict[str, Any]], r: Resultado) -> None:
    """objetivos/O<nn>.md válidos; meta apontando para objetivo inexistente é aviso (vira objetivo implícito)."""
    ids = {o["id"] for o in _registros_da_pasta(dados, "objetivos", "objetivo", "objetivo", "O<nn>.md", r)}
    for meta_id, meta in sorted(metas.items()):
        if meta.get("objetivo") and meta["objetivo"] not in ids:
            r.aviso(
                "metas/%s.md" % meta_id,
                "objetivo %s sem objetivos/%s.md (a meta vira objetivo implícito)"
                % (meta["objetivo"], meta["objetivo"]),
            )


def _tem_arquivos_de_meta(dados: Path) -> bool:
    pasta = dados / "metas"
    return pasta.is_dir() and any(p.suffix == SUFIXO_MD and not p.name.startswith(".") for p in pasta.iterdir())


def _ler_registro(dados: Path, r: Resultado) -> Optional[dict[str, Any]]:
    path = dados / schema.CAMINHOS["registro"]
    rotulo = _relativo(path, dados)
    if not path.exists():
        return None
    try:
        registro = gpio.ler_json(path)
    except GpErro:
        if gpio.recuperar(path):
            r.aviso(rotulo, "JSON corrompido; restaurado do .bak")
            try:
                registro = gpio.ler_json(path)
            except GpErro as erro:
                r.codigo_forcado = EXIT_IO
                r.estado = ESTADO_REGISTRO
                r.erro(rotulo, "corrompido mesmo após restaurar: %s" % erro.mensagem)
                return None
        else:
            r.codigo_forcado = EXIT_IO
            r.estado = ESTADO_REGISTRO
            r.erro(rotulo, "JSON corrompido e sem .bak válido; rode registro.py --recuperar")
            return None
    if not isinstance(registro, dict):
        r.erro(rotulo, "esperado objeto JSON")
        return None
    if registro.get("schema_version") != schema.SCHEMA_VERSION:
        _checar_schema_version(registro, rotulo, r)
        return None
    r.erros_de(rotulo, schema.validar_registro("registro", registro))
    _conferir_feitas_e_checkins(dados, rotulo, r)
    return registro


def _conferir_feitas_e_checkins(dados: Path, rotulo: str, r: Resultado) -> None:
    """``feitas`` (horas) e ``checkins`` (estado) andam juntos; divergência muda a demanda do mês sem aviso (R7)."""
    from goalpacer import registro as reg

    try:
        registro = reg.carregar(dados)  # com os arquivos anuais: um par pode ter ido para registro-AAAA.json
    except GpErro:
        return
    checkins = registro.get("checkins", {})
    horas = {item.get("task_id") for lista in registro.get("feitas", {}).values() for item in lista}
    for task_id in sorted(t for t in horas if checkins.get(t, {}).get("estado") != "feita"):
        r.aviso(
            rotulo,
            "feitas tem %s, mas o check-in do bloco não está feita (%s); a demanda do mês conta horas que o estado não confirma"
            % (task_id, checkins.get(task_id, {}).get("estado", "sem check-in")),
        )
    for task_id in sorted(t for t, c in checkins.items() if c.get("estado") == "feita" and t not in horas):
        r.aviso(
            rotulo,
            "o check-in de %s está feita, mas o bloco não está em feitas; as horas dele não entram na demanda"
            % task_id,
        )


def _ids_de_meta_no_texto(texto: str) -> set[str]:
    """Ids ``M<nn>`` nas subseções ``### M<nn>`` de um plano."""
    ids = set()
    for linha in texto.split("\n"):
        m = schema.RE_SUBSECAO_META.match(linha.rstrip("\r"))
        if m:
            ids.add(m.group(1))
    return ids


def _validar_planos(dados: Path, metas: dict[str, dict[str, Any]], r: Resultado) -> None:
    pasta = dados / "planos"
    if not pasta.is_dir():
        return
    for path in sorted(pasta.glob("*" + SUFIXO_MD)):
        rotulo = _relativo(path, dados)
        if not schema.validar_id("mes", path.stem):
            r.erro(rotulo, "nome de arquivo inválido (esperado AAAA-MM.md)")
            continue
        lido = _ler_markdown(path, "plano", rotulo, r)
        if lido is None:
            continue
        plano, corpo = lido
        if plano["mes"] != path.stem:
            r.erro(rotulo, "mes: %r difere do nome do arquivo" % plano["mes"])
        for id_meta in sorted(_ids_de_meta_no_texto(corpo) - set(metas)):
            r.aviso(rotulo, "órfão: seção de %s sem metas/%s.md" % (id_meta, id_meta))
        r.erros_de(rotulo, verificar_numeros_plano(plano, corpo))


def _validar_sinais(dados: Path, r: Resultado) -> None:
    pasta = dados / "sinais"
    if not pasta.is_dir():
        return
    for path in sorted(pasta.glob("*" + SUFIXO_MD)):
        rotulo = _relativo(path, dados)
        if not schema.validar_id("dia", path.stem):
            r.erro(rotulo, "nome de arquivo inválido (esperado AAAA-MM-DD.md)")
            continue
        lido = _ler_markdown(path, "sinais", rotulo, r)
        if lido is not None and lido[0]["data"].isoformat() != path.stem:
            r.erro(rotulo, "data: %s difere do nome do arquivo" % lido[0]["data"].isoformat())


def _validar_dias(dados: Path, metas: dict[str, dict[str, Any]], r: Resultado) -> None:
    pasta = dados / "dias"
    for path in sorted(pasta.glob("*" + SUFIXO_MD)) if pasta.is_dir() else []:
        rotulo = _relativo(path, dados)
        if not schema.validar_id("dia", path.stem):
            r.erro(rotulo, "nome de arquivo inválido (esperado AAAA-MM-DD.md)")
            continue
        lido = _ler_markdown(path, "dia", rotulo, r)
        if lido is None:
            continue
        dia, corpo = lido
        if dia["data"].isoformat() != path.stem:
            r.erro(rotulo, "data: %s difere do nome do arquivo" % dia["data"].isoformat())
        try:
            blocos = frontmatter.parse_blocos(corpo)
        except frontmatter.ErroFrontmatter as erro:
            r.erro(rotulo, erro.mensagem)
            continue
        _validar_blocos_do_dia(rotulo, blocos, metas, r)


def _validar_blocos_do_dia(
    rotulo: str, blocos: list[dict[str, Any]], metas: dict[str, dict[str, Any]], r: Resultado
) -> None:
    """Cada bloco uma vez por dia, no esquema de task; bloco de meta sem arquivo é aviso (órfão), não erro."""
    vistos: set[str] = set()
    for bloco in blocos:
        rotulo_bloco = "%s: bloco %s (linha do corpo %d)" % (rotulo, bloco["id"], bloco.pop("_linha"))
        if bloco["id"] in vistos:
            r.erro(rotulo_bloco, "id repetido no mesmo dia")
            continue
        vistos.add(bloco["id"])
        coagido, erros = frontmatter.coagir(bloco, schema.ESQUEMAS["task"])
        erros = erros or schema.validar_registro("task", coagido)
        if erros:
            r.erros_de(rotulo_bloco, erros)
        elif coagido["meta"] not in metas:
            r.aviso(rotulo_bloco, "órfão: meta %s sem metas/%s.md" % (coagido["meta"], coagido["meta"]))


def contexto_valido(dados: Path) -> dict[str, Any]:
    """``contexto.md`` de uma pasta cujo grafo passa: sem onboarding é ``GpErro(EXIT_ESTADO)``, grafo inválido é o
    código da validação com os primeiros erros (o diário e o mensal começam por aqui)."""
    resultado = validar_grafo(dados)
    if resultado.codigo == EXIT_ESTADO:
        raise GpErro(EXIT_ESTADO, "%s: %s" % (resultado.estado, MENSAGEM_ONBOARDING))
    if resultado.codigo != EXIT_OK:
        raise GpErro(resultado.codigo, "validar grafo: " + "; ".join(resultado.erros[:5]))
    return frontmatter.ler_contexto(dados)


def verificar_numeros_plano(plano: dict[str, Any], corpo: str) -> list[str]:
    """Achado 2.5: fora dos blocos de prosa, o plano tem de ser exatamente o
    que ``balanco.py`` escreveu. ``hash_numeros`` do front-matter é o hash do
    corpo sem o texto da prosa; diferente = alguém (modelo ou mão) mexeu em
    números, tabelas ou seções (NumerosAlterados)."""
    from goalpacer import balanco

    atual = balanco.hash_numeros(corpo)
    if plano.get("hash_numeros") != atual:
        return ["hash_numeros: números do plano alterados fora do balanço (NumerosAlterados); rode balanco.py --render"]
    return []


def validar_grafo(dados: Path) -> Resultado:
    """Toda a pasta de dados; ver o docstring do módulo para as regras."""
    r = Resultado()
    if not dados.is_dir():
        r.codigo_forcado = EXIT_IO
        r.erro(str(dados), "pasta de dados não existe")
        return r
    if not (dados / schema.CAMINHOS["contexto"]).exists() or not _tem_arquivos_de_meta(dados):
        r.estado_esperado(ESTADO_SEM_ONBOARDING, MENSAGEM_ONBOARDING)
        return r
    contexto = _ler_contexto(dados, r)
    metas = _ler_metas(dados, r)
    _validar_objetivos(dados, metas, r)
    _ler_registro(dados, r)
    _validar_planos(dados, metas, r)
    _validar_sinais(dados, r)
    _validar_dias(dados, metas, r)
    if r.estado == ESTADO_SCHEMA:
        return r
    if not r.erros and contexto is not None and not any(m.get("estado") == "ativa" for m in metas.values()):
        r.estado_esperado(ESTADO_SEM_META_ATIVA, MENSAGEM_ONBOARDING)
    return r


# --- cache e ops ----------------------------------------------------------


def _calendar_id_metas_do_contexto(dados: Path) -> Optional[str]:
    path = dados / schema.CAMINHOS["contexto"]
    if not path.exists():
        return None
    try:
        bruto, _ = frontmatter.ler_arquivo(path)
    except GpErro:
        return None
    valor = bruto.get("calendar_id_metas")
    return valor if isinstance(valor, str) and valor else None


def validar_cache(arquivo: Path, calendar_id_metas: Optional[str], dados: Optional[Path]) -> Resultado:
    """Um ``cache/calendar-*.json`` compacto (esquema ``cache_calendar``)."""
    r = Resultado()
    rotulo = arquivo.name
    cache = _ler_json(arquivo, rotulo, r)
    if cache is None:
        return r
    if not isinstance(cache, dict):
        r.erro(rotulo, "esperado objeto JSON")
        return r
    r.erros_de(rotulo, schema.validar_registro("cache_calendar", cache))
    esperado = calendar_id_metas or (_calendar_id_metas_do_contexto(dados) if dados else None)
    if esperado is None:
        r.aviso(rotulo, "calendar_id_metas não conferido (sem --calendar-id-metas nem contexto.md)")
    elif cache.get("calendar_id_metas") != esperado:
        r.erro(rotulo, "calendar_id_metas: difere do contexto (cache de outra instalação?)")
    return r


def validar_ops(arquivo: Path, planejadas: bool, dados: Optional[Path]) -> Resultado:
    """Um ``cache/ops-*.json`` (esquema ``ops``); sem ``planejadas``, op sem
    status ou com status erro é falha (achado 2.3)."""
    r = Resultado()
    rotulo = arquivo.name
    ops = _ler_json(arquivo, rotulo, r)
    if ops is None:
        return r
    if not isinstance(ops, dict):
        r.erro(rotulo, "esperado objeto JSON")
        return r
    r.erros_de(rotulo, schema.validar_registro("ops", ops))
    if not r.erros:
        for i, op in enumerate(ops.get("ops") or []):
            problema = _problema_da_op(op, planejadas)
            if problema:
                r.erro(rotulo, "ops[%d] %s" % (i, problema))
    esperado = _calendar_id_metas_do_contexto(dados) if dados else None
    if esperado is not None and ops.get("calendar_id_metas") != esperado:
        r.erro(rotulo, "calendar_id_metas: difere do contexto")
    return r


def _problema_da_op(op: dict[str, Any], planejadas: bool) -> Optional[str]:
    """Sem status só vale no arquivo de planejadas; erro traz a mensagem do conector; create ok precisa do id novo."""
    status = op.get("status")
    if status is None:
        return None if planejadas else "(%s %s): sem status = falhou" % (op.get("op"), op.get("task_id"))
    if status == "erro":
        detalhe = ": " + str(op.get("mensagem")) if op.get("mensagem") else ""
        return "(%s %s): erro%s" % (op.get("op"), op.get("task_id"), detalhe)
    if op.get("op") == "create" and not op.get("event_id_resultado"):
        return "(create %s): ok sem event_id_resultado" % op.get("task_id")
    return None


# --- CLI ------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = cli.parser_base("valida a pasta de dados do Goal Pacer (grafo, cache do Calendar, ops)")
    parser.add_argument("--json", action="store_true", help="resultado em JSON no stdout")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("grafo", help="contexto.md, metas/, registro.json, planos/, dias/")
    p_cache = sub.add_parser("cache", help="um cache/calendar-*.json compacto")
    p_cache.add_argument("arquivo", type=Path)
    p_cache.add_argument(
        "--calendar-id-metas",
        dest="calendar_id_metas",
        default=None,
        help="id do calendário Metas (senão lê contexto.md)",
    )
    p_ops = sub.add_parser("ops", help="um cache/ops-*.json")
    p_ops.add_argument("arquivo", type=Path)
    p_ops.add_argument("--planejadas", action="store_true", help="ops ainda não executadas (status ausente é aceito)")
    return parser


def _imprimir(r: Resultado, como_json: bool) -> None:
    if como_json:
        sys.stdout.write(json.dumps(r.como_dict(), ensure_ascii=False, indent=2) + "\n")
        sys.stdout.flush()
    for texto in r.erros:
        print("erro: " + texto, file=sys.stderr)
    for texto in r.avisos:
        print("aviso: " + texto, file=sys.stderr)
    sys.stderr.flush()


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        if args.comando == "grafo":
            r = validar_grafo(dados)
        elif args.comando == "cache":
            r = validar_cache(args.arquivo, args.calendar_id_metas, dados)
        else:
            r = validar_ops(args.arquivo, args.planejadas, dados)
    except GpErro as erro:
        r = Resultado()
        r.codigo_forcado = erro.codigo
        r.erros.append(erro.mensagem)
    _imprimir(r, args.json)
    return r.codigo


if __name__ == "__main__":
    raise SystemExit(main())
