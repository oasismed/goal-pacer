// Tela Conexões: provedor de IA, estado de cada conector (visto pelo doctor e pelos jobs) e fontes dos sinais do mês.
// O painel não chama conector: só mostra o que o doctor e os jobs gravaram e liga ou desliga fontes pelo /api/fonte.
import { acao, el, t } from "../nucleo.js";
import { cabeca, card } from "../pecas.js";

export var CLASSE_DO_ESTADO = {
  conectado: "e-florescendo", com_export: "e-florescendo",
  reconectar: "e-travada",
  desconectado: "e-pausada", sem_export: "e-pausada",
  sem_verificacao: "e-atencao", provedor: "e-atencao",
};

function linhaConexao(c) {
  var fonte = null;
  if (c.fonte) {
    const botao = el("button", { classe: "botao-claro", type: "button", "aria-pressed": c.ativa ? "true" : "false", texto: c.ativa ? t("fonte_tirar") : t("fonte_usar") });
    botao.addEventListener("click", function () { acao("/api/fonte", { fonte: c.fonte, ativa: !c.ativa }); });
    fonte = el("div", { classe: "conexao-fonte" }, [el("span", { classe: "sub", texto: c.ativa ? t("fonte_nos_sinais") : t("fonte_fora_dos_sinais") }), botao]);
  }
  return el("li", { classe: "conexao", "data-conexao": c.id }, [
    el("div", { classe: "conexao-topo" }, [
      el("div", { classe: "conexao-nome" }, [el("b", { texto: c.nome }), el("small", { texto: c.papel })]),
      el("span", { classe: "pilula " + (CLASSE_DO_ESTADO[c.estado] || "e-atencao"), texto: c.estado_texto }),
    ]),
    c.linhas.length ? el("ul", { classe: "conexao-linhas" }, c.linhas.map(function (l) { return el("li", { texto: l }); })) : null,
    fonte,
  ]);
}

export function telaConexoes(m) {
  var lista = card("", t("conexoes_lista_titulo"), t("conexoes_lista_detalhe"), [el("ul", { classe: "conexoes" }, m.conexoes.map(linhaConexao))], "t-conexoes");
  var provedor = card("", t("provedor_titulo"), null, [
    el("p", { classe: "resumo", texto: m.provedor }),
    el("p", { classe: "sub", texto: m.onde }),
    el("p", { classe: "sub", texto: m.verificado }),
    el("ul", { classe: "comandos" }, [el("li", {}, [el("code", { texto: t("comando_verificar") }), el("span", { classe: "sub", texto: t("comando_verificar_texto") })])]),
  ], "t-provedor");
  var outros = card("", t("outros_titulo"), null, [el("p", { classe: "sub", texto: t("outros_texto") })], "t-outros");
  var tela = [cabeca({ titulo: t("nav_conexoes"), sub: t("conexoes_sub") })];
  if (m.problema) { tela.push(el("p", { classe: "aviso", texto: m.problema })); }
  tela.push(el("div", { classe: "grade" }, [el("div", { classe: "coluna col-7" }, [lista]), el("div", { classe: "coluna col-5" }, [provedor, outros])]));
  return tela;
}
