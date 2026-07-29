"""Replay immutable V5 actions through the RP04A elbow tracking challenger."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import canonical_seeded_action_static as _static
from . import canonical_seeded_action_static_v2 as _static_v2
from . import canonical_seeded_action_temporal as _temporal
from .coordinated_unloading_tracking_challenger import (
    apply_elbow_tracking_challenger,
)
from .current_workcell import current_square_center
from .observable_episode import (
    build_simulator_episode,
    first_divergence,
    write_episode,
)
from .paths import REPO_ROOT


class CoordinatedUnloadingTrackingTemporalError(RuntimeError):
    """A frozen V5 tracking-challenger input or denominator changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinatedUnloadingTrackingTemporalError(message)


def _bound(entry: Mapping[str, Any]) -> Path:
    path = (REPO_ROOT / str(entry["path"])).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise CoordinatedUnloadingTrackingTemporalError(
            "tracking temporal input escapes repository"
        ) from error
    _require(path.is_file(), f"tracking temporal input is missing: {path}")
    _require(
        _sha(path) == entry["sha256"],
        f"tracking temporal input changed: {path}",
    )
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _baseline_episode(
    v5_receipt: Mapping[str, Any],
    *,
    case_id: str,
    variant_id: str,
) -> dict[str, Any]:
    case = next(
        row for row in v5_receipt["results"] if row["case_id"] == case_id
    )
    path = next(
        row
        for row in case["plant_paths"]
        if row["path_id"] == "canonical_direct_target"
    )
    variant = next(
        row
        for row in path["robustness"]
        if row["variant_id"] == variant_id
    )
    return _json(variant["observable_episode"])


