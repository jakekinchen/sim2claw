"""Freeze a replacement split after rejected validation without decoding pixels."""

from __future__ import annotations

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


SCHEMA = "sim2claw.observable_registration_json_only_validation_split_restart_contract.v1"
MANIFEST_SCHEMA = "sim2claw.observable_registration_json_only_validation_split_manifest.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_json_only_validation_split_restart_receipt.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_json_only_validation_split_restart_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_json_only_validation_split_restart_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(binding: dict[str, Any], *, root: Path, label: str) -> Path:
    path = root / str(binding.get("path") or "")
    _require(path.is_file(), f"missing {label}: {path}")
    _require(sha256_file(path) == binding.get("sha256"), f"{label} hash drifted")
    return path


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _new_role(position: int, split: dict[str, Any]) -> str:
    for role in (
        "expanded_development",
        "fresh_validation",
        "final_evaluator_heldout",
    ):
        if position in [int(value) for value in split[f"{role}_positions"]]:
            return role
    raise FactoryArtifactError(f"split does not assign position {position}")


def load_json_only_validation_split_restart_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR88 split-restart contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    split = contract["split"]
    _require(
        split["source_order"] == "or68_ascending_sha256_utf8_recording_id"
        and split["expanded_development_positions"] == list(range(1, 8))
        and split["fresh_validation_positions"] == [8, 9]
        and split["final_evaluator_heldout_positions"] == [10, 11]
        and split["opened_or87_validation_becomes_development"] is True
        and split["retroactive_validation_claim_allowed"] is False
        and split["prospective_pristine_holdout_claimed"] is False
        and split["prior_historical_pixel_access_acknowledged"] is True,
        "split restart boundary drifted",
    )
    expected_ids = split["expected_recording_ids_by_role"]
    _require(
        {name: len(rows) for name, rows in expected_ids.items()}
        == {
            "expanded_development": 7,
            "fresh_validation": 2,
            "final_evaluator_heldout": 2,
        },
        "split identity counts drifted",
    )
    access = contract["physical_access"]
    _require(
        access["path_stat_allowed"] is True
        and access["byte_hash_allowed"] is True
        and all(
            access[name] is False
            for name in (
                "video_decode_allowed",
                "frame_extraction_allowed",
                "pixel_metric_evaluation_allowed",
                "annotation_allowed",
            )
        ),
        "physical access widened",
    )
    execution = contract["execution"]
    _require(
        execution["json_outputs_only"] is True
        and execution["paid_compute_allowed"] is False
        and all(
            execution[name] == 0
            for name in (
                "physical_frames_decoded_allowed",
                "physical_video_decodes_allowed",
                "renderer_runs_allowed",
                "candidate_videos_allowed",
                "parameter_fits_allowed",
                "candidate_selections_allowed",
                "simulator_replays_allowed",
                "hardware_actions_allowed",
            )
        ),
        "execution boundary widened",
    )
    _require(
        contract["claim_limits"]["split_restart_only"] is True
        and not any(
            value
            for name, value in contract["claim_limits"].items()
            if name != "split_restart_only"
        ),
        "claim boundary widened",
    )
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def run_json_only_validation_split_restart_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR88 one-run receipt already exists")
    contract = load_json_only_validation_split_restart_contract(contract_path, root=root)
    sources = {
        name: _bound_path(binding, root=root, label=name)
        for name, binding in contract["sources"].items()
    }
    or87 = load_json_object(sources["or87_closeout"], label="OR87 closeout")
    inventory = load_json_object(
        sources["or68_pairing_inventory"], label="OR68 pairing inventory"
    )
    or69 = load_json_object(sources["or69_receipt"], label="OR69 receipt")

    _require(
        or87.get("status") == "TERMINAL_REJECT_ONLY_VALIDATION_CAMERA_WORKCELL_RESPONSE_FAILED"
        and or87.get("failed_gate", {}).get("name") == "pooled_mean_tolerant_edge_f1"
        and or87.get("result", {}).get("evaluator_heldout_reads") == 0,
        "OR87 rejection boundary drifted",
    )
    pairs = inventory.get("pairs")
    _require(isinstance(pairs, list) and len(pairs) == 11, "OR68 inventory drifted")
    _require(
        [row.get("split_position") for row in pairs] == list(range(1, 12)),
        "OR68 position order drifted",
    )
    regenerated = {
        str(row["recording_id"]): row for row in or69.get("regenerated", [])
    }
    _require(len(regenerated) == 4, "OR69 regenerated trace inventory drifted")

    split = contract["split"]
    expected = split["expected_recording_ids_by_role"]
    result_pairs: list[dict[str, Any]] = []
    role_counts = {name: 0 for name in expected}
    for row in pairs:
        position = int(row["split_position"])
        recording_id = str(row["recording_id"])
        new_role = _new_role(position, split)
        role_counts[new_role] += 1
        trace = dict(row["state_trace"])
        if trace.get("availability") == "missing_requires_action_identical_regeneration":
            replacement = regenerated.get(recording_id)
            _require(replacement is not None, f"missing regenerated trace for {recording_id}")
            trace = {
                "availability": "action_identical_regenerated_state_trace",
                "path": replacement["state_trace_path"],
                "sha256": replacement["state_trace_sha256"],
                "frame_count": replacement["state_trace_frame_count"],
                "fps": replacement["state_trace_fps"],
                "inspection_only": replacement["inspection_only"],
                "shared_scene_sha256": replacement["scene_revision_sha256"],
            }
        trace_path = root / str(trace.get("path") or "")
        _require(trace_path.is_file(), f"missing ready trace for {recording_id}")
        _require(sha256_file(trace_path) == trace.get("sha256"), f"trace hash drifted for {recording_id}")
        video = dict(row["physical_video"])
        video["access"] = "byte_hash_bound_not_decoded_by_or88"
        result_pairs.append(
            {
                "split_position": position,
                "split_key_sha256": row["split_key_sha256"],
                "recording_id": recording_id,
                "prior_split_role": row["split_role"],
                "new_split_role": new_role,
                "action_array_sha256": row["action_array_sha256"],
                "action_byte_identical": row["action_byte_identical"],
                "physical_samples": row["physical_samples"],
                "physical_video": video,
                "state_trace": trace,
                "successor_pixel_status": (
                    "opened_before_or88_now_development"
                    if new_role == "expanded_development"
                    else "unread_since_or68_role_freeze_through_or88"
                ),
            }
        )

    _require(
        role_counts
        == {
            "expanded_development": 7,
            "fresh_validation": 2,
            "final_evaluator_heldout": 2,
        },
        "new split counts drifted",
    )
    for role, recording_ids in expected.items():
        observed = [
            row["recording_id"]
            for row in result_pairs
            if row["new_split_role"] == role
        ]
        _require(observed == recording_ids, f"{role} identities drifted")

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "source_order": split["source_order"],
        "pairs": result_pairs,
        "role_counts": role_counts,
        "opened_validation_reclassified_as_development": [
            row["recording_id"] for row in result_pairs if row["split_position"] in (5, 6, 7)
        ],
        "fresh_validation_unread_recording_ids": expected["fresh_validation"],
        "final_evaluator_heldout_unread_recording_ids": expected["final_evaluator_heldout"],
        "or88_physical_video_decodes": 0,
        "prior_historical_pixel_access_acknowledged": True,
    }
    manifest_path = output_directory / "split_manifest.json"
    atomic_write_json(manifest_path, manifest)
    gates = {
        "eleven_identities_bound": len(result_pairs) == 11,
        "all_state_traces_ready": all(row["state_trace"]["path"] for row in result_pairs),
        "opened_validation_reclassified_as_development": True,
        "fresh_validation_exactly_positions_8_and_9": [
            row["split_position"] for row in result_pairs if row["new_split_role"] == "fresh_validation"
        ] == [8, 9],
        "final_heldout_exactly_positions_10_and_11": [
            row["split_position"] for row in result_pairs if row["new_split_role"] == "final_evaluator_heldout"
        ] == [10, 11],
        "no_physical_video_decodes_or_pixel_reads": True,
        "no_render_fit_selection_replay_hardware_or_paid_compute": True,
        "no_retroactive_validation_or_pristine_claim": True,
    }
    _require(all(gates.values()), "OR88 split restart gate failed")
    manifest_sha = sha256_file(manifest_path)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "status": "PASS_JSON_ONLY_VALIDATION_SPLIT_RESTART_FROZEN",
        "proof_class": contract["proof_class"],
        "contract": {"path": _relative(contract_path, root), "sha256": sha256_file(contract_path)},
        "split_manifest": {"path": _relative(manifest_path, root), "sha256": manifest_sha},
        "gates": gates,
        "result": {
            "episode_count": 11,
            "role_counts": role_counts,
            "expanded_development_recording_ids": expected["expanded_development"],
            "fresh_validation_recording_ids": expected["fresh_validation"],
            "final_evaluator_heldout_recording_ids": expected["final_evaluator_heldout"],
            "fresh_validation_reads": 0,
            "final_evaluator_heldout_reads": 0,
        },
        "execution": {
            "physical_frames_decoded": 0,
            "physical_video_decodes": 0,
            "renderer_runs": 0,
            "candidate_videos": 0,
            "parameter_fits": 0,
            "candidate_selections": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "non_json_outputs": 0,
            "paid_compute": False,
        },
        "reviewer_decision": "ADVANCE_TO_EXPANDED_DEVELOPMENT_GLOBAL_MONOTONE_RESPONSE_FIT",
        "next_transition": "freeze_or89_expanded_development_global_monotone_response_fit",
        "claim_limits": contract["claim_limits"],
    }
    receipt["artifact_sha256"] = canonical_digest(
        {"split_manifest_sha256": manifest_sha, "gates": gates, "result": receipt["result"]}
    )
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    run_json_only_validation_split_restart_once()
