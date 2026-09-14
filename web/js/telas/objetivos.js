// Tela Objetivos: força de cada objetivo e o quanto cada meta o move.
import { el, t } from "../nucleo.js";
import { anelObjetivo, cabeca, card, chipMeta, pilulaEstado, pilulaNeutra, pilulaObjetivo, titulo2 } from "../pecas.js";

// --- Objetivos --------------------------------------------------------------------------

export function telaObjetivos(m) {
  var cards = m.objetivos.map(function (o) {
    var topo = el("div", { classe: "obj-topo" }, [
      el("div", { classe: "texto-par" }, [
        el("h3", { texto: o.titulo }),
        el("div", { classe: "pilulas" }, [pilulaObjetivo(o.estado)]),
        el("p", { classe: "sub", texto: o.alavanca ? t("coach.alavanca", { meta: o.alavanca.rotulo + " " + o.alavanca.titulo }) : t("coach.sem_alavanca") }),
      ]),
      anelObjetivo(o, 118),
    ]);
    var pares = o.implicito
      ? el("p", { classe: "sub", texto: t("coach.objetivo_implicito") })
      : el("div", { classe: "pares" }, [
        el("div", { classe: "texto-par" }, [el("small", { texto: t("por_que") }), el("p", { texto: o.por_que })]),
        el("div", { classe: "texto-par" }, [el("small", { texto: t("como_vou_saber") }), el("p", { texto: o.como_vou_saber })]),
      ]);
    var move = el("div", { classe: "move" }, o.metas.map(function (x) {
      var fatia = el("div", { classe: "fatia" });
      fatia.style.width = Math.round(Math.max(0.04, x.fatia) * 100) + "%";
      var cheio = el("i", {});
      cheio.style.width = x.fatia > 0 ? Math.round(Math.min(1, x.contribuicao / x.fatia) * 100) + "%" : "0%";
      fatia.appendChild(cheio);
      return el("a", { classe: "move-linha", href: "#/meta/" + x.id }, [
        el("div", { classe: "move-rot" }, [
          el("span", { classe: "titulo" }, [chipMeta(x), el("span", { texto: x.titulo })]),
          el("span", { classe: "pilulas" }, [pilulaNeutra(t("coach.impacto_" + x.impacto)), pilulaEstado(x.estado)]),
        ]),
        el("div", { classe: "trilho-peso", role: "img", "aria-label": x.titulo + ": " + t("coach.impacto_" + x.impacto) + ", " + t("coach.estado_" + x.estado) }, [fatia]),
      ]);
    }));
    var c = card("obj-card", null, null, [topo, pares, titulo2([el("span", { texto: t("move_titulo") })]), move, el("p", { classe: "legenda-mini", texto: t("move_legenda") })]);
    c.style.setProperty("--cor", o.cor);
    return c;
  });
  return [cabeca({ titulo: t("objetivos_pagina"), sub: t("objetivos_sub") }), el("div", { classe: "grade-objetivos" }, cards)];
}
