"""Fail-closed retrospective publication evidence for the retired workcell.

The physical source recordings are immutable inputs.  This module binds those
bytes into replay anchors and fits only posteriors supported by fields that
were actually recorded.  It never repairs a trace, approves a transform, or
turns qualitative video review into metric calibration evidence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import t as student_t

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


GATE_SCHEMA = "sim2claw.retrospective_publication_gate.v1"
RECEIPT_SCHEMA = "sim2claw.retrospective_publication_receipt.v1"
ANCHOR_SCHEMA = "sim2claw.physical_replay_anchor.v1"
TRACKING_POSTERIOR_SCHEMA = "sim2claw.physical_tracking_observation_posterior.v1"
IMAGE_FIT_SCHEMA = "sim2claw.qualitative_image_offset_fit.v1"
CAMPAIGN_SCHEMA = "sim2claw.corrective_provider_campaign.v1"
SUBSCRIPTION_PILOT_SCHEMA = "sim2claw.corrective_subscription_pilot.v1"
CAMPAIGN_MANIFEST_SCHEMA = "sim2claw.corrective_provider_campaign_manifest.v1"

DEFAULT_GATE_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "sim2claw_retrospective_publication_gate_v1.json"
)


class RetrospectivePublicationError(ValueError):
    """An evidence input or frozen publication boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RetrospectivePublicationError(message)


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise RetrospectivePublicationError(f"{label} is not numeric") from error
    _require(math.isfinite(result), f"{label} is not finite")
    return result


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RetrospectivePublicationError(f"{label} escapes the repository root") from error
    return path


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _bound_json(repo_root: Path, descriptor: Mapping[str, Any], label: str) -> tuple[Path, dict[str, Any]]:
    _require(set(descriptor) == {"path", "sha256"}, f"{label} binding keys changed")
    path = _repo_path(repo_root, str(descriptor["path"]), label)
    _require(path.is_file(), f"{label} is missing: {_relative(repo_root, path)}")
    actual = sha256_file(path)
    _require(actual == descriptor["sha256"], f"{label} hash changed")
    return path, load_json_object(path, label=label)


