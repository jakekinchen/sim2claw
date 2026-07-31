#include <librealsense2/rs.hpp>

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>

namespace {

struct Options {
  bool help = false;
  std::filesystem::path output_prefix;
  std::string serial;
  int frames = 120;
  int width = 424;
  int height = 240;
  int fps = 30;
};

void print_help() {
  std::cout
      << "RealSenseD405MetricRecorder\n"
      << "Usage: RealSenseD405MetricRecorder --output-prefix PATH "
         "[--serial SERIAL] [--frames N] [--width N] [--height N] [--fps N]\n"
      << "Outputs: PATH.z16, PATH.metadata.jsonl, PATH.manifest.json\n"
      << "Depth format: raw Z16 rows in frame order; metric depth is "
         "raw_value * depth_scale_meters.\n"
      << "Manifest fields: schema_version, device_name, device_serial, "
         "librealsense_api_version, width, height, fps, frame_count, "
         "depth_scale_meters, intrinsics, raw_frame_bytes.\n"
      << "Frame metadata fields: frame_index, frame_number, "
         "sensor_timestamp_ms, sensor_timestamp_domain, "
         "host_arrival_steady_ns, raw_offset_bytes, width, height, stride_bytes, "
         "bits_per_pixel, frame_counter, actual_exposure_us, gain_level, "
         "actual_fps_x1000.\n"
      << "Safety: --help returns before context creation, device enumeration, "
         "or stream opening.\n";
}

int parse_positive_int(const std::string &value, const std::string &name) {
  std::size_t consumed = 0;
  const int parsed = std::stoi(value, &consumed);
  if (consumed != value.size() || parsed <= 0) {
    throw std::runtime_error(name + " must be a positive integer");
  }
  return parsed;
}

Options parse_options(int argc, char **argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--help" || argument == "-h") {
      options.help = true;
      continue;
    }
    if (index + 1 >= argc) {
      throw std::runtime_error("missing value for " + argument);
    }
    const std::string value = argv[++index];
    if (argument == "--output-prefix") {
      options.output_prefix = value;
    } else if (argument == "--serial") {
      options.serial = value;
    } else if (argument == "--frames") {
      options.frames = parse_positive_int(value, argument);
    } else if (argument == "--width") {
      options.width = parse_positive_int(value, argument);
    } else if (argument == "--height") {
      options.height = parse_positive_int(value, argument);
    } else if (argument == "--fps") {
      options.fps = parse_positive_int(value, argument);
    } else {
      throw std::runtime_error("unknown option: " + argument);
    }
  }
  return options;
}

std::string json_escape(const std::string &value) {
  std::ostringstream escaped;
  for (const char character : value) {
    switch (character) {
    case '\\':
      escaped << "\\\\";
      break;
    case '"':
      escaped << "\\\"";
      break;
    case '\n':
      escaped << "\\n";
      break;
    case '\r':
      escaped << "\\r";
      break;
    case '\t':
      escaped << "\\t";
      break;
    default:
      escaped << character;
    }
  }
  return escaped.str();
}

std::string metadata_or_null(
    const rs2::frame &frame, rs2_frame_metadata_value key) {
  if (!frame.supports_frame_metadata(key)) {
    return "null";
  }
  return std::to_string(frame.get_frame_metadata(key));
}

std::string device_info_or_empty(
    const rs2::device &device, rs2_camera_info key) {
  return device.supports(key) ? device.get_info(key) : "";
}

std::filesystem::path with_suffix(
    const std::filesystem::path &prefix, const std::string &suffix) {
  return std::filesystem::path(prefix.string() + suffix);
}

} // namespace

