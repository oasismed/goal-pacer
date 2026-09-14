// Goal Pacer, painel local. Seções por hash (#/hoje, #/dia/2026-09-25, #/horizontes, #/periodo/trimestre/2026-T4, #/objetivos,
// #/metas, #/meta/M01, #/checkin, #/status, #/conexoes, #/comecar), cada uma montada do modelo de scripts/painel.py por um módulo em js/telas/.
// A tela fala em leituras qualitativas: os números (0 a 1) só desenham anéis, mapas e trilhas; o texto vem de
// modelo.textos (grupos "painel" e "coach" do copy). Nenhum dado vira HTML. Módulos nativos do navegador, sem build:
//
//   app.js            navegação por hash e carga de cada tela
//   js/nucleo.js      textos, criação de nós, CSSOM, avisos, API com token, gravação
//   js/pecas.js       peças compartilhadas (pílulas, cartões, anéis, blocos, decisão, horizonte)
//   js/telas/*.js     uma tela por arquivo; tela nova = um arquivo + uma linha em DESENHOS
import { $, NIVEIS, ROTAS, aoRecarregar, api, avisar, definirTextos, el, limpar, marcarRolagem, t, temTexto } from "./js/nucleo.js";
import { telaHoje } from "./js/telas/hoje.js";
import { telaPeriodo } from "./js/telas/periodo.js";
import { telaObjetivos } from "./js/telas/objetivos.js";
import { telaMetas } from "./js/telas/metas.js";
import { telaMeta } from "./js/telas/meta.js";
import { telaCheckin } from "./js/telas/checkin.js";
import { telaStatus } from "./js/telas/status.js";
import { telaConexoes } from "./js/telas/conexoes.js";
import { telaComecar } from "./js/telas/comecar.js";

var atual = { tela: null, parametro: null };

// --- navegação --------------------------------------------------------------------------

var DESENHOS = { hoje: telaHoje, objetivos: telaObjetivos, metas: telaMetas, meta: telaMeta, periodo: telaPeriodo, checkin: telaCheckin, status: telaStatus, conexoes: telaConexoes, comecar: telaComecar };

// devolve {tela, parametro, rota}; parâmetros com formato estrito, o servidor valida de novo
function lerHash() {
  var partes = (location.hash || "#/hoje").replace(/^#\/?/, "").split("/");
  if (partes[0] === "dia" && /^\d{4}-\d{2}-\d{2}$/.test(partes[1] || "")) {
    return { tela: "hoje", parametro: partes[1], rota: ROTAS.hoje + "?data=" + partes[1] };
  }
  if (partes[0] === "horizontes") { return { tela: "periodo", parametro: "ano", rota: ROTAS.periodo + "?nivel=ano" }; }
  if (partes[0] === "periodo" && NIVEIS.indexOf(partes[1]) >= 0 && partes[1] !== "dia") {
    const id = /^[0-9A-Z-]{4,10}$/.test(partes[2] || "") ? partes[2] : "";
    return { tela: "periodo", parametro: partes[1] + "/" + id, rota: ROTAS.periodo + "?nivel=" + partes[1] + (id ? "&id=" + id : "") };
  }
  if (partes[0] === "meta" && /^M[0-9]{2}$/.test(partes[1] || "")) { return { tela: "meta", parametro: partes[1], rota: ROTAS.meta + partes[1] }; }
  var tela = DESENHOS[partes[0]] && ["meta", "periodo"].indexOf(partes[0]) < 0 ? partes[0] : "hoje";
  return { tela: tela, parametro: null, rota: ROTAS[tela] };
}

// o painel reiniciado (update, agente do login) tem token novo: a página recarrega uma vez, nunca em laço
function recarregarUmaVez() {
  var agora = Date.now();
  try {
    if (agora - Number(sessionStorage.getItem("gp-recarga") || 0) < 15000) { return false; }
    sessionStorage.setItem("gp-recarga", String(agora));
  } catch { return false; }
  location.reload();
  return true;
}

function avisoVazio() {
  return el("section", { classe: "aviso-vazio", role: "note" }, [
    el("div", {}, [el("strong", { texto: t("vazio_titulo") }), el("p", { classe: "sub", texto: t("vazio_texto") })]),
    el("a", { classe: "botao-escuro", href: "#/comecar", texto: t("vazio_acao") }),
  ]);
}

function carregar(manterRolagem) {
  var destino = lerHash();
  var mudou = destino.tela !== atual.tela || destino.parametro !== atual.parametro;
  atual = destino;
  var tela = $("tela");
  tela.setAttribute("aria-busy", "true");
  return api("GET", destino.rota).then(function (d) {
    var agora = lerHash();
    if (agora.tela !== destino.tela || agora.parametro !== destino.parametro) { return; }
    definirTextos(d.modelo.textos);
    document.querySelectorAll("[data-t]").forEach(function (no) { no.textContent = t(no.getAttribute("data-t")); });
    document.querySelectorAll("[data-t-rotulo]").forEach(function (no) { no.setAttribute("aria-label", t(no.getAttribute("data-t-rotulo"))); });
    document.querySelectorAll("#nav a").forEach(function (a) {
      var alvo = a.getAttribute("data-tela");
      if (alvo === destino.tela || (destino.tela === "meta" && alvo === "metas")) { a.setAttribute("aria-current", "page"); } else { a.removeAttribute("aria-current"); }
    });
    $("selo-demo").hidden = !d.demo;
    // sem onboarding: quem abre o painel pela primeira vez vai à tela Começar; nas outras telas, tudo vazio e um convite
    if (d.vazio && !location.hash) { location.hash = "#/comecar"; return; }
    var rolagem = window.scrollY;
    limpar(tela);
    if (d.vazio) { tela.appendChild(avisoVazio()); }
    DESENHOS[destino.tela](d.modelo).forEach(function (no) { if (no) { tela.appendChild(no); } });
    document.title = t("titulo_pagina") + " · " + t("nav_" + ({ meta: "metas", periodo: "horizontes", comecar: "comecar" }[destino.tela] || destino.tela));
    $("rodape").textContent = t("rodape", { endereco: d.endereco });
    tela.setAttribute("aria-busy", "false");
    window.scrollTo(0, manterRolagem && !mudou ? rolagem : 0);
    document.querySelectorAll(".nav, .niveis").forEach(marcarRolagem);
  }).catch(function (erro) {
    tela.setAttribute("aria-busy", "false");
    if (erro.classe === "SemOnboarding" && destino.tela !== "comecar") { location.hash = "#/comecar"; return; }
    if (erro.status === 403 && recarregarUmaVez()) { return; }
    avisar(temTexto("erro_carregar") ? t("erro_carregar", { erro: erro.message }) : erro.message, true);
  });
}

// módulos rodam depois do HTML lido (como defer): dá para ligar os eventos já
aoRecarregar(carregar);
$("atualizar").addEventListener("click", function () { carregar(true); });
window.addEventListener("hashchange", function () { carregar(false); });
carregar(false);
