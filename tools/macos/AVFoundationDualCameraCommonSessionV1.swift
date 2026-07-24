#!/usr/bin/env swift

import Foundation
@preconcurrency import AVFoundation
import CoreMedia
import CoreVideo
import Darwin

private let schema = "sim2claw.avfoundation_dual_camera_common_session_observation.v1"

private struct DeviceSpec {
    let role: String
    let name: String
    let uniqueID: String
    let modelID: String
    let formatIndex: Int
    let rangeIndex: Int
    let width: Int32
    let height: Int32
    let subtype: String
    let fps: Double
}

private struct Options {
    let d405: DeviceSpec
    let c922: DeviceSpec
    let duration: Double
    let maximumCallbacks: Int
    let contractSHA256: String
    let output: String

    static func parse(_ args: [String]) throws -> Options {
        var values: [String: String] = [:]
        var index = 1
        while index < args.count {
            guard args[index].hasPrefix("--"), index + 1 < args.count else {
                throw NSError(domain: "options", code: 1)
            }
            values[args[index]] = args[index + 1]
            index += 2
        }
        func text(_ key: String) throws -> String {
            guard let value = values[key], !value.isEmpty else {
                throw NSError(domain: "missing_\(key)", code: 2)
            }
            return value
        }
        func integer(_ key: String) throws -> Int {
            guard let value = Int(try text(key)), value >= 0 else {
                throw NSError(domain: "invalid_\(key)", code: 3)
            }
            return value
        }
        func number(_ key: String) throws -> Double {
            guard let value = Double(try text(key)), value.isFinite, value > 0 else {
                throw NSError(domain: "invalid_\(key)", code: 4)
            }
            return value
        }
        func device(_ prefix: String, role: String) throws -> DeviceSpec {
            DeviceSpec(
                role: role,
                name: try text("--\(prefix)-name"),
                uniqueID: try text("--\(prefix)-unique-id"),
                modelID: try text("--\(prefix)-model-id"),
                formatIndex: try integer("--\(prefix)-format-index"),
                rangeIndex: try integer("--\(prefix)-range-index"),
                width: Int32(try integer("--\(prefix)-width")),
                height: Int32(try integer("--\(prefix)-height")),
                subtype: try text("--\(prefix)-subtype"),
                fps: try number("--\(prefix)-fps")
            )
        }
        let hash = try text("--contract-sha256")
        guard hash.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else {
            throw NSError(domain: "invalid_contract_hash", code: 5)
        }
        return Options(
            d405: try device("d405", role: "d405"),
            c922: try device("c922", role: "c922"),
            duration: try number("--duration-seconds"),
            maximumCallbacks: try integer("--maximum-callbacks"),
            contractSHA256: hash,
            output: try text("--output")
        )
    }
}

private struct FormatState: Codable {
    let role: String
    let localizedName: String
    let uniqueID: String
    let modelID: String
    let formatIndex: Int
    let rangeIndex: Int
    let width: Int
    let height: Int
    let subtype: String
    let minimumDurationSeconds: Double?
    let maximumDurationSeconds: Double?
}

private struct Stage: Codable {
    let name: String
    let sessionRunning: Bool
    let d405InputAdmitted: Bool
    let c922InputAdmitted: Bool
    let d405OutputAdmitted: Bool
    let c922OutputAdmitted: Bool
    let d405: FormatState?
    let c922: FormatState?
}

private struct CallbackEvent: Codable {
    let eventIndex: Int
    let role: String
    let kind: String
    let sequence: Int
    let hostContinuousNS: UInt64
    let ptsSeconds: Double?
    let durationSeconds: Double?
    let width: Int?
    let height: Int?
    let subtype: String?
    let connectionEnabled: Bool
    let connectionActive: Bool
    let dropReason: String?
}

private struct Observation: Codable {
    let schemaVersion: String
    let contractSHA256: String
    let observerRole: String
    let status: String
    let failureReason: String?
    let detectedDeviceNames: [String]
    let d405MatchCount: Int
    let c922MatchCount: Int
    let commonCaptureSessionsUsed: Int
    let independentCameraSessionsUsed: Int
    let robotMotionTrialsUsed: Int
    let simulatorReplaysUsed: Int
    let providerCallsUsed: Int
    let durationSecondsRequested: Double
    let maximumCallbacks: Int
    let d405OutputCount: Int
    let d405DropCount: Int
    let c922OutputCount: Int
    let c922DropCount: Int
    let stages: [Stage]
    let events: [CallbackEvent]
}

