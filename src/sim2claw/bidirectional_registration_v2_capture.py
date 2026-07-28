"""Review and execute the v2 no-contact RGB registration acquisition."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np
from PIL import Image

from .bidirectional_registration_v2_route import (
    compile_exact_route,
    load_route,
)
from .learning_factory_artifacts import sha256_file
from .paths import REPO_ROOT
from .replay_eligibility import action_sha256
from .wrist_view_reposition import (
    _identity_and_limits,
    _joint_delta,
    _validated_gateway_actual,
)


PACKET_SCHEMA = "sim2claw.bidirectional_pawn_push_v2_registration_capture.v1"
REVIEW_SCHEMA = (
    "sim2claw.bidirectional_pawn_push_v2_registration_capture_review.v1"
)
EXECUTION_SCHEMA = (
    "sim2claw.bidirectional_pawn_push_v2_registration_capture_execution.v1"
)
DEFAULT_PACKET = (
    REPO_ROOT
    / "configs/hardware/"
    "bidirectional_pawn_push_v2_registration_capture_v1.json"
)


class RegistrationCaptureV2Error(RuntimeError):
    """The prospective capture review or guarded registration motion failed."""


class Recorder(Protocol):
    process: Any

    def start(self) -> dict[str, Any]: ...
    def finish(self) -> dict[str, Any]: ...


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistrationCaptureV2Error(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistrationCaptureV2Error(
            f"cannot read JSON {path}: {error}"
        ) from error
    _require(isinstance(value, dict), f"expected object in {path}")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _bound(binding: Mapping[str, Any], hash_key: str = "sha256") -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "bound path escaped repository",
    )
    path = (REPO_ROOT / relative).resolve()
    _require(
        path.is_file() and sha256_file(path) == binding.get(hash_key),
        f"bound source changed: {relative}",
    )
    return path


def load_packet(
    path: Path = DEFAULT_PACKET,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    path = path.resolve()
    packet = _json(path)
    _require(packet.get("schema_version") == PACKET_SCHEMA, "packet schema changed")
    _require(
        packet.get("status") == "frozen_before_registration_motion",
        "packet status widened",
    )
    authority = packet.get("authority") or {}
    _require(
        authority.get("owner_authorized_agent_controlled_rgb_observation") is True
        and authority.get(
            "owner_authorized_reviewed_no_contact_registration_motion"
        )
        is True
        and authority.get("registration_motion_requires_pre_motion_reviewer_continue")
        is True
        and not any(
            authority.get(key)
            for key in (
                "counted_task_action",
                "pawn_contact",
                "policy_evidence",
                "task_success",
                "transfer",
                "training",
            )
        ),
        "packet authority is absent or overbroad",
    )
    acquisition_path = _bound(packet["acquisition_contract"])
    route_path = _bound(packet["route_contract"])
    acquisition = _json(acquisition_path)
    route, route_acquisition, route_acquisition_path = load_route(route_path)
    _require(
        route_acquisition_path == acquisition_path
        and route_acquisition == acquisition,
        "route/acquisition binding changed",
    )
    return packet, acquisition, route, route_path


def _load_array(binding: Mapping[str, Any]) -> tuple[Path, np.ndarray]:
    path = _bound(binding, "npy_sha256")
    try:
        values = np.asarray(
            np.load(path, allow_pickle=False), dtype="<f8", order="C"
        )
    except (OSError, TypeError, ValueError) as error:
        raise RegistrationCaptureV2Error(
            f"cannot load frozen setup array {path}: {error}"
        ) from error
    _require(
        values.shape == tuple(binding["shape"])
        and values.dtype == np.dtype("<f8")
        and np.all(np.isfinite(values))
        and action_sha256(values) == binding["action_sha256"],
        f"frozen setup array changed: {path}",
    )
    return path, values


def _validate_static_receipt(
    packet: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    binding = packet.get("static_receipt") or packet["v02_static_receipt"]
    path = _bound(binding)
    receipt = _json(path)
    _require(
        receipt.get("reviewer", {}).get("decision")
        == binding["required_reviewer_decision"]
        and receipt.get("reviewer", {}).get("evidence_anchor")
        == binding["required_evidence_anchor"]
        and receipt.get("gates")
        and all(receipt["gates"].values())
        and receipt.get("physical_motion_commanded") is False
        and receipt.get("camera_opened") is False
        and receipt.get("gateway_constructed") is False,
        "static route authority did not pass or widened",
    )
    return path, receipt


def _validated_start_bridge(
    packet: Mapping[str, Any],
    safety: Mapping[str, Any],
) -> dict[str, Any]:
    bridge = packet.get("live_rebase_setup_bridge")
    if bridge is None:
        return {
            "bridge_id": "legacy_no_bridge",
            "pattern": "none",
            "duration_seconds": 0.0,
            "command_count": 0,
            "excluded_from_policy_task_and_transfer_evidence": True,
        }
    interval = 1.0 / float(safety["sample_hz"])
    _require(
        bridge.get("bridge_id")
        == "v04_acquisition_v2_time_only_pre_row_bridge_v1"
        and bridge.get("pattern") == "time_only_pre_row_bridge"
        and float(bridge.get("duration_seconds", -1.0)) == interval
        and int(bridge.get("command_count", -1)) == 0
        and bridge.get("first_frozen_row_elapsed_seconds") == interval
        and bridge.get("maximum_live_rebase_delta_degrees")
        == safety["fresh_start_maximum_absolute_delta_degrees"]
        and bridge.get("maximum_post_hold_to_first_row_delta_degrees")
        == 3.0
        and bridge.get("sends_no_command") is True
        and bridge.get("changes_frozen_arrays") is False
        and bridge.get("excluded_from_policy_task_and_transfer_evidence") is True,
        "live rebase setup bridge changed or widened",
    )
    return dict(bridge)


def _default_preflight() -> dict[str, Any]:
    from .teleop_recording import physical_excitation_follower_preflight

    return physical_excitation_follower_preflight()


def _default_gateway(identity: Mapping[str, Any]) -> Any:
    from .physical_canary import _default_gateway as make_gateway
    from .physical_canary import _gateway_identity

    return make_gateway(_gateway_identity(identity))


def _default_recorder(
    output_root: Path,
    *,
    contract: Mapping[str, Any],
    camera_session_token: str,
    fixed_mount_token: str,
) -> Recorder:
    from .c922_terminal_hold_capture import NativeC922StillRecorder

    return NativeC922StillRecorder(
        output_root,
        contract=contract,
        camera_session_token=camera_session_token,
        fixed_mount_token=fixed_mount_token,
    )


def review_capture_plan(
    *,
    packet_path: Path = DEFAULT_PACKET,
    review_path: Path,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Emit the final deterministic, motion-free capture reviewer decision."""

    packet, acquisition, route, _ = load_packet(packet_path)
    static_path, static = _validate_static_receipt(packet)
    preflight = (preflight_fn or _default_preflight)()
    identity, start, lower, upper = _identity_and_limits(preflight)
    expected_start = np.asarray(
        route["source_rebase"]["expected_degrees_percent"],
        dtype=np.float64,
    )
    _require(
        float(np.max(np.abs(start - expected_start)))
        <= float(route["source_rebase"]["maximum_absolute_delta_degrees"]),
        "fresh start differs from the frozen rebase envelope",
    )
    compiled = compile_exact_route(route, acquisition)
    egress_path, egress = _load_array(
        packet["exact_setup_arrays"]["source_egress"]
    )
    main_path, main = _load_array(
        packet["exact_setup_arrays"]["capture_and_return"]
    )
    _require(
        np.array_equal(egress, compiled["egress"])
        and np.array_equal(main, compiled["main"])
        and static["source_egress"]["action_sha256"] == action_sha256(egress)
        and static["capture_and_return"]["action_sha256"] == action_sha256(main),
        "frozen setup arrays differ from fresh compile or V02 receipt",
    )
    camera_contract_path = _bound(
        packet["camera_transaction"]["capture_contract"]
    )
    camera_source_path = _bound(
        packet["camera_transaction"]["capture_source"]
    )
    camera_contract = _json(camera_contract_path)
    _require(
        camera_contract.get("status") == "preregistered_before_capture_or_motion"
        and camera_contract.get("camera", {}).get("role") == "c922"
        and camera_contract.get("selection", {}).get("maximum_ring_frames") == 180,
        "C922 capture contract changed",
    )
    safety = packet["tracking_and_safety"]
    start_bridge = _validated_start_bridge(packet, safety)
    hold_mode = str(safety.get("hold_gate_mode", "legacy_sample_tail_v1"))
    true_time_hold_gate_bound = True
    if hold_mode == "monotonic_true_time_v1":
        hold_rows = int(route["compile"]["stationary_hold_samples_per_target"])
        true_time_hold_gate_bound = bool(
            safety.get("reset_deadline_on_camera_start") is True
            and int(safety["hold_maximum_rows"]) == hold_rows
            and float(safety["hold_minimum_unscored_settle_seconds"]) >= 0.5
            and float(safety["hold_scoring_seconds"]) >= 2.0
            and float(safety["hold_maximum_monotonic_seconds"])
            >= (
                float(safety["hold_minimum_unscored_settle_seconds"])
                + float(safety["hold_scoring_seconds"])
            )
            and all(
                int(item["sample_count"]) == hold_rows
                for item in compiled["capture_slices"]
            )
        )
    _require(
        compiled["sample_hz"] == safety["sample_hz"]
        and np.all(egress >= lower)
        and np.all(egress <= upper)
        and np.all(main >= lower)
        and np.all(main <= upper)
        and len(compiled["capture_slices"])
        == sum(
            len(acquisition["split"][name])
            for name in ("fit_targets", "heldout_targets")
        )
        and safety["torque_off_every_exit"] is True
        and safety["pawn_contact_forbidden"] is True
        and true_time_hold_gate_bound,
        "fresh pre-motion safety binding failed",
    )
    review = {
        "schema_version": REVIEW_SCHEMA,
        "status": "completed_before_registration_motion",
        "proof_class": "motion_free_registration_capture_review_only",
        "packet_path": str(packet_path.resolve()),
        "packet_sha256": sha256_file(packet_path.resolve()),
        "hardware_identity": identity,
        "fresh_follower_start_degrees": start.tolist(),
        "fresh_calibrated_minimum": lower.tolist(),
        "fresh_calibrated_maximum": upper.tolist(),
        "static_receipt_path": str(static_path),
        "static_receipt_sha256": sha256_file(static_path),
        "exact_setup_arrays": {
            "source_egress": {
                "path": str(egress_path),
                "npy_sha256": sha256_file(egress_path),
                "action_sha256": action_sha256(egress),
                "shape": list(egress.shape),
            },
            "capture_and_return": {
                "path": str(main_path),
                "npy_sha256": sha256_file(main_path),
                "action_sha256": action_sha256(main),
                "shape": list(main.shape),
            },
        },
        "capture_slices": compiled["capture_slices"],
        "live_rebase_setup_bridge": start_bridge,
        "camera_contract_path": str(camera_contract_path),
        "camera_contract_sha256": sha256_file(camera_contract_path),
        "camera_source_path": str(camera_source_path),
        "camera_source_sha256": sha256_file(camera_source_path),
        "gates": {
            "fresh_torque_off_preflight": True,
            "fresh_start_inside_frozen_rebase": True,
            "static_reviewer_continue": True,
            "all_static_gates": True,
            "exact_arrays_match_fresh_compile": True,
            "exact_arrays_match_v02_receipt": True,
            "fresh_joint_limits": True,
            "capture_slice_count_matches_frozen_split": True,
            "camera_contract_and_source_bound": True,
            "camera_before_motion_contract": True,
            "live_rebase_setup_bridge_bound": True,
            "true_time_hold_gate_bound": true_time_hold_gate_bound,
            "torque_off_every_exit_contract": True,
            "no_task_or_pawn_contact_authority": True,
        },
        "reviewer": {
            "kind": packet["pre_motion_review"]["reviewer_kind"],
            "decision": "CONTINUE",
            "evidence_anchor": 100,
        },
        "physical_motion_commanded": False,
        "camera_opened": False,
        "gateway_constructed": False,
        "counted_physical_attempts": 0,
    }
    _require(all(review["gates"].values()), "pre-motion reviewer gates failed")
    _write_once(review_path.resolve(), review)
    return {
        **review,
        "review_path": str(review_path.resolve()),
        "review_sha256": sha256_file(review_path.resolve()),
    }


