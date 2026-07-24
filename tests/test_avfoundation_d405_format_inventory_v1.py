from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sim2claw.avfoundation_d405_format_inventory_v1 import (
    ATTEMPT_SCHEMA,
    BINARY_RELATIVE_PATH,
    CANONICAL_OUTPUT_ROOT,
    OBSERVATION_SCHEMA,
    PRELAUNCH_SCHEMA,
    PROOF_CLASS,
    USED_BUDGET,
    evaluate_d405_format_inventory,
    load_d405_format_inventory_contract,
    run_d405_format_inventory_observation,
)
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/avfoundation_d405_format_inventory_v1.json"
SOURCE = ROOT / "tools/macos/AVFoundationFormatInventoryV2.swift"
EVALUATOR = (
    ROOT / "src/sim2claw/avfoundation_d405_format_inventory_v1.py"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload))


def _format(
    *,
    index: int = 0,
    width: int = 424,
    height: int = 240,
    subtype: str = "2vuy",
    minimum_fps: float = 5.0,
    maximum_fps: float = 5.0,
) -> dict[str, object]:
    return {
        "format_index": index,
        "width": width,
        "height": height,
        "media_subtype_fourcc": subtype,
        "is_video_binned": None,
        "video_field_of_view_degrees": None,
        "video_max_zoom_factor": None,
        "supported_color_space_raw_values": [],
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


def _runtime(observed: Path) -> dict[str, object]:
    binary = observed / BINARY_RELATIVE_PATH
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"synthetic D405 inventory binary\n")
    compiler = Path("/usr/bin/swiftc")
    return {
        "contract_sha256": _sha(CONTRACT),
        "source_sha256": _sha(SOURCE),
        "evaluator_sha256": _sha(EVALUATOR),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha(compiler),
        "swift_version": "Apple Swift version 6.3 synthetic-test",
        "binary_path": BINARY_RELATIVE_PATH,
        "binary_sha256": _sha(binary),
    }


