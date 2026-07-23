import Foundation

enum DemoAction: String, CaseIterable, Sendable {
    case inverseToBase = "inverse_to_base"
    case baseToInverse = "base_to_inverse"
    case loop

    var title: String {
        switch self {
        case .inverseToBase: "Inverse → Base"
        case .baseToInverse: "Base → Inverse"
        case .loop: "Loop Back & Forth"
        }
    }

    var subtitle: String {
        switch self {
        case .inverseToBase: "Run the six return moves"
        case .baseToInverse: "Run the six forward moves"
        case .loop: "Run the five-minute 12-move cycle"
        }
    }

    var systemImage: String {
        switch self {
        case .inverseToBase: "arrow.backward.to.line"
        case .baseToInverse: "arrow.forward.to.line"
        case .loop: "repeat"
        }
    }
}

struct DemoLoopSnapshot: Codable, Equatable, Sendable {
    let status: String
    let action: String?
    let currentMove: String?
    let completedMoves: Int
    let totalMoves: Int
    let ready: Bool
    let physicalAuthority: Bool
    let error: String?

    enum CodingKeys: String, CodingKey {
        case status, action, ready, error
        case currentMove = "current_move"
        case completedMoves = "completed_moves"
        case totalMoves = "total_moves"
        case physicalAuthority = "physical_authority"
    }

    var isRunning: Bool { status == "running" || status == "stopping" }
}

struct StudioSourceSnapshot: Codable, Equatable, Sendable {
    let ready: Bool?
    let deviceName: String?
    let registrationState: String?

    enum CodingKeys: String, CodingKey {
        case ready
        case deviceName = "device_name"
        case registrationState = "registration_state"
    }
}

struct StudioSnapshot: Codable, Equatable, Sendable {
    let state: String
    let mainStatus: String
    let mode: String
    let physicalAuthority: Bool
    let source: StudioSourceSnapshot
    let demoLoop: DemoLoopSnapshot

    enum CodingKeys: String, CodingKey {
        case state, mode, source
        case mainStatus = "main_status"
        case physicalAuthority = "physical_authority"
        case demoLoop = "demo_loop"
    }
}

struct OrchestratorEnvelope: Decodable, Sendable {
    let ok: Bool
    let orchestrator: StudioSnapshot?
    let error: String?
}

enum StudioClientError: LocalizedError {
    case invalidResponse
    case rejected(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: "Studio returned an invalid response."
        case let .rejected(message): message
        }
    }
}

struct StudioClient: Sendable {
    var snapshot: @Sendable () async throws -> StudioSnapshot
    var sessionAction: @Sendable (_ action: String, _ mode: String?) async throws -> StudioSnapshot
    var demoAction: @Sendable (_ action: String) async throws -> StudioSnapshot

    static func live(baseURL: URL = URL(string: "http://127.0.0.1:4173")!) -> StudioClient {
        let transport = StudioTransport(baseURL: baseURL)
        return StudioClient(
            snapshot: { try await transport.snapshot() },
            sessionAction: { action, mode in
                try await transport.post(
                    path: "api/orchestrator/session",
                    payload: ["action": action, "mode": mode].compactMapValues { $0 }
                )
            },
            demoAction: { action in
                try await transport.post(
                    path: "api/orchestrator/demo",
                    payload: ["action": action]
                )
            }
        )
    }
}

private actor StudioTransport {
    let baseURL: URL
    let session: URLSession
    let decoder = JSONDecoder()

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func snapshot() async throws -> StudioSnapshot {
        let request = URLRequest(url: baseURL.appending(path: "api/orchestrator"))
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw StudioClientError.invalidResponse
        }
        return try decoder.decode(StudioSnapshot.self, from: data)
    }

    func post(path: String, payload: [String: String]) async throws -> StudioSnapshot {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(payload)
        let (data, response) = try await session.data(for: request)
        guard response is HTTPURLResponse else {
            throw StudioClientError.invalidResponse
        }
        let envelope = try decoder.decode(OrchestratorEnvelope.self, from: data)
        guard envelope.ok, let snapshot = envelope.orchestrator else {
            throw StudioClientError.rejected(envelope.error ?? "Studio rejected the command.")
        }
        return snapshot
    }
}
