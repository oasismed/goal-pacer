// Peças compartilhadas pelas telas: pílulas, cartões, anéis, blocos, decisão e navegação do horizonte.
import { ESTAGIOS, NIVEIS, acao, el, lembrar, limpar, palavraDividida, svg, t } from "./nucleo.js";

// --- peças ------------------------------------------------------------------------------

export function pilulaEstado(estado) { return el("span", { classe: "pilula e-" + estado, texto: t("coach.estado_" + estado) }); }
export function pilulaObjetivo(estado) { return el("span", { classe: "pilula e-" + estado, texto: t("coach.objetivo_" + estado) }); }
export function pilulaFaixa(faixa) { return faixa ? el("span", { classe: "pilula e-" + faixa, texto: t("coach.espaco_" + faixa) }) : null; }
export function pilulaNeutra(texto) { return el("span", { classe: "pilula sem-ponto neutra", texto: texto }); }
export function chipMeta(meta) { return el("span", { classe: "chip-meta", cor: meta.cor, texto: meta.rotulo || meta.rotulo_meta }); }

export function card(classe, titulo, detalhe, filhos, id) {
  var cabecalho = titulo ? el("h2", { id: id }, [el("span", { texto: titulo }), detalhe ? el("small", { texto: detalhe }) : null]) : null;
  return el("section", { classe: "card " + (classe || ""), "aria-labelledby": titulo && id ? id : null }, [cabecalho].concat(filhos || []));
}

export function titulo2(filhos) { return el("h2", {}, filhos); }

export function cabeca(opcoes) {
  return el("header", { classe: "cabeca" }, [
    opcoes.voltar || null,
    opcoes.selo ? el("span", { classe: "selo", texto: opcoes.selo }) : null,
    opcoes.antes || null,
    el("h1", { texto: opcoes.titulo }),
    opcoes.sub ? el("p", { classe: "sub", texto: opcoes.sub }) : null,
    opcoes.depois || null,
  ]);
}

export function iconeCheck(tamanho) {
  return svg("svg", { viewBox: "0 0 15 15", width: tamanho || 15, height: tamanho || 15, fill: "none", stroke: "currentColor", "stroke-width": "2.4", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" },
    [svg("path", { d: "M3.2 7.9l2.8 2.8 5.8-6" })]);
}

// trilho claro e arco da leitura; valor ausente (sem sinal) deixa só o trilho
export function arco(cx, cy, r, valor, cor, espessura) {
  var c = 2 * Math.PI * r;
  var grupo = svg("g", {});
  grupo.appendChild(svg("circle", { cx: cx, cy: cy, r: r, fill: "none", "stroke-width": espessura, estilo: "stroke:" + cor + ";stroke-opacity:0.15" }));
  if (valor !== null && valor !== undefined) {
    grupo.appendChild(svg("circle", {
      "class": "anel", cx: cx, cy: cy, r: r, fill: "none", "stroke-width": espessura, "stroke-linecap": "round",
      "stroke-dasharray": c.toFixed(2), "stroke-dashoffset": (c * (1 - Math.max(0.03, Math.min(1, valor)))).toFixed(2),
      transform: "rotate(-90 " + cx + " " + cy + ")", estilo: "stroke:" + cor,
    }));
  }
  return grupo;
}

export function anelObjetivo(o, tamanho) {
  var s = tamanho || 118;
  var desenho = svg("svg", { viewBox: "0 0 " + s + " " + s, width: s, height: s, role: "img", "aria-label": o.titulo + ": " + t("coach.objetivo_" + o.estado) });
  desenho.appendChild(arco(s / 2, s / 2, s / 2 - (s > 80 ? 9 : 6), o.forca, o.cor, s > 80 ? 12 : 8));
  if (s > 80) {
    const linhas = palavraDividida(t("coach.objetivo_" + o.estado));
    linhas.forEach(function (linha, i) {
      desenho.appendChild(svg("text", { x: s / 2, y: s / 2 + 5 + (i - (linhas.length - 1) / 2) * 15, "text-anchor": "middle", "font-size": "12.5", "font-weight": "750", fill: "#15181D", texto: linha }));
    });
  }
  return desenho;
}

export function jornadaSegmentos(estagio) {
  var indice = ESTAGIOS.indexOf(estagio);
  return el("div", { classe: "jornada", "aria-hidden": "true" }, ESTAGIOS.map(function (_, i) {
    return el("i", { classe: i < indice ? "feito" : i === indice ? "atual" : "" });
  }));
}

export function faisca(trilha, cor) {
  var w = 240, h = 34, pontos = [];
  var desenho = svg("svg", { "class": "faisca", viewBox: "0 0 " + w + " " + h, preserveAspectRatio: "none", "aria-hidden": "true" });
  var meio = h - 0.5 * (h - 6) - 3;
  desenho.appendChild(svg("line", { x1: 0, x2: w, y1: meio, y2: meio, "stroke-dasharray": "3 4", estilo: "stroke:rgba(21,24,29,0.18);stroke-width:1" }));
  trilha.forEach(function (v, i) {
    if (v === null) { return; }
    pontos.push([(i / (trilha.length - 1)) * (w - 8) + 4, h - v * (h - 6) - 3]);
  });
  if (pontos.length > 1) {
    desenho.appendChild(svg("polyline", { points: pontos.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" "), fill: "none", "stroke-width": "2.2", "stroke-linejoin": "round", "stroke-linecap": "round", estilo: "stroke:" + cor }));
  }
  if (pontos.length) {
    const ultimo = pontos[pontos.length - 1];
    desenho.appendChild(svg("circle", { cx: ultimo[0], cy: ultimo[1], r: 3.2, estilo: "fill:" + cor }));
  }
  return desenho;
}

