// Tela Começar: o onboarding pela tela, para quem instalou sem terminal. Seis passos com o mesmo rascunho da skill
// (conta, metas, horário, fontes, conferir, pronto); cada passo grava o rascunho, então dá para fechar e voltar.
// O servidor completa horizonte e semanas pelo prazo e grava pelas funções do onboarding.py.
import { $, IMPACTOS, api, avisar, el, emApp, instalacaoApp, lembrar, limpar, t } from "../nucleo.js";
import { cabeca, card } from "../pecas.js";

export var PASSOS = ["conta", "metas", "horario", "fontes", "conferir"];
export var FONTES = ["gmail", "whatsapp", "notion", "drive"];
var CHAVE_PASSO = "gp-comecar-passo";

// o que já respondido + o que o detectar achou, sem sobrescrever uma resposta com a detecção
export function respostasIniciais(m) {
  var r = Object.assign({}, (m.rascunho && m.rascunho.respostas) || {});
  var d = m.deteccao || {};
  ["email_proprio", "calendar_id_metas", "calendar_id_primario", "timezone"].forEach(function (chave) {
    if (!r[chave] && d[chave]) { r[chave] = d[chave]; }
  });
  if (!r.idioma) { r.idioma = m.idioma; }
  if (!r.metas || !r.metas.length) { r.metas = [metaVazia()]; }
  if (!r.objetivos) { r.objetivos = []; }
  if (!r.horario_util) { r.horario_util = { seg_sex: "09:00-18:00", sab: "", dom: "" }; }
  // gmail só vem marcado quando o Gmail está conectado: sem conector, o app segue só com o que a pessoa escreve
  if (!r.fontes_ativas) { r.fontes_ativas = (d.fontes_disponiveis || []).indexOf("gmail") >= 0 ? ["gmail"] : []; }
  return r;
}

export function metaVazia() { return { titulo: "", objetivo: "", prazo: "", custo_h_semana_escolhido: "", impacto: "importante", prazo_externo: false, palavras_chave: [] }; }

// só as metas com título entram; horas viram número e objetivo vazio sai
export function metasParaGravar(metas) {
  return metas.filter(function (x) { return (x.titulo || "").trim(); }).map(function (x) {
    var meta = { titulo: x.titulo.trim(), prazo: x.prazo, custo_h_semana_escolhido: Number(x.custo_h_semana_escolhido), impacto: x.impacto || "importante", prazo_externo: !!x.prazo_externo, palavras_chave: x.palavras_chave || [] };
    if ((x.objetivo || "").trim()) { meta.objetivo = x.objetivo.trim(); }
    return meta;
  });
}

function campo(id, rotulo, entrada, ajuda) {
  entrada.id = id;
  return el("div", { classe: "campo" }, [el("label", { "for": id, texto: rotulo }), entrada, ajuda ? el("small", { classe: "sub", texto: ajuda }) : null]);
}

function botao(classe, texto, clique) {
  var b = el("button", { classe: classe, type: "button", texto: texto });
  b.addEventListener("click", clique);
  return b;
}

// --- passos -----------------------------------------------------------------------------

// o que a conta precisa, com o link de onde se resolve cada item (abrem no navegador, fora do painel)
export function requisitos() {
  return [
    [t("comecar_req_claude"), t("comecar_link_claude"), "https://code.claude.com/docs/en/setup"],
    [t("comecar_req_conectores"), t("comecar_link_conectores"), "https://claude.ai/settings/connectors"],
    [t("comecar_req_calendario"), t("comecar_link_calendario"), "https://calendar.google.com/calendar/r/settings/createcalendar"],
  ];
}

var CONECTORES = [["Google_Calendar", "conexao_calendar"], ["Gmail", "conexao_gmail"], ["Notion", "conexao_notion"], ["Google_Drive", "conexao_drive"]];
var INTERVALO_CONTA_MS = 8000;
var MAXIMO_CONFERENCIAS = 150; // uns 20 minutos conferindo sozinha; depois, só pelo botão
var INTERVALO_METAS_MS = 60000; // procurar o calendário Metas gasta tokens: uma vez por minuto, até 10 vezes
var vigia = { passo: 0 };

function link(texto, href) { return el("a", { href: href, target: "_blank", rel: "noopener", texto: texto }); }

