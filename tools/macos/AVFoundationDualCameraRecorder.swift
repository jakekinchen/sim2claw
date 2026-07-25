#!/usr/bin/env swift

import Foundation
@preconcurrency import AVFoundation
import CoreMedia
import CoreVideo
import Darwin

private let readySchema = "sim2claw.native_dual_camera_recorder_ready.v1"
private let reportSchema = "sim2claw.native_dual_camera_recorder_report.v1"
private let eventSchema = "sim2claw.native_camera_callback_event.v1"

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
    let bitRate: Int
    let outputName: String
}

private struct Options {
    let d405: DeviceSpec
    let c922: DeviceSpec
    let outputRoot: String
    let readyTimeoutSeconds: Double

    static func parse(_ arguments: [String]) throws -> Options {
        var values: [String: String] = [:]
        var index = 1
        while index < arguments.count {
            guard arguments[index].hasPrefix("--"), index + 1 < arguments.count else {
                throw NSError(domain: "invalid_arguments", code: 1)
            }
            values[arguments[index]] = arguments[index + 1]
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
        func device(_ role: String, bitRate: Int, outputName: String) throws -> DeviceSpec {
            let prefix = "--\(role)"
            return DeviceSpec(
                role: role,
                name: try text("\(prefix)-name"),
                uniqueID: try text("\(prefix)-unique-id"),
                modelID: try text("\(prefix)-model-id"),
                formatIndex: try integer("\(prefix)-format-index"),
                rangeIndex: try integer("\(prefix)-range-index"),
                width: Int32(try integer("\(prefix)-width")),
                height: Int32(try integer("\(prefix)-height")),
                subtype: try text("\(prefix)-subtype"),
                fps: try number("\(prefix)-fps"),
                bitRate: bitRate,
                outputName: outputName
            )
        }
        return Options(
            d405: try device("d405", bitRate: 1_000_000, outputName: "wrist_d405.native.mov"),
            c922: try device("c922", bitRate: 4_000_000, outputName: "overhead_c922.native.mov"),
            outputRoot: try text("--output-root"),
            readyTimeoutSeconds: try number("--ready-timeout-seconds")
        )
    }
}

private struct FormatState: Codable {
    let role: String
    let localizedName: String
    let uniqueID: String
    let modelID: String
    let formatIndex: Int
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
    let d405OutputBoundToExactInput: Bool
    let c922OutputBoundToExactInput: Bool
    let d405: FormatState
    let c922: FormatState
}

private struct CallbackEvent: Codable {
    let schemaVersion: String
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
    let appendedToWriter: Bool
    let warmupExcluded: Bool
    let dropReason: String?
    let error: String?
}

private struct StreamSummary: Codable {
    let role: String
    let outputPath: String
    let outputCallbackCount: Int
    let appleDropCallbackCount: Int
    let writerAppendCount: Int
    let warmupExcludedCallbackCount: Int
    let writerBackpressureCount: Int
    let firstPTSSeconds: Double?
    let lastPTSSeconds: Double?
    let firstHostContinuousNS: UInt64?
    let lastHostContinuousNS: UInt64?
    let writerStatus: String
    let errors: [String]
}

private struct ReadyManifest: Codable {
    let schemaVersion: String
    let status: String
    let sessionCount: Int
    let commonSessionRunning: Bool
    let independentCameraSessions: Int
    let callbackTimestampPath: String
    let stages: [Stage]
    let streams: [StreamSummary]
    let semantics: [String: Bool]
}

private struct FinalReport: Codable {
    let schemaVersion: String
    let status: String
    let failureReason: String?
    let sessionCount: Int
    let independentCameraSessions: Int
    let callbackTimestampPath: String
    let stages: [Stage]
    let streams: [StreamSummary]
    let postStopFormatIndexOperationalGate: Bool
    let semantics: [String: Bool]
}

private final class ContinuousClock: @unchecked Sendable {
    private var info = mach_timebase_info_data_t()
    init() { mach_timebase_info(&info) }
    func now() -> UInt64 {
        UInt64(Double(mach_continuous_time()) * Double(info.numer) / Double(info.denom))
    }
}

private final class StopState: @unchecked Sendable {
    private let lock = NSLock()
    private var requested = false
    func request() {
        lock.lock()
        requested = true
        lock.unlock()
    }
    func isRequested() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return requested
    }
}

private final class EventSink: @unchecked Sendable {
    private let lock = NSLock()
    private let handle: FileHandle
    private let encoder: JSONEncoder

