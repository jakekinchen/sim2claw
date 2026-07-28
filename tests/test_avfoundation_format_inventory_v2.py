from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_bytes,
)
from sim2claw.avfoundation_format_inventory_v2 import (
    ATTEMPT_SCHEMA,
    OBSERVATION_SCHEMA,
    PRELAUNCH_SCHEMA,
    USED_BUDGET,
    evaluate_format_inventory_v2,
    load_format_inventory_v2_contract,
    run_format_inventory_v2_observation,
    validate_v2_source_is_primitive_observer,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/avfoundation_format_inventory_v2.json"
)
SOURCE_PATH = REPO_ROOT / "tools/macos/AVFoundationFormatInventoryV2.swift"
EVALUATOR_PATH = REPO_ROOT / "src/sim2claw/avfoundation_format_inventory_v2.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _format(
    *,
    index: int,
    width: int = 640,
    height: int = 480,
    subtype: str = "2vuy",
    minimum_fps: float = 29.97002997002997,
    maximum_fps: float = 29.97002997002997,
    field_of_view: float | None = None,
) -> dict[str, object]:
    return {
        "format_index": index,
        "width": width,
        "height": height,
        "media_subtype_fourcc": subtype,
        "is_video_binned": None,
        "video_field_of_view_degrees": field_of_view,
        "video_max_zoom_factor": None,
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


def _runtime(observation_root: Path) -> dict[str, object]:
    binary = observation_root / "runtime/avfoundation-format-inventory-v2"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic v2 inventory binary\n")
    compiler = Path("/usr/bin/swiftc")
    return {
        "contract_sha256": _sha256(CONTRACT_PATH),
        "source_sha256": _sha256(SOURCE_PATH),
        "evaluator_sha256": _sha256(EVALUATOR_PATH),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256(compiler),
        "swift_version": "Apple Swift version 6.3 synthetic-test",
        "binary_path": "runtime/avfoundation-format-inventory-v2",
        "binary_sha256": _sha256(binary),
    }


def _materialize_observation(
    root: Path,
    *,
    formats: list[dict[str, object]] | None = None,
    return_code: int = 0,
    raw_available: bool = True,
) -> Path:
    observation_root = root / "observed"
    runtime = _runtime(observation_root)
    contract = load_format_inventory_v2_contract(CONTRACT_PATH)
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256(CONTRACT_PATH),
        "proof_class": "camera_device_format_inventory",
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_inventory_path": "raw/inventory.json",
        "stderr_path": "raw/inventory.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    raw_path = observation_root / "raw/inventory.json"
    if raw_available:
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
            "status": "observed",
            "device_localized_name": "C922 Pro Stream Webcam",
            "device_unique_id": "synthetic-c922",
            "device_model_id": "synthetic-model",
            "formats": formats or [_format(index=0)],
        }
        _write_json(raw_path, observation)
    stderr_path = observation_root / "raw/inventory.stderr.log"
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text("", encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256(CONTRACT_PATH),
        "proof_class": "camera_device_format_inventory",
        "status": (
            "observer_completed_with_raw"
            if raw_available
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": return_code,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": _sha256(raw_path) if raw_available else None,
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha256(stderr_path),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write_json(observation_root / "attempt.json", attempt)
    return observation_root


def _rewrite_attempt(observation_root: Path, attempt: dict[str, object]) -> None:
    _write_json(observation_root / "attempt.json", attempt)


def _rewrite_raw(observation_root: Path, observation: dict[str, object]) -> None:
    raw_path = observation_root / "raw/inventory.json"
    _write_json(raw_path, observation)
    attempt_path = observation_root / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_inventory_sha256"] = _sha256(raw_path)
    _write_json(attempt_path, attempt)


def test_v2_contract_preserves_rule_budget_and_serialization() -> None:
    contract = load_format_inventory_v2_contract(CONTRACT_PATH)
    assert contract["selection_rule"]["maximum_fractional_fps_deviation"] == 0.05
    assert contract["operation_budget"]["inventory_observations_maximum"] == 1
    assert contract["serialization"]["encoder"] == "Foundation.JSONEncoder"
    assert contract["serialization"]["dictionary_any_values_allowed"] is False
    assert contract["authority"]["capture_session_start"] is False


@pytest.mark.parametrize(
    "field",
    ["selection_rule", "serialization", "operation_budget"],
)
def test_v2_contract_rejects_post_hoc_method_change(
    tmp_path: Path,
    field: str,
) -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if field == "selection_rule":
        contract[field]["maximum_fractional_fps_deviation"] = 0.1
    elif field == "serialization":
        contract[field]["dictionary_any_values_allowed"] = True
    else:
        contract[field]["inventory_observations_maximum"] = 2
    path = tmp_path / "contract.json"
    _write_json(path, contract)
    with pytest.raises(AVFoundationFormatInventoryError, match="changed"):
        load_format_inventory_v2_contract(path)


def test_v2_swift_source_typechecks_and_is_primitive_only() -> None:
    validate_v2_source_is_primitive_observer(SOURCE_PATH)
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "[String: Any]" not in source
    assert "JSONSerialization" not in source
    result = __import__("subprocess").run(
        ["swiftc", "-typecheck", str(SOURCE_PATH)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert result.returncode == 0, result.stderr


def test_runner_writes_prelaunch_manifest_before_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_root = tmp_path / "observed"

    def fake_compile(**_: object) -> dict[str, object]:
        return _runtime(output_root)

    def fake_run(*_: object, **__: object) -> SimpleNamespace:
        assert (output_root / "attempt-prelaunch.json").is_file()
        return SimpleNamespace(returncode=-6, stderr="synthetic signal\n")

    monkeypatch.setattr(
        "sim2claw.avfoundation_format_inventory_v2.compile_format_inventory_v2",
        fake_compile,
    )
    monkeypatch.setattr(
        "sim2claw.avfoundation_format_inventory_v2.subprocess.run",
        fake_run,
    )
    attempt = run_format_inventory_v2_observation(
        contract_path=CONTRACT_PATH,
        source_path=SOURCE_PATH,
        evaluator_path=EVALUATOR_PATH,
        output_root=output_root,
    )
    assert attempt["status"] == "observer_failed_without_raw"
    assert attempt["return_code"] == -6
    assert attempt["raw_inventory_sha256"] is None
    assert (output_root / "attempt.json").is_file()


def test_v2_evaluator_selects_fractional_rate_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    evaluation, receipt = evaluate_format_inventory_v2(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "supported_exact_or_fractional_rate_candidate"
    assert evaluation["format_count"] == 1
    assert evaluation["eligible_candidate_count"] == 1
    assert evaluation["selected_candidate"]["fps_deviation"] < 0.05
    assert evaluation["claim_limits"]["future_campaign_authorized"] is False
    assert receipt["verdict"] == evaluation["verdict"]


def test_v2_evaluator_keeps_macos_unavailable_fov_out_of_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(
        tmp_path,
        formats=[_format(index=0, field_of_view=None)],
    )
    evaluation, _ = evaluate_format_inventory_v2(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "supported_exact_or_fractional_rate_candidate"
    assert "video_field_of_view_degrees" not in evaluation["selected_candidate"]


def test_v2_evaluator_abstains_with_finalized_missing_raw_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(
        tmp_path,
        return_code=-6,
        raw_available=False,
    )
    evaluation, _ = evaluate_format_inventory_v2(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["raw_inventory_available"] is False
    assert evaluation["format_count"] is None


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("prelaunch_hash", "prelaunch binding changed"),
        ("budget", "budget, or authority changed"),
        ("binary", "runtime identity changed"),
        ("raw", "raw identity changed"),
        ("camera", "camera identity changed"),
    ],
)
def test_v2_evaluator_rejects_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    attempt_path = observation_root / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    if mutation == "prelaunch_hash":
        attempt["prelaunch_manifest_sha256"] = "0" * 64
        _rewrite_attempt(observation_root, attempt)
    elif mutation == "budget":
        attempt["budget"]["capture_sessions_used"] = 1
        _rewrite_attempt(observation_root, attempt)
    elif mutation == "binary":
        (
            observation_root / "runtime/avfoundation-format-inventory-v2"
        ).write_bytes(b"substituted\n")
    elif mutation == "raw":
        (observation_root / "raw/inventory.json").write_text(
            "{}\n", encoding="utf-8"
        )
    else:
        raw_path = observation_root / "raw/inventory.json"
        observation = json.loads(raw_path.read_text(encoding="utf-8"))
        observation["camera_name_requested"] = "substituted"
        _rewrite_raw(observation_root, observation)
    with pytest.raises(AVFoundationFormatInventoryError, match=match):
        evaluate_format_inventory_v2(
            contract_path=CONTRACT_PATH,
            observation_root=observation_root,
            output_root=tmp_path / "evaluated",
        )


def test_v2_evaluation_is_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    observation_root = _materialize_observation(tmp_path)
    first_evaluation, first_receipt = evaluate_format_inventory_v2(
        contract_path=CONTRACT_PATH,
        observation_root=observation_root,
        output_root=tmp_path / "eval-1",
    )
    second_evaluation, second_receipt = evaluate_format_inventory_v2(
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
