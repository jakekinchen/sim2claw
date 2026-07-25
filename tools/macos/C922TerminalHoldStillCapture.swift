#!/usr/bin/env swift

import Foundation
@preconcurrency import AVFoundation
import CoreImage
import CoreMedia
import CoreVideo
import CryptoKit
import Darwin
import ImageIO
import UniformTypeIdentifiers

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
    let maximumFrames: Int
    let sessionToken: String
    let mountToken: String
    let outputDirectory: URL
    let stopPath: URL

    static func parse() throws -> Options {
        var values: [String: String] = [:]
        var index = 1
        while index < CommandLine.arguments.count {
            guard index + 1 < CommandLine.arguments.count else {
                throw NSError(domain: "arguments", code: 1)
            }
            values[CommandLine.arguments[index]] = CommandLine.arguments[index + 1]
            index += 2
        }
        guard
            let name = values["--camera-name"],
            let uniqueID = values["--camera-unique-id"],
            let modelID = values["--camera-model-id"],
            let formatText = values["--format-index"], let format = Int(formatText),
            let rangeText = values["--range-index"], let range = Int(rangeText),
            let widthText = values["--width"], let width = Int32(widthText),
            let heightText = values["--height"], let height = Int32(heightText),
            let subtype = values["--subtype"], subtype == "420v",
            let fpsText = values["--supported-fps"], let fps = Double(fpsText),
            let maximumText = values["--maximum-frames"], let maximum = Int(maximumText),
            let session = values["--session-token"], !session.isEmpty,
            let mount = values["--mount-token"], !mount.isEmpty,
            let output = values["--output-directory"],
            let stop = values["--stop-path"],
            format >= 0, range >= 0, width == 640, height == 480,
            fps.isFinite, fps > 0, maximum > 0
        else {
            throw NSError(domain: "arguments", code: 2)
        }
        return Options(
            cameraName: name, cameraUniqueID: uniqueID, cameraModelID: modelID,
            formatIndex: format, rangeIndex: range, width: width, height: height,
            subtype: subtype, supportedFPS: fps, maximumFrames: maximum,
            sessionToken: session, mountToken: mount,
            outputDirectory: URL(fileURLWithPath: output),
            stopPath: URL(fileURLWithPath: stop)
        )
    }
}

private func fourCC(_ value: FourCharCode) -> String {
    let bytes = [
        UInt8((value >> 24) & 0xff), UInt8((value >> 16) & 0xff),
        UInt8((value >> 8) & 0xff), UInt8(value & 0xff),
    ]
    return String(bytes: bytes, encoding: .ascii) ?? String(format: "0x%08x", value)
}

private func hostContinuousNS() -> UInt64 {
    var info = mach_timebase_info_data_t()
    mach_timebase_info(&info)
    return UInt64(
        Double(mach_continuous_time()) * Double(info.numer) / Double(info.denom)
    )
}

private func sha256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func atomicJSON<T: Encodable>(_ value: T, to path: URL) throws {
    let data = try JSONEncoder().encode(value)
    try data.write(to: path, options: .atomic)
}

private struct Ready: Encodable {
    let schemaVersion = "sim2claw.c922_terminal_hold_capture_ready.v1"
    let cameraName: String
    let cameraUniqueID: String
    let cameraModelID: String
    let width: Int
    let height: Int
    let mediaSubtype: String
    let pixelFormat: String
    let supportedFPS: Double
    let cameraSessionToken: String
    let fixedMountToken: String
    let firstFrameHostContinuousNS: UInt64
}

private struct FrameEvent: Encodable {
    let schemaVersion = "sim2claw.c922_terminal_hold_frame_event.v1"
    let sequence: Int
    let hostContinuousNS: UInt64
    let ptsSeconds: Double
    let durationSeconds: Double
    let width: Int
    let height: Int
    let mediaSubtype: String
    let pixelFormat: String
    let cameraName: String
    let cameraUniqueID: String
    let cameraModelID: String
    let pngPath: String
    let pngSHA256: String
    let cameraSessionToken: String
    let fixedMountToken: String
}

private struct FinalReport: Encodable {
    let schemaVersion = "sim2claw.c922_terminal_hold_capture_final.v1"
    let status: String
    let outputCallbackCount: Int
    let droppedCallbackCount: Int
    let retainedFrameCount: Int
    let cameraSessionToken: String
    let fixedMountToken: String
}