// linha do Claude Code: o único item obrigatório, com o botão que resolve o que falta
function linhaClaude(conta, redesenhar, entrar) {
  var c = (conta && conta.claude) || {};
  if (c.instalado && c.logado) {
    return el("li", { classe: "ok", texto: c.plano ? t("comecar_claude_logado_plano", { plano: c.plano }) : t("comecar_claude_logado") });
  }
  var acao = c.instalado
    ? botao("botao-escuro", t("comecar_login_claude"), function () { entrar(acao); })
    : botao("botao-escuro", t("comecar_instalar_claude"), function () { acaoConta("/api/comecar/instalar-claude", acao, redesenhar); });
  acao.disabled = !!c.instalando;
  var texto = c.instalando ? t("comecar_claude_instalando") : c.instalado ? t("comecar_claude_sem_login") : t("comecar_claude_falta");
  return el("li", { classe: "falta" }, [el("span", { texto: texto + " " }), acao, el("span", { texto: " " }), link(t("comecar_link_claude"), requisitos()[0][2])]);
}

function acaoConta(rota, botaoUsado, redesenhar) {
  botaoUsado.disabled = true;
  api("POST", rota, {}).then(function (d) { avisar(d.mensagem); redesenhar(); }).catch(function (erro) { botaoUsado.disabled = false; avisar(erro.message, true); });
}

// login do Claude Code sem terminal: o navegador abre a página de login, e o código que ela mostra volta por aqui
function caixaDeLogin(caixa, url, depois) {
  limpar(caixa);
  var codigo = el("input", { type: "text", autocomplete: "off", spellcheck: "false" });
  var entrar = botao("botao-escuro", t("comecar_login_entrar"), function () {
    entrar.disabled = true;
    api("POST", "/api/comecar/login-codigo", { codigo: codigo.value }).then(function (d) {
      avisar(d.mensagem);
      limpar(caixa);
      depois();
    }).catch(function (erro) { entrar.disabled = false; avisar(erro.message, true); });
  });
  caixa.appendChild(el("div", { classe: "login-claude" }, [
    el("p", { classe: "sub", texto: t("comecar_login_instrucao") + " " }, [url ? link(t("comecar_login_link"), url) : null]),
    el("div", { classe: "campos" }, [campo("cc-login-codigo", t("comecar_login_codigo"), codigo)]),
    el("div", { classe: "acoes-form" }, [entrar]),
  ]));
  codigo.focus();
}

function listaConectores(conta) {
  var estados = (conta && conta.conectores) || {};
  return el("ul", { classe: "conectores-conta" }, CONECTORES.map(function (par) {
    var estado = estados[par[0]] || "desconectado";
    return el("li", { classe: "conector-" + estado }, [el("b", { texto: t(par[1]) }), el("span", { texto: " " + t("comecar_conector_" + estado) })]);
  }));
}

