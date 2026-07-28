#!/usr/bin/env swift

import Foundation
@preconcurrency import AVFoundation
import CoreMedia
import CoreVideo
import Darwin

private let observationSchema = "sim2claw.avfoundation_c922_callback_observation.v3"
private let eventSchema = "sim2claw.avfoundation_c922_callback_event.v3"

private enum ObserverFailure: Error, CustomStringConvertible {
    case invalidArguments(String)
    case outputExists(String)
    case authorization(Int)
    case deviceCount(Int)
    case deviceIdentity(String)
    case formatUnavailable
    case formatIdentity(String)
    case inputUnavailable
    case outputUnavailable
    case outputWrite(String)

    var description: String {
        switch self {
        case .invalidArguments(let detail): return "invalid_arguments: \(detail)"
        case .outputExists(let path): return "output_exists: \(path)"
        case .authorization(let status): return "camera_authorization_status: \(status)"
        case .deviceCount(let count): return "camera_exact_match_count: \(count)"
        case .deviceIdentity(let detail): return "camera_identity_mismatch: \(detail)"
        case .formatUnavailable: return "frozen_format_unavailable"
        case .formatIdentity(let detail): return "frozen_format_mismatch: \(detail)"
        case .inputUnavailable: return "capture_input_unavailable"
        case .outputUnavailable: return "capture_output_unavailable"
        case .outputWrite(let detail): return "output_write_failed: \(detail)"
        }
    }
}

private struct Options {
    let cameraName: String
    let cameraUniqueID: String
    let cameraModelID: String
    let formatIndex: Int
    let rangeIndex: Int
    let width: Int32
    let height: Int32
    let subtype: String
    let supportedFPS: Double
    let durationSeconds: Double
    let maximumCallbacks: Int
    let contractSHA256: String
    let outputPath: String

    static func parse(_ arguments: [String]) throws -> Options {
        var values: [String: String] = [:]
        var index = 1
        while index < arguments.count {
            let key = arguments[index]
            guard key.hasPrefix("--"), index + 1 < arguments.count else {
                throw ObserverFailure.invalidArguments("Expected --key value pairs.")
            }
            guard values[key] == nil else {
                throw ObserverFailure.invalidArguments("Duplicate argument \(key).")
            }
            values[key] = arguments[index + 1]
            index += 2
        }
        let expected = Set([
            "--camera-name", "--camera-unique-id", "--camera-model-id",
            "--format-index", "--range-index", "--width", "--height",
            "--subtype", "--supported-fps", "--duration-seconds",
            "--maximum-callbacks", "--contract-sha256", "--output",
        ])
        guard Set(values.keys).subtracting(expected).isEmpty else {
            throw ObserverFailure.invalidArguments("Unexpected argument.")
        }
        guard
            let cameraName = values["--camera-name"], !cameraName.isEmpty,
            let cameraUniqueID = values["--camera-unique-id"], !cameraUniqueID.isEmpty,
            let cameraModelID = values["--camera-model-id"], !cameraModelID.isEmpty,
            let formatText = values["--format-index"],
            let formatIndex = Int(formatText), formatIndex >= 0,
            let rangeText = values["--range-index"],
            let rangeIndex = Int(rangeText), rangeIndex >= 0,
            let widthText = values["--width"], let width = Int32(widthText), width > 0,
            let heightText = values["--height"], let height = Int32(heightText), height > 0,
            let subtype = values["--subtype"], subtype.count == 4,
            let fpsText = values["--supported-fps"],
            let supportedFPS = Double(fpsText), supportedFPS.isFinite, supportedFPS > 0,
            let durationText = values["--duration-seconds"],
            let durationSeconds = Double(durationText),
            durationSeconds.isFinite, durationSeconds > 0,
            let callbacksText = values["--maximum-callbacks"],
            let maximumCallbacks = Int(callbacksText), maximumCallbacks > 0,
            let contractSHA256 = values["--contract-sha256"],
            contractSHA256.count == 64,
            let outputPath = values["--output"], !outputPath.isEmpty
        else {
            throw ObserverFailure.invalidArguments("Required arguments are invalid.")
        }
        return Options(
            cameraName: cameraName,
            cameraUniqueID: cameraUniqueID,
            cameraModelID: cameraModelID,
            formatIndex: formatIndex,
            rangeIndex: rangeIndex,
            width: width,
            height: height,
            subtype: subtype,
            supportedFPS: supportedFPS,
            durationSeconds: durationSeconds,
            maximumCallbacks: maximumCallbacks,
            contractSHA256: contractSHA256,
            outputPath: outputPath
        )
    }
}

private struct TimeObservation: Codable {
    let valid: Bool
    let numeric: Bool
    let value: Int64
    let timescale: Int32
    let seconds: Double?

