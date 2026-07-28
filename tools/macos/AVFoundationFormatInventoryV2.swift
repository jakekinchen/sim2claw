import AVFoundation
import CoreMedia
import Foundation

private let schemaVersion = "sim2claw.avfoundation_format_inventory_observation.v2"

private enum InventoryError: Error, CustomStringConvertible {
    case invalidArguments(String)
    case invalidTime(String)
    case outputWrite(String)

    var description: String {
        switch self {
        case .invalidArguments(let message):
            return "invalid_arguments:\(message)"
        case .invalidTime(let message):
            return "invalid_time:\(message)"
        case .outputWrite(let message):
            return "output_write_failed:\(message)"
        }
    }
}

private struct Options {
    let cameraName: String
    let contractSHA256: String
    let outputPath: URL
}

private struct FrameRateRangeObservation: Codable {
    let rangeIndex: Int
    let minimumFPS: Double
    let maximumFPS: Double
    let minimumFrameDurationSeconds: Double
    let maximumFrameDurationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case rangeIndex = "range_index"
        case minimumFPS = "minimum_fps"
        case maximumFPS = "maximum_fps"
        case minimumFrameDurationSeconds = "minimum_frame_duration_seconds"
        case maximumFrameDurationSeconds = "maximum_frame_duration_seconds"
    }
}

private struct FormatObservation: Codable {
    let formatIndex: Int
    let width: Int
    let height: Int
    let mediaSubtypeFourCC: String
    let isVideoBinned: Bool?
    let videoFieldOfViewDegrees: Double?
    let videoMaxZoomFactor: Double?
    let supportedColorSpaceRawValues: [Int]
    let frameRateRanges: [FrameRateRangeObservation]

    enum CodingKeys: String, CodingKey {
        case formatIndex = "format_index"
        case width
        case height
        case mediaSubtypeFourCC = "media_subtype_fourcc"
        case isVideoBinned = "is_video_binned"
        case videoFieldOfViewDegrees = "video_field_of_view_degrees"
        case videoMaxZoomFactor = "video_max_zoom_factor"
        case supportedColorSpaceRawValues = "supported_color_space_raw_values"
        case frameRateRanges = "frame_rate_ranges"
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(formatIndex, forKey: .formatIndex)
        try container.encode(width, forKey: .width)
        try container.encode(height, forKey: .height)
        try container.encode(mediaSubtypeFourCC, forKey: .mediaSubtypeFourCC)
        if let isVideoBinned {
            try container.encode(isVideoBinned, forKey: .isVideoBinned)
        } else {
            try container.encodeNil(forKey: .isVideoBinned)
        }
        if let videoFieldOfViewDegrees {
            try container.encode(
                videoFieldOfViewDegrees,
                forKey: .videoFieldOfViewDegrees
            )
        } else {
            try container.encodeNil(forKey: .videoFieldOfViewDegrees)
        }
        if let videoMaxZoomFactor {
            try container.encode(
                videoMaxZoomFactor,
                forKey: .videoMaxZoomFactor
            )
        } else {
            try container.encodeNil(forKey: .videoMaxZoomFactor)
        }
        try container.encode(
            supportedColorSpaceRawValues,
            forKey: .supportedColorSpaceRawValues
        )
        try container.encode(frameRateRanges, forKey: .frameRateRanges)
    }
}

private struct InventoryObservation: Codable {
    let schemaVersion: String
    let contractSHA256: String
    let observerRole: String
    let captureSessionCreated: Bool
    let captureSessionStarted: Bool
    let sourceSampleCount: Int
    let authorizationStatusRawValue: Int
    let cameraNameRequested: String
    let deviceMatchCount: Int
    let detectedDeviceNames: [String]
    let status: String
    let failureReason: String?
    let deviceLocalizedName: String?
    let deviceUniqueID: String?
    let deviceModelID: String?
    let formats: [FormatObservation]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case contractSHA256 = "contract_sha256"
        case observerRole = "observer_role"
        case captureSessionCreated = "capture_session_created"
        case captureSessionStarted = "capture_session_started"
        case sourceSampleCount = "source_sample_count"
        case authorizationStatusRawValue = "authorization_status_raw_value"
        case cameraNameRequested = "camera_name_requested"
        case deviceMatchCount = "device_match_count"
        case detectedDeviceNames = "detected_device_names"
        case status
        case failureReason = "failure_reason"
        case deviceLocalizedName = "device_localized_name"
        case deviceUniqueID = "device_unique_id"
        case deviceModelID = "device_model_id"
        case formats
    }
}

private func parseOptions() throws -> Options {
    var cameraName: String?
    var contractSHA256: String?
    var outputPath: URL?
    var index = 1
    let arguments = CommandLine.arguments
    while index < arguments.count {
        let flag = arguments[index]
        guard index + 1 < arguments.count else {
            throw InventoryError.invalidArguments("missing_value_for_\(flag)")
        }
        let value = arguments[index + 1]
        switch flag {
        case "--camera-name":
            cameraName = value
        case "--contract-sha256":
            contractSHA256 = value
        case "--output":
            outputPath = URL(fileURLWithPath: value)
        default:
            throw InventoryError.invalidArguments("unknown_flag_\(flag)")
        }
        index += 2
    }
    guard let cameraName, !cameraName.isEmpty else {
        throw InventoryError.invalidArguments("camera_name_required")
    }
    guard let contractSHA256,
          contractSHA256.range(
            of: "^[0-9a-f]{64}$",
            options: .regularExpression
          ) != nil
    else {
        throw InventoryError.invalidArguments("contract_sha256_required")
    }
    guard let outputPath else {
        throw InventoryError.invalidArguments("output_required")
    }
    return Options(
        cameraName: cameraName,
        contractSHA256: contractSHA256,
        outputPath: outputPath
    )
}

