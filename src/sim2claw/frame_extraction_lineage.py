"""One-shot deterministic lineage proof for an existing C922 source frame."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from PIL import Image


CONTRACT_SCHEMA = "sim2claw.frame_extraction_lineage_contract.v1"
EVALUATION_SCHEMA = "sim2claw.frame_extraction_lineage_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.frame_extraction_receipt.v1"
CONTRACT_SHA256 = "331bf9226cd17248b3cf80c503e47d7e01c913755b4077c25aa94896b0396a3f"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/current_100mm_frame_lineage_v1.json"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "outputs/current-100mm-frame-lineage-v1"
DECODER_WRAPPER_PATH = REPO_ROOT / "tools/current_frame_decoder_v1.zsh"


class FrameExtractionLineageError(RuntimeError):
    """The frozen frame-lineage boundary was unavailable or changed."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical_bytes(value) + b"\n")
    temporary.replace(path)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FrameExtractionLineageError(f"Could not load {label}: {error}") from error
    if not isinstance(value, dict):
        raise FrameExtractionLineageError(f"{label} must be an object.")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FrameExtractionLineageError(message)


def _source_path(declared: Any) -> Path:
    _require(isinstance(declared, str) and bool(declared), "Source path is missing.")
    path = (REPO_ROOT / declared).resolve()
    root = REPO_ROOT.resolve()
    _require(path != root and root in path.parents, "Source path escapes the repository.")
    return path


def load_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    _require(sha256_file(path) == CONTRACT_SHA256, "Contract identity changed.")
    contract = _load_json(path, "frame-lineage contract")
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "Contract schema changed.")
    _require(contract.get("status") == "preregistered", "Contract status changed.")
    for name in ("capture_receipt", "video", "existing_frame"):
        source_path = _source_path(contract["source"][f"{name}_path"])
        _require(source_path.is_file(), f"{name} source is missing.")
        _require(
            sha256_file(source_path) == contract["source"][f"{name}_sha256"],
            f"{name} source identity changed.",
        )
    source = contract["source"]
    capture = _load_json(_source_path(source["capture_receipt_path"]), "capture receipt")
    reports = capture.get("camera_reports")
    matches = (
        [
            row
            for row in reports
            if isinstance(row, dict) and row.get("id") == source["camera_id"]
        ]
        if isinstance(reports, list)
        else []
    )
    _require(len(matches) == 1, "Capture receipt camera binding changed.")
    report = matches[0]
    _require(
        report.get("name") == source["camera_name"]
        and report.get("size") == f"{source['image_size_px'][0]}x{source['image_size_px'][1]}"
        and report.get("filter") == source["capture_orientation_filter"]
        and report.get("sha256") == source["video_sha256"]
        and report.get("status") == "completed_full_timestamp_coverage",
        "Capture receipt video identity changed.",
    )
    _require(
        capture.get("promotion_authority") is False
        and capture.get("training_admission") is False,
        "Capture receipt authority changed.",
    )
    decoder = contract["decoder"]
    for name in ("ffmpeg", "ffprobe"):
        binary = Path(decoder[f"{name}_path"])
        _require(binary.is_file(), f"{name} is unavailable.")
        _require(
            sha256_file(binary) == decoder[f"{name}_sha256"],
            f"{name} identity changed.",
        )
    _require(DECODER_WRAPPER_PATH.is_file(), "Decoder wrapper is unavailable.")
    _require(
        contract["budgets"]
        == {
            "metadata_probes_maximum": 1,
            "frame_derivations_maximum": 1,
            "retries_maximum": 0,
            "camera_sessions_maximum": 0,
            "new_camera_frames_maximum": 0,
            "robot_motions_maximum": 0,
            "simulator_replays_maximum": 0,
            "provider_calls_maximum": 0,
        },
        "Frame-lineage budget changed.",
    )
    return contract


def _probe_arguments(contract: dict[str, Any]) -> list[str]:
    decoder = contract["decoder"]
    video = _source_path(contract["source"]["video_path"])
    return [
        decoder["ffprobe_path"],
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        (
            "stream=codec_name,width,height,pix_fmt,avg_frame_rate,time_base,"
            "start_time,duration,nb_frames:frame=best_effort_timestamp_time"
        ),
        "-of",
        "json",
        str(video),
    ]


def _decode_arguments(contract: dict[str, Any], output_path: Path) -> list[str]:
    video = _source_path(contract["source"]["video_path"])
    return [
        str(DECODER_WRAPPER_PATH),
        str(video),
        str(output_path),
    ]


