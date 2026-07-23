import Foundation
import Observation

@MainActor
@Observable
final class DemoControlStore {
    enum Activity: Equatable {
        case idle
        case starting
        case stopping
        case commanding(DemoAction)

        var label: String {
            switch self {
            case .idle: "Ready"
            case .starting: "Starting Studio…"
            case .stopping: "Stopping after the current move…"
            case let .commanding(action): "Starting \(action.title)…"
            }
        }
    }

    private let studio: StudioClient
    private let server: ServerClient

    var snapshot: StudioSnapshot?
    var activity: Activity = .idle
    var message = "Power on to initialize the C922 overhead camera and follower."
    var errorMessage: String?

    init(studio: StudioClient = .live(), server: ServerClient = .live()) {
        self.studio = studio
        self.server = server
    }

    var isPowered: Bool { snapshot != nil }
    var isBusy: Bool { activity != .idle || snapshot?.demoLoop.isRunning == true }
    var motionReady: Bool {
        snapshot?.demoLoop.ready == true
            && snapshot?.demoLoop.physicalAuthority == true
            && snapshot?.source.ready == true
    }

    func refresh(silent: Bool = true) async {
        do {
            let latest = try await studio.snapshot()
            snapshot = latest
            if latest.demoLoop.isRunning {
                message = progressMessage(latest.demoLoop)
            } else if latest.demoLoop.status == "completed" {
                message = "Sequence complete. Follower torque is off."
            } else if latest.demoLoop.status == "failed" {
                errorMessage = latest.demoLoop.error ?? "The fixed demo sequence failed."
            } else if motionReady {
                message = "Motion ready · follower + overhead connected"
            }
        } catch {
            snapshot = nil
            if !silent { errorMessage = error.localizedDescription }
        }
    }

    func togglePower() async {
        if isPowered {
            await powerOff()
        } else {
            await powerOn()
        }
    }

    func powerOn() async {
        guard activity == .idle else { return }
        activity = .starting
        errorMessage = nil
        do {
            if (try? await studio.snapshot()) == nil {
                try await server.start()
            }
            let connected = try await waitForServer()
            let ready: StudioSnapshot
            switch connected.state {
            case "STOPPED":
                ready = try await studio.sessionAction("start", "demo_physical")
            case "PAUSED":
                ready = try await studio.sessionAction("resume", nil)
            default:
                ready = connected
            }
            snapshot = ready
            message = ready.demoLoop.ready
                ? "Motion ready · follower + overhead connected"
                : "Studio started; waiting for demo hardware preflight."
        } catch {
            errorMessage = error.localizedDescription
        }
        activity = .idle
    }

    func powerOff() async {
        guard activity == .idle else { return }
        activity = .stopping
        errorMessage = nil
        do {
            if snapshot?.demoLoop.isRunning == true {
                _ = try await studio.demoAction("stop")
                try await waitForMotionStop()
            }
            if let current = try? await studio.snapshot(), current.state != "STOPPED" {
                _ = try await studio.sessionAction("stop", nil)
            }
            try await server.stop()
            snapshot = nil
            message = "Studio stopped. Follower motion authority is closed."
        } catch {
            errorMessage = error.localizedDescription
        }
        activity = .idle
    }

    func run(_ action: DemoAction) async {
        guard activity == .idle, motionReady, snapshot?.demoLoop.isRunning != true else { return }
        activity = .commanding(action)
        errorMessage = nil
        do {
            snapshot = try await studio.demoAction(action.rawValue)
            message = "Running \(action.title)…"
        } catch {
            errorMessage = error.localizedDescription
        }
        activity = .idle
    }

    private func waitForServer() async throws -> StudioSnapshot {
        var latestError: Error = StudioClientError.invalidResponse
        for _ in 0..<40 {
            do { return try await studio.snapshot() }
            catch { latestError = error }
            try await Task.sleep(for: .milliseconds(250))
        }
        throw latestError
    }

    private func waitForMotionStop() async throws {
        for _ in 0..<180 {
            let latest = try await studio.snapshot()
            snapshot = latest
            if !latest.demoLoop.isRunning { return }
            try await Task.sleep(for: .seconds(1))
        }
        throw StudioClientError.rejected("The current guarded move did not stop within three minutes.")
    }

    private func progressMessage(_ loop: DemoLoopSnapshot) -> String {
        let move = loop.currentMove?
            .replacingOccurrences(of: "_to_", with: " → ")
            .uppercased()
        let detail = move.map { " · \($0)" } ?? ""
        return "Running \(loop.completedMoves)/\(loop.totalMoves)\(detail)"
    }
}
