// Núcleo do painel: estado dos textos, criação de nós só por createElement e textContent, CSSOM, avisos e chamadas à API com o token.

export var TOKEN = (document.querySelector('meta[name="gp-token"]') || {}).content || "";
export var NS = "http://www.w3.org/2000/svg";
export var ROTAS = { hoje: "/api/painel", objetivos: "/api/objetivos", metas: "/api/metas", meta: "/api/meta?id=", periodo: "/api/periodo", checkin: "/api/checkin", status: "/api/status", conexoes: "/api/conexoes", comecar: "/api/comecar" };
export var NIVEIS = ["ano", "semestre", "trimestre", "mes", "semana", "dia"];
export var ESTAGIOS = ["comeco", "construcao", "consolidacao", "reta_final", "conquista"];
export var IMPACTOS = ["essencial", "importante", "apoio"];
export var SENTIMENTOS = ["energia", "firme", "pesada"];
export var FAIXAS_TRACAO = [[0, 0.3, "travada"], [0.3, 0.5, "atencao"], [0.5, 0.7, "ritmo"], [0.7, 1, "florescendo"]];
var textos = {};
var ocupado = false;
var recarregar = function () { return Promise.resolve(); };

// --- utilidades -------------------------------------------------------------------------

export function $(id) { return document.getElementById(id); }

export function t(chave, valores) {
  var texto = textos[chave] || "";
  Object.keys(valores || {}).forEach(function (k) { texto = texto.split("{" + k + "}").join(String(valores[k])); });
  return texto;
}

export function el(tag, attrs, filhos) {
  var no = document.createElement(tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (attrs[k] === undefined || attrs[k] === null) { return; }
    if (k === "texto") { no.textContent = attrs[k]; }
    else if (k === "classe") { no.className = attrs[k]; }
    else if (k === "cor") { no.style.setProperty("--cor", attrs[k]); }
    else { no.setAttribute(k, attrs[k]); }
  });
  (filhos || []).forEach(function (f) { if (f) { no.appendChild(typeof f === "string" ? document.createTextNode(f) : f); } });
  return no;
}

export function svg(tag, attrs, filhos) {
  var no = document.createElementNS(NS, tag);
  Object.keys(attrs || {}).forEach(function (k) {
    if (k === "texto") { no.textContent = attrs[k]; }
    else if (k === "estilo") { estilizar(no, attrs[k]); }
    else { no.setAttribute(k, attrs[k]); }
  });
  (filhos || []).forEach(function (f) { if (f) { no.appendChild(f); } });
  return no;
}

// CSP style-src 'self' recusa o atributo style; propriedade a propriedade pelo CSSOM é permitido
export function estilizar(no, declaracoes) {
  declaracoes.split(";").forEach(function (par) {
    var i = par.indexOf(":");
    if (i > 0) { no.style.setProperty(par.slice(0, i).trim(), par.slice(i + 1).trim()); }
  });
}

export function limpar(no) { while (no.firstChild) { no.removeChild(no.firstChild); } }

export function avisar(mensagem, erro) {
  var toast = $("toast");
  toast.textContent = mensagem;
  toast.className = "toast" + (erro ? " erro" : "");
  toast.hidden = false;
  clearTimeout(avisar.timer);
  avisar.timer = setTimeout(function () { toast.hidden = true; }, erro ? 6000 : 3400);
}

export function lembrar(chave, valor) {
  try { if (valor === undefined) { return localStorage.getItem(chave); } localStorage.setItem(chave, valor); } catch { return null; }
  return null;
}

export function api(metodo, rota, corpo) {
  var opcoes = { method: metodo, headers: { "X-GP-Token": TOKEN }, credentials: "same-origin" };
  if (corpo) { opcoes.headers["Content-Type"] = "application/json"; opcoes.body = JSON.stringify(corpo); }
  return fetch(rota, opcoes).then(function (resp) {
    return resp.json().catch(function () { return { ok: false, erro: resp.statusText }; }).then(function (dados) {
      if (!resp.ok || !dados.ok) {
        const erro = new Error(dados.erro || resp.statusText);
        erro.classe = dados.classe || null;
        erro.erros = dados.erros || [];
        erro.status = resp.status;
        throw erro;
      }
      return dados;
    });
  });
}