def _rgb24_sha256(path: Path) -> tuple[str, list[int]]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        return hashlib.sha256(rgb.tobytes()).hexdigest(), [rgb.width, rgb.height]


def _evaluate(
    contract: dict[str, Any],
    *,
    probe: subprocess.CompletedProcess[bytes],
    decode: subprocess.CompletedProcess[bytes],
    derived_path: Path,
) -> dict[str, Any]:
    failed: list[str] = []
    if probe.returncode != 0:
        failed.append("metadata_probe_return_code")
        metadata: dict[str, Any] = {}
    else:
        try:
            metadata = json.loads(probe.stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            metadata = {}
            failed.append("metadata_probe_json")
    streams = metadata.get("streams") if isinstance(metadata, dict) else None
    frames = metadata.get("frames") if isinstance(metadata, dict) else None
    expected = contract["expected_stream"]
    if not isinstance(streams, list) or len(streams) != 1:
        failed.append("stream_identity")
        stream: dict[str, Any] = {}
    else:
        stream = streams[0]
        try:
            observed_stream = {
                "codec_name": stream.get("codec_name"),
                "width": stream.get("width"),
                "height": stream.get("height"),
                "pixel_format": stream.get("pix_fmt"),
                "average_frame_rate": stream.get("avg_frame_rate"),
                "time_base": stream.get("time_base"),
                "start_time_seconds": float(stream.get("start_time", -1.0)),
                "duration_seconds": float(stream.get("duration", -1.0)),
                "frame_count": int(stream.get("nb_frames", -1)),
            }
        except (TypeError, ValueError):
            observed_stream = {}
        if observed_stream != expected:
            failed.append("stream_identity")
    frame_index = int(contract["decoder"]["frame_index_zero_based"])
    expected_pts = float(contract["decoder"]["frame_pts_seconds"])
    if not isinstance(frames, list) or len(frames) <= frame_index:
        failed.append("frame_pts")
        observed_pts = None
    else:
        try:
            observed_pts = float(frames[frame_index]["best_effort_timestamp_time"])
        except (KeyError, TypeError, ValueError):
            observed_pts = None
        if observed_pts is None or abs(observed_pts - expected_pts) > 1e-9:
            failed.append("frame_pts")

    derived_sha: str | None = None
    derived_rgb_sha: str | None = None
    derived_size: list[int] | None = None
    if decode.returncode != 0 or not derived_path.is_file():
        failed.append("frame_derivation")
    else:
        derived_sha = sha256_file(derived_path)
        try:
            derived_rgb_sha, derived_size = _rgb24_sha256(derived_path)
        except OSError:
            failed.append("derived_frame_decode")
        source = contract["source"]
        if derived_sha != source["existing_frame_sha256"]:
            failed.append("derived_file_bytes")
        if derived_rgb_sha != source["existing_frame_rgb24_sha256"]:
            failed.append("derived_rgb24_bytes")
        if derived_size != source["image_size_px"]:
            failed.append("derived_dimensions")

    source_frame = _source_path(contract["source"]["existing_frame_path"])
    existing_rgb_sha, existing_size = _rgb24_sha256(source_frame)
    if existing_rgb_sha != contract["source"]["existing_frame_rgb24_sha256"]:
        failed.append("existing_rgb24_bytes")
    if existing_size != contract["source"]["image_size_px"]:
        failed.append("existing_dimensions")
    verdict = (
        contract["decision"]["pass_verdict"]
        if not failed
        else contract["decision"]["fail_verdict"]
    )
    return {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "verdict": verdict,
        "failed_gates": sorted(set(failed)),
        "frame_index_zero_based": frame_index,
        "expected_frame_pts_seconds": expected_pts,
        "observed_frame_pts_seconds": observed_pts,
        "derived_frame_sha256": derived_sha,
        "derived_frame_rgb24_sha256": derived_rgb_sha,
        "existing_frame_sha256": contract["source"]["existing_frame_sha256"],
        "existing_frame_rgb24_sha256": existing_rgb_sha,
        "file_bytes_identical": (
            derived_sha == contract["source"]["existing_frame_sha256"]
        ),
        "decoded_rgb24_identical": (
            derived_rgb_sha == existing_rgb_sha
            == contract["source"]["existing_frame_rgb24_sha256"]
        ),
        "budget": {
            "metadata_probes_used": 1,
            "frame_derivations_used": 1,
            "retries_used": 0,
            "camera_sessions_used": 0,
            "new_camera_frames_used": 0,
            "robot_motions_used": 0,
            "simulator_replays_used": 0,
            "provider_calls_used": 0,
        },
        "authority": {
            **contract["authority"],
            "metric_registration_readiness_v1_changed": False,
            "twin_fidelity_changed": False,
        },
    }


def materialize(
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    _require(
        output_root.resolve() == DEFAULT_OUTPUT_ROOT.resolve(),
        "Frame lineage requires the canonical output root.",
    )
    _require(not output_root.exists(), "Frame-lineage output exists; replay refused.")
    contract = load_contract(contract_path)
    output_root.mkdir(parents=True, exist_ok=False)
    raw_root = output_root / "raw"
    raw_root.mkdir()
    derived_path = raw_root / "derived_frame.png"
    probe_args = _probe_arguments(contract)
    decode_args = _decode_arguments(contract, derived_path)
    prelaunch = {
        "schema_version": "sim2claw.frame_extraction_lineage_prelaunch.v1",
        "contract_sha256": CONTRACT_SHA256,
        "runner_evaluator_sha256": sha256_file(Path(__file__).resolve()),
        "probe_arguments": probe_args,
        "decode_arguments": decode_args,
        "budget": contract["budgets"],
        "authority": contract["authority"],
    }
    _write_json(output_root / "prelaunch.json", prelaunch)
    probe = subprocess.run(probe_args, capture_output=True, check=False, timeout=20)
    (raw_root / "ffprobe.stdout.json").write_bytes(probe.stdout)
    (raw_root / "ffprobe.stderr.log").write_bytes(probe.stderr)
    decode = subprocess.run(decode_args, capture_output=True, check=False, timeout=20)
    (raw_root / "ffmpeg.stdout.log").write_bytes(decode.stdout)
    (raw_root / "ffmpeg.stderr.log").write_bytes(decode.stderr)
    evaluation = _evaluate(
        contract,
        probe=probe,
        decode=decode,
        derived_path=derived_path,
    )
    _write_json(output_root / "evaluation.json", evaluation)
    if evaluation["verdict"] != contract["decision"]["pass_verdict"]:
        raise FrameExtractionLineageError(
            "Frame lineage did not pass; no consumable receipt was written."
        )
    decoder = contract["decoder"]
    wrapper_sha256 = sha256_file(DECODER_WRAPPER_PATH)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": CONTRACT_SHA256,
        "proof_class": contract["authority"]["proof_class"],
        "verdict": evaluation["verdict"],
        "source_video_sha256": contract["source"]["video_sha256"],
        "source_timestamp_seconds": decoder["frame_pts_seconds"],
        "source_frame_index_zero_based": decoder["frame_index_zero_based"],
        "decoder_identity": {
            "name": "sim2claw-current-frame-decoder",
            "version": "1",
            "executable_path": str(DECODER_WRAPPER_PATH.relative_to(REPO_ROOT)),
            "executable_sha256": wrapper_sha256,
        },
        "underlying_decoder_identity": {
            "name": "ffmpeg",
            "version": decoder["ffmpeg_version"],
            "executable_path": decoder["ffmpeg_path"],
            "executable_sha256": decoder["ffmpeg_sha256"],
        },
        "probe_identity": {
            "name": "ffprobe",
            "executable_path": decoder["ffprobe_path"],
            "executable_sha256": decoder["ffprobe_sha256"],
        },
        "orientation_filter": contract["source"]["capture_orientation_filter"],
        "orientation_application": decoder["orientation_application"],
        "output_frame_sha256": evaluation["derived_frame_sha256"],
        "output_frame_rgb24_sha256": evaluation["derived_frame_rgb24_sha256"],
        "existing_frame_sha256": evaluation["existing_frame_sha256"],
        "file_bytes_identical": evaluation["file_bytes_identical"],
        "decoded_rgb24_identical": evaluation["decoded_rgb24_identical"],
        "evaluation_sha256": sha256_file(output_root / "evaluation.json"),
        "evaluation_digest": canonical_digest(evaluation),
        "budget": evaluation["budget"],
        "authority": evaluation["authority"],
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    _write_json(output_root / "receipt.json", receipt)
    return {"evaluation": evaluation, "receipt": receipt}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(argv)
    result = materialize(contract_path=args.contract, output_root=args.output_root)
    print(json.dumps(result["receipt"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