def _validate_review(
    review_path: Path,
    packet_path: Path,
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    review_path = review_path.resolve()
    review = _json(review_path)
    _require(
        review.get("schema_version") == REVIEW_SCHEMA
        and review.get("status") == "completed_before_registration_motion"
        and review.get("packet_sha256") == sha256_file(packet_path.resolve())
        and review.get("reviewer", {}).get("decision")
        == packet["pre_motion_review"]["required_decision"]
        and review.get("gates")
        and all(review["gates"].values())
        and review.get("physical_motion_commanded") is False
        and review.get("camera_opened") is False
        and review.get("gateway_constructed") is False,
        "pre-motion capture review did not admit execution",
    )
    return review


def _camera_process_running(recorder: Recorder) -> bool:
    process = getattr(recorder, "process", None)
    return process is not None and process.poll() is None


def _validate_camera_record(
    value: Mapping[str, Any],
    contract: Mapping[str, Any],
    token: str,
    mount: str,
) -> None:
    camera = contract["camera"]
    expected = {
        "cameraName": camera["localized_name"],
        "cameraUniqueID": camera["unique_id"],
        "cameraModelID": camera["model_id"],
        "width": camera["width"],
        "height": camera["height"],
        "mediaSubtype": camera["media_subtype_fourcc"],
        "pixelFormat": camera["media_subtype_fourcc"],
        "cameraSessionToken": token,
        "fixedMountToken": mount,
    }
    _require(
        all(value.get(key) == expected_value for key, expected_value in expected.items()),
        "C922 identity, exact mode, or fixed-mount token changed",
    )


def _finish_target_camera(
    *,
    recorder: Recorder,
    started: Mapping[str, Any],
    output_root: Path,
    camera_root: Path,
    contract: Mapping[str, Any],
    token: str,
    mount: str,
    target_id: str,
    opaque_id: str,
    split: str,
    hold_records: list[dict[str, Any]],
    safety: Mapping[str, Any],
) -> dict[str, Any]:
    finished = recorder.finish()
    _validate_camera_record(started, contract, token, mount)
    _validate_camera_record(finished, contract, token, mount)
    _require(
        finished.get("status") == "completed"
        and finished.get("droppedCallbackCount") == 0,
        "C922 target capture did not close without drops",
    )
    maximum_tracking_error = float(
        safety["joint_hold_tracking_maximum_degrees"]
    )
    scoring, scoring_metadata = _scoring_window(
        hold_records,
        safety=safety,
    )
    first_ns = int(scoring[0]["host_continuous_ns"])
    last_ns = int(scoring[-1]["host_continuous_ns"])
    _require(
        last_ns > first_ns
        and max(
            max(abs(value) for value in row["tracking_error"])
            for row in scoring
        )
        <= maximum_tracking_error,
        "target hold did not meet the frozen two-second tracking gate",
    )
    ledger_path = Path(str(finished["ledger_path"]))
    _require(
        ledger_path.is_file()
        and sha256_file(ledger_path) == finished["ledger_sha256"],
        "C922 callback ledger changed",
    )
    events = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
    ]
    candidates = [
        event
        for event in events
        if first_ns <= int(event.get("hostContinuousNS", -1)) <= last_ns
    ]
    _require(candidates, "no retained C922 frame overlaps the scored hold")
    midpoint = (first_ns + last_ns) // 2
    selected = min(
        candidates,
        key=lambda event: abs(int(event["hostContinuousNS"]) - midpoint),
    )
    _validate_camera_record(selected, contract, token, mount)
    source = camera_root / str(selected["pngPath"])
    _require(
        source.is_file() and sha256_file(source) == selected["pngSHA256"],
        "selected C922 frame changed",
    )
    with Image.open(source) as image:
        _require(
            image.format == "PNG" and image.size == (640, 480),
            "selected target frame is not exact-mode PNG",
        )
    target_root = (
        output_root / "fit" / target_id
        if split == "fit"
        else output_root / "heldout-sealed" / opaque_id
    )
    target_root.mkdir(parents=True, exist_ok=False)
    selected_path = target_root / "selected.png"
    shutil.copyfile(source, selected_path)
    selected_sha = sha256_file(selected_path)
    receipt = {
        "target_id": target_id,
        "opaque_id": opaque_id,
        "split": split,
        "camera_session_token": token,
        "camera_started": dict(started),
        "camera_finished": dict(finished),
        "camera_ledger_path": str(ledger_path),
        "camera_ledger_sha256": sha256_file(ledger_path),
        "selected_source_path": str(source),
        "selected_path": str(selected_path),
        "selected_sha256": selected_sha,
        "selected_bytes": selected_path.stat().st_size,
        "selected_sequence": selected["sequence"],
        "selected_host_continuous_ns": selected["hostContinuousNS"],
        "scored_hold_first_host_continuous_ns": first_ns,
        "scored_hold_last_host_continuous_ns": last_ns,
        "scored_hold_sample_count": len(scoring),
        **scoring_metadata,
        "maximum_absolute_tracking_error": max(
            max(abs(value) for value in row["tracking_error"])
            for row in scoring
        ),
    }
    receipt_path = target_root / "capture_receipt.json"
    _write_once(receipt_path, receipt)
    return {
        **receipt,
        "capture_receipt_path": str(receipt_path),
        "capture_receipt_sha256": sha256_file(receipt_path),
    }


