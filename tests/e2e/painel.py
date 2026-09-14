#!/usr/bin/env python3
"""E2E do painel: sobe ``web.py --demo`` numa porta livre, percorre as telas e as ações, confere o console, o celular
(390 px) e o registro local; imprime OK/FALHOU por item e sai com 3 se algum falhou.

    python3 tests/e2e/painel.py                          navegador headless do gstack (browse), na máquina
    python3 tests/e2e/painel.py --navegador playwright   Playwright (requirements-e2e.txt e playwright install chromium)

Dados sintéticos do demo, só 127.0.0.1, nenhum conector, nenhum token. O percurso é um só para os dois navegadores;
cada um só precisa saber ir a uma URL, rodar uma expressão, esperar, trocar o tamanho da janela e contar erros do
console. ``BROWSE=<binário>`` troca o binário do gstack.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

RAIZ = Path(__file__).resolve().parent.parent.parent
BROWSE_PADRAO = Path.home() / ".claude" / "skills" / "gstack" / "browse" / "dist" / "browse"
ESPERA_ACAO_MS = 1200
TELAS = [
    "hoje",
    "dia/2026-09-25",
    "horizontes",
    "periodo/semestre/2026-S2",
    "periodo/trimestre/2026-T4",
    "periodo/mes/2026-10",
    "periodo/semana/2026-W40",
    "objetivos",
    "metas",
    "meta/M01",
    "meta/M03",
    "checkin",
    "status",
    "conexoes",
]
TELAS_CELULAR = ["hoje", "horizontes", "metas", "meta/M01", "checkin", "status", "conexoes"]


class Gstack:
    """O ``browse`` do gstack: um processo por comando, o navegador fica no ar entre eles."""

    def __init__(self, binario: str) -> None:
        if not os.access(binario, os.X_OK):
            raise SystemExit("FALHOU navegador do gstack ausente em %s (defina BROWSE)" % binario)
        self.binario = binario

    def _rodar(self, *args: str) -> str:
        proc = subprocess.run([self.binario, *args], capture_output=True, text=True, timeout=120, check=False)
        return proc.stdout

    def ir(self, url: str) -> None:
        self._rodar("goto", url)
        self._rodar("wait", "--networkidle")

    def js(self, expressao: str) -> str:
        linhas = [l for l in self._rodar("js", expressao).splitlines() if "UNTRUSTED" not in l]
        return linhas[-1].strip() if linhas else ""

    def esperar(self, ms: int) -> None:
        time.sleep(ms / 1000)  # o wait do browse espera seletor ou rede, não tempo

    def janela(self, largura: int, altura: int) -> None:
        self._rodar("viewport", "%dx%d" % (largura, altura))

    def limpar_console(self) -> None:
        self._rodar("console", "--clear")

    def erros_do_console(self) -> int:
        saida = self._rodar("console", "--errors")
        return sum(1 for l in saida.splitlines() if l.strip() and "UNTRUSTED" not in l and "no console errors" not in l)

    def fechar(self) -> None:
        return None


class Playwright:
    """Playwright síncrono num Chromium headless; erros do console e da página contados pelos eventos."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._contexto = sync_playwright().start()
        self._navegador = self._contexto.chromium.launch()
        self.pagina = self._navegador.new_page(viewport={"width": 1280, "height": 900})
        self.erros: list[str] = []
        self.pagina.on("console", lambda msg: self.erros.append(msg.text) if msg.type == "error" else None)
        self.pagina.on("pageerror", lambda erro: self.erros.append(str(erro)))

    def ir(self, url: str) -> None:
        self.pagina.goto(url, wait_until="networkidle")

    def js(self, expressao: str) -> str:
        valor: Any = self.pagina.evaluate(expressao)
        if isinstance(valor, bool):
            return "true" if valor else "false"
        return "" if valor is None else str(valor)

    def esperar(self, ms: int) -> None:
        self.pagina.wait_for_timeout(ms)

    def janela(self, largura: int, altura: int) -> None:
        self.pagina.set_viewport_size({"width": largura, "height": altura})

    def limpar_console(self) -> None:
        self.erros.clear()

    def erros_do_console(self) -> int:
        return len(self.erros)

    def fechar(self) -> None:
        self._navegador.close()
        self._contexto.stop()


