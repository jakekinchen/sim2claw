from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.avfoundation_source_localization import (
    AVFoundationLocalizationError,
    CAMPAIGN_SCHEMA,
    EXPECTED_TRIAL_ORDER,
    ORCHESTRATION_EVENT_SCHEMA,
    SOURCE_EVENT_SCHEMA,
    TRIAL_SCHEMA,
    _canonical_bytes,
    compile_source_probe,
    evaluate_source_localization_campaign,
    load_source_localization_contract,
    parse_orchestration_events,
    parse_source_events,
    summarize_source_events,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/avfoundation_source_localization_v1.json"
)
SOURCE_PATH = REPO_ROOT / "tools/macos/AVFoundationSourceProbe.swift"
RUNNER_PATH = REPO_ROOT / "src/sim2claw/avfoundation_source_localization.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical_bytes(row) for row in rows))


def _source_events(
    *,
    boundary_gap: bool = False,
    drop_reason: str | None = None,
    disconnect: bool = False,
) -> list[dict[str, object]]:
    base = 1_000_000_000
    rows: list[dict[str, object]] = []

    def add(event_type: str, host_ns: int, **fields: object) -> None:
        rows.append(
            {
                "schema_version": SOURCE_EVENT_SCHEMA,
                "event_index": len(rows),
                "event_type": event_type,
                "host_continuous_ns": host_ns,
                **fields,
            }
        )

    add("probe_started", base)
    add("session_start_requested", base + 1_000_000)
    add("session_start_returned", base + 10_000_000)
    sample_rows = [
        (base + 4_980_000_000, 0.000000),
        (
            base + 5_020_000_000,
            0.500000 if boundary_gap else 0.033333,
        ),
        (
            base + 24_980_000_000,
            0.533333 if boundary_gap else 0.066666,
        ),
        (
            base + 25_020_000_000,
            0.566666 if boundary_gap else 0.099999,
        ),
    ]
    for sequence, (host_ns, pts) in enumerate(sample_rows, start=1):
        add(
            "sample_output",
            host_ns,
            local_sequence=sequence,
            sample_pts_valid=True,
            sample_pts_seconds=pts,
        )
    if drop_reason is not None:
        add(
            "sample_dropped",
            base + 25_030_000_000,
            local_sequence=1,
            sample_pts_valid=True,
            sample_pts_seconds=0.133332,
            drop_reason=drop_reason,
            drop_reason_info=None,
        )
    if disconnect:
        add(
            "device_disconnected",
            base + 25_040_000_000,
            device_name="Intel(R) RealSense(TM) Depth Camera 405  Depth",
        )
    add("session_stop_requested", base + 30_000_000_000)
    add("session_stop_returned", base + 30_010_000_000)
    add(
        "probe_finished",
        base + 30_020_000_000,
        sample_output_count=4,
        sample_dropped_count=1 if drop_reason is not None else 0,
        write_failure=None,
    )
    return rows


def _orchestration_events() -> list[dict[str, object]]:
    base = 1_000_000_000
    event_types = [
        ("trial_started", base),
        ("lifecycle_start_requested", base + 5_000_000_000),
        ("lifecycle_start_returned", base + 5_100_000_000),
        ("lifecycle_stop_requested", base + 25_000_000_000),
        ("lifecycle_stop_returned", base + 25_100_000_000),
        ("trial_finished", base + 31_000_000_000),
    ]
    return [
        {
            "schema_version": ORCHESTRATION_EVENT_SCHEMA,
            "event_index": index,
            "event_type": event_type,
            "host_continuous_ns": host_ns,
        }
        for index, (event_type, host_ns) in enumerate(event_types)
    ]