private func fourCC(_ value: FourCharCode) -> String {
    let bytes = [
        UInt8((value >> 24) & 0xff), UInt8((value >> 16) & 0xff),
        UInt8((value >> 8) & 0xff), UInt8(value & 0xff),
    ]
    return bytes.allSatisfy { $0 >= 32 && $0 <= 126 }
        ? (String(bytes: bytes, encoding: .ascii) ?? String(format: "0x%08x", value))
        : String(format: "0x%08x", value)
}

private final class Clock {
    private var info = mach_timebase_info_data_t()
    init() { mach_timebase_info(&info) }
    func now() -> UInt64 {
        UInt64(Double(mach_continuous_time()) * Double(info.numer) / Double(info.denom))
    }
}

private final class Ledger: @unchecked Sendable {
    private let lock = NSLock()
    private let clock = Clock()
    private let maximum: Int
    private var rows: [CallbackEvent] = []
    private var counts: [String: Int] = [:]

    init(maximum: Int) { self.maximum = maximum }

    func append(
        role: String,
        kind: String,
        sample: CMSampleBuffer,
        connection: AVCaptureConnection,
        dropReason: String?
    ) {
        lock.lock()
        defer { lock.unlock() }
        guard rows.count < maximum else { return }
        let key = "\(role):\(kind)"
        counts[key, default: 0] += 1
        let description = CMSampleBufferGetFormatDescription(sample)
        let dimensions = description.map(CMVideoFormatDescriptionGetDimensions)
        let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        let duration = CMTimeGetSeconds(CMSampleBufferGetDuration(sample))
        rows.append(
            CallbackEvent(
                eventIndex: rows.count,
                role: role,
                kind: kind,
                sequence: counts[key, default: 0],
                hostContinuousNS: clock.now(),
                ptsSeconds: pts.isFinite ? pts : nil,
                durationSeconds: duration.isFinite ? duration : nil,
                width: dimensions.map { Int($0.width) },
                height: dimensions.map { Int($0.height) },
                subtype: description.map { fourCC(CMFormatDescriptionGetMediaSubType($0)) },
                connectionEnabled: connection.isEnabled,
                connectionActive: connection.isActive,
                dropReason: dropReason
            )
        )
    }

    func snapshot() -> ([CallbackEvent], [String: Int]) {
        lock.lock()
        defer { lock.unlock() }
        return (rows, counts)
    }
}

private final class Delegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let role: String
    let ledger: Ledger
    init(role: String, ledger: Ledger) {
        self.role = role
        self.ledger = ledger
    }
    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        ledger.append(
            role: role, kind: "output", sample: sampleBuffer,
            connection: connection, dropReason: nil
        )
    }
    func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        let reason = CMGetAttachment(
            sampleBuffer,
            key: kCMSampleBufferAttachmentKey_DroppedFrameReason,
            attachmentModeOut: nil
        ).map { String(describing: $0) }
        ledger.append(
            role: role, kind: "drop", sample: sampleBuffer,
            connection: connection, dropReason: reason
        )
    }
}

private func findDevice(
    spec: DeviceSpec,
    devices: [AVCaptureDevice]
) throws -> AVCaptureDevice {
    let matches = devices.filter { $0.localizedName == spec.name }
    guard matches.count == 1, let device = matches.first else {
        throw NSError(domain: "\(spec.role)_match_count_\(matches.count)", code: 10)
    }
    guard device.uniqueID == spec.uniqueID, device.modelID == spec.modelID else {
        throw NSError(domain: "\(spec.role)_identity_mismatch", code: 11)
    }
    return device
}

private func configure(_ device: AVCaptureDevice, spec: DeviceSpec) throws {
    guard spec.formatIndex < device.formats.count else {
        throw NSError(domain: "\(spec.role)_format_missing", code: 12)
    }
    let format = device.formats[spec.formatIndex]
    guard spec.rangeIndex < format.videoSupportedFrameRateRanges.count else {
        throw NSError(domain: "\(spec.role)_range_missing", code: 13)
    }
    let range = format.videoSupportedFrameRateRanges[spec.rangeIndex]
    let dimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
    let subtype = fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription))
    guard dimensions.width == spec.width, dimensions.height == spec.height,
          subtype == spec.subtype,
          abs(range.minFrameRate - spec.fps) < 1e-9,
          abs(range.maxFrameRate - spec.fps) < 1e-9
    else {
        throw NSError(domain: "\(spec.role)_format_identity_mismatch", code: 14)
    }
    device.activeFormat = format
    device.activeVideoMinFrameDuration = range.minFrameDuration
    device.activeVideoMaxFrameDuration = range.minFrameDuration
}

