#!/usr/bin/env swift

import Foundation
@preconcurrency import AVFoundation
import CoreMedia
import CoreVideo
import Darwin

private let eventSchema = "sim2claw.avfoundation_source_event.v1"

private struct ProbeOptions {
    let cameraName: String
    let width: Int32
    let height: Int32
    let fps: Int32
    let durationSeconds: Double
    let outputPath: String

    static func parse(_ arguments: [String]) throws -> ProbeOptions {
        var values: [String: String] = [:]
        var index = 1
        while index < arguments.count {
            let key = arguments[index]
            guard key.hasPrefix("--"), index + 1 < arguments.count else {
                throw ProbeFailure.invalidArguments("Expected --key value pairs.")
            }
            if values[key] != nil {
                throw ProbeFailure.invalidArguments("Duplicate argument \(key).")
            }
            values[key] = arguments[index + 1]
            index += 2
        }

        guard let cameraName = values["--camera-name"], !cameraName.isEmpty,
              let widthText = values["--width"], let width = Int32(widthText), width > 0,
              let heightText = values["--height"], let height = Int32(heightText), height > 0,
              let fpsText = values["--fps"], let fps = Int32(fpsText), fps > 0,
              let durationText = values["--duration-seconds"],
              let durationSeconds = Double(durationText), durationSeconds > 0,
              let outputPath = values["--output"], !outputPath.isEmpty
        else {
            throw ProbeFailure.invalidArguments(
                "Required: --camera-name --width --height --fps "
                    + "--duration-seconds --output."
            )
        }
        let expected = Set([
            "--camera-name",
            "--width",
            "--height",
            "--fps",
            "--duration-seconds",
            "--output",
        ])
        let unexpected = Set(values.keys).subtracting(expected)
        if !unexpected.isEmpty {
            throw ProbeFailure.invalidArguments(
                "Unexpected arguments: \(unexpected.sorted().joined(separator: ", "))."
            )
        }
        return ProbeOptions(
            cameraName: cameraName,
            width: width,
            height: height,
            fps: fps,
            durationSeconds: durationSeconds,
            outputPath: outputPath
        )
    }
}

private enum ProbeFailure: Error, CustomStringConvertible {
    case invalidArguments(String)
    case outputExists(String)
    case deviceCount(Int)
    case inputUnavailable
    case outputUnavailable
    case formatUnavailable
    case noSamples
    case outputWrite(String)
    case runtime(String)

    var description: String {
        switch self {
        case .invalidArguments(let detail):
            return "invalid_arguments: \(detail)"
        case .outputExists(let path):
            return "output_exists: \(path)"
        case .deviceCount(let count):
            return "camera_exact_match_count: \(count)"
        case .inputUnavailable:
            return "capture_input_unavailable"
        case .outputUnavailable:
            return "capture_output_unavailable"
        case .formatUnavailable:
            return "requested_format_unavailable"
        case .noSamples:
            return "no_source_samples"
        case .outputWrite(let detail):
            return "output_write_failed: \(detail)"
        case .runtime(let detail):
            return "runtime_failure: \(detail)"
        }
    }
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

    func stamp() -> [String: Any] {
        let ticks = mach_continuous_time()
        let nanoseconds = UInt64((Double(ticks) * Double(numer)) / Double(denom))
        return [
            "host_continuous_ticks": ticks,
            "host_continuous_ns": nanoseconds,
            "mach_timebase_numer": numer,
            "mach_timebase_denom": denom,
        ]
    }
}

private final class EventSink {
    private let lock = NSLock()
    private let handle: FileHandle
    private let clock = ContinuousClock()
    private var nextIndex = 0
    private(set) var writeFailure: String?

