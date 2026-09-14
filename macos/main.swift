// Goal Pacer.app: janela nativa do painel local (WKWebView em http://127.0.0.1:8765/), sem navegador.
//
// Dois jeitos de chegar ao Mac, o mesmo código:
//   - compilado na própria máquina pelo instalador (scripts/goalpacer/janela.py), sem Python dentro: só a janela;
//   - o app do .dmg (dev/empacotar.py), com Resources/python (Python universal) e Resources/goal-pacer (a versão com
//     o manifesto assinado). Ao abrir, se não há instalação, se ela é mais antiga que o app ou se o Python dos jobs
//     sumiu, o app roda o instalador embutido (instalar.py --instalar-ou-atualizar --de-app) e mostra o progresso;
//     depois abre o painel. Arrastar a versão nova para Aplicativos e abrir é o update.
// Endereço, agente do painel e textos vêm do Info.plist (textos do copy; no .dmg, dos dois idiomas). Links para fora
// do painel abrem no navegador padrão. Se o painel não responde, a janela acorda o agente do login (launchctl
// kickstart) e tenta outra vez por meio minuto. Fechar a janela não para nada: os jobs e o painel seguem por trás.
import Cocoa
import WebKit

let informacoes = Bundle.main.infoDictionary ?? [:]
let tentativasMaximas = 15
let linhasGuardadas = 200

func textosDoIdioma() -> [String: String] {
    if let porIdioma = informacoes["GPTextosIdiomas"] as? [String: [String: String]] {
        let preferido = Locale.preferredLanguages.first ?? "pt-BR"
        if let escolhidos = porIdioma[preferido.hasPrefix("pt") ? "pt-BR" : "en"] ?? porIdioma["pt-BR"] {
            return escolhidos
        }
    }
    return informacoes["GPTextos"] as? [String: String] ?? [:]
}

let textos = textosDoIdioma()

func texto(_ chave: String) -> String { textos[chave] ?? chave }

// o instalador que vem dentro do app do .dmg; o app compilado na máquina não tem
struct Embutido {
    let python: URL
    let instalador: URL
    let origem: URL

    static func achar() -> Embutido? {
        guard let recursos = Bundle.main.resourceURL else { return nil }
        let python = recursos.appendingPathComponent("python/bin/python3")
        let origem = recursos.appendingPathComponent("goal-pacer")
        let instalador = origem.appendingPathComponent("scripts/instalar.py")
        let arquivos = FileManager.default
        guard arquivos.isExecutableFile(atPath: python.path), arquivos.fileExists(atPath: instalador.path) else {
            return nil
        }
        return Embutido(python: python, instalador: instalador, origem: origem)
    }
}

func maisNova(_ versao: String, que outra: String) -> Bool {
    let a = versao.split(separator: ".").map { Int($0) ?? 0 }
    let b = outra.split(separator: ".").map { Int($0) ?? 0 }
    for indice in 0..<max(a.count, b.count) {
        let x = indice < a.count ? a[indice] : 0
        let y = indice < b.count ? b[indice] : 0
        if x != y { return x > y }
    }
    return false
}

