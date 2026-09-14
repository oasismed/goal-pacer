// Tela Status: execuções do job, configuração, celular na rede de casa e comandos do terminal.
import { acao, api, avisar, el, limpar, t } from "../nucleo.js";
import { cabeca, card } from "../pecas.js";
import { cardInstalarApp } from "./comecar.js";

// --- manutenção: doctor e atualizar, só no próprio computador --------------------------

export function cardManutencao(m) {
  var saida = el("div", { classe: "manutencao-saida", "aria-live": "polite" });
  var doctor = el("button", { classe: "botao-claro", type: "button", texto: t("manutencao_doctor") });
  doctor.addEventListener("click", function () {
    doctor.disabled = true;
    limpar(saida);
    saida.appendChild(el("p", { classe: "sub", texto: t("manutencao_conferindo") }));
    api("POST", "/api/doctor", {}).then(function (d) {
      limpar(saida);
      saida.appendChild(el("ul", { classe: "conferencia" }, d.itens.map(function (item) {
        return el("li", { classe: item.ok ? "ok" : "falta" }, [el("b", { texto: item.nome }), el("span", { texto: " " + item.detalhe })]);
      })));
    }).catch(function (erro) { limpar(saida); avisar(erro.message, true); }).then(function () { doctor.disabled = false; });
  });
  var atualizar = el("button", { classe: "botao-claro", type: "button", texto: t("manutencao_atualizar") });
  atualizar.addEventListener("click", function () {
    atualizar.disabled = true;
    api("POST", "/api/atualizar", {}).then(function (d) {
      avisar(d.mensagem);
      acompanharAtualizacao(saida, 0);
    }).catch(function (erro) { atualizar.disabled = false; avisar(erro.message, true); });
  });
  var confirmacao = el("div", { classe: "confirmar-remocao" });
  confirmacao.hidden = true;
  var remover = el("button", { classe: "botao-claro", type: "button", texto: t("manutencao_remover") });
  remover.addEventListener("click", function () {
    limpar(confirmacao);
    confirmacao.hidden = false;
    var sim = el("button", { classe: "botao-escuro", type: "button", texto: t("manutencao_remover_sim") });
    var nao = el("button", { classe: "botao-claro", type: "button", texto: t("comecar_voltar") });
    sim.addEventListener("click", function () {
      sim.disabled = true;
      api("POST", "/api/desinstalar", { confirmar: true }).then(function (d) { limpar(confirmacao); confirmacao.appendChild(el("p", { classe: "resumo", texto: d.mensagem })); }).catch(function (erro) { sim.disabled = false; avisar(erro.message, true); });
    });
    nao.addEventListener("click", function () { confirmacao.hidden = true; });
    confirmacao.appendChild(el("p", { classe: "sub", texto: t("manutencao_remover_explica") }));
    confirmacao.appendChild(el("div", { classe: "acoes-form" }, [sim, nao]));
  });
  var aviso = m.versao_nova ? el("p", { classe: "resumo", texto: t("manutencao_versao_nova", { versao: m.versao_nova }) }) : null;
  if (m.versao_nova) { atualizar.className = "botao-escuro"; }
  return card("", t("manutencao_titulo"), t("manutencao_detalhe", { versao: m.versao || "" }), [aviso, el("div", { classe: "acoes-form" }, [doctor, atualizar, remover]), confirmacao, saida], "t-manutencao");
}

// o update reinicia o painel: enquanto ele volta, as leituras falham e a tela espera; de volta, recarrega
export function acompanharAtualizacao(saida, tentativas) {
  api("GET", "/api/atualizacao").then(function (d) {
    limpar(saida);
    saida.appendChild(el("pre", { classe: "manutencao-log", texto: d.modelo.linhas.join("\n") }));
    if (d.modelo.rodando && tentativas < 200) { setTimeout(function () { acompanharAtualizacao(saida, tentativas + 1); }, 3000); }
  }).catch(function () {
    if (tentativas < 200) { setTimeout(function () { location.reload(); }, 5000); }
  });
}

// --- Status -----------------------------------------------------------------------------

