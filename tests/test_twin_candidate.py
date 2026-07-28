from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.canary_contact_preflight import (
    CanaryContactError,
    DEFAULT_POLICY_PATH,
    evaluate_canary_contact_preflight,
)
from sim2claw.c922_exact_mode_calibration import (
    DISTORTION_SCHEMA,
    INTRINSICS_SCHEMA,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.recorded_replay import (
    ReplayContractError,
    canonical_json_sha256,
    sha256_file,
)
from sim2claw.replay_eligibility import action_sha256, audit_exact_replay_manifest
from sim2claw.twin_candidate import (
    CANARY_INPUT_SCHEMA,
    TIMING_ADMISSION_SCHEMA,
    TwinCandidateError,
    compose_twin_candidate_and_canary,
)
from sim2claw.workcell_registration import (
    BOARD_FIT_SCHEMA,
    TRANSFORM_SCHEMA,
    WORKSPACE_POSE_ID,
)


BASELINE = REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json"


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, object]:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    timing = [
        stage
        for stage in baseline["parameter_stages"]
        if stage["name"] == "timing_control"
    ][0]
    family = {
        "stage": "timing_control",
        "parameters": copy.deepcopy(timing["parameters"]),
        "excluded": ["geometry", "contact_object", "deadband", "friction", "load"],
    }
    family["digest"] = canonical_json_sha256(family)
    split = {
        "owner": "fixture-independent-evaluator",
        "unit": "whole_episode",
        "seed": "fixture",
        "assignments": {
            "fixture-train": "train",
            "fixture-validation": "validation",
            "fixture-held-out": "held_out",
        },
        "counts": {"train": 1, "validation": 1, "held_out": 1},
    }
    split["digest"] = canonical_json_sha256(split)
    robot = {
        "robot_id": "fixture-so101",
        "follower_port": "/dev/fixture-so101",
        "follower_calibration_sha256": "1" * 64,
        "gateway_schema": "sim2claw.so101_physical_gateway.v2",
    }
    p9 = {
        "schema_version": TIMING_ADMISSION_SCHEMA,
        "status": "synthetic_fixture_admitted",
        "proof_class": "synthetic_fixture",
        "source_fit": {"sha256": "2" * 64},
        "source_cohort": {"sha256": "3" * 64},
        "source_config": {
            "sha256": sha256_file(BASELINE),
            "config_id": baseline["config_id"],
        },
        "identity": {"robot": robot, "workspace_pose_id": WORKSPACE_POSE_ID},
        "candidate_family": family,
        "selected_parameters": {
            "command_latency_seconds": 0.04,
            "actuator_gain_scale": 1.1,
            "joint_damping_scale": 1.2,
        },
        "frozen_split": split,
        "action_identity": {
            "sha256_by_episode": {
                "fixture-train": "5" * 64,
                "fixture-validation": "6" * 64,
                "fixture-held-out": "7" * 64,
            },
            "byte_identical": True,
        },
        "held_out_replay": {
            "fit_or_selection_performed": False,
            "improvement_gate": {"passed": True},
        },
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": True,
        "evaluator_admission": False,
        "parameters_promoted": False,
        "physical_authority": False,
    }
    evaluator = {
        "name": "fixture-registration-evaluator",
        "version": "1",
        "executable_sha256": "8" * 64,
    }
    assignment = "9" * 64
    correspondences = "a" * 64
    thresholds = {
        "maximum_leave_one_out_board_rms_m": 0.0015,
        "maximum_annotator_disagreement_m": 0.0015,
        "maximum_leave_one_out_reprojection_rms_px": 2.0,
    }
    transform = {
        "schema_version": TRANSFORM_SCHEMA,
        "camera_id": "logitech-overhead",
        "workspace_pose_id": WORKSPACE_POSE_ID,
        "board_pose_id": "fixture-board",
        "transform_4x4": np.eye(4).tolist(),
        "transform_convention": {
            "matrix_direction": "workcell_from_camera",
            "camera_axes": "opencv_x_right_y_down_z_forward",
            "workcell_axes": {"handedness": "right_handed"},
            "composition": "workcell_from_board @ inverse(camera_from_board)",
        },
        "thresholds": thresholds,
        "assignment_digest": assignment,
        "input_hashes": {
            "source_frame_sha256": "b" * 64,
            "board_measurement_sha256": "c" * 64,
            "survey_sha256": "d" * 64,
            "camera_intrinsics_sha256": "e" * 64,
            "lens_distortion_sha256": "f" * 64,
            "correspondences_digest": correspondences,
        },
        "evaluator_identity": evaluator,
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": True,
        "physical_authority": False,
    }
    board = {
        "schema_version": BOARD_FIT_SCHEMA,
        "evaluation_method": "leave_one_out",
        "board_rms_m": 0.0002,
        "max_annotator_disagreement_m": 0.0003,
        "leave_one_out_reprojection_rms_px": 0.4,
        "point_ids": [f"point-{index}" for index in range(8)],
        "assignment_digest": assignment,
        "correspondences_digest": correspondences,
        "uncertainty_propagated": True,
        "evaluator_identity": evaluator,
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": True,
    }
    start = [-0.2232741, 0.655613, -0.5256741, 0.7046496, 1.964844, 0.45]
    identity = {
        "robot": robot,
        "camera_id": "logitech-overhead",
        "workspace_pose_id": WORKSPACE_POSE_ID,
        "board_pose_id": "fixture-board",
    }
    canary = {
        "schema_version": CANARY_INPUT_SCHEMA,
        "synthetic": True,
        "identity": identity,
        "initial_state": {
            "joint_position": start,
            "joint_velocity": [0.0] * 6,
            "joint_position_source": "measured",
            "joint_velocity_source": "measured",
            "measurement_id": "fixture-anchor",
            "measurement_sha256": "0" * 64,
        },
        "joint_limits": {
            "minimum": [-3.0] * 5 + [0.0],
            "maximum": [3.0] * 5 + [1.0],
            "unit": "radian",
            "source_id": "fixture-limits",
            "source_sha256": "1" * 64,
        },
    }
    paths = {}
    for name, value in (
        ("p9", p9),
        ("transform", transform),
        ("board", board),
        ("canary", canary),
    ):
        path = tmp_path / f"{name}.json"
        _write(path, value)
        paths[name] = path
    return {
        "paths": paths,
        "values": {"p9": p9, "transform": transform, "board": board, "canary": canary},
        "baseline": BASELINE,
    }