    init(url: URL) throws {
        FileManager.default.createFile(atPath: url.path, contents: nil)
        handle = try FileHandle(forWritingTo: url)
        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    }

    func append(_ event: CallbackEvent) {
        lock.lock()
        defer { lock.unlock() }
        do {
            var data = try encoder.encode(event)
            data.append(0x0a)
            try handle.write(contentsOf: data)
        } catch {
            FileHandle.standardError.write(
                Data("callback_event_write_failed: \(error)\n".utf8)
            )
        }
    }

    func close() {
        lock.lock()
        defer { lock.unlock() }
        handle.synchronizeFile()
        try? handle.close()
    }
}

private final class StreamWriter: @unchecked Sendable {
    let spec: DeviceSpec
    private let lock = NSLock()
    private let clock: ContinuousClock
    private let sink: EventSink
    private let writer: AVAssetWriter
    private let input: AVAssetWriterInput
    private var sessionStarted = false
    private var outputCount = 0
    private var dropCount = 0
    private var appendCount = 0
    private var warmupCount = 0
    private var backpressureCount = 0
    private var firstValidSourcePTS: Double?
    private var firstPTS: Double?
    private var lastPTS: Double?
    private var firstHostNS: UInt64?
    private var lastHostNS: UInt64?
    private var errors: [String] = []

    init(spec: DeviceSpec, root: URL, sink: EventSink, clock: ContinuousClock) throws {
        self.spec = spec
        self.sink = sink
        self.clock = clock
        let outputURL = root.appendingPathComponent(spec.outputName)
        writer = try AVAssetWriter(url: outputURL, fileType: .mov)
        input = AVAssetWriterInput(
            mediaType: .video,
            outputSettings: [
                AVVideoCodecKey: AVVideoCodecType.h264,
                AVVideoWidthKey: Int(spec.width),
                AVVideoHeightKey: Int(spec.height),
                AVVideoCompressionPropertiesKey: [
                    AVVideoAverageBitRateKey: spec.bitRate,
                    AVVideoExpectedSourceFrameRateKey: spec.fps,
                    AVVideoMaxKeyFrameIntervalKey: max(1, Int(spec.fps.rounded())),
                ],
            ]
        )
        input.expectsMediaDataInRealTime = true
        guard writer.canAdd(input) else {
            throw NSError(domain: "\(spec.role)_writer_input_not_admitted", code: 30)
        }
        writer.add(input)
        guard writer.startWriting() else {
            throw NSError(
                domain: "\(spec.role)_writer_start_failed_\(writer.error?.localizedDescription ?? "unknown")",
                code: 31
            )
        }
    }

    func append(
        sample: CMSampleBuffer,
        connection: AVCaptureConnection
    ) {
        let hostNS = clock.now()
        let ptsTime = CMSampleBufferGetPresentationTimeStamp(sample)
        let ptsValue = CMTimeGetSeconds(ptsTime)
        let durationValue = CMTimeGetSeconds(CMSampleBufferGetDuration(sample))
        let description = CMSampleBufferGetFormatDescription(sample)
        let dimensions = description.map(CMVideoFormatDescriptionGetDimensions)
        var appended = false
        var warmupExcluded = false
        var eventError: String?
        var sequence = 0

        lock.lock()
        outputCount += 1
        sequence = outputCount
        if !ptsValue.isFinite || ptsValue <= 1.0 {
            warmupExcluded = true
            warmupCount += 1
        } else {
            if firstValidSourcePTS == nil { firstValidSourcePTS = ptsValue }
            if ptsValue - (firstValidSourcePTS ?? ptsValue) < 1.0 {
                warmupExcluded = true
                warmupCount += 1
            }
        }
        if !warmupExcluded && !sessionStarted {
            writer.startSession(atSourceTime: ptsTime)
            sessionStarted = true
        }
        if warmupExcluded {
            // Preserve every callback in the ledger while keeping the frozen
            // one-source-PTS-second startup window out of production assets.
        } else if input.isReadyForMoreMediaData {
            appended = input.append(sample)
            if appended {
                appendCount += 1
                if firstPTS == nil { firstPTS = ptsValue.isFinite ? ptsValue : nil }
                lastPTS = ptsValue.isFinite ? ptsValue : lastPTS
                if firstHostNS == nil { firstHostNS = hostNS }
                lastHostNS = hostNS
            } else {
                eventError = writer.error?.localizedDescription ?? "writer_append_failed"
                errors.append(eventError!)
            }
        } else {
            backpressureCount += 1
            eventError = "writer_backpressure"
            errors.append(eventError!)
        }
        lock.unlock()

        sink.append(
            CallbackEvent(
                schemaVersion: eventSchema,
                role: spec.role,
                kind: "output",
                sequence: sequence,
                hostContinuousNS: hostNS,
                ptsSeconds: ptsValue.isFinite ? ptsValue : nil,
                durationSeconds: durationValue.isFinite ? durationValue : nil,
                width: dimensions.map { Int($0.width) },
                height: dimensions.map { Int($0.height) },
                subtype: description.map {
                    fourCC(CMFormatDescriptionGetMediaSubType($0))
                },
                connectionEnabled: connection.isEnabled,
                connectionActive: connection.isActive,
                appendedToWriter: appended,
                warmupExcluded: warmupExcluded,
                dropReason: nil,
                error: eventError
            )
        )
    }