class Percurso:
    def __init__(self, navegador: Any, url: str, logs: Path) -> None:
        self.nav = navegador
        self.url = url
        self.logs = logs
        self.falhas = 0

    def conferir(self, rotulo: str, obtido: Any, esperado: Any) -> None:
        if obtido == esperado:
            print("OK %s" % rotulo)
        else:
            print("FALHOU %s: veio [%s], esperado [%s]" % (rotulo, obtido, esperado))
            self.falhas += 1

    def ir(self, rota: str) -> None:
        self.nav.ir("%s/?e2e=%d#/%s" % (self.url, random.randint(0, 99999), rota))

    def acao(self, rotulo: str, expressao: str, trecho: str) -> None:
        self.nav.js(expressao)
        self.nav.esperar(ESPERA_ACAO_MS)
        aviso = self.nav.js(
            'document.getElementById("toast").hidden ? "" : document.getElementById("toast").textContent'
        )
        if trecho in aviso:
            print("OK ação %s" % rotulo)
        else:
            print("FALHOU ação %s: aviso [%s]" % (rotulo, aviso))
            self.falhas += 1

    def eventos(self, filtro: Callable[[dict], bool]) -> int:
        total = 0
        for arquivo in glob.glob(str(self.logs / "eventos-*.jsonl")):
            with open(arquivo, encoding="utf-8") as linhas:
                total += sum(1 for linha in linhas if filtro(json.loads(linha)))
        return total

    def rodar(self) -> int:
        nav = self.nav
        nav.janela(1280, 900)
        nav.limpar_console()
        carregada = 'document.getElementById("tela").getAttribute("aria-busy") + ":" + (document.getElementById("tela").children.length > 1)'
        for rota in TELAS:
            self.ir(rota)
            self.conferir("tela %s" % rota, nav.js(carregada), "false:true")
        self._acoes()
        self.conferir("console sem erros", nav.erros_do_console(), 0)
        nav.janela(390, 844)
        for rota in TELAS_CELULAR:
            self.ir(rota)
            self.conferir(
                "celular %s sem rolagem lateral" % rota,
                nav.js("document.documentElement.scrollWidth <= window.innerWidth"),
                "true",
            )
        self.ir("status")
        menu = '(() => { const n = document.querySelector(".nav"); return n.classList.contains("rola") + ":" + (n.querySelector("[aria-current=page]").getBoundingClientRect().right <= window.innerWidth); })()'
        self.conferir("celular: menu marca a rolagem e mostra o item atual", nav.js(menu), "true:true")
        nav.janela(1280, 900)
        self.conferir("registro local tem os pedidos", self.eventos(lambda e: e["tipo"] == "painel") > 30, True)
        self.conferir(
            "registro local sem erro de tela", self.eventos(lambda e: e["tipo"] in ("erro_front", "painel_erro")), 0
        )
        return self.falhas

    def esperar_ate(self, rotulo: str, expressao: str, esperado: str, tentativas: int = 60) -> None:
        obtido = ""
        for _ in range(tentativas):
            obtido = self.nav.js(expressao)
            if obtido == esperado:
                break
            self.nav.esperar(500)
        self.conferir(rotulo, obtido, esperado)

    def primeiro_uso(self) -> int:
        """Painel sem metas: as telas abrem vazias com o convite, a primeira visita cai no Começar, a conta é
        conferida sozinha (fixtures offline), grava uma meta e chega nas telas."""
        nav = self.nav
        nav.janela(1280, 900)
        self.ir("hoje")
        self.esperar_ate(
            "primeiro uso: sem metas a tela Hoje abre vazia, com o convite para o Começar",
            'location.hash + ":" + !!document.querySelector(".aviso-vazio")',
            "#/hoje:true",
        )
        nav.ir("%s/?e2e=%d" % (self.url, random.randint(0, 99999)))
        self.esperar_ate(
            "primeiro uso: a primeira visita sem metas abre no Começar",
            'location.hash + ":" + !!document.getElementById("t-comecar-conta")',
            "#/comecar:true",
        )
        self.esperar_ate(
            "primeiro uso: Claude Code e conectores conferidos sozinhos",
            'String(document.querySelectorAll(".conectores-conta li.conector-conectado").length >= 2)',
            "true",
        )
        self.esperar_ate(
            "primeiro uso: conta conferida (e-mail e calendário Metas)",
            'String(document.querySelectorAll("ul.conferencia li.ok").length >= 2)',
            "true",
        )
        nav.js(_clicar("Continuar"))
        self.esperar_ate("primeiro uso: passo das metas", 'String(!!document.getElementById("cm-titulo-1"))', "true")
        nav.js(
            _preencher("cm-titulo-1", "Correr 10 km")
            + _preencher("cm-prazo-1", "2026-12-15")
            + _preencher("cm-horas-1", "3")
            + "1"
        )
        nav.js(_clicar("Continuar"))
        self.esperar_ate("primeiro uso: passo do horário", 'String(!!document.getElementById("ch-seg_sex"))', "true")
        nav.js(_clicar("Continuar"))
        self.esperar_ate("primeiro uso: passo das fontes", 'String(!!document.getElementById("cf-lembretes"))', "true")
        nav.js(_clicar("Continuar"))
        self.esperar_ate(
            "primeiro uso: conferir já traz o e-mail da conta",
            '(document.getElementById("cc-email") || {}).value || ""',
            "pessoa@exemplo.test",
        )
        nav.js(_clicar("Gravar minhas metas"))
        self.esperar_ate(
            "primeiro uso: metas gravadas", 'String(!!document.getElementById("t-comecar-pronto"))', "true"
        )
        self.ir("metas")
        carregada = 'document.getElementById("tela").getAttribute("aria-busy") + ":" + (document.getElementById("tela").children.length > 1)'
        self.esperar_ate("primeiro uso: a tela Metas abre com a meta gravada", carregada, "false:true")
        self.ir("status")
        self.esperar_ate(
            "primeiro uso: Status com manutenção e o app para instalar",
            'String(!!document.getElementById("t-manutencao") && !!document.getElementById("t-app"))',
            "true",
        )
        self.conferir(
            "primeiro uso: registro local sem erro de tela",
            self.eventos(lambda e: e["tipo"] in ("erro_front", "painel_erro")),
            0,
        )
        return self.falhas

    def _acoes(self) -> None:
        self.ir("hoje")
        self.acao(
            "confirmar bloco",
            'document.querySelector("button.check[aria-pressed=false]:not([disabled])").click(), 1',
            "Confirmada",
        )
        self.acao("não fiz", 'document.querySelector("button.mini").click(), 1', "Anotado")
        self.acao(
            "decisão manter",
            'Array.from(document.querySelectorAll("button.saida")).find(b => /Manter/.test(b.textContent)).click(), 1',
            "segue como está",
        )
        self.ir("meta/M02")
        self.acao("sentimento", 'document.querySelector("button.escolha.s-firme").click(), 1', "Anotado para")
        self.acao("marco", 'document.querySelector("button.marco[aria-pressed=false]").click(), 1', "Marco")
        self.acao(
            "ajustar horas",
            'document.getElementById("aj-horas").value = "6", document.querySelector(".acoes-form .botao-escuro").click(), 1',
            "ajustada",
        )
        self.acao(
            "pausar", 'Array.from(document.querySelectorAll(".acoes-form button.mini"))[0].click(), 1', "ajustada"
        )
        self.acao(
            "retomar", 'Array.from(document.querySelectorAll(".acoes-form button.mini"))[0].click(), 1', "ajustada"
        )
        self.ir("conexoes")
        self.conferir(
            "conexões: cinco conexões e o estado do doctor",
            self.nav.js(
                'document.querySelectorAll("li.conexao").length + ":" + document.querySelectorAll("li.conexao .pilula").length'
            ),
            "5:5",
        )
        botao_notion = 'document.querySelector("li[data-conexao=notion] .conexao-fonte button").click(), 1'
        self.acao("fonte fora dos sinais", botao_notion, "próxima leitura mensal")
        self.acao("fonte de volta aos sinais", botao_notion, "próxima leitura mensal")
        self.ir("checkin")
        self.acao(
            "check-in vazio recusado",
            'document.querySelector(".barra-salvar .botao-escuro").click(), 1',
            "antes de salvar",
        )
        self.acao(
            "check-in completo",
            'document.querySelector(".ck-bloco button.sim").click(), document.querySelector(".ck-meta button.escolha").click(), document.getElementById("ck-nota").value = "manhã cedo rende", document.querySelector(".barra-salvar .botao-escuro").click(), 1',
            "Check-in salvo",
        )