private func state(_ device: AVCaptureDevice, spec: DeviceSpec) -> FormatState {
    let description = device.activeFormat.formatDescription
    let dimensions = CMVideoFormatDescriptionGetDimensions(description)
    let subtype = fourCC(CMFormatDescriptionGetMediaSubType(description))
    let minimum = CMTimeGetSeconds(device.activeVideoMinFrameDuration)
    let maximum = CMTimeGetSeconds(device.activeVideoMaxFrameDuration)
    return FormatState(
        role: spec.role, localizedName: device.localizedName,
        uniqueID: device.uniqueID, modelID: device.modelID,
        formatIndex: spec.formatIndex, rangeIndex: spec.rangeIndex,
        width: Int(dimensions.width), height: Int(dimensions.height),
        subtype: subtype,
        minimumDurationSeconds: minimum.isFinite ? minimum : nil,
        maximumDurationSeconds: maximum.isFinite ? maximum : nil
    )
}

private func write(_ observation: Observation, path: String) throws {
    let url = URL(fileURLWithPath: path)
    guard !FileManager.default.fileExists(atPath: url.path) else {
        throw NSError(domain: "output_exists", code: 20)
    }
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(), withIntermediateDirectories: true
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    var data = try encoder.encode(observation)
    data.append(0x0a)
    try data.write(to: url, options: .withoutOverwriting)
}

