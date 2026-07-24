from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    MANIFEST_SCHEMA,
    OBSERVATION_SCHEMA,
    _canonical_bytes,
    evaluate_format_inventory,
    load_format_inventory_contract,
    validate_inventory_source_is_observer_only,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/avfoundation_format_inventory_v1.json"
)
SOURCE_PATH = REPO_ROOT / "tools/macos/AVFoundationFormatInventory.swift"
EVALUATOR_PATH = REPO_ROOT / "src/sim2claw/avfoundation_format_inventory.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _format(
    *,
    format_index: int,
    width: int,
    height: int,
    subtype: str,
    minimum_fps: float,
    maximum_fps: float,
) -> dict[str, object]:
    return {
        "format_index": format_index,
        "width": width,
        "height": height,
        "media_subtype_fourcc": subtype,
        "is_video_binned": False,
        "video_field_of_view_degrees": 78.0,
        "video_max_zoom_factor": 1.0,
        "supported_color_space_raw_values": [0, 1],
        "frame_rate_ranges": [
            {
                "range_index": 0,
                "minimum_fps": minimum_fps,
                "maximum_fps": maximum_fps,
                "minimum_frame_duration_seconds": 1.0 / maximum_fps,
                "maximum_frame_duration_seconds": 1.0 / minimum_fps,
            }
        ],
    }


def _materialize_observation(
    root: Path,
    *,
    formats: list[dict[str, object]] | None = None,
    status: str = "observed",
    return_code: int = 0,
) -> Path:
    observation_root = root / "observation"
    binary = observation_root / "runtime/avfoundation-format-inventory"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic format inventory binary\n")
    raw_path = observation_root / "raw/inventory.json"
    stderr_path = observation_root / "raw/inventory.stderr.log"
    observation = {
        "schema_version": OBSERVATION_SCHEMA,
        "contract_sha256": _sha256(CONTRACT_PATH),
        "observer_role": "device_format_enumeration_only",
        "capture_session_created": False,
        "capture_session_started": False,
        "source_sample_count": 0,
        "authorization_status_raw_value": 3,
        "camera_name_requested": "C922 Pro Stream Webcam",
        "device_match_count": 1,
        "detected_device_names": ["C922 Pro Stream Webcam"],
        "status": status,
        "device_localized_name": "C922 Pro Stream Webcam",
        "device_unique_id": "synthetic-c922",
        "device_model_id": "synthetic-model",
        "formats": formats
        or [
            _format(
                format_index=0,
                width=1280,
                height=720,
                subtype="2vuy",
                minimum_fps=30.0,
                maximum_fps=30.0,
            ),
            _format(
                format_index=1,
                width=640,
                height=480,
                subtype="2vuy",
                minimum_fps=29.97002997002997,
                maximum_fps=29.97002997002997,
            ),
        ],
    }
    _write_json(raw_path, observation)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("", encoding="utf-8")
    compiler = Path("/usr/bin/swiftc")
    contract = load_format_inventory_contract(CONTRACT_PATH)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256(CONTRACT_PATH),
        "proof_class": "camera_device_format_inventory",
        "runtime_identity": {
            "contract_sha256": _sha256(CONTRACT_PATH),
            "source_sha256": _sha256(SOURCE_PATH),
            "evaluator_sha256": _sha256(EVALUATOR_PATH),
            "compiler_path": str(compiler),
            "compiler_sha256": _sha256(compiler),
            "swift_version": "Apple Swift version 6.3 synthetic-test",
            "binary_path": "runtime/avfoundation-format-inventory",
            "binary_sha256": _sha256(binary),
        },
        "return_code": return_code,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": _sha256(raw_path),
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha256(stderr_path),
        "budget": {
            "inventory_observations_used": 1,
            "capture_sessions_used": 0,
            "source_samples_used": 0,
            "d405_lifecycle_operations_used": 0,
            "robot_motion_trials_used": 0,
            "provider_calls_used": 0,
        },
        "authority": contract["authority"],
    }
    _write_json(observation_root / "observation.json", manifest)
    return observation_root


def _rewrite_raw_and_manifest(
    observation_root: Path,
    observation: dict[str, object],
) -> None:
    raw_path = observation_root / "raw/inventory.json"
    _write_json(raw_path, observation)
    manifest_path = observation_root / "observation.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["raw_inventory_sha256"] = _sha256(raw_path)
    _write_json(manifest_path, manifest)


def test_contract_freezes_one_enumeration_and_zero_capture_authority() -> None:
    contract = load_format_inventory_contract(CONTRACT_PATH)
    assert contract["operation_budget"]["inventory_observations_maximum"] == 1
    assert contract["operation_budget"]["capture_sessions_maximum"] == 0
    assert contract["operation_budget"]["source_samples_maximum"] == 0
    assert contract["authority"]["device_and_format_enumeration"] is True
    assert contract["authority"]["capture_session_start"] is False
    assert contract["authority"]["camera_frame_capture"] is False
    assert contract["authority"]["d405_lifecycle"] is False
    assert contract["authority"]["robot_motion"] is False