def _clicar(texto: str) -> str:
    return (
        'Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === %s && !b.disabled).click(), 1'
        % json.dumps(texto)
    )


def _preencher(ident: str, valor: str) -> str:
    return (
        '(e => (e.value = %s, e.dispatchEvent(new Event("input", {bubbles: true})), '
        'e.dispatchEvent(new Event("change", {bubbles: true}))))(document.getElementById(%s)), '
        % (json.dumps(valor), json.dumps(ident))
    )


def _subir(argumentos: list[str], env: dict[str, str]) -> tuple[subprocess.Popen, str]:
    porta = _porta_livre()
    processo = subprocess.Popen(
        [sys.executable, str(RAIZ / "scripts" / "web.py"), *argumentos, "--porta", str(porta)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    url = "http://127.0.0.1:%d" % porta
    for _ in range(240):
        try:
            urllib.request.urlopen(url + "/", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    return processo, url


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E2E do painel: dados de exemplo e o primeiro uso sem metas")
    parser.add_argument("--navegador", choices=("gstack", "playwright"), default="gstack")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="gp-e2e-") as temporaria:
        pasta = Path(temporaria)
        logs_demo, logs_novo, vazia = pasta / "logs-demo", pasta / "logs-novo", pasta / "vazia"
        vazia.mkdir()
        servidores = [
            _subir(["--demo"], dict(os.environ, GP_LOGS_DIR=str(logs_demo))),
            _subir(
                ["--offline", "--dados", str(vazia)],
                dict(
                    os.environ,
                    GP_LOGS_DIR=str(logs_novo),
                    GP_RAIZ=str(pasta / "raiz"),
                    GP_OFFLINE_DIR=str(RAIZ / "tests" / "fixtures" / "offline"),
                ),
            ),
        ]
        navegador: Any = None
        try:
            navegador = (
                Playwright()
                if args.navegador == "playwright"
                else Gstack(os.environ.get("BROWSE") or str(BROWSE_PADRAO))
            )
            falhas = Percurso(navegador, servidores[0][1], logs_demo).rodar()
            falhas += Percurso(navegador, servidores[1][1], logs_novo).primeiro_uso()
        finally:
            if navegador is not None:
                navegador.fechar()
            for processo, _url in servidores:
                processo.terminate()
                processo.communicate(timeout=30)
    print()
    print("E2E do painel: tudo certo" if not falhas else "E2E do painel: %d item(ns) com FALHOU" % falhas)
    return 3 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
