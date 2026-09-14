// Tela Meta (#/meta/Mxx): leitura do coach, trilha, sinais, jornada, sentimento, ajustes e números.
import { ESTAGIOS, FAIXAS_TRACAO, IMPACTOS, SENTIMENTOS, acao, avisar, el, svg, t } from "../nucleo.js";
import { cabeca, card, chipMeta, hrefPeriodo, iconeCheck, linhaBloco, listaEvidencias, pilulaEstado, pilulaNeutra, titulo2 } from "../pecas.js";

// --- Meta -------------------------------------------------------------------------------

export function faixaDe(v) {
  for (let i = FAIXAS_TRACAO.length - 1; i >= 0; i--) { if (v >= FAIXAS_TRACAO[i][0]) { return FAIXAS_TRACAO[i][2]; } }
  return "travada";
}

// tração por semana sobre as faixas com nome dos estados
export function trilhaGrafico(meta) {
  var L = 12, R = 118, T = 12, B = 30, W = 600 - L - R, H = 220 - T - B;
  var y = function (v) { return T + (1 - v) * H; };
  var x = function (i) { return L + 18 + (i / (meta.trilha.length - 1)) * (W - 36); };
  var desenho = svg("svg", { "class": "trilha", viewBox: "0 0 600 220", role: "img", "aria-label": t("trilha_titulo") + ": " + meta.trilha.map(function (v, i) {
    return meta.trilha_semanas[i] + " " + (v === null ? t("trilha_sem") : t("coach.estado_" + faixaDe(v)));
  }).join(", ") });
  FAIXAS_TRACAO.forEach(function (f) {
    desenho.appendChild(svg("rect", { x: L, y: y(f[1]), width: W, height: y(f[0]) - y(f[1]), estilo: "fill:var(--" + f[2] + "-bg);fill-opacity:0.8" }));
    desenho.appendChild(svg("text", { x: L + W + 10, y: (y(f[0]) + y(f[1])) / 2 + 4, "font-size": "11.5", "font-weight": "700", estilo: "fill:var(--" + f[2] + ")", texto: t("coach.estado_" + f[2]) }));
  });
  var pontos = [];
  meta.trilha.forEach(function (v, i) {
    desenho.appendChild(svg("text", { x: x(i), y: T + H + 20, "text-anchor": "middle", "font-size": "11", fill: "#858B94", texto: meta.trilha_semanas[i] }));
    if (v !== null) { pontos.push([x(i), y(v)]); } else {
      desenho.appendChild(svg("circle", { cx: x(i), cy: T + H - 8, r: 4, estilo: "fill:none;stroke:#858B94;stroke-width:1.5;stroke-dasharray:2 2" }));
    }
  });
  var traco = pontos.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
  if (pontos.length > 1) {
    const area = "M" + pontos[0][0].toFixed(1) + "," + (T + H) + " L" + traco.split(" ").join(" L") + " L" + pontos[pontos.length - 1][0].toFixed(1) + "," + (T + H) + " Z";
    desenho.appendChild(svg("path", { d: area, estilo: "fill:" + meta.cor + ";fill-opacity:0.12" }));
    desenho.appendChild(svg("polyline", { points: traco, fill: "none", "stroke-width": "3", "stroke-linejoin": "round", "stroke-linecap": "round", estilo: "stroke:" + meta.cor }));
  }
  pontos.forEach(function (p, i) {
    desenho.appendChild(svg("circle", { cx: p[0], cy: p[1], r: i === pontos.length - 1 ? 6 : 4, estilo: "fill:#FFFFFF;stroke-width:2.5;stroke:" + meta.cor }));
  });
  return desenho;
}