def _compose(fixture: dict[str, object], output: Path) -> dict[str, object]:
    paths = fixture["paths"]
    return compose_twin_candidate_and_canary(
        p9_admission_path=paths["p9"],
        p13_transform_path=paths["transform"],
        p13_board_fit_path=paths["board"],
        baseline_config_path=fixture["baseline"],
        canary_input_path=paths["canary"],
        output_directory=output,
        synthetic_fixture_mode=True,
    )


def _p16_evidence(
    fixture: dict[str, object],
    tmp_path: Path,
) -> dict[str, Path]:
    common = {
        "camera_id": "logitech-overhead",
        "evaluator_owned": True,
        "self_scored": False,
        "synthetic": True,
    }
    intrinsics_path = tmp_path / "p8-intrinsics.json"
    distortion_path = tmp_path / "p8-distortion.json"
    _write(
        intrinsics_path,
        {
            "schema_version": INTRINSICS_SCHEMA,
            **common,
            "camera_matrix": np.eye(3).tolist(),
        },
    )
    _write(
        distortion_path,
        {
            "schema_version": DISTORTION_SCHEMA,
            **common,
            "model": "fixture",
            "coefficients": [0.0] * 5,
        },
    )
    transform = fixture["values"]["transform"]
    transform["input_hashes"]["intrinsics_sha256"] = sha256_file(intrinsics_path)
    transform["input_hashes"]["distortion_sha256"] = sha256_file(distortion_path)
    _write(fixture["paths"]["transform"], transform)
    return {
        "p8_intrinsics_path": intrinsics_path,
        "p8_distortion_path": distortion_path,
        "p9_admission_path": fixture["paths"]["p9"],
        "p13_transform_path": fixture["paths"]["transform"],
        "p13_board_fit_path": fixture["paths"]["board"],
    }