private final class Delegate: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let options: Options
    private let context = CIContext(options: [.cacheIntermediates: false])
    private var sequence = 0
    private var dropped = 0
    private var ring: [Int: FrameEvent] = [:]

    init(options: Options) {
        self.options = options
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        let callbackHostNS = hostContinuousNS()
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        let pixelFormat = fourCC(CVPixelBufferGetPixelFormatType(pixelBuffer))
        guard width == 640, height == 480, pixelFormat == "420v" else { return }
        let eventSequence = sequence
        sequence += 1
        let slot = eventSequence % options.maximumFrames
        let relative = String(format: "frames/frame-%03d.png", slot)
        let destination = options.outputDirectory.appendingPathComponent(relative)
        let image = CIImage(cvPixelBuffer: pixelBuffer)
        guard let cgImage = context.createCGImage(image, from: image.extent) else { return }
        let data = NSMutableData()
        guard
            let writer = CGImageDestinationCreateWithData(
                data, UTType.png.identifier as CFString, 1, nil
            )
        else { return }
        CGImageDestinationAddImage(writer, cgImage, nil)
        guard CGImageDestinationFinalize(writer) else { return }
        let immutable = data as Data
        do {
            try immutable.write(to: destination, options: .atomic)
            let pts = CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sampleBuffer))
            let duration = CMTimeGetSeconds(CMSampleBufferGetDuration(sampleBuffer))
            let event = FrameEvent(
                sequence: eventSequence,
                hostContinuousNS: callbackHostNS,
                ptsSeconds: pts.isFinite ? pts : -1,
                durationSeconds: duration.isFinite ? duration : -1,
                width: width, height: height, mediaSubtype: "420v",
                pixelFormat: pixelFormat,
                cameraName: options.cameraName,
                cameraUniqueID: options.cameraUniqueID,
                cameraModelID: options.cameraModelID,
                pngPath: relative,
                pngSHA256: sha256(immutable),
                cameraSessionToken: options.sessionToken,
                fixedMountToken: options.mountToken
            )
            ring[slot] = event
            if eventSequence == 0 {
                try atomicJSON(
                    Ready(
                        cameraName: options.cameraName,
                        cameraUniqueID: options.cameraUniqueID,
                        cameraModelID: options.cameraModelID,
                        width: width, height: height, mediaSubtype: "420v",
                        pixelFormat: pixelFormat, supportedFPS: options.supportedFPS,
                        cameraSessionToken: options.sessionToken,
                        fixedMountToken: options.mountToken,
                        firstFrameHostContinuousNS: event.hostContinuousNS
                    ),
                    to: options.outputDirectory.appendingPathComponent("ready.json")
                )
            }
        } catch {
            fputs("frame_write_failed: \(error)\\n", stderr)
        }
    }

    func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        dropped += 1
    }

    func finish() throws {
        let ordered = ring.values.sorted { $0.sequence < $1.sequence }
        let encoder = JSONEncoder()
        let ledger = try ordered.map {
            String(data: try encoder.encode($0), encoding: .utf8)!
        }.joined(separator: "\n") + "\n"
        try ledger.write(
            to: options.outputDirectory.appendingPathComponent("frames.jsonl"),
            atomically: true, encoding: .utf8
        )
        try atomicJSON(
            FinalReport(
                status: "completed", outputCallbackCount: sequence,
                droppedCallbackCount: dropped, retainedFrameCount: ordered.count,
                cameraSessionToken: options.sessionToken,
                fixedMountToken: options.mountToken
            ),
            to: options.outputDirectory.appendingPathComponent("final.json")
        )
    }
}

do {
    let options = try Options.parse()
    try FileManager.default.createDirectory(
        at: options.outputDirectory.appendingPathComponent("frames"),
        withIntermediateDirectories: true
    )
    let authorization = AVCaptureDevice.authorizationStatus(for: .video)
    guard authorization == .authorized else {
        throw NSError(domain: "camera_authorization", code: Int(authorization.rawValue))
    }
    let devices = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external], mediaType: .video, position: .unspecified
    ).devices.filter {
        $0.localizedName == options.cameraName
            && $0.uniqueID == options.cameraUniqueID
            && $0.modelID == options.cameraModelID
    }
    guard devices.count == 1 else { throw NSError(domain: "camera_identity", code: devices.count) }
    let device = devices[0]
    guard options.formatIndex < device.formats.count else {
        throw NSError(domain: "format_index", code: options.formatIndex)
    }
    let format = device.formats[options.formatIndex]
    guard options.rangeIndex < format.videoSupportedFrameRateRanges.count else {
        throw NSError(domain: "range_index", code: options.rangeIndex)
    }
    let dimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
    let subtype = fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription))
    let range = format.videoSupportedFrameRateRanges[options.rangeIndex]
    guard dimensions.width == options.width, dimensions.height == options.height,
          subtype == options.subtype,
          abs(range.maxFrameRate - options.supportedFPS) < 0.001 else {
        throw NSError(domain: "format_identity", code: 1)
    }

    let session = AVCaptureSession()
    let input = try AVCaptureDeviceInput(device: device)
    let output = AVCaptureVideoDataOutput()
    output.alwaysDiscardsLateVideoFrames = true
    output.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String:
            Int(kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange)
    ]
    session.beginConfiguration()
    guard session.canAddInput(input), session.canAddOutput(output) else {
        throw NSError(domain: "session_io", code: 1)
    }
    session.addInput(input)
    session.addOutput(output)
    try device.lockForConfiguration()
    device.activeFormat = format
    device.activeVideoMinFrameDuration = range.minFrameDuration
    device.activeVideoMaxFrameDuration = range.minFrameDuration
    session.commitConfiguration()
    let delegate = Delegate(options: options)
    let queue = DispatchQueue(label: "sim2claw.c922-terminal-hold")
    output.setSampleBufferDelegate(delegate, queue: queue)
    session.startRunning()
    device.unlockForConfiguration()
    while !FileManager.default.fileExists(atPath: options.stopPath.path) {
        Thread.sleep(forTimeInterval: 0.02)
    }
    session.stopRunning()
    output.setSampleBufferDelegate(nil, queue: nil)
    queue.sync {}
    try delegate.finish()
} catch {
    fputs("c922_terminal_hold_capture_failed: \(error)\\n", stderr)
    exit(2)
}