def _materialize_campaign(
    root: Path,
    *,
    treatment_gap: bool = False,
    treatment_drop_reason: str | None = None,
    disconnect_trial: str | None = None,
) -> Path:
    contract = load_source_localization_contract(CONTRACT_PATH)
    campaign_root = root / "raw"
    binary = campaign_root / "runtime/avfoundation-source-probe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic compiled probe\n")
    entries: list[dict[str, object]] = []

    for attempt_index, trial_id in enumerate(EXPECTED_TRIAL_ORDER, start=1):
        cell = "T" if trial_id.startswith("T") else "C"
        trial_root = campaign_root / "trials" / trial_id
        source_path = trial_root / "c922_source_events.jsonl"
        orchestration_path = trial_root / "orchestration_events.jsonl"
        _write_jsonl(
            source_path,
            _source_events(
                boundary_gap=treatment_gap and cell == "T",
                drop_reason=treatment_drop_reason if cell == "T" else None,
                disconnect=trial_id == disconnect_trial,
            ),
        )
        _write_jsonl(orchestration_path, _orchestration_events())
        artifacts = {
            source_path.name: _sha256(source_path),
            orchestration_path.name: _sha256(orchestration_path),
        }
        report_path: Path | None = None
        if cell == "T":
            report_path = trial_root / "d405_report.json"
            _write_json(
                report_path,
                {"status": "completed", "source_stall_detected": False},
            )
            artifacts[report_path.name] = _sha256(report_path)
        trial = {
            "schema_version": TRIAL_SCHEMA,
            "trial_id": trial_id,
            "attempt_index": attempt_index,
            "cell": cell,
            "replacement": False,
            "robot_motion": False,
            "trial_error": None,
            "source_probe_return_code": 0,
            "source_event_path": source_path.name,
            "orchestration_event_path": orchestration_path.name,
            "d405_report_path": report_path.name if report_path else None,
            "artifact_sha256": artifacts,
        }
        trial_path = trial_root / "trial.json"
        _write_json(trial_path, trial)
        entries.append(
            {
                "trial_id": trial_id,
                "attempt_index": attempt_index,
                "cell": cell,
                "trial_sha256": _sha256(trial_path),
            }
        )

    campaign = {
        "schema_version": CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256(CONTRACT_PATH),
        "proof_class": "camera_source_lifecycle_localization",
        "runtime_identity": {
            "source_probe_binary_path": "runtime/avfoundation-source-probe",
            "source_probe_binary_sha256": _sha256(binary),
            "swift_source_sha256": _sha256(SOURCE_PATH),
            "python_runner_sha256": _sha256(RUNNER_PATH),
        },
        "budget": {
            "required_trials": 12,
            "used_trials": 12,
            "control_trials": 6,
            "treatment_trials": 6,
            "replacement_trials_allowed": 0,
            "replacement_trials_used": 0,
            "robot_motion_trials": 0,
            "provider_calls": 0,
        },
        "trials": entries,
        "authority": contract["authority"],
    }
    _write_json(campaign_root / "campaign.json", campaign)
    return campaign_root


def test_frozen_contract_loads_with_closed_authority() -> None:
    contract = load_source_localization_contract(CONTRACT_PATH)
    assert contract["campaign"]["fixed_trial_order"] == EXPECTED_TRIAL_ORDER
    assert contract["campaign"]["total_trials"] == 12
    assert contract["campaign"]["replacement_trials"] == 0
    assert not any(contract["authority"].values())


def test_contract_rejects_post_hoc_threshold_change(tmp_path: Path) -> None:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    payload["evaluator"]["boundary_window_seconds"] = 2.0
    path = tmp_path / "contract.json"
    _write_json(path, payload)
    with pytest.raises(AVFoundationLocalizationError, match="boundary_window_seconds"):
        load_source_localization_contract(path)


