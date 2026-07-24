import AVFoundation
import CoreMedia
import Foundation

private let schemaVersion = "sim2claw.avfoundation_format_inventory_observation.v1"

private enum InventoryError: Error, CustomStringConvertible {
    case invalidArguments(String)
    case outputWrite(String)

    var description: String {
        switch self {
        case .invalidArguments(let message):
            return "invalid_arguments:\(message)"
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
        return String(bytes: bytes, encoding: .ascii) ?? String(format: "0x%08x", value)
    }
    return String(format: "0x%08x", value)
}

private func finiteSeconds(_ time: CMTime) -> Any {
    let seconds = CMTimeGetSeconds(time)
    return seconds.isFinite ? seconds : NSNull()
}

private func writeJSON(_ payload: [String: Any], to path: URL) throws {
    do {
        var data = try JSONSerialization.data(
            withJSONObject: payload,
            options: [.prettyPrinted, .sortedKeys]
        )
        try FileManager.default.createDirectory(
            at: path.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        data.append(0x0a)
        try data.write(to: path, options: .atomic)
    } catch {
        throw InventoryError.outputWrite(String(describing: error))
    }
}

private func formatPayload(
    _ format: AVCaptureDevice.Format,
    formatIndex: Int
) -> [String: Any] {
    let description = format.formatDescription
    let dimensions = CMVideoFormatDescriptionGetDimensions(description)
    let ranges = format.videoSupportedFrameRateRanges.enumerated().map {
        rangeIndex, range in
        [
            "range_index": rangeIndex,
            "minimum_fps": range.minFrameRate,
            "maximum_fps": range.maxFrameRate,
            "minimum_frame_duration_seconds": finiteSeconds(range.minFrameDuration),
            "maximum_frame_duration_seconds": finiteSeconds(range.maxFrameDuration),
        ] as [String: Any]
    }
    return [
        "format_index": formatIndex,
        "width": Int(dimensions.width),
        "height": Int(dimensions.height),
        "media_subtype_fourcc": fourCC(
            CMFormatDescriptionGetMediaSubType(description)
        ),
        "is_video_binned": NSNull(),
        "video_field_of_view_degrees": format.videoFieldOfView,
        "video_max_zoom_factor": NSNull(),
        "supported_color_space_raw_values": format.supportedColorSpaces
            .map(\.rawValue)
            .sorted(),
        "frame_rate_ranges": ranges,
    ]
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
    var payload: [String: Any] = [
        "schema_version": schemaVersion,
        "contract_sha256": options.contractSHA256,
        "observer_role": "device_format_enumeration_only",
        "capture_session_created": false,
        "capture_session_started": false,
        "source_sample_count": 0,
        "authorization_status_raw_value": authorizationStatus.rawValue,
        "camera_name_requested": options.cameraName,
        "device_match_count": matches.count,
        "detected_device_names": devices.map(\.localizedName).sorted(),
        "formats": [],
    ]
    guard authorizationStatus == .authorized else {
        payload["status"] = "prerequisite_unavailable"
        payload["failure_reason"] = "camera_authorization_not_granted"
        try writeJSON(payload, to: options.outputPath)
        return 2
    }
    guard matches.count == 1, let device = matches.first else {
        payload["status"] = "prerequisite_unavailable"
        payload["failure_reason"] = "exact_device_match_count_invalid"
        try writeJSON(payload, to: options.outputPath)
        return 2
    }
    payload["status"] = "observed"
    payload["device_localized_name"] = device.localizedName
    payload["device_unique_id"] = device.uniqueID
    payload["device_model_id"] = device.modelID
    payload["formats"] = device.formats.enumerated().map {
        formatPayload($0.element, formatIndex: $0.offset)
    }
    try writeJSON(payload, to: options.outputPath)
    return 0
}

do {
    let options = try parseOptions()
    exit(try runInventory(options: options))
} catch {
    FileHandle.standardError.write(
        Data("AVFoundationFormatInventory: \(error)\n".utf8)
    )
    exit(2)
}