export function telaMeta(m) {
  var x = m.meta;
  var objetivoAtual = m.objetivo && !m.objetivo.implicito ? m.objetivo.id : "";
  var voltar = el("a", { classe: "voltar", href: "#/metas", texto: "← " + t("voltar_metas") });
  var antes = el("div", { classe: "pilulas" }, [chipMeta(x), objetivoAtual ? el("a", { classe: "chip-obj", cor: m.objetivo.cor, href: "#/objetivos", texto: m.objetivo.titulo }) : null]);
  var depois = el("div", { classe: "pilulas" }, [
    pilulaEstado(x.estado), pilulaNeutra(t("coach.impacto_" + x.impacto)),
    pilulaNeutra(x.tendencia ? t("coach.tendencia_" + x.tendencia) : t("coach.tendencia_sem_sinal")),
    el("a", { classe: "pilula sem-ponto neutra", href: hrefPeriodo(x.horizonte, x.periodo_prazo), texto: t("horizonte_meta_" + x.horizonte) + " · " + t("prazo_data", { data: x.prazo_curto }) + (x.prazo_externo ? " · " + t("prazo_externo") : "") }),
    x.compasso ? pilulaNeutra(t("coach.compasso_" + x.compasso)) : null,
  ]);

  var leitura = card("", t("leitura_titulo"), m.leitura.parada, [el("div", { classe: "leitura" }, [
    m.leitura.funcionando ? el("p", { texto: m.leitura.funcionando }) : null,
    el("p", { texto: m.leitura.atrito }),
    el("p", { classe: "passo", texto: m.leitura.passo }),
  ])], "t-leitura");
  var trilha = card("", t("trilha_titulo"), t("trilha_detalhe"), [el("div", { classe: "tabela-rolagem" }, [trilhaGrafico(x)])], "t-trilha");
  var sinais = card("", t("sinais_titulo"), t("sinais_detalhe"), [el("div", { classe: "sinais" }, m.sinais.map(function (s) {
    return el("div", { classe: "sinal" }, [
      el("b", { texto: t("coach.sinal_" + s.nome) }),
      el("div", { classe: "medidor n-" + s.nivel, "aria-hidden": "true" }, [el("i"), el("i"), el("i")]),
      el("span", { texto: s.frase }),
    ]);
  }))], "t-sinais");

  var recentes = el("div", { classe: "lista" }, m.recentes.map(function (b) { return linhaBloco(b, { comDia: true }); }));
  if (!m.recentes.length) { recentes.appendChild(el("p", { classe: "vazio", texto: t("sem_recentes") })); }
  var proximos = el("div", { classe: "lista" }, m.proximos.map(function (b) { return linhaBloco(b, { comDia: true }); }));
  if (!m.proximos.length) { proximos.appendChild(el("p", { classe: "vazio", texto: t("sem_proximos") })); }
  var blocos = card("", t("recentes_titulo"), null, [recentes, titulo2([el("span", { texto: t("proximos_titulo") })]), proximos], "t-recentes");

  var indice = ESTAGIOS.indexOf(x.estagio);
  var passos = el("div", { classe: "passos-jornada" }, ESTAGIOS.map(function (e, i) {
    return el("div", { classe: i < indice ? "feito" : i === indice ? "atual" : "" }, [el("i"), el("span", { texto: t("coach.estagio_" + e) })]);
  }));
  var marcos = el("ul", { classe: "marcos" }, x.marcos.map(function (mc) {
    var botao = el("button", { classe: "marco", type: "button", "aria-pressed": mc.feito ? "true" : "false" }, [el("span", { classe: "caixa" }, [iconeCheck(13)]), el("span", { texto: mc.texto })]);
    botao.addEventListener("click", function () { acao("/api/meta/marco", { meta: x.id, indice: mc.indice, feito: !mc.feito }); });
    return el("li", {}, [botao]);
  }));
  var jornada = card("", t("jornada"), t("coach.estagio_" + x.estagio), [passos, titulo2([el("span", { texto: t("marcos_titulo") })]),
    x.marcos.length ? marcos : el("p", { classe: "vazio", texto: t("sem_marcos", { meta: x.id }) })], "t-jornada");

  var escolhas = el("div", { classe: "escolhas" }, SENTIMENTOS.map(function (s) {
    var botao = el("button", { classe: "escolha s-" + s, type: "button", "aria-pressed": x.sentimento === s ? "true" : "false", texto: t("coach.sentimento_" + s) });
    botao.addEventListener("click", function () { acao("/api/sentimento", { meta: x.id, valor: s }); });
    return botao;
  }));
  var sentir = card("", t("sentimento_titulo"), x.sentimento ? t("coach.sentimento_" + x.sentimento) : t("sentimento_nenhum"), [escolhas], "t-sentir");

  var horas = el("input", { id: "aj-horas", type: "number", min: "0.5", max: "40", step: "0.5", value: String(x.custo_h_semana) });
  var prazo = el("input", { id: "aj-prazo", type: "date", value: x.prazo });
  var impacto = el("select", { id: "aj-impacto" }, IMPACTOS.map(function (imp) { return el("option", { value: imp, texto: t("coach.impacto_" + imp) }); }));
  impacto.value = x.impacto;
  var objetivo = el("select", { id: "aj-objetivo" }, [el("option", { value: "", texto: t("sem_objetivo") })].concat(m.objetivos_opcoes.map(function (o) { return el("option", { value: o.id, texto: o.titulo }); })));
  objetivo.value = objetivoAtual;
  var salvar = el("button", { classe: "botao-escuro", type: "button", texto: t("salvar") });
  salvar.addEventListener("click", function () {
    var corpo = { meta: x.id };
    if (Number(horas.value) !== x.custo_h_semana) { corpo.custo = Number(horas.value); }
    if (prazo.value !== x.prazo) { corpo.prazo = prazo.value; }
    if (impacto.value !== x.impacto) { corpo.impacto = impacto.value; }
    if (objetivo.value !== objetivoAtual) { corpo.objetivo = objetivo.value; }
    if (Object.keys(corpo).length === 1) { return avisar(t("ajuste_igual", { meta: x.rotulo })); }
    acao("/api/meta/ajustar", corpo);
  });
  var pausada = x.estado_arquivo === "pausada";
  var pausar = el("button", { classe: "mini", type: "button", texto: pausada ? t("retomar") : t("pausar") });
  pausar.addEventListener("click", function () { acao("/api/meta/ajustar", { meta: x.id, estado: pausada ? "ativa" : "pausada" }); });
  var concluir = el("button", { classe: "mini", type: "button", texto: t("concluir") });
  concluir.hidden = x.estado_arquivo === "concluida";
  concluir.addEventListener("click", function () { acao("/api/meta/ajustar", { meta: x.id, estado: "concluida" }); });
  var campo = function (entrada, rotulo) { return el("div", { classe: "campo" }, [el("label", { "for": entrada.id, texto: rotulo }), entrada]); };
  var ajustes = card("", t("ajustes_titulo"), t("ajustes_detalhe"), [el("div", { classe: "form" }, [
    el("div", { classe: "campos" }, [campo(horas, t("horas_rotulo")), campo(prazo, t("prazo_campo")), campo(impacto, t("impacto_rotulo")), campo(objetivo, t("objetivo_rotulo"))]),
    el("div", { classe: "acoes-form" }, [salvar, pausar, concluir]),
  ])], "t-ajustes");

  var n = m.numeros;
  var par = function (rotulo, valor) { return valor === null || valor === undefined ? null : el("div", {}, [el("dt", { texto: rotulo }), el("dd", { texto: String(valor) })]); };
  var numeros = card("", t("numeros_titulo"), t("numeros_detalhe"), [el("dl", { classe: "numeros" }, [
    par(t("num_custo"), n.custo), par(t("num_semanas"), n.semanas), par(t("num_total"), n.total), par(t("num_feito"), n.feito),
    par(t("num_cobertura"), n.cobertura), n.decisao ? par(t("num_decisao"), t("saida_" + n.decisao)) : null,
  ])], "t-numeros");
  var evidencias = card("", t("evidencias_titulo"), null, [listaEvidencias(m.evidencias, false)], "t-evidencias");

  var grade = el("div", { classe: "grade" }, [
    el("div", { classe: "coluna col-7" }, [leitura, trilha, sinais, blocos]),
    el("div", { classe: "coluna col-5" }, [jornada, sentir, ajustes, numeros, evidencias]),
  ]);
  grade.style.setProperty("--cor", x.cor);
  return [cabeca({ voltar: voltar, antes: antes, titulo: x.titulo, sub: x.por_que, depois: depois }), grade];
}