def replay_tracking_challenger(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Run exactly twenty V5 episodes under the frozen elbow-only response."""

    _require(
        not output_directory.exists(),
        "immutable tracking-temporal output directory already exists",
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _require(
        contract.get("schema_version")
        == "sim2claw.coordinated_unloading_tracking_temporal.v1",
        "unexpected tracking-temporal contract",
    )
    expected_fields = {
        "schema_version",
        "contract_id",
        "status",
        "proof_class",
        "inputs",
        "plant",
        "acceptance",
        "output_directory",
        "authority",
        "claim_boundary",
    }
    _require(set(contract) == expected_fields, "tracking temporal widened")
    _require(
        contract["authority"]
        == {
            "dynamic_simulation": True,
            "fit_or_refit": False,
            "action_selection": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "transfer_claim": False,
        },
        "tracking-temporal authority changed",
    )
    for entry in contract["inputs"].values():
        _bound(entry)
    v5 = _json(contract["inputs"]["v5_contract"])
    v5_receipt = _json(contract["inputs"]["v5_receipt"])
    fit = _json(contract["inputs"]["tracking_fit_receipt"])
    fit_closeout = _json(contract["inputs"]["tracking_fit_closeout"])
    base = _json(contract["inputs"]["base_temporal_contract"])
    _require(
        v5["schema_version"]
        == "sim2claw.canonical_wrist_path_selected_temporal.v5"
        and v5["base_temporal_contract"]
        == contract["inputs"]["base_temporal_contract"]
        and len(v5["cases"]) == 4,
        "V5 case universe changed",
    )
    _require(
        v5_receipt["passed"] is True
        and v5_receipt["direction_counts"]
        == {"REAL_TO_SIM": 2, "SIM_TO_REAL": 2}
        and v5_receipt["physical_task_attempts"] == 0,
        "V5 direct/ZOH baseline is not the immutable 40/40 pass",
    )
    _require(
        fit["status"] == "coordinated_unloading_tracking_fit_pass"
        and fit["passed"] is True
        and fit["task_outcomes_used"] is False
        and fit["mapping_approved"] is False
        and fit_closeout["status"]
        == "heldout_fit_pass_task_challenger_admitted",
        "tracking fit was not admitted",
    )
    plant = contract["plant"]
    _require(
        plant["kind"] == "elbow_only_first_order_affine_per_sample"
        and plant["joint_index"] == 2
        and plant["non_elbow_path"] == "canonical_direct_target"
        and plant["task_outcomes_used_for_fit"] is False
        and plant["causal_latency_calibrated"] is False,
        "tracking plant scope changed",
    )
    _require(
        float(plant["alpha"]) == float(fit["joint"]["alpha"])
        and float(plant["bias_degrees_per_sample"])
        == float(fit["joint"]["bias_degrees_per_sample"])
        and list(plant["measured_observed_support_degrees"])
        == [
            fit["support"]["full_observed_minimum_degrees"],
            fit["support"]["full_observed_maximum_degrees"],
        ],
        "tracking plant parameters differ from the frozen fit",
    )
    _require(
        contract["acceptance"]
        == {
            "expected_case_count": 4,
            "expected_variants_per_case": 5,
            "expected_challenger_episode_count": 20,
            "minimum_passing_cases_per_direction": 2,
            "all_challenger_episodes_must_pass": True,
            "prior_v5_direct_and_zoh_40_of_40_must_remain_passed": True,
        },
        "tracking-temporal denominator changed",
    )
    manifest = _temporal._json(base["inputs"]["candidate_manifest"])
    rigid = _temporal._json(base["inputs"]["registration_candidate"])
    model_builder = _static_v2._calibrated_registered_model(
        _static._registered_current_model,
        manifest["candidate_config"],
    )
    model, addresses, _, jaw_bodies = model_builder(
        rigid, float(base["simulation"]["timestep_s"])
    )
    actuators = [
        _static._named_id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        for name in _static.ALL_JOINTS
    ]
    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(base["camera_gate"]["image_size_px"])
    sample_hz = float(base["action_identity"]["sample_hz"])
    support_low, support_high = [
        float(value) for value in plant["measured_observed_support_degrees"]
    ]
    output_directory.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    total_passing_episodes = 0
    total_episodes = 0
    for case in v5["cases"]:
        requested = _temporal._load_action(case)
        requested_sha = hashlib.sha256(
            requested.tobytes(order="C")
        ).hexdigest()
        _require(
            requested_sha == case["action_sha256"],
            "V5 requested action bytes changed",
        )
        applied, physical_applied = apply_elbow_tracking_challenger(
            requested,
            candidate_config=manifest["candidate_config"],
            alpha=float(plant["alpha"]),
            bias_degrees_per_sample=float(
                plant["bias_degrees_per_sample"]
            ),
            initial_actual_degrees=float(
                plant["initial_actual_elbow_degrees"]
            ),
        )
        physical_requested = _static._physical_actions(
            requested, manifest["candidate_config"]
        )
        timestamps = np.arange(len(requested), dtype="<f8") / sample_hz
        trace_directory = output_directory / "traces" / case["case_id"]
        trace_directory.mkdir(parents=True)
        traces = {
            "requested": _temporal._write_tensor(
                trace_directory, "requested", requested
            ),
            "mapped": _temporal._write_tensor(
                trace_directory, "mapped", requested
            ),
            "sent": _temporal._write_tensor(
                trace_directory, "sent", requested
            ),
            "applied": _temporal._write_tensor(
                trace_directory, "applied", applied
            ),
            "physical_requested": _temporal._write_tensor(
                trace_directory, "physical_requested", physical_requested
            ),
            "physical_applied": _temporal._write_tensor(
                trace_directory, "physical_applied", physical_applied
            ),
            "timestamps": _temporal._write_tensor(
                trace_directory, "timestamps", timestamps
            ),
        }
        rates = np.max(
            np.abs(np.diff(physical_applied, axis=0)) * sample_hz,
            axis=0,
        )
        rate_limits = np.asarray(
            base["action_identity"]["gateway_rate_limits_per_joint"],
            dtype=np.float64,
        )
        elbow_applied = physical_applied[:, 2]
        extrapolated = (elbow_applied < support_low) | (
            elbow_applied > support_high
        )
        source = np.asarray(
            current_square_center(case["source_square"]), dtype=np.float64
        )
        destination = np.asarray(
            current_square_center(case["destination_square"]),
            dtype=np.float64,
        )
        direction = destination - source
        direction /= np.linalg.norm(direction)
        robustness: list[dict[str, Any]] = []
        divergences: list[dict[str, Any]] = []
        for variant in base["robustness_variants"]:
            longitudinal, lateral = variant["delta_m"]
            delta = (
                direction[:2] * longitudinal
                + np.asarray([-direction[1], direction[0]]) * lateral
            )
            consequence = _temporal._replay(
                model=model,
                addresses=addresses,
                actuators=actuators,
                jaw_bodies=jaw_bodies,
                action=applied,
                selected_name=case["selected_piece_id"],
                source_delta_m=delta,
                direction=direction,
                substeps=int(base["simulation"]["substeps_per_row"]),
                sample_hz=sample_hz,
                first_object_motion_threshold_m=float(
                    base["observable_episode"][
                        "first_object_motion_threshold_m"
                    ]
                ),
                camera=camera,
                image_size=image_size,
                reset_layout=v5["reset_layout"],
            )
            observable = consequence.pop("observable_inputs")
            checks = {
                "progress": consequence["signed_progress_mm"]
                >= base["gates"]["minimum_signed_progress_mm"],
                "selected_contact": consequence["selected_contact_steps"] > 0,
                "excluded_contact": consequence["excluded_contact_steps"] == 0,
                "excluded_displacement": consequence[
                    "maximum_excluded_displacement_mm"
                ]
                <= base["gates"]["maximum_excluded_displacement_mm"],
                "no_lift": consequence["maximum_selected_vertical_rise_mm"]
                <= base["gates"]["maximum_selected_vertical_rise_mm"],
                "collision": not consequence[
                    "new_nonselected_jaw_collision_pairs"
                ],
                "camera_margin": consequence["camera_margin_px"]
                >= base["camera_gate"]["minimum_margin_px"],
            }
            task_outcome = (
                "pass"
                if all(checks.values())
                else "fail:"
                + ",".join(
                    sorted(
                        name for name, value in checks.items() if not value
                    )
                )
            )
            episode = build_simulator_episode(
                episode_id=(
                    f"{case['case_id']}__elbow_tracking_challenger__"
                    f"{variant['variant_id']}"
                ),
                requested=requested,
                applied=applied,
                sample_hz=sample_hz,
                joint_states=observable["joint_states"],
                link_poses=observable["link_poses"],
                object_states_board_se2=observable[
                    "object_states_board_se2"
                ],
                object_covariances=observable["object_covariances"],
                contact_states=observable["contact_states"],
                task_outcome=task_outcome,
                first_object_motion_sample=observable[
                    "first_object_motion_sample"
                ],
                provenance={
                    "contract_path": _display_path(contract_path),
                    "contract_sha256": _sha(contract_path),
                    "case_id": case["case_id"],
                    "direction": case["direction"],
                    "plant_path_id": "physical_elbow_tracking_challenger",
                    "plant_kind": plant["kind"],
                    "diagnostic_only": True,
                    "calibrated_physical_latency": False,
                    "variant_id": variant["variant_id"],
                    "source_delta_m": delta.tolist(),
                    "object_covariance_semantics":
                    "zero_deterministic_simulator_state",
                },
            )
            episode_path = (
                output_directory
                / "episodes"
                / case["case_id"]
                / f"{variant['variant_id']}.json"
            )
            episode_receipt = write_episode(episode, episode_path)
            episode_receipt["path"] = _display_path(episode_path)
            baseline = _baseline_episode(
                v5_receipt,
                case_id=case["case_id"],
                variant_id=variant["variant_id"],
            )
            divergences.append(
                {
                    "variant_id": variant["variant_id"],
                    **first_divergence(
                        baseline,
                        episode,
                        joint_threshold=float(
                            base["first_divergence"][
                                "joint_threshold_rad"
                            ]
                        ),
                        link_position_threshold_m=float(
                            base["first_divergence"][
                                "link_position_threshold_m"
                            ]
                        ),
                        object_position_threshold_m=float(
                            base["first_divergence"][
                                "object_position_threshold_m"
                            ]
                        ),
                        object_yaw_threshold_rad=float(
                            base["first_divergence"][
                                "object_yaw_threshold_rad"
                            ]
                        ),
                    ),
                }
            )
            episode_passed = all(checks.values())
            total_episodes += 1
            total_passing_episodes += int(episode_passed)
            robustness.append(
                {
                    "variant_id": variant["variant_id"],
                    **consequence,
                    "checks": checks,
                    "passed": episode_passed,
                    "observable_episode": episode_receipt,
                }
            )
        identity_checks = {
            "requested_hash_matches_v5": requested_sha
            == case["action_sha256"],
            "requested_mapped_sent_byte_identical": (
                traces["requested"]["sha256"]
                == traces["mapped"]["sha256"]
                == traces["sent"]["sha256"]
            ),
            "non_elbow_applied_byte_identical": bool(
                np.array_equal(
                    applied[:, [0, 1, 3, 4, 5]],
                    requested[:, [0, 1, 3, 4, 5]],
                )
            ),
            "applied_gateway_rate_compatible": bool(
                np.all(rates <= rate_limits)
            ),
            "timestamps_strictly_monotonic": bool(
                np.all(np.diff(timestamps) > 0.0)
            ),
        }
        case_passed = all(identity_checks.values()) and all(
            row["passed"] for row in robustness
        )
        results.append(
            {
                "case_id": case["case_id"],
                "direction": case["direction"],
                "source_square": case["source_square"],
                "destination_square": case["destination_square"],
                "selected_piece_id": case["selected_piece_id"],
                "action_sha256": case["action_sha256"],
                "action_shape": case["action_shape"],
                "traces": traces,
                "identity_checks": identity_checks,
                "maximum_applied_physical_rate_per_second": rates.tolist(),
                "gateway_rate_limits_per_joint": rate_limits.tolist(),
                "measured_support": {
                    "minimum_degrees": support_low,
                    "maximum_degrees": support_high,
                    "extrapolated_applied_row_count": int(
                        np.count_nonzero(extrapolated)
                    ),
                    "first_extrapolated_applied_row": (
                        int(np.flatnonzero(extrapolated)[0])
                        if np.any(extrapolated)
                        else None
                    ),
                    "minimum_applied_elbow_degrees": float(
                        np.min(elbow_applied)
                    ),
                    "maximum_applied_elbow_degrees": float(
                        np.max(elbow_applied)
                    ),
                    "extrapolation_is_diagnostic_only": True,
                },
                "robustness": robustness,
                "direct_baseline_vs_tracking_first_divergence": divergences,
                "passed": case_passed,
            }
        )
    passing = [row for row in results if row["passed"]]
    direction_counts = {
        direction: sum(row["direction"] == direction for row in passing)
        for direction in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    passed = (
        total_episodes
        == contract["acceptance"]["expected_challenger_episode_count"]
        and total_passing_episodes == total_episodes
        and direction_counts == {"REAL_TO_SIM": 2, "SIM_TO_REAL": 2}
    )
    receipt = {
        "schema_version":
        "sim2claw.coordinated_unloading_tracking_temporal_receipt.v1",
        "contract_id": contract["contract_id"],
        "contract_path": _display_path(contract_path),
        "contract_sha256": _sha(contract_path),
        "status": (
            "coordinated_unloading_tracking_temporal_pass"
            if passed
            else "coordinated_unloading_tracking_temporal_reject"
        ),
        "passed": passed,
        "prior_v5_direct_zoh_episode_count": 40,
        "prior_v5_direct_zoh_pass_count": 40,
        "challenger_episode_count": total_episodes,
        "challenger_passing_episode_count": total_passing_episodes,
        "direction_counts": direction_counts,
        "results": results,
        "task_outcomes_used_for_fit": False,
        "action_selection_or_refit": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "mapping_approved": False,
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }
    (output_directory / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "CoordinatedUnloadingTrackingTemporalError",
    "replay_tracking_challenger",
]