// a mesma raiz que o Python usa (base.raiz: GP_RAIZ, senão ~/.goal-pacer do HOME); o teste do .dmg abre o app num HOME
// temporário
func raizDaInstalacao() -> URL {
    let ambiente = ProcessInfo.processInfo.environment
    if let raiz = ambiente["GP_RAIZ"], !raiz.isEmpty { return URL(fileURLWithPath: raiz) }
    let casa = ambiente["HOME"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.homeDirectoryForCurrentUser
    return casa.appendingPathComponent(".goal-pacer")
}

func instalacaoAtual() -> [String: Any]? {
    let caminho = raizDaInstalacao().appendingPathComponent("jobs/instalacao.json")
    guard let dados = try? Data(contentsOf: caminho) else { return nil }
    return (try? JSONSerialization.jsonObject(with: dados)) as? [String: Any]
}

func precisaPreparar() -> Bool {
    guard Embutido.achar() != nil else { return false }
    let doApp = informacoes["CFBundleShortVersionString"] as? String ?? "0.0.0"
    guard let atual = instalacaoAtual(), let instalada = atual["versao"] as? String else { return true }
    if let python = atual["python3"] as? String, !FileManager.default.isExecutableFile(atPath: python) {
        return true
    }
    return maisNova(doApp, que: instalada)
}

func literalJS(_ valor: String) -> String {
    guard let dados = try? JSONSerialization.data(withJSONObject: [valor]),
          let lista = String(data: dados, encoding: .utf8) else { return "\"\"" }
    return String(lista.dropFirst().dropLast())
}

func seguro(_ valor: String) -> String {
    valor.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
}

final class Janela: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    let endereco = URL(string: informacoes["GPEndereco"] as? String ?? "http://127.0.0.1:8765/")!
    let agente = informacoes["GPLabelPainel"] as? String ?? "com.goal-pacer.painel"
    var janela: NSWindow?
    var web: WKWebView?
    var tentativas = 0
    var preparacao: Process?
    var linhas: [String] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.mainMenu = menuPrincipal()
        let configuracao = WKWebViewConfiguration()
        configuracao.applicationNameForUserAgent = "GoalPacerApp"  // o painel sabe que já está no app
        let web = WKWebView(frame: .zero, configuration: configuracao)
        web.navigationDelegate = self
        web.uiDelegate = self
        let janela = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 860),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        janela.title = "Goal Pacer"
        janela.minSize = NSSize(width: 420, height: 560)
        janela.contentView = web
        janela.center()
        janela.setFrameAutosaveName("GoalPacerJanela")
        janela.makeKeyAndOrderFront(nil)
        self.web = web
        self.janela = janela
        NSApp.activate(ignoringOtherApps: true)
        if precisaPreparar() { preparar() } else { abrirPainel() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // --- instalação ou update pelo instalador embutido ----------------------------------------------------------

    func preparar() {
        guard let embutido = Embutido.achar(), preparacao == nil else { return }
        linhas = []
        web?.loadHTMLString(pagina(texto("instalando"), detalhe: ""), baseURL: nil)
        let processo = Process()
        processo.executableURL = embutido.python
        processo.arguments = [
            embutido.instalador.path, "--origem-padrao", embutido.origem.path, "--nao-interativo",
            "--instalar-ou-atualizar", "--de-app", Bundle.main.bundlePath,
        ]
        var ambiente = ProcessInfo.processInfo.environment
        ambiente["PYTHONUTF8"] = "1"
        ambiente["PYTHONDONTWRITEBYTECODE"] = "1"  // nada de __pycache__ dentro do app: mudaria o que foi assinado
        processo.environment = ambiente
        let saida = Pipe()
        processo.standardOutput = saida
        processo.standardError = saida
        saida.fileHandleForReading.readabilityHandler = { alca in
            let dados = alca.availableData
            guard !dados.isEmpty, let pedaco = String(data: dados, encoding: .utf8) else { return }
            DispatchQueue.main.async { self.acrescentar(pedaco) }
        }
        processo.terminationHandler = { fim in
            saida.fileHandleForReading.readabilityHandler = nil
            DispatchQueue.main.async { self.terminou(fim.terminationStatus) }
        }
        do {
            try processo.run()
            preparacao = processo
        } catch {
            linhas.append(error.localizedDescription)
            terminou(-1)
        }
    }

    func acrescentar(_ pedaco: String) {
        linhas += pedaco.split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        if linhas.count > linhasGuardadas { linhas.removeFirst(linhas.count - linhasGuardadas) }
        let ultima = literalJS(linhas.last ?? "")
        web?.evaluateJavaScript("var d = document.getElementById('detalhe'); if (d) { d.textContent = \(ultima); }")
    }

    func terminou(_ codigo: Int32) {
        preparacao = nil
        if codigo == 0 {
            tentativas = 0
            abrirPainel()
            return
        }
        let detalhe = linhas.suffix(12).joined(separator: "\n")
        web?.loadHTMLString(pagina(texto("instalacao_parou"), detalhe: detalhe, tentar: true), baseURL: nil)
    }

    // --- painel ---------------------------------------------------------------------------------------------

    func abrirPainel() {
        let pedido = URLRequest(url: endereco, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 2)
        URLSession.shared.dataTask(with: pedido) { _, resposta, _ in
            DispatchQueue.main.async {
                if resposta is HTTPURLResponse {
                    self.tentativas = 0
                    self.web?.load(URLRequest(url: self.endereco))
                } else {
                    self.esperarPainel()
                }
            }
        }.resume()
    }

    func esperarPainel() {
        if tentativas == 0 { acordarAgente() }
        tentativas += 1
        web?.loadHTMLString(pagina(texto(tentativas > tentativasMaximas ? "sem_painel" : "esperando")), baseURL: nil)
        if tentativas <= tentativasMaximas {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { self.abrirPainel() }
        }
    }

    func acordarAgente() {
        let processo = Process()
        let lancador = ProcessInfo.processInfo.environment["GP_LAUNCHCTL"] ?? "/bin/launchctl"  // o do teste, se houver
        processo.executableURL = URL(fileURLWithPath: lancador.isEmpty ? "/bin/launchctl" : lancador)
        processo.arguments = ["kickstart", "gui/\(getuid())/\(agente)"]
        try? processo.run()
    }

    func pagina(_ mensagem: String, detalhe: String = "", tentar: Bool = false) -> String {
        let botao = tentar
            ? "<p><a href=\"goalpacer://tentar\" style=\"display:inline-block;margin-top:12px;padding:10px 18px;"
                + "border-radius:999px;background:#15181D;color:#FFF;text-decoration:none\">"
                + "\(seguro(texto("tentar_outra_vez")))</a></p>"
            : ""
        return "<html><body style=\"margin:0;display:grid;place-items:center;height:100vh;background:#E9ECEF;"
            + "color:#15181D;font:15px -apple-system,sans-serif\"><div style=\"max-width:40em;text-align:center;"
            + "padding:24px\"><p style=\"line-height:1.5\">\(seguro(mensagem))</p><pre id=\"detalhe\" style=\""
            + "white-space:pre-wrap;text-align:left;font:12px ui-monospace,monospace;color:#4E5561\">"
            + "\(seguro(detalhe))</pre>\(botao)</div></body></html>"
    }

    // painel dentro da janela; o resto (Google Calendar, ajuda) no navegador padrão
    func webView(
        _ webView: WKWebView,
        decidePolicyFor acao: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = acao.request.url else { return decisionHandler(.allow) }
        if url.scheme == "goalpacer" {
            decisionHandler(.cancel)
            return preparar()
        }
        if url.scheme == "about" || (url.host == endereco.host && url.port == endereco.port) {
            return decisionHandler(.allow)
        }
        if ["http", "https", "mailto"].contains(url.scheme ?? "") { NSWorkspace.shared.open(url) }
        decisionHandler(.cancel)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for acao: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if let url = acao.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if preparacao == nil { abrirPainel() }
    }

    @objc func recarregar(_ sender: Any?) {
        if preparacao != nil { return }
        tentativas = 0
        if precisaPreparar() { preparar() } else { abrirPainel() }
    }
}