    init(_ time: CMTime) {
        valid = time.isValid
        numeric = time.isNumeric
        value = time.value
        timescale = time.timescale
        let raw = time.isNumeric ? CMTimeGetSeconds(time) : Double.nan
        seconds = raw.isFinite ? raw : nil
    }
}

private struct CallbackEvent: Codable {
    var schemaVersion = eventSchema
    var eventIndex: Int
    var eventType: String
    var hostContinuousNS: UInt64
    var authorizationStatusRawValue: Int?
    var exactMatchCount: Int?
    var detectedDeviceNames: [String]?
    var deviceLocalizedName: String?
    var deviceUniqueID: String?
    var deviceModelID: String?
    var formatIndex: Int?
    var frameRateRangeIndex: Int?
    var formatWidth: Int?
    var formatHeight: Int?
    var formatMediaSubtype: String?
    var supportedFPS: Double?
    var activeMinFrameDurationSeconds: Double?
    var activeMaxFrameDurationSeconds: Double?
    var sessionPresetRawValue: String?
    var deviceLockHeld: Bool?
    var sessionRunning: Bool?
    var localSequence: Int?
    var samplePTS: TimeObservation?
    var sampleDuration: TimeObservation?
    var pixelFormat: String?
    var connectionEnabled: Bool?
    var connectionActive: Bool?
    var dropReason: String?
    var dropReasonInfo: String?
    var sampleOutputCount: Int?
    var sampleDroppedCount: Int?
}

private struct Observation: Codable {
    var schemaVersion = observationSchema
    let contractSHA256: String
    var proofClass = "camera_source_callback_delivery"
    var observerRole = "source_callback_observer_only"
    let cameraNameRequested: String
    let cameraUniqueIDRequested: String
    let cameraModelIDRequested: String
    let formatIndexRequested: Int
    let frameRateRangeIndexRequested: Int
    let durationSecondsRequested: Double
    let maximumCallbacks: Int
    let sampleOutputCount: Int
    let sampleDroppedCount: Int
    let captureSessionsUsed: Int
    var d405LifecycleOperationsUsed = 0
    var robotMotionTrialsUsed = 0
    var simulatorReplaysUsed = 0
    var providerCallsUsed = 0
    let events: [CallbackEvent]
}

private func fourCC(_ value: FourCharCode) -> String {
    let bytes: [UInt8] = [
        UInt8((value >> 24) & 0xff),
        UInt8((value >> 16) & 0xff),
        UInt8((value >> 8) & 0xff),
        UInt8(value & 0xff),
    ]
    if bytes.allSatisfy({ $0 >= 32 && $0 <= 126 }) {
        return String(bytes: bytes, encoding: .ascii) ?? String(format: "0x%08x", value)
    }
    return String(format: "0x%08x", value)
}

private final class ContinuousClock {
    private let numer: UInt64
    private let denom: UInt64

    init() {
        var info = mach_timebase_info_data_t()
        mach_timebase_info(&info)
        numer = UInt64(info.numer)
        denom = UInt64(info.denom)
    }

    func nowNS() -> UInt64 {
        UInt64(
            (Double(mach_continuous_time()) * Double(numer)) / Double(denom)
        )
    }
}

private final class EventLedger: @unchecked Sendable {
    private let lock = NSLock()
    private let clock = ContinuousClock()
    private let maximumCallbacks: Int
    private var rows: [CallbackEvent] = []
    private var outputs = 0
    private var drops = 0

    init(maximumCallbacks: Int) {
        self.maximumCallbacks = maximumCallbacks
    }

    func emit(_ type: String, update: (inout CallbackEvent) -> Void = { _ in }) {
        lock.lock()
        defer { lock.unlock() }
        var event = CallbackEvent(
            eventIndex: rows.count,
            eventType: type,
            hostContinuousNS: clock.nowNS()
        )
        update(&event)
        rows.append(event)
    }

    func emitSample(
        _ type: String,
        sampleBuffer: CMSampleBuffer,
        connection: AVCaptureConnection,
        dropReason: String? = nil,
        dropReasonInfo: String? = nil
    ) {
        lock.lock()
        defer { lock.unlock() }
        guard outputs + drops < maximumCallbacks else { return }
        let isDrop = type == "sample_dropped"
        if isDrop { drops += 1 } else { outputs += 1 }
        let description = CMSampleBufferGetFormatDescription(sampleBuffer)
        let dimensions = description.map(CMVideoFormatDescriptionGetDimensions)
        let subtype = description.map { fourCC(CMFormatDescriptionGetMediaSubType($0)) }
        let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer)
        var event = CallbackEvent(
            eventIndex: rows.count,
            eventType: type,
            hostContinuousNS: clock.nowNS()
        )
        event.localSequence = isDrop ? drops : outputs
        event.samplePTS = TimeObservation(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
        event.sampleDuration = TimeObservation(CMSampleBufferGetDuration(sampleBuffer))
        event.formatWidth = dimensions.map { Int($0.width) }
        event.formatHeight = dimensions.map { Int($0.height) }
        event.formatMediaSubtype = subtype
        event.pixelFormat = pixelBuffer.map { fourCC(CVPixelBufferGetPixelFormatType($0)) }
        event.connectionEnabled = connection.isEnabled
        event.connectionActive = connection.isActive
        event.dropReason = dropReason
        event.dropReasonInfo = dropReasonInfo
        rows.append(event)
    }