def load_publication_gate(
    path: Path = DEFAULT_GATE_PATH, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    value = load_json_object(path, label="retrospective publication gate")
    _require(value.get("schema_version") == GATE_SCHEMA, "unsupported publication gate schema")
    _require(value.get("gate_id") == "sim2claw-retrospective-publication-gate-20260720-v1", "publication gate identity changed")
    authority = value.get("authority")
    _require(isinstance(authority, dict) and authority, "publication authority is missing")
    _require(all(item is False for item in authority.values()), "publication gate widened authority")
    expected = value.get("expected_inventory")
    _require(
        expected
        == {
            "episode_count": 18,
            "sample_count": 7741,
            "catalog_bound_asset_count": 54,
            "evidence_frame_count": 36,
            "owner_accepted_visual_marker_count": 26,
            "directed_skill_count": 12,
        },
        "publication inventory changed",
    )
    posterior = value.get("posterior", {})
    _require(posterior.get("episode_is_independent_unit") is True, "posterior unit changed")
    _require(posterior.get("credible_mass") == 0.95, "posterior credible mass changed")
    _require(len(posterior.get("joint_names", [])) == 6, "posterior joint inventory changed")
    campaign_path = _repo_path(repo_root, value["provider_campaign"]["path"], "provider campaign")
    _require(campaign_path.is_file(), "frozen provider campaign is missing")
    return value


def _read_samples(
    path: Path,
    *,
    episode_id: str,
    required_schema: str,
    vector_length: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_timestamp: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise RetrospectivePublicationError(
                    f"{episode_id} samples line {line_number} is invalid JSON"
                ) from error
            _require(isinstance(row, dict), f"{episode_id} sample is not an object")
            _require(row.get("schema_version") == required_schema, f"{episode_id} sample schema changed")
            _require(row.get("recording_id") == episode_id, f"{episode_id} sample recording identity changed")
            _require(row.get("sample_index") == len(rows), f"{episode_id} sample indices are not contiguous")
            timestamp = _finite(row.get("timestamp_monotonic_seconds"), "sample timestamp")
            if previous_timestamp is not None:
                _require(timestamp > previous_timestamp, f"{episode_id} timestamps are not strictly increasing")
            previous_timestamp = timestamp
            for field in (
                "follower_actual_position_degrees",
                "follower_command_degrees",
                "follower_requested_degrees",
            ):
                vector = row.get(field)
                _require(isinstance(vector, list) and len(vector) == vector_length, f"{episode_id} {field} shape changed")
                for index, item in enumerate(vector):
                    _finite(item, f"{episode_id} {field}[{index}]")
            rows.append(row)
    _require(rows, f"{episode_id} samples are empty")
    return rows


def _normal_inverse_gamma_fit(
    values: Sequence[float],
    prior: Mapping[str, Any],
    credible_mass: float,
    *,
    unit: str,
) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    _require(array.ndim == 1 and array.size >= 2, "posterior needs at least two independent units")
    _require(np.isfinite(array).all(), "posterior observations contain non-finite values")
    mu0 = _finite(prior.get("mean"), "prior mean")
    kappa0 = _finite(prior.get("mean_strength"), "prior mean strength")
    alpha0 = _finite(prior.get("shape"), "prior shape")
    beta0 = _finite(prior.get("scale"), "prior scale")
    _require(kappa0 > 0.0 and alpha0 > 1.0 and beta0 > 0.0, "posterior prior must be proper")
    n = int(array.size)
    observed_mean = float(np.mean(array))
    centered_sum = float(np.sum(np.square(array - observed_mean)))
    kappa_n = kappa0 + n
    mu_n = (kappa0 * mu0 + n * observed_mean) / kappa_n
    alpha_n = alpha0 + n / 2.0
    beta_n = beta0 + 0.5 * centered_sum + (kappa0 * n * (observed_mean - mu0) ** 2) / (2.0 * kappa_n)
    tail = (1.0 - credible_mass) / 2.0
    quantiles = (tail, 0.5, 1.0 - tail)
    degrees_of_freedom = 2.0 * alpha_n
    mean_scale = math.sqrt(beta_n / (alpha_n * kappa_n))
    predictive_scale = math.sqrt(beta_n * (kappa_n + 1.0) / (alpha_n * kappa_n))
    return {
        "model": "normal_inverse_gamma",
        "unit": unit,
        "independent_unit_count": n,
        "observed_mean": observed_mean,
        "observed_sample_stddev": float(np.std(array, ddof=1)),
        "prior": {
            "mean": mu0,
            "mean_strength": kappa0,
            "shape": alpha0,
            "scale": beta0,
        },
        "posterior": {
            "mean": mu_n,
            "mean_strength": kappa_n,
            "shape": alpha_n,
            "scale": beta_n,
            "variance_mean": beta_n / (alpha_n - 1.0),
        },
        "mean_distribution": {
            "distribution": "student_t",
            "degrees_of_freedom": degrees_of_freedom,
            "location": mu_n,
            "scale": mean_scale,
            "credible_mass": credible_mass,
            "quantiles": {
                str(q): float(student_t.ppf(q, degrees_of_freedom, loc=mu_n, scale=mean_scale))
                for q in quantiles
            },
        },
        "episode_predictive_distribution": {
            "distribution": "student_t",
            "degrees_of_freedom": degrees_of_freedom,
            "location": mu_n,
            "scale": predictive_scale,
            "credible_mass": credible_mass,
            "quantiles": {
                str(q): float(student_t.ppf(q, degrees_of_freedom, loc=mu_n, scale=predictive_scale))
                for q in quantiles
            },
        },
    }


def _empirical_summary(values: Iterable[float], unit: str) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    _require(array.size > 0 and np.isfinite(array).all(), "empirical summary is empty or invalid")
    return {
        "unit": unit,
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "stddev": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
        "rmse": float(np.sqrt(np.mean(np.square(array)))),
        "quantiles": {
            "0.025": float(np.quantile(array, 0.025)),
            "0.5": float(np.quantile(array, 0.5)),
            "0.975": float(np.quantile(array, 0.975)),
        },
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def _vector_summary(rows: Sequence[Sequence[float]], unit: str) -> dict[str, Any]:
    array = np.asarray(rows, dtype=np.float64)
    _require(array.ndim == 2 and array.shape[0] >= 2, "vector fit needs at least two rows")
    return {
        "unit": unit,
        "count": int(array.shape[0]),
        "mean": [float(item) for item in np.mean(array, axis=0)],
        "covariance": [[float(item) for item in row] for row in np.cov(array, rowvar=False, ddof=1)],
        "component_quantiles": {
            str(q): [float(item) for item in np.quantile(array, q, axis=0)]
            for q in (0.025, 0.5, 0.975)
        },
    }


def _verify_visual_evidence(
    repo_root: Path,
    frame_selection: Mapping[str, Any],
    owner_review: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    frame_rows: dict[tuple[str, str], Mapping[str, Any]] = {}
    frame_hashes: set[str] = set()
    for episode in frame_selection.get("episodes", []):
        episode_id = str(episode.get("recording_id"))
        for frame in episode.get("frames", []):
            phase = str(frame.get("phase"))
            key = (episode_id, phase)
            _require(key not in frame_rows, f"duplicate evidence frame {key}")
            path = _repo_path(repo_root, str(frame["path"]), f"evidence frame {key}")
            _require(path.is_file(), f"evidence frame is missing: {_relative(repo_root, path)}")
            actual = sha256_file(path)
            _require(actual == frame.get("sha256"), f"evidence frame hash changed: {key}")
            frame_rows[key] = {**frame, "portable_path": _relative(repo_root, path)}
            frame_hashes.add(actual)

    marker_rows = owner_review.get("accepted_marker_manifest")
    _require(isinstance(marker_rows, list), "owner marker manifest is missing")
    pixel_offsets: list[list[float]] = []
    metric_proposal_offsets: list[list[float]] = []
    marker_hashes: list[str] = []
    episodes_by_id = {
        str(row.get("recording_id")): row for row in frame_selection.get("episodes", [])
    }
    for marker in marker_rows:
        key = (str(marker.get("source_recording_id")), str(marker.get("phase")))
        _require(key in frame_rows, f"owner marker has no evidence frame: {key}")
        _require(marker.get("frame_sha256") == frame_rows[key].get("sha256"), f"owner marker frame hash changed: {key}")
        proposal = episodes_by_id[key[0]].get("visual_fiducial_proposals", {}).get(key[1])
        _require(isinstance(proposal, dict), f"owner marker has no visual proposal: {key}")
        for marker_field, proposal_field in (
            ("visual_fiducial_center_px", "center_px"),
            ("inferred_contact_center_px", "contact_center_px"),
        ):
            marker_value = np.asarray(marker.get(marker_field), dtype=np.float64)
            proposal_value = np.asarray(proposal.get(proposal_field), dtype=np.float64)
            _require(marker_value.shape == (2,) and np.allclose(marker_value, proposal_value, atol=1e-9), f"owner marker geometry changed: {key}")
        pixel_offset = proposal.get("signed_contact_center_offset_px")
        metric_offset = proposal.get("signed_board_offset_mm_approximate_unreviewed")
        _require(isinstance(pixel_offset, list) and len(pixel_offset) == 2, f"pixel offset missing: {key}")
        _require(isinstance(metric_offset, list) and len(metric_offset) == 2, f"metric proposal offset missing: {key}")
        pixel_offsets.append([_finite(item, "pixel offset") for item in pixel_offset])
        metric_proposal_offsets.append([_finite(item, "metric proposal offset") for item in metric_offset])
        marker_hashes.append(str(marker["frame_sha256"]))

    fit = {
        "schema_version": IMAGE_FIT_SCHEMA,
        "source_review_sha256": canonical_digest(owner_review),
        "accepted_marker_count": len(marker_rows),
        "pixel_fit": _vector_summary(pixel_offsets, "pixel"),
        "proposal_metric_sensitivity_fit": _vector_summary(metric_proposal_offsets, "millimeter"),
        "pixel_offset_semantics": "owner_accepted_inferred_contact_cross_relative_to_proposal_nominal_square_center",
        "proposal_metric_semantics": "unreviewed_homography_projection_sensitivity_only",
        "admission": {
            "qualitative_image_space": True,
            "metric_calibration": False,
            "simulator_parameter_fit": False,
            "physical_transfer_proof": False,
        },
    }
    integrity = {
        "evidence_frame_count": len(frame_rows),
        "unique_evidence_frame_hash_count": len(frame_hashes),
        "owner_accepted_marker_count": len(marker_rows),
        "marker_frame_hash_count": len(marker_hashes),
        "all_marker_frames_bound": len(marker_hashes) == len(marker_rows),
    }
    return integrity, fit


def _verify_provider_campaign(repo_root: Path, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    campaign = load_json_object(path, label="provider campaign")
    if campaign.get("schema_version") == SUBSCRIPTION_PILOT_SCHEMA:
        from .subscription_pilot import load_subscription_pilot_campaign

        campaign = load_subscription_pilot_campaign(path, repo_root=repo_root)
        budgets = campaign["budgets"]
        bindings = campaign["artifact_bindings"]
        readiness = {
            "frozen": True,
            "protocol": campaign["campaign_mode"],
            "system_count": budgets["system_count"],
            "case_count": budgets["case_count"],
            "case_attempt_count": budgets["total_case_attempts"],
            "subscription_case_attempt_count": budgets["subscription_case_attempts"],
            "paid_api_case_attempt_count": budgets["paid_api_case_attempts"],
            "paid_api_retry_count": budgets["paid_api_retry_count"],
            "paid_api_maximum_cost_usd": budgets["paid_api_maximum_cost_usd"],
            "campaign_maximum_incremental_cost_usd": budgets[
                "campaign_maximum_incremental_cost_usd"
            ],
            "artifact_bindings_verified": True,
            "sandbox_oci_digest_present": bool(bindings.get("sandbox_image_digest")),
            "execution_authorized": False,
            "subscription_usage_authorized": False,
            "provider_calls_authorized": False,
            "spend_authorized": False,
            "execution_ready": False,
            "execution_blockers": [
                "codex_sol_model_access_not_checked",
                "claude_fable_model_access_not_checked",
                "groq_api_key_not_checked",
                "subscription_usage_not_authorized",
                "provider_call_and_spend_not_authorized",
                "execution_not_authorized",
            ],
        }
        return campaign, readiness
    _require(campaign.get("schema_version") == CAMPAIGN_SCHEMA, "unsupported provider campaign schema")
    authority = campaign.get("authority", {})
    _require(authority and all(item is False for item in authority.values()), "provider campaign became authorized")
    design = campaign.get("factorial_design", {})
    harnesses = design.get("harnesses")
    treatments = design.get("model_treatments")
    _require(harnesses == ["codex_cli", "claude_code"], "provider harness inventory changed")
    _require(isinstance(treatments, list) and len(treatments) == 10, "provider treatment inventory changed")
    treatment_ids = [str(item.get("treatment_id")) for item in treatments]
    _require(len(treatment_ids) == len(set(treatment_ids)), "provider treatment IDs are duplicated")
    for treatment in treatments:
        exact = str(treatment.get("exact_model_id", ""))
        inspect_model = str(treatment.get("inspect_model", ""))
        _require(exact and inspect_model.endswith(exact), f"provider treatment is not exact: {treatment.get('treatment_id')}")
        _require("latest" not in exact and not exact.endswith("-max") or exact in {"claude-fable-5", "kimi-k3"}, f"provider treatment uses an alias: {exact}")
        credential = str(treatment.get("credential_env", ""))
        _require(credential.endswith("API_KEY"), "provider credential binding changed")
    bindings = campaign.get("artifact_bindings", {})
    binding_paths = {
        "agents_sha256": "evals/inspect_gapbench/agents.py",
        "corrective_dataset_sha256": "evals/inspect_gapbench/corrective_dataset.py",
        "corrective_tools_sha256": "evals/inspect_gapbench/corrective_tools.py",
        "dockerfile_sha256": "evals/inspect_gapbench/Dockerfile",
        "compose_sha256": "evals/inspect_gapbench/compose.yaml",
        "uv_lock_sha256": "uv.lock",
    }
    binding_results: dict[str, Any] = {}
    for field, relative in binding_paths.items():
        bound_path = _repo_path(repo_root, relative, field)
        actual = sha256_file(bound_path)
        _require(actual == bindings.get(field), f"provider campaign binding changed: {relative}")
        binding_results[field] = actual
    skill_root = _repo_path(repo_root, "evals/inspect_gapbench/corrective_skills", "corrective skills")
    skill_bindings = {
        path.parent.name: sha256_file(path)
        for path in sorted(skill_root.glob("*/SKILL.md"))
    }
    _require(len(skill_bindings) == 5, "corrective skill inventory changed")
    _require(
        canonical_digest(skill_bindings) == bindings.get("corrective_skill_bundle_sha256"),
        "corrective skill bundle changed",
    )
    benchmark = campaign.get("benchmark", {})
    for field, path_field in (("contract_sha256", "contract_path"), ("task_sha256", "inspect_task")):
        raw_path = str(benchmark[path_field]).split("@", 1)[0]
        actual = sha256_file(_repo_path(repo_root, raw_path, path_field))
        _require(actual == benchmark[field], f"provider benchmark binding changed: {raw_path}")
    total_runs = len(harnesses) * len(treatments) * int(benchmark["epochs"])
    total_case_attempts = total_runs * len(benchmark["cases"])
    execution_blockers = [
        "provider_credentials_not_checked",
        "provider_access_not_checked",
        "spend_not_authorized",
        "execution_not_authorized",
    ]
    if not bindings.get("sandbox_oci_digest"):
        execution_blockers.insert(0, "sandbox_oci_digest_missing")
    readiness = {
        "frozen": True,
        "model_treatment_count": len(treatments),
        "harness_count": len(harnesses),
        "epochs": int(benchmark["epochs"]),
        "task_run_count": total_runs,
        "case_attempt_count": total_case_attempts,
        "artifact_bindings_verified": True,
        "sandbox_oci_digest_present": bool(bindings.get("sandbox_oci_digest")),
        "execution_authorized": False,
        "provider_calls_authorized": False,
        "spend_authorized": False,
        "execution_ready": False,
        "execution_blockers": execution_blockers,
    }
    return campaign, readiness


def build_publication_receipt(
    *,
    gate_path: Path = DEFAULT_GATE_PATH,
    repo_root: Path = REPO_ROOT,
    capability_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    gate = load_publication_gate(gate_path, repo_root=repo_root)
    inputs = gate["inputs"]
    catalog_path, catalog = _bound_json(repo_root, inputs["catalog"], "physical catalog")
    _, frame_selection = _bound_json(repo_root, inputs["frame_selection"], "frame selection")
    _, owner_review = _bound_json(repo_root, inputs["owner_visual_review"], "owner visual review")
    sysid_path, sysid_config = _bound_json(repo_root, inputs["sysid_config"], "sysid config")

    anchor_contract = gate["replay_anchor"]
    posterior_contract = gate["posterior"]
    joint_names = list(posterior_contract["joint_names"])
    expected = gate["expected_inventory"]
    transform_rows = sysid_config["physical_adapter"]["joint_transform"]["joints"]
    source_units = {
        str(row["source_joint"]): str(row["input_unit"]) for row in transform_rows
    }
    _require(set(source_units) == set(joint_names), "source joint units changed")
    catalog_episodes = catalog.get("episodes")
    _require(isinstance(catalog_episodes, list), "catalog episodes are missing")
    _require(len(catalog_episodes) == expected["episode_count"], "catalog episode count changed")

    anchors: list[dict[str, Any]] = []
    episode_tracking_means: dict[str, list[float]] = {name: [] for name in joint_names}
    pooled_tracking: dict[str, list[float]] = {name: [] for name in joint_names}
    episode_intervals: list[float] = []
    total_samples = 0
    asset_count = 0

    for episode in catalog_episodes:
        episode_id = str(episode.get("recording_id"))
        assets = episode.get("assets")
        _require(isinstance(assets, dict), f"{episode_id} catalog assets are missing")
        expected_hashes = {
            "samples": episode.get("samples_sha256"),
            "receipt": episode.get("receipt_sha256"),
            "overhead_video": episode.get("overhead_video_sha256"),
        }
        asset_bindings: dict[str, Any] = {}
        for name in anchor_contract["required_catalog_assets"]:
            path = _repo_path(repo_root, str(assets[name]), f"{episode_id} {name}")
            _require(path.is_file(), f"{episode_id} {name} is missing")
            actual = sha256_file(path)
            _require(actual == expected_hashes[name], f"{episode_id} {name} hash changed")
            asset_bindings[name] = {"path": _relative(repo_root, path), "sha256": actual}
            asset_count += 1

        rows = _read_samples(
            _repo_path(repo_root, str(assets["samples"]), f"{episode_id} samples"),
            episode_id=episode_id,
            required_schema=anchor_contract["required_sample_schema"],
            vector_length=int(anchor_contract["required_vector_length"]),
        )
        _require(len(rows) == episode.get("sample_count"), f"{episode_id} sample count changed")
        total_samples += len(rows)
        timestamps = np.asarray([row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64)
        intervals = np.diff(timestamps)
        _require(intervals.size > 0 and np.all(intervals > 0), f"{episode_id} has no valid intervals")
        episode_intervals.append(float(np.mean(intervals)))
        actual = np.asarray([row["follower_actual_position_degrees"] for row in rows], dtype=np.float64)
        command = np.asarray([row["follower_command_degrees"] for row in rows], dtype=np.float64)
        residual = actual - command
        for index, name in enumerate(joint_names):
            values = residual[:, index]
            episode_tracking_means[name].append(float(np.mean(values)))
            pooled_tracking[name].extend(float(item) for item in values)

        trace_payload = [
            {
                "sample_index": row["sample_index"],
                "timestamp_monotonic_seconds": row["timestamp_monotonic_seconds"],
                "follower_command_degrees": row["follower_command_degrees"],
                "follower_actual_position_degrees": row["follower_actual_position_degrees"],
            }
            for row in rows
        ]
        anchors.append(
            {
                "schema_version": ANCHOR_SCHEMA,
                "recording_id": episode_id,
                "proof_class": episode.get("proof_class"),
                "source_square": episode.get("source_square"),
                "destination_square": episode.get("destination_square"),
                "sample_count": len(rows),
                "duration_seconds": float(timestamps[-1] - timestamps[0]),
                "mean_sample_interval_seconds": float(np.mean(intervals)),
                "maximum_sample_interval_seconds": float(np.max(intervals)),
                "assets": asset_bindings,
                "replay_trace_sha256": canonical_digest(trace_payload),
                "sample_semantics_valid": True,
                "simulator_replay_eligible": False,
                "anchor_semantics": anchor_contract["anchor_semantics"],
            }
        )

    _require(total_samples == expected["sample_count"], "physical sample inventory changed")
    _require(asset_count == expected["catalog_bound_asset_count"], "catalog asset inventory changed")
    visual_integrity, image_fit = _verify_visual_evidence(repo_root, frame_selection, owner_review)
    _require(visual_integrity["evidence_frame_count"] == expected["evidence_frame_count"], "evidence frame inventory changed")
    _require(visual_integrity["owner_accepted_marker_count"] == expected["owner_accepted_visual_marker_count"], "owner marker inventory changed")
    _require(owner_review.get("directed_skill_coverage_count") == expected["directed_skill_count"], "directed skill coverage changed")

    tracking_joints: list[dict[str, Any]] = []
    for name in joint_names:
        unit = source_units[name]
        tracking_joints.append(
            {
                "joint_name": name,
                "episode_mean_bias_posterior": _normal_inverse_gamma_fit(
                    episode_tracking_means[name],
                    posterior_contract["tracking_prior"],
                    float(posterior_contract["credible_mass"]),
                    unit=unit,
                ),
                "pooled_within_trace_residual": _empirical_summary(pooled_tracking[name], unit),
            }
        )
    tracking_posterior = {
        "schema_version": TRACKING_POSTERIOR_SCHEMA,
        "posterior_id": "physical-tracking-observation-20260720-v1",
        "source_catalog_sha256": sha256_file(catalog_path),
        "source_anchor_set_sha256": canonical_digest(anchors),
        "model": posterior_contract["model"],
        "independent_unit": "whole_physical_episode",
        "episode_count": len(anchors),
        "sample_count": total_samples,
        "residual_semantics": posterior_contract["tracking_residual"],
        "joints": tracking_joints,
        "sample_interval_posterior": _normal_inverse_gamma_fit(
            episode_intervals,
            posterior_contract["sample_interval_prior"],
            float(posterior_contract["credible_mass"]),
            unit="second",
        ),
        "limitations": [
            "episode means are the independent units; within-episode temporal autocorrelation is not modeled",
            "the posterior describes physical command tracking in source units, not MuJoCo parameter values",
            "the physical-to-simulator joint transform is provisional and unapproved",
            "latency, gain, and damping are not separately identifiable from this observational fit",
        ],
        "authority": {
            "diagnostic_physical_observation": True,
            "simulator_calibration": False,
            "domain_randomization_admission": False,
            "training_admission": False,
            "physical_transfer_proof": False,
        },
    }

    if capability_report is None:
        from .system_identification import inspect_recording_catalog_inputs

        capability_report = inspect_recording_catalog_inputs(
            catalog_path,
            repo_root=repo_root,
            config_path=sysid_path,
            inspection_scope="canonical_checkout",
        )
    capability = dict(capability_report)
    _require(capability.get("schema_version") == "sim2claw.sysid_input_capability.v1", "sysid capability schema changed")
    _require(capability.get("episode_count") == len(anchors), "sysid capability episode count changed")
    capability_summary = {
        "strict_sample_semantics_valid_episode_count": capability.get("strict_sample_semantics_valid_episode_count"),
        "joint_range_valid_episode_count": capability.get("joint_range_valid_episode_count"),
        "joint_replay_ready_episode_count": capability.get("joint_replay_ready_episode_count"),
        "full_provenance_chain_episode_count": capability.get("full_provenance_chain_episode_count"),
        "aggregate_observable_status": capability.get("aggregate_observable_status"),
        "physical_joint_transform": capability.get("physical_joint_transform"),
        "geometry_stage_ready": capability.get("geometry_stage_ready"),
        "timing_control_fit_ready": capability.get("timing_control_fit_ready"),
        "contact_object_stage_ready": capability.get("contact_object_stage_ready"),
        "calibration_ready": capability.get("calibration_ready"),
        "calibration_ready_reason": capability.get("calibration_ready_reason"),
    }
    transform = sysid_config["physical_adapter"]["joint_transform"]
    _require(transform.get("calibration_approved") is False, "publication gate cannot silently approve the joint transform")
    _require(capability_summary["joint_replay_ready_episode_count"] == 0, "exact replay status changed; freeze a new gate before publication")

    campaign_path = _repo_path(repo_root, gate["provider_campaign"]["path"], "provider campaign")
    campaign, campaign_readiness = _verify_provider_campaign(repo_root, campaign_path)

    gates = {
        "asset_lineage": {"status": "pass", "proof_class": "physical_source_integrity"},
        "real_replay_anchors": {"status": "pass", "proof_class": "physical_source_replay_intent"},
        "strict_sample_semantics": {"status": "pass", "episode_count": len(anchors)},
        "physical_tracking_observation_posterior": {"status": "pass_diagnostic_only", "domain_randomization_admitted": False},
        "qualitative_image_offset_fit": {"status": "pass_descriptive_only", "metric": False},
        "metric_endpoint_calibration": {"status": "blocked", "reason": "owner review has zero metric pose annotations and the proposal homography is not independently held-out validated"},
        "exact_simulator_replay": {"status": "blocked", "reason": "physical joint transform is provisional and zero of eighteen episodes pass exact simulator range validation"},
        "geometry_sysid": {"status": "blocked", "reason": "measured end-effector position is unavailable"},
        "timing_control_sysid": {"status": "blocked", "reason": "exact simulator replay is ineligible, so latency gain and damping cannot be identified against replay"},
        "contact_object_sysid": {"status": "blocked", "reason": "measured pawn pose and contact observables are unavailable"},
        "provider_campaign_freeze": {"status": "pass_specification_only", "execution_ready": False},
        "physical_transfer": {"status": "blocked", "reason": "the retired workspace cannot supply a new held-out hardware evaluation"},
    }
    return {
        "schema_version": RECEIPT_SCHEMA,
        "gate_id": gate["gate_id"],
        "gate_contract_sha256": sha256_file(gate_path),
        "proof_class": gate["proof_class"],
        "inventory": {
            "episode_count": len(anchors),
            "sample_count": total_samples,
            "catalog_bound_asset_count": asset_count,
            **visual_integrity,
        },
        "source_bindings": {
            name: descriptor for name, descriptor in inputs.items()
        },
        "anchor_set_sha256": canonical_digest(anchors),
        "anchors": anchors,
        "tracking_posterior": tracking_posterior,
        "qualitative_image_fit": image_fit,
        "sysid_capability": capability_summary,
        "provider_campaign": {
            "campaign_id": campaign["campaign_id"],
            "campaign_sha256": sha256_file(campaign_path),
            **campaign_readiness,
        },
        "gates": gates,
        "publication_verdict": {
            "retrospective_source_package_ready": True,
            "diagnostic_real_data_posterior_ready": True,
            "simulator_calibration_ready": False,
            "sim_to_real_claim_ready": False,
            "physical_transfer_claim_ready": False,
            "strongest_supported_claim": "hash-bound physical source corpus with strict replay anchors, a diagnostic posterior over observed joint tracking and sample timing, and qualitative image-space endpoint evidence",
            "terminal_negative_findings_are_results": True,
        },
        "authority": gate["authority"],
    }


def write_publication_receipt(
    output_path: Path,
    *,
    gate_path: Path = DEFAULT_GATE_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt = build_publication_receipt(gate_path=gate_path, repo_root=repo_root)
    atomic_write_json(output_path, receipt)
    return receipt


def build_provider_campaign_manifest(
    *,
    campaign_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    campaign, readiness = _verify_provider_campaign(repo_root, campaign_path)
    benchmark = campaign["benchmark"]
    fixed = campaign["fixed_execution"]
    jobs: list[dict[str, Any]] = []
    for harness in campaign["factorial_design"]["harnesses"]:
        for treatment in campaign["factorial_design"]["model_treatments"]:
            model_args: list[str] = []
            generate_config: dict[str, Any] = {}
            if treatment["provider"] != "anthropic":
                generate_config["temperature"] = fixed["default_temperature"]
            if treatment["api_mode"] == "responses":
                model_args.extend(["responses_api=true"])
            elif treatment["provider"] in {"moonshot", "alibaba_model_studio"}:
                model_args.extend(["responses_api=false"])
            reasoning = treatment["reasoning"]
            if reasoning["parameter"] == "enable_thinking":
                generate_config["extra_body"] = {"enable_thinking": True}
            else:
                generate_config[reasoning["parameter"]] = reasoning["value"]
            job_id = f"{harness}--{treatment['treatment_id']}"
            generate_config_path = f"runs/publication-gate/provider-job-configs/{job_id}.json"
            argv = [
                "uv", "run", "--group", "inspect", "inspect", "eval",
                benchmark["inspect_task"],
                "-T", f"harness={harness}",
                "--model", treatment["inspect_model"],
                "--sample-shuffle", str(benchmark["case_order_seed"]),
                "--epochs", str(benchmark["epochs"]),
                "--max-connections", str(fixed["max_connections"]),
                "--max-samples", str(fixed["max_samples"]),
                "--max-retries", str(fixed["max_retries"]),
                "--generate-config", generate_config_path,
                "--score-on-error",
                "--no-fail-on-error",
                "--log-model-api",
                "--log-refusals",
            ]
            if treatment["base_url"]:
                argv.extend(["--model-base-url", treatment["base_url"]])
            for argument in model_args:
                argv.extend(["-M", argument])
            jobs.append(
                {
                    "job_id": job_id,
                    "harness": harness,
                    "treatment_id": treatment["treatment_id"],
                    "provider": treatment["provider"],
                    "exact_model_id": treatment["exact_model_id"],
                    "credential_source_env": treatment["credential_env"],
                    "credential_target_env": "OPENAI_API_KEY" if treatment["provider"] in {"moonshot", "alibaba_model_studio"} else treatment["credential_env"],
                    "generate_config_path": generate_config_path,
                    "generate_config": generate_config,
                    "argv": argv,
                    "authorized": False,
                }
            )
    return {
        "schema_version": CAMPAIGN_MANIFEST_SCHEMA,
        "campaign_id": campaign["campaign_id"],
        "campaign_sha256": sha256_file(campaign_path),
        "dry_run": True,
        "job_count": len(jobs),
        "case_attempt_count": readiness["case_attempt_count"],
        "jobs_sha256": canonical_digest(jobs),
        "jobs": jobs,
        "readiness": readiness,
        "execution_instructions": "This artifact is an argv manifest, not execution authorization. Resolve credentials only in process environment after the OCI digest, provider access, and spend gates pass.",
    }


__all__ = [
    "ANCHOR_SCHEMA",
    "CAMPAIGN_MANIFEST_SCHEMA",
    "DEFAULT_GATE_PATH",
    "GATE_SCHEMA",
    "IMAGE_FIT_SCHEMA",
    "RECEIPT_SCHEMA",
    "TRACKING_POSTERIOR_SCHEMA",
    "RetrospectivePublicationError",
    "build_provider_campaign_manifest",
    "build_publication_receipt",
    "load_publication_gate",
    "write_publication_receipt",
]
