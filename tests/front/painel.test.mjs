// Testes de unidade do front do painel (node:test, sem npm). O DOM não existe aqui: só as funções puras e as tabelas
// que ligam as telas, as rotas e o que os modelos em Python produzem. O percurso no navegador é o tests/e2e/painel.sh.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

globalThis.document = { querySelector: () => null, getElementById: () => null };
globalThis.window = { addEventListener() {} };
globalThis.location = { hash: "", origin: "" };

const raiz = new URL("../../", import.meta.url);
const ler = (caminho) => readFileSync(new URL(caminho, raiz), "utf-8");
const nucleo = await import(new URL("web/js/nucleo.js", raiz));
const pecas = await import(new URL("web/js/pecas.js", raiz));
const meta = await import(new URL("web/js/telas/meta.js", raiz));
const conexoes = await import(new URL("web/js/telas/conexoes.js", raiz));

test("t troca todas as variáveis e chave ausente vira vazio", () => {
  nucleo.definirTextos({ ola: "{nome} e {nome}: {n}" });
  assert.equal(nucleo.t("ola", { nome: "Ana", n: 3 }), "Ana e Ana: 3");
  assert.equal(nucleo.t("nao_existe"), "");
  assert.equal(nucleo.temTexto("ola"), true);
  nucleo.definirTextos(null);
  assert.equal(nucleo.temTexto("ola"), true); // null mantém os textos carregados
});

test("palavra dividida só no primeiro espaço", () => {
  assert.deepEqual(nucleo.palavraDividida("pede atenção agora"), ["pede", "atenção agora"]);
  assert.deepEqual(nucleo.palavraDividida("travada"), ["travada"]);
});

test("links de período e classes de leitura", () => {
  assert.equal(pecas.hrefPeriodo("dia", "2026-09-28"), "#/dia/2026-09-28");
  assert.equal(pecas.hrefPeriodo("trimestre", "2026-T4"), "#/periodo/trimestre/2026-T4");
  assert.equal(pecas.classeLeitura("coach.estado_florescendo"), "l-forte");
  assert.equal(pecas.classeLeitura("coach.objetivo_construcao"), "l-media");
  assert.equal(pecas.classeLeitura("foco"), "l-fraca");
  assert.equal(pecas.classeLeitura(undefined), "l-neutra");
});

test("faixa de tração pelos limites de cada estado", () => {
  assert.deepEqual([0, 0.29, 0.3, 0.5, 0.69, 0.7, 1].map(meta.faixaDe), ["travada", "travada", "atencao", "ritmo", "ritmo", "florescendo", "florescendo"]);
  assert.equal(meta.faixaDe(-1), "travada");
});

test("toda tela tem rota, desenho e item no menu", () => {
  const desenhos = [...ler("web/app.js").match(/var DESENHOS = \{([^}]*)\}/)[1].matchAll(/(\w+):/g)].map((m) => m[1]);
  const menu = [...ler("web/index.html").matchAll(/data-tela="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(desenhos.filter((d) => !(d in nucleo.ROTAS)), []);
  assert.deepEqual(menu.filter((d) => !desenhos.includes(d)), []);
  // a meta abre pela lista; o começar abre sozinho enquanto não há metas e o app se instala pelo Status
  assert.deepEqual(desenhos.filter((d) => !["meta", "comecar"].includes(d) && !menu.includes(d)), []);
});

test("cada estado de conexão que o painel.py produz tem cor", () => {
  const python = ler("scripts/goalpacer/conexoes.py") + ler("scripts/painel.py");
  const doModulo = [...python.match(/^ESTADOS = \(([^)]*)\)/m)[1].matchAll(/"(\w+)"/g)].map((m) => m[1]);
  const doPainel = [...python.matchAll(/"estado": "(\w+)"/g)].map((m) => m[1]);
  const semCor = [...new Set([...doModulo, ...doPainel])].filter((e) => !(e in conexoes.CLASSE_DO_ESTADO));
  assert.deepEqual(semCor, []);
});
