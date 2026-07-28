from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image

import sim2claw.frame_extraction_lineage as lineage
from sim2claw.metric_registration_readiness import (
    _verified_executable_identity,
)


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
    assert "-show_frames" in probe
    assert decode[0].endswith("tools/current_frame_decoder_v1.zsh")
    wrapper = Path(decode[0]).read_text(encoding="utf-8")
    assert "select=eq(n\\,29)" in wrapper
    assert "-frames:v 1" in wrapper
    assert "hflip" not in wrapper and "vflip" not in wrapper
    assert "-ss" not in wrapper


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


def test_rgb_substitution_fails_independently_of_file_gate(tmp_path: Path) -> None:
    contract = _contract()
    derived = tmp_path / "derived.png"
    Image.new("RGB", (640, 480), (255, 0, 0)).save(derived)
    result = lineage._evaluate(
        contract,
        probe=_completed(_probe_payload(contract)),
        decode=_completed(),
        derived_path=derived,
    )
    assert "derived_file_bytes" in result["failed_gates"]
    assert "derived_rgb24_bytes" in result["failed_gates"]
    assert result["decoded_rgb24_identical"] is False


def test_missing_frames_array_fails_pts_gate(tmp_path: Path) -> None:
    contract = _contract()
    payload = json.loads(_probe_payload(contract))
    payload.pop("frames")
    existing = lineage._source_path(contract["source"]["existing_frame_path"])
    derived = tmp_path / "derived.png"
    derived.write_bytes(existing.read_bytes())
    result = lineage._evaluate(
        contract,
        probe=_completed(json.dumps(payload).encode()),
        decode=_completed(),
        derived_path=derived,
    )
    assert result["verdict"] == "frame_extraction_lineage_mismatch"
    assert "frame_pts" in result["failed_gates"]


def test_one_probe_one_decode_and_pass_receipt_is_consumer_compatible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = _contract()
    output = tmp_path / "canonical"
    monkeypatch.setattr(lineage, "DEFAULT_OUTPUT_ROOT", output)
    calls: list[list[str]] = []
    existing = lineage._source_path(contract["source"]["existing_frame_path"])

    def run(
        arguments: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append(arguments)
        assert kwargs == {
            "capture_output": True,
            "check": False,
            "timeout": 20,
        }
        if arguments[0].endswith("ffprobe"):
            return _completed(_probe_payload(contract))
        Path(arguments[-1]).write_bytes(existing.read_bytes())
        return _completed()

    monkeypatch.setattr(lineage.subprocess, "run", run)
    result = lineage.materialize(
        contract_path=CONTRACT_PATH,
        output_root=output,
    )
    assert len(calls) == 2
    assert sum(call[0].endswith("ffprobe") for call in calls) == 1
    assert sum(call[0].endswith("current_frame_decoder_v1.zsh") for call in calls) == 1
    receipt = result["receipt"]
    assert receipt["verdict"] == "frame_extraction_lineage_verified"
    assert receipt["file_bytes_identical"] is True
    assert receipt["decoded_rgb24_identical"] is True
    assert _verified_executable_identity(
        receipt["decoder_identity"],
        repo_root=Path(__file__).resolve().parents[1],
    )


def test_failed_evaluation_writes_no_consumable_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    contract = _contract()
    output = tmp_path / "canonical"
    monkeypatch.setattr(lineage, "DEFAULT_OUTPUT_ROOT", output)

    def run(
        arguments: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[bytes]:
        if arguments[0].endswith("ffprobe"):
            return _completed(_probe_payload(contract))
        return _completed(returncode=1)

    monkeypatch.setattr(lineage.subprocess, "run", run)
    with pytest.raises(lineage.FrameExtractionLineageError, match="no consumable"):
        lineage.materialize(
            contract_path=CONTRACT_PATH,
            output_root=output,
        )
    assert (output / "evaluation.json").is_file()
    assert not (output / "receipt.json").exists()