    func snapshot() -> (events: [CallbackEvent], output: Int, dropped: Int) {
        lock.lock()
        defer { lock.unlock() }
        return (rows, outputs, drops)
    }
}

private final class SourceDelegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let ledger: EventLedger

    init(ledger: EventLedger) {
        self.ledger = ledger
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        ledger.emitSample("sample_output", sampleBuffer: sampleBuffer, connection: connection)
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        ledger.emitSample(
            "sample_dropped",
            sampleBuffer: sampleBuffer,
            connection: connection,
            dropReason: attachment(sampleBuffer, key: kCMSampleBufferAttachmentKey_DroppedFrameReason),
            dropReasonInfo: attachment(sampleBuffer, key: kCMSampleBufferAttachmentKey_DroppedFrameReasonInfo)
        )
    }

    private func attachment(_ sampleBuffer: CMSampleBuffer, key: CFString) -> String? {
        guard let value = CMGetAttachment(
            sampleBuffer,
            key: key,
            attachmentModeOut: nil
        ) else { return nil }
        return String(describing: value)
    }
}

private func formatIdentity(
    device: AVCaptureDevice,
    options: Options,
    preset: AVCaptureSession.Preset,
    lockHeld: Bool
) -> (exact: Bool, update: (inout CallbackEvent) -> Void) {
    let description = device.activeFormat.formatDescription
    let dimensions = CMVideoFormatDescriptionGetDimensions(description)
    let subtype = fourCC(CMFormatDescriptionGetMediaSubType(description))
    let minimum = CMTimeGetSeconds(device.activeVideoMinFrameDuration)
    let maximum = CMTimeGetSeconds(device.activeVideoMaxFrameDuration)
    let target = 1.0 / options.supportedFPS
    let exact = dimensions.width == options.width
        && dimensions.height == options.height
        && subtype == options.subtype
        && minimum.isFinite
        && maximum.isFinite
        && abs(minimum - target) < 1e-9
        && abs(maximum - target) < 1e-9
    let update: (inout CallbackEvent) -> Void = {
        $0.deviceLocalizedName = device.localizedName
        $0.deviceUniqueID = device.uniqueID
        $0.deviceModelID = device.modelID
        $0.formatIndex = options.formatIndex
        $0.frameRateRangeIndex = options.rangeIndex
        $0.formatWidth = Int(dimensions.width)
        $0.formatHeight = Int(dimensions.height)
        $0.formatMediaSubtype = subtype
        $0.supportedFPS = options.supportedFPS
        $0.activeMinFrameDurationSeconds = minimum
        $0.activeMaxFrameDurationSeconds = maximum
        $0.sessionPresetRawValue = preset.rawValue
        $0.deviceLockHeld = lockHeld
    }
    return (exact, update)
}

private func writeObservation(_ observation: Observation, path: String) throws {
    let url = URL(fileURLWithPath: path)
    guard !FileManager.default.fileExists(atPath: url.path) else {
        throw ObserverFailure.outputExists(url.path)
    }
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    do {
        var data = try encoder.encode(observation)
        data.append(0x0a)
        try data.write(to: url, options: .withoutOverwriting)
    } catch {
        throw ObserverFailure.outputWrite(String(describing: error))
    }
}

private func finish(options: Options, ledger: EventLedger) throws {
    let beforeFinish = ledger.snapshot()
    ledger.emit("observer_finished") {
        $0.sampleOutputCount = beforeFinish.output
        $0.sampleDroppedCount = beforeFinish.dropped
    }
    let final = ledger.snapshot()
    try writeObservation(
        Observation(
            contractSHA256: options.contractSHA256,
            cameraNameRequested: options.cameraName,
            cameraUniqueIDRequested: options.cameraUniqueID,
            cameraModelIDRequested: options.cameraModelID,
            formatIndexRequested: options.formatIndex,
            frameRateRangeIndexRequested: options.rangeIndex,
            durationSecondsRequested: options.durationSeconds,
            maximumCallbacks: options.maximumCallbacks,
            sampleOutputCount: final.output,
            sampleDroppedCount: final.dropped,
            captureSessionsUsed: 1,
            events: final.events
        ),
        path: options.outputPath
    )
}