export function linhaBloco(b, opcoes) {
  var botao = el("button", {
    classe: "check" + (b.presumida ? " presumida" : ""), type: "button", cor: b.cor,
    "aria-pressed": b.confirmada ? "true" : "false", "aria-label": b.confirmada ? t("confirmada") : t("confirmar", { titulo: b.titulo }),
  }, [iconeCheck()]);
  if (!b.pode_confirmar) { botao.disabled = !b.confirmada; }
  if (b.pode_confirmar) { botao.addEventListener("click", function () { botao.setAttribute("aria-pressed", "true"); acao("/api/confirmar", { task_id: b.id }); }); }
  var titulo = el("div", { classe: "titulo" }, [chipMeta(b), el("span", { texto: b.titulo })]);
  if (b.presumida) { titulo.appendChild(el("span", { classe: "tag-estado", texto: t("feita_presumida") })); }
  if (b.nao_feita) { titulo.appendChild(el("span", { classe: "tag-estado", texto: t("nao_feita") })); }
  if (["movida", "apagada", "reagendada"].indexOf(b.estado) >= 0) { titulo.appendChild(el("span", { classe: "tag-estado", texto: t("bloco_" + b.estado) })); }
  var direita = null;
  if (b.passou && b.pode_confirmar && !b.nao_feita) {
    direita = el("button", { classe: "mini", type: "button", texto: t("nao_fiz") });
    direita.addEventListener("click", function () { acao("/api/nao-feita", { task_id: b.id }); });
  }
  return el("div", { classe: "bloco", cor: b.cor }, [
    botao,
    el("div", { classe: "hora" }, [b.inicio, el("small", { texto: opcoes && opcoes.comDia ? b.dia_curto : b.duracao })]),
    el("div", {}, [titulo, b.porque ? el("div", { classe: "porque", texto: b.porque }) : null]),
    direita,
  ]);
}

export function cartaoDecisao(d) {
  // respondida neste aparelho: some até o diário refazer o plano (a chave muda com o texto novo)
  if (lembrar("gp-decisao-" + d.chave) === "1") { return null; }
  var respondida = function () { lembrar("gp-decisao-" + d.chave, "1"); };
  var id = "decisao-" + d.meta;
  var cartao = card("decisao", d.titulo_card, d.titulo, [el("p", { classe: "sub", texto: d.texto })], id + "-t");
  if (d.cor) { cartao.style.setProperty("--cor", d.cor); }
  var saidas = [["reduzir", t("saida_reduzir")], [d.prazo_externo ? "renegociar" : "adiar", d.prazo_externo ? t("saida_renegociar") : t("saida_adiar")], ["manter", t("saida_manter")]];
  var linha = el("div", { classe: "saidas" });
  var campo = el("div", { classe: "campo" });
  campo.hidden = true;
  saidas.forEach(function (par) {
    var botao = el("button", { classe: "saida", type: "button", "aria-pressed": "false", texto: par[1] });
    botao.addEventListener("click", function () {
      Array.prototype.forEach.call(linha.children, function (b) { b.setAttribute("aria-pressed", b === botao ? "true" : "false"); });
      if (par[0] === "manter") {
        campo.hidden = true;
        return acao("/api/decisao", { meta: d.meta, saida: "manter" }, respondida);
      }
      limpar(campo);
      var reduzir = par[0] === "reduzir";
      var entrada = el("input", reduzir
        ? { id: id + "-custo", type: "number", min: "0.5", step: "0.5", value: String(Math.max(0.5, d.custo_h_semana - 1)) }
        : { id: id + "-prazo", type: "date", value: d.prazo });
      var aplicar = el("button", { classe: "botao-escuro", type: "button", texto: t("aplicar") });
      aplicar.addEventListener("click", function () {
        acao("/api/decisao", reduzir ? { meta: d.meta, saida: "reduzir", custo: Number(entrada.value) } : { meta: d.meta, saida: par[0], prazo: entrada.value }, respondida);
      });
      campo.appendChild(el("label", { "for": entrada.id, texto: reduzir ? t("custo_rotulo") : t("prazo_rotulo") }));
      campo.appendChild(el("div", { classe: "campo-linha" }, [entrada, aplicar]));
      campo.hidden = false;
      entrada.focus();
    });
    linha.appendChild(botao);
  });
  cartao.appendChild(linha);
  cartao.appendChild(campo);
  return cartao;
}