function passoConta(m, r, ir) {
  var d = m.deteccao;
  var numero = vigia.passo; // cada ir() troca o número: o passo que saiu da tela para de conferir
  var claudeLista = el("ul", { classe: "conferencia" });
  var loginCaixa = el("div", { classe: "comecar-login" }); // fora da lista: a conferência a cada 8 s não apaga o código colado
  var conectores = el("div", { classe: "comecar-conectores" });
  var status = el("div", { classe: "comecar-conta" });
  var conferir = botao("botao-claro", d ? t("comecar_conferir_de_novo") : t("comecar_conferir"), function () { detectar(false); });
  function detectar(sozinho) {
    conferir.disabled = true;
    conferir.textContent = t("comecar_conferindo");
    return api("POST", "/api/comecar/detectar", {}).then(function (resposta) {
      m.deteccao = resposta.deteccao;
      Object.assign(r, respostasIniciais(Object.assign({}, m, { rascunho: { respostas: r } })));
      if (numero === vigia.passo) { ir("conta"); }
    }).catch(function (erro) { conferir.disabled = false; conferir.textContent = t("comecar_conferir"); if (!sozinho) { avisar(erro.message, true); } });
  }
  function desenharConta(conta) {
    m.conta = conta;
    limpar(claudeLista);
    claudeLista.appendChild(linhaClaude(conta, conferirConta, function (botaoUsado) {
      botaoUsado.disabled = true;
      api("POST", "/api/comecar/login-claude", {}).then(function (resposta) {
        botaoUsado.disabled = false;
        caixaDeLogin(loginCaixa, resposta.url, conferirContaAgora);
      }).catch(function (erro) { botaoUsado.disabled = false; avisar(erro.message, true); });
    }));
    if (conta && conta.claude && conta.claude.logado) { limpar(loginCaixa); }
    limpar(conectores);
    conectores.appendChild(listaConectores(conta));
    conferir.hidden = !(conta && conta.claude && conta.claude.logado);
  }
  var vezes = 0;
  function conferirContaAgora() {
    api("POST", "/api/comecar/conta", {}).then(function (resposta) { if (numero === vigia.passo) { desenharConta(resposta.conta); } }).catch(function () { return null; });
  }
  var procurasMetas = 0;
  function conferirConta() {
    if (numero !== vigia.passo) { return; } // saiu do passo: para de conferir
    if (document.hidden) { setTimeout(conferirConta, INTERVALO_CONTA_MS); return; }
    api("POST", "/api/comecar/conta", {}).then(function (resposta) {
      if (numero !== vigia.passo) { return; }
      var antes = m.conta;
      desenharConta(resposta.conta);
      var agora = resposta.conta.conectores || {};
      var mudou = !antes || ["Google_Calendar", "Gmail"].some(function (s) { return agora[s] === "conectado" && (antes.conectores || {})[s] !== "conectado"; });
      if (resposta.conta.claude.logado && mudou && (agora.Google_Calendar === "conectado" || agora.Gmail === "conectado") && !(m.deteccao && m.deteccao.email_proprio)) { detectar(true); return; }
      if (m.deteccao && agora.Google_Calendar === "conectado" && !m.deteccao.calendar_id_metas && procurasMetas < 10) {
        procurasMetas += 1;
        setTimeout(function () { if (numero === vigia.passo) { detectar(true); } }, INTERVALO_METAS_MS);
      }
    }).catch(function () { return null; }).then(function () {
      vezes += 1;
      if (vezes < MAXIMO_CONFERENCIAS && numero === vigia.passo) { setTimeout(conferirConta, INTERVALO_CONTA_MS); }
    });
  }
  desenharConta(m.conta);
  conferirConta();
  if (d) {
    status.appendChild(el("ul", { classe: "conferencia" }, [
      el("li", { classe: d.email_proprio ? "ok" : "falta", texto: d.email_proprio ? t("comecar_email_ok", { email: d.email_proprio }) : t("comecar_email_falta") }),
      el("li", { classe: d.calendar_id_metas ? "ok" : "falta" }, d.calendar_id_metas ? [t("comecar_metas_ok")] : [el("span", { texto: t("comecar_metas_falta") + " " }), link(t("comecar_link_calendario"), requisitos()[2][2])]),
      el("li", { classe: "ok", texto: t("comecar_fontes_achadas", { fontes: (d.fontes_disponiveis || []).map(function (f) { return t("conexao_" + f); }).join(", ") }) }),
    ]));
  }
  var seguir = botao("botao-escuro", t("comecar_continuar"), function () { ir("metas"); });
  return card("", t("comecar_conta_titulo"), t("comecar_conta_detalhe"), [
    el("h3", { classe: "comecar-sub", texto: t("comecar_claude_titulo") }),
    claudeLista,
    loginCaixa,
    m.plataforma === "macos" ? el("p", { classe: "sub", texto: t("comecar_chaveiro") }) : null,
    el("h3", { classe: "comecar-sub", texto: t("comecar_conectores_titulo") }),
    el("p", { classe: "sub", texto: t("comecar_conectores_opcionais") + " " }, [link(t("comecar_link_conectores"), requisitos()[1][2])]),
    conectores,
    status,
    el("div", { classe: "acoes-form" }, [conferir, seguir]),
  ], "t-comecar-conta");
}

