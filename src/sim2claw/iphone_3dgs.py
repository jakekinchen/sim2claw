from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "sim2claw.iphone_video_3dgs_receipt.v1"
PROOF_CLASS = "monocular_video_relative_scale_3dgs"


class IPhone3DGSError(RuntimeError):
    """Raised when the fail-closed video-to-3DGS pathway cannot continue."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    parts = resolved.parts
    if "artifacts" not in parts or "private" not in parts:
        raise IPhone3DGSError(
            "3DGS runs must be written below an ignored artifacts/private directory"
        )
    return resolved


def _require_executable(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise IPhone3DGSError(f"{label} is not an executable file: {resolved}")
    return resolved


def _run(
    argv: Sequence[str],
    *,
    log_prefix: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise IPhone3DGSError(
            f"command exceeded {timeout_seconds}s: {argv[0]}"
        ) from error
    log_prefix.parent.mkdir(parents=True, exist_ok=True)
    log_prefix.with_suffix(".stdout.log").write_text(result.stdout, encoding="utf-8")
    log_prefix.with_suffix(".stderr.log").write_text(result.stderr, encoding="utf-8")
    receipt = {
        "argv": list(argv),
        "elapsed_seconds": time.monotonic() - started,
        "exit_code": result.returncode,
        "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
    }
    if result.returncode != 0:
        raise IPhone3DGSError(
            f"command failed with exit {result.returncode}: {argv[0]}; "
            f"see {log_prefix.with_suffix('.stderr.log')}"
        )
    return receipt


def probe_video(video: Path, ffprobe_binary: Path) -> dict[str, Any]:
    ffprobe = _require_executable(ffprobe_binary, "ffprobe")
    result = subprocess.run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,duration:format=duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise IPhone3DGSError(f"ffprobe failed: {result.stderr.strip()}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    if len(streams) != 1:
        raise IPhone3DGSError("source must contain one readable primary video stream")
    duration = float(streams[0].get("duration") or payload.get("format", {}).get("duration"))
    if not math.isfinite(duration) or duration <= 0:
        raise IPhone3DGSError("source video duration is invalid")
    return {"duration_seconds": duration, **streams[0]}


def deterministic_split(
    frame_names: Sequence[str], *, holdout_fraction: float, seed: str
) -> tuple[list[str], list[str]]:
    names = list(frame_names)
    if len(names) < 8 or len(names) != len(set(names)):
        raise IPhone3DGSError("at least eight uniquely named frames are required")
    if not 0.05 <= holdout_fraction <= 0.4:
        raise IPhone3DGSError("holdout fraction must be between 0.05 and 0.4")
    count = max(2, min(len(names) - 4, round(len(names) * holdout_fraction)))
    ranked = sorted(
        names,
        key=lambda name: (hashlib.sha256(f"{seed}\0{name}".encode()).hexdigest(), name),
    )
    selected = set(ranked[:count])
    return [name for name in names if name not in selected], [
        name for name in names if name in selected
    ]


def inspect_gaussian_ply(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        header = handle.read(min(size, 128 * 1024))
    marker = b"end_header\n"
    end = header.find(marker)
    if end < 0:
        raise IPhone3DGSError("Gaussian PLY header is missing end_header")
    text = header[: end + len(marker)].decode("ascii", errors="strict")
    lines = text.splitlines()
    if not lines or lines[0] != "ply" or "format binary_little_endian 1.0" not in lines:
        raise IPhone3DGSError("only binary little-endian Gaussian PLY is accepted")
    vertex_rows = [line for line in lines if line.startswith("element vertex ")]
    if len(vertex_rows) != 1:
        raise IPhone3DGSError("Gaussian PLY must declare one vertex element")
    splats = int(vertex_rows[0].split()[-1])
    properties = [line.removeprefix("property ") for line in lines if line.startswith("property ")]
    required = {"float x", "float y", "float z", "float opacity", "float scale_0", "float rot_0"}
    if not required <= set(properties):
        raise IPhone3DGSError("PLY does not contain the required Gaussian fields")
    if splats <= 0 or size <= end + len(marker):
        raise IPhone3DGSError("Gaussian PLY has no binary splat payload")
    sh_degree = 0
    rest = sum(name.startswith("float f_rest_") for name in properties)
    if rest >= 45:
        sh_degree = 3
    elif rest >= 24:
        sh_degree = 2
    elif rest >= 9:
        sh_degree = 1
    return {
        "bytes": size,
        "sha256": sha256_file(path),
        "splat_count": splats,
        "property_count": len(properties),
        "inferred_sh_degree": sh_degree,
        "format": "binary_little_endian_1.0",
    }


@dataclass(frozen=True)
class PipelineConfig:
    video: Path
    output: Path
    ffmpeg_binary: Path
    ffprobe_binary: Path
    colmap_binary: Path
    brush_binary: Path
    keyframes: int = 80
    holdout_fraction: float = 0.125
    max_resolution: int = 1920
    training_steps: int = 30_000
    max_splats: int = 2_000_000
    seed: int = 42


def _extract_frames(config: PipelineConfig, duration: float) -> dict[str, Any]:
    frame_root = config.output / "frames"
    frame_root.mkdir(parents=True, exist_ok=False)
    fps = config.keyframes / duration
    return _run(
        [
            str(config.ffmpeg_binary),
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(config.video),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps={fps:.12f},scale='min({config.max_resolution},iw)':-2:flags=lanczos",
            "-frames:v",
            str(config.keyframes),
            "-q:v",
            "2",
            "-map_metadata",
            "-1",
            str(frame_root / "frame-%06d.jpg"),
        ],
        log_prefix=config.output / "logs" / "01-extract",
        timeout_seconds=1800,
    )


def _stage_training_frames(config: PipelineConfig, training: Sequence[str]) -> Path:
    image_root = config.output / "colmap" / "images"
    image_root.mkdir(parents=True, exist_ok=False)
    for name in training:
        source = config.output / "frames" / name
        destination = image_root / name
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
    return image_root


def _run_colmap(config: PipelineConfig, image_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    root = config.output / "colmap"
    database = root / "database.db"
    sparse = root / "sparse"
    sparse.mkdir(parents=True, exist_ok=False)
    common = ["--log_to_stderr", "1"]
    receipts = [
        _run(
            [
                str(config.colmap_binary), "feature_extractor", *common,
                "--database_path", str(database), "--image_path", str(image_root),
                "--ImageReader.single_camera", "1", "--ImageReader.camera_model", "OPENCV",
                "--SiftExtraction.use_gpu", "0", "--SiftExtraction.max_num_features", "8192",
            ],
            log_prefix=config.output / "logs" / "02-colmap-features",
            timeout_seconds=3600,
        ),
        _run(
            [
                str(config.colmap_binary), "exhaustive_matcher", *common,
                "--database_path", str(database), "--SiftMatching.use_gpu", "0",
            ],
            log_prefix=config.output / "logs" / "03-colmap-matches",
            timeout_seconds=3600,
        ),
        _run(
            [
                str(config.colmap_binary), "mapper", *common,
                "--database_path", str(database), "--image_path", str(image_root),
                "--output_path", str(sparse), "--Mapper.ba_refine_principal_point", "0",
            ],
            log_prefix=config.output / "logs" / "04-colmap-map",
            timeout_seconds=3600,
        ),
    ]
    models = [path for path in sparse.iterdir() if path.is_dir()]
    if not models:
        raise IPhone3DGSError("COLMAP produced no sparse model")
    selected = max(models, key=lambda path: sum(item.stat().st_size for item in path.iterdir()))
    return selected, receipts


def _stage_brush_dataset(
    config: PipelineConfig, image_root: Path, sparse_model: Path
) -> Path:
    dataset = config.output / "brush-input"
    images = dataset / "images"
    sparse = dataset / "sparse" / "0"
    images.mkdir(parents=True)
    sparse.mkdir(parents=True)
    for source in sorted(image_root.iterdir()):
        if not source.is_file():
            continue
        destination = images / source.name
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
    for source in sorted(sparse_model.iterdir()):
        if source.is_file():
            shutil.copyfile(source, sparse / source.name)
    required = {"cameras.bin", "images.bin", "points3D.bin"}
    if not required <= {path.name for path in sparse.iterdir()}:
        raise IPhone3DGSError("selected COLMAP model is incomplete")
    return dataset


def run_iphone_3dgs(config: PipelineConfig) -> dict[str, Any]:
    video = config.video.expanduser().resolve(strict=True)
    if not video.is_file():
        raise IPhone3DGSError("source video is not a file")
    output = _require_private_output(config.output)
    if output.exists():
        raise IPhone3DGSError(f"output already exists: {output}")
    if not 16 <= config.keyframes <= 500:
        raise IPhone3DGSError("keyframes must be between 16 and 500")
    if not 100 <= config.training_steps <= 100_000:
        raise IPhone3DGSError("training steps must be between 100 and 100000")
    ffmpeg = _require_executable(config.ffmpeg_binary, "ffmpeg")
    ffprobe = _require_executable(config.ffprobe_binary, "ffprobe")
    colmap = _require_executable(config.colmap_binary, "COLMAP")
    brush = _require_executable(config.brush_binary, "Brush")
    object.__setattr__(config, "video", video)
    object.__setattr__(config, "output", output)
    object.__setattr__(config, "ffmpeg_binary", ffmpeg)
    object.__setattr__(config, "ffprobe_binary", ffprobe)
    object.__setattr__(config, "colmap_binary", colmap)
    object.__setattr__(config, "brush_binary", brush)
    output.mkdir(parents=True, mode=0o700)

    source = {"path": str(video), "bytes": video.stat().st_size, "sha256": sha256_file(video)}
    technical = probe_video(video, config.ffprobe_binary)
    commands: list[dict[str, Any]] = [_extract_frames(config, technical["duration_seconds"])]
    frame_names = sorted(path.name for path in (output / "frames").glob("*.jpg"))
    if len(frame_names) != config.keyframes:
        raise IPhone3DGSError(
            f"extraction produced {len(frame_names)} frames; expected {config.keyframes}"
        )
    training, heldout = deterministic_split(
        frame_names,
        holdout_fraction=config.holdout_fraction,
        seed=f"sim2claw-iphone-3dgs-v1:{source['sha256']}",
    )
    split = {
        "frozen_before_reconstruction": True,
        "training": training,
        "heldout": heldout,
    }
    split["split_sha256"] = _canonical_sha256(split)
    _write_json(output / "split.json", split)

    image_root = _stage_training_frames(config, training)
    sparse_model, colmap_receipts = _run_colmap(config, image_root)
    commands.extend(colmap_receipts)
    brush_dataset = _stage_brush_dataset(config, image_root, sparse_model)
    brush_output = output / "gaussians"
    brush_output.mkdir()
    commands.append(
        _run(
            [
                str(brush), str(brush_dataset),
                "--total-steps", str(config.training_steps),
                "--max-resolution", str(config.max_resolution),
                "--max-splats", str(config.max_splats),
                "--sh-degree", "3", "--seed", str(config.seed),
                "--eval-every", str(config.training_steps + 1),
                "--export-every", str(config.training_steps),
                "--export-path", str(brush_output),
                "--export-name", "candidate_{iter}.ply",
            ],
            log_prefix=output / "logs" / "05-brush-train",
            timeout_seconds=7200,
        )
    )
    candidate = brush_output / f"candidate_{config.training_steps}.ply"
    if not candidate.is_file():
        raise IPhone3DGSError("Brush exited successfully without the declared PLY export")
    artifact = inspect_gaussian_ply(candidate)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "proof_class": PROOF_CLASS,
        "source": source,
        "video": technical,
        "runtime_dependencies": {
            "ffmpeg": {"path": str(ffmpeg), "sha256": sha256_file(ffmpeg)},
            "ffprobe": {"path": str(ffprobe), "sha256": sha256_file(ffprobe)},
            "colmap": {"path": str(colmap), "sha256": sha256_file(colmap)},
            "brush": {"path": str(brush), "sha256": sha256_file(brush)},
        },
        "split": split,
        "settings": {
            "keyframes": config.keyframes,
            "max_resolution": config.max_resolution,
            "training_steps": config.training_steps,
            "max_splats": config.max_splats,
            "seed": config.seed,
            "camera_model": "OPENCV_single_camera_uncalibrated",
        },
        "sparse_model": str(sparse_model),
        "artifact": {"path": str(candidate), **artifact},
        "commands": commands,
        "authority": {
            "real_video_3dgs": True,
            "metric_scale": False,
            "rgbd": False,
            "physical_task": False,
            "training_or_policy_evidence": False,
            "heldout_photometric_evaluation": False,
        },
        "limitations": [
            "monocular_video_has_arbitrary_global_scale",
            "camera_intrinsics_are_sfm_estimates_not_physical_calibration",
            "heldout_frames_are_excluded_but_not_scored_by_this_v1_path",
            "visual_reconstruction_is_not_collision_or_robot_authority",
        ],
    }
    receipt["canonical_payload_sha256"] = _canonical_sha256(receipt)
    _write_json(output / "receipt.json", receipt)
    return receipt
