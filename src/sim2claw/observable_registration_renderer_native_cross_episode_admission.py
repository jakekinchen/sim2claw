"""Freeze the cross-episode, renderer-native successor without decoding footage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = (
    "sim2claw.observable_registration_renderer_native_"
    "cross_episode_admission_contract.v1"
)
INVENTORY_SCHEMA = (
    "sim2claw.observable_registration_renderer_native_"
    "cross_episode_pairing_inventory.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_renderer_native_"
    "cross_episode_admission_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_renderer_native_cross_episode_admission_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_renderer_native_cross_episode_admission_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path") or "")
    _require(path.is_file(), f"missing {label}: {path}")
    _require(
        sha256_file(path) == binding.get("sha256"),
        f"{label} hash drifted",
    )
    return path


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _role(position: int, contract: dict[str, Any]) -> str:
    for role, bounds in contract["split"]["roles_by_one_based_position"].items():
        if int(bounds[0]) <= position <= int(bounds[1]):
            return role
    raise FactoryArtifactError(f"split does not assign position {position}")


def load_renderer_native_cross_episode_admission_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR68 admission contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    corpus = contract["corpus"]
    _require(
        corpus["expected_episode_count"] == 11
        and corpus["expected_published_shared_scene_trace_count"] == 7
        and corpus["expected_trace_regeneration_count"] == 4
        and corpus["require_distinct_recording_ids"] is True
        and corpus["require_distinct_action_array_sha256"] is True
        and corpus["require_action_byte_identical"] is True,
        "corpus admission boundary drifted",
    )
    split = contract["split"]
    _require(
        split["key"] == "sha256_utf8_recording_id"
        and split["order"] == "ascending_hex_digest"
        and split["roles_by_one_based_position"]
        == {
            "development": [1, 4],
            "validation": [5, 7],
            "evaluator_heldout": [8, 11],
        }
        and split["expected_counts"]
        == {"development": 4, "validation": 3, "evaluator_heldout": 4}
        and split["historical_outcome_rank_may_assign_roles"] is False
        and split["prior_historical_pixel_access_acknowledged"] is True
        and split["prospective_pristine_holdout_claimed"] is False,
        "split boundary drifted",
    )
    provenance = contract["candidate_provenance"]
    _require(
        provenance["required_pixel_source"] == "declared_3d_renderer_only"
        and provenance["shared_parameter_vector_across_all_episodes"] is True
        and len(provenance["prohibited_candidate_input_prefixes"]) == 3,
        "renderer provenance weakened",
    )
    forbidden_true = (
        "physical_video_may_construct_candidate",
        "validation_or_heldout_may_select_candidate",
        "episode_specific_parameters_allowed",
        "frame_specific_parameters_allowed",
        "screen_space_geometry_allowed",
        "physical_image_derived_materials_allowed",
        "background_plates_allowed",
        "post_render_compositing_allowed",
        "geometric_or_optical_flow_warps_allowed",
        "missing_frame_substitution_allowed",
    )
    _require(
        not any(provenance[name] for name in forbidden_true),
        "target-derived candidate input became admissible",
    )
    access = contract["physical_access"]
    _require(
        access == {
            "path_stat_allowed": True,
            "byte_hash_allowed": True,
            "video_decode_allowed": False,
            "frame_extraction_allowed": False,
            "pixel_metric_evaluation_allowed": False,
            "annotation_allowed": False,
        },
        "physical access boundary widened",
    )
    execution = contract["execution"]
    _require(
        execution["json_outputs_only"] is True
        and all(
            execution[name] == 0
            for name in (
                "physical_frames_decoded_allowed",
                "simulator_replays_allowed",
                "renderer_runs_allowed",
                "candidate_videos_allowed",
                "parameter_fits_allowed",
                "hardware_actions_allowed",
            )
        ),
        "execution boundary widened",
    )
    _require(not any(contract["claim_limits"].values()), "claim limit widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def run_renderer_native_cross_episode_admission_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR68 one-run receipt already exists")
    contract = load_renderer_native_cross_episode_admission_contract(
        contract_path, root=root
    )
    sources = {
        name: _bound_path(binding, root=root, label=name)
        for name, binding in contract["sources"].items()
    }
    cohort = load_json_object(
        sources["eleven_episode_cohort"], label="OR68 eleven-episode cohort"
    )
    gallery = load_json_object(
        sources["published_ranked_gallery"], label="OR68 ranked gallery"
    )
    scene = load_json_object(
        sources["published_shared_scene"], label="OR68 shared scene"
    )
    or67 = load_json_object(sources["or67_closeout"], label="OR67 closeout")

    _require(
        cohort.get("schema_version") == "sim2claw.pawn_bg_grasp_group_probe.v1",
        "cohort schema drifted",
    )
    cohort_rows = cohort.get("episodes")
    _require(isinstance(cohort_rows, list), "cohort episodes missing")
    expected_count = int(contract["corpus"]["expected_episode_count"])
    _require(len(cohort_rows) == expected_count, "cohort episode count drifted")
    _require(
        set(cohort.get("recording_ids") or [])
        == {str(row.get("recording_id") or "") for row in cohort_rows},
        "cohort recording identity list drifted",
    )
    _require(
        cohort.get("summary", {}).get("action_invariance") is True,
        "cohort no longer reports action invariance",
    )
    _require(
        gallery.get("schema_version")
        == "sim2claw.pawn_bg_ranked_grasp_gallery.v1",
        "gallery schema drifted",
    )
    published_rows = {
        str(row["recording_id"]): row for row in gallery.get("episodes", [])
    }
    excluded_ids = {
        str(row["recording_id"]) for row in gallery.get("excluded_episodes", [])
    }
    _require(
        len(published_rows)
        == int(contract["corpus"]["expected_published_shared_scene_trace_count"]),
        "published trace count drifted",
    )
    _require(
        len(excluded_ids) == 4 and not (set(published_rows) & excluded_ids),
        "historical gallery membership drifted",
    )
    _require(
        scene.get("schema_version") == "sim2claw.mujoco_scene_manifest.v1"
        and scene.get("authority", {}).get("physics") == "mujoco"
        and scene.get("authority", {}).get("browser_renderer") == "inspection_only"
        and scene.get("authority", {}).get("physical_authority") is False,
        "shared scene proof boundary drifted",
    )
    _require(
        or67.get("execution", {}).get("mujoco_renderer_runs") == 0
        and or67.get("execution", {}).get("simulator_replays") == 0
        and or67.get("claim_limits", {}).get("mujoco_scene_implementation") is False
        and or67.get("claim_limits", {}).get("physics_fidelity") is False,
        "OR67 quarantine evidence drifted",
    )

    recording_ids = [str(row.get("recording_id") or "") for row in cohort_rows]
    action_hashes = [str(row.get("action_array_sha256") or "") for row in cohort_rows]
    _require(
        len(set(recording_ids)) == expected_count and all(recording_ids),
        "recording IDs are not distinct",
    )
    _require(
        len(set(action_hashes)) == expected_count
        and all(len(value) == 64 for value in action_hashes),
        "action array hashes are not distinct",
    )
    _require(
        all(row.get("action_byte_identical") is True for row in cohort_rows),
        "cohort contains a non-identical action replay",
    )
    _require(
        set(recording_ids) == set(published_rows) | excluded_ids,
        "gallery does not partition the eleven-episode cohort",
    )

    dataset_root = root / contract["corpus"]["physical_recording_root"]
    sorted_rows = sorted(
        cohort_rows,
        key=lambda row: hashlib.sha256(
            str(row["recording_id"]).encode("utf-8")
        ).hexdigest(),
    )
    pairs: list[dict[str, Any]] = []
    role_counts = {name: 0 for name in contract["split"]["expected_counts"]}
    published_trace_count = 0
    regeneration_count = 0
    for position, row in enumerate(sorted_rows, start=1):
        recording_id = str(row["recording_id"])
        folder_label = str(row["folder_label"])
        digest = hashlib.sha256(recording_id.encode("utf-8")).hexdigest()
        role = _role(position, contract)
        role_counts[role] += 1
        episode_directory = dataset_root / f"{folder_label}__{recording_id}"
        sample_path = episode_directory / contract["corpus"]["physical_samples_name"]
        video_path = episode_directory / contract["corpus"]["physical_video_name"]
        _require(sample_path.is_file(), f"missing physical samples for {recording_id}")
        _require(video_path.is_file(), f"missing physical video for {recording_id}")
        sample_rows = sum(1 for line in sample_path.open("rb") if line.strip())
        _require(sample_rows > 0, f"empty physical samples for {recording_id}")

        published = published_rows.get(recording_id)
        if published is None:
            _require(recording_id in excluded_ids, "unknown trace availability state")
            trace = {
                "availability": "missing_requires_action_identical_regeneration",
                "path": None,
                "sha256": None,
                "shared_scene_sha256": contract["sources"][
                    "published_shared_scene"
                ]["sha256"],
            }
            regeneration_count += 1
            historical_membership = "excluded_from_outcome_ranked_publication"
        else:
            artifact = published.get("state_trace") or {}
            trace_path = root / str(artifact.get("state_trace_path") or "")
            _require(trace_path.is_file(), f"missing published trace for {recording_id}")
            trace_sha = sha256_file(trace_path)
            _require(
                trace_sha == artifact.get("state_trace_sha256"),
                f"published trace hash drifted for {recording_id}",
            )
            _require(
                artifact.get("scene_manifest_sha256")
                == contract["sources"]["published_shared_scene"]["sha256"],
                f"published trace scene drifted for {recording_id}",
            )
            trace = {
                "availability": "published_shared_scene_state_trace",
                "path": _relative(trace_path, root),
                "sha256": trace_sha,
                "frame_count": int(artifact["frame_count"]),
                "fps": float(artifact["fps"]),
                "shared_scene_sha256": artifact["scene_manifest_sha256"],
                "inspection_only": bool(artifact["inspection_only"]),
            }
            published_trace_count += 1
            historical_membership = "selected_by_outcome_ranked_publication"

        pairs.append(
            {
                "split_position": position,
                "split_role": role,
                "split_key_sha256": digest,
                "recording_id": recording_id,
                "folder_label": folder_label,
                "action_array_sha256": str(row["action_array_sha256"]),
                "action_byte_identical": True,
                "physical_samples": {
                    "path": _relative(sample_path, root),
                    "sha256": sha256_file(sample_path),
                    "row_count": sample_rows,
                },
                "physical_video": {
                    "path": _relative(video_path, root),
                    "sha256": sha256_file(video_path),
                    "size_bytes": video_path.stat().st_size,
                    "access": "byte_hash_only_not_decoded",
                },
                "historical_gallery_membership": historical_membership,
                "state_trace": trace,
            }
        )

    _require(
        role_counts == contract["split"]["expected_counts"],
        "deterministic split count drifted",
    )
    _require(
        published_trace_count
        == contract["corpus"]["expected_published_shared_scene_trace_count"],
        "published trace inventory drifted",
    )
    _require(
        regeneration_count == contract["corpus"]["expected_trace_regeneration_count"],
        "trace regeneration inventory drifted",
    )

    inventory = {
        "schema_version": INVENTORY_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "split_algorithm": (
            "sha256(recording_id utf-8) ascending; positions 1-4 development, "
            "5-7 validation, 8-11 evaluator_heldout"
        ),
        "role_counts": role_counts,
        "pairs": pairs,
        "trace_readiness": {
            "published_shared_scene_state_trace_count": published_trace_count,
            "action_identical_trace_regeneration_required_count": regeneration_count,
            "renderer_video_count": 0,
        },
        "physical_access": {
            "videos_stat_or_byte_hashed": expected_count,
            "videos_decoded": 0,
            "frames_extracted": 0,
            "pixel_metrics_computed": 0,
        },
        "candidate_provenance": contract["candidate_provenance"],
        "claim_limits": contract["claim_limits"],
    }
    inventory["artifact_sha256"] = canonical_digest(inventory)
    inventory_path = output_directory / "pairing_inventory.json"
    atomic_write_json(inventory_path, inventory)

    gates = {
        "eleven_distinct_recording_ids": len(set(recording_ids)) == 11,
        "eleven_distinct_action_hashes": len(set(action_hashes)) == 11,
        "all_actions_byte_identical": all(
            row["action_byte_identical"] for row in pairs
        ),
        "all_physical_samples_present": all(
            row["physical_samples"]["row_count"] > 0 for row in pairs
        ),
        "all_physical_videos_present_and_byte_hashed": all(
            row["physical_video"]["size_bytes"] > 0 for row in pairs
        ),
        "deterministic_split_complete": role_counts
        == contract["split"]["expected_counts"],
        "published_traces_share_one_scene": published_trace_count == 7,
        "missing_trace_regeneration_explicit": regeneration_count == 4,
        "physical_video_frames_not_decoded": True,
        "or67_quarantined_from_successor_inputs": True,
    }
    _require(all(gates.values()), "OR68 admission gate failed")
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_SPLIT_FROZEN_TRACE_REGENERATION_REQUIRED_RENDERER_NOT_READY",
        "proof_class": contract["proof_class"],
        "contract": {
            "path": _relative(contract_path, root),
            "sha256": sha256_file(contract_path),
        },
        "pairing_inventory": {
            "path": _relative(inventory_path, root),
            "sha256": sha256_file(inventory_path),
            "artifact_sha256": inventory["artifact_sha256"],
        },
        "result": {
            "episode_count": expected_count,
            "role_counts": role_counts,
            "published_shared_scene_state_trace_count": published_trace_count,
            "action_identical_trace_regeneration_required_count": regeneration_count,
            "renderer_runtime_ready": False,
            "candidate_video_count": 0,
            "physical_video_frames_decoded": 0,
            "shared_parameter_vector_required": True,
            "pixel_similarity_achieved": False,
            "physics_fidelity_achieved": False,
        },
        "gates": gates,
        "prohibited_candidate_input_prefixes": contract["candidate_provenance"][
            "prohibited_candidate_input_prefixes"
        ],
        "execution": {
            "physical_frames_decoded": 0,
            "simulator_replays": 0,
            "renderer_runs": 0,
            "candidate_videos": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
            "non_json_outputs": 0,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "ADVANCE_TO_ACTION_IDENTICAL_MISSING_TRACE_REGENERATION",
        "next_transition": "freeze_or69_four_missing_action_identical_state_trace_regenerations",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    run_renderer_native_cross_episode_admission_once()