private func run(_ options: Options) throws {
    let ledger = EventLedger(maximumCallbacks: options.maximumCallbacks)
    ledger.emit("observer_started")
    let authorization = AVCaptureDevice.authorizationStatus(for: .video)
    ledger.emit("authorization_observed") {
        $0.authorizationStatusRawValue = authorization.rawValue
    }
    guard authorization == .authorized else {
        throw ObserverFailure.authorization(authorization.rawValue)
    }

    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external, .builtInWideAngleCamera],
        mediaType: .video,
        position: .unspecified
    )
    let matches = discovery.devices.filter { $0.localizedName == options.cameraName }
    ledger.emit("device_discovery_observed") {
        $0.exactMatchCount = matches.count
        $0.detectedDeviceNames = discovery.devices.map(\.localizedName).sorted()
    }
    guard matches.count == 1, let device = matches.first else {
        throw ObserverFailure.deviceCount(matches.count)
    }
    guard device.uniqueID == options.cameraUniqueID, device.modelID == options.cameraModelID else {
        throw ObserverFailure.deviceIdentity(
            "unique=\(device.uniqueID), model=\(device.modelID)"
        )
    }
    guard options.formatIndex < device.formats.count else {
        throw ObserverFailure.formatUnavailable
    }
    let format = device.formats[options.formatIndex]
    guard options.rangeIndex < format.videoSupportedFrameRateRanges.count else {
        throw ObserverFailure.formatUnavailable
    }
    let range = format.videoSupportedFrameRateRanges[options.rangeIndex]
    let dimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
    let subtype = fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription))
    guard dimensions.width == options.width, dimensions.height == options.height else {
        throw ObserverFailure.formatIdentity("dimensions=\(dimensions.width)x\(dimensions.height)")
    }
    guard subtype == options.subtype,
          abs(range.maxFrameRate - options.supportedFPS) < 1e-9,
          abs(range.minFrameRate - options.supportedFPS) < 1e-9
    else {
        throw ObserverFailure.formatIdentity("subtype or rate changed")
    }

    let session = AVCaptureSession()
    session.beginConfiguration()
    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else { throw ObserverFailure.inputUnavailable }
    session.addInput(input)
    let output = AVCaptureVideoDataOutput()
    output.alwaysDiscardsLateVideoFrames = true
    output.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String:
            Int(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)
    ]
    guard session.canAddOutput(output) else { throw ObserverFailure.outputUnavailable }
    let queue = DispatchQueue(label: "sim2claw.avfoundation-c922-callback-delivery-v3")
    let delegate = SourceDelegate(ledger: ledger)
    session.addOutput(output)

    try device.lockForConfiguration()
    var deviceLockHeld = true
    defer {
        if deviceLockHeld {
            device.unlockForConfiguration()
        }
    }
    device.activeFormat = format
    device.activeVideoMinFrameDuration = range.minFrameDuration
    device.activeVideoMaxFrameDuration = range.minFrameDuration
    let beforeCommit = formatIdentity(
        device: device, options: options, preset: session.sessionPreset, lockHeld: true
    )
    ledger.emit("format_while_locked_before_commit", update: beforeCommit.update)
    session.commitConfiguration()
    let afterCommit = formatIdentity(
        device: device, options: options, preset: session.sessionPreset, lockHeld: true
    )
    ledger.emit("format_while_locked_after_commit", update: afterCommit.update)
    guard beforeCommit.exact && afterCommit.exact else {
        device.unlockForConfiguration()
        deviceLockHeld = false
        try finish(options: options, ledger: ledger)
        return
    }

    session.startRunning()
    ledger.emit("session_start_returned") { $0.sessionRunning = session.isRunning }
    let afterStart = formatIdentity(
        device: device, options: options, preset: session.sessionPreset, lockHeld: true
    )
    ledger.emit("format_while_locked_after_start", update: afterStart.update)
    device.unlockForConfiguration()
    deviceLockHeld = false
    ledger.emit("device_unlock_returned") { $0.deviceLockHeld = false }
    output.setSampleBufferDelegate(delegate, queue: queue)

    if session.isRunning && afterStart.exact {
        RunLoop.current.run(until: Date().addingTimeInterval(options.durationSeconds))
    }
    if session.isRunning {
        session.stopRunning()
    }
    ledger.emit("session_stop_returned") { $0.sessionRunning = session.isRunning }
    queue.sync {}
    try finish(options: options, ledger: ledger)
}

do {
    try run(Options.parse(CommandLine.arguments))
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationCallbackDeliveryV3: \(error)\n".utf8)
    )
    exit(2)
}