def test_swift_probe_typechecks() -> None:
    result = __import__("subprocess").run(
        ["swiftc", "-typecheck", str(SOURCE_PATH)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30.0,
    )
    assert result.returncode == 0, result.stderr


def test_compiler_binds_source_runner_and_binary(tmp_path: Path) -> None:
    identity = compile_source_probe(
        contract_path=CONTRACT_PATH,
        source_path=SOURCE_PATH,
        runner_path=RUNNER_PATH,
        binary_path=tmp_path / "avfoundation-source-probe",
    )
    assert identity["contract_sha256"] == _sha256(CONTRACT_PATH)
    assert identity["swift_source_sha256"] == _sha256(SOURCE_PATH)
    assert identity["python_runner_sha256"] == _sha256(RUNNER_PATH)
    assert identity["source_probe_binary_sha256"] == _sha256(
        tmp_path / "avfoundation-source-probe"
    )


def test_source_parser_rejects_schema_and_event_replay(tmp_path: Path) -> None:
    rows = _source_events()
    rows[1]["schema_version"] = "wrong"
    path = tmp_path / "events.jsonl"
    _write_jsonl(path, rows)
    with pytest.raises(AVFoundationLocalizationError, match="schema"):
        parse_source_events(path)

    rows = _source_events()
    rows[2]["event_index"] = rows[1]["event_index"]
    _write_jsonl(path, rows)
    with pytest.raises(AVFoundationLocalizationError, match="not contiguous"):
        parse_source_events(path)


def test_orchestration_parser_rejects_non_monotonic_host_time(tmp_path: Path) -> None:
    rows = _orchestration_events()
    rows[2]["host_continuous_ns"] = 0
    path = tmp_path / "orchestration.jsonl"
    _write_jsonl(path, rows)
    with pytest.raises(AVFoundationLocalizationError, match="non-monotonic"):
        parse_orchestration_events(path)


def test_summary_separates_boundary_gap_and_drop_reason() -> None:
    summary = summarize_source_events(
        source_events=_source_events(
            boundary_gap=True,
            drop_reason="DroppedFrameReason_FrameWasLate",
        ),
        orchestration_events=_orchestration_events(),
        nominal_interval_seconds=1.0 / 30.0,
        large_interval_multiplier=1.5,
        boundary_window_seconds=1.5,
    )
    assert summary["large_source_interval_count"] == 1
    assert summary["boundary_aligned_large_source_interval_count"] == 1
    assert summary["sample_dropped_count"] == 1
    assert summary["boundary_aligned_dropped_sample_count"] == 1
    assert summary["semantics"]["source_continuity_proves_physical_exposure_continuity"] is False


def test_summary_rejects_malformed_pts() -> None:
    events = _source_events()
    sample = next(row for row in events if row["event_type"] == "sample_output")
    sample["sample_pts_seconds"] = "nan"
    with pytest.raises(AVFoundationLocalizationError, match="non-finite"):
        summarize_source_events(
            source_events=events,
            orchestration_events=_orchestration_events(),
            nominal_interval_seconds=1.0 / 30.0,
            large_interval_multiplier=1.5,
            boundary_window_seconds=1.5,
        )


def test_evaluator_reports_source_continuity_and_is_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    campaign_root = _materialize_campaign(tmp_path)
    first_eval, first_receipt = evaluate_source_localization_campaign(
        contract_path=CONTRACT_PATH,
        campaign_root=campaign_root,
        output_root=tmp_path / "eval-1",
    )
    second_eval, second_receipt = evaluate_source_localization_campaign(
        contract_path=CONTRACT_PATH,
        campaign_root=campaign_root,
        output_root=tmp_path / "eval-2",
    )
    assert first_eval["verdict"] == "source_continuous_under_d405_lifecycle"
    assert first_eval == second_eval
    assert first_receipt == second_receipt
    assert (tmp_path / "eval-1/evaluation.json").read_bytes() == (
        tmp_path / "eval-2/evaluation.json"
    ).read_bytes()
    assert (tmp_path / "eval-1/receipt.json").read_bytes() == (
        tmp_path / "eval-2/receipt.json"
    ).read_bytes()


def test_evaluator_reports_replicated_source_discontinuity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    campaign_root = _materialize_campaign(tmp_path, treatment_gap=True)
    evaluation, _ = evaluate_source_localization_campaign(
        contract_path=CONTRACT_PATH,
        campaign_root=campaign_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "source_discontinuity_replicated"
    assert evaluation["treatment_source_discontinuity_trial_count"] == 6
    assert evaluation["control_boundary_event_count"] == 0


def test_evaluator_reports_replicated_late_client_drop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    campaign_root = _materialize_campaign(
        tmp_path,
        treatment_drop_reason="DroppedFrameReason_FrameWasLate",
    )
    evaluation, _ = evaluate_source_localization_campaign(
        contract_path=CONTRACT_PATH,
        campaign_root=campaign_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "client_lateness_or_buffer_pressure_replicated"
    assert evaluation["treatment_late_or_buffer_trial_count"] == 6


def test_evaluator_abstains_on_device_disconnect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    campaign_root = _materialize_campaign(tmp_path, disconnect_trial="T03")
    evaluation, _ = evaluate_source_localization_campaign(
        contract_path=CONTRACT_PATH,
        campaign_root=campaign_root,
        output_root=tmp_path / "evaluated",
    )
    assert evaluation["verdict"] == "prerequisite_abstention"
    assert evaluation["device_disconnect_count"] == 1


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("order", "order or uniqueness"),
        ("authority", "authority changed"),
        ("binary", "binary identity changed"),
        ("trial_hash", "Trial receipt mismatch"),
    ],
)
def test_evaluator_rejects_substitution_and_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    match: str,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    campaign_root = _materialize_campaign(tmp_path)
    campaign_path = campaign_root / "campaign.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    if mutation == "order":
        campaign["trials"][0], campaign["trials"][1] = (
            campaign["trials"][1],
            campaign["trials"][0],
        )
        _write_json(campaign_path, campaign)
    elif mutation == "authority":
        campaign["authority"]["robot_motion"] = True
        _write_json(campaign_path, campaign)
    elif mutation == "binary":
        (campaign_root / "runtime/avfoundation-source-probe").write_text(
            "substituted\n",
            encoding="utf-8",
        )
    else:
        campaign["trials"][0]["trial_sha256"] = "0" * 64
        _write_json(campaign_path, campaign)

    with pytest.raises(AVFoundationLocalizationError, match=match):
        evaluate_source_localization_campaign(
            contract_path=CONTRACT_PATH,
            campaign_root=campaign_root,
            output_root=tmp_path / "evaluated",
        )
