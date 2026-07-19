from __future__ import annotations

import struct
from pathlib import Path

import pytest

from sim2claw.iphone_3dgs import (
    IPhone3DGSError,
    _require_private_output,
    deterministic_split,
    inspect_gaussian_ply,
)
from sim2claw.cli import build_parser


def test_split_is_deterministic_disjoint_and_source_ordered() -> None:
    frames = [f"frame-{index:06d}.jpg" for index in range(80)]
    first = deterministic_split(frames, holdout_fraction=0.125, seed="frozen")
    second = deterministic_split(frames, holdout_fraction=0.125, seed="frozen")
    assert first == second
    training, heldout = first
    assert len(training) == 70
    assert len(heldout) == 10
    assert not set(training) & set(heldout)
    assert training == [name for name in frames if name in set(training)]
    assert heldout == [name for name in frames if name in set(heldout)]


def test_private_output_gate_rejects_tracked_style_path(tmp_path: Path) -> None:
    with pytest.raises(IPhone3DGSError, match="artifacts/private"):
        _require_private_output(tmp_path / "outputs" / "scan")
    accepted = _require_private_output(tmp_path / "artifacts" / "private" / "scan")
    assert accepted.name == "scan"


def test_gaussian_ply_inspection_requires_real_gaussian_fields(tmp_path: Path) -> None:
    header = "\n".join(
        [
            "ply",
            "format binary_little_endian 1.0",
            "element vertex 1",
            "property float x",
            "property float y",
            "property float z",
            "property float opacity",
            "property float scale_0",
            "property float rot_0",
            "property float f_rest_0",
            "end_header",
            "",
        ]
    ).encode("ascii")
    path = tmp_path / "candidate.ply"
    path.write_bytes(header + struct.pack("<7f", *([0.0] * 7)))
    report = inspect_gaussian_ply(path)
    assert report["splat_count"] == 1
    assert report["format"] == "binary_little_endian_1.0"
    assert report["inferred_sh_degree"] == 0


def test_split_rejects_too_few_frames() -> None:
    with pytest.raises(IPhone3DGSError, match="at least eight"):
        deterministic_split(["a.jpg"], holdout_fraction=0.125, seed="x")


def test_cli_exposes_explicit_pipeline_dependencies(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        [
            "iphone-3dgs",
            "--video",
            str(tmp_path / "source.MOV"),
            "--output",
            str(tmp_path / "artifacts/private/run"),
            "--ffmpeg",
            "/tools/ffmpeg",
            "--ffprobe",
            "/tools/ffprobe",
            "--colmap",
            "/tools/colmap",
            "--brush",
            "/tools/brush",
        ]
    )
    assert args.command == "iphone-3dgs"
    assert args.training_steps == 30_000
    assert args.keyframes == 80