// grava pela API, avisa e recarrega a tela atual no mesmo ponto da rolagem
export function acao(rota, corpo, depois) {
  if (ocupado) { return Promise.resolve(); }
  ocupado = true;
  return api("POST", rota, corpo).then(function (d) {
    if (depois) { depois(d); }
    if (d.mensagem) { avisar(d.mensagem); }
    return recarregar(true);
  }).catch(function (erro) {
    avisar(t("erro_acao", { erro: erro.message }), true);
    return recarregar(true);
  }).then(function () { ocupado = false; });
}

// o navegador oferece instalar o painel como app (Chrome e Edge): o evento fica guardado para o botão da tela
export var instalacaoApp = { evento: null };
window.addEventListener("beforeinstallprompt", function (ev) { ev.preventDefault(); instalacaoApp.evento = ev; });

// no app instalado pelo navegador (standalone), na janela nativa do Mac (Goal Pacer.app põe GoalPacerApp no user agent)
// ou na janela do Windows (o atalho abre o navegador em modo app com ?janela=1)
export function emApp() { return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true || /GoalPacerApp/.test(navigator.userAgent) || /[?&]janela=1/.test(location.search); }

export function palavraDividida(texto) {
  var i = texto.indexOf(" ");
  return i < 0 ? [texto] : [texto.slice(0, i), texto.slice(i + 1)];
}

// erro de JavaScript vira registro local no computador (jobs/logs), nunca serviço de fora; até 5 por abertura
var errosEnviados = 0;

function reportarErro(dados) {
  if (errosEnviados >= 5) { return; }
  errosEnviados += 1;
  try {
    fetch("/api/erro-front", { method: "POST", credentials: "same-origin", headers: { "X-GP-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(dados) })
      .catch(function () { return null; });
  } catch { return; }
}

function telaAtual() { return ((location.hash || "#/hoje").replace(/^#\/?/, "").split("/")[0] || "hoje").slice(0, 12); }

window.addEventListener("error", function (ev) {
  reportarErro({ mensagem: String(ev.message || "").slice(0, 300), arquivo: String(ev.filename || "").replace(location.origin, "").slice(0, 120),
    linha: ev.lineno || 0, coluna: ev.colno || 0, tela: telaAtual() });
});
window.addEventListener("unhandledrejection", function (ev) {
  var motivo = ev.reason && ev.reason.message ? ev.reason.message : ev.reason;
  reportarErro({ mensagem: String(motivo || "").slice(0, 300), arquivo: "", linha: 0, coluna: 0, tela: telaAtual() });
});

// menu que rola para o lado: degradê na borda enquanto houver itens escondidos e o item atual à vista (celular)
export function marcarRolagem(no) {
  if (!no) { return; }
  var atualizar = function () {
    var rola = no.scrollWidth - no.clientWidth > 2;
    no.classList.toggle("rola", rola);
    no.classList.toggle("no-fim", !rola || no.scrollLeft + no.clientWidth >= no.scrollWidth - 2);
    no.classList.toggle("no-inicio", !rola || no.scrollLeft <= 2);
  };
  var ativo = no.querySelector('[aria-current="page"]');
  if (ativo && no.scrollWidth > no.clientWidth) {
    no.scrollLeft = Math.max(0, ativo.offsetLeft - (no.clientWidth - ativo.offsetWidth) / 2);
  }
  if (!no.dataset.rolagem) {
    no.dataset.rolagem = "1";
    no.addEventListener("scroll", atualizar, { passive: true });
    window.addEventListener("resize", atualizar);
  }
  atualizar();
}

// o módulo da navegação registra como recarregar a tela depois de uma gravação (evita import circular)
export function aoRecarregar(fn) { recarregar = fn; }

export function definirTextos(novos) { textos = novos || textos; }

export function temTexto(chave) { return Boolean(textos[chave]); }
