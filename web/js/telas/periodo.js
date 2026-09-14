// Tela Horizontes (#/periodo/<nivel>/<id>): leitura do período, partes, metas do nível e, no mês, espaço e decisões.
import { el, svg, t } from "../nucleo.js";
import { anelMini, arco, cabeca, card, cartaoDecisao, chipMeta, classeLeitura, hrefPeriodo, linhaMetaPeriodo, listaEvidencias, navegacaoHorizonte, pilulaEstado, pilulaNeutra, semanasEspaco, setas } from "../pecas.js";

export function telaPeriodo(m) {
  var ids = {};
  m.niveis.forEach(function (n) { ids[n.nivel] = n.id; });
  var tela = [navegacaoHorizonte(m.trilha, m.nivel, ids)];
  tela.push(cabeca({
    selo: t("nivel_" + m.nivel), titulo: m.titulo, sub: m.intervalo,
    depois: el("div", { classe: "cabeca-acoes" }, [
      el("span", { classe: "pilula sem-ponto fase-" + m.fase, texto: t("fase_" + m.fase) }),
      setas(hrefPeriodo(m.nivel, m.anterior), hrefPeriodo(m.nivel, m.proximo), t("anterior"), t("proximo")),
    ]),
  }));

  var raio = { tempo: 76, leitura: 56 };
  var desenho = svg("svg", { viewBox: "0 0 172 172", role: "img", "aria-label": t("fase_" + m.fase) + ", " + t(m.leitura.chave) });
  desenho.appendChild(arco(86, 86, raio.tempo, m.fase === "futuro" ? null : m.tempo, "var(--tinta)", 8));
  desenho.appendChild(arco(86, 86, raio.leitura, m.leitura.valor, "var(--verde)", 16));
  var leitura = card("manchete-card", t("leitura_periodo"), t("tempo_detalhe"), [
    el("div", { classe: "aneis" }, [desenho, el("div", { classe: "legenda" }, [
      el("div", { classe: "palavra " + classeLeitura(m.leitura.chave), texto: t(m.leitura.chave) }),
      el("p", { classe: "sub", texto: m.leitura.frase }),
    ])]),
  ], "t-leitura-periodo");
  if (m.alavanca) {
    const a = m.alavanca;
    leitura.appendChild(el("a", { classe: "alavanca", href: "#/meta/" + a.id, cor: a.cor }, [
      el("small", { texto: t("alavanca_titulo") }),
      el("div", { classe: "titulo" }, [chipMeta(a), el("span", { texto: a.titulo })]),
      el("div", { classe: "pilulas" }, [pilulaEstado(a.estado), a.compasso ? pilulaNeutra(t("coach.compasso_" + a.compasso)) : null]),
    ]));
  }

  var nivelFilho = m.filhos.length ? m.filhos[0].nivel : null;
  var partes = el("div", { classe: "partes partes-" + nivelFilho }, m.filhos.map(function (f) {
    var info = [];
    if (f.prazos) { info.push(el("span", { texto: f.prazos === 1 ? t("prazos_um") : t("prazos_n", { n: f.prazos }) })); }
    if (f.blocos) {
      info.push(f.blocos.length
        ? el("span", { classe: "chips-blocos" }, f.blocos.map(function (x) { return el("i", { classe: x.feita ? "feita" : "", cor: x.cor, title: x.rotulo_meta }); }))
        : el("span", { texto: t("sem_blocos_dia") }));
    }
    return el("a", { classe: "parte fase-" + f.fase + (f.fase === "atual" || f.hoje ? " agora" : ""), href: hrefPeriodo(f.nivel, f.id) }, [
      anelMini(f.valor, 44, f.fase === "futuro"),
      el("div", { classe: "parte-texto" }, [
        el("b", { texto: f.rotulo }),
        f.intervalo ? el("small", { texto: f.intervalo }) : null,
        el("span", { classe: "leitura-curta " + classeLeitura(f.leitura), texto: t(f.leitura) }),
        info.length ? el("span", { classe: "linha-info" }, info) : null,
      ]),
    ]);
  }));
  var cardPartes = card("col-12", t("partes_" + nivelFilho), t("partes_detalhe"), [partes], "t-partes");

  var esquerda = [leitura], direita = [];
  if (["trimestre", "semestre", "ano"].indexOf(m.nivel) >= 0) {
    direita.push(card("", t("metas_do_" + m.nivel), null, [m.metas_nivel.length
      ? el("div", { classe: "metas-linhas" }, m.metas_nivel.map(linhaMetaPeriodo))
      : el("p", { classe: "vazio", texto: t("sem_metas_nivel") })], "t-metas-nivel"));
    if (m.metas_acima.length) {
      direita.push(card("", t("metas_acima"), null, [el("div", { classe: "metas-linhas" }, m.metas_acima.map(linhaMetaPeriodo))], "t-metas-acima"));
    }
    if (m.metas_abaixo.length) {
      direita.push(card("", t("metas_abaixo"), null, [el("div", { classe: "metas-linhas" }, m.metas_abaixo.map(linhaMetaPeriodo))], "t-metas-abaixo"));
    }
  } else if (m.metas_acima.length) {
    direita.push(card("", t("metas_em_jogo"), null, [el("div", { classe: "metas-linhas" }, m.metas_acima.map(linhaMetaPeriodo))], "t-metas-jogo"));
  }
  if (m.nivel === "mes") {
    if (m.espaco) {
      esquerda.push(card("", t("semanas_titulo"), t("semanas_detalhe"), [
        el("div", { classe: "palavra f-" + m.espaco.faixa, texto: t("coach.espaco_" + m.espaco.faixa) }),
        el("p", { classe: "sub", texto: m.espaco.texto }),
        semanasEspaco(m.espaco.semanas, false),
      ], "t-semanas"));
    } else if (m.sem_plano) {
      esquerda.push(el("p", { classe: "vazio", texto: m.sem_plano }));
    }
    if (m.resumo) { esquerda.push(card("", t("resumo_titulo"), null, [el("p", { classe: "resumo", texto: m.resumo })], "t-resumo")); }
    m.decisoes.map(cartaoDecisao).filter(Boolean).forEach(function (c) { direita.unshift(c); });
    if (m.evidencias.length) { direita.push(card("", t("evidencias_titulo"), null, [listaEvidencias(m.evidencias, true)], "t-evid-mes")); }
  }
  tela.push(el("div", { classe: "grade" }, [cardPartes, el("div", { classe: "coluna col-5" }, esquerda), el("div", { classe: "coluna col-7" }, direita)]));
  return tela;
}