def _clean_p16_fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, Path]]:
    fixture = _fixture(tmp_path)
    fixture["values"]["canary"]["initial_state"]["joint_position"] = [
        1.1908479727818317,
        0.02767843375388379,
        1.1267926077044281,
        -0.9730003915962206,
        0.41239521366234166,
        0.45,
    ]
    _write(fixture["paths"]["canary"], fixture["values"]["canary"])
    evidence = _p16_evidence(fixture, tmp_path)
    p15 = _compose(fixture, tmp_path / "p15")
    return fixture, p15, evidence


def test_valid_fixture_is_immutable_bounded_and_byte_identical(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before = BASELINE.read_bytes()
    result = _compose(fixture, tmp_path / "output")
    assert BASELINE.read_bytes() == before
    candidate = json.loads(Path(result["candidate_manifest_path"]).read_text())
    assert [row["field"] for row in candidate["applied_parameters"]] == [
        "command_latency_seconds",
        "actuator_gain_scale",
        "joint_damping_scale",
    ]
    assert candidate["unapplied_fields"][0]["field"] == "transform_4x4"
    canary_path = Path(result["canary_bundle_path"])
    canary = json.loads(canary_path.read_text())
    actions = np.asarray(canary["applied_actions"], dtype=np.float64)
    payload = base64.b64decode(canary["frozen_action_payload"]["base64"])
    assert hashlib.sha256(payload).hexdigest() == action_sha256(actions)
    assert canary["requested_actions"] == canary["applied_actions"]
    assert actions[0].tolist() == actions[-1].tolist()
    assert np.all(actions[:, 5] == actions[0, 5])
    assert canary["safety"]["maximum_velocity_radians_s"] <= canary["safety"][
        "velocity_bound_radians_s"
    ]
    assert canary["safety"]["maximum_acceleration_radians_s2"] <= canary["safety"][
        "acceleration_bound_radians_s2"
    ]
    assert audit_exact_replay_manifest(canary_path)["exact_replay_eligible"] is True
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    ("artifact", "mutation", "message"),
    [
        ("p9", lambda value: value.update(self_scored=True), "self-scored"),
        (
            "p9",
            lambda value: value.update(synthetic=False),
            "synthetic proof class",
        ),
        (
            "p9",
            lambda value: value["held_out_replay"]["improvement_gate"].update(passed=False),
            "held-out replay gate failed",
        ),
        (
            "p9",
            lambda value: value["source_config"].update(sha256="0" * 64),
            "source config hash or identity drifted",
        ),
        (
            "transform",
            lambda value: value.update(workspace_pose_id="wrong-workspace"),
            "workspace identity drifted",
        ),
        (
            "transform",
            lambda value: value.update(assignment_digest="0" * 64),
            "assignment lineage drifted",
        ),
    ],
)
def test_identity_hash_self_score_gate_and_order_fail_closed(
    tmp_path: Path, artifact: str, mutation, message: str
) -> None:
    fixture = _fixture(tmp_path)
    value = fixture["values"][artifact]
    mutation(value)
    _write(fixture["paths"][artifact], value)
    with pytest.raises(TwinCandidateError, match=message):
        _compose(fixture, tmp_path / "output")


