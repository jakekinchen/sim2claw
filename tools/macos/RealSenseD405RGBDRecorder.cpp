// New native RGBD evidence path. The frozen OR44 depth recorder is unchanged.
// SDK source: librealsense2 rs_pipeline.hpp / rs_frame.hpp (see acquisition doc).
#include <librealsense2/rs.hpp>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using Clock = std::chrono::steady_clock;

namespace {
constexpr int WIDTH = 848, HEIGHT = 480, FPS = 30;
struct Options {
  bool help = false, capture = false;
  std::string serial, experiment;
  fs::path output;
  int frames = 800;
};

std::string quoted(const std::string &value) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(c);
    else out << c;
  }
  return out.str() + '"';
}

bool identifier(const std::string &value) {
  if (value.empty() || value.size() > 100) return false;
  return value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.") == std::string::npos;
}

Options parse(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    std::string key = argv[i];
    if (key == "--help" || key == "-h") { o.help = true; continue; }
    if (key == "--capture") { o.capture = true; continue; }
    if (i + 1 == argc) throw std::runtime_error("missing option value");
    std::string value = argv[++i];
    if (key == "--output-dir") o.output = value;
    else if (key == "--serial") o.serial = value;
    else if (key == "--experiment-id") o.experiment = value;
    else if (key == "--frames") {
      std::size_t n;
      o.frames = std::stoi(value, &n);
      if (n != value.size()) throw std::runtime_error("invalid frame count");
    } else throw std::runtime_error("unknown option: " + key);
  }
  if (o.help) return o;
  if (!o.capture) throw std::runtime_error("capture is disabled; --capture requires separate current camera authority");
  if (!identifier(o.experiment) || !identifier(o.serial) || o.output.empty())
    throw std::runtime_error("explicit experiment-id, serial and new output-dir are required");
  if (o.frames < 1 || o.frames > 900) throw std::runtime_error("frames must be between 1 and 900");
  if (fs::exists(o.output)) throw std::runtime_error("output directory already exists; preserve prior evidence");
  return o;
}

std::int64_t now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}

std::string optional_metadata(const rs2::frame &f, rs2_frame_metadata_value key) {
  return f.supports_frame_metadata(key) ? std::to_string(f.get_frame_metadata(key)) : "null";
}

void intrinsics(std::ostream &out, const rs2_intrinsics &i) {
  if (!(std::isfinite(i.fx) && std::isfinite(i.fy) && i.fx > 0 && i.fy > 0))
    throw std::runtime_error("invalid focal lengths");
  out << "{\"width\":" << i.width << ",\"height\":" << i.height
      << ",\"fx\":" << i.fx << ",\"fy\":" << i.fy
      << ",\"ppx\":" << i.ppx << ",\"ppy\":" << i.ppy
      << ",\"distortion_model\":" << int(i.model) << ",\"coeffs\":[";
  for (int j = 0; j < 5; ++j) out << (j ? "," : "") << i.coeffs[j];
  out << "]}";
}

void frame(std::ostream &out, const rs2::video_frame &f, std::uint64_t offset) {
  out << "{\"frame_number\":" << f.get_frame_number()
      << ",\"device_timestamp_ms\":" << f.get_timestamp()
      << ",\"timestamp_domain\":" << quoted(rs2_timestamp_domain_to_string(f.get_frame_timestamp_domain()))
      << ",\"width\":" << f.get_width() << ",\"height\":" << f.get_height()
      << ",\"stride_bytes\":" << f.get_stride_in_bytes()
      << ",\"bits_per_pixel\":" << f.get_bits_per_pixel()
      << ",\"offset_bytes\":" << offset
      << ",\"bytes\":" << std::uint64_t(f.get_stride_in_bytes()) * f.get_height()
      << ",\"frame_counter\":" << optional_metadata(f, RS2_FRAME_METADATA_FRAME_COUNTER)
      << ",\"actual_exposure_us\":" << optional_metadata(f, RS2_FRAME_METADATA_ACTUAL_EXPOSURE)
      << ",\"gain_level\":" << optional_metadata(f, RS2_FRAME_METADATA_GAIN_LEVEL)
      << ",\"actual_fps_x1000\":" << optional_metadata(f, RS2_FRAME_METADATA_ACTUAL_FPS) << "}";
}

void verify_profile(const rs2::video_stream_profile &p, rs2_format format) {
  if (p.width() != WIDTH || p.height() != HEIGHT || p.fps() != FPS || p.format() != format)
    throw std::runtime_error("negotiated stream profile differs from exact requested profile");
}
} // namespace

