"""Fail-closed evaluator for an unusable AVFoundation localization campaign.

This module is deliberately separate from ``avfoundation_source_localization``:
the completed campaign binds that runner byte-for-byte.  Changing the runner
after execution would invalidate the raw evidence.  This evaluator can only
seal a campaign in which every frozen attempt failed before source measurement
or D405 lifecycle treatment began.  It cannot score a successful campaign.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_source_localization import (
    AVFoundationLocalizationError,
    CAMPAIGN_SCHEMA,
    EVALUATION_SCHEMA,
    EXPECTED_TRIAL_ORDER,
    RECEIPT_SCHEMA,
    _canonical_digest,
    _load_trial,
    _sha256_file,
    _write_json,
    load_source_localization_contract,
    parse_orchestration_events,
    parse_source_events,
)


EXPECTED_BUDGET = {
    "required_trials": 12,
    "used_trials": 12,
    "control_trials": 6,
    "treatment_trials": 6,
    "replacement_trials_allowed": 0,
    "replacement_trials_used": 0,
    "robot_motion_trials": 0,
    "provider_calls": 0,
}


def _load_campaign(path: Path) -> dict[str, Any]:
    try:
        campaign = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationLocalizationError(
            f"Could not load campaign: {error}"
        ) from error
    if not isinstance(campaign, dict):
        raise AVFoundationLocalizationError("Campaign is not an object.")
    return campaign


def seal_source_localization_prerequisite_abstention(
    *,
    contract_path: Path,
    campaign_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify immutable failed attempts and emit a deterministic abstention."""

    contract = load_source_localization_contract(contract_path)
    if output_root.exists():
        raise AVFoundationLocalizationError(
            "Evaluation output already exists; replay/substitution is forbidden."
        )
    campaign_path = campaign_root / "campaign.json"
    campaign = _load_campaign(campaign_path)
    contract_sha256 = _sha256_file(contract_path)
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA:
        raise AVFoundationLocalizationError("Campaign schema changed.")
    if campaign.get("contract_sha256") != contract_sha256:
        raise AVFoundationLocalizationError("Campaign contract identity changed.")
    if campaign.get("authority") != contract["authority"]:
        raise AVFoundationLocalizationError("Campaign authority changed.")
    if campaign.get("budget") != EXPECTED_BUDGET:
        raise AVFoundationLocalizationError("Campaign budget changed.")

    entries = campaign.get("trials")
    if not isinstance(entries, list) or len(entries) != 12:
        raise AVFoundationLocalizationError("Campaign must contain exactly 12 trials.")
    observed_ids = [entry.get("trial_id") for entry in entries]
    if observed_ids != EXPECTED_TRIAL_ORDER or len(set(observed_ids)) != 12:
        raise AVFoundationLocalizationError("Campaign trial order or uniqueness changed.")

    runtime = campaign.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise AVFoundationLocalizationError("Campaign runtime identity is missing.")
    binary_relative = runtime.get("source_probe_binary_path")
    if (
        not isinstance(binary_relative, str)
        or binary_relative.startswith("/")
        or ".." in binary_relative
    ):
        raise AVFoundationLocalizationError("Unsafe source-probe binary path.")
    binary_path = campaign_root / binary_relative
    if (
        not binary_path.is_file()
        or _sha256_file(binary_path) != runtime.get("source_probe_binary_sha256")
    ):
        raise AVFoundationLocalizationError("Source-probe binary identity changed.")
    source_path = Path(contract["runtime_identity"]["swift_source_path"])
    runner_path = Path(contract["runtime_identity"]["python_runner_path"])
    if (
        not source_path.is_file()
        or _sha256_file(source_path) != runtime.get("swift_source_sha256")
        or not runner_path.is_file()
        or _sha256_file(runner_path) != runtime.get("python_runner_sha256")
    ):
        raise AVFoundationLocalizationError("Source or runner identity changed.")

    rows: list[dict[str, Any]] = []
    failure_signatures: Counter[str] = Counter()
    source_sample_count = 0
    session_started_count = 0
    d405_lifecycle_started_count = 0
    for entry in entries:
        trial = _load_trial(campaign_root, entry)
        trial_root = campaign_root / "trials" / trial["trial_id"]
        source_events = parse_source_events(
            trial_root / trial["source_event_path"]
        )
        orchestration_events = parse_orchestration_events(
            trial_root / trial["orchestration_event_path"]
        )
        event_types = [str(event["event_type"]) for event in source_events]
        orchestration_types = [
            str(event["event_type"]) for event in orchestration_events
        ]
        if not event_types or event_types[0] != "probe_started":
            raise AVFoundationLocalizationError(
                f"Trial {trial['trial_id']} lacks probe_started."
            )
        if (
            orchestration_types[0] != "trial_started"
            or orchestration_types[-1] != "trial_finished"
        ):
            raise AVFoundationLocalizationError(
                f"Trial {trial['trial_id']} orchestration boundaries changed."
            )

        return_code = trial.get("source_probe_return_code")
        trial_error = trial.get("trial_error")
        if (
            not isinstance(return_code, int)
            or return_code == 0
            or not isinstance(trial_error, str)
            or not trial_error
        ):
            raise AVFoundationLocalizationError(
                "Abstention sealer requires every trial to have a recorded "
                "non-zero source-probe failure."
            )
        started = orchestration_events[0]
        finished = orchestration_events[-1]
        if (
            started.get("trial_id") not in {None, trial["trial_id"]}
            or started.get("cell") not in {None, trial["cell"]}
            or finished.get("trial_id") not in {None, trial["trial_id"]}
            or finished.get("cell") not in {None, trial["cell"]}
            or finished.get("source_probe_return_code") not in {None, return_code}
            or finished.get("trial_error") not in {None, trial_error}
        ):
            raise AVFoundationLocalizationError(
                f"Trial {trial['trial_id']} orchestration identity changed."
            )
        if trial.get("d405_report_path") is not None:
            raise AVFoundationLocalizationError(
                "Abstention sealer cannot classify a trial with a D405 report."
            )
        if any(
            event_type in {"sample_output", "sample_dropped"}
            for event_type in event_types
        ):
            raise AVFoundationLocalizationError(
                "Abstention sealer cannot discard observed source samples."
            )
        if any(
            event_type.startswith("lifecycle_")
            for event_type in orchestration_types
        ):
            raise AVFoundationLocalizationError(
                "Abstention sealer cannot discard an executed D405 lifecycle."
            )

        source_sample_count += sum(
            event_type in {"sample_output", "sample_dropped"}
            for event_type in event_types
        )
        session_started_count += event_types.count("session_start_returned")
        d405_lifecycle_started_count += orchestration_types.count(
            "lifecycle_start_requested"
        )
        stderr_path = trial_root / "source_probe.stderr.log"
        try:
            failure_signature = stderr_path.read_text(
                encoding="utf-8"
            ).strip()
        except OSError as error:
            raise AVFoundationLocalizationError(
                f"Could not read trial stderr: {error}"
            ) from error
        if not failure_signature:
            failure_signature = "stderr_empty"
        failure_signatures[failure_signature] += 1
        rows.append(
            {
                "trial_id": trial["trial_id"],
                "cell": trial["cell"],
                "complete": False,
                "source": None,
                "source_unavailable_reason": trial_error,
                "source_probe_return_code": return_code,
                "observed_source_event_types": event_types,
                "observed_orchestration_event_types": orchestration_types,
                "failure_signature": failure_signature,
            }
        )

    evaluator_path = Path(__file__)
    source_probe = contract["cameras"]["source_probe"]
    exact_format_failure = (
        failure_signatures
        == {"AVFoundationSourceProbe: requested_format_unavailable": len(rows)}
    )
    missing_prerequisite = (
        f"An exact {source_probe['name']} AVFoundation format matching the "
        f"preregistered {source_probe['width']}x{source_probe['height']}@"
        f"{source_probe['fps']} request was unavailable to the source probe."
        if exact_format_failure
        else "Every source probe failed before session startup; no source "
        "continuity measurement or D405 lifecycle treatment was executed."
    )
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha256,
        "campaign_sha256": _sha256_file(campaign_path),
        "abstention_evaluator_sha256": _sha256_file(evaluator_path),
        "proof_class": "camera_source_lifecycle_localization",
        "verdict": "prerequisite_abstention",
        "campaign_attempt_count": len(rows),
        "control_attempt_count": sum(row["cell"] == "C" for row in rows),
        "treatment_attempt_count": sum(row["cell"] == "T" for row in rows),
        "usable_measurement_trial_count": 0,
        "incomplete_trial_count": len(rows),
        "source_sample_or_drop_count": source_sample_count,
        "session_start_returned_count": session_started_count,
        "d405_lifecycle_started_count": d405_lifecycle_started_count,
        "failure_signature_counts": dict(sorted(failure_signatures.items())),
        "missing_prerequisite": missing_prerequisite,
        "trials": rows,
        "claim_limits": {
            "source_continuity_measured": False,
            "physical_exposure_continuity": False,
            "cross_camera_exposure_synchronization": False,
            "metric_depth": False,
            "motion_capture_reliability": False,
            "simulator_calibration": False,
            "task_success": False,
            "sealed_container_result_reclassified": False,
        },
    }

    raw_artifacts: dict[str, str] = {}
    for path in sorted(campaign_root.rglob("*")):
        if path.is_file():
            raw_artifacts[path.relative_to(campaign_root).as_posix()] = _sha256_file(
                path
            )
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": contract_sha256,
        "campaign_sha256": _sha256_file(campaign_path),
        "abstention_evaluator_sha256": _sha256_file(evaluator_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": "camera_source_lifecycle_localization",
        "verdict": "prerequisite_abstention",
        "budget": EXPECTED_BUDGET,
        "raw_artifact_sha256": raw_artifacts,
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
