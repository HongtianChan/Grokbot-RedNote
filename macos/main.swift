import Cocoa
import Foundation
import WebKit

let serviceHost = "127.0.0.1"
let servicePort = 18765
let projectDir = "PROJECT_DIR"

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var service: Process?
    var startedService = false
    var pollTimer: Timer?
    var lastSignature = ""
    var pageReady = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        startServiceIfNeeded()
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startPolling()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        if startedService, let service, service.isRunning {
            service.terminate()
        }
    }

    private func buildWindow() {
        let rect = NSRect(x: 0, y: 0, width: 400, height: 680)
        window = NSWindow(
            contentRect: rect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "XHS Reader"
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("XHSReaderAvatar")
        window.appearance = NSAppearance(named: .darkAqua)
        window.titlebarAppearsTransparent = true
        window.titlebarSeparatorStyle = .none
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.minSize = NSSize(width: 320, height: 520)

        let container = NSView(frame: rect)
        container.wantsLayer = true
        container.autoresizingMask = [.width, .height]

        let effect = NSVisualEffectView(frame: rect)
        effect.autoresizingMask = [.width, .height]
        effect.material = .fullScreenUI
        effect.blendingMode = .behindWindow
        effect.state = .active
        effect.isEmphasized = true
        container.addSubview(effect)

        let dim = NSView(frame: rect)
        dim.autoresizingMask = [.width, .height]
        dim.wantsLayer = true
        dim.layer?.backgroundColor = NSColor(srgbRed: 0x30 / 255, green: 0x31 / 255, blue: 0x33 / 255, alpha: 0.55).cgColor
        container.addSubview(dim)

        let config = WKWebViewConfiguration()
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        webView = WKWebView(frame: rect, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.setValue(false, forKey: "drawsBackground")
        if #available(macOS 12.0, *) {
            webView.underPageBackgroundColor = .clear
        }
        webView.navigationDelegate = self
        container.addSubview(webView)

        window.contentView = container
        loadScene()
    }

    private func loadScene(attemptsLeft: Int = 40) {
        if isServiceUp(), let url = URL(string: "http://\(serviceHost):\(servicePort)/avatar/scene.html") {
            webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 8))
            return
        }
        if attemptsLeft <= 0 { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            self?.loadScene(attemptsLeft: attemptsLeft - 1)
        }
    }

    private func startPolling() {
        pollTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            self?.pollStatus()
        }
        pollTimer?.tolerance = 0.08
    }

    private func pollStatus() {
        guard pageReady, let url = URL(string: "http://\(serviceHost):\(servicePort)/status") else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 0.8
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            guard let self else { return }
            var payload: [String: Any] = [
                "ok": false,
                "busy": false,
                "searching": false,
                "activity": NSNull(),
                "keyword": "",
            ]
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            if code == 200, let data,
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let searching = obj["searching"] as? Bool ?? false
                let busy = (obj["busy"] as? Bool) ?? searching
                payload["ok"] = obj["ok"] as? Bool ?? true
                payload["busy"] = busy
                payload["searching"] = searching
                if let activity = obj["activity"] as? String, !activity.isEmpty {
                    payload["activity"] = activity
                } else {
                    payload["activity"] = NSNull()
                }
                payload["keyword"] = obj["keyword"] as? String ?? ""
            }
            DispatchQueue.main.async {
                self.applyStatus(payload)
            }
        }.resume()
    }

    private func applyStatus(_ payload: [String: Any], force: Bool = false) {
        guard pageReady else { return }
        let busy = payload["busy"] as? Bool ?? false
        let activity = payload["activity"] as? String ?? ""
        let keyword = payload["keyword"] as? String ?? ""
        let signature = "\(busy)|\(activity)|\(keyword)"
        if !force, signature == lastSignature { return }
        lastSignature = signature
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let json = String(data: data, encoding: .utf8) else { return }
        let js = """
        (async () => {
          const started = Date.now();
          while (!window.setScene && !window.setAvatar) {
            if (Date.now() - started > 4000) return;
            await new Promise((r) => setTimeout(r, 40));
          }
          const payload = \(json);
          if (window.setScene) window.setScene(payload);
          else if (window.setAvatar) window.setAvatar({ state: payload.busy ? "loading" : "happy", color: "#E5050F", eyeColor: "#FFFFFF", shape: "blob", reducedMotion: false, maxFrameRate: 60 });
        })()
        """
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    private func startServiceIfNeeded() {
        if isServiceUp() { return }
        let script = (projectDir as NSString).appendingPathComponent("xhs_reader.py")
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        proc.arguments = [script, "--service"]
        proc.currentDirectoryURL = URL(fileURLWithPath: projectDir)
        let logPath = "/tmp/xhs-reader-service.log"
        if !FileManager.default.fileExists(atPath: logPath) {
            FileManager.default.createFile(atPath: logPath, contents: nil)
        }
        let log = FileHandle(forWritingAtPath: logPath)
        proc.standardOutput = log
        proc.standardError = log
        do {
            try proc.run()
            service = proc
            startedService = true
        } catch {
            presentError("Could not start the local reader service: \(error)")
        }
    }

    private func isServiceUp() -> Bool {
        var request = URLRequest(url: URL(string: "http://\(serviceHost):\(servicePort)/health")!)
        request.timeoutInterval = 0.5
        let config = URLSessionConfiguration.ephemeral
        let queue = OperationQueue()
        let session = URLSession(configuration: config, delegate: nil, delegateQueue: queue)
        let sem = DispatchSemaphore(value: 0)
        var ok = false
        session.dataTask(with: request) { _, response, _ in
            if let http = response as? HTTPURLResponse, http.statusCode == 200 { ok = true }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 0.7)
        session.invalidateAndCancel()
        return ok
    }

    private func presentError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "XHS Reader"
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.runModal()
    }
}

extension AppDelegate: WKNavigationDelegate {
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        pageReady = true
        lastSignature = ""
        applyStatus(["busy": false, "searching": false, "activity": NSNull(), "keyword": ""], force: true)
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        // Keep the scene in-window; open note links in the default browser
        // so /go can 302 with its xsec_token intact.
        if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           let scheme = url.scheme?.lowercased(),
           scheme == "http" || scheme == "https" {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