int main(int argc, char **argv) {
  try {
    const Options o = parse(argc, argv);
    if (o.help) {
      std::cout << "RealSenseD405RGBDRecorder (preparation only until separately admitted)\n"
        "--help returns before device enumeration or camera access.\n"
        "Capture options: --capture --serial ID --experiment-id NEW_ID --output-dir NEW_PATH [--frames 1..900]\n"
        "Exact streams: 848x480 at 30 Hz, raw Z16 depth and RGB8 color.\n"
        "Outputs: depth.z16, color.rgb8, frames.jsonl, manifest.json.\n"
        "SDK frameset association is recorded; exposure synchronization is not assumed.\n"
        "No serial, torque, robot motion, fitting, or retries. Partial captures remain without a completion manifest.\n";
      return 0;
    }
    // All option and destination checks precede SDK context creation.
    // Invocation here requires separately reviewed, current camera authority.
    if (!o.output.parent_path().empty()) fs::create_directories(o.output.parent_path());
    if (!fs::create_directory(o.output)) throw std::runtime_error("output directory collision");
    rs2::context context;
    bool found = false;
    for (auto device : context.query_devices()) {
      if (device.supports(RS2_CAMERA_INFO_SERIAL_NUMBER) && device.supports(RS2_CAMERA_INFO_NAME)
          && o.serial == device.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER)
          && std::string(device.get_info(RS2_CAMERA_INFO_NAME)).find("D405") != std::string::npos) found = true;
    }
    if (!found) throw std::runtime_error("explicit D405 serial not found");
    rs2::pipeline pipeline(context);
    rs2::config config;
    config.enable_device(o.serial);
    config.enable_stream(RS2_STREAM_DEPTH, WIDTH, HEIGHT, RS2_FORMAT_Z16, FPS);
    config.enable_stream(RS2_STREAM_COLOR, WIDTH, HEIGHT, RS2_FORMAT_RGB8, FPS);
    auto profile = pipeline.start(config);
    auto depth_profile = profile.get_stream(RS2_STREAM_DEPTH).as<rs2::video_stream_profile>();
    auto color_profile = profile.get_stream(RS2_STREAM_COLOR).as<rs2::video_stream_profile>();
    verify_profile(depth_profile, RS2_FORMAT_Z16);
    verify_profile(color_profile, RS2_FORMAT_RGB8);
    auto device = profile.get_device();
    const double scale = device.first<rs2::depth_sensor>().get_depth_scale();
    if (!std::isfinite(scale) || scale <= 0) throw std::runtime_error("invalid depth scale");
    auto transform = depth_profile.get_extrinsics_to(color_profile);
    std::ofstream depth(o.output / "depth.z16", std::ios::binary);
    std::ofstream color(o.output / "color.rgb8", std::ios::binary);
    std::ofstream rows(o.output / "frames.jsonl");
    depth.exceptions(std::ios::failbit | std::ios::badbit);
    color.exceptions(std::ios::failbit | std::ios::badbit);
    rows.exceptions(std::ios::failbit | std::ios::badbit);
    rows << std::setprecision(17);
    std::uint64_t depth_offset = 0, color_offset = 0;
    const auto started = Clock::now();
    for (int index = 0; index < o.frames; ++index) {
      if (Clock::now() - started > std::chrono::seconds(40)) throw std::runtime_error("capture deadline exceeded");
      rs2::frameset frames;
      if (!pipeline.try_wait_for_frames(&frames, 2000)) throw std::runtime_error("frame timeout; no retry");
      const auto arrival = now_ns();
      auto d = frames.get_depth_frame();
      auto c = frames.get_color_frame();
      if (!d || !c) throw std::runtime_error("incomplete RGBD frameset");
      const auto db = std::uint64_t(d.get_stride_in_bytes()) * d.get_height();
      const auto cb = std::uint64_t(c.get_stride_in_bytes()) * c.get_height();
      depth.write(static_cast<const char *>(d.get_data()), db);
      color.write(static_cast<const char *>(c.get_data()), cb);
      rows << "{\"schema_version\":\"sim2claw.d405_rgbd_frame.v1\",\"index\":" << index
           << ",\"host_arrival_steady_ns\":" << arrival << ",\"depth\":";
      frame(rows, d, depth_offset);
      rows << ",\"color\":";
      frame(rows, c, color_offset);
      rows << "}\n";
      depth_offset += db;
      color_offset += cb;
    }
    pipeline.stop();
    depth.close(); color.close(); rows.close();
    std::ofstream manifest(o.output / "manifest.partial.json");
    manifest.exceptions(std::ios::failbit | std::ios::badbit);
    manifest << std::setprecision(17)
      << "{\"schema_version\":\"sim2claw.d405_rgbd_capture.v1\",\"status\":\"complete\","
      << "\"proof_class\":\"unreviewed_native_rgbd_capture\",\"experiment_id\":" << quoted(o.experiment)
      << ",\"device_serial\":" << quoted(o.serial) << ",\"device_name\":\"Intel RealSense D405\","
      << "\"sdk_version\":" << quoted(RS2_API_VERSION_STR) << ",\"frame_count\":" << o.frames
      << ",\"width\":" << WIDTH << ",\"height\":" << HEIGHT << ",\"fps\":" << FPS
      << ",\"depth_format\":\"Z16\",\"color_format\":\"RGB8\",\"depth_scale_meters\":" << scale
      << ",\"pairing\":\"sdk_frameset\",\"exposure_synchronization_verified\":false,"
      << "\"host_clock\":\"std_chrono_steady_clock_nanoseconds\",\"depth_intrinsics\":";
    intrinsics(manifest, depth_profile.get_intrinsics());
    manifest << ",\"color_intrinsics\":";
    intrinsics(manifest, color_profile.get_intrinsics());
    manifest << ",\"depth_to_color\":{\"rotation_column_major\":[";
    for (int i = 0; i < 9; ++i) manifest << (i ? "," : "") << transform.rotation[i];
    manifest << "],\"translation_m\":[";
    for (int i = 0; i < 3; ++i) manifest << (i ? "," : "") << transform.translation[i];
    manifest << "]}}\n";
    manifest.close();
    fs::rename(o.output / "manifest.partial.json", o.output / "manifest.json");
    std::cout << "Capture saved for offline integrity review; no calibration or task authority.\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "error: " << error.what() << "\n";
    return 2;
  }
}
