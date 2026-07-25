from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

import sim2claw.frame_extraction_lineage as lineage


CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "configs/evaluations/current_100mm_frame_lineage_v1.json"
)


def _contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _probe_payload(contract: dict[str, object]) -> bytes:
    expected = contract["expected_stream"]
    stream = {
        "codec_name": expected["codec_name"],
        "width": expected["width"],
        "height": expected["height"],
        "pix_fmt": expected["pixel_format"],
        "avg_frame_rate": expected["average_frame_rate"],
        "time_base": expected["time_base"],
        "start_time": f"{expected['start_time_seconds']:.6f}",
        "duration": f"{expected['duration_seconds']:.6f}",
        "nb_frames": str(expected["frame_count"]),
    }
    frames = [
        {"best_effort_timestamp_time": f"{index / 30.0:.6f}"}
        for index in range(expected["frame_count"])
    ]
    frames[29]["best_effort_timestamp_time"] = "1.000000"
    return json.dumps({"streams": [stream], "frames": frames}).encode()


def _completed(stdout: bytes = b"", returncode: int = 0) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")


def test_contract_binds_source_decoder_and_zero_authority() -> None:
    contract = lineage.load_contract(CONTRACT_PATH)
    assert contract["decoder"]["frame_index_zero_based"] == 29
    assert contract["decoder"]["frame_pts_seconds"] == 1.0
    assert contract["decoder"]["geometric_filter_during_extraction"] is None
    assert contract["budgets"]["frame_derivations_maximum"] == 1
    assert contract["budgets"]["retries_maximum"] == 0
    assert contract["authority"]["physical_motion_authorized"] is False


def test_exact_commands_have_no_alternate_search_or_geometric_filter(tmp_path: Path) -> None:
    contract = _contract()
    probe = lineage._probe_arguments(contract)
    decode = lineage._decode_arguments(contract, tmp_path / "derived.png")
    assert probe[0] == "/opt/homebrew/bin/ffprobe"
    assert decode[0] == "/opt/homebrew/bin/ffmpeg"
    assert "select=eq(n\\,29)" in decode
    assert "-frames:v" in decode and decode[decode.index("-frames:v") + 1] == "1"
    assert "hflip" not in decode and "vflip" not in decode
    assert "-ss" not in decode


def test_matching_probe_and_frame_pass_pure_evaluator(tmp_path: Path) -> None:
    contract = _contract()
    existing = lineage._source_path(contract["source"]["existing_frame_path"])
    derived = tmp_path / "derived.png"
    derived.write_bytes(existing.read_bytes())
    result = lineage._evaluate(
        contract,
        probe=_completed(_probe_payload(contract)),
        decode=_completed(),
        derived_path=derived,
    )
    assert result["verdict"] == "frame_extraction_lineage_verified"
    assert result["failed_gates"] == []
    assert result["file_bytes_identical"] is True
    assert result["decoded_rgb24_identical"] is True
    assert result["budget"]["camera_sessions_used"] == 0


@pytest.mark.parametrize(
    ("mutation", "failed_gate"),
    [
        ("pts", "frame_pts"),
        ("dimensions", "stream_identity"),
        ("frame_bytes", "derived_file_bytes"),
        ("probe_failure", "metadata_probe_return_code"),
        ("decode_failure", "frame_derivation"),
    ],
)
def test_substitution_or_failure_is_rejected(
    tmp_path: Path,
    mutation: str,
    failed_gate: str,
) -> None:
    contract = _contract()
    existing = lineage._source_path(contract["source"]["existing_frame_path"])
    derived = tmp_path / "derived.png"
    derived.write_bytes(existing.read_bytes())
    probe_payload = json.loads(_probe_payload(contract))
    probe_rc = 0
    decode_rc = 0
    if mutation == "pts":
        probe_payload["frames"][29]["best_effort_timestamp_time"] = "1.100000"
    elif mutation == "dimensions":
        probe_payload["streams"][0]["width"] = 1920
    elif mutation == "frame_bytes":
        derived.write_bytes(b"not-a-png")
    elif mutation == "probe_failure":
        probe_rc = 1
    else:
        decode_rc = 1
        derived.unlink()
    result = lineage._evaluate(
        contract,
        probe=_completed(json.dumps(probe_payload).encode(), probe_rc),
        decode=_completed(returncode=decode_rc),
        derived_path=derived,
    )
    assert result["verdict"] == "frame_extraction_lineage_mismatch"
    assert failed_gate in result["failed_gates"]


def test_contract_or_output_root_substitution_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    altered = copy.deepcopy(_contract())
    altered["decoder"]["frame_index_zero_based"] = 30
    path = tmp_path / "altered.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(lineage.FrameExtractionLineageError, match="identity"):
        lineage.load_contract(path)
    with pytest.raises(lineage.FrameExtractionLineageError, match="canonical"):
        lineage.materialize(
            contract_path=CONTRACT_PATH,
            output_root=tmp_path / "substituted",
        )
    existing = tmp_path / "canonical"
    existing.mkdir()
    monkeypatch.setattr(lineage, "DEFAULT_OUTPUT_ROOT", existing)
    with pytest.raises(lineage.FrameExtractionLineageError, match="exists"):
        lineage.materialize(contract_path=CONTRACT_PATH, output_root=existing)