func menuPrincipal() -> NSMenu {
    let principal = NSMenu()
    func item(_ chave: String, _ acao: Selector, _ tecla: String, _ extras: NSEvent.ModifierFlags = []) -> NSMenuItem {
        let novo = NSMenuItem(title: texto(chave), action: acao, keyEquivalent: tecla)
        novo.keyEquivalentModifierMask = extras.union(.command)
        return novo
    }
    func submenu(_ titulo: String, _ itens: [NSMenuItem]) {
        let menu = NSMenu(title: titulo)
        itens.forEach { menu.addItem($0) }
        let raiz = NSMenuItem()
        raiz.submenu = menu
        principal.addItem(raiz)
    }
    submenu("Goal Pacer", [
        item("ocultar", #selector(NSApplication.hide(_:)), "h"),
        NSMenuItem.separator(),
        item("sair", #selector(NSApplication.terminate(_:)), "q"),
    ])
    submenu(texto("editar"), [
        item("desfazer", Selector(("undo:")), "z"),
        item("refazer", Selector(("redo:")), "z", .shift),
        NSMenuItem.separator(),
        item("recortar", #selector(NSText.cut(_:)), "x"),
        item("copiar", #selector(NSText.copy(_:)), "c"),
        item("colar", #selector(NSText.paste(_:)), "v"),
        item("selecionar_tudo", #selector(NSText.selectAll(_:)), "a"),
    ])
    submenu(texto("ver"), [item("recarregar", #selector(Janela.recarregar(_:)), "r")])
    submenu(texto("janela"), [
        item("minimizar", #selector(NSWindow.performMiniaturize(_:)), "m"),
        item("fechar", #selector(NSWindow.performClose(_:)), "w"),
    ])
    return principal
}

let aplicacao = NSApplication.shared
let delegado = Janela()
aplicacao.delegate = delegado
aplicacao.setActivationPolicy(.regular)
aplicacao.run()