def test_contract_rejects_post_hoc_rate_tolerance_change(tmp_path: Path) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract["selection_rule"]["maximum_fractional_fps_deviation"] = 0.10
    path = tmp_path / "contract.json"
    _write_json(path, contract)
    with pytest.raises(
        AVFoundationFormatInventoryError, match="Selection rule changed"
    ):
        load_format_inventory_contract(path)


def test_swift_observer_typechecks_and_has_no_capture_surface() -> None:
    validate_inventory_source_is_observer_only(SOURCE_PATH)
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert '"verdict"' not in source
    assert '"eligible"' not in source
    result = __import__("subprocess").run(
        ["swiftc", "-typecheck", str(SOURCE_PATH)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert result.returncode == 0, result.stderr


def test_evaluator_selects_fractional_rate_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    evaluation, receipt = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "supported_exact_or_fractional_rate_candidate"
    assert evaluation["format_count"] == 2
    assert evaluation["exact_dimension_candidate_count"] == 1
    assert evaluation["eligible_candidate_count"] == 1
    assert evaluation["selected_candidate"]["format_index"] == 1
    assert evaluation["selected_candidate"]["fps_deviation"] < 0.05
    assert evaluation["claim_limits"]["future_campaign_authorized"] is False
    assert receipt["verdict"] == evaluation["verdict"]


def test_evaluator_rejects_rate_outside_frozen_tolerance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    formats = [
        _format(
            format_index=0,
            width=640,
            height=480,
            subtype="2vuy",
            minimum_fps=29.9,
            maximum_fps=29.9,
        )
    ]
    observation_root = _materialize_observation(tmp_path, formats=formats)
    evaluation, _ = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "no_supported_exact_dimension_rate_candidate"
    assert evaluation["eligible_candidate_count"] == 0
    assert evaluation["selected_candidate"] is None


def test_evaluator_applies_frozen_subtype_tie_break(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    formats = [
        _format(
            format_index=0,
            width=640,
            height=480,
            subtype="2vuy",
            minimum_fps=30.0,
            maximum_fps=30.0,
        ),
        _format(
            format_index=1,
            width=640,
            height=480,
            subtype="420v",
            minimum_fps=30.0,
            maximum_fps=30.0,
        ),
    ]
    observation_root = _materialize_observation(tmp_path, formats=formats)
    evaluation, _ = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["selected_candidate"]["media_subtype_fourcc"] == "420v"
    assert evaluation["selected_candidate"]["format_index"] == 1


def test_evaluator_abstains_on_observer_prerequisite_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(
        tmp_path,
        status="prerequisite_unavailable",
        return_code=2,
    )
    raw_path = observation_root / "raw/inventory.json"
    observation = json.loads(raw_path.read_text(encoding="utf-8"))
    observation["device_match_count"] = 0
    observation["formats"] = []
    _rewrite_raw_and_manifest(observation_root, observation)
    evaluation, _ = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["format_count"] == 0


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("raw_hash", "Raw observation identity changed"),
        ("binary", "identity changed"),
        ("evaluator", "identity changed"),
        ("budget", "budget changed"),
        ("authority", "authority changed"),
        ("camera", "camera identity changed"),
    ],
)
def test_evaluator_rejects_identity_authority_and_budget_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    manifest_path = observation_root / "observation.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "raw_hash":
        (observation_root / "raw/inventory.json").write_text(
            "{}\n", encoding="utf-8"
        )
    elif mutation == "binary":
        (
            observation_root / "runtime/avfoundation-format-inventory"
        ).write_bytes(b"substituted\n")
    elif mutation == "evaluator":
        manifest["runtime_identity"]["evaluator_sha256"] = "0" * 64
        _write_json(manifest_path, manifest)
    elif mutation == "budget":
        manifest["budget"]["capture_sessions_used"] = 1
        _write_json(manifest_path, manifest)
    elif mutation == "authority":
        manifest["authority"]["camera_frame_capture"] = True
        _write_json(manifest_path, manifest)
    else:
        raw_path = observation_root / "raw/inventory.json"
        observation = json.loads(raw_path.read_text(encoding="utf-8"))
        observation["camera_name_requested"] = "substituted"
        _rewrite_raw_and_manifest(observation_root, observation)
    with pytest.raises(AVFoundationFormatInventoryError, match=match):
        evaluate_format_inventory(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "evaluated",
        )


def test_evaluator_rejects_duplicate_format_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    raw_path = observation_root / "raw/inventory.json"
    observation = json.loads(raw_path.read_text(encoding="utf-8"))
    observation["formats"][1]["format_index"] = 0
    _rewrite_raw_and_manifest(observation_root, observation)
    with pytest.raises(
        AVFoundationFormatInventoryError, match="duplicate or non-contiguous"
    ):
        evaluate_format_inventory(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "evaluated",
        )


def test_evaluation_materialization_is_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    first_evaluation, first_receipt = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "eval-1",
    )
    second_evaluation, second_receipt = evaluate_format_inventory(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "eval-2",
    )
    assert first_evaluation == second_evaluation
    assert first_receipt == second_receipt
    assert (tmp_path / "eval-1/evaluation.json").read_bytes() == (
        tmp_path / "eval-2/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "eval-1/receipt.json").read_bytes() == (
        tmp_path / "eval-2/receipt.json"
    ).read_bytes()