private func run(_ options: Options) throws -> Int32 {
    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external, .builtInWideAngleCamera],
        mediaType: .video,
        position: .unspecified
    )
    let devices = discovery.devices
    let detected = devices.map(\.localizedName).sorted()
    let dMatches = devices.filter { $0.localizedName == options.d405.name }.count
    let cMatches = devices.filter { $0.localizedName == options.c922.name }.count
    guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
        throw NSError(domain: "camera_authorization_not_granted", code: 21)
    }
    let d405 = try findDevice(spec: options.d405, devices: devices)
    let c922 = try findDevice(spec: options.c922, devices: devices)
    let session = AVCaptureSession()
    session.beginConfiguration()
    session.sessionPreset = .high
    let dInput = try AVCaptureDeviceInput(device: d405)
    let cInput = try AVCaptureDeviceInput(device: c922)
    var dInputOK = false, cInputOK = false
    var dOutputOK = false, cOutputOK = false
    var stages: [Stage] = []

    guard session.canAddInput(dInput) else {
        throw NSError(domain: "d405_input_not_admitted", code: 22)
    }
    session.addInput(dInput); dInputOK = true
    guard session.canAddInput(cInput) else {
        session.commitConfiguration()
        let observation = Observation(
            schemaVersion: schema, contractSHA256: options.contractSHA256,
            observerRole: "dual_camera_common_session_callback_observer_only",
            status: "prerequisite_unavailable",
            failureReason: "c922_second_video_input_not_admitted",
            detectedDeviceNames: detected, d405MatchCount: dMatches,
            c922MatchCount: cMatches, commonCaptureSessionsUsed: 0,
            independentCameraSessionsUsed: 0, robotMotionTrialsUsed: 0,
            simulatorReplaysUsed: 0, providerCallsUsed: 0,
            durationSecondsRequested: options.duration,
            maximumCallbacks: options.maximumCallbacks,
            d405OutputCount: 0, d405DropCount: 0,
            c922OutputCount: 0, c922DropCount: 0,
            stages: [], events: []
        )
        try write(observation, path: options.output)
        return 2
    }
    session.addInput(cInput); cInputOK = true

    let dOutput = AVCaptureVideoDataOutput()
    dOutput.alwaysDiscardsLateVideoFrames = true
    dOutput.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String:
            Int(kCVPixelFormatType_422YpCbCr8)
    ]
    let cOutput = AVCaptureVideoDataOutput()
    cOutput.alwaysDiscardsLateVideoFrames = true
    cOutput.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String:
            Int(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)
    ]
    guard session.canAddOutput(dOutput) else {
        throw NSError(domain: "d405_output_not_admitted", code: 23)
    }
    session.addOutput(dOutput); dOutputOK = true
    guard session.canAddOutput(cOutput) else {
        throw NSError(domain: "c922_output_not_admitted", code: 24)
    }
    session.addOutput(cOutput); cOutputOK = true

    try d405.lockForConfiguration()
    var dLocked = true
    defer { if dLocked { d405.unlockForConfiguration() } }
    try c922.lockForConfiguration()
    var cLocked = true
    defer { if cLocked { c922.unlockForConfiguration() } }
    try configure(d405, spec: options.d405)
    try configure(c922, spec: options.c922)
    stages.append(Stage(
        name: "before_commit", sessionRunning: false,
        d405InputAdmitted: dInputOK, c922InputAdmitted: cInputOK,
        d405OutputAdmitted: dOutputOK, c922OutputAdmitted: cOutputOK,
        d405: state(d405, spec: options.d405),
        c922: state(c922, spec: options.c922)
    ))
    session.commitConfiguration()
    stages.append(Stage(
        name: "after_commit", sessionRunning: session.isRunning,
        d405InputAdmitted: dInputOK, c922InputAdmitted: cInputOK,
        d405OutputAdmitted: dOutputOK, c922OutputAdmitted: cOutputOK,
        d405: state(d405, spec: options.d405),
        c922: state(c922, spec: options.c922)
    ))

    let ledger = Ledger(maximum: options.maximumCallbacks)
    let dQueue = DispatchQueue(label: "sim2claw.common-session.d405")
    let cQueue = DispatchQueue(label: "sim2claw.common-session.c922")
    let dDelegate = Delegate(role: "d405", ledger: ledger)
    let cDelegate = Delegate(role: "c922", ledger: ledger)
    dOutput.setSampleBufferDelegate(dDelegate, queue: dQueue)
    cOutput.setSampleBufferDelegate(cDelegate, queue: cQueue)
    session.startRunning()
    stages.append(Stage(
        name: "after_start", sessionRunning: session.isRunning,
        d405InputAdmitted: dInputOK, c922InputAdmitted: cInputOK,
        d405OutputAdmitted: dOutputOK, c922OutputAdmitted: cOutputOK,
        d405: state(d405, spec: options.d405),
        c922: state(c922, spec: options.c922)
    ))
    d405.unlockForConfiguration(); dLocked = false
    c922.unlockForConfiguration(); cLocked = false
    if session.isRunning {
        RunLoop.current.run(until: Date().addingTimeInterval(options.duration))
        session.stopRunning()
    }
    dQueue.sync {}; cQueue.sync {}
    stages.append(Stage(
        name: "after_stop", sessionRunning: session.isRunning,
        d405InputAdmitted: dInputOK, c922InputAdmitted: cInputOK,
        d405OutputAdmitted: dOutputOK, c922OutputAdmitted: cOutputOK,
        d405: state(d405, spec: options.d405),
        c922: state(c922, spec: options.c922)
    ))
    let snapshot = ledger.snapshot()
    func count(_ role: String, _ kind: String) -> Int {
        snapshot.1["\(role):\(kind)", default: 0]
    }
    try write(
        Observation(
            schemaVersion: schema, contractSHA256: options.contractSHA256,
            observerRole: "dual_camera_common_session_callback_observer_only",
            status: "completed",
            failureReason: nil,
            detectedDeviceNames: detected, d405MatchCount: dMatches,
            c922MatchCount: cMatches, commonCaptureSessionsUsed: 1,
            independentCameraSessionsUsed: 0, robotMotionTrialsUsed: 0,
            simulatorReplaysUsed: 0, providerCallsUsed: 0,
            durationSecondsRequested: options.duration,
            maximumCallbacks: options.maximumCallbacks,
            d405OutputCount: count("d405", "output"),
            d405DropCount: count("d405", "drop"),
            c922OutputCount: count("c922", "output"),
            c922DropCount: count("c922", "drop"),
            stages: stages, events: snapshot.0
        ),
        path: options.output
    )
    return 0
}

do {
    exit(try run(Options.parse(CommandLine.arguments)))
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationDualCameraCommonSessionV1: \(error)\n".utf8)
    )
    exit(2)
}
