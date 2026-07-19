"""Fail-closed GR00T LeRobot mixture from independently admitted datasets.

The builder never evaluates an episode and never admits raw recordings.  It
only verifies the frozen receipts named by the mixture contract, reindexes the
already-admitted rows, normalizes the video canvas, and records exact lineage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "tasks" / "chess_manipulation_groot_multisource_v2.json"
)
CONTRACT_SCHEMA = "sim2claw.groot_multisource_dataset_contract.v2"
CONTRACT_ID = "chess_manipulation_groot_multisource_v2"
RECEIPT_SCHEMA = "sim2claw.groot_multisource_lerobot_dataset_receipt.v2"
PREFLIGHT_SCHEMA = "sim2claw.groot_multisource_dataset_preflight.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_groot_multisource_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _read_json(path)
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise ValueError("unsupported GR00T multisource dataset contract")
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("GR00T multisource dataset identity changed")
    if contract.get("frozen_before_export") is not True:
        raise ValueError("GR00T multisource contract must be frozen before export")

    cohorts = contract.get("cohorts", [])
    labels = [row.get("dataset_label") for row in cohorts]
    if labels != [
        "chess_pick_place_groot_v1",
        "chess_pick_place_groot_recovery_v2",
        "chess_pick_place_pawn_groot_v1",
    ]:
        raise ValueError("GR00T multisource cohort order or identity changed")
    if any(row.get("all_rows_evaluator_admitted") is not True for row in cohorts):
        raise ValueError("every GR00T multisource cohort must be evaluator admitted")
    if any(row.get("physical_authority") is not False for row in cohorts):
        raise ValueError("simulation mixture may not claim physical authority")

    unique_count = sum(int(row["unique_source_episode_count"]) for row in cohorts)
    derived_count = sum(
        int(row["unique_source_episode_count"])
        * int(row["dataset_repetitions_per_source_episode"])
        for row in cohorts
    )
    frame_count = sum(
        int(row["source_frame_count"])
        * int(row["dataset_repetitions_per_source_episode"])
        for row in cohorts
    )
    dataset = contract["dataset"]
    if unique_count != int(dataset["unique_source_episode_count"]):
        raise ValueError("GR00T multisource unique episode count changed")
    if derived_count != int(dataset["derived_dataset_episode_count"]):
        raise ValueError("GR00T multisource derived episode count changed")
    if frame_count != int(dataset["frame_count"]):
        raise ValueError("GR00T multisource frame count changed")
    effective = frame_count - derived_count * (
        int(contract["model"]["action_horizon"]) - 1
    )
    if effective != int(dataset["expected_effective_h16_start_count"]):
        raise ValueError("GR00T multisource action-horizon denominator changed")
    if int(dataset.get("held_out_rows", -1)) != 0:
        raise ValueError("held-out rows may not enter the GR00T multisource dataset")

    excluded = contract["excluded_evidence"]
    if int(excluded.get("physical_training_rows", -1)) != 0:
        raise ValueError("physical quarantine rows entered the training contract")
    if int(excluded.get("counterexample_training_rows", -1)) != 0:
        raise ValueError("counterexample rows entered the training contract")
    if excluded.get("raw_failure_actions_may_enter_behavior_cloning") is not False:
        raise ValueError("raw failure actions may not enter behavior cloning")
    return contract


def _receipt_manifest(receipt: dict[str, Any]) -> dict[str, str]:
    if "payload_manifest" in receipt:
        return {
            str(path): str(row["sha256"])
            for path, row in receipt["payload_manifest"].items()
        }
    if "files" in receipt:
        return {str(path): str(digest) for path, digest in receipt["files"].items()}
    raise ValueError("source dataset receipt has no payload manifest")


def _verify_source_dataset(
    root: Path, cohort: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    receipt_path = root / "dataset_receipt.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(f"source dataset receipt is missing: {receipt_path}")
    if sha256_file(receipt_path) != cohort["dataset_receipt_sha256"]:
        raise ValueError(f"source receipt drifted: {cohort['cohort_id']}")
    receipt = _read_json(receipt_path)
    manifest = _receipt_manifest(receipt)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "dataset_receipt.json"
    }
    if actual != set(manifest):
        missing = sorted(set(manifest) - actual)
        extra = sorted(actual - set(manifest))
        raise ValueError(
            f"source dataset inventory drifted: {cohort['cohort_id']} "
            f"missing={missing} extra={extra}"
        )
    for relative, expected in manifest.items():
        if sha256_file(root / relative) != expected:
            raise ValueError(
                f"source dataset payload drifted: {cohort['cohort_id']}:{relative}"
            )

    info = _read_json(root / "meta" / "info.json")
    episodes = _read_jsonl(root / "meta" / "episodes.jsonl")
    tasks = _read_jsonl(root / "meta" / "tasks.jsonl")
    expected_episodes = int(cohort["unique_source_episode_count"])
    expected_frames = int(cohort["source_frame_count"])
    if int(info.get("total_episodes", -1)) != expected_episodes:
        raise ValueError(f"source episode count drifted: {cohort['cohort_id']}")
    if int(info.get("total_frames", -1)) != expected_frames:
        raise ValueError(f"source frame count drifted: {cohort['cohort_id']}")
    if len(episodes) != expected_episodes:
        raise ValueError(f"source episode ledger drifted: {cohort['cohort_id']}")
    if sum(int(row["length"]) for row in episodes) != expected_frames:
        raise ValueError(f"source episode lengths drifted: {cohort['cohort_id']}")
    if int(info.get("fps", -1)) != 20:
        raise ValueError(f"source FPS drifted: {cohort['cohort_id']}")
    features = info["features"]
    if features["action"]["shape"] != [6]:
        raise ValueError(f"source action shape drifted: {cohort['cohort_id']}")
    if features["observation.state"]["shape"] != [6]:
        raise ValueError(f"source state shape drifted: {cohort['cohort_id']}")
    if features["observation.images.front"]["dtype"] != "video":
        raise ValueError(f"source video modality drifted: {cohort['cohort_id']}")

    if cohort["cohort_id"] == "historical_nominal_rook_king_v1":
        if receipt.get("all_expert_episodes_passed_frozen_evaluator") is not True:
            raise ValueError("nominal source lost evaluator admission")
    elif cohort["cohort_id"] == "historical_recovery_rook_king_v2":
        evidence = receipt.get("episode_evidence", [])
        if len(evidence) != expected_episodes or any(
            row.get("verdict", {}).get("success") is not True for row in evidence
        ):
            raise ValueError("recovery source lost evaluator admission")
    elif cohort["cohort_id"] == "current_100mm_pawn_v1":
        if receipt.get("all_source_rows_evaluator_admitted") is not True:
            raise ValueError("pawn source lost evaluator admission")
        if int(receipt.get("held_out_rows", -1)) != 0:
            raise ValueError("pawn source contains held-out rows")
        if receipt.get("scene", {}).get("workspace_pose_id") != cohort.get(
            "workspace_pose_id"
        ):
            raise ValueError("pawn source workspace identity drifted")
    return receipt, info, episodes, tasks


def _episode_path(root: Path, kind: str, episode_index: int) -> Path:
    if kind == "data":
        return root / "data" / "chunk-000" / f"episode_{episode_index:06d}.parquet"
    if kind == "video":
        return (
            root
            / "videos"
            / "chunk-000"
            / "observation.images.front"
            / f"episode_{episode_index:06d}.mp4"
        )
    raise ValueError("episode path kind must be data or video")


def _replace_scalar_column(table: Any, name: str, value: int) -> Any:
    import pyarrow as pa

    column_index = table.schema.get_field_index(name)
    if column_index < 0:
        raise ValueError(f"source parquet is missing {name}")
    field = table.schema.field(column_index)
    values = pa.array(np.full(table.num_rows, value), type=field.type)
    return table.set_column(column_index, field, values)


def _normalize_video(source: Path, destination: Path, *, copy_only: bool) -> None:
    if copy_only:
        shutil.copyfile(source, destination)
        return
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to normalize GR00T video")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        "scale=256:256:flags=lanczos",
        "-r",
        "20",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(destination),
    ]
    subprocess.run(command, check=True)


def _stats(values: np.ndarray) -> dict[str, list[float]]:
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    return {
        "mean": matrix.mean(axis=0).tolist(),
        "std": matrix.std(axis=0).tolist(),
        "min": matrix.min(axis=0).tolist(),
        "max": matrix.max(axis=0).tolist(),
        "q01": np.quantile(matrix, 0.01, axis=0).tolist(),
        "q99": np.quantile(matrix, 0.99, axis=0).tolist(),
    }


def export_groot_multisource_dataset(
    output: Path,
    *,
    nominal_dataset: Path,
    recovery_dataset: Path,
    pawn_dataset: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Build the frozen multisource mixture without admitting new evidence."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    contract = load_groot_multisource_contract(contract_path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite GR00T multisource dataset: {output}")
    staging = output.with_name(output.name + ".partial")
    if staging.exists():
        raise FileExistsError(f"stale partial GR00T multisource dataset exists: {staging}")

    source_paths = {
        "chess_pick_place_groot_v1": nominal_dataset,
        "chess_pick_place_groot_recovery_v2": recovery_dataset,
        "chess_pick_place_pawn_groot_v1": pawn_dataset,
    }
    sources: dict[str, dict[str, Any]] = {}
    for cohort in contract["cohorts"]:
        label = cohort["dataset_label"]
        receipt, info, episodes, tasks = _verify_source_dataset(
            source_paths[label], cohort
        )
        sources[label] = {
            "cohort": cohort,
            "root": source_paths[label],
            "receipt": receipt,
            "info": info,
            "episodes": episodes,
            "tasks": tasks,
        }

    nominal_info = sources["chess_pick_place_groot_v1"]["info"]
    action_names = nominal_info["features"]["action"]["names"]
    state_names = nominal_info["features"]["observation.state"]["names"]
    for source in sources.values():
        features = source["info"]["features"]
        if features["action"]["names"] != action_names:
            raise ValueError("source action feature names are incompatible")
        if features["observation.state"]["names"] != state_names:
            raise ValueError("source state feature names are incompatible")

    (staging / "data" / "chunk-000").mkdir(parents=True)
    video_root = (
        staging / "videos" / "chunk-000" / "observation.images.front"
    )
    video_root.mkdir(parents=True)
    (staging / "meta").mkdir()
    (staging / "source_lineage").mkdir()

    task_strings: list[str] = []
    for cohort in contract["cohorts"]:
        source = sources[cohort["dataset_label"]]
        for row in sorted(source["tasks"], key=lambda item: int(item["task_index"])):
            task = str(row["task"])
            if task not in task_strings:
                task_strings.append(task)
    task_indices = {task: index for index, task in enumerate(task_strings)}

    episode_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    state_values: list[np.ndarray] = []
    action_values: list[np.ndarray] = []
    timestamp_values: list[np.ndarray] = []
    reward_values: list[np.ndarray] = []
    global_index = 0
    dataset_episode_index = 0

    for cohort in contract["cohorts"]:
        source = sources[cohort["dataset_label"]]
        source_root = source["root"]
        source_video_shape = source["info"]["features"][
            "observation.images.front"
        ]["shape"]
        repetitions = int(cohort["dataset_repetitions_per_source_episode"])
        for source_episode in source["episodes"]:
            source_episode_index = int(source_episode["episode_index"])
            tasks = source_episode.get("tasks", [])
            if len(tasks) != 1:
                raise ValueError("multisource episodes must have one constant task")
            task = str(tasks[0])
            for replica_index in range(repetitions):
                table = pq.read_table(
                    _episode_path(source_root, "data", source_episode_index)
                )
                if table.num_rows != int(source_episode["length"]):
                    raise ValueError("source parquet length differs from episode metadata")
                table = _replace_scalar_column(
                    table, "episode_index", dataset_episode_index
                )
                table = _replace_scalar_column(table, "task_index", task_indices[task])
                index_field = table.schema.field(table.schema.get_field_index("index"))
                index_values = pa.array(
                    np.arange(global_index, global_index + table.num_rows),
                    type=index_field.type,
                )
                table = table.set_column(
                    table.schema.get_field_index("index"), index_field, index_values
                )

                data_path = _episode_path(staging, "data", dataset_episode_index)
                pq.write_table(table, data_path, compression="zstd")

                source_video = _episode_path(
                    source_root, "video", source_episode_index
                )
                destination_video = _episode_path(
                    staging, "video", dataset_episode_index
                )
                _normalize_video(
                    source_video,
                    destination_video,
                    copy_only=source_video_shape == [256, 256, 3],
                )

                state_values.append(
                    np.asarray(table["observation.state"].to_pylist(), dtype=np.float32)
                )
                action_values.append(
                    np.asarray(table["action"].to_pylist(), dtype=np.float32)
                )
                timestamp_values.append(
                    np.asarray(table["timestamp"].to_pylist(), dtype=np.float32)
                )
                reward_values.append(
                    np.asarray(table["next.reward"].to_pylist(), dtype=np.float32)
                )
                episode_rows.append(
                    {
                        "episode_index": dataset_episode_index,
                        "length": table.num_rows,
                        "tasks": [task],
                    }
                )
                lineage = {
                    "dataset_episode_index": dataset_episode_index,
                    "cohort_id": cohort["cohort_id"],
                    "source_dataset_label": cohort["dataset_label"],
                    "source_dataset_receipt_sha256": cohort[
                        "dataset_receipt_sha256"
                    ],
                    "source_episode_index": source_episode_index,
                    "source_episode_replica_index": replica_index,
                    "replica_is_sampling_weight_not_independent_evidence": repetitions
                    > 1,
                    "geometry_class": cohort["geometry_class"],
                    "task": task,
                    "frame_count": table.num_rows,
                    "source_parquet_sha256": sha256_file(
                        _episode_path(source_root, "data", source_episode_index)
                    ),
                    "source_video_sha256": sha256_file(source_video),
                    "derived_parquet_sha256": sha256_file(data_path),
                    "derived_video_sha256": sha256_file(destination_video),
                    "training_rows_evaluator_admitted": True,
                    "physical_authority": False,
                }
                lineage_path = (
                    staging
                    / "source_lineage"
                    / f"episode_{dataset_episode_index:06d}.json"
                )
                _write_json(lineage_path, lineage)
                lineage_rows.append(lineage)
                global_index += table.num_rows
                dataset_episode_index += 1

    dataset_contract = contract["dataset"]
    if dataset_episode_index != int(dataset_contract["derived_dataset_episode_count"]):
        raise ValueError("derived episode count differs from frozen contract")
    if global_index != int(dataset_contract["frame_count"]):
        raise ValueError("derived frame count differs from frozen contract")

    info = json.loads(json.dumps(nominal_info))
    info["robot_type"] = "sim2claw_so101_multisource_simulation"
    info["total_episodes"] = dataset_episode_index
    info["total_frames"] = global_index
    info["total_tasks"] = len(task_strings)
    info["total_videos"] = dataset_episode_index
    info["total_chunks"] = 1
    info["splits"] = {"train": f"0:{dataset_episode_index}"}
    video_feature = info["features"]["observation.images.front"]
    video_feature["shape"] = [256, 256, 3]
    video_feature["info"]["video.height"] = 256
    video_feature["info"]["video.width"] = 256

    _write_json(staging / "meta" / "info.json", info)
    _write_jsonl(staging / "meta" / "episodes.jsonl", episode_rows)
    _write_jsonl(
        staging / "meta" / "tasks.jsonl",
        [
            {"task": task, "task_index": index}
            for index, task in enumerate(task_strings)
        ],
    )
    shutil.copyfile(
        sources["chess_pick_place_groot_v1"]["root"]
        / "meta"
        / "modality.json",
        staging / "meta" / "modality.json",
    )
    (staging / "meta" / "relative_stats.json").write_text("{}", encoding="utf-8")
    _write_json(
        staging / "meta" / "stats.json",
        {
            "action": _stats(np.concatenate(action_values, axis=0)),
            "next.reward": _stats(np.concatenate(reward_values, axis=0)),
            "observation.state": _stats(np.concatenate(state_values, axis=0)),
            "timestamp": _stats(np.concatenate(timestamp_values, axis=0)),
        },
    )

    payload_manifest = {
        path.relative_to(staging).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(staging.rglob("*"))
        if path.is_file()
    }
    action_horizon = int(contract["model"]["action_horizon"])
    effective_start_count = sum(
        int(row["length"]) - action_horizon + 1 for row in episode_rows
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "dataset_contract_id": contract["contract_id"],
        "dataset_contract_sha256": sha256_file(contract_path),
        "format": dataset_contract["format"],
        "unique_source_episode_count": int(
            dataset_contract["unique_source_episode_count"]
        ),
        "derived_dataset_episode_count": dataset_episode_index,
        "frame_count": global_index,
        "task_count": len(task_strings),
        "effective_h16_start_count": effective_start_count,
        "held_out_rows": 0,
        "failed_action_rows": 0,
        "physical_training_rows": 0,
        "all_training_rows_evaluator_admitted": True,
        "source_cohorts": [
            {
                "cohort_id": cohort["cohort_id"],
                "dataset_label": cohort["dataset_label"],
                "dataset_receipt_sha256": cohort["dataset_receipt_sha256"],
                "geometry_class": cohort["geometry_class"],
                "unique_source_episode_count": cohort[
                    "unique_source_episode_count"
                ],
                "dataset_repetitions_per_source_episode": cohort[
                    "dataset_repetitions_per_source_episode"
                ],
            }
            for cohort in contract["cohorts"]
        ],
        "lineage_rows": len(lineage_rows),
        "payload_manifest": payload_manifest,
        "payload_manifest_sha256": canonical_sha256(payload_manifest),
        "training_cannot_promote": True,
        "dataset_builder_declared_success": False,
        "physical_authority": False,
    }
    canonical_receipt = dict(receipt)
    receipt["canonical_payload_sha256"] = canonical_sha256(canonical_receipt)
    _write_json(staging / "dataset_receipt.json", receipt)
    staging.rename(output)
    return receipt


def _video_probe(path: Path) -> dict[str, int]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required to verify GR00T video")
    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,nb_frames,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(process.stdout)["streams"][0]
    numerator, denominator = str(stream["r_frame_rate"]).split("/", 1)
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frames": int(stream["nb_frames"]),
        "fps": int(round(int(numerator) / int(denominator))),
    }


def validate_multisource_episode_alignment(
    *,
    episode_index: int,
    row_count: int,
    parquet_row_count: int,
    parquet_episode_indices: list[int],
    global_indices: list[int],
    expected_global_index: int,
    task_indices: list[int],
    task_count: int,
    video: dict[str, int],
) -> None:
    """Validate one derived parquet/video/task schedule without I/O."""

    if parquet_row_count != row_count:
        raise ValueError("GR00T multisource parquet length drifted")
    if set(parquet_episode_indices) != {episode_index}:
        raise ValueError("GR00T multisource episode index drifted")
    expected_indices = list(
        range(expected_global_index, expected_global_index + row_count)
    )
    if global_indices != expected_indices:
        raise ValueError("GR00T multisource global indices are not contiguous")
    observed_tasks = set(task_indices)
    if len(observed_tasks) != 1 or not observed_tasks <= set(range(task_count)):
        raise ValueError("GR00T multisource task schedule drifted")
    expected_video = {
        "width": 256,
        "height": 256,
        "frames": row_count,
        "fps": 20,
    }
    if video != expected_video:
        raise ValueError(
            f"GR00T multisource video alignment drifted: {episode_index}:{video}"
        )


def preflight_groot_multisource_dataset(
    dataset: Path,
    *,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Verify the composite payload, indices, video alignment, and H16 counts."""

    import pyarrow.parquet as pq

    contract = load_groot_multisource_contract(contract_path)
    receipt_path = dataset / "dataset_receipt.json"
    receipt = _read_json(receipt_path)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise ValueError("unsupported GR00T multisource dataset receipt")
    if receipt.get("dataset_contract_sha256") != sha256_file(contract_path):
        raise ValueError("GR00T multisource dataset used another contract")
    canonical_receipt = dict(receipt)
    recorded_canonical = canonical_receipt.pop("canonical_payload_sha256")
    if canonical_sha256(canonical_receipt) != recorded_canonical:
        raise ValueError("GR00T multisource dataset receipt hash is invalid")

    expected_manifest = receipt["payload_manifest"]
    actual = {
        path.relative_to(dataset).as_posix()
        for path in dataset.rglob("*")
        if path.is_file() and path.name != "dataset_receipt.json"
    }
    if actual != set(expected_manifest):
        raise ValueError("GR00T multisource payload inventory drifted")
    for relative, row in expected_manifest.items():
        path = dataset / relative
        if path.stat().st_size != int(row["size_bytes"]):
            raise ValueError(f"GR00T multisource payload size drifted: {relative}")
        if sha256_file(path) != row["sha256"]:
            raise ValueError(f"GR00T multisource payload hash drifted: {relative}")
    if canonical_sha256(expected_manifest) != receipt["payload_manifest_sha256"]:
        raise ValueError("GR00T multisource manifest hash is invalid")

    info = _read_json(dataset / "meta" / "info.json")
    episodes = _read_jsonl(dataset / "meta" / "episodes.jsonl")
    tasks = _read_jsonl(dataset / "meta" / "tasks.jsonl")
    expected_episodes = int(contract["dataset"]["derived_dataset_episode_count"])
    expected_frames = int(contract["dataset"]["frame_count"])
    if len(episodes) != expected_episodes or int(info["total_episodes"]) != expected_episodes:
        raise ValueError("GR00T multisource episode count drifted")
    if int(info["total_frames"]) != expected_frames:
        raise ValueError("GR00T multisource frame count drifted")
    if len(tasks) != int(contract["dataset"]["task_count"]):
        raise ValueError("GR00T multisource task count drifted")

    global_index = 0
    effective_starts = 0
    video_frames = 0
    for episode in episodes:
        episode_index = int(episode["episode_index"])
        table = pq.read_table(_episode_path(dataset, "data", episode_index))
        row_count = int(episode["length"])
        indices = table["index"].to_pylist()
        video = _video_probe(_episode_path(dataset, "video", episode_index))
        validate_multisource_episode_alignment(
            episode_index=episode_index,
            row_count=row_count,
            parquet_row_count=table.num_rows,
            parquet_episode_indices=table["episode_index"].to_pylist(),
            global_indices=indices,
            expected_global_index=global_index,
            task_indices=table["task_index"].to_pylist(),
            task_count=len(tasks),
            video=video,
        )
        global_index += row_count
        video_frames += video["frames"]
        effective_starts += row_count - int(contract["model"]["action_horizon"]) + 1

    if global_index != expected_frames or video_frames != expected_frames:
        raise ValueError("GR00T multisource aggregate alignment drifted")
    if effective_starts != int(
        contract["dataset"]["expected_effective_h16_start_count"]
    ):
        raise ValueError("GR00T multisource H16 denominator drifted")
    if receipt.get("held_out_rows") != 0 or receipt.get("failed_action_rows") != 0:
        raise ValueError("excluded rows entered the GR00T multisource dataset")
    if receipt.get("physical_training_rows") != 0:
        raise ValueError("physical quarantine rows entered the GR00T multisource dataset")

    report = {
        "schema_version": PREFLIGHT_SCHEMA,
        "passed": True,
        "dataset_contract_sha256": sha256_file(contract_path),
        "dataset_receipt_sha256": sha256_file(receipt_path),
        "dataset_payload_manifest_sha256": receipt["payload_manifest_sha256"],
        "episode_count": expected_episodes,
        "unique_source_episode_count": int(
            contract["dataset"]["unique_source_episode_count"]
        ),
        "frame_count": expected_frames,
        "video_frame_count": video_frames,
        "task_count": len(tasks),
        "effective_h16_start_count": effective_starts,
        "action_target_slot_count": effective_starts
        * int(contract["model"]["action_horizon"]),
        "action_scalar_count": effective_starts
        * int(contract["model"]["action_horizon"])
        * int(contract["dataset"]["action_dimension"]),
        "held_out_rows": 0,
        "failed_action_rows": 0,
        "physical_training_rows": 0,
        "training_started": False,
        "model_queries": 0,
        "training_cannot_promote": True,
    }
    report["canonical_payload_sha256"] = canonical_sha256(report)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output_path, report)
    return report