    init(path: String) throws {
        let url = URL(fileURLWithPath: path)
        if FileManager.default.fileExists(atPath: url.path) {
            throw ProbeFailure.outputExists(url.path)
        }
        let parent = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: parent,
            withIntermediateDirectories: true
        )
        guard FileManager.default.createFile(atPath: url.path, contents: nil),
              let opened = FileHandle(forWritingAtPath: url.path)
        else {
            throw ProbeFailure.outputWrite("Could not create \(url.path).")
        }
        handle = opened
    }

    deinit {
        try? handle.close()
    }

    func emit(_ eventType: String, fields: [String: Any] = [:]) {
        lock.lock()
        defer { lock.unlock() }
        guard writeFailure == nil else {
            return
        }
        var event = fields
        event["schema_version"] = eventSchema
        event["event_type"] = eventType
        event["event_index"] = nextIndex
        for (key, value) in clock.stamp() {
            event[key] = value
        }
        event["wall_time_utc"] = ISO8601DateFormatter().string(from: Date())
        nextIndex += 1
        do {
            let data = try JSONSerialization.data(
                withJSONObject: event,
                options: [.sortedKeys, .withoutEscapingSlashes]
            )
            handle.write(data)
            handle.write(Data([0x0a]))
            try handle.synchronize()
        } catch {
            writeFailure = String(describing: error)
        }
    }
}

private final class SourceDelegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let sink: EventSink
    private let lock = NSLock()
    private var outputSamples = 0
    private var droppedSamples = 0

    init(sink: EventSink) {
        self.sink = sink
    }

    func counts() -> (output: Int, dropped: Int) {
        lock.lock()
        defer { lock.unlock() }
        return (outputSamples, droppedSamples)
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        let callbackEntered = mach_continuous_time()
        lock.lock()
        outputSamples += 1
        let sequence = outputSamples
        lock.unlock()
        sink.emit(
            "sample_output",
            fields: sampleFields(
                sampleBuffer,
                localSequence: sequence,
                callbackEntered: callbackEntered,
                connection: connection
            )
        )
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        let callbackEntered = mach_continuous_time()
        lock.lock()
        droppedSamples += 1
        let sequence = droppedSamples
        lock.unlock()
        var fields = sampleFields(
            sampleBuffer,
            localSequence: sequence,
            callbackEntered: callbackEntered,
            connection: connection
        )
        fields["drop_reason"] = attachmentDescription(
            sampleBuffer,
            key: kCMSampleBufferAttachmentKey_DroppedFrameReason
        )
        fields["drop_reason_info"] = attachmentDescription(
            sampleBuffer,
            key: kCMSampleBufferAttachmentKey_DroppedFrameReasonInfo
        )
        sink.emit("sample_dropped", fields: fields)
    }

    private func sampleFields(
        _ sampleBuffer: CMSampleBuffer,
        localSequence: Int,
        callbackEntered: UInt64,
        connection: AVCaptureConnection
    ) -> [String: Any] {
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        let duration = CMSampleBufferGetDuration(sampleBuffer)
        var fields: [String: Any] = [
            "local_sequence": localSequence,
            "callback_entered_ticks": callbackEntered,
            "callback_exited_ticks": mach_continuous_time(),
            "connection_enabled": connection.isEnabled,
            "connection_active": connection.isActive,
        ]
        appendTime(pts, prefix: "sample_pts", into: &fields)
        appendTime(duration, prefix: "sample_duration", into: &fields)
        if let description = CMSampleBufferGetFormatDescription(sampleBuffer) {
            let dimensions = CMVideoFormatDescriptionGetDimensions(description)
            fields["format_width"] = Int(dimensions.width)
            fields["format_height"] = Int(dimensions.height)
            fields["format_media_subtype"] = fourCC(
                CMFormatDescriptionGetMediaSubType(description)
            )
        }
        if let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) {
            fields["pixel_format"] = fourCC(CVPixelBufferGetPixelFormatType(buffer))
        }
        return fields
    }

    private func appendTime(
        _ value: CMTime,
        prefix: String,
        into fields: inout [String: Any]
    ) {
        fields["\(prefix)_valid"] = value.isValid
        fields["\(prefix)_numeric"] = value.isNumeric
        fields["\(prefix)_value"] = value.value
        fields["\(prefix)_timescale"] = value.timescale
        fields["\(prefix)_seconds"] = value.isNumeric ? CMTimeGetSeconds(value) : NSNull()
    }

    private func attachmentDescription(
        _ sampleBuffer: CMSampleBuffer,
        key: CFString
    ) -> Any {
        guard let value = CMGetAttachment(
            sampleBuffer,
            key: key,
            attachmentModeOut: nil
        ) else {
            return NSNull()
        }
        return String(describing: value)
    }
}