function linhaMeta(r, meta, indice, redesenhar) {
  var titulo = el("input", { type: "text", maxlength: "120", value: meta.titulo, placeholder: t("comecar_meta_exemplo") });
  titulo.addEventListener("input", function () { meta.titulo = titulo.value; });
  var objetivo = el("input", { type: "text", maxlength: "120", value: meta.objetivo || "", list: "comecar-objetivos", placeholder: t("comecar_objetivo_exemplo") });
  objetivo.addEventListener("input", function () { meta.objetivo = objetivo.value; });
  var prazo = el("input", { type: "date", value: meta.prazo || "" });
  prazo.addEventListener("change", function () { meta.prazo = prazo.value; });
  var horas = el("input", { type: "number", min: "0.5", max: "40", step: "0.5", value: String(meta.custo_h_semana_escolhido || "") });
  horas.addEventListener("input", function () { meta.custo_h_semana_escolhido = horas.value; });
  var impacto = el("select", {}, IMPACTOS.map(function (imp) { return el("option", { value: imp, texto: t("coach.impacto_" + imp) }); }));
  impacto.value = meta.impacto || "importante";
  impacto.addEventListener("change", function () { meta.impacto = impacto.value; });
  var externo = el("input", { type: "checkbox" });
  externo.checked = !!meta.prazo_externo;
  externo.addEventListener("change", function () { meta.prazo_externo = externo.checked; });
  var tirar = r.metas.length > 1 ? botao("saida", t("comecar_tirar_meta"), function () { r.metas.splice(indice, 1); redesenhar(); }) : null;
  var n = indice + 1;
  return el("fieldset", { classe: "comecar-meta" }, [
    el("legend", { texto: t("comecar_meta_n", { n: n }) }),
    campo("cm-titulo-" + n, t("comecar_meta_titulo"), titulo),
    el("div", { classe: "campos" }, [
      campo("cm-prazo-" + n, t("comecar_meta_prazo"), prazo),
      campo("cm-horas-" + n, t("comecar_meta_horas"), horas, t("comecar_meta_horas_ajuda")),
      campo("cm-impacto-" + n, t("comecar_meta_impacto"), impacto),
      campo("cm-objetivo-" + n, t("comecar_meta_objetivo"), objetivo, t("comecar_meta_objetivo_ajuda")),
    ]),
    el("label", { classe: "campo-linha", "for": "cm-externo-" + n }, [Object.assign(externo, { id: "cm-externo-" + n }), el("span", { texto: t("comecar_meta_externo") })]),
    tirar,
  ]);
}

function passoMetas(m, r, ir) {
  var lista = el("div", { classe: "comecar-metas" });
  var redesenhar = function () {
    limpar(lista);
    r.metas.forEach(function (meta, i) { lista.appendChild(linhaMeta(r, meta, i, redesenhar)); });
    mais.hidden = r.metas.length >= m.teto_metas;
  };
  var mais = botao("botao-claro", t("comecar_mais_meta"), function () { r.metas.push(metaVazia()); redesenhar(); });
  var sugestoes = el("datalist", { id: "comecar-objetivos" }, (r.metas || []).map(function (x) { return x.objetivo; }).filter(Boolean).map(function (o) { return el("option", { value: o }); }));
  redesenhar();
  return card("", t("comecar_metas_titulo"), t("comecar_metas_detalhe"), [
    sugestoes, lista, mais,
    el("div", { classe: "acoes-form" }, [
      botao("botao-claro", t("comecar_voltar"), function () { ir("conta"); }),
      botao("botao-escuro", t("comecar_continuar"), function () {
        var metas = metasParaGravar(r.metas);
        if (!metas.length) { avisar(t("comecar_sem_metas"), true); return; }
        var objetivos = Array.from(new Set(metas.map(function (x) { return x.objetivo; }).filter(Boolean))).slice(0, m.teto_objetivos).map(function (o) { return { titulo: o }; });
        r.metas = metas;
        salvar({ metas: metas, objetivos: objetivos }, function () { ir("horario"); });
      }),
    ]),
  ], "t-comecar-metas");
}

function passoHorario(r, ir) {
  var h = r.horario_util;
  var entradas = ["seg_sex", "sab", "dom"].map(function (dia) {
    var entrada = el("input", { type: "text", inputmode: "numeric", value: h[dia] || "", placeholder: t("comecar_horario_vazio") });
    entrada.addEventListener("input", function () { h[dia] = entrada.value; });
    return campo("ch-" + dia, t("comecar_horario_" + dia), entrada);
  });
  return card("", t("comecar_horario_titulo"), t("comecar_horario_detalhe"), [
    el("div", { classe: "campos" }, entradas),
    el("div", { classe: "acoes-form" }, [
      botao("botao-claro", t("comecar_voltar"), function () { ir("metas"); }),
      botao("botao-escuro", t("comecar_continuar"), function () {
        salvar({ horario_util: { seg_sex: (h.seg_sex || "").trim() || "nenhum", sab: (h.sab || "").trim() || "nenhum", dom: (h.dom || "").trim() || "nenhum" } }, function () { ir("fontes"); });
      }),
    ]),
  ], "t-comecar-horario");
}