    func recordDrop(
        sample: CMSampleBuffer,
        connection: AVCaptureConnection
    ) {
        let hostNS = clock.now()
        let ptsValue = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))
        let durationValue = CMTimeGetSeconds(CMSampleBufferGetDuration(sample))
        let description = CMSampleBufferGetFormatDescription(sample)
        let dimensions = description.map(CMVideoFormatDescriptionGetDimensions)
        let reason = CMGetAttachment(
            sample,
            key: kCMSampleBufferAttachmentKey_DroppedFrameReason,
            attachmentModeOut: nil
        ).map { String(describing: $0) }
        lock.lock()
        dropCount += 1
        let sequence = dropCount
        lock.unlock()
        sink.append(
            CallbackEvent(
                schemaVersion: eventSchema,
                role: spec.role,
                kind: "drop",
                sequence: sequence,
                hostContinuousNS: hostNS,
                ptsSeconds: ptsValue.isFinite ? ptsValue : nil,
                durationSeconds: durationValue.isFinite ? durationValue : nil,
                width: dimensions.map { Int($0.width) },
                height: dimensions.map { Int($0.height) },
                subtype: description.map {
                    fourCC(CMFormatDescriptionGetMediaSubType($0))
                },
                connectionEnabled: connection.isEnabled,
                connectionActive: connection.isActive,
                appendedToWriter: false,
                warmupExcluded: false,
                dropReason: reason,
                error: nil
            )
        )
    }

    func isReady() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return appendCount > 0 && errors.isEmpty
    }

    func hasFailure() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return !errors.isEmpty || dropCount > 0 || writer.status == .failed
    }

    func finish(timeoutSeconds: Double) {
        lock.lock()
        let shouldFinish = sessionStarted
        lock.unlock()
        guard shouldFinish else {
            writer.cancelWriting()
            lock.lock()
            errors.append("no_samples_appended")
            lock.unlock()
            return
        }
        input.markAsFinished()
        let semaphore = DispatchSemaphore(value: 0)
        writer.finishWriting { semaphore.signal() }
        if semaphore.wait(timeout: .now() + timeoutSeconds) == .timedOut {
            writer.cancelWriting()
            lock.lock()
            errors.append("writer_finish_timeout")
            lock.unlock()
        } else if writer.status != .completed {
            lock.lock()
            errors.append(
                writer.error?.localizedDescription ?? "writer_did_not_complete"
            )
            lock.unlock()
        }
    }

    func summary() -> StreamSummary {
        lock.lock()
        defer { lock.unlock() }
        return StreamSummary(
            role: spec.role,
            outputPath: spec.outputName,
            outputCallbackCount: outputCount,
            appleDropCallbackCount: dropCount,
            writerAppendCount: appendCount,
            warmupExcludedCallbackCount: warmupCount,
            writerBackpressureCount: backpressureCount,
            firstPTSSeconds: firstPTS,
            lastPTSSeconds: lastPTS,
            firstHostContinuousNS: firstHostNS,
            lastHostContinuousNS: lastHostNS,
            writerStatus: writerStatus(writer.status),
            errors: errors
        )
    }
}

private final class Delegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    let stream: StreamWriter
    init(stream: StreamWriter) { self.stream = stream }
    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        stream.append(sample: sampleBuffer, connection: connection)
    }
    func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        stream.recordDrop(sample: sampleBuffer, connection: connection)
    }
}