export function cardRede(m) {
  var caixa = card("", t("rede_titulo"), t("rede_detalhe"), [], "t-rede");
  if (!m.rede) { caixa.appendChild(el("p", { classe: "sub", texto: t("rede_desligada") })); return caixa; }
  if (!m.local) { caixa.appendChild(el("p", { classe: "sub", texto: t("rede_so_mac") })); return caixa; }
  api("GET", "/api/pareamento").then(function (d) {
    var esquecer = el("button", { classe: "saida", type: "button", texto: t("rede_esquecer") });
    esquecer.hidden = d.aparelhos === 0;
    esquecer.addEventListener("click", function () { acao("/api/esquecer-aparelhos", {}); });
    caixa.appendChild(el("p", { classe: "sub", texto: t("rede_passos") }));
    caixa.appendChild(el("div", { classe: "rede-dados" }, [el("code", { classe: "rede-endereco", texto: d.endereco_rede || t("rede_sem_endereco") }),
      el("div", { classe: "rede-codigo" }, [el("small", { texto: t("rede_codigo") }), el("b", { texto: d.codigo || "" })])]));
    caixa.appendChild(el("div", { classe: "rede-rodape" }, [el("span", { classe: "sub", texto: d.aparelhos === 0 ? t("rede_aparelhos_zero") : d.aparelhos === 1 ? t("rede_aparelhos_um") : t("rede_aparelhos_n", { n: d.aparelhos }) }), esquecer]));
    caixa.appendChild(d.impressao
      ? el("p", { classe: "sub rede-impressao", texto: t("rede_impressao", { impressao: d.impressao }) })
      : el("p", { classe: "sub", texto: t("rede_aviso") }));
  }).catch(function () { caixa.appendChild(el("p", { classe: "sub", texto: t("rede_so_mac") })); });
  return caixa;
}

export function telaStatus(m) {
  var linhas = m.execucoes.map(function (e) {
    return el("tr", {}, [
      el("td", { classe: "num", texto: e.quando }),
      el("td", { classe: "mono", texto: e.modo }),
      el("td", {}, [e.ok ? el("span", { classe: "pilula e-florescendo", texto: t("execucao_ok") }) : el("span", { classe: "pilula e-travada", texto: e.classe || "" }),
        e.ok ? null : el("small", { texto: e.motivo + (e.acao ? ": " + e.acao : "") })]),
      el("td", { classe: "num", texto: e.tokens ? t("tokens", { n: e.tokens.toLocaleString(t("locale") || "pt-BR") }) : "" }),
      el("td", { classe: "num", texto: e.duracao ? t("segundos", { n: e.duracao }) : "" }),
    ]);
  });
  var tabela = m.execucoes.length
    ? el("div", { classe: "tabela-rolagem" }, [el("table", {}, [el("tbody", {}, linhas)])])
    : el("p", { classe: "vazio", texto: t("sem_execucoes") });
  var execucoes = card("", t("execucoes_titulo"), t("execucoes_detalhe"), [tabela, el("p", { classe: "sub", texto: t("proximo_job", { quando: m.proximo }) })], "t-exec");
  var par = function (rotulo, valor) { return el("div", {}, [el("dt", { texto: rotulo }), el("dd", { texto: valor })]); };
  var config = card("", t("config_titulo"), null, [el("dl", { classe: "config" }, [
    par(t("fuso_rotulo"), m.fuso),
    par(t("horario_rotulo"), m.horario.map(function (h) { return h.dias + " " + h.faixa; }).join(" · ")),
    par(t("fontes_rotulo"), m.fontes.join(", ")),
    par(t("cadastro_rotulo"), t("cadastro_texto", { metas: m.n_metas, objetivos: m.n_objetivos })),
  ])], "t-config");
  var comandos = card("", t("comandos_titulo"), t("comandos_detalhe"), [el("ul", { classe: "comandos" }, ["diario", "mensal", "doctor"].map(function (c) {
    return el("li", {}, [el("code", { texto: t("comando_" + c) }), el("span", { classe: "sub", texto: t("comando_" + c + "_texto") })]);
  }))], "t-comandos");
  var tela = [cabeca({ titulo: t("nav_status"), sub: t("status_sub") })];
  if (m.silencio) { tela.push(el("p", { classe: "aviso", texto: m.silencio })); }
  var direita = [config, cardRede(m), m.local ? cardManutencao(m) : null, m.local ? cardInstalarApp(m) : null, comandos];
  tela.push(el("div", { classe: "grade" }, [el("div", { classe: "coluna col-7" }, [execucoes]), el("div", { classe: "coluna col-5" }, direita)]));
  return tela;
}
