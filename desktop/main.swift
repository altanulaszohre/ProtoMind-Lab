import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var process: Process?
    var timer: Timer?
    var root: URL!
    var ready: URL!
    var started = Date()
    var localURL: URL?
    var ending = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        root = Bundle.main.bundleURL.deletingLastPathComponent()
        let menu = NSMenu()
        let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "About ProtoMind Lab", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit ProtoMind Lab", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(); editItem.title = "Edit"; menu.addItem(editItem)
        let edit = NSMenu(title: "Edit"); editItem.submenu = edit
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0,y: 0,width: 1420,height: 970),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.title = "ProtoMind Lab"
        window.minSize = NSSize(width: 900,height: 700)
        window.backgroundColor = NSColor(calibratedRed:0.04,green:0.07,blue:0.09,alpha:1)
        window.delegate = self
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .nonPersistent()
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.autoresizingMask = [.width,.height]
        webView.navigationDelegate = self
        window.contentView!.addSubview(webView)
        window.center(); window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps:true)
        webView.loadHTMLString("<body style='background:#101a22;color:#b7d7ca;font:16px -apple-system;padding:60px'><h2>ProtoMind Lab</h2><p>Starting your local observatory…</p></body>",baseURL:nil)
        do {
            guard FileManager.default.fileExists(atPath:root.appendingPathComponent("scripts/observatory.sh").path) else {throw NSError(domain:"Keep this app in the ProtoMind Lab project directory.",code:1)}
            try FileManager.default.createDirectory(at:root.appendingPathComponent("tmp"),withIntermediateDirectories:true)
            try FileManager.default.createDirectory(at:root.appendingPathComponent("logs"),withIntermediateDirectories:true)
            ready = root.appendingPathComponent("tmp/desktop-\(UUID().uuidString).json")
            let log = root.appendingPathComponent("logs/desktop.log")
            if !FileManager.default.fileExists(atPath:log.path) {FileManager.default.createFile(atPath:log.path,contents:nil)}
            let output = try FileHandle(forWritingTo:log); try output.truncate(atOffset:0)
            let p = Process(); p.executableURL = URL(fileURLWithPath:"/bin/sh")
            p.arguments = [root.appendingPathComponent("scripts/observatory.sh").path,"--desktop","--port","0","--ready-file","tmp/"+ready.lastPathComponent]
            p.currentDirectoryURL = root; p.standardOutput = output; p.standardError = output
            process = p; try p.run()
            timer = Timer.scheduledTimer(withTimeInterval:0.2,repeats:true){[weak self] _ in self?.pollStartup()}
        } catch { showError("Could not start the local server. Run scripts/setup.sh, then rebuild the web app if needed. Details: \(error.localizedDescription)") }
    }
    func pollStartup() {
        if let data = try? Data(contentsOf:ready), let obj = try? JSONSerialization.jsonObject(with:data) as? [String:Any], let value = obj["url"] as? String, let url = URL(string:value) {
            timer?.invalidate(); localURL = url; try? FileManager.default.removeItem(at:ready)
            webView.load(URLRequest(url:url)); return
        }
        if process?.isRunning == false || Date().timeIntervalSince(started)>25 {
            timer?.invalidate(); showError("The local server did not become ready. Check logs/desktop.log and run scripts/setup.sh. No model download is needed for replay.")
        }
    }
    func showError(_ message:String) {
        let alert = NSAlert(); alert.messageText = "ProtoMind Lab could not start"; alert.informativeText = message
        alert.addButton(withTitle:"Close"); alert.runModal(); NSApp.terminate(nil)
    }
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy)->Void) {
        guard let url = action.request.url else {decisionHandler(.cancel);return}
        if url.scheme == "about" || (url.host == "127.0.0.1" && url.port == localURL?.port) {decisionHandler(.allow)} else {decisionHandler(.cancel)}
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool {true}
    func applicationShouldTerminate(_ sender:NSApplication)->NSApplication.TerminateReply {
        if ending || process?.isRunning != true {return .terminateNow}
        ending = true; timer?.invalidate(); process?.terminate()
        let owned = process!
        DispatchQueue.global().async {
            let deadline = Date().addingTimeInterval(12)
            while owned.isRunning && Date()<deadline {Thread.sleep(forTimeInterval:0.1)}
            if owned.isRunning {kill(owned.processIdentifier,SIGKILL)}
            DispatchQueue.main.async {NSApp.reply(toApplicationShouldTerminate:true)}
        }
        return .terminateLater
    }
}
let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
