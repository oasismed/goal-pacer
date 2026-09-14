#!/usr/bin/env python3
"""checkin.py inferir | confirmar --respostas <json>: o check-in (T5; design "Check-in em 6 passos").

A skill conversa; este script decide e grava. Dois comandos::

    inferir   --> lê os blocos abertos de dias/*.md, um list_events do Metas
                  (janela dos blocos) + os [GP] do primário, infere
                  apagada/movida/reagendada/feita?(presumida)/sem_sinal
                  (goalpacer.inferencia), grava em registro.json respeitando a
                  máquina de estados e imprime o que a skill precisa para os
                  passos 1 e 2 (linha-resumo, presumidas, inferidas, nota sugerida)
    confirmar --> aplica as respostas do usuário (passos 2, 4 e 5): feitas
                  confirmadas com duração real, não feitas, progresso declarado,
                  nota de aprendizado aceita (perfil.md) ou recusada; recalcula
                  perfil.json; diz o que mudou. O passo 6 (regenerar o dia)
                  chama diario.py --sem-inferir quando ele existir (T6).

Respostas de ``confirmar``::

    {"feitas": [{"task_id": "D-...", "duracao_real_h": 1.5}], "nao_feitas": ["D-..."],
     "progresso": {"M01": 50}, "nota": {"texto": "...", "aceita": false},
     "decisoes": {"M02": {"saida": "adiar", "prazo": "2027-04-12"}}}

Só ``origem: confirmado`` abate a demanda; presumidas continuam "feita?"
até o usuário confirmar (uma tecla aqui, ou apagar/mover o bloco).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goalpacer import (
    balanco,
    base,
    calendar_ops,
    cli,
    clock,
    conexoes,
    copy,
    frontmatter,
    inferencia,
    io as gpio,
    metas as gpmetas,
    perfil as prf,
    registro as reg,
    schema,
)
from goalpacer.base import EXIT_ESTADO, EXIT_IO, EXIT_OK, EXIT_VALIDACAO, GpErro

TAXA_NOTA = 0.34
NOME_PERFIL_MD = "perfil.md"


def _contexto(dados: Path) -> dict[str, Any]:
    path = dados / schema.CAMINHOS["contexto"]
    if not path.exists():
        raise GpErro(
            EXIT_ESTADO,
            "sem_onboarding: "
            + copy.texto("onboarding.abertura")
            .split(".")[0]
            .lower()
            .replace("vamos montar", "rode /goal-pacer onboarding para montar"),
        )
    bruto, _ = frontmatter.ler_arquivo(path)
    coagido, erros = frontmatter.coagir(bruto, schema.ESQUEMAS["contexto"])
    erros = erros or schema.validar_registro("contexto", coagido)
    if erros:
        raise GpErro(EXIT_VALIDACAO, "contexto.md: " + "; ".join(erros[:5]))
    return coagido


def _abertos(blocos: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in blocos.values() if b.get("estado") in reg.ESTADOS_ABERTOS and b.get("origem") != "confirmado"]


def _nota_sugerida(
    perfil: Optional[dict[str, Any]], registro: dict[str, Any], agora: datetime
) -> Optional[dict[str, Any]]:
    """Uma nota de aprendizado (passo 5): a pior célula confiável abaixo de TAXA_NOTA, se não foi recusada há 30 dias."""
    if not perfil:
        return None
    candidatas = []
    for celula, item in perfil.get("janelas", {}).items():
        if int(item.get("n", 0)) >= prf.MINIMO_OBSERVACOES and float(item["taxa_conclusao"]) <= TAXA_NOTA:
            candidatas.append((float(item["taxa_conclusao"]), celula, int(item["n"])))
    for taxa, celula, n in sorted(candidatas):
        dia, faixa = celula.split("-")
        nome_dia = copy.lista("calendario.dias_nota")[schema.DIAS_SEMANA.index(dia)]
        nome_faixa = copy.lista("calendario.faixas_nota")[schema.FAIXAS_HORA.index(faixa)]
        restricao = copy.texto("checkin.restricao", dia=nome_dia, faixa=nome_faixa)
        if reg.nota_recusada_recente(registro, restricao, agora):
            continue
        return {
            "celula": celula,
            "texto": restricao,
            "pergunta": copy.texto(
                "checkin.p5_nota", dia=nome_dia, faixa=nome_faixa, pct=round(taxa * 100), n=n, restricao=restricao
            ),
        }
    return None


def _resumo(contagens: dict[str, int]) -> str:
    partes = []
    for chave in ("confirmadas", "presumidas", "movidas", "reagendadas", "apagadas"):
        n = contagens.get(chave)
        if n:
            partes.append(copy.texto("checkin.conta_%s_%s" % (chave, "um" if n == 1 else "n"), n=n))
    return " · ".join(partes) if partes else copy.texto("checkin.sem_movimento")


def _bloco_saida(bloco: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": bloco["id"],
        "titulo": bloco.get("titulo", ""),
        "meta": bloco.get("meta"),
        "inicio": bloco["inicio"].isoformat(timespec="minutes"),
        "fim": bloco["fim"].isoformat(timespec="minutes"),
        "duracao_h": bloco.get("duracao_h"),
        "estado": bloco.get("estado"),
        "origem": bloco.get("origem"),
    }


def decisoes_pendentes(dados: Path, agora: datetime) -> list[dict[str, Any]]:
    """Decisões do plano do mês da semana de ``agora`` para metas ativas.

    Plano gerado com outras metas (``hash_metas`` diferente) não oferece
    decisão: alguma já foi respondida e o próximo diário refaz o balanço."""
    mes = clock.mes_da_semana(clock.semana_iso(agora.date()))
    path = dados / "planos" / ("%s.md" % mes)
    if not path.exists():
        return []
    metas = prf._ler_metas(dados)
    plano = balanco.ler_plano(path.read_text(encoding="utf-8"))
    if plano["frontmatter"].get("hash_metas") != schema.hash_metas(metas.values()):
        return []
    saida = []
    for meta_id, texto in plano["decisoes"]:
        meta = metas.get(meta_id)
        if meta is None or meta.get("estado", "ativa") != "ativa":
            continue
        saida.append(
            {
                "meta": meta_id,
                "titulo": meta["titulo"],
                "texto": texto,
                "sugerida": plano["metas"].get(meta_id, {}).get("decisao"),
                "prazo": meta["prazo"].isoformat(),
                "prazo_externo": bool(meta.get("prazo_externo")),
                "custo_h_semana": meta["custo_h_semana_escolhido"],
            }
        )
    return saida


def inferir(dados: Path, *, modo_offline: bool, agora: Optional[datetime] = None) -> dict[str, Any]:
    agora = agora or clock.agora()
    contexto = _contexto(dados)
    registro = reg.carregar(dados)
    lidos = prf.ler_blocos(dados)
    blocos = prf.blocos_com_registro(dados, registro, lidos=lidos)
    abertos = _abertos(blocos)
    # sem Google Calendar não há o que inferir: os blocos esperam o check-in da pessoa
    usa = conexoes.usa_agenda(contexto)
    inferidas = _inferencias(contexto, abertos, agora, modo_offline=modo_offline) if abertos and usa else []
    aplicadas = [a for a in (_aplicar_inferencia(registro, blocos, inf, agora) for inf in inferidas) if a is not None]
    reg.salvar(registro, dados)
    perfil = prf.calcular(dados, agora, registro=registro, blocos=lidos)
    prf.gravar(dados, perfil)
    presumidas = [
        _bloco_saida(b) for b in blocos.values() if b.get("estado") == "feita" and b.get("origem") == "presumido"
    ]
    contagens = _contagens(blocos)
    return {
        "resumo": _resumo(contagens),
        "contagens": contagens,
        "aplicadas": aplicadas,
        "presumidas": presumidas,
        "inferidas": [
            _bloco_saida(b)
            for b in blocos.values()
            if b.get("estado") in ("movida", "reagendada", "apagada") and b.get("origem") == "inferido"
        ],
        "sem_sinal": [_bloco_saida(b) for b in blocos.values() if b.get("estado") == "sem_sinal"],
        "segunda": agora.weekday() == 0,
        "nota_sugerida": _nota_sugerida(perfil, registro, agora),
        "decisoes": decisoes_pendentes(dados, agora),
        "perfil": {m: perfil["metas"][m] for m in perfil["metas"]},
        "metas_sentir": metas_para_sentir(dados, registro),
    }


def _inferencias(
    contexto: dict[str, Any], abertos: list[dict[str, Any]], agora: datetime, *, modo_offline: bool
) -> list[inferencia.Inferencia]:
    """Eventos do Metas e os ``[GP]`` do primário na janela dos blocos abertos, e o que cada bloco virou."""
    metas_id = contexto["calendar_id_metas"]
    inicio, fim = inferencia.janela_dos_blocos(abertos, agora)
    eventos = calendar_ops.ler_eventos(metas_id, inicio, fim, calendar_id_metas=metas_id, modo_offline=modo_offline)
    eventos += calendar_ops.ler_eventos(
        contexto["calendar_id_primario"],
        inicio,
        fim,
        calendar_id_metas=metas_id,
        modo_offline=modo_offline,
        full_text=calendar_ops.FULLTEXT_GC,
    )
    return inferencia.inferir(
        abertos,
        eventos,
        calendar_id_metas=metas_id,
        calendar_id_primario=contexto["calendar_id_primario"],
        instalacao_id=contexto["instalacao_id"],
        agora=agora,
    )


def _aplicar_inferencia(
    registro: dict[str, Any], blocos: dict[str, dict[str, Any]], inf: inferencia.Inferencia, agora: datetime
) -> Optional[dict[str, Any]]:
    """Grava a inferência no registro (confirmado vence inferido: o registro recusa) e devolve a linha aplicada."""
    bloco = blocos[inf.task_id]
    if inf.estado == "sem_sinal" and bloco.get("estado") == "sem_sinal":
        return None
    gravou = reg.registrar_checkin(
        registro,
        inf.task_id,
        inf.estado,
        inf.origem,
        ts=agora,
        inicio=inf.inicio,
        fim=inf.fim,
        calendar_id=inf.calendar_id,
        calendar_event_id=inf.calendar_event_id,
    )
    if not gravou:
        return None
    if inf.estado == "feita":
        reg.registrar_feita(registro, bloco["meta"], inf.task_id, float(bloco["duracao_h"]), inf.origem, ts=agora)
    else:
        reg.remover_feita(registro, inf.task_id)
    bloco["estado"], bloco["origem"] = inf.estado, inf.origem
    return {
        "task_id": inf.task_id,
        "estado": inf.estado,
        "origem": inf.origem,
        "motivo": inf.motivo,
        "calendar_id": inf.calendar_id,
        "calendar_event_id": inf.calendar_event_id,
        "inicio": inf.inicio.isoformat(timespec="minutes") if inf.inicio else None,
        "fim": inf.fim.isoformat(timespec="minutes") if inf.fim else None,
    }


def _contagens(blocos: dict[str, dict[str, Any]]) -> dict[str, int]:
    estados = [(b.get("estado"), b.get("origem")) for b in blocos.values()]
    return {
        "confirmadas": estados.count(("feita", "confirmado")),
        "presumidas": estados.count(("feita", "presumido")),
        "movidas": sum(1 for e, _ in estados if e == "movida"),
        "reagendadas": sum(1 for e, _ in estados if e == "reagendada"),
        "apagadas": sum(1 for e, _ in estados if e == "apagada"),
    }


TETO_SENTIR = 4


def metas_para_sentir(dados: Path, registro: dict[str, Any]) -> list[dict[str, Any]]:
    """Metas ativas para "como você está com ela?", as de maior impacto primeiro (até 4, o teto de uma pergunta)."""
    metas = [m for m in prf._ler_metas(dados).values() if m.get("estado", "ativa") == "ativa"]
    metas.sort(key=lambda m: (-schema.PESO_IMPACTO.get(m.get("impacto") or "importante", 2), m["id"]))
    saida = []
    for meta in metas[:TETO_SENTIR]:
        historico = registro.get("sentimentos", {}).get(meta["id"]) or []
        ultimo = max(historico, key=lambda s: str(s.get("ts")))["valor"] if historico else None
        saida.append(
            {
                "meta": meta["id"],
                "rotulo": "M%d" % int(meta["id"][1:]),
                "titulo": meta["titulo"],
                "impacto": meta.get("impacto") or "importante",
                "ultimo": ultimo,
            }
        )
    return saida


_numero = base.numero


def confirmar(dados: Path, respostas: dict[str, Any], *, agora: Optional[datetime] = None) -> dict[str, Any]:
    agora = agora or clock.agora()
    _contexto(dados)
    registro = reg.carregar(dados)
    lidos = prf.ler_blocos(dados)
    c = _Confirmacao(dados, registro, prf.blocos_com_registro(dados, registro, lidos=lidos), agora)
    c.feitas(respostas.get("feitas") or [])
    c.nao_feitas(respostas.get("nao_feitas") or [])
    c.progresso(respostas.get("progresso") or {})
    c.sentimentos(respostas.get("sentimentos") or {})
    decisoes = c.decisoes_validas(respostas.get("decisoes") or {})
    if c.erros:
        raise GpErro(EXIT_VALIDACAO, "\n".join(c.erros))
    c.nota(respostas.get("nota"))
    for meta_id, decisao in decisoes:
        c.aplicar_decisao(meta_id, decisao)
    reg.salvar(registro, dados)
    perfil = prf.calcular(dados, agora, registro=registro, blocos=lidos)
    prf.gravar(dados, perfil)
    return {
        "mudancas": c.mudancas,
        "perfil": perfil["metas"],
        "n_confirmadas": perfil["n_confirmadas"],
        "proximo": "semanal.py e diario.py --sem-inferir" if decisoes else "diario.py --sem-inferir",
    }


class _Confirmacao:
    """Aplica as respostas ao registro em memória, juntando as mudanças (para a tela) e as recusas (todas de uma vez:
    com qualquer recusa nada é gravado)."""

    def __init__(
        self, dados: Path, registro: dict[str, Any], blocos: dict[str, dict[str, Any]], agora: datetime
    ) -> None:
        self.dados = dados
        self.registro = registro
        self.blocos = blocos
        self.agora = agora
        self.mudancas: list[str] = []
        self.erros: list[str] = []

    def _meta_existe(self, meta_id: str) -> bool:
        return (self.dados / "metas" / ("%s.md" % meta_id)).exists()

    def feitas(self, itens: list[Any]) -> None:
        for item in itens:
            task_id = item.get("task_id") if isinstance(item, dict) else item
            bruto = item.get("duracao_real_h") if isinstance(item, dict) else None
            real = _numero(bruto)
            if task_id not in self.blocos:
                self.erros.append("feitas: bloco %r não existe" % (task_id,))
            elif bruto is not None and (real is None or real <= 0):
                self.erros.append("feitas: duracao_real_h de %s inválida: %r" % (task_id, bruto))
            else:
                bloco = self.blocos[task_id]
                reg.registrar_checkin(self.registro, task_id, "feita", "confirmado", ts=self.agora, duracao_real_h=real)
                reg.registrar_feita(
                    self.registro,
                    bloco["meta"],
                    task_id,
                    float(bloco["duracao_h"]),
                    "confirmado",
                    duracao_real_h=real,
                    ts=self.agora,
                )
                duracao = " (%.2g h)" % real if real else ""
                self.mudancas.append(copy.texto("checkin.mudanca_feita", task=task_id, duracao=duracao))

    def nao_feitas(self, task_ids: list[Any]) -> None:
        for task_id in task_ids:
            if task_id not in self.blocos:
                self.erros.append("nao_feitas: bloco %r não existe" % (task_id,))
                continue
            reg.registrar_checkin(self.registro, task_id, "nao_feita", "confirmado", ts=self.agora)
            reg.remover_feita(self.registro, task_id)
            self.mudancas.append(copy.texto("checkin.mudanca_nao_feita", task=task_id))

    def progresso(self, declarados: dict[str, Any]) -> None:
        for meta, pct in declarados.items():
            valor = _numero(pct)
            if valor is None or not 0 <= valor <= 100 or not schema.validar_id("meta", meta):
                self.erros.append("progresso: %r para %r inválido (0 a 100)" % (pct, meta))
                continue
            reg.declarar_progresso(self.registro, meta, valor, ts=self.agora)
            self.mudancas.append(copy.texto("checkin.mudanca_progresso", meta=meta, pct="%.0f" % valor))

    def sentimentos(self, marcados: dict[str, Any]) -> None:
        for meta_id, valor in sorted(marcados.items()):
            if not self._meta_existe(meta_id) or valor not in schema.SENTIMENTOS:
                self.erros.append(
                    "sentimentos: %r para %r inválido (%s)" % (valor, meta_id, "|".join(schema.SENTIMENTOS))
                )
                continue
            reg.registrar_sentimento(self.registro, meta_id, valor, ts=self.agora)
            sentimento = copy.texto("coach.sentimento_" + valor).lower()
            self.mudancas.append(copy.texto("checkin.mudanca_sentimento", meta=meta_id, sentimento=sentimento))

    def decisoes_validas(self, decisoes: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        validas = []
        for meta_id, decisao in sorted(decisoes.items()):
            if not isinstance(decisao, dict) or decisao.get("saida") not in gpmetas.SAIDAS:
                self.erros.append("decisoes: %s precisa de {saida: %s}" % (meta_id, "|".join(gpmetas.SAIDAS)))
            elif not self._meta_existe(meta_id):
                self.erros.append("decisoes: meta %s não existe" % meta_id)
            else:
                validas.append((meta_id, decisao))
        return validas

    def nota(self, nota: Any) -> None:
        if not (isinstance(nota, dict) and isinstance(nota.get("texto"), str) and nota["texto"].strip()):
            return
        texto = " ".join(nota["texto"].split())
        if not nota.get("aceita"):
            reg.recusar_nota(self.registro, texto, ts=self.agora)
            self.mudancas.append(copy.texto("checkin.mudanca_nota_recusada", dias=reg.DIAS_NOTA_RECUSADA))
            return
        path = base.caminho_dados(NOME_PERFIL_MD)
        atual = (
            path.read_text(encoding="utf-8")
            if path.exists()
            else "# Perfil\n\nO que o Goal Pacer sabe sobre você. Edite à vontade.\n\n## Observações confirmadas\n"
        )
        gpio.escrever_atomico(path, atual.rstrip("\n") + "\n- %s: %s\n" % (self.agora.date().isoformat(), texto))
        self.mudancas.append(copy.texto("checkin.mudanca_nota"))

    def aplicar_decisao(self, meta_id: str, decisao: dict[str, Any]) -> None:
        feito = gpmetas.aplicar_decisao(self.dados, meta_id, decisao)
        campos = ", ".join(copy.texto("checkin.mudanca_campo", campo=c, valor=v[1]) for c, v in feito.items())
        self.mudancas.append(
            copy.texto(
                "checkin.mudanca_decisao",
                meta=meta_id,
                saida=copy.texto("status.decisao_" + decisao["saida"]),
                detalhe=" (%s)" % campos if feito else "",
            )
        )


def _parser() -> argparse.ArgumentParser:
    parser = cli.parser_base("check-in do Goal Pacer: inferir do Calendar e confirmar respostas")
    parser.add_argument("--json", action="store_true", help="saída em JSON")
    sub = parser.add_subparsers(dest="comando")
    sub.add_parser("inferir", help="lê o Calendar, grava inferências e imprime o resumo")
    p_c = sub.add_parser("confirmar", help="aplica as respostas do usuário e recalcula o perfil")
    p_c.add_argument("--respostas", type=Path, required=True)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.comando is None:
        parser.print_usage(sys.stderr)
        return EXIT_VALIDACAO
    trava = None
    try:
        cli.aplicar_args_base(args)
        dados = base.data_dir()
        try:
            trava = reg.lock(dados)
        except GpErro as erro:
            raise GpErro(EXIT_IO, copy.texto("checkin.lock_preso", detalhe=erro.mensagem)) from erro
        if args.comando == "inferir":
            saida = inferir(dados, modo_offline=args.offline)
            texto = copy.texto("checkin.abertura", resumo=saida["resumo"])
        else:
            respostas = gpio.ler_json(args.respostas)
            if not isinstance(respostas, dict):
                raise GpErro(EXIT_VALIDACAO, "respostas: esperado objeto JSON")
            saida = confirmar(dados, respostas)
            texto = copy.texto(
                "checkin.fechamento",
                mudancas="\n".join("- " + m for m in saida["mudancas"]) or "- " + copy.texto("checkin.nada_a_mudar"),
            )
        if args.json:
            sys.stdout.write(json.dumps(saida, ensure_ascii=False, indent=2, default=str) + "\n")
        else:
            sys.stdout.write(texto + "\n")
        return EXIT_OK
    except GpErro as erro:
        if args.json:
            sys.stdout.write(
                json.dumps({"ok": False, "codigo": erro.codigo, "erros": erro.mensagem.split("\n")}, ensure_ascii=False)
                + "\n"
            )
        print("erro: " + erro.mensagem, file=sys.stderr)
        return erro.codigo
    finally:
        if trava is not None:
            trava.liberar()


if __name__ == "__main__":
    raise SystemExit(main())