export function semanasEspaco(semanas, mini) {
  var caixa = el("div", { classe: "semanas" + (mini ? " mini-semanas" : "") });
  caixa.style.setProperty("--n", String(Math.max(1, semanas.length)));
  semanas.forEach(function (s) {
    var barra = el("i", {});
    barra.style.height = Math.max(8, Math.round(s.valor * 100)) + "%";
    caixa.appendChild(el("div", { classe: "semana f-" + s.faixa + (s.atual ? " agora" : ""), title: t("oferta_demanda", { oferta: s.oferta, demanda: s.demanda }) }, [
      el("div", { classe: "coluna-barra" }, [barra]),
      el("span", {}, [s.curta, mini ? null : el("small", { texto: t("coach.espaco_" + s.faixa) })]),
    ]));
  });
  return caixa;
}

export function listaEvidencias(evidencias, comMeta) {
  if (!evidencias.length) { return el("p", { classe: "vazio", texto: t("sem_evidencias") }); }
  return el("ul", { classe: "eventos" }, evidencias.map(function (e) {
    return el("li", {}, [el("time", { texto: e.data }), el("span", { classe: "titulo" }, [comMeta ? chipMeta(e) : null, el("span", { texto: e.resumo }), el("small", { texto: e.fonte })])]);
  }));
}

// --- navegação do horizonte (ano > semestre > trimestre > mês > semana > dia) --------------

export function hrefPeriodo(nivel, id) { return nivel === "dia" ? "#/dia/" + id : "#/periodo/" + nivel + "/" + id; }

// trilha = ancestrais [{nivel, id, rotulo}]; ids = {nivel: id} do período atual e dos que o contêm
export function navegacaoHorizonte(trilha, nivelAtual, ids) {
  var migalhas = el("ol", { classe: "migalhas", "aria-label": t("trilha_rotulo") }, trilha.map(function (p) {
    return el("li", {}, [el("a", { href: hrefPeriodo(p.nivel, p.id), texto: p.rotulo })]);
  }));
  var seletor = el("div", { classe: "niveis", role: "group", "aria-label": t("niveis_rotulo") }, NIVEIS.map(function (n) {
    var atual = n === nivelAtual;
    return el("a", { href: ids[n] ? hrefPeriodo(n, ids[n]) : "#/horizontes", "aria-current": atual ? "page" : null, classe: atual ? "ativo" : "", texto: t("nivel_" + n) });
  }));
  return el("div", { classe: "horizonte-nav" }, [trilha.length ? migalhas : el("span"), seletor]);
}

export function setas(anterior, proximo, rotuloAnterior, rotuloProximo) {
  return el("div", { classe: "setas" }, [
    el("a", { classe: "seta", href: anterior, "aria-label": rotuloAnterior, title: rotuloAnterior, texto: "‹" }),
    el("a", { classe: "seta", href: proximo, "aria-label": rotuloProximo, title: rotuloProximo, texto: "›" }),
  ]);
}

export function classeLeitura(chave) {
  var fim = (chave || "").split("_").pop();
  return "l-" + ({ florescendo: "forte", firme: "forte", ritmo: "media", construcao: "media", atencao: "fraca", foco: "fraca" }[fim] || "neutra");
}

export function anelMini(valor, tamanho, futuro) {
  var s = tamanho || 44;
  var desenho = svg("svg", { viewBox: "0 0 " + s + " " + s, width: s, height: s, "aria-hidden": "true", "class": futuro ? "anel-futuro" : "" });
  desenho.appendChild(arco(s / 2, s / 2, s / 2 - 5, valor, "var(--verde)", 6));
  return desenho;
}

export function linhaMetaPeriodo(x) {
  return el("a", { classe: "meta-periodo", href: "#/meta/" + x.id, cor: x.cor }, [
    el("div", { classe: "meta-topo" }, [el("span", { classe: "titulo" }, [chipMeta(x), el("span", { texto: x.titulo })]), pilulaEstado(x.estado)]),
    el("div", { classe: "linha-info" }, [
      el("span", { texto: t("horizonte_meta_" + x.horizonte) }),
      x.compasso ? el("span", { texto: t("coach.compasso_" + x.compasso) }) : null,
      el("span", { classe: x.prazo_aqui ? "prazo-aqui" : "", texto: t("prazo_data", { data: x.prazo_curto }) + (x.prazo_aqui ? " · " + t("prazo_aqui") : "") }),
    ]),
    jornadaSegmentos(x.estagio),
  ]);
}