private func fourCC(_ value: FourCharCode) -> String {
    let bytes: [UInt8] = [
        UInt8((value >> 24) & 0xff),
        UInt8((value >> 16) & 0xff),
        UInt8((value >> 8) & 0xff),
        UInt8(value & 0xff),
    ]
    if bytes.allSatisfy({ $0 >= 0x20 && $0 <= 0x7e }) {
        return String(bytes: bytes, encoding: .ascii)
            ?? String(format: "0x%08x", value)
    }
    return String(format: "0x%08x", value)
}

private func finiteSeconds(_ time: CMTime, label: String) throws -> Double {
    let seconds = CMTimeGetSeconds(time)
    guard seconds.isFinite else {
        throw InventoryError.invalidTime(label)
    }
    return seconds
}

private func formatObservation(
    _ format: AVCaptureDevice.Format,
    formatIndex: Int
) throws -> FormatObservation {
    let description = format.formatDescription
    let dimensions = CMVideoFormatDescriptionGetDimensions(description)
    let ranges = try format.videoSupportedFrameRateRanges.enumerated().map {
        rangeIndex, range in
        FrameRateRangeObservation(
            rangeIndex: rangeIndex,
            minimumFPS: Double(range.minFrameRate),
            maximumFPS: Double(range.maxFrameRate),
            minimumFrameDurationSeconds: try finiteSeconds(
                range.minFrameDuration,
                label: "minimum_frame_duration"
            ),
            maximumFrameDurationSeconds: try finiteSeconds(
                range.maxFrameDuration,
                label: "maximum_frame_duration"
            )
        )
    }
    return FormatObservation(
        formatIndex: formatIndex,
        width: Int(dimensions.width),
        height: Int(dimensions.height),
        mediaSubtypeFourCC: fourCC(
            CMFormatDescriptionGetMediaSubType(description)
        ),
        isVideoBinned: nil,
        videoFieldOfViewDegrees: nil,
        videoMaxZoomFactor: nil,
        supportedColorSpaceRawValues: format.supportedColorSpaces
            .map { Int($0.rawValue) }
            .sorted(),
        frameRateRanges: ranges
    )
}

private func writeObservation(
    _ observation: InventoryObservation,
    to path: URL
) throws {
    do {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        var data = try encoder.encode(observation)
        data.append(0x0a)
        try FileManager.default.createDirectory(
            at: path.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: path, options: .atomic)
    } catch {
        throw InventoryError.outputWrite(String(describing: error))
    }
}

private func runInventory(options: Options) throws -> Int32 {
    let authorizationStatus = AVCaptureDevice.authorizationStatus(for: .video)
    let discovery = AVCaptureDevice.DiscoverySession(
        deviceTypes: [.external, .builtInWideAngleCamera],
        mediaType: .video,
        position: .unspecified
    )
    let devices = discovery.devices
    let matches = devices.filter { $0.localizedName == options.cameraName }
    let common = (
        authorizationStatusRawValue: Int(authorizationStatus.rawValue),
        detectedDeviceNames: devices.map(\.localizedName).sorted()
    )
    guard authorizationStatus == .authorized else {
        try writeObservation(
            InventoryObservation(
                schemaVersion: schemaVersion,
                contractSHA256: options.contractSHA256,
                observerRole: "device_format_enumeration_only",
                captureSessionCreated: false,
                captureSessionStarted: false,
                sourceSampleCount: 0,
                authorizationStatusRawValue: common.authorizationStatusRawValue,
                cameraNameRequested: options.cameraName,
                deviceMatchCount: matches.count,
                detectedDeviceNames: common.detectedDeviceNames,
                status: "prerequisite_unavailable",
                failureReason: "camera_authorization_not_granted",
                deviceLocalizedName: nil,
                deviceUniqueID: nil,
                deviceModelID: nil,
                formats: []
            ),
            to: options.outputPath
        )
        return 2
    }
    guard matches.count == 1, let device = matches.first else {
        try writeObservation(
            InventoryObservation(
                schemaVersion: schemaVersion,
                contractSHA256: options.contractSHA256,
                observerRole: "device_format_enumeration_only",
                captureSessionCreated: false,
                captureSessionStarted: false,
                sourceSampleCount: 0,
                authorizationStatusRawValue: common.authorizationStatusRawValue,
                cameraNameRequested: options.cameraName,
                deviceMatchCount: matches.count,
                detectedDeviceNames: common.detectedDeviceNames,
                status: "prerequisite_unavailable",
                failureReason: "exact_device_match_count_invalid",
                deviceLocalizedName: nil,
                deviceUniqueID: nil,
                deviceModelID: nil,
                formats: []
            ),
            to: options.outputPath
        )
        return 2
    }
    let formats = try device.formats.enumerated().map {
        try formatObservation($0.element, formatIndex: $0.offset)
    }
    try writeObservation(
        InventoryObservation(
            schemaVersion: schemaVersion,
            contractSHA256: options.contractSHA256,
            observerRole: "device_format_enumeration_only",
            captureSessionCreated: false,
            captureSessionStarted: false,
            sourceSampleCount: 0,
            authorizationStatusRawValue: common.authorizationStatusRawValue,
            cameraNameRequested: options.cameraName,
            deviceMatchCount: matches.count,
            detectedDeviceNames: common.detectedDeviceNames,
            status: "observed",
            failureReason: nil,
            deviceLocalizedName: device.localizedName,
            deviceUniqueID: device.uniqueID,
            deviceModelID: device.modelID,
            formats: formats
        ),
        to: options.outputPath
    )
    return 0
}

do {
    let options = try parseOptions()
    exit(try runInventory(options: options))
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationFormatInventoryV2: \(error)\n".utf8)
    )
    exit(2)
}
