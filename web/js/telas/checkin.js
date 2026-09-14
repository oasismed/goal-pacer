// Tela Check-in: blocos a confirmar, como está cada meta, decisões e uma nota, num salvar só.
import { SENTIMENTOS, acao, avisar, el, t } from "../nucleo.js";
import { cabeca, cartaoDecisao, chipMeta } from "../pecas.js";

// --- Check-in ---------------------------------------------------------------------------

export function telaCheckin(m) {
  var rascunho = { blocos: {}, sentimentos: {} };
  var passo = function (n, titulo, detalhe) {
    return el("h2", {}, [el("span", {}, [el("span", { classe: "passo-num", texto: String(n) }), titulo]), detalhe ? el("small", { texto: detalhe }) : null]);
  };

  var lista = el("div", { classe: "lista" }, m.pendentes.map(function (b) {
    var sim = el("button", { classe: "sim", type: "button", "aria-pressed": "false", texto: t("fiz") });
    var nao = el("button", { classe: "nao", type: "button", "aria-pressed": "false", texto: t("nao_fiz") });
    var marcar = function (valor) {
      rascunho.blocos[b.id] = rascunho.blocos[b.id] === valor ? null : valor;
      sim.setAttribute("aria-pressed", rascunho.blocos[b.id] === "feita" ? "true" : "false");
      nao.setAttribute("aria-pressed", rascunho.blocos[b.id] === "nao_feita" ? "true" : "false");
    };
    sim.addEventListener("click", function () { marcar("feita"); });
    nao.addEventListener("click", function () { marcar("nao_feita"); });
    var titulo = el("div", { classe: "titulo" }, [chipMeta(b), el("span", { texto: b.titulo })]);
    if (b.presumida) { titulo.appendChild(el("span", { classe: "tag-estado", texto: t("feita_presumida") })); }
    return el("div", { classe: "ck-bloco" }, [el("div", {}, [el("div", { classe: "hora" }, [b.dia_curto + " · " + b.inicio]), titulo]),
      el("div", { classe: "alterna", role: "group", "aria-label": b.titulo }, [sim, nao])]);
  }));
  if (!m.pendentes.length) { lista.appendChild(el("p", { classe: "vazio", texto: t("sem_pendentes") })); }
  var feitos = el("section", { classe: "card" }, [passo(1, t("passo_feitos"), t("passo_feitos_detalhe")), lista]);

  var metas = el("div", { classe: "coluna" }, m.metas.map(function (x) {
    var botoes = SENTIMENTOS.map(function (s) {
      var botao = el("button", { classe: "escolha s-" + s, type: "button", "aria-pressed": "false", texto: t("coach.sentimento_" + s) });
      botao.addEventListener("click", function () {
        rascunho.sentimentos[x.id] = rascunho.sentimentos[x.id] === s ? null : s;
        botoes.forEach(function (outro, i) { outro.setAttribute("aria-pressed", rascunho.sentimentos[x.id] === SENTIMENTOS[i] ? "true" : "false"); });
      });
      return botao;
    });
    return el("div", { classe: "ck-meta" }, [el("div", { classe: "titulo" }, [chipMeta(x), el("span", { texto: x.titulo })]), el("div", { classe: "escolhas" }, botoes)]);
  }));
  metas.style.gap = "0";
  var sentir = el("section", { classe: "card" }, [passo(2, t("passo_sentir"), t("passo_sentir_detalhe")), metas]);

  var decisoes = m.decisoes.map(cartaoDecisao).filter(Boolean);
  if (decisoes.length) { decisoes[0].insertBefore(passo(3, t("decisoes_titulo")), decisoes[0].firstChild); }
  var nota = el("textarea", { id: "ck-nota", maxlength: "280", placeholder: t("nota_exemplo"), "aria-label": t("passo_nota") });
  var cardNota = el("section", { classe: "card" }, [passo(decisoes.length ? 4 : 3, t("passo_nota"), t("passo_nota_detalhe")), el("div", { classe: "campo" }, [nota])]);

  var salvar = el("button", { classe: "botao-escuro", type: "button", texto: t("salvar_checkin") });
  salvar.addEventListener("click", function () {
    var corpo = { feitas: [], nao_feitas: [], sentimentos: {}, nota: nota.value.trim() };
    Object.keys(rascunho.blocos).forEach(function (id) {
      if (rascunho.blocos[id] === "feita") { corpo.feitas.push(id); }
      if (rascunho.blocos[id] === "nao_feita") { corpo.nao_feitas.push(id); }
    });
    Object.keys(rascunho.sentimentos).forEach(function (id) { if (rascunho.sentimentos[id]) { corpo.sentimentos[id] = rascunho.sentimentos[id]; } });
    if (!corpo.feitas.length && !corpo.nao_feitas.length && !Object.keys(corpo.sentimentos).length && !corpo.nota) { return avisar(t("checkin_vazio"), true); }
    acao("/api/checkin", corpo);
  });

  return [
    cabeca({ titulo: t("nav_checkin"), sub: t("checkin_sub") }),
    el("div", { classe: "grade" }, [el("div", { classe: "coluna col-7" }, [feitos].concat(decisoes)), el("div", { classe: "coluna col-5" }, [sentir, cardNota])]),
    el("div", { classe: "barra-salvar" }, [el("span", { classe: "sub", texto: t("salvar_dica") }), salvar]),
  ];
}
