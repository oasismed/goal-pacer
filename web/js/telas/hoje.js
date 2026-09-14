// Tela Hoje (e #/dia/<data>): blocos do dia, anéis dos horizontes, objetivos, metas e espaço do mês.
import { el, svg, t } from "../nucleo.js";
import { anelObjetivo, arco, cabeca, card, cartaoDecisao, chipMeta, linhaBloco, navegacaoHorizonte, pilulaEstado, pilulaNeutra, pilulaObjetivo, semanasEspaco, setas } from "../pecas.js";

// --- Hoje -------------------------------------------------------------------------------

export function aneisHorizontes(horizontes) {
  var raios = { hoje: 40, semana: 58, mes: 76 };
  var desenho = svg("svg", { viewBox: "0 0 172 172", role: "img", "aria-label": horizontes.map(function (h) { return t("coach.horizonte_" + h.nome) + ": " + t(h.leitura); }).join(", ") });
  horizontes.slice().reverse().forEach(function (h) { desenho.appendChild(arco(86, 86, raios[h.nome], h.valor, "var(--anel-" + h.nome + ")", 13)); });
  var legenda = el("div", { classe: "legenda" }, horizontes.map(function (h) {
    var bola = el("i", {});
    bola.style.background = "var(--anel-" + h.nome + ")";
    return el("div", { classe: "item" }, [bola, el("div", {}, [
      el("span", { classe: "nome" }, [t("coach.horizonte_" + h.nome) + " · ", el("em", { texto: t("coach.horizonte_" + h.nome + "_leitura") })]),
      el("b", { texto: t(h.leitura) }),
    ])]);
  }));
  return el("div", { classe: "aneis" }, [desenho, legenda]);
}

export function telaHoje(m) {
  var ids = { dia: m.data };
  m.trilha.forEach(function (p) { ids[p.nivel] = p.id; });
  var acoes = el("div", { classe: "cabeca-acoes" }, [
    m.e_hoje ? null : el("a", { classe: "link", href: "#/hoje", texto: t("voltar_hoje") }),
    setas("#/dia/" + m.anterior, "#/dia/" + m.proximo, t("dia_anterior"), t("dia_seguinte")),
  ]);
  var tela = [navegacaoHorizonte(m.trilha, "dia", ids), cabeca({ selo: m.titulo_dia, titulo: m.manchete, sub: m.sub, depois: acoes })];
  if (m.silencio) { tela.push(el("p", { classe: "aviso", texto: m.silencio })); }

  var lista = el("div", { classe: "lista" }, m.blocos.map(function (b) { return linhaBloco(b); }));
  if (!m.blocos.length) { lista.appendChild(el("p", { classe: "vazio", texto: t("sem_blocos") })); }
  var cardHoje = card("", t("hoje_titulo"), m.agenda_google === false ? t("hoje_detalhe_app") : t("hoje_detalhe"), [lista], "t-hoje");
  if (m.desde) {
    cardHoje.appendChild(el("p", { classe: "sub", texto: t("desde", { dia: m.desde.dia }) }));
    cardHoje.appendChild(el("div", { classe: "pilulas" }, (m.desde.contagem ? m.desde.contagem.split(" · ") : []).map(pilulaNeutra)));
  }
  var esquerda = [cardHoje].concat(m.decisoes.map(cartaoDecisao));
  if (m.avisos.length) {
    esquerda.push(card("avisos", t("avisos_titulo"), null, [el("ul", {}, m.avisos.map(function (a) { return el("li", { texto: a }); }))], "t-avisos"));
  }

  var cardAneis = card("manchete-card", t("aneis_titulo"), t("aneis_detalhe"), [aneisHorizontes(m.horizontes)], "t-aneis");
  if (m.alavanca) {
    const a = m.alavanca;
    cardAneis.appendChild(el("a", { classe: "alavanca", href: "#/meta/" + a.id, cor: a.cor }, [
      el("small", { texto: t("alavanca_titulo") }),
      el("div", { classe: "titulo" }, [chipMeta(a), el("span", { texto: a.titulo })]),
      el("div", { classe: "pilulas" }, [pilulaEstado(a.estado), el("span", { classe: "link", texto: t("abrir_meta", { meta: a.rotulo }) })]),
    ]));
  }

  var objetivos = el("div", { classe: "objetivos-lista" }, m.objetivos.map(function (o) {
    var fatias = el("div", { classe: "fatias", "aria-hidden": "true" }, o.metas.map(function (x) {
      var i = el("i", { title: x.rotulo + ": " + t("coach.estado_" + x.estado) });
      i.style.flex = String(Math.max(0.08, x.fatia));
      i.style.setProperty("--c", "var(--" + x.estado + ")");
      return i;
    }));
    return el("a", { classe: "obj-linha", href: "#/objetivos" }, [anelObjetivo(o, 52), el("div", {}, [el("div", { classe: "nome", texto: o.titulo }), fatias]), pilulaObjetivo(o.estado)]);
  }));
  var cardObjetivos = card("", t("objetivos_card"), t("objetivos_card_detalhe"), [objetivos], "t-objetivos");

  var metas = el("div", { classe: "metas-linhas" }, m.metas.map(function (x) {
    return el("a", { classe: "meta-linha", href: "#/meta/" + x.id }, [el("span", { classe: "nome" }, [chipMeta(x), el("span", { texto: x.titulo })]), pilulaEstado(x.estado)]);
  }));
  var verTodas = el("a", { classe: "link", href: "#/metas", texto: t("ver_todas") });
  verTodas.style.justifySelf = "start";
  var direita = [cardAneis, cardObjetivos, card("", t("metas_card"), t("metas_card_detalhe"), [metas, verTodas], "t-metas")];
  if (m.espaco) {
    direita.push(card("", t("espaco_titulo", { mes: m.mes_nome }), t("espaco_detalhe"), [
      el("div", { classe: "palavra f-" + m.espaco.faixa, texto: t("coach.espaco_" + m.espaco.faixa) }),
      el("p", { classe: "sub", texto: m.espaco.texto }),
      semanasEspaco(m.espaco.semanas, true),
    ], "t-espaco"));
  }
  tela.push(el("div", { classe: "grade" }, [el("div", { classe: "coluna col-7" }, esquerda), el("div", { classe: "coluna col-5" }, direita)]));
  return tela;
}