function passoFontes(m, r, ir) {
  var disponiveis = (m.deteccao && m.deteccao.fontes_disponiveis) || ["whatsapp"];
  var marcas = FONTES.filter(function (f) { return disponiveis.indexOf(f) >= 0; }).map(function (fonte) {
    var caixa = el("input", { type: "checkbox", id: "cf-" + fonte });
    caixa.checked = r.fontes_ativas.indexOf(fonte) >= 0;
    caixa.addEventListener("change", function () {
      r.fontes_ativas = r.fontes_ativas.filter(function (f) { return f !== fonte; }).concat(caixa.checked ? [fonte] : []);
    });
    return el("label", { classe: "campo-linha", "for": "cf-" + fonte }, [caixa, el("span", { texto: t("conexao_" + fonte) })]);
  });
  var palavras = r.metas.map(function (meta, i) {
    var entrada = el("input", { type: "text", value: (meta.palavras_chave || []).join(", "), placeholder: t("comecar_palavras_exemplo") });
    entrada.addEventListener("input", function () { r.metas[i].palavras_chave = entrada.value.split(",").map(function (p) { return p.trim(); }).filter(Boolean).slice(0, 3); });
    return campo("cp-" + (i + 1), meta.titulo, entrada);
  });
  var lembretes = el("input", { type: "checkbox", id: "cf-lembretes" });
  lembretes.checked = r.lembretes === "sim";
  lembretes.addEventListener("change", function () { r.lembretes = lembretes.checked ? "sim" : "nao"; });
  return card("", t("comecar_fontes_titulo"), t("comecar_fontes_detalhe"), [
    el("div", { classe: "comecar-fontes" }, marcas),
    el("h3", { texto: t("comecar_palavras_titulo") }),
    el("p", { classe: "sub", texto: t("comecar_palavras_detalhe") }),
    el("div", { classe: "campos" }, palavras),
    el("label", { classe: "campo-linha", "for": "cf-lembretes" }, [lembretes, el("span", { texto: t("comecar_lembretes") })]),
    el("div", { classe: "acoes-form" }, [
      botao("botao-claro", t("comecar_voltar"), function () { ir("horario"); }),
      botao("botao-escuro", t("comecar_continuar"), function () {
        salvar({ fontes_ativas: r.fontes_ativas, lembretes: r.lembretes || "nao", metas: metasParaGravar(r.metas) }, function () { ir("conferir"); });
      }),
    ]),
  ], "t-comecar-fontes");
}

function passoConferir(m, r, ir) {
  var email = el("input", { type: "email", value: r.email_proprio || "" });
  var fuso = el("input", { type: "text", value: r.timezone || "" });
  var idioma = el("select", {}, [["pt-BR", "Português (Brasil)"], ["en", "English"]].map(function (par) { return el("option", { value: par[0], texto: par[1] }); }));
  idioma.value = r.idioma || "pt-BR";
  var erros = el("ul", { classe: "comecar-erros" });
  var gravar = botao("botao-escuro", t("comecar_gravar"), function () {
    gravar.disabled = true;
    limpar(erros);
    var respostas = { email_proprio: email.value.trim(), timezone: fuso.value.trim(), idioma: idioma.value };
    ["calendar_id_metas", "calendar_id_primario"].forEach(function (chave) { if (r[chave]) { respostas[chave] = r[chave]; } });
    api("POST", "/api/comecar/rascunho", { respostas: respostas })
      .then(function () { return api("POST", "/api/comecar/gravar", {}); })
      .then(function (d) {
        avisar(d.mensagem);
        lembrar(CHAVE_PASSO, "");
        m.configurado = true;
        m.agenda_google = !!respostas.calendar_id_metas;
        ir("pronto");
        if (m.instalado) { primeiroDia(m); }
      })
      .catch(function (erro) {
        gravar.disabled = false;
        avisar(erro.message, true);
        (erro.erros || []).forEach(function (linha) { erros.appendChild(el("li", { texto: linha })); });
      });
  });
  return card("", t("comecar_conferir_titulo"), t("comecar_conferir_detalhe"), [
    el("div", { classe: "campos" }, [campo("cc-email", t("comecar_email"), email), campo("cc-fuso", t("comecar_fuso"), fuso), campo("cc-idioma", t("comecar_idioma"), idioma)]),
    erros,
    el("div", { classe: "acoes-form" }, [botao("botao-claro", t("comecar_voltar"), function () { ir("fontes"); }), gravar]),
  ], "t-comecar-conferir");
}