private func writerStatus(_ status: AVAssetWriter.Status) -> String {
    switch status {
    case .unknown: return "unknown"
    case .writing: return "writing"
    case .completed: return "completed"
    case .failed: return "failed"
    case .cancelled: return "cancelled"
    @unknown default: return "unknown_future_status"
    }
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
    let minimum = CMTimeGetSeconds(device.activeVideoMinFrameDuration)
    let maximum = CMTimeGetSeconds(device.activeVideoMaxFrameDuration)
    return FormatState(
        role: spec.role,
        localizedName: device.localizedName,
        uniqueID: device.uniqueID,
        modelID: device.modelID,
        formatIndex: device.formats.firstIndex { $0 === device.activeFormat } ?? -1,
        width: Int(dimensions.width),
        height: Int(dimensions.height),
        subtype: fourCC(CMFormatDescriptionGetMediaSubType(description)),
        minimumDurationSeconds: minimum.isFinite ? minimum : nil,
        maximumDurationSeconds: maximum.isFinite ? maximum : nil
    )
}

private func connectionIsBound(
    session: AVCaptureSession,
    connection: AVCaptureConnection,
    port: AVCaptureInput.Port
) -> Bool {
    session.connections.contains { $0 === connection }
        && connection.inputPorts.contains { $0 === port }
}

private func writeJSON<T: Encodable>(_ value: T, to url: URL) throws {
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    var data = try encoder.encode(value)
    data.append(0x0a)
    try data.write(to: url, options: .atomic)
}