def _materialize(
    root: Path,
    *,
    formats: list[dict[str, object]] | None = None,
    return_code: int = 0,
    raw_available: bool = True,
) -> Path:
    observed = root / "observed"
    runtime = _runtime(observed)
    contract = load_d405_format_inventory_contract(CONTRACT)
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha(CONTRACT),
        "proof_class": PROOF_CLASS,
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_inventory_path": "raw/inventory.json",
        "stderr_path": "raw/inventory.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = observed / "attempt-prelaunch.json"
    _write(prelaunch_path, prelaunch)
    raw_path = observed / "raw/inventory.json"
    if raw_available:
        _write(
            raw_path,
            {
                "schema_version": OBSERVATION_SCHEMA,
                "contract_sha256": _sha(CONTRACT),
                "observer_role": "device_format_enumeration_only",
                "capture_session_created": False,
                "capture_session_started": False,
                "source_sample_count": 0,
                "authorization_status_raw_value": 3,
                "camera_name_requested": contract["device"][
                    "exact_localized_name"
                ],
                "device_match_count": 1,
                "detected_device_names": sorted(
                    [
                        "C922 Pro Stream Webcam",
                        contract["device"]["exact_localized_name"],
                    ]
                ),
                "status": "observed",
                "failure_reason": None,
                "device_localized_name": contract["device"][
                    "exact_localized_name"
                ],
                "device_unique_id": contract["device"]["exact_unique_id"],
                "device_model_id": contract["device"]["exact_model_id"],
                "formats": formats or [_format()],
            },
        )
    stderr = observed / "raw/inventory.stderr.log"
    stderr.parent.mkdir(parents=True, exist_ok=True)
    stderr.write_text("", encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha(CONTRACT),
        "proof_class": PROOF_CLASS,
        "status": (
            "observer_completed_with_raw"
            if raw_available
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": return_code,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": _sha(raw_path) if raw_available else None,
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha(stderr),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write(observed / "attempt.json", attempt)
    return observed


def _rewrite_raw(observed: Path, payload: dict[str, object]) -> None:
    raw = observed / "raw/inventory.json"
    _write(raw, payload)
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_inventory_sha256"] = _sha(raw)
    _write(attempt_path, attempt)


def test_contract_freezes_zero_session_rule_and_exact_identity() -> None:
    contract = load_d405_format_inventory_contract(CONTRACT)
    assert contract["device"]["exact_unique_id"] == "0x20000080860b5b"
    assert contract["selection_rule"]["target_width"] == 424
    assert contract["selection_rule"]["target_height"] == 240
    assert contract["selection_rule"]["target_fps"] == 5.0
    assert (
        contract["selection_rule"]["maximum_fractional_fps_deviation"] == 0.01
    )
    assert contract["operation_budget"]["capture_sessions_maximum"] == 0
    assert contract["authority"]["camera_frame_capture"] is False


@pytest.mark.parametrize("field", ["device", "selection_rule", "operation_budget"])
def test_contract_rejects_identity_threshold_or_budget_mutation(
    tmp_path: Path,
    field: str,
) -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if field == "device":
        contract[field]["exact_unique_id"] = "substituted"
    elif field == "selection_rule":
        contract[field]["maximum_fractional_fps_deviation"] = 1.0
    else:
        contract[field]["capture_sessions_maximum"] = 1
    mutated = tmp_path / "contract.json"
    _write(mutated, contract)
    with pytest.raises(AVFoundationFormatInventoryError, match="changed"):
        load_d405_format_inventory_contract(mutated)


def test_runner_persists_prelaunch_before_observer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    output = tmp_path / "observed"
    monkeypatch.setattr(
        "sim2claw.avfoundation_d405_format_inventory_v1."
        "CANONICAL_OUTPUT_ROOT",
        output,
    )

    def fake_compile(**_: object) -> dict[str, object]:
        return _runtime(output)

    def fake_run(*_: object, **__: object) -> SimpleNamespace:
        assert (output / "attempt-prelaunch.json").is_file()
        return SimpleNamespace(returncode=-6, stderr="synthetic signal\n")

    monkeypatch.setattr(
        "sim2claw.avfoundation_d405_format_inventory_v1."
        "compile_d405_format_inventory",
        fake_compile,
    )
    monkeypatch.setattr(
        "sim2claw.avfoundation_d405_format_inventory_v1.subprocess.run",
        fake_run,
    )
    attempt = run_d405_format_inventory_observation(
        contract_path=CONTRACT,
        source_path=SOURCE,
        evaluator_path=EVALUATOR,
        output_root=output,
    )
    assert attempt["return_code"] == -6
    assert attempt["raw_inventory_sha256"] is None
    assert (output / "attempt.json").is_file()


def test_runner_rejects_replayed_output_root_before_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    output = tmp_path / "observed"
    monkeypatch.setattr(
        "sim2claw.avfoundation_d405_format_inventory_v1."
        "CANONICAL_OUTPUT_ROOT",
        output,
    )
    output.mkdir()
    with pytest.raises(AVFoundationFormatInventoryError, match="replay"):
        run_d405_format_inventory_observation(
            contract_path=CONTRACT,
            source_path=SOURCE,
            evaluator_path=EVALUATOR,
            output_root=output,
        )


def test_runner_rejects_arbitrary_fresh_output_root() -> None:
    arbitrary = CANONICAL_OUTPUT_ROOT.with_name("unregistered-fresh-root")
    assert not arbitrary.exists()
    with pytest.raises(
        AVFoundationFormatInventoryError,
        match="authorized canonical root",
    ):
        run_d405_format_inventory_observation(
            contract_path=CONTRACT,
            source_path=SOURCE,
            evaluator_path=EVALUATOR,
            output_root=arbitrary,
        )


def test_evaluator_selects_exact_d405_candidate_without_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    evaluation, receipt = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "supported_d405_common_session_candidate"
    assert evaluation["format_count"] == 1
    assert evaluation["eligible_candidate_count"] == 1
    assert evaluation["selected_candidate"]["nearest_supported_fps"] == 5.0
    assert evaluation["claim_limits"]["native_common_session_supported"] is False
    assert receipt["verdict"] == evaluation["verdict"]


def test_evaluator_rejects_nonfinite_native_rate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    raw_path = observed / "raw/inventory.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["formats"][0]["frame_rate_ranges"][0]["minimum_fps"] = float("nan")
    raw_path.write_text(
        json.dumps(raw, allow_nan=True, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    attempt_path = observed / "attempt.json"
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    attempt["raw_inventory_sha256"] = _sha(raw_path)
    _write(attempt_path, attempt)
    with pytest.raises(AVFoundationFormatInventoryError, match="non-finite"):
        evaluate_d405_format_inventory(
            contract_path=CONTRACT,
            observation_root=observed,
            output_root=tmp_path / "evaluated",
        )


def test_evaluator_reports_no_candidate_without_relaxing_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(
        tmp_path,
        formats=[_format(width=640, height=480, minimum_fps=30, maximum_fps=30)],
    )
    evaluation, _ = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "no_supported_d405_common_session_candidate"
    assert evaluation["selected_candidate"] is None


def test_evaluator_abstains_when_observer_failed_without_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path, return_code=-6, raw_available=False)
    evaluation, _ = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["format_count"] is None


def test_evaluator_accepts_exact_empty_match_count_abstention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path, return_code=2)
    raw_path = observed / "raw/inventory.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw.update(
        {
            "authorization_status_raw_value": 3,
            "status": "prerequisite_unavailable",
            "failure_reason": "exact_device_match_count_invalid",
            "device_match_count": 0,
            "device_localized_name": None,
            "device_unique_id": None,
            "device_model_id": None,
            "formats": [],
        }
    )
    _rewrite_raw(observed, raw)
    evaluation, _ = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["format_count"] is None


@pytest.mark.parametrize(
    "mutation",
    ["formats", "identity", "status", "contradictory_match_count"],
)
def test_evaluator_rejects_malformed_raw_abstention(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path, return_code=2)
    raw_path = observed / "raw/inventory.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw.update(
        {
            "authorization_status_raw_value": 3,
            "status": "prerequisite_unavailable",
            "failure_reason": "exact_device_match_count_invalid",
            "device_match_count": 0,
            "device_localized_name": None,
            "device_unique_id": None,
            "device_model_id": None,
            "formats": [],
        }
    )
    if mutation == "formats":
        raw["formats"] = [_format()]
    elif mutation == "identity":
        raw["device_unique_id"] = "substituted"
    elif mutation == "status":
        raw["status"] = "observed"
    else:
        raw["device_match_count"] = 1
    _rewrite_raw(observed, raw)
    with pytest.raises(
        AVFoundationFormatInventoryError,
        match="malformed|contradicts",
    ):
        evaluate_d405_format_inventory(
            contract_path=CONTRACT,
            observation_root=observed,
            output_root=tmp_path / "evaluated",
        )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("device", "observed device identity changed"),
        ("capture", "widened into capture behavior"),
        ("raw", "raw identity changed"),
        ("binary", "runtime identity changed"),
        ("budget", "budget, or authority changed"),
    ],
)
def test_evaluator_rejects_substitution_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    if mutation in {"device", "capture"}:
        raw_path = observed / "raw/inventory.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if mutation == "device":
            raw["device_unique_id"] = "substituted"
        else:
            raw["capture_session_created"] = True
            raw["source_sample_count"] = 1
        _rewrite_raw(observed, raw)
    elif mutation == "raw":
        (observed / "raw/inventory.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "binary":
        (observed / BINARY_RELATIVE_PATH).write_bytes(b"substituted\n")
    else:
        attempt_path = observed / "attempt.json"
        attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
        attempt["budget"]["capture_sessions_used"] = 1
        _write(attempt_path, attempt)
    with pytest.raises(AVFoundationFormatInventoryError, match=match):
        evaluate_d405_format_inventory(
            contract_path=CONTRACT,
            observation_root=observed,
            output_root=tmp_path / "evaluated",
        )


def test_evaluation_materializes_byte_identically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    observed = _materialize(tmp_path)
    first = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "eval-1",
    )
    second = evaluate_d405_format_inventory(
        contract_path=CONTRACT,
        observation_root=observed,
        output_root=tmp_path / "eval-2",
    )
    assert first == second
    assert (tmp_path / "eval-1/evaluation.json").read_bytes() == (
        tmp_path / "eval-2/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "eval-1/receipt.json").read_bytes() == (
        tmp_path / "eval-2/receipt.json"
    ).read_bytes()