function salvar(respostas, depois) {
  api("POST", "/api/comecar/rascunho", { respostas: respostas }).then(depois).catch(function (erro) { avisar(erro.message, true); });
}

// --- pronto: primeiro dia e o app instalado ----------------------------------------------

export function cardInstalarApp(m) {
  var filhos = [];
  if (!emApp() && m && m.janela) { filhos.push(el("p", { classe: "resumo", texto: m.plataforma === "windows" ? t("app_windows") : t("app_mac") })); }
  if (emApp()) {
    filhos.push(el("p", { classe: "sub", texto: t("app_ja_instalado") }));
  } else if (instalacaoApp.evento) {
    filhos.push(botao("botao-escuro", t("app_instalar"), function () {
      instalacaoApp.evento.prompt();
      instalacaoApp.evento = null;
    }));
  } else {
    filhos.push(el("ul", { classe: "comandos" }, [t("app_chrome"), t("app_safari")].map(function (texto) { return el("li", { texto: texto }); })));
  }
  return card("", t("app_titulo"), t("app_detalhe"), filhos, "t-app");
}

// o primeiro dia sai sozinho logo depois de gravar as metas; o botão fica para gerar outra vez
function primeiroDia(m, botaoUsado) {
  if (botaoUsado) { botaoUsado.disabled = true; }
  m.primeiroDiaPedido = true;
  return api("POST", "/api/comecar/primeiro-dia", {}).then(function (d) { avisar(d.mensagem); }).catch(function (erro) {
    m.primeiroDiaPedido = false;
    if (botaoUsado) { botaoUsado.disabled = false; }
    avisar(erro.message, true);
  });
}

function passoPronto(m) {
  var dia = botao("botao-escuro", t("comecar_primeiro_dia"), function () { primeiroDia(m, dia); });
  dia.hidden = !m.instalado || !!m.primeiroDiaPedido;
  var hoje = el("a", { classe: "botao-claro", href: "#/hoje", texto: t("comecar_ir_hoje") });
  return [
    card("", t("comecar_pronto_titulo"), t("comecar_pronto_detalhe"), [
      el("p", { classe: "resumo", texto: !m.instalado ? t("comecar_pronto_sem_instalacao") : m.agenda_google === false ? t("comecar_pronto_texto_app") : t("comecar_pronto_texto") }),
      el("div", { classe: "acoes-form" }, [dia, hoje]),
    ], "t-comecar-pronto"),
    cardInstalarApp(m),
  ];
}

// --- tela --------------------------------------------------------------------------------

export function telaComecar(m) {
  var r = respostasIniciais(m);
  var corpo = el("div", { classe: "coluna col-12 comecar" });
  var trilha = el("ol", { classe: "comecar-trilha", "aria-label": t("comecar_passos") });
  var ir = function (passo) {
    vigia.passo += 1;
    lembrar(CHAVE_PASSO, passo);
    limpar(corpo);
    limpar(trilha);
    PASSOS.forEach(function (p, i) {
      trilha.appendChild(el("li", { classe: p === passo ? "atual" : PASSOS.indexOf(passo) > i || passo === "pronto" ? "feito" : "", texto: t("comecar_passo_" + p) }));
    });
    var desenhos = {
      conta: function () { return [passoConta(m, r, ir)]; },
      metas: function () { return [passoMetas(m, r, ir)]; },
      horario: function () { return [passoHorario(r, ir)]; },
      fontes: function () { return [passoFontes(m, r, ir)]; },
      conferir: function () { return [passoConferir(m, r, ir)]; },
      pronto: function () { return passoPronto(m); },
    };
    (desenhos[passo] || desenhos.conta)().forEach(function (no) { corpo.appendChild(no); });
    if ($("tela")) { window.scrollTo(0, 0); }
  };
  var inicio = m.configurado ? "pronto" : lembrar(CHAVE_PASSO) || "conta";
  ir(PASSOS.indexOf(inicio) >= 0 || inicio === "pronto" ? inicio : "conta");
  return [
    cabeca({ titulo: t("nav_comecar"), sub: m.configurado ? t("comecar_sub_pronto") : t("comecar_sub") }),
    m.configurado ? null : trilha,
    el("div", { classe: "grade" }, [corpo]),
  ];
}
