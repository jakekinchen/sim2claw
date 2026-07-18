import AppKit
import Foundation

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let controllerPath: String = {
        if let override = ProcessInfo.processInfo.environment["SIM2CLAW_JETSON_TELEOP_SCRIPT"] {
            return override
        }
        let executable = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        return executable.deletingLastPathComponent()
            .appendingPathComponent("mac-teleop.sh")
            .path
    }()

    private var window: NSWindow!
    private var statusLabel: NSTextField!
    private var toggleButton: NSButton!
    private var spinner: NSProgressIndicator!
    private var isRunning = false
    private var isBusy = false
    private var statusTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 430, height: 230))

        let title = NSTextField(labelWithString: "SO-101 Robot Teleoperation")
        title.font = .systemFont(ofSize: 22, weight: .semibold)
        title.alignment = .center
        title.frame = NSRect(x: 25, y: 178, width: 380, height: 30)
        content.addSubview(title)

        statusLabel = NSTextField(labelWithString: "Checking Jetson…")
        statusLabel.font = .systemFont(ofSize: 15, weight: .medium)
        statusLabel.alignment = .center
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.frame = NSRect(x: 25, y: 137, width: 350, height: 24)
        content.addSubview(statusLabel)

        spinner = NSProgressIndicator(frame: NSRect(x: 382, y: 140, width: 18, height: 18))
        spinner.style = .spinning
        spinner.controlSize = .small
        content.addSubview(spinner)

        toggleButton = makeButton(
            title: "▶  START TELEOP",
            color: NSColor.systemGreen,
            frame: NSRect(x: 70, y: 62, width: 290, height: 58),
            action: #selector(toggleTeleop)
        )
        content.addSubview(toggleButton)

        let hint = NSTextField(labelWithString: "Keep the Jetson connected to this Mac by USB-C.")
        hint.font = .systemFont(ofSize: 12)
        hint.alignment = .center
        hint.textColor = .tertiaryLabelColor
        hint.frame = NSRect(x: 25, y: 22, width: 380, height: 18)
        content.addSubview(hint)

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 430, height: 230),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "SO-101 Teleop Control"
        window.contentView = content
        window.center()
        window.isReleasedWhenClosed = false
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        runController("status")
        statusTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            guard let self, !self.isBusy else { return }
            self.runController("status", showBusy: false)
        }
    }

    private func makeButton(title: String, color: NSColor, frame: NSRect, action: Selector) -> NSButton {
        let button = NSButton(frame: frame)
        button.title = title
        button.font = .systemFont(ofSize: 18, weight: .bold)
        button.bezelStyle = .rounded
        button.isBordered = false
        button.wantsLayer = true
        button.layer?.backgroundColor = color.cgColor
        button.layer?.cornerRadius = 12
        button.contentTintColor = .white
        button.target = self
        button.action = action
        return button
    }

    @objc private func toggleTeleop() {
        runController(isRunning ? "stop" : "start")
    }

    private func setBusy(_ busy: Bool, message: String) {
        isBusy = busy
        toggleButton.isEnabled = !busy
        statusLabel.stringValue = message
        statusLabel.textColor = .secondaryLabelColor
        busy ? spinner.startAnimation(nil) : spinner.stopAnimation(nil)
    }

    private func showState(running: Bool) {
        isRunning = running
        statusLabel.stringValue = running ? "● TELEOP RUNNING" : "● TELEOP STOPPED"
        statusLabel.textColor = running ? .systemGreen : .systemRed
        toggleButton.title = running ? "■  STOP TELEOP" : "▶  START TELEOP"
        toggleButton.layer?.backgroundColor = (running ? NSColor.systemRed : NSColor.systemGreen).cgColor
    }

    private func runController(_ action: String, showBusy: Bool = true) {
        if showBusy {
            setBusy(true, message: action == "stop" ? "Stopping safely…" : action == "start" ? "Starting…" : "Checking Jetson…")
        } else {
            isBusy = true
        }

        let task = Process()
        let output = Pipe()
        task.executableURL = URL(fileURLWithPath: "/bin/bash")
        task.arguments = [controllerPath, action]
        task.standardOutput = output
        task.standardError = output

        task.terminationHandler = { [weak self] process in
            let data = output.fileHandleForReading.readDataToEndOfFile()
            let text = String(data: data, encoding: .utf8)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""

            DispatchQueue.main.async {
                guard let self else { return }
                self.isBusy = false
                self.toggleButton.isEnabled = true
                self.spinner.stopAnimation(nil)

                if process.terminationStatus != 0 {
                    self.statusLabel.stringValue = text.isEmpty ? "Could not reach the Jetson" : text
                    self.statusLabel.textColor = .systemOrange
                } else if text.contains("STARTED") || text == "RUNNING" || text.contains("already running") {
                    self.showState(running: true)
                } else {
                    self.showState(running: false)
                }
            }
        }

        do {
            try task.run()
        } catch {
            setBusy(false, message: "Could not launch controller")
            statusLabel.textColor = .systemOrange
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        statusTimer?.invalidate()
        return true
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