private final class NotificationLedger {
    private let sink: EventSink
    private var tokens: [NSObjectProtocol] = []

    init(sink: EventSink, session: AVCaptureSession) {
        self.sink = sink
        let center = NotificationCenter.default
        tokens.append(
            center.addObserver(
                forName: AVCaptureSession.runtimeErrorNotification,
                object: session,
                queue: nil
            ) { [weak self] notification in
                let error = notification.userInfo?[AVCaptureSessionErrorKey]
                self?.sink.emit(
                    "session_runtime_error",
                    fields: ["error": String(describing: error ?? NSNull())]
                )
            }
        )
        tokens.append(
            center.addObserver(
                forName: AVCaptureSession.wasInterruptedNotification,
                object: session,
                queue: nil
            ) { [weak self] notification in
                self?.sink.emit(
                    "session_interrupted",
                    fields: ["user_info": String(describing: notification.userInfo ?? [:])]
                )
            }
        )
        tokens.append(
            center.addObserver(
                forName: AVCaptureSession.interruptionEndedNotification,
                object: session,
                queue: nil
            ) { [weak self] _ in
                self?.sink.emit("session_interruption_ended")
            }
        )
        tokens.append(
            center.addObserver(
                forName: AVCaptureDevice.wasConnectedNotification,
                object: nil,
                queue: nil
            ) { [weak self] notification in
                self?.emitDevice("device_connected", notification: notification)
            }
        )
        tokens.append(
            center.addObserver(
                forName: AVCaptureDevice.wasDisconnectedNotification,
                object: nil,
                queue: nil
            ) { [weak self] notification in
                self?.emitDevice("device_disconnected", notification: notification)
            }
        )
    }

    deinit {
        let center = NotificationCenter.default
        for token in tokens {
            center.removeObserver(token)
        }
    }

    private func emitDevice(_ eventType: String, notification: Notification) {
        guard let device = notification.object as? AVCaptureDevice else {
            sink.emit(eventType, fields: ["device_unavailable": true])
            return
        }
        sink.emit(
            eventType,
            fields: [
                "device_name": device.localizedName,
                "device_unique_id": device.uniqueID,
                "device_connected": device.isConnected,
            ]
        )
    }
}

private func selectFormat(
    device: AVCaptureDevice,
    width: Int32,
    height: Int32,
    fps: Int32
) -> AVCaptureDevice.Format? {
    let candidates = device.formats.filter { format in
        let dimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
        guard dimensions.width == width, dimensions.height == height else {
            return false
        }
        return format.videoSupportedFrameRateRanges.contains { range in
            range.minFrameRate <= Double(fps) && range.maxFrameRate >= Double(fps)
        }
    }
    let preferred = candidates.first { format in
        let subtype = CMFormatDescriptionGetMediaSubType(format.formatDescription)
        return subtype == kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
    }
    return preferred ?? candidates.first
}

