import Foundation

enum ServerControllerError: LocalizedError {
    case repositoryNotFound
    case uvNotFound
    case commandFailed(String)

    var errorDescription: String? {
        switch self {
        case .repositoryNotFound: "Could not locate the sim2claw repository."
        case .uvNotFound: "Could not locate uv. Install it or set SIM2CLAW_UV_PATH."
        case let .commandFailed(message): message
        }
    }
}

struct ServerClient: Sendable {
    var start: @Sendable () async throws -> Void
    var stop: @Sendable () async throws -> Void

    static func live() -> ServerClient {
        let controller = ServerProcessController()
        return ServerClient(
            start: { try await controller.start() },
            stop: { try await controller.stop() }
        )
    }
}

private actor ServerProcessController {
    private var launchedProcess: Process?

    func start() throws {
        if launchedProcess?.isRunning == true { return }
        let repository = try Self.repositoryRoot()
        let uv = try Self.uvExecutable()
        let process = Process()
        process.executableURL = uv
        process.arguments = [
            "run", "sim2claw", "studio",
            "--host", "127.0.0.1",
            "--port", "4173",
            "--no-open",
        ]
        process.currentDirectoryURL = repository
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        launchedProcess = process
    }

    func stop() throws {
        let output = try Self.runAndCapture(
            executable: URL(fileURLWithPath: "/usr/sbin/lsof"),
            arguments: ["-nP", "-tiTCP:4173", "-sTCP:LISTEN"]
        )
        let identifiers = output
            .split(whereSeparator: \.isNewline)
            .compactMap { Int32($0.trimmingCharacters(in: .whitespaces)) }
        for identifier in identifiers {
            _ = try? Self.runAndCapture(
                executable: URL(fileURLWithPath: "/bin/kill"),
                arguments: [String(identifier)]
            )
        }
        if launchedProcess?.isRunning == true {
            launchedProcess?.terminate()
        }
        launchedProcess = nil
    }

    private static func repositoryRoot() throws -> URL {
        let environment = ProcessInfo.processInfo.environment
        if let declared = environment["SIM2CLAW_REPO_ROOT"] {
            let url = URL(fileURLWithPath: declared, isDirectory: true)
            if isRepository(url) { return url }
        }
        var candidate = Bundle.main.bundleURL.deletingLastPathComponent()
        for _ in 0..<8 {
            if isRepository(candidate) { return candidate }
            candidate.deleteLastPathComponent()
        }
        candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<8 {
            if isRepository(candidate) { return candidate }
            candidate.deleteLastPathComponent()
        }
        throw ServerControllerError.repositoryNotFound
    }

    private static func isRepository(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.appending(path: "pyproject.toml").path)
            && FileManager.default.fileExists(atPath: url.appending(path: "src/sim2claw").path)
    }

    private static func uvExecutable() throws -> URL {
        if let declared = ProcessInfo.processInfo.environment["SIM2CLAW_UV_PATH"],
           FileManager.default.isExecutableFile(atPath: declared)
        {
            return URL(fileURLWithPath: declared)
        }
        for path in ["/opt/homebrew/bin/uv", "/usr/local/bin/uv"]
        where FileManager.default.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        throw ServerControllerError.uvNotFound
    }

    private static func runAndCapture(executable: URL, arguments: [String]) throws -> String {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = executable
        process.arguments = arguments
        process.standardOutput = pipe
        process.standardError = pipe
        try process.run()
        process.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let output = String(decoding: data, as: UTF8.self)
        if process.terminationStatus != 0 && !output.isEmpty {
            throw ServerControllerError.commandFailed(output.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return output
    }
}