def test_real_mode_rejects_synthetic_inputs(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    with pytest.raises(TwinCandidateError, match="synthetic proof class"):
        compose_twin_candidate_and_canary(
            p9_admission_path=paths["p9"],
            p13_transform_path=paths["transform"],
            p13_board_fit_path=paths["board"],
            baseline_config_path=fixture["baseline"],
            canary_input_path=paths["canary"],
            output_directory=tmp_path / "output",
            synthetic_fixture_mode=False,
        )


def test_unsupported_runtime_field_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    timing = [
        stage
        for stage in baseline["parameter_stages"]
        if stage["name"] == "timing_control"
    ][0]
    timing["parameters"][0]["target"] = "camera_latency_seconds"
    baseline_path = tmp_path / "unsupported-baseline.json"
    _write(baseline_path, baseline)
    fixture["baseline"] = baseline_path
    p9 = fixture["values"]["p9"]
    p9["candidate_family"]["parameters"] = copy.deepcopy(timing["parameters"])
    family = p9["candidate_family"]
    family["digest"] = canonical_json_sha256(
        {key: value for key, value in family.items() if key != "digest"}
    )
    _write(fixture["paths"]["p9"], p9)
    with pytest.raises(ReplayContractError, match="unsupported parameter target"):
        _compose(fixture, tmp_path / "output")


def test_family_ordering_drift_fails_even_with_recomputed_digest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    p9 = fixture["values"]["p9"]
    family = p9["candidate_family"]
    family["parameters"].reverse()
    family["digest"] = canonical_json_sha256(
        {key: value for key, value in family.items() if key != "digest"}
    )
    _write(fixture["paths"]["p9"], p9)
    with pytest.raises(TwinCandidateError, match="ordering drifted from baseline"):
        _compose(fixture, tmp_path / "output")


def test_preexisting_output_is_never_overwritten(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "candidate_manifest.json").write_text("occupied", encoding="utf-8")
    with pytest.raises(TwinCandidateError, match="refusing to overwrite"):
        _compose(fixture, output)


def test_native_step_contact_audit_passes_clean_frozen_motion(
    tmp_path: Path,
) -> None:
    before = BASELINE.read_bytes()
    _, p15, evidence = _clean_p16_fixture(tmp_path)
    receipt = evaluate_canary_contact_preflight(
        candidate_path=Path(p15["candidate_manifest_path"]),
        canary_path=Path(p15["canary_bundle_path"]),
        baseline_path=BASELINE,
        **evidence,
        policy_path=DEFAULT_POLICY_PATH,
        output_path=tmp_path / "contact-admission.json",
        synthetic_fixture_mode=True,
    )
    audit = receipt["native_contact_audit"]
    assert receipt["status"] == "synthetic_fixture_no_contact_passed"
    assert audit["native_step_count"] > 1
    assert audit["forbidden_contact_event_count"] == 0
    assert audit["first_forbidden_contact"] is None
    assert receipt["simulation_no_contact_admitted"] is False
    assert receipt["physical_authority"] is False
    assert receipt["stop_before_robot_gateway"] is True
    assert receipt["gateway_constructed"] is False
    assert BASELINE.read_bytes() == before


def test_native_step_contact_audit_detects_existing_scene_forbidden_contact(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    evidence = _p16_evidence(fixture, tmp_path)
    p15 = _compose(fixture, tmp_path / "p15")
    receipt = evaluate_canary_contact_preflight(
        candidate_path=Path(p15["candidate_manifest_path"]),
        canary_path=Path(p15["canary_bundle_path"]),
        baseline_path=BASELINE,
        **evidence,
        policy_path=DEFAULT_POLICY_PATH,
        output_path=tmp_path / "contact-admission.json",
        synthetic_fixture_mode=True,
    )
    event = receipt["native_contact_audit"]["first_forbidden_contact"]
    assert receipt["status"] == "rejected_forbidden_contact"
    assert receipt["native_contact_audit"]["forbidden_contact_event_count"] > 0
    assert {event["body_a"], event["body_b"]} == {
        "left_camera_mount",
        "tan_pawn_d7",
    }
    assert receipt["ready_for_operator_hardware_preflight"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda policy: policy.update(forbidden_object_body_roots=[]),
            "object policy is empty",
        ),
        (
            lambda policy: policy.update(
                forbidden_static_geom_names=["missing-floor"]
            ),
            "unknown geom",
        ),
    ],
)
def test_native_contact_policy_empty_or_unknown_fails_closed(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    _, p15, evidence = _clean_p16_fixture(tmp_path)
    policy = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    mutation(policy)
    policy_path = tmp_path / "policy.json"
    _write(policy_path, policy)
    with pytest.raises(CanaryContactError, match=message):
        evaluate_canary_contact_preflight(
            candidate_path=Path(p15["candidate_manifest_path"]),
            canary_path=Path(p15["canary_bundle_path"]),
            baseline_path=BASELINE,
            **evidence,
            policy_path=policy_path,
            output_path=tmp_path / "contact-admission.json",
            synthetic_fixture_mode=True,
        )


@pytest.mark.parametrize(
    ("artifact", "mutation", "message"),
    [
        (
            "canary",
            lambda value: value["applied_actions"][1].__setitem__(
                0, value["applied_actions"][1][0] + 0.001
            ),
            "not byte-identical",
        ),
        (
            "canary",
            lambda value: value["initial_state"]["joint_position"].__setitem__(
                0, value["initial_state"]["joint_position"][0] + 0.001
            ),
            "initial state drifted",
        ),
        (
            "candidate",
            lambda value: value["candidate_config"]["parameter_stages"][1][
                "parameters"
            ][0].update(nominal=0.03),
            "candidate config hash drifted",
        ),
    ],
)
def test_contact_preflight_action_initial_state_and_config_drift_fail_closed(
    tmp_path: Path,
    artifact: str,
    mutation,
    message: str,
) -> None:
    _, p15, evidence = _clean_p16_fixture(tmp_path)
    result_key = (
        f"{artifact}_bundle_path"
        if artifact == "canary"
        else "candidate_manifest_path"
    )
    path = Path(p15[result_key])
    value = json.loads(path.read_text(encoding="utf-8"))
    mutation(value)
    _write(path, value)
    with pytest.raises(CanaryContactError, match=message):
        evaluate_canary_contact_preflight(
            candidate_path=Path(p15["candidate_manifest_path"]),
            canary_path=Path(p15["canary_bundle_path"]),
            baseline_path=BASELINE,
            **evidence,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=tmp_path / "contact-admission.json",
            synthetic_fixture_mode=True,
        )


def test_contact_preflight_refuses_overwrite_before_evaluation(
    tmp_path: Path,
) -> None:
    _, p15, evidence = _clean_p16_fixture(tmp_path)
    output = tmp_path / "contact-admission.json"
    output.write_text("occupied", encoding="utf-8")
    with pytest.raises(CanaryContactError, match="refusing to overwrite"):
        evaluate_canary_contact_preflight(
            candidate_path=Path(p15["candidate_manifest_path"]),
            canary_path=Path(p15["canary_bundle_path"]),
            baseline_path=BASELINE,
            **evidence,
            policy_path=DEFAULT_POLICY_PATH,
            output_path=output,
            synthetic_fixture_mode=True,
        )


def test_contact_preflight_never_imports_robot_or_gateway_modules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import builtins
    import sys

    _, p15, evidence = _clean_p16_fixture(tmp_path)
    forbidden_modules = {
        "sim2claw.physical_gateway",
        "sim2claw.teleop_recording",
    }
    assert forbidden_modules.isdisjoint(sys.modules)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.endswith(("physical_gateway", "teleop_recording")):
            raise AssertionError(f"hardware module import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    receipt = evaluate_canary_contact_preflight(
        candidate_path=Path(p15["candidate_manifest_path"]),
        canary_path=Path(p15["canary_bundle_path"]),
        baseline_path=BASELINE,
        **evidence,
        policy_path=DEFAULT_POLICY_PATH,
        output_path=tmp_path / "contact-admission.json",
        synthetic_fixture_mode=True,
    )
    assert receipt["gateway_constructed"] is False
    assert forbidden_modules.isdisjoint(sys.modules)


def test_simulation_only_composes_from_hash_bound_p10_anchor_and_native_preflight(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    p9 = fixture["values"]["p9"]
    p9.update(
        status="admitted_configuration_input",
        proof_class="replay_evaluator",
        synthetic=False,
        evaluator_admission=True,
    )
    _write(fixture["paths"]["p9"], p9)
    p10_root = tmp_path / "p10"
    recording = p10_root / "recording"
    recording.mkdir(parents=True)
    start = np.asarray(
        [1.1908479727818317, 0.02767843375388379, 1.1267926077044281,
         -0.9730003915962206, 0.41239521366234166, 0.45],
        dtype=np.float64,
    )
    samples_path = recording / "samples.jsonl"
    samples_path.write_text(
        json.dumps(
            {
                "timestamp_monotonic_seconds": 0.0,
                "follower_actual_position_degrees": np.rad2deg(start).tolist(),
                "follower_actual_velocity_degrees_s": [0.0] * 6,
            }
        ) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "sim2claw.physical_recording_receipt.v1",
        "recording_id": "p10-anchor",
        "mode": "physical_follower",
        "backend": {
            "schema_version": p9["identity"]["robot"]["gateway_schema"],
            "follower_port": p9["identity"]["robot"]["follower_port"],
            "follower_calibration_sha256": p9["identity"]["robot"]["follower_calibration_sha256"],
        },
        "workcell_registration": {"workspace_pose_id": WORKSPACE_POSE_ID},
        "samples_sha256": sha256_file(samples_path),
    }
    receipt_path = recording / "recording_receipt.json"
    _write(receipt_path, receipt)
    manifest = {
        "schema_version": "sim2claw.replay_manifest.v1",
        "conversion_provenance": {
            "recording_receipt_sha256": sha256_file(receipt_path),
            "samples_sha256": sha256_file(samples_path),
        },
    }
    manifest_path = p10_root / "p4-manifest.json"
    _write(manifest_path, manifest)
    cohort_path = p10_root / "p9_cohort.json"
    _write(
        cohort_path,
        {
            "schema_version": "sim2claw.physical_timing_actuation_cohort.v1",
            "episodes": [{"recording": "recording", "exact_replay_manifest": "p4-manifest.json"}],
        },
    )
    p9["source_cohort"]["sha256"] = sha256_file(cohort_path)
    _write(fixture["paths"]["p9"], p9)
    p15 = compose_twin_candidate_and_canary(
        p9_admission_path=fixture["paths"]["p9"],
        baseline_config_path=BASELINE,
        output_directory=tmp_path / "simulation-only",
        simulation_only=True,
        p10_cohort_path=cohort_path,
    )
    candidate = json.loads(Path(p15["candidate_manifest_path"]).read_text())
    canary = json.loads(Path(p15["canary_bundle_path"]).read_text())
    assert candidate["status"] == "simulation_only_partial"
    assert candidate["geometry_provenance"]["transform_applied"] is False
    assert candidate["runtime"]["p13_required_for_metric_or_physical"] is True
    assert canary["simulation_only"] is True
    assert canary["requested_actions"] == canary["applied_actions"]
    receipt = evaluate_canary_contact_preflight(
        candidate_path=Path(p15["candidate_manifest_path"]),
        canary_path=Path(p15["canary_bundle_path"]),
        baseline_path=BASELINE,
        p9_admission_path=fixture["paths"]["p9"],
        policy_path=DEFAULT_POLICY_PATH,
        output_path=tmp_path / "simulation-contact.json",
        simulation_only=True,
    )
    assert receipt["status"] == "simulation_only_no_contact_passed"
    assert receipt["native_contact_audit"]["forbidden_contact_event_count"] == 0
    assert receipt["ready_for_operator_hardware_preflight"] is False
    assert receipt["simulation_no_contact_admitted"] is True
    assert receipt["stop_before_robot_gateway"] is True
    samples_path.write_text(
        samples_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8"
    )
    with pytest.raises(CanaryContactError, match="source hash drifted"):
        evaluate_canary_contact_preflight(
            candidate_path=Path(p15["candidate_manifest_path"]),
            canary_path=Path(p15["canary_bundle_path"]),
            baseline_path=BASELINE,
            p9_admission_path=fixture["paths"]["p9"],
            policy_path=DEFAULT_POLICY_PATH,
            output_path=tmp_path / "simulation-contact-drift.json",
            simulation_only=True,
        )