def _maximum_tracking_error(record: Mapping[str, Any]) -> float:
    return max(abs(float(value)) for value in record["tracking_error"])


def _scoring_window(
    hold_records: list[dict[str, Any]],
    *,
    safety: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select a legacy row tail or a bounded authoritative monotonic window."""

    mode = str(safety.get("hold_gate_mode", "legacy_sample_tail_v1"))
    if mode == "legacy_sample_tail_v1":
        scoring = hold_records[-40:]
        _require(
            len(scoring) == 40,
            "target lacks the frozen two-second scoring tail",
        )
        return scoring, {
            "hold_gate_mode": mode,
            "unscored_settle_elapsed_seconds": None,
            "scored_hold_elapsed_seconds": (
                int(scoring[-1]["host_continuous_ns"])
                - int(scoring[0]["host_continuous_ns"])
            )
            / 1e9,
        }

    _require(
        mode == "monotonic_true_time_v1",
        "unknown registration hold gate mode",
    )
    maximum_rows = int(safety["hold_maximum_rows"])
    maximum_seconds = float(safety["hold_maximum_monotonic_seconds"])
    settle_seconds = float(safety["hold_minimum_unscored_settle_seconds"])
    scoring_seconds = float(safety["hold_scoring_seconds"])
    maximum_error = float(safety["joint_hold_tracking_maximum_degrees"])
    _require(
        2 <= len(hold_records) <= maximum_rows,
        "target exceeded the frozen true-time row bound",
    )
    first_ns = int(hold_records[0]["host_continuous_ns"])
    final_ns = int(hold_records[-1]["host_continuous_ns"])
    hold_elapsed = (final_ns - first_ns) / 1e9
    _require(
        0.0 < hold_elapsed <= maximum_seconds,
        "target exceeded the frozen true-time duration bound",
    )
    earliest_score_ns = first_ns + int(round(settle_seconds * 1e9))
    score_start_index = next(
        (
            index
            for index, record in enumerate(hold_records)
            if int(record["host_continuous_ns"]) >= earliest_score_ns
            and _maximum_tracking_error(record) <= maximum_error
        ),
        None,
    )
    _require(
        score_start_index is not None,
        "target never entered the unchanged tracking gate after true-time settle",
    )
    score_start_ns = int(
        hold_records[score_start_index]["host_continuous_ns"]
    )
    score_end_index = next(
        (
            index
            for index in range(score_start_index, len(hold_records))
            if (
                int(hold_records[index]["host_continuous_ns"])
                - score_start_ns
            )
            / 1e9
            >= scoring_seconds
        ),
        None,
    )
    _require(
        score_end_index is not None,
        "target lacks the frozen true-time scoring duration",
    )
    post_entry = hold_records[score_start_index:]
    _require(
        all(
            _maximum_tracking_error(record) <= maximum_error
            for record in post_entry
        ),
        "target left the unchanged tracking gate after scoring began",
    )
    scoring = hold_records[score_start_index : score_end_index + 1]
    score_elapsed = (
        int(scoring[-1]["host_continuous_ns"])
        - int(scoring[0]["host_continuous_ns"])
    ) / 1e9
    _require(
        score_elapsed >= scoring_seconds,
        "target true-time score window shortened",
    )
    return scoring, {
        "hold_gate_mode": mode,
        "hold_elapsed_seconds": hold_elapsed,
        "hold_maximum_rows": maximum_rows,
        "hold_maximum_monotonic_seconds": maximum_seconds,
        "unscored_settle_elapsed_seconds": (
            int(scoring[0]["host_continuous_ns"]) - first_ns
        )
        / 1e9,
        "required_unscored_settle_seconds": settle_seconds,
        "scored_hold_elapsed_seconds": score_elapsed,
        "required_scored_hold_seconds": scoring_seconds,
    }


def execute_registration_capture(
    *,
    packet_path: Path = DEFAULT_PACKET,
    review_path: Path,
    output_root: Path,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Mapping[str, Any]], Any] | None = None,
    recorder_factory: Callable[..., Recorder] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute one camera-enclosed registration transaction, then torque off."""

    _require(operator_acknowledged, "explicit v2 registration authority is required")
    packet_path = packet_path.resolve()
    packet, acquisition, route, _ = load_packet(packet_path)
    review = _validate_review(review_path, packet_path, packet)
    _validate_static_receipt(packet)
    preflight_provider = preflight_fn or _default_preflight
    preflight = preflight_provider()
    identity, start, lower, upper = _identity_and_limits(preflight)
    _require(
        identity == review["hardware_identity"],
        "hardware identity changed after V03 review",
    )
    expected_start = np.asarray(
        route["source_rebase"]["expected_degrees_percent"],
        dtype=np.float64,
    )
    _require(
        float(np.max(np.abs(start - expected_start)))
        <= float(route["source_rebase"]["maximum_absolute_delta_degrees"]),
        "fresh execution start differs from the frozen rebase envelope",
    )
    compiled = compile_exact_route(route, acquisition)
    _, egress = _load_array(packet["exact_setup_arrays"]["source_egress"])
    _, main = _load_array(packet["exact_setup_arrays"]["capture_and_return"])
    _require(
        np.array_equal(egress, compiled["egress"])
        and np.array_equal(main, compiled["main"])
        and np.all(egress >= lower)
        and np.all(egress <= upper)
        and np.all(main >= lower)
        and np.all(main <= upper),
        "fresh execution arrays changed or exceed limits",
    )
    output_root = output_root.resolve()
    _require(not output_root.exists(), "refusing to overwrite capture execution")
    output_root.mkdir(parents=True)
    telemetry_path = output_root / "joint_samples.jsonl"
    telemetry_path.open("x").close()
    receipt_path = output_root / "execution_receipt.json"
    camera_contract_path = _bound(
        packet["camera_transaction"]["capture_contract"]
    )
    camera_contract = _json(camera_contract_path)
    camera_spec = packet["camera_transaction"]
    safety = packet["tracking_and_safety"]
    start_bridge = _validated_start_bridge(packet, safety)
    sample_hz = int(safety["sample_hz"])
    interval = 1.0 / sample_hz
    target_split = {
        item["target_id"]: "fit"
        for item in acquisition["split"]["fit_targets"]
    }
    target_split.update(
        {
            item["target_id"]: "heldout"
            for item in acquisition["split"]["heldout_targets"]
        }
    )
    heldout_ids = {
        item["target_id"]: str(
            item.get("opaque_id") or f"heldout-{index:02d}"
        )
        for index, item in enumerate(
            acquisition["split"]["heldout_targets"],
            start=1,
        )
    }
    recorder_builder = recorder_factory or _default_recorder
    gateway_builder = gateway_factory or _default_gateway
    gateway: Any | None = None
    active_recorder: Recorder | None = None
    active_started: dict[str, Any] | None = None
    active_camera_root: Path | None = None
    active_token: str | None = None
    camera_records: list[dict[str, Any]] = []
    target_records: list[dict[str, Any]] = []
    executed_egress: list[np.ndarray] = []
    executed_main: list[np.ndarray] = []
    main_records: dict[int, dict[str, Any]] = {}
    global_sample = 0
    physical_motion_commanded = False
    gateway_opened = False
    error: Exception | None = None
    final_preflight: dict[str, Any] | None = None
    started_wall = clock_fn()
    motion_epoch: float | None = None
    next_deadline: float | None = None
    start_bridge_receipt: dict[str, Any] = {
        **start_bridge,
        "actual_duration_seconds": 0.0,
        "actual_command_count": 0,
        "post_hold_to_first_row_maximum_delta_degrees": None,
    }

    def start_camera(label: str) -> None:
        nonlocal active_recorder, active_started, active_camera_root, active_token
        nonlocal next_deadline
        _require(active_recorder is None, "overlapping C922 owner sessions")
        active_camera_root = output_root / "camera-sessions" / label
        active_token = (
            f"{camera_spec['camera_session_prefix']}-{label}"
        )
        active_recorder = recorder_builder(
            active_camera_root,
            contract=camera_contract,
            camera_session_token=active_token,
            fixed_mount_token=camera_spec["fixed_mount_token"],
        )
        active_started = active_recorder.start()
        _validate_camera_record(
            active_started,
            camera_contract,
            active_token,
            camera_spec["fixed_mount_token"],
        )
        _require(
            _camera_process_running(active_recorder),
            "C922 source owner is not running",
        )
        if safety.get("reset_deadline_on_camera_start") is True:
            next_deadline = None

    def finish_non_target_camera(label: str) -> None:
        nonlocal active_recorder, active_started, active_camera_root, active_token
        _require(
            active_recorder is not None
            and active_started is not None
            and active_camera_root is not None
            and active_token is not None,
            "no active C922 owner to finish",
        )
        finished = active_recorder.finish()
        _validate_camera_record(
            finished,
            camera_contract,
            active_token,
            camera_spec["fixed_mount_token"],
        )
        _require(
            finished.get("status") == "completed"
            and finished.get("droppedCallbackCount") == 0,
            "C922 enclosure session failed",
        )
        camera_records.append(
            {
                "label": label,
                "target_capture": False,
                "started": active_started,
                "finished": finished,
            }
        )
        active_recorder = None
        active_started = None
        active_camera_root = None
        active_token = None

    def send_row(
        array_id: str,
        row_index: int,
        target: np.ndarray,
    ) -> dict[str, Any]:
        nonlocal global_sample, physical_motion_commanded, next_deadline
        _require(
            gateway is not None
            and active_recorder is not None
            and _camera_process_running(active_recorder),
            "gateway row lacks a live C922 owner",
        )
        if next_deadline is None:
            next_deadline = clock_fn()
        elif global_sample > 0:
            next_deadline += interval
            delay = next_deadline - clock_fn()
            if delay > 0.0:
                sleep_fn(delay)
        _require(_camera_process_running(active_recorder), "C922 exited before row")
        elapsed = max(0.0, clock_fn() - float(motion_epoch))
        sample = gateway.sample(
            elapsed,
            exact_requested_degrees=np.asarray(target, dtype="<f8"),
        )
        actual = _validated_gateway_actual(
            sample,
            np.asarray(target, dtype="<f8"),
            phase="registration",
        )
        requested = np.asarray(sample["follower_requested_degrees"], dtype="<f8")
        sent = np.asarray(sample["follower_command_degrees"], dtype="<f8")
        _require(
            requested.tobytes() == target.tobytes()
            and sent.tobytes() == target.tobytes(),
            "requested/mapped/sent bytes differ",
        )
        error_values = _joint_delta(actual, target)
        record = {
            "global_sample_index": global_sample,
            "array_id": array_id,
            "array_row_index": row_index,
            "host_continuous_ns": int(round(clock_fn() * 1e9)),
            "elapsed_seconds": elapsed,
            "requested_physical_units": target.tolist(),
            "mapped_physical_units": target.tolist(),
            "sent_physical_units": target.tolist(),
            "actual_physical_units": actual.tolist(),
            "tracking_error": error_values.tolist(),
            **sample,
        }
        with telemetry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        global_sample += 1
        physical_motion_commanded = True
        return record

    try:
        start_camera("target-01")
        gateway = gateway_builder(identity)
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        gateway_opened = True
        _require(
            np.max(
                np.abs(
                    _joint_delta(
                        np.asarray(opened["follower_start_degrees"]),
                        start,
                    )
                )
            )
            <= float(safety["fresh_start_maximum_absolute_delta_degrees"])
            and opened.get("device_configuration_rewritten") is False
            and opened.get("physical_follower_torque_enabled") is True,
            "gateway start or configuration changed after camera readiness",
        )
        post_hold_start = np.asarray(
            opened.get("follower_registration_degrees")
            or opened["follower_start_degrees"],
            dtype=np.float64,
        )
        post_hold_to_first = float(
            np.max(np.abs(_joint_delta(post_hold_start, egress[0])))
        )
        _require(
            post_hold_to_first
            <= float(
                start_bridge.get(
                    "maximum_post_hold_to_first_row_delta_degrees",
                    0.0,
                )
            )
            if start_bridge["pattern"] == "time_only_pre_row_bridge"
            else post_hold_to_first <= 1e-12,
            "post-hold start exceeds the frozen time-only bridge envelope",
        )
        motion_epoch = clock_fn()
        bridge_started = motion_epoch
        sleep_fn(float(start_bridge["duration_seconds"]))
        bridge_finished = clock_fn()
        start_bridge_receipt = {
            **start_bridge,
            "actual_duration_seconds": bridge_finished - bridge_started,
            "actual_command_count": 0,
            "post_hold_to_first_row_maximum_delta_degrees": post_hold_to_first,
        }
        for row_index, target in enumerate(egress):
            send_row("source_egress", row_index, target)
            executed_egress.append(target.copy())

        slices = compiled["capture_slices"]
        slice_by_end = {
            int(item["end_index_exclusive"]) - 1: item for item in slices
        }
        next_slice_start = {
            int(slices[index - 1]["end_index_exclusive"]): index + 1
            for index in range(1, len(slices))
        }
        return_start = int(slices[-1]["end_index_exclusive"])
        for row_index, target in enumerate(main):
            if row_index in next_slice_start:
                start_camera(f"target-{next_slice_start[row_index]:02d}")
            elif row_index == return_start:
                start_camera("return")
            record = send_row("capture_and_return", row_index, target)
            executed_main.append(target.copy())
            main_records[row_index] = record
            if row_index in slice_by_end:
                item = slice_by_end[row_index]
                target_id = str(item["target_id"])
                hold = [
                    main_records[index]
                    for index in range(
                        int(item["start_index"]),
                        int(item["end_index_exclusive"]),
                    )
                ]
                _require(
                    active_recorder is not None
                    and active_started is not None
                    and active_camera_root is not None
                    and active_token is not None,
                    "target ended without active C922 owner",
                )
                split = target_split[target_id]
                opaque_id = (
                    target_id if split == "fit" else heldout_ids[target_id]
                )
                target_receipt = _finish_target_camera(
                    recorder=active_recorder,
                    started=active_started,
                    output_root=output_root,
                    camera_root=active_camera_root,
                    contract=camera_contract,
                    token=active_token,
                    mount=camera_spec["fixed_mount_token"],
                    target_id=target_id,
                    opaque_id=opaque_id,
                    split=split,
                    hold_records=hold,
                    safety=safety,
                )
                target_records.append(target_receipt)
                camera_records.append(
                    {
                        "label": f"target-{len(target_records):02d}",
                        "target_capture": True,
                        "target_id": target_id,
                        "opaque_id": opaque_id,
                        "split": split,
                        "started": active_started,
                        "finished": target_receipt["camera_finished"],
                    }
                )
                active_recorder = None
                active_started = None
                active_camera_root = None
                active_token = None
        finish_non_target_camera("return")
        _require(
            np.array_equal(np.asarray(executed_egress, dtype="<f8"), egress)
            and np.array_equal(np.asarray(executed_main, dtype="<f8"), main)
            and len(target_records) == len(slices),
            "executed registration rows or capture count changed",
        )
    except Exception as caught:
        error = caught
    finally:
        if active_recorder is not None:
            try:
                finished = active_recorder.finish()
                camera_records.append(
                    {
                        "label": active_token,
                        "target_capture": False,
                        "aborted": True,
                        "started": active_started,
                        "finished": finished,
                    }
                )
            except Exception as caught:
                error = error or caught
        if gateway is not None:
            try:
                gateway.close()
            except Exception as caught:
                error = error or caught
        try:
            final_preflight = preflight_provider()
            _identity_and_limits(final_preflight)
        except Exception as caught:
            error = error or caught

    fit_manifest = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_fit_capture_manifest.v1",
        "members": [
            {
                "target_id": row["target_id"],
                "image_path": row["selected_path"],
                "image_sha256": row["selected_sha256"],
                "image_bytes": row["selected_bytes"],
                "capture_receipt_path": row["capture_receipt_path"],
                "capture_receipt_sha256": row["capture_receipt_sha256"],
            }
            for row in target_records
            if row["split"] == "fit"
        ],
    }
    heldout_manifest = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_heldout_sealed_manifest.v1",
        "sealed": True,
        "members": [
            {
                "opaque_id": row["opaque_id"],
                "image_sha256": row["selected_sha256"],
                "image_bytes": row["selected_bytes"],
                "capture_receipt_sha256": row["capture_receipt_sha256"],
            }
            for row in target_records
            if row["split"] == "heldout"
        ],
    }
    fit_manifest_path = output_root / "fit_manifest.json"
    heldout_manifest_path = output_root / "heldout_sealed_manifest.json"
    _write_once(fit_manifest_path, fit_manifest)
    _write_once(heldout_manifest_path, heldout_manifest)
    torque_off = bool(
        final_preflight is not None
        and final_preflight.get("physical_follower_torque_enabled") is False
        and final_preflight.get("device_configuration_rewritten") is False
    )
    receipt = {
        "schema_version": EXECUTION_SCHEMA,
        "status": (
            "completed_no_contact_registration_capture"
            if error is None and torque_off
            else "stopped_safely"
        ),
        "proof_class": "physical_rgb_no_contact_registration_observation_only",
        "packet_path": str(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "review_path": str(review_path.resolve()),
        "review_sha256": sha256_file(review_path.resolve()),
        "hardware_identity": identity,
        "fresh_preflight_start_degrees": start.tolist(),
        "gateway_opened": gateway_opened,
        "physical_motion_commanded": physical_motion_commanded,
        "live_rebase_setup_bridge": start_bridge_receipt,
        "source_egress": {
            "planned_action_sha256": action_sha256(egress),
            "executed_action_sha256": (
                action_sha256(np.asarray(executed_egress, dtype="<f8"))
                if executed_egress
                else None
            ),
            "planned_sample_count": len(egress),
            "executed_sample_count": len(executed_egress),
        },
        "capture_and_return": {
            "planned_action_sha256": action_sha256(main),
            "executed_action_sha256": (
                action_sha256(np.asarray(executed_main, dtype="<f8"))
                if executed_main
                else None
            ),
            "planned_sample_count": len(main),
            "executed_sample_count": len(executed_main),
        },
        "joint_samples_path": str(telemetry_path),
        "joint_samples_sha256": sha256_file(telemetry_path),
        "camera_sessions": camera_records,
        "target_captures": target_records,
        "fit_manifest_path": str(fit_manifest_path),
        "fit_manifest_sha256": sha256_file(fit_manifest_path),
        "heldout_sealed_manifest_path": str(heldout_manifest_path),
        "heldout_sealed_manifest_sha256": sha256_file(heldout_manifest_path),
        "requested_mapped_sent_byte_identity": bool(
            len(executed_egress) == len(egress)
            and len(executed_main) == len(main)
        ),
        "all_target_scored_holds_pass_tracking": bool(
            len(target_records) == len(compiled["capture_slices"])
            and all(
                row["maximum_absolute_tracking_error"]
                <= float(safety["joint_hold_tracking_maximum_degrees"])
                for row in target_records
            )
        ),
        "camera_started_before_gateway_open": bool(camera_records),
        "camera_drop_count_total": sum(
            int((row.get("finished") or {}).get("droppedCallbackCount") or 0)
            for row in camera_records
        ),
        "final_preflight": final_preflight,
        "physical_follower_torque_enabled": (
            final_preflight.get("physical_follower_torque_enabled")
            if final_preflight is not None
            else None
        ),
        "torque_off_confirmed": torque_off,
        "pawn_contact_authorized": False,
        "counted_task_action": False,
        "counted_physical_attempts": 0,
        "error": str(error) if error is not None else None,
        "wall_duration_seconds": max(0.0, clock_fn() - started_wall),
    }
    _write_once(receipt_path, receipt)
    if error is not None or not torque_off:
        raise RegistrationCaptureV2Error(
            "V03 registration capture stopped with torque-off cleanup: "
            + (str(error) if error is not None else "final torque-off proof failed")
        ) from error
    return {
        **receipt,
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
    }