int main(int argc, char **argv) {
  try {
    const Options options = parse_options(argc, argv);
    if (options.help) {
      print_help();
      return 0;
    }
    if (options.output_prefix.empty()) {
      throw std::runtime_error("--output-prefix is required");
    }

    // Hardware access begins only below this line. The --help path above is
    // intentionally usable for build verification under camera-open=false.
    rs2::context context;
    std::optional<std::string> selected_serial;
    for (const rs2::device &device : context.query_devices()) {
      const std::string name = device_info_or_empty(device, RS2_CAMERA_INFO_NAME);
      const std::string serial =
          device_info_or_empty(device, RS2_CAMERA_INFO_SERIAL_NUMBER);
      const bool is_d405 = name.find("D405") != std::string::npos;
      const bool serial_matches =
          options.serial.empty() || serial == options.serial;
      if (is_d405 && serial_matches) {
        selected_serial = serial;
        break;
      }
    }
    if (!selected_serial.has_value()) {
      throw std::runtime_error("no matching Intel RealSense D405 found");
    }

    rs2::pipeline pipeline(context);
    rs2::config configuration;
    configuration.enable_device(*selected_serial);
    configuration.enable_stream(
        RS2_STREAM_DEPTH, options.width, options.height, RS2_FORMAT_Z16,
        options.fps);
    const rs2::pipeline_profile profile = pipeline.start(configuration);
    const rs2::device device = profile.get_device();
    const std::string device_name =
        device_info_or_empty(device, RS2_CAMERA_INFO_NAME);
    if (device_name.find("D405") == std::string::npos) {
      pipeline.stop();
      throw std::runtime_error("opened device is not a D405");
    }
    const auto depth_sensor = device.first<rs2::depth_sensor>();
    const float depth_scale = depth_sensor.get_depth_scale();
    const auto stream_profile =
        profile.get_stream(RS2_STREAM_DEPTH).as<rs2::video_stream_profile>();
    const rs2_intrinsics intrinsics = stream_profile.get_intrinsics();

    const std::filesystem::path raw_path =
        with_suffix(options.output_prefix, ".z16");
    const std::filesystem::path metadata_path =
        with_suffix(options.output_prefix, ".metadata.jsonl");
    const std::filesystem::path manifest_path =
        with_suffix(options.output_prefix, ".manifest.json");
    if (!raw_path.parent_path().empty()) {
      std::filesystem::create_directories(raw_path.parent_path());
    }
    std::ofstream raw(raw_path, std::ios::binary | std::ios::trunc);
    std::ofstream metadata(metadata_path, std::ios::trunc);
    if (!raw || !metadata) {
      pipeline.stop();
      throw std::runtime_error("failed to open output files");
    }

    std::uint64_t raw_offset = 0;
    std::uint64_t raw_frame_bytes = 0;
    for (int frame_index = 0; frame_index < options.frames; ++frame_index) {
      const rs2::frameset frames = pipeline.wait_for_frames();
      const rs2::depth_frame depth = frames.get_depth_frame();
      if (!depth) {
        throw std::runtime_error("missing depth frame");
      }
      const auto host_arrival =
          std::chrono::steady_clock::now().time_since_epoch();
      const auto host_arrival_ns =
          std::chrono::duration_cast<std::chrono::nanoseconds>(host_arrival)
              .count();
      raw_frame_bytes = static_cast<std::uint64_t>(depth.get_stride_in_bytes()) *
                        static_cast<std::uint64_t>(depth.get_height());
      raw.write(
          static_cast<const char *>(depth.get_data()),
          static_cast<std::streamsize>(raw_frame_bytes));
      if (!raw) {
        throw std::runtime_error("failed to write raw depth frame");
      }

      metadata << std::setprecision(17)
               << "{\"schema_version\":\"sim2claw.d405_depth_frame.v1\","
               << "\"frame_index\":" << frame_index << ","
               << "\"frame_number\":" << depth.get_frame_number() << ","
               << "\"sensor_timestamp_ms\":" << depth.get_timestamp() << ","
               << "\"sensor_timestamp_domain\":\""
               << json_escape(rs2_timestamp_domain_to_string(
                      depth.get_frame_timestamp_domain()))
               << "\","
               << "\"host_arrival_steady_ns\":" << host_arrival_ns << ","
               << "\"raw_offset_bytes\":" << raw_offset << ","
               << "\"width\":" << depth.get_width() << ","
               << "\"height\":" << depth.get_height() << ","
               << "\"stride_bytes\":" << depth.get_stride_in_bytes() << ","
               << "\"bits_per_pixel\":" << depth.get_bits_per_pixel() << ","
               << "\"frame_counter\":"
               << metadata_or_null(depth, RS2_FRAME_METADATA_FRAME_COUNTER)
               << ",\"actual_exposure_us\":"
               << metadata_or_null(depth, RS2_FRAME_METADATA_ACTUAL_EXPOSURE)
               << ",\"gain_level\":"
               << metadata_or_null(depth, RS2_FRAME_METADATA_GAIN_LEVEL)
               << ",\"actual_fps_x1000\":"
               << metadata_or_null(depth, RS2_FRAME_METADATA_ACTUAL_FPS)
               << "}\n";
      raw_offset += raw_frame_bytes;
    }
    pipeline.stop();
    raw.close();
    metadata.close();

    std::ofstream manifest(manifest_path, std::ios::trunc);
    if (!manifest) {
      throw std::runtime_error("failed to open manifest output");
    }
    manifest
        << std::setprecision(17)
        << "{\n"
        << "  \"schema_version\": "
           "\"sim2claw.d405_metric_depth_capture_manifest.v1\",\n"
        << "  \"device_name\": \"" << json_escape(device_name) << "\",\n"
        << "  \"device_serial\": \"" << json_escape(*selected_serial)
        << "\",\n"
        << "  \"librealsense_api_version\": " << RS2_API_VERSION << ",\n"
        << "  \"width\": " << intrinsics.width << ",\n"
        << "  \"height\": " << intrinsics.height << ",\n"
        << "  \"fps\": " << options.fps << ",\n"
        << "  \"frame_count\": " << options.frames << ",\n"
        << "  \"depth_scale_meters\": " << depth_scale << ",\n"
        << "  \"raw_frame_bytes\": " << raw_frame_bytes << ",\n"
        << "  \"intrinsics\": {\n"
        << "    \"fx\": " << intrinsics.fx << ", \"fy\": " << intrinsics.fy
        << ", \"ppx\": " << intrinsics.ppx
        << ", \"ppy\": " << intrinsics.ppy << ",\n"
        << "    \"model\": " << static_cast<int>(intrinsics.model)
        << ", \"coeffs\": [" << intrinsics.coeffs[0] << ", "
        << intrinsics.coeffs[1] << ", " << intrinsics.coeffs[2] << ", "
        << intrinsics.coeffs[3] << ", " << intrinsics.coeffs[4] << "]\n"
        << "  }\n"
        << "}\n";
    return 0;
  } catch (const rs2::error &error) {
    std::cerr << "librealsense error: " << error.what() << "\n";
    return 2;
  } catch (const std::exception &error) {
    std::cerr << "error: " << error.what() << "\n";
    return 2;
  }
}
