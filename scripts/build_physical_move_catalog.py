#!/usr/bin/env python3
"""Build a receipt-grounded catalog for the latest physical pawn recordings.

The catalog is an intake/routing surface, not a learned-policy registry.  Raw
physical traces remain unqualified until their metadata, segmentation, replay,
and task-outcome gates have been reviewed independently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MOVE_RE = re.compile(r"(?P<source>[a-h][1-8])[-_ ]to[-_ ](?P<destination>[a-h][1-8])", re.I)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_move(text: str) -> tuple[str, str] | None:
    match = MOVE_RE.search(text)
    if not match:
        return None
    return match.group("source").lower(), match.group("destination").lower()


def relative(path: Path) -> str:
    return path.as_posix()


def build_episode(root: Path, directory: Path, preferred_recording_id: str | None) -> dict[str, Any]:
    receipt_path = directory / "recording_receipt.json"
    samples_path = directory / "samples.jsonl"
    video_path = directory / "overhead_c922.mp4"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    recording_id = str(receipt["recording_id"])
    receipt_source = str(receipt["source_square"]).lower()
    receipt_destination = str(receipt["destination_square"]).lower()
    folder_label = directory.name.split("__", 1)[0].lower()
    folder_move = parse_move(folder_label)
    receipt_move = (receipt_source, receipt_destination)
    if folder_move is None:
        metadata_status = "conflict_folder_label_unparseable"
    elif folder_move != receipt_move:
        metadata_status = "conflict_folder_label_vs_receipt"
    else:
        metadata_status = "consistent_folder_label_and_receipt"

    receipt_hash = sha256_file(receipt_path)
    samples_hash = sha256_file(samples_path)
    video_hash = sha256_file(video_path)
    declared_samples_hash = receipt.get("samples_sha256")
    declared_video_hash = receipt.get("overhead_video", {}).get("video_sha256")
    if declared_samples_hash and declared_samples_hash != samples_hash:
        raise ValueError(f"samples hash mismatch: {samples_path}")
    if declared_video_hash and declared_video_hash != video_hash:
        raise ValueError(f"video hash mismatch: {video_path}")

    move_id = f"{receipt_source}_to_{receipt_destination}"
    same_rank = receipt_source[1] == receipt_destination[1]
    same_file = receipt_source[0] == receipt_destination[0]
    movement_axis = "horizontal" if same_rank and not same_file else (
        "vertical" if same_file and not same_rank else "other"
    )
    return {
        "recording_id": recording_id,
        "source_path": relative(directory),
        "folder_label": folder_label,
        "receipt_label": receipt.get("label"),
        "source_square": receipt_source,
        "destination_square": receipt_destination,
        "move_id": move_id,
        "policy_candidate_id": f"pawn_{move_id}_v1",
        "movement_axis": movement_axis,
        "brev_generalization_candidate": movement_axis == "horizontal",
        "metadata_status": metadata_status,
        "candidate_role": (
            "preferred_keep"
            if recording_id == preferred_recording_id
            else "source_candidate"
        ),
        "callable_policy": False,
        "proof_class": receipt.get("proof_class"),
        "mode": receipt.get("mode"),
        "outcome_label": receipt.get("outcome_label"),
        "training_admission": receipt.get("training_admission"),
        "sample_hz": receipt.get("sample_hz"),
        "sample_count": receipt.get("sample_count"),
        "duration_seconds": receipt.get("duration_seconds"),
        "receipt_sha256": receipt_hash,
        "samples_sha256": samples_hash,
        "overhead_video_sha256": video_hash,
        "assets": {
            "receipt": relative(receipt_path),
            "samples": relative(samples_path),
            "overhead_video": relative(video_path),
        },
    }


def build_catalog(root: Path, preferred_recording_id: str) -> dict[str, Any]:
    episodes = [
        build_episode(root, directory, preferred_recording_id)
        for directory in sorted(root.iterdir())
        if directory.is_dir() and (directory / "recording_receipt.json").is_file()
    ]
    if not episodes:
        raise ValueError(f"no recording receipts found under {root}")
    if not any(item["recording_id"] == preferred_recording_id for item in episodes):
        raise ValueError(f"preferred recording is not present: {preferred_recording_id}")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        grouped.setdefault(episode["move_id"], []).append(episode)
    moves = []
    for move_id in sorted(grouped):
        candidates = grouped[move_id]
        preferred = [item for item in candidates if item["candidate_role"] == "preferred_keep"]
        horizontal = any(item["movement_axis"] == "horizontal" for item in candidates)
        moves.append(
            {
                "move_id": move_id,
                "policy_candidate_id": f"pawn_{move_id}_v1",
                "candidate_recording_ids": [item["recording_id"] for item in candidates],
                "preferred_recording_id": preferred[0]["recording_id"] if preferred else None,
                "movement_axis": "horizontal" if horizontal else candidates[0]["movement_axis"],
                "brev_generalization_candidate": horizontal,
                "callable_policy": False,
                "status": "source_candidates_pending_reconciliation",
            }
        )

    horizontal_candidates = [
        episode for episode in episodes if episode["brev_generalization_candidate"]
    ]
    return {
        "schema_version": "sim2claw.physical_pawn_move_catalog.v1",
        "catalog_id": "physical_pawn_moves_20260719_latest_v1",
        "reviewed_at": "2026-07-19",
        "raw_storage": {
            "root": relative(root),
            "availability": "owner_local_ignored_artifacts_not_distributed_by_git",
            "git_policy": "raw_receipts_samples_videos_remain_ignored",
            "mutation_policy": "raw_receipts_are_immutable; corrections_live_in_this_catalog",
        },
        "routing_decision": {
            "observation": "overhead_camera_board_state_is_a_planner_input_only",
            "selection": "planner_selects_a_receipt_grounded_move_id_after_board_state_review",
            "execution": "future_versioned_act_policy_adapter_after_replay_and_evaluator_admission",
            "callable_policy_authorized": False,
            "learned_policy_verified": False,
            "physical_task_success_proven": False,
            "training_rows_admitted": 0,
        },
        "brev_generalization": {
            "status": "candidate_not_admitted",
            "rationale": "same-rank side-to-side demonstrations are retained as a supplemental generalization lane; they still require the Brev contract, split, and evaluator gates",
            "candidate_recording_ids": [
                episode["recording_id"] for episode in horizontal_candidates
            ],
            "candidate_move_ids": sorted(
                {episode["move_id"] for episode in horizontal_candidates}
            ),
            "candidate_count": len(horizontal_candidates),
        },
        "discarded_recordings": [
            {
                "recording_id": "20260719T032722Z-84dc04de",
                "original_path": "datasets/manipulation_source_recordings/g1-to-g2__20260719T032722Z-84dc04de",
                "recovery_location": "user_trash",
                "reason": "initial_attempt_replaced_by_explicit_redo",
                "replacement_recording_id": "20260719T032810Z-9e623c5e",
            }
        ],
        "moves": moves,
        "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("datasets/manipulation_source_recordings"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preferred-recording-id", required=True)
    args = parser.parse_args()
    catalog = build_catalog(args.root, args.preferred_recording_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "episode_count": len(catalog["episodes"]), "move_count": len(catalog["moves"])}, indent=2))


if __name__ == "__main__":
    main()