private func runProbe(options: ProbeOptions) throws {
    let sink = try EventSink(path: options.outputPath)
    sink.emit(
        "probe_started",
        fields: [
            "camera_name_requested": options.cameraName,
            "width_requested": Int(options.width),
            "height_requested": Int(options.height),
            "fps_requested": Int(options.fps),
            "duration_seconds_requested": options.durationSeconds,
            "drop_late_frames": true,
            "diagnostic_only": true,
            "metric_depth": false,
        ]
    )

    let authorization = AVCaptureDevice.authorizationStatus(for: .video)
    sink.emit(
        "authorization_observed",
        fields: ["authorization_status": authorization.rawValue]
    )
    guard authorization == .authorized else {
        throw ProbeFailure.runtime(
            "Camera authorization is not already granted; status=\(authorization.rawValue)."
        )
    }

    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external, .builtInWideAngleCamera],
        mediaType: .video,
        position: .unspecified
    )
    let matches = discovery.devices.filter { $0.localizedName == options.cameraName }
    sink.emit(
        "device_discovery_observed",
        fields: [
            "exact_match_count": matches.count,
            "detected_device_names": discovery.devices.map(\.localizedName).sorted(),
        ]
    )
    guard matches.count == 1, let device = matches.first else {
        throw ProbeFailure.deviceCount(matches.count)
    }
    guard let format = selectFormat(
        device: device,
        width: options.width,
        height: options.height,
        fps: options.fps
    ) else {
        throw ProbeFailure.formatUnavailable
    }

    try device.lockForConfiguration()
    device.activeFormat = format
    let frameDuration = CMTime(value: 1, timescale: options.fps)
    device.activeVideoMinFrameDuration = frameDuration
    device.activeVideoMaxFrameDuration = frameDuration
    device.unlockForConfiguration()

    let selectedDimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
    let selectedSubtype = CMFormatDescriptionGetMediaSubType(format.formatDescription)
    sink.emit(
        "format_selected",
        fields: [
            "device_name": device.localizedName,
            "device_unique_id": device.uniqueID,
            "format_width": Int(selectedDimensions.width),
            "format_height": Int(selectedDimensions.height),
            "format_media_subtype": fourCC(selectedSubtype),
            "fps": Int(options.fps),
        ]
    )

    let session = AVCaptureSession()
    session.beginConfiguration()
    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else {
        throw ProbeFailure.inputUnavailable
    }
    session.addInput(input)

    let output = AVCaptureVideoDataOutput()
    output.alwaysDiscardsLateVideoFrames = true
    output.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String:
            Int(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)
    ]
    guard session.canAddOutput(output) else {
        throw ProbeFailure.outputUnavailable
    }
    let callbackQueue = DispatchQueue(label: "sim2claw.avfoundation-source-probe")
    let delegate = SourceDelegate(sink: sink)
    output.setSampleBufferDelegate(delegate, queue: callbackQueue)
    session.addOutput(output)
    session.commitConfiguration()

    let notifications = NotificationLedger(sink: sink, session: session)
    _ = notifications
    sink.emit("session_start_requested")
    session.startRunning()
    sink.emit("session_start_returned", fields: ["session_running": session.isRunning])
    guard session.isRunning else {
        throw ProbeFailure.runtime("AVCaptureSession did not enter running state.")
    }

    let deadline = Date().addingTimeInterval(options.durationSeconds)
    RunLoop.current.run(until: deadline)

    sink.emit("session_stop_requested", fields: ["session_running": session.isRunning])
    session.stopRunning()
    sink.emit("session_stop_returned", fields: ["session_running": session.isRunning])
    callbackQueue.sync {}

    let counts = delegate.counts()
    if counts.output == 0 {
        throw ProbeFailure.noSamples
    }
    sink.emit(
        "probe_finished",
        fields: [
            "sample_output_count": counts.output,
            "sample_dropped_count": counts.dropped,
            "write_failure": sink.writeFailure ?? NSNull(),
            "diagnostic_only": true,
        ]
    )
    if let writeFailure = sink.writeFailure {
        throw ProbeFailure.outputWrite(writeFailure)
    }
}

do {
    let options = try ProbeOptions.parse(CommandLine.arguments)
    try runProbe(options: options)
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationSourceProbe: \(error)\n".utf8)
    )
    exit(2)
}
