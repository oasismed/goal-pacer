// Tela Metas: mapa de energia (impacto por tração) e um cartão por meta.
import { IMPACTOS, el, svg, t } from "../nucleo.js";
import { cabeca, card, chipMeta, faisca, jornadaSegmentos, pilulaEstado, pilulaNeutra } from "../pecas.js";

// --- Metas ------------------------------------------------------------------------------

// impacto (linhas) por tração (colunas), com as divisões do backend (tração 0,5; impacto importante ou mais).
// Os nomes dos quadrantes ficam fora da área dos pontos: em cima os de alto impacto, embaixo os de apoio.
export function mapaEnergia(metas) {
  var L = 110, R = 20, T = 66, linha = 92, W = 1000 - L - R, H = linha * 3, meio = L + W / 2;
  var desenho = svg("svg", { "class": "mapa", viewBox: "0 0 1000 " + (T + H + 84), role: "group", "aria-label": t("mapa_titulo") });
  var quadrantes = [
    [L, T, W / 2, 2 * linha, "destravar", "atencao", "start", 26], [meio, T, W / 2, 2 * linha, "proteger", "florescendo", "end", 26],
    [L, T + 2 * linha, W / 2, linha, "repensar", "pausada", "start", T + H + 50], [meio, T + 2 * linha, W / 2, linha, "manter_leve", "ritmo", "end", T + H + 50],
  ];
  quadrantes.forEach(function (q) {
    var x = q[6] === "start" ? q[0] + 6 : q[0] + q[2] - 6;
    desenho.appendChild(svg("rect", { x: q[0] + 3, y: q[1] + 3, width: q[2] - 6, height: q[3] - 6, rx: 20, estilo: "fill:var(--" + q[5] + "-bg);fill-opacity:0.78" }));
    desenho.appendChild(svg("text", { x: x, y: q[7], "text-anchor": q[6], "font-size": "15", "font-weight": "800", estilo: "fill:var(--" + q[5] + ")", texto: t("coach.quadrante_" + q[4]) }));
    desenho.appendChild(svg("text", { x: x, y: q[7] + 19, "text-anchor": q[6], "font-size": "12.5", fill: "#5F6670", texto: t("coach.quadrante_" + q[4] + "_texto") }));
  });
  IMPACTOS.forEach(function (imp, i) {
    desenho.appendChild(svg("text", { x: L - 14, y: T + linha * i + linha / 2 + 5, "text-anchor": "end", "font-size": "13.5", "font-weight": "700", fill: "#5F6670", texto: t("coach.impacto_" + imp) }));
  });
  desenho.appendChild(svg("text", { x: meio - 14, y: T + H + 22, "text-anchor": "end", "font-size": "12.5", "font-weight": "600", fill: "#858B94", texto: "← " + t("mapa_pouca") + " " + t("mapa_tracao") }));
  desenho.appendChild(svg("text", { x: meio + 14, y: T + H + 22, "text-anchor": "start", "font-size": "12.5", "font-weight": "600", fill: "#858B94", texto: t("mapa_boa") + " " + t("mapa_tracao") + " →" }));
  var usados = {};
  metas.forEach(function (x) {
    var fila = IMPACTOS.indexOf(x.impacto);
    var cx = L + Math.max(0.05, Math.min(0.95, x.tracao)) * W;
    usados[fila] = usados[fila] || [];
    var vizinhos = usados[fila].filter(function (outro) { return Math.abs(outro - cx) < 46; }).length;
    usados[fila].push(cx);
    var cy = T + linha * fila + linha / 2 + (vizinhos ? (vizinhos % 2 ? -22 : 22) : 0);
    var ponto = svg("g", { "class": "ponto", tabindex: "0", role: "link", "aria-label": x.titulo + ": " + t("coach.estado_" + x.estado) + ", " + t("coach.quadrante_" + x.quadrante) });
    ponto.appendChild(svg("title", { texto: x.rotulo + " " + x.titulo + " · " + t("coach.estado_" + x.estado) }));
    ponto.appendChild(svg("circle", { "class": "aro", cx: cx, cy: cy, r: 23, estilo: "fill:#FFFFFF;stroke:" + x.cor + ";stroke-width:2;stroke-opacity:0.35" }));
    ponto.appendChild(svg("circle", { cx: cx, cy: cy, r: 18, estilo: "fill:" + x.cor }));
    ponto.appendChild(svg("text", { x: cx, y: cy + 5, "text-anchor": "middle", "font-size": "13", "font-weight": "800", fill: "#FFFFFF", texto: x.rotulo }));
    var ir = function () { location.hash = "#/meta/" + x.id; };
    ponto.addEventListener("click", ir);
    ponto.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ir(); } });
    desenho.appendChild(ponto);
  });
  return desenho;
}

export function cartaoMeta(x, objetivos) {
  var objetivo = x.objetivo && objetivos[x.objetivo];
  return el("a", { classe: "meta-card", href: "#/meta/" + x.id, cor: x.cor }, [
    el("div", { classe: "meta-topo" }, [el("div", { classe: "titulo" }, [chipMeta(x), el("h3", { texto: x.titulo })]), pilulaEstado(x.estado)]),
    el("div", { classe: "linha-info" }, [
      objetivo && !objetivo.implicito ? el("span", { classe: "chip-obj", cor: objetivo.cor, texto: objetivo.titulo }) : null,
      pilulaNeutra(t("coach.impacto_" + x.impacto)),
      el("span", { texto: t("horizonte_meta_" + x.horizonte) + " · " + t("prazo_data", { data: x.prazo_curto }) + (x.prazo_externo ? " · " + t("prazo_externo") : "") }),
    ]),
    el("div", {}, [
      el("div", { classe: "jornada-rot" }, [el("span", {}, [t("jornada") + ": ", el("b", { texto: t("coach.estagio_" + x.estagio) })]),
        el("span", { texto: x.tendencia ? t("coach.tendencia_" + x.tendencia) : t("coach.tendencia_sem_sinal") })]),
      jornadaSegmentos(x.estagio),
    ]),
    faisca(x.trilha, x.cor),
    el("div", { classe: "linha-info" }, [
      el("span", { texto: x.sentimento ? t("coach.sentimento_" + x.sentimento) : t("sentimento_nenhum") }),
      el("span", { texto: "·" }),
      el("span", { texto: x.compasso ? t("coach.compasso_" + x.compasso) : t("coach.quadrante_" + x.quadrante) }),
    ]),
  ]);
}

export function telaMetas(m) {
  var legenda = el("div", { classe: "pilulas" }, Object.keys(m.objetivos).filter(function (k) { return !m.objetivos[k].implicito; }).map(function (k) {
    return el("span", { classe: "chip-obj", cor: m.objetivos[k].cor, texto: m.objetivos[k].titulo });
  }));
  var ativas = m.metas.filter(function (x) { return x.estado_arquivo === "ativa"; });
  return [
    cabeca({ titulo: t("metas_pagina"), sub: t("metas_sub") }),
    el("div", { classe: "grade" }, [
      card("col-12", t("mapa_titulo"), t("mapa_detalhe"), [el("div", { classe: "tabela-rolagem" }, [mapaEnergia(ativas)]), legenda], "t-mapa"),
      card("col-12", t("lista_titulo"), null, [el("div", { classe: "metas-grade" }, m.metas.map(function (x) { return cartaoMeta(x, m.objetivos); }))], "t-lista"),
    ]),
  ];
}