private func run(_ options: Options) throws -> Int32 {
    guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
        throw NSError(domain: "camera_authorization_not_granted", code: 20)
    }
    let root = URL(fileURLWithPath: options.outputRoot, isDirectory: true)
    try FileManager.default.createDirectory(
        at: root, withIntermediateDirectories: true
    )
    let eventsURL = root.appendingPathComponent("camera_callback_timestamps.jsonl")
    let readyURL = root.appendingPathComponent("native_camera_ready.json")
    let reportURL = root.appendingPathComponent("native_camera_report.json")
    for url in [eventsURL, readyURL, reportURL] {
        guard !FileManager.default.fileExists(atPath: url.path) else {
            throw NSError(domain: "output_exists_\(url.lastPathComponent)", code: 21)
        }
    }

    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external, .builtInWideAngleCamera],
        mediaType: .video,
        position: .unspecified
    )
    let d405 = try findDevice(spec: options.d405, devices: discovery.devices)
    let c922 = try findDevice(spec: options.c922, devices: discovery.devices)
    let eventSink = try EventSink(url: eventsURL)
    let clock = ContinuousClock()
    let dWriter = try StreamWriter(
        spec: options.d405, root: root, sink: eventSink, clock: clock
    )
    let cWriter = try StreamWriter(
        spec: options.c922, root: root, sink: eventSink, clock: clock
    )
    let dDelegate = Delegate(stream: dWriter)
    let cDelegate = Delegate(stream: cWriter)
    let dQueue = DispatchQueue(label: "sim2claw.native-recorder.d405")
    let cQueue = DispatchQueue(label: "sim2claw.native-recorder.c922")
    let session = AVCaptureSession()
    var stages: [Stage] = []

    session.beginConfiguration()
    session.sessionPreset = .high
    try d405.lockForConfiguration()
    var dLocked = true
    defer { if dLocked { d405.unlockForConfiguration() } }
    try c922.lockForConfiguration()
    var cLocked = true
    defer { if cLocked { c922.unlockForConfiguration() } }
    try configure(d405, spec: options.d405)
    try configure(c922, spec: options.c922)

    let dInput = try AVCaptureDeviceInput(device: d405)
    let cInput = try AVCaptureDeviceInput(device: c922)
    guard session.canAddInput(dInput) else {
        throw NSError(domain: "d405_input_not_admitted", code: 22)
    }
    session.addInput(dInput)
    guard session.canAddInput(cInput) else {
        throw NSError(domain: "c922_second_video_input_not_admitted", code: 23)
    }
    session.addInput(cInput)

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
        throw NSError(domain: "d405_output_not_admitted", code: 24)
    }
    session.addOutputWithNoConnections(dOutput)
    guard session.canAddOutput(cOutput) else {
        throw NSError(domain: "c922_output_not_admitted", code: 25)
    }
    session.addOutputWithNoConnections(cOutput)
    guard
        let dPort = dInput.ports.first(where: { $0.mediaType == .video }),
        let cPort = cInput.ports.first(where: { $0.mediaType == .video })
    else {
        throw NSError(domain: "exact_video_input_port_unavailable", code: 26)
    }
    let dConnection = AVCaptureConnection(inputPorts: [dPort], output: dOutput)
    let cConnection = AVCaptureConnection(inputPorts: [cPort], output: cOutput)
    guard session.canAddConnection(dConnection) else {
        throw NSError(domain: "d405_exact_connection_not_admitted", code: 27)
    }
    session.addConnection(dConnection)
    guard session.canAddConnection(cConnection) else {
        throw NSError(domain: "c922_exact_connection_not_admitted", code: 28)
    }
    session.addConnection(cConnection)

    func stage(_ name: String) -> Stage {
        Stage(
            name: name,
            sessionRunning: session.isRunning,
            d405InputAdmitted: true,
            c922InputAdmitted: true,
            d405OutputAdmitted: true,
            c922OutputAdmitted: true,
            d405OutputBoundToExactInput: connectionIsBound(
                session: session, connection: dConnection, port: dPort
            ),
            c922OutputBoundToExactInput: connectionIsBound(
                session: session, connection: cConnection, port: cPort
            ),
            d405: state(d405, spec: options.d405),
            c922: state(c922, spec: options.c922)
        )
    }

    stages.append(stage("before_commit"))
    session.commitConfiguration()
    stages.append(stage("after_commit"))
    dOutput.setSampleBufferDelegate(dDelegate, queue: dQueue)
    cOutput.setSampleBufferDelegate(cDelegate, queue: cQueue)
    session.startRunning()
    stages.append(stage("after_start"))
    d405.unlockForConfiguration()
    dLocked = false
    c922.unlockForConfiguration()
    cLocked = false

    let stopState = StopState()
    signal(SIGINT, SIG_IGN)
    signal(SIGTERM, SIG_IGN)
    let interruptSource = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    let terminateSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
    interruptSource.setEventHandler { stopState.request() }
    terminateSource.setEventHandler { stopState.request() }
    interruptSource.resume()
    terminateSource.resume()

    let readyDeadline = Date().addingTimeInterval(options.readyTimeoutSeconds)
    while !(dWriter.isReady() && cWriter.isReady())
        && Date() < readyDeadline
        && !dWriter.hasFailure()
        && !cWriter.hasFailure()
    {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    let ready = dWriter.isReady() && cWriter.isReady()
    if ready {
        try writeJSON(
            ReadyManifest(
                schemaVersion: readySchema,
                status: "recording",
                sessionCount: 1,
                commonSessionRunning: session.isRunning,
                independentCameraSessions: 0,
                callbackTimestampPath: eventsURL.lastPathComponent,
                stages: stages,
                streams: [cWriter.summary(), dWriter.summary()],
                semantics: [
                    "camera_exposure_timestamps": false,
                    "cross_camera_exposure_synchronized": false,
                    "metric_depth": false,
                    "physical_authority": false,
                ]
            ),
            to: readyURL
        )
    } else {
        stopState.request()
    }

    while !stopState.isRequested() {
        if dWriter.hasFailure() || cWriter.hasFailure() {
            stopState.request()
            break
        }
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }

    if session.isRunning { session.stopRunning() }
    dQueue.sync {}
    cQueue.sync {}
    withExtendedLifetime((dDelegate, cDelegate)) {}
    stages.append(stage("after_stop"))
    cWriter.finish(timeoutSeconds: 12.0)
    dWriter.finish(timeoutSeconds: 12.0)
    eventSink.close()

    let summaries = [cWriter.summary(), dWriter.summary()]
    let completed = ready && summaries.allSatisfy {
        $0.writerStatus == "completed"
            && $0.writerAppendCount + $0.warmupExcludedCallbackCount
                == $0.outputCallbackCount
            && $0.appleDropCallbackCount == 0
            && $0.writerBackpressureCount == 0
            && $0.errors.isEmpty
    }
    let failureReason = completed
        ? nil
        : (
            ready
                ? "one_or_more_stream_writers_failed"
                : "both_streams_did_not_reach_first_frame_readiness"
        )
    try writeJSON(
        FinalReport(
            schemaVersion: reportSchema,
            status: completed ? "completed" : "failed",
            failureReason: failureReason,
            sessionCount: 1,
            independentCameraSessions: 0,
            callbackTimestampPath: eventsURL.lastPathComponent,
            stages: stages,
            streams: summaries,
            postStopFormatIndexOperationalGate: false,
            semantics: [
                "active_session_format_identity_required": true,
                "after_stop_format_object_identity_required": false,
                "camera_exposure_timestamps": false,
                "cross_camera_exposure_synchronized": false,
                "metric_depth": false,
                "physical_authority": false,
            ]
        ),
        to: reportURL
    )
    return completed ? 0 : 2
}

do {
    exit(try run(Options.parse(CommandLine.arguments)))
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationDualCameraRecorder: \(error)\n".utf8)
    )
    exit(2)
}
