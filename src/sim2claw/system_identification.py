"""Staged, evaluator-gated system identification for recorded-action replay.

The fitting surface is intentionally bounded.  Whole episodes are frozen into
train and held-out splits before optimization; official ``mujoco.sysid`` is
used only when its pinned extra imports and executes; and the local fallback is
restricted to parameters declared smooth and fallback-supported.
"""

from __future__ import annotations

import copy
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import mujoco
import numpy as np

from .paths import REPO_ROOT
from .recorded_replay import (
    RecordedEpisode,
    ReplayContractError,
    ReplayRangeError,
    calculate_metrics,
    load_recorded_episode,
    load_sysid_config,
    inspect_episode_joint_limits,
    nominal_parameter_values,
    portable_content_identity,
    replay_residual_blocks,
    sha256_file,
    simulate_and_align,
    validate_parameter_values,
    write_replay_receipt,
)


CAPABILITY_SCHEMA = "sim2claw.mujoco_sysid_capability.v1"
SPLIT_SCHEMA = "sim2claw.sysid_episode_split.v1"
FIT_RECEIPT_SCHEMA = "sim2claw.sysid_fit_receipt.v1"
INPUT_CAPABILITY_SCHEMA = "sim2claw.sysid_input_capability.v1"

OFFICIAL_REQUIRED_EXPORTS = (
    "Parameter",
    "ParameterDict",
    "TimeSeries",
    "ModelSequences",
    "build_residual_fn",
    "optimize",
)


class SystemIdentificationError(RuntimeError):
    """A staged fit cannot proceed without weakening its declared contract."""


class StageDataError(SystemIdentificationError):
    """A parameter stage has no measured observable that can constrain it."""


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _portable_repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def mujoco_sysid_capability(*, exercise: bool = False) -> dict[str, Any]:
    """Inspect the pinned official toolbox without turning presence into use."""

    version = importlib.metadata.version("mujoco")
    requirements = importlib.metadata.metadata("mujoco").get_all("Requires-Dist") or []
    declared_extra_requirements = sorted(
        requirement for requirement in requirements if 'extra == "sysid"' in requirement
    )
    module_present = importlib.util.find_spec("mujoco.sysid") is not None
    importable = False
    compatible = False
    missing_exports: list[str] = list(OFFICIAL_REQUIRED_EXPORTS)
    import_error: str | None = None
    if module_present:
        try:
            from mujoco import sysid

            importable = True
            missing_exports = [
                name for name in OFFICIAL_REQUIRED_EXPORTS if not hasattr(sysid, name)
            ]
            compatible = not missing_exports
        except Exception as error:  # pragma: no cover - environment-dependent path
            import_error = f"{type(error).__name__}: {error}"
    exact_compatible = compatible and version == "3.10.0"
    exercise_report: dict[str, Any] | None = None
    exercise_error: str | None = None
    if exercise and exact_compatible:
        try:
            exercise_report = exercise_official_sysid()
        except Exception as error:  # pragma: no cover - environment-dependent path
            exercise_error = f"{type(error).__name__}: {error}"
    actionable = None
    if not module_present:
        actionable = "install the pinned MuJoCo distribution containing mujoco.sysid"
    elif not importable:
        actionable = (
            "sync the declared pinned extra with `uv sync --frozen`; "
            "pyproject.toml must retain mujoco[sysid]==3.10.0"
        )
    elif missing_exports:
        actionable = (
            "keep fitting fail-closed and reconcile the adapter against the pinned "
            f"MuJoCo {version} API"
        )
    elif version != "3.10.0":
        actionable = (
            "sync the exact pinned toolbox with `uv sync --frozen`; "
            f"found MuJoCo {version}, expected 3.10.0"
        )
    elif exercise_error:
        actionable = (
            "keep official fitting disabled and inspect the bounded exercise error; "
            "the local fallback remains smooth-parameter-only"
        )
    return {
        "schema_version": CAPABILITY_SCHEMA,
        "distribution": "mujoco",
        "version": version,
        "expected_version": "3.10.0",
        "version_matches_pin": version == "3.10.0",
        "module": "mujoco.sysid",
        "module_present": module_present,
        "declared_sysid_extra_requirements": declared_extra_requirements,
        "importable": importable,
        "compatible": exact_compatible,
        "required_exports": list(OFFICIAL_REQUIRED_EXPORTS),
        "missing_exports": missing_exports,
        "import_error": import_error,
        "exercise_error": exercise_error,
        "actionable_resolution": actionable,
        "primary_documentation": [
            "https://github.com/google-deepmind/mujoco/blob/3.10.0/python/mujoco/sysid/README.md",
            "https://mujoco.readthedocs.io/en/3.10.0/changelog.html",
        ],
        "local_fallback": {
            "implementation": "local_bounded_gauss_newton",
            "deterministic": True,
            "allowed_only_when_parameter_smooth": True,
            "allowed_only_when_fallback_supported": True,
            "contact_or_object_parameters_supported": False,
            "official_sysid_claim": False,
        },
        "official_surface_exercised": bool(
            exact_compatible
            and exercise_report
            and exercise_report.get("passed")
        ),
        "exercise": exercise_report,
        "claim": (
            "official_sysid_exercised"
            if exact_compatible and exercise_report and exercise_report.get("passed")
            else "capability_inspection_only"
        ),
    }


def write_mujoco_sysid_capability(
    output_path: Path,
    *,
    exercise: bool = False,
) -> dict[str, Any]:
    report = mujoco_sysid_capability(exercise=exercise)
    _atomic_json(output_path.resolve(), report)
    result = copy.deepcopy(report)
    result["report_path"] = str(output_path.resolve())
    result["report_sha256"] = sha256_file(output_path.resolve())
    return result


def exercise_official_sysid() -> dict[str, Any]:
    """Execute the pinned optimizer on a bounded one-parameter smooth probe."""

    from mujoco import sysid

    target = 0.375
    params = sysid.ParameterDict()
    params.add(
        sysid.Parameter(
            "probe",
            nominal=0.8,
            min_value=-1.0,
            max_value=1.0,
        )
    )

    def residual_fn(vector: np.ndarray, _: Any) -> tuple[list[np.ndarray], None, None]:
        array = np.asarray(vector, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2 or array.shape[0] != 1:
            raise ValueError("official probe received an invalid parameter batch")
        return [array - target], None, None

    optimizer_output = io.StringIO()
    with contextlib.redirect_stdout(optimizer_output):
        fitted, result = sysid.optimize(
            initial_params=params,
            residual_fn=residual_fn,
            optimizer="mujoco",
            verbose=False,
            max_iters=20,
        )
    fitted_value = float(fitted["probe"].value[0])
    return {
        "backend": "mujoco.sysid.optimize",
        "optimizer": "mujoco",
        "target": target,
        "fitted": fitted_value,
        "absolute_error": abs(fitted_value - target),
        "passed": abs(fitted_value - target) <= 1e-8,
        "result_has_jacobian": getattr(result, "jac", None) is not None,
        "optimizer_trace_line_count": len(optimizer_output.getvalue().splitlines()),
    }


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _square_column(value: Any) -> str | None:
    square = str(value or "").lower()
    if (
        len(square) == 2
        and square[0] in "abcdefgh"
        and square[1] in "12345678"
    ):
        return square[0]
    return None


def _catalog_episode_entry(episode: Mapping[str, Any]) -> dict[str, Any]:
    source_square = str(episode.get("source_square") or "").lower()
    destination_square = str(episode.get("destination_square") or "").lower()
    source_column = _square_column(source_square)
    destination_column = _square_column(destination_square)
    source_path = str(
        episode.get("source_path")
        or Path(str(episode["assets"]["samples"])).parent
    )
    assets = episode.get("assets") or {}
    return {
        "episode_id": str(episode["recording_id"]),
        "source_kind": (
            "physical_recording" if assets.get("receipt") else "canonical_episode"
        ),
        "source_path": source_path,
        "source_receipt_path": assets.get("receipt"),
        "source_receipt_sha256": episode.get("receipt_sha256"),
        "source_samples_path": assets.get("samples"),
        "source_samples_sha256": str(episode["samples_sha256"]),
        "source_square": source_square or None,
        "destination_square": destination_square or None,
        "source_column": source_column,
        "destination_column": destination_column,
        "proof_class": str(episode.get("proof_class") or "unknown"),
        "metadata_status": episode.get("metadata_status"),
        "column_adjudication": copy.deepcopy(episode.get("column_adjudication")),
    }


def _hash_fraction(seed: str, episode_id: str) -> float:
    digest = hashlib.sha256(f"{seed}:{episode_id}".encode("utf-8")).digest()
    return int.from_bytes(digest, "big") / float(2**256)


_SPLIT_DIGEST_FIELDS = (
    "schema_version",
    "split_id",
    "frozen",
    "owner",
    "unit",
    "strategy",
    "held_out_column",
    "seed",
    "holdout_fraction",
    "source_catalog",
    "sysid_config",
    "split_authority",
    "split_counts",
    "episodes",
    "leakage_guards",
    "created_at",
)


def _split_assignment_digest(manifest: Mapping[str, Any]) -> str:
    payload = {
        field: copy.deepcopy(manifest.get(field)) for field in _SPLIT_DIGEST_FIELDS
    }
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _split_authority_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    split = config["split"]
    config_sha256 = config.get("_config_sha256")
    if not _is_sha256(config_sha256):
        raise SystemIdentificationError(
            "split validation requires a loaded, hash-bound sysid config"
        )
    return {
        "config_id": config["config_id"],
        "config_sha256": config_sha256,
        "owner": split["owner"],
        "unit": split["unit"],
        "allowed_strategies": list(split["allowed_strategies"]),
        "default_strategy": split["default_strategy"],
        "seed": split["seed"],
        "holdout_fraction": float(split["holdout_fraction"]),
        "leave_one_column_out_rule": split["leave_one_column_out_rule"],
    }


def _validate_column_adjudication(entry: Mapping[str, Any]) -> None:
    if entry.get("metadata_status") != "reviewed_adjudicated":
        raise SystemIdentificationError(
            "leave-one-column-out requires reviewed column adjudication lineage "
            f"and metadata_status=reviewed_adjudicated for episode {entry.get('episode_id')}"
        )
    adjudication = entry.get("column_adjudication")
    if not isinstance(adjudication, Mapping):
        raise SystemIdentificationError(
            "leave-one-column-out requires reviewed column adjudication lineage "
            f"for episode {entry.get('episode_id')}"
        )
    required_text = ("decision_id", "reviewer", "reviewed_at")
    if adjudication.get("status") != "reviewed" or any(
        not str(adjudication.get(field) or "").strip() for field in required_text
    ):
        raise SystemIdentificationError(
            "leave-one-column-out column adjudication must be reviewed with "
            f"decision lineage for episode {entry.get('episode_id')}"
        )
    if not _is_sha256(adjudication.get("evidence_sha256")):
        raise SystemIdentificationError(
            "leave-one-column-out column adjudication requires a bound evidence hash "
            f"for episode {entry.get('episode_id')}"
        )
    if (
        str(adjudication.get("source_square") or "").lower()
        != str(entry.get("source_square") or "").lower()
        or str(adjudication.get("destination_square") or "").lower()
        != str(entry.get("destination_square") or "").lower()
    ):
        raise SystemIdentificationError(
            "leave-one-column-out adjudicated squares do not match the frozen episode "
            f"for {entry.get('episode_id')}"
        )


def freeze_episode_split(
    catalog_path: Path,
    config_path: Path,
    output_path: Path,
    *,
    strategy: str = "deterministic_hash",
    held_out_column: str | None = None,
) -> dict[str, Any]:
    """Freeze a whole-episode split owned by the declared evaluator."""

    catalog_path = catalog_path.resolve()
    config_path = config_path.resolve()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    config = load_sysid_config(config_path)
    split_config = config["split"]
    entries = [_catalog_episode_entry(episode) for episode in catalog["episodes"]]
    if not entries:
        raise SystemIdentificationError("catalog contains no episodes")
    if strategy not in {"deterministic_hash", "leave_one_column_out"}:
        raise SystemIdentificationError(f"unsupported split strategy: {strategy}")
    normalized_column: str | None = None
    if strategy == "leave_one_column_out":
        normalized_column = str(held_out_column or "").lower()
        if normalized_column not in tuple("abcdefgh"):
            raise SystemIdentificationError(
                "leave-one-column-out requires --held-out-column a through h"
            )
        incomplete = [
            entry["episode_id"]
            for entry in entries
            if entry.get("source_column") is None
            or entry.get("destination_column") is None
        ]
        if incomplete:
            raise SystemIdentificationError(
                "leave-one-column-out requires source and destination column "
                f"metadata for every episode: {incomplete}"
            )
        for entry in entries:
            _validate_column_adjudication(entry)
    for entry in entries:
        if strategy == "deterministic_hash":
            fraction = _hash_fraction(
                str(split_config["seed"]), str(entry["episode_id"])
            )
            entry["split"] = (
                "held_out"
                if fraction < float(split_config["holdout_fraction"])
                else "train"
            )
            entry["assignment_fraction"] = fraction
        else:
            touched_columns = {
                entry.get("source_column"), entry.get("destination_column")
            }
            entry["split"] = (
                "held_out" if normalized_column in touched_columns else "train"
            )
            entry["assignment_fraction"] = None
    split_counts = {
        name: sum(entry["split"] == name for entry in entries)
        for name in ("train", "held_out")
    }
    if not all(split_counts.values()):
        raise SystemIdentificationError(
            f"split must retain train and held_out episodes: {split_counts}"
        )
    manifest = {
        "schema_version": SPLIT_SCHEMA,
        "split_id": f"{catalog.get('catalog_id', catalog_path.stem)}:{strategy}",
        "frozen": True,
        "owner": split_config["owner"],
        "unit": "whole_episode",
        "strategy": strategy,
        "held_out_column": normalized_column,
        "seed": split_config["seed"],
        "holdout_fraction": (
            float(split_config["holdout_fraction"])
            if strategy == "deterministic_hash"
            else None
        ),
        "source_catalog": {
            "path": _portable_repo_path(catalog_path),
            "sha256": sha256_file(catalog_path),
            "catalog_id": catalog.get("catalog_id"),
        },
        "sysid_config": {
            "path": _portable_repo_path(config_path),
            "sha256": sha256_file(config_path),
            "config_id": config["config_id"],
        },
        "split_authority": _split_authority_from_config(config),
        "split_counts": split_counts,
        "episodes": sorted(entries, key=lambda entry: str(entry["episode_id"])),
        "leakage_guards": {
            "episode_id_disjoint": True,
            "source_samples_sha256_disjoint": True,
            "row_level_split_forbidden": True,
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    manifest["assignment_digest_sha256"] = _split_assignment_digest(manifest)
    validate_split_manifest(manifest, config=config)
    _atomic_json(output_path.resolve(), manifest)
    result = copy.deepcopy(manifest)
    result["manifest_path"] = str(output_path.resolve())
    result["manifest_sha256"] = sha256_file(output_path.resolve())
    return result


def validate_split_manifest(
    manifest: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
) -> None:
    if manifest.get("schema_version") != SPLIT_SCHEMA:
        raise SystemIdentificationError("unsupported episode split schema")
    if manifest.get("frozen") is not True or manifest.get("unit") != "whole_episode":
        raise SystemIdentificationError("split must be frozen at whole-episode scope")
    if not str(manifest.get("owner") or "").strip():
        raise SystemIdentificationError("split owner is required")
    expected_authority = _split_authority_from_config(config)
    if manifest.get("split_authority") != expected_authority:
        raise SystemIdentificationError(
            "split authority drifted from the hash-bound sysid config"
        )
    if (
        manifest.get("owner") != expected_authority["owner"]
        or manifest.get("unit") != expected_authority["unit"]
        or manifest.get("seed") != expected_authority["seed"]
    ):
        raise SystemIdentificationError(
            "split owner/unit/seed drifted from the hash-bound sysid config"
        )
    strategy = str(manifest.get("strategy") or "")
    if strategy not in {"deterministic_hash", "leave_one_column_out"}:
        raise SystemIdentificationError("split strategy is unsupported")
    if strategy not in expected_authority["allowed_strategies"]:
        raise SystemIdentificationError(
            "split strategy is not allowed by the hash-bound sysid config"
        )
    seed = str(manifest.get("seed") or "")
    if not seed:
        raise SystemIdentificationError("split seed is required")
    if strategy == "deterministic_hash":
        if manifest.get("held_out_column") is not None:
            raise SystemIdentificationError(
                "deterministic split cannot declare a held-out column"
            )
        try:
            holdout_fraction = float(manifest["holdout_fraction"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemIdentificationError(
                "deterministic split holdout_fraction is required"
            ) from error
        if not math.isfinite(holdout_fraction) or not 0.0 < holdout_fraction < 1.0:
            raise SystemIdentificationError(
                "deterministic split holdout_fraction must be between zero and one"
            )
        if holdout_fraction != expected_authority["holdout_fraction"]:
            raise SystemIdentificationError(
                "split holdout_fraction drifted from the hash-bound sysid config"
            )
    else:
        held_out_column = str(manifest.get("held_out_column") or "").lower()
        if held_out_column not in tuple("abcdefgh"):
            raise SystemIdentificationError(
                "leave-one-column-out requires a frozen held_out_column"
            )
        if manifest.get("holdout_fraction") is not None:
            raise SystemIdentificationError(
                "leave-one-column-out cannot declare holdout_fraction"
            )
    for binding_name in ("source_catalog", "sysid_config"):
        binding = manifest.get(binding_name)
        if not isinstance(binding, Mapping) or not _is_sha256(binding.get("sha256")):
            raise SystemIdentificationError(
                f"split {binding_name} content binding is incomplete"
            )
    if (
        manifest["sysid_config"].get("config_id") != expected_authority["config_id"]
        or manifest["sysid_config"].get("sha256")
        != expected_authority["config_sha256"]
    ):
        raise SystemIdentificationError(
            "split sysid_config binding drifted from supplied config authority"
        )
    expected_split_id = (
        f"{manifest['source_catalog'].get('catalog_id')}:{strategy}"
    )
    if manifest.get("split_id") != expected_split_id:
        raise SystemIdentificationError("split_id drifted from catalog and strategy")
    entries = manifest.get("episodes")
    if not isinstance(entries, list) or not entries:
        raise SystemIdentificationError("split requires episode entries")
    episode_ids = [str(entry.get("episode_id") or "") for entry in entries]
    if episode_ids != sorted(episode_ids):
        raise SystemIdentificationError("split episodes must remain sorted by episode_id")
    seen_ids: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    counts = {"train": 0, "held_out": 0}
    for entry in entries:
        split = str(entry.get("split") or "")
        if split not in counts:
            raise SystemIdentificationError("episode split must be train or held_out")
        episode_id = str(entry.get("episode_id") or "")
        source_hash = str(entry.get("source_samples_sha256") or "")
        if not episode_id or not _is_sha256(source_hash):
            raise SystemIdentificationError("split episode identity/hash is incomplete")
        source_kind = entry.get("source_kind")
        if source_kind not in {"physical_recording", "canonical_episode"}:
            raise SystemIdentificationError(
                f"split episode {episode_id} source_kind is required"
            )
        if source_kind == "physical_recording":
            portable_paths = (
                entry.get("source_path"),
                entry.get("source_receipt_path"),
                entry.get("source_samples_path"),
            )
            if any(
                not str(path or "").strip() or Path(str(path)).is_absolute()
                for path in portable_paths
            ) or not _is_sha256(entry.get("source_receipt_sha256")):
                raise SystemIdentificationError(
                    f"physical episode {episode_id} requires portable catalog/receipt/sample provenance"
                )
            if entry.get("source_samples_sha256") != source_hash:
                raise SystemIdentificationError(
                    f"physical episode {episode_id} sample provenance hash drifted"
                )
        if episode_id in seen_ids:
            raise SystemIdentificationError(
                f"episode leakage: {episode_id} appears more than once"
            )
        if source_hash in seen_hashes:
            raise SystemIdentificationError(
                "source-content leakage: identical samples appear in multiple entries"
            )
        seen_ids[episode_id] = split
        seen_hashes[source_hash] = split
        counts[split] += 1
        source_square = entry.get("source_square")
        destination_square = entry.get("destination_square")
        expected_source_column = _square_column(source_square)
        expected_destination_column = _square_column(destination_square)
        if entry.get("source_column") != expected_source_column or entry.get(
            "destination_column"
        ) != expected_destination_column:
            raise SystemIdentificationError(
                f"episode {episode_id} column fields drifted from its frozen squares"
            )
        if strategy == "deterministic_hash":
            expected_fraction = _hash_fraction(seed, episode_id)
            declared_fraction = entry.get("assignment_fraction")
            if (
                isinstance(declared_fraction, bool)
                or not isinstance(declared_fraction, (int, float))
                or float(declared_fraction) != expected_fraction
            ):
                raise SystemIdentificationError(
                    f"episode {episode_id} deterministic assignment_fraction drifted"
                )
            expected_split = (
                "held_out" if expected_fraction < holdout_fraction else "train"
            )
        else:
            if expected_source_column is None or expected_destination_column is None:
                raise SystemIdentificationError(
                    "leave-one-column-out requires valid source and destination squares "
                    f"for episode {episode_id}"
                )
            _validate_column_adjudication(entry)
            if entry.get("assignment_fraction") is not None:
                raise SystemIdentificationError(
                    "leave-one-column-out assignment_fraction must remain null"
                )
            expected_split = (
                "held_out"
                if str(manifest["held_out_column"]) in {
                    expected_source_column,
                    expected_destination_column,
                }
                else "train"
            )
        if split != expected_split:
            raise SystemIdentificationError(
                f"episode {episode_id} assignment drifted from the frozen {strategy} algorithm"
            )
    if not all(counts.values()):
        raise SystemIdentificationError(
            f"split requires non-empty train and held_out sets: {counts}"
        )
    declared_counts = manifest.get("split_counts")
    if not isinstance(declared_counts, Mapping) or set(declared_counts) != set(counts):
        raise SystemIdentificationError("split_counts must declare train and held_out")
    if any(
        isinstance(declared_counts.get(name), bool)
        or not isinstance(declared_counts.get(name), int)
        or declared_counts[name] != count
        for name, count in counts.items()
    ):
        raise SystemIdentificationError("split_counts do not match episode assignments")
    leakage_guards = manifest.get("leakage_guards") or {}
    if any(
        leakage_guards.get(name) is not True
        for name in (
            "episode_id_disjoint",
            "source_samples_sha256_disjoint",
            "row_level_split_forbidden",
        )
    ):
        raise SystemIdentificationError("split leakage guards must be frozen true")
    declared_digest = manifest.get("assignment_digest_sha256")
    if not _is_sha256(declared_digest):
        raise SystemIdentificationError("split assignment digest is required")
    expected_digest = _split_assignment_digest(manifest)
    if declared_digest != expected_digest:
        raise SystemIdentificationError("split assignment digest drifted")


def load_split_manifest(
    path: Path,
    *,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    path = path.resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_split_manifest(manifest, config=config)
    manifest["_manifest_path"] = str(path)
    manifest["_manifest_sha256"] = sha256_file(path)
    return manifest


def _aggregate_joint_limit_reports(
    episode_reports: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sections = (
        "initial_measured_state",
        "measured_trajectory",
        "recorded_commands",
    )
    aggregate: dict[str, Any] = {}
    for section in sections:
        reports = [
            report["joint_limit_validation"][section]
            for report in episode_reports
            if isinstance(report.get("joint_limit_validation"), Mapping)
            and isinstance(report["joint_limit_validation"].get(section), Mapping)
        ]
        per_joint_names = sorted(
            {
                name
                for report in reports
                for name in (report.get("per_joint") or {})
            }
        )
        aggregate[section] = {
            "audited_episode_count": len(reports),
            "row_count": sum(int(report.get("row_count", 0)) for report in reports),
            "violating_row_count": sum(
                int(report.get("violating_row_count", 0)) for report in reports
            ),
            "violating_joint_value_count": sum(
                int(report.get("violating_joint_value_count", 0))
                for report in reports
            ),
            "maximum_exceedance": max(
                (float(report.get("maximum_exceedance", 0.0)) for report in reports),
                default=0.0,
            ),
            "per_joint": {
                name: {
                    "violating_row_count": sum(
                        int((report.get("per_joint") or {}).get(name, {}).get(
                            "violating_row_count", 0
                        ))
                        for report in reports
                    ),
                    "maximum_exceedance": max(
                        (
                            float((report.get("per_joint") or {}).get(name, {}).get(
                                "maximum_exceedance", 0.0
                            ))
                            for report in reports
                        ),
                        default=0.0,
                    ),
                }
                for name in per_joint_names
            },
        }
    audit_complete = bool(episode_reports) and all(
        aggregate[section]["audited_episode_count"] == len(episode_reports)
        and aggregate[section]["row_count"] > 0
        for section in sections
    )
    aggregate["audit_complete"] = audit_complete
    aggregate["all_audited_values_within_limits"] = audit_complete and all(
        aggregate[section]["violating_joint_value_count"] == 0
        for section in sections
    )
    return aggregate


def inspect_recording_catalog_inputs(
    catalog_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    config_path: Path | None = None,
    inspection_scope: str = "auto",
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Strictly parse and range-audit physical inputs without interpreting video."""

    catalog_path = catalog_path.resolve()
    repo_root = repo_root.resolve()
    config_path = (
        config_path.resolve()
        if config_path is not None
        else (REPO_ROOT / "configs/sysid/recorded_action_sysid_v1.json").resolve()
    )
    config = load_sysid_config(config_path)
    transform_adapter = config.get("physical_adapter") or {}
    transform = transform_adapter.get("joint_transform") or {}
    transform_approved = transform.get("calibration_approved") is True
    if not repo_root.is_dir():
        raise SystemIdentificationError(f"inspection repo root is not a directory: {repo_root}")
    allowed_scopes = {
        "auto",
        "canonical_checkout",
        "isolated_codex_worktree",
        "explicit_repo_root",
    }
    if inspection_scope not in allowed_scopes:
        raise SystemIdentificationError(
            f"unsupported inspection scope {inspection_scope!r}: {sorted(allowed_scopes)}"
        )
    if inspection_scope == "auto":
        if repo_root == REPO_ROOT.resolve() and {
            ".codex",
            "worktrees",
        }.issubset(repo_root.parts):
            scope_kind = "isolated_codex_worktree"
        elif repo_root == REPO_ROOT.resolve():
            scope_kind = "project_checkout"
        else:
            scope_kind = "explicit_repo_root"
    elif inspection_scope == "canonical_checkout":
        # A caller-supplied path cannot, by itself, establish that it is the
        # coordinator's canonical checkout.  Preserve the legacy CLI spelling
        # as an explicit-root request while making the receipt refuse that
        # stronger identity claim.
        scope_kind = "explicit_repo_root"
    else:
        scope_kind = inspection_scope
    canonical_checkout_inspected = False
    if scope_kind == "isolated_codex_worktree" and not {
        ".codex",
        "worktrees",
    }.issubset(repo_root.parts):
        raise SystemIdentificationError(
            "isolated_codex_worktree scope requires a .codex/worktrees repo_root"
        )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    episode_reports: list[dict[str, Any]] = []
    for episode in catalog["episodes"]:
        required_assets = {
            "recording_receipt": str(episode["assets"]["receipt"]),
            "samples": str(episode["assets"]["samples"]),
        }
        bound_assets = {
            "recording_receipt": {
                "path": required_assets["recording_receipt"],
                "expected_sha256": str(episode.get("receipt_sha256") or ""),
                "required_for_joint_replay": True,
            },
            "samples": {
                "path": required_assets["samples"],
                "expected_sha256": str(episode.get("samples_sha256") or ""),
                "required_for_joint_replay": True,
            },
            "overhead_video": {
                "path": str(episode["assets"].get("overhead_video") or ""),
                "expected_sha256": str(
                    episode.get("overhead_video_sha256") or ""
                ),
                "required_for_joint_replay": False,
            },
        }
        integrity: dict[str, dict[str, Any]] = {}
        for name, descriptor in bound_assets.items():
            path_text = descriptor["path"]
            expected_sha256 = descriptor["expected_sha256"]
            bound = bool(path_text and len(expected_sha256) == 64)
            path = repo_root / path_text if path_text else None
            present = bool(path and path.is_file())
            actual_sha256 = sha256_file(path) if present and path is not None else None
            integrity[name] = {
                **descriptor,
                "catalog_bound": bound,
                "present": present,
                "actual_sha256": actual_sha256,
                "matches_catalog": bool(
                    bound and actual_sha256 and actual_sha256 == expected_sha256
                ),
            }
        availability = {
            name: integrity[name]["present"] for name in required_assets
        }
        required_integrity_valid = all(
            integrity[name]["matches_catalog"] for name in required_assets
        )
        receipt_chain_valid = False
        receipt_chain_error: str | None = None
        if required_integrity_valid:
            try:
                receipt = json.loads(
                    (repo_root / required_assets["recording_receipt"]).read_text(
                        encoding="utf-8"
                    )
                )
                if receipt.get("mode") != "physical_follower":
                    raise ValueError("receipt mode is not physical_follower")
                if receipt.get("recording_id") != episode["recording_id"]:
                    raise ValueError("receipt recording_id does not match catalog")
                if receipt.get("samples_sha256") != episode.get("samples_sha256"):
                    raise ValueError("receipt samples_sha256 does not match catalog")
                receipt_chain_valid = True
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                receipt_chain_error = f"{type(error).__name__}: {error}"
        elif all(availability.values()):
            receipt_chain_error = "required asset hash does not match catalog"
        sample_semantics_valid = False
        sample_semantics_error: str | None = None
        joint_limit_validation: dict[str, Any] | None = None
        provenance_chain_complete = False
        if required_integrity_valid and receipt_chain_valid:
            source_directory = repo_root / str(
                episode.get("source_path")
                or Path(required_assets["samples"]).parent
            )
            try:
                catalog_relative_path = catalog_path.relative_to(repo_root).as_posix()
            except ValueError:
                catalog_relative_path = None
            source_provenance = {
                "episode_id": episode["recording_id"],
                "catalog": {
                    "kind": (
                        "repo_relative"
                        if catalog_relative_path is not None
                        else "content_addressed"
                    ),
                    "path": catalog_relative_path,
                    "_runtime_path": str(catalog_path),
                    "catalog_id": catalog.get("catalog_id"),
                    "sha256": sha256_file(catalog_path),
                },
                "recording_receipt": {
                    "kind": "repo_relative",
                    "path": required_assets["recording_receipt"],
                    "sha256": str(episode.get("receipt_sha256") or ""),
                },
                "samples": {
                    "kind": "repo_relative",
                    "path": required_assets["samples"],
                    "sha256": str(episode.get("samples_sha256") or ""),
                },
            }
            try:
                parsed_episode = load_recorded_episode(
                    source_directory,
                    config,
                    source_provenance=source_provenance,
                )
                sample_semantics_valid = True
                joint_limit_validation = inspect_episode_joint_limits(
                    parsed_episode,
                    config,
                    model_base_directory=config_path.parent,
                )
                provenance_chain_complete = bool(
                    parsed_episode.source_provenance.get("chain_complete")
                )
            except ReplayRangeError as error:
                sample_semantics_valid = True
                sample_semantics_error = f"{type(error).__name__}: {error}"
                joint_limit_validation = dict(error.diagnostics)
                provenance_chain_complete = True
            except (OSError, TypeError, ValueError, ReplayContractError) as error:
                sample_semantics_error = f"{type(error).__name__}: {error}"
        range_valid = bool(
            joint_limit_validation
            and joint_limit_validation.get("all_within_limits")
        )
        ready_for_joint_replay = bool(
            required_integrity_valid
            and receipt_chain_valid
            and sample_semantics_valid
            and range_valid
            and provenance_chain_complete
            and transform_approved
        )
        episode_reports.append(
            {
                "episode_id": episode["recording_id"],
                "proof_class": episode.get("proof_class"),
                "metadata_status": episode.get("metadata_status"),
                "required_assets": required_assets,
                "asset_availability": availability,
                "catalog_bound_asset_integrity": integrity,
                "receipt_samples_chain_valid": receipt_chain_valid,
                "receipt_samples_chain_error": receipt_chain_error,
                "sample_semantics_valid": sample_semantics_valid,
                "sample_semantics_error": sample_semantics_error,
                "joint_limit_validation": joint_limit_validation,
                "joint_transform_calibration_approved": transform_approved,
                "full_catalog_receipt_sample_provenance_bound": (
                    provenance_chain_complete
                ),
                "ready_for_joint_replay": ready_for_joint_replay,
                "measured_observables": {
                    "command_joint_position": (
                        "strictly_parsed_physical_source_schema"
                        if sample_semantics_valid
                        else "unverified_payload_missing_or_invalid"
                    ),
                    "joint_position": (
                        "strictly_parsed_physical_source_schema"
                        if sample_semantics_valid
                        else "unverified_payload_missing_or_invalid"
                    ),
                    "gripper_position": (
                        "derivable_from_measured_gripper_joint"
                        if sample_semantics_valid
                        else "unverified_payload_missing_or_invalid"
                    ),
                    "end_effector_position": "unavailable_not_recorded",
                    "end_effector_orientation": "unavailable_not_recorded",
                    "pawn_position": "unavailable_no_reviewed_metric_pose_source",
                    "pawn_orientation": "unavailable_no_reviewed_metric_pose_source",
                    "initial_object_state": (
                        "unavailable_no_measured_body_free_joint_pose_binding"
                    ),
                    "contact_active": "unavailable_not_recorded",
                    "contact_force": "unavailable_not_recorded",
                },
            }
        )
    ready_count = sum(report["ready_for_joint_replay"] for report in episode_reports)
    semantic_valid_count = sum(
        report["sample_semantics_valid"] for report in episode_reports
    )
    range_valid_count = sum(
        bool(
            report.get("joint_limit_validation")
            and report["joint_limit_validation"].get("all_within_limits")
        )
        for report in episode_reports
    )
    provenance_complete_count = sum(
        report["full_catalog_receipt_sample_provenance_bound"]
        for report in episode_reports
    )
    aggregate_joint_limits = _aggregate_joint_limit_reports(episode_reports)
    metadata_conflict_count = sum(
        report.get("metadata_status") == "conflict_folder_label_vs_receipt"
        for report in episode_reports
    )
    missing_paths = sorted(
        {
            path
            for report in episode_reports
            for name, path in report["required_assets"].items()
            if not report["asset_availability"][name]
        }
    )
    mismatched_required_paths = sorted(
        {
            descriptor["path"]
            for report in episode_reports
            for name, descriptor in report["catalog_bound_asset_integrity"].items()
            if descriptor["required_for_joint_replay"]
            and descriptor["present"]
            and not descriptor["matches_catalog"]
        }
    )
    bound_asset_reports = [
        descriptor
        for report in episode_reports
        for descriptor in report["catalog_bound_asset_integrity"].values()
        if descriptor["catalog_bound"]
    ]
    verified_bound_hash_count = sum(
        descriptor["matches_catalog"] for descriptor in bound_asset_reports
    )
    missing_bound_paths = sorted(
        {
            descriptor["path"]
            for descriptor in bound_asset_reports
            if not descriptor["present"]
        }
    )
    mismatched_bound_paths = sorted(
        {
            descriptor["path"]
            for descriptor in bound_asset_reports
            if descriptor["present"] and not descriptor["matches_catalog"]
        }
    )
    all_episodes_ready = bool(episode_reports) and ready_count == len(episode_reports)
    all_bound_hashes_verified = bool(bound_asset_reports) and (
        verified_bound_hash_count == len(bound_asset_reports)
    )
    result = {
        "schema_version": INPUT_CAPABILITY_SCHEMA,
        "inspection_scope": {
            "kind": scope_kind,
            "requested_kind": inspection_scope,
            "root_at_generation": str(repo_root),
            "provided_root_inspected": True,
            "scope_source": (
                "runtime_auto_detection"
                if inspection_scope == "auto"
                else "caller_supplied_repo_root"
            ),
            "root_path_semantics": "runtime_local_not_portable_project_contract",
            "canonical_checkout_inspected": canonical_checkout_inspected,
            "canonical_checkout_state": (
                "caller_supplied_root_inspected_without_canonical_identity_claim"
                if inspection_scope == "canonical_checkout"
                else "not_assessed_by_this_receipt"
            ),
        },
        "catalog": {
            "sha256": sha256_file(catalog_path),
            "catalog_id": catalog.get("catalog_id"),
            "identity": portable_content_identity(
                catalog_path, sha256_file(catalog_path)
            ),
        },
        "sysid_config": {
            "config_id": config["config_id"],
            "sha256": sha256_file(config_path),
            "identity": {
                "kind": "content_addressed",
                "sha256": sha256_file(config_path),
            },
        },
        "physical_joint_transform": {
            "schema_version": transform.get("schema_version"),
            "transform_id": transform.get("transform_id"),
            "sha256": transform_adapter.get("joint_transform_sha256"),
            "calibration_approved": transform_approved,
            "review_status": transform.get("review_status"),
            "joint_identity_and_order": transform.get("simulator_joint_names"),
            "exact_formula": "sim = sign * source * scale + zero_offset",
            "initial_velocity_source_field": (
                "follower_actual_velocity_degrees_s"
            ),
            "velocity_exact_formula": "sim_velocity = sign * source_velocity * scale",
            "velocity_zero_offset_applied": False,
        },
        "episode_count": len(episode_reports),
        "joint_replay_ready_episode_count": ready_count,
        "strict_sample_semantics_valid_episode_count": semantic_valid_count,
        "joint_range_valid_episode_count": range_valid_count,
        "full_provenance_chain_episode_count": provenance_complete_count,
        "aggregate_joint_limit_validation": aggregate_joint_limits,
        "metadata_conflict_episode_count": metadata_conflict_count,
        "missing_required_asset_count": len(missing_paths),
        "missing_required_assets": missing_paths,
        "mismatched_required_asset_count": len(mismatched_required_paths),
        "mismatched_required_assets": mismatched_required_paths,
        "current_root_catalog_integrity": {
            "catalog_bound_asset_count": len(bound_asset_reports),
            "verified_catalog_bound_hash_count": verified_bound_hash_count,
            "missing_catalog_bound_asset_count": len(missing_bound_paths),
            "missing_catalog_bound_assets": missing_bound_paths,
            "mismatched_catalog_bound_asset_count": len(mismatched_bound_paths),
            "mismatched_catalog_bound_assets": mismatched_bound_paths,
            "all_catalog_bound_hashes_verified": all_bound_hashes_verified,
            "video_files_hashed_for_integrity_only": True,
            "video_content_interpreted": False,
        },
        "episodes": episode_reports,
        "aggregate_observable_status": {
            "joint_position": (
                "available_for_all_episodes"
                if semantic_valid_count == len(episode_reports)
                else "available_for_some_episodes"
                if semantic_valid_count
                else "payloads_missing_or_invalid"
            ),
            "end_effector_position": "unavailable",
            "end_effector_orientation": "unavailable",
            "pawn_position": "unavailable",
            "pawn_orientation": "unavailable",
            "contact_active": "unavailable",
            "contact_force": "unavailable",
        },
        "video_used_for_metric_observables": False,
        "endpoint_visual_proposals_used_for_metric_observables": False,
        "endpoint_visual_proposals_status": (
            "unreviewed_not_pawn_trajectory_or_contact_input"
        ),
        "physical_motion": False,
        "joint_timing_replay_ready": all_episodes_ready,
        "timing_control_fit_ready": all_episodes_ready,
        "geometry_stage_ready": False,
        "contact_object_stage_ready": False,
        "calibration_ready": False,
        "calibration_ready_reason": (
            "joint/timing requires strict sample semantics, a reviewed hash-bound transform, "
            "and all initial/measured/command values within simulator limits; full calibration "
            "also lacks measured end-effector, object-pose, pawn, and contact trajectories"
        ),
        "claim": (
            "joint_timing_replay_inputs_present"
            if all_episodes_ready
            else "joint_timing_replay_blocked_by_transform_or_ranges"
            if semantic_valid_count == len(episode_reports)
            and provenance_complete_count == len(episode_reports)
            else "partial_joint_timing_replay_inputs_present"
            if ready_count
            else "missing_input_manifest_only"
        ),
        "post_cherry_pick_canonical_commands": [
            "cd /Users/kelly/Developer/sim2claw",
            "uv sync --frozen",
            (
                "uv run --frozen sim2claw sysid-input-report "
                "--catalog configs/data/physical_pawn_move_catalog_20260719.json "
                "--config configs/sysid/recorded_action_sysid_v1.json "
                "--repo-root /Users/kelly/Developer/sim2claw "
                "--inspection-scope canonical_checkout "
                "--output runs/sysid/physical_pawn_input_capability_post_cherry_pick.json"
            ),
        ],
        "post_cherry_pick_fit_exit_semantics": (
            "do not run sysid-fit while joint_timing_replay_ready is false; the current "
            "provisional transform and any range violations are calibration blockers"
        ),
        "input_report_exit_semantics": (
            "the CLI returns zero only when every catalog episode is integrity-verified "
            "and ready for joint/timing replay; this never implies full calibration readiness"
        ),
        "created_at": datetime.now(UTC).isoformat(),
    }
    if not canonical_checkout_inspected:
        result["coordinator_reported_canonical_state"] = {
            "physical_recording_directories_recovered": 18,
            "catalog_bound_hashes_verified": 54,
            "verified_by_this_receipt": False,
            "requires_post_cherry_pick_regeneration": True,
        }
    if output_path is not None:
        _atomic_json(output_path.resolve(), result)
        result["report_path"] = str(output_path.resolve())
        result["report_sha256"] = sha256_file(output_path.resolve())
    return result


@dataclass(frozen=True)
class LeastSquaresResult:
    values: np.ndarray
    loss: float
    iterations: int
    converged: bool | None
    backend: str
    details: Mapping[str, Any]


def _official_least_squares(
    descriptors: Sequence[Mapping[str, Any]],
    initial: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    *,
    optimizer: str,
    maximum_iterations: int,
) -> LeastSquaresResult:
    capability = mujoco_sysid_capability()
    if not capability["compatible"]:
        raise SystemIdentificationError(
            "official mujoco.sysid is unavailable or incompatible: "
            f"{capability['actionable_resolution'] or capability['import_error']}"
        )
    from mujoco import sysid

    params = sysid.ParameterDict()
    for descriptor, value in zip(descriptors, initial, strict=True):
        params.add(
            sysid.Parameter(
                str(descriptor["name"]),
                nominal=float(value),
                min_value=float(descriptor["minimum"]),
                max_value=float(descriptor["maximum"]),
            )
        )

    def official_residual(
        vector: np.ndarray,
        _: Any,
    ) -> tuple[list[np.ndarray], None, None]:
        array = np.asarray(vector, dtype=np.float64)
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        if array.ndim != 2 or array.shape[0] != len(descriptors):
            raise ValueError(
                "official sysid parameter batch does not match the stage"
            )
        columns = [residual_fn(array[:, index]) for index in range(array.shape[1])]
        return [np.column_stack(columns)], None, None

    optimizer_output = io.StringIO()
    with contextlib.redirect_stdout(optimizer_output):
        fitted, result = sysid.optimize(
            initial_params=params,
            residual_fn=official_residual,
            optimizer=optimizer,
            verbose=False,
            check_conditioning=True,
            max_iters=maximum_iterations,
        )
    values = fitted.as_vector().astype(np.float64)
    residual = residual_fn(values)
    if not np.all(np.isfinite(values)) or not np.all(np.isfinite(residual)):
        raise SystemIdentificationError(
            "official mujoco.sysid returned non-finite parameters or residuals"
        )
    backend_success = getattr(result, "success", None)
    objective_history = (getattr(result, "extras", None) or {}).get(
        "objective", []
    )
    iterations = max(0, len(objective_history) - 1)
    details = {
        "optimizer": optimizer,
        "jacobian_available": getattr(result, "jac", None) is not None,
        "gradient_available": getattr(result, "grad", None) is not None,
        "status": getattr(result, "status", None),
        "message": str(getattr(result, "message", "")) or None,
        "backend_reported_success": (
            bool(backend_success) if backend_success is not None else None
        ),
        "maximum_iterations": maximum_iterations,
        "optimizer_trace_line_count": len(optimizer_output.getvalue().splitlines()),
    }
    return LeastSquaresResult(
        values=values,
        loss=0.5 * float(np.dot(residual, residual)),
        iterations=iterations,
        converged=(
            bool(backend_success) if backend_success is not None else None
        ),
        backend="mujoco.sysid.optimize",
        details=details,
    )


def _finite_difference_jacobian(
    vector: np.ndarray,
    residual: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    lower: np.ndarray,
    upper: np.ndarray,
    relative_step: float,
) -> np.ndarray:
    columns: list[np.ndarray] = []
    for index in range(vector.size):
        span = max(upper[index] - lower[index], 1.0)
        step = max(relative_step * span, np.finfo(np.float64).eps ** 0.5)
        forward = min(vector[index] + step, upper[index])
        backward = max(vector[index] - step, lower[index])
        if forward == backward:
            columns.append(np.zeros_like(residual))
            continue
        if forward != vector[index] and backward != vector[index]:
            right = vector.copy()
            left = vector.copy()
            right[index] = forward
            left[index] = backward
            derivative = (residual_fn(right) - residual_fn(left)) / (
                forward - backward
            )
        elif forward != vector[index]:
            right = vector.copy()
            right[index] = forward
            derivative = (residual_fn(right) - residual) / (forward - vector[index])
        else:
            left = vector.copy()
            left[index] = backward
            derivative = (residual - residual_fn(left)) / (vector[index] - backward)
        columns.append(derivative)
    return np.column_stack(columns)


def _local_least_squares(
    descriptors: Sequence[Mapping[str, Any]],
    initial: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    *,
    maximum_iterations: int,
    relative_step: float,
) -> LeastSquaresResult:
    unsupported = [
        str(descriptor["name"])
        for descriptor in descriptors
        if not bool(descriptor.get("smooth"))
        or not bool(descriptor.get("fallback_supported"))
    ]
    if unsupported:
        raise SystemIdentificationError(
            "local fallback rejects non-smooth or unsupported parameters: "
            f"{unsupported}"
        )
    lower = np.asarray(
        [float(descriptor["minimum"]) for descriptor in descriptors],
        dtype=np.float64,
    )
    upper = np.asarray(
        [float(descriptor["maximum"]) for descriptor in descriptors],
        dtype=np.float64,
    )
    vector = np.clip(initial.astype(np.float64), lower, upper)
    residual = residual_fn(vector)
    loss = 0.5 * float(np.dot(residual, residual))
    damping = 1e-6
    converged = False
    completed_iterations = 0
    for iteration in range(maximum_iterations):
        completed_iterations = iteration + 1
        jacobian = _finite_difference_jacobian(
            vector,
            residual,
            residual_fn,
            lower,
            upper,
            relative_step,
        )
        normal = jacobian.T @ jacobian + damping * np.eye(vector.size)
        gradient = jacobian.T @ residual
        try:
            step = np.linalg.solve(normal, -gradient)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(normal, -gradient, rcond=None)[0]
        if np.linalg.norm(step, ord=np.inf) <= 1e-10:
            converged = True
            break
        accepted = False
        for line_search in range(12):
            candidate = np.clip(vector + (0.5**line_search) * step, lower, upper)
            candidate_residual = residual_fn(candidate)
            candidate_loss = 0.5 * float(
                np.dot(candidate_residual, candidate_residual)
            )
            if candidate_loss + 1e-15 < loss:
                improvement = loss - candidate_loss
                vector = candidate
                residual = candidate_residual
                loss = candidate_loss
                damping = max(damping / 3.0, 1e-12)
                accepted = True
                if improvement <= 1e-12 * max(1.0, loss):
                    converged = True
                break
        if converged:
            break
        if not accepted:
            damping *= 10.0
            if damping > 1e12:
                break
    return LeastSquaresResult(
        values=vector,
        loss=loss,
        iterations=completed_iterations,
        converged=converged,
        backend="local_bounded_gauss_newton",
        details={
            "robust_residual": "Huber pseudo-residual",
            "finite_difference_relative_step": relative_step,
            "final_damping": damping,
        },
    )


STAGE_OBSERVABLES = {
    "geometry": {
        "end_effector_position",
        "end_effector_orientation",
        "pawn_position",
        "pawn_orientation",
    },
    "timing_control": {
        "joint_position",
        "end_effector_position",
        "end_effector_orientation",
        "gripper_position",
    },
    "contact_object": {
        "joint_position",
        "gripper_position",
        "pawn_position",
        "pawn_orientation",
        "contact_active",
        "contact_force",
    },
}


def _stage_data_report(
    stage: Mapping[str, Any],
    episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    by_episode = {
        episode.episode_id: sorted(episode.available_observables())
        for episode in episodes
    }
    union = set().union(*(set(values) for values in by_episode.values()))
    missing_all: dict[str, list[str]] = {}
    for observable in stage.get("requires_all_observables", []):
        missing = [
            episode_id
            for episode_id, available in by_episode.items()
            if observable not in available
        ]
        if missing:
            missing_all[str(observable)] = missing
    required_any = set(stage.get("requires_any_observable", []))
    any_present = not required_any or bool(required_any.intersection(union))
    weights = config["loss"]["weights"]
    parameter_support: dict[str, Any] = {}
    for parameter in stage.get("parameters", []):
        configured = set(str(value) for value in parameter["supports_observables"])
        measured_weighted = sorted(
            observable
            for observable in configured.intersection(union)
            if float(weights.get(observable, 0.0)) > 0.0
        )
        parameter_support[str(parameter["name"])] = {
            "configured_supporting_observables": sorted(configured),
            "measured_weighted_supporting_observables": measured_weighted,
            "dependency_supported": bool(measured_weighted),
        }
    dependency_ready = all(
        report["dependency_supported"] for report in parameter_support.values()
    )
    object_binding_by_episode = {
        episode.episode_id: episode.initial_object_state.get("status") == "available"
        for episode in episodes
    }
    return {
        "episode_observables": by_episode,
        "available_union": sorted(union),
        "missing_required_all": missing_all,
        "required_any": sorted(required_any),
        "required_any_present": any_present,
        "parameter_support": parameter_support,
        "parameter_dependency_ready": dependency_ready,
        "object_binding_by_episode": object_binding_by_episode,
        "ready": not missing_all and any_present,
    }


def _stage_residual_function(
    episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
    current_parameters: Mapping[str, float],
    descriptors: Sequence[Mapping[str, Any]],
    *,
    model_base_directory: Path | None,
) -> Callable[[np.ndarray], np.ndarray]:
    descriptor_names = [str(descriptor["name"]) for descriptor in descriptors]
    target_stage = next(
        stage
        for stage in config["parameter_stages"]
        if [parameter["name"] for parameter in stage.get("parameters", [])]
        == descriptor_names
    )
    allowed = set().union(
        *(
            set(str(value) for value in descriptor["supports_observables"])
            for descriptor in descriptors
        )
    ).intersection(STAGE_OBSERVABLES[str(target_stage["name"])])

    def residual(vector: np.ndarray) -> np.ndarray:
        values = dict(current_parameters)
        values.update(
            {
                name: float(value)
                for name, value in zip(descriptor_names, vector, strict=True)
            }
        )
        blocks: list[np.ndarray] = []
        for episode in episodes:
            replay = simulate_and_align(
                episode,
                config,
                parameter_values=values,
                model_base_directory=model_base_directory,
            )
            episode_blocks = replay_residual_blocks(
                replay,
                config,
                allowed_observables=allowed,
            )
            blocks.extend(episode_blocks.values())
        if not blocks:
            raise StageDataError(
                f"stage {target_stage['name']} has no weighted measured residuals"
            )
        result = np.concatenate(blocks)
        if not np.all(np.isfinite(result)):
            raise SystemIdentificationError(
                f"stage {target_stage['name']} produced non-finite residuals"
            )
        return result

    return residual


def _parameter_sensitivity_report(
    descriptors: Sequence[Mapping[str, Any]],
    point: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = residual_fn(point)
    relative_step = float(config["optimizer"]["finite_difference_relative_step"])
    threshold = float(config["optimizer"]["minimum_parameter_sensitivity"])
    parameters: dict[str, Any] = {}
    for index, descriptor in enumerate(descriptors):
        lower = float(descriptor["minimum"])
        upper = float(descriptor["maximum"])
        requested_step = max(
            relative_step * (upper - lower),
            np.finfo(np.float64).eps,
        )
        candidate = point.copy()
        if candidate[index] + requested_step <= upper:
            candidate[index] += requested_step
        elif candidate[index] - requested_step >= lower:
            candidate[index] -= requested_step
        else:
            parameters[str(descriptor["name"])] = {
                "identifiable": False,
                "reason": "parameter bounds do not admit a finite perturbation",
                "sensitivity_norm": 0.0,
            }
            continue
        actual_step = float(candidate[index] - point[index])
        perturbed = residual_fn(candidate)
        if perturbed.shape != baseline.shape:
            raise SystemIdentificationError(
                f"parameter {descriptor['name']} perturbation changed residual shape"
            )
        sensitivity = float(np.linalg.norm(perturbed - baseline) / abs(actual_step))
        finite = math.isfinite(sensitivity)
        identifiable = finite and sensitivity >= threshold
        parameters[str(descriptor["name"])] = {
            "configured_supporting_observables": list(
                descriptor["supports_observables"]
            ),
            "perturbation": actual_step,
            "sensitivity_norm": sensitivity if finite else None,
            "minimum_sensitivity": threshold,
            "finite": finite,
            "identifiable": identifiable,
            "reason": (
                None
                if identifiable
                else "finite perturbation produced no nontrivial weighted residual sensitivity"
            ),
        }
    return {
        "method": "one_parameter_finite_perturbation_residual_norm",
        "baseline_residual_scalar_count": int(baseline.size),
        "minimum_parameter_sensitivity": threshold,
        "parameters": parameters,
        "all_parameters_identifiable": all(
            report["identifiable"] for report in parameters.values()
        ),
    }


def _fit_start(
    descriptors: Sequence[Mapping[str, Any]],
    start: np.ndarray,
    residual_fn: Callable[[np.ndarray], np.ndarray],
    config: Mapping[str, Any],
    *,
    backend: str,
) -> tuple[LeastSquaresResult, str | None]:
    optimizer = config["optimizer"]
    official_failure: str | None = None
    if backend not in {"auto", "official", "local"}:
        raise SystemIdentificationError(f"unsupported fitting backend: {backend}")
    if backend in {"auto", "official"}:
        try:
            return (
                _official_least_squares(
                    descriptors,
                    start,
                    residual_fn,
                    optimizer=str(optimizer["official_optimizer"]),
                    maximum_iterations=int(optimizer["maximum_iterations"]),
                ),
                None,
            )
        except Exception as error:
            official_failure = f"{type(error).__name__}: {error}"
            if backend == "official":
                raise SystemIdentificationError(
                    f"official sysid fit failed closed: {official_failure}"
                ) from error
    return (
        _local_least_squares(
            descriptors,
            start,
            residual_fn,
            maximum_iterations=int(optimizer["maximum_iterations"]),
            relative_step=float(optimizer["finite_difference_relative_step"]),
        ),
        official_failure,
    )


def fit_parameter_stage(
    stage: Mapping[str, Any],
    episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
    current_parameters: Mapping[str, float],
    *,
    backend: str = "auto",
    model_base_directory: Path | None = None,
) -> dict[str, Any]:
    data_report = _stage_data_report(stage, episodes, config)
    stage_name = str(stage["name"])
    if not data_report["ready"]:
        return {
            "name": stage_name,
            "order": stage["order"],
            "status": (
                "rejected_no_data"
                if stage_name == "contact_object"
                else "skipped_no_data"
            ),
            "data": data_report,
            "reason": (
                "contact/object parameters require measured pawn or contact data"
                if stage_name == "contact_object"
                else "stage requirements are not present in the recorded episodes"
            ),
            "parameters_unchanged": True,
        }
    if not data_report["parameter_dependency_ready"]:
        return {
            "name": stage_name,
            "order": stage["order"],
            "status": (
                "rejected_unidentifiable"
                if stage_name == "contact_object"
                else "skipped_unidentifiable"
            ),
            "data": data_report,
            "reason": (
                "one or more fitted parameters has no measured, weighted supporting observable"
            ),
            "parameters_unchanged": True,
        }
    if stage_name == "contact_object":
        available = set(data_report["available_union"])
        binding_errors: list[str] = []
        object_data_episodes = [
            episode
            for episode in episodes
            if episode.available_observables().intersection(
                {"pawn_position", "pawn_orientation", "contact_active", "contact_force"}
            )
        ]
        missing_object_bindings = [
            episode.episode_id
            for episode in object_data_episodes
            if episode.initial_object_state.get("status") != "available"
        ]
        if missing_object_bindings:
            binding_errors.append(
                "measured object body/free-joint initial-state binding is required for "
                f"episodes {missing_object_bindings}"
            )
        contact_groups = config["bindings"].get("contact_body_groups")
        if available.intersection({"contact_active", "contact_force"}) and not (
            isinstance(contact_groups, list)
            and len(contact_groups) == 2
            and all(isinstance(group, list) and group for group in contact_groups)
        ):
            binding_errors.append(
                "two non-empty contact_body_groups are required for contact telemetry"
            )
        if binding_errors:
            return {
                "name": stage_name,
                "order": stage["order"],
                "status": "rejected_missing_model_binding",
                "data": data_report,
                "reason": "; ".join(binding_errors),
                "parameters_unchanged": True,
            }
    descriptors = list(stage.get("parameters", []))
    if not descriptors:
        return {
            "name": stage_name,
            "order": stage["order"],
            "status": "no_parameters",
            "data": data_report,
            "parameters_unchanged": True,
        }
    residual_fn = _stage_residual_function(
        episodes,
        config,
        current_parameters,
        descriptors,
        model_base_directory=model_base_directory,
    )
    lower = np.asarray(
        [float(descriptor["minimum"]) for descriptor in descriptors]
    )
    upper = np.asarray(
        [float(descriptor["maximum"]) for descriptor in descriptors]
    )
    first = np.asarray(
        [float(current_parameters[str(descriptor["name"])]) for descriptor in descriptors]
    )
    try:
        sensitivity = _parameter_sensitivity_report(
            descriptors,
            first,
            residual_fn,
            config,
        )
    except Exception as error:
        return {
            "name": stage_name,
            "order": stage["order"],
            "status": (
                "rejected_unidentifiable"
                if stage_name == "contact_object"
                else "skipped_unidentifiable"
            ),
            "data": data_report,
            "sensitivity": {
                "all_parameters_identifiable": False,
                "error": f"{type(error).__name__}: {error}",
            },
            "reason": "parameter sensitivity evaluation failed closed",
            "parameters_unchanged": True,
        }
    if not sensitivity["all_parameters_identifiable"]:
        return {
            "name": stage_name,
            "order": stage["order"],
            "status": (
                "rejected_unidentifiable"
                if stage_name == "contact_object"
                else "skipped_unidentifiable"
            ),
            "data": data_report,
            "sensitivity": sensitivity,
            "reason": "one or more fitted parameters has zero or non-finite perturbation sensitivity",
            "parameters_unchanged": True,
        }
    rng = np.random.default_rng(
        int(config["optimizer"]["seed"]) + int(stage["order"])
    )
    starts = [first]
    for _ in range(int(config["optimizer"]["multi_start_count"]) - 1):
        starts.append(rng.uniform(lower, upper))
    attempts: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []
    for start_index, start in enumerate(starts):
        try:
            result, official_failure = _fit_start(
                descriptors,
                start,
                residual_fn,
                config,
                backend=backend,
            )
            parameter_map = {
                str(descriptor["name"]): float(value)
                for descriptor, value in zip(descriptors, result.values, strict=True)
            }
            attempt = {
                "start_index": start_index,
                "initial_parameters": {
                    str(descriptor["name"]): float(value)
                    for descriptor, value in zip(descriptors, start, strict=True)
                },
                "parameters": parameter_map,
                "loss": result.loss,
                "backend": result.backend,
                "iterations": result.iterations,
                "converged": result.converged,
                "official_attempt_failure": official_failure,
                "details": dict(result.details),
                "status": "completed",
            }
            attempts.append(attempt)
            successes.append(attempt)
        except Exception as error:
            attempts.append(
                {
                    "start_index": start_index,
                    "initial_parameters": {
                        str(descriptor["name"]): float(value)
                        for descriptor, value in zip(descriptors, start, strict=True)
                    },
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    if not successes:
        raise SystemIdentificationError(
            f"all bounded starts failed for stage {stage_name}: {attempts}"
        )
    successes.sort(key=lambda attempt: (float(attempt["loss"]), attempt["start_index"]))
    best = successes[0]
    relative = float(config["optimizer"]["near_equivalent_relative_loss"])
    absolute = float(config["optimizer"]["near_equivalent_absolute_loss"])
    threshold = float(best["loss"]) + max(absolute, relative * abs(float(best["loss"])))
    near = [attempt for attempt in successes if float(attempt["loss"]) <= threshold]
    distributions: dict[str, Any] = {}
    for descriptor in descriptors:
        name = str(descriptor["name"])
        values = np.asarray([attempt["parameters"][name] for attempt in near])
        distributions[name] = {
            "minimum": float(np.min(values)),
            "maximum": float(np.max(values)),
            "mean": float(np.mean(values)),
            "standard_deviation": float(np.std(values)),
            "bound_minimum": float(descriptor["minimum"]),
            "bound_maximum": float(descriptor["maximum"]),
        }
    return {
        "name": stage_name,
        "order": stage["order"],
        "status": "optimized",
        "data": data_report,
        "sensitivity": sensitivity,
        "best_parameters": best["parameters"],
        "best_train_loss": best["loss"],
        "best_backend": best["backend"],
        "multi_start_count": len(starts),
        "completed_start_count": len(successes),
        "attempts": attempts,
        "near_equivalent": {
            "threshold_loss": threshold,
            "fit_count": len(near),
            "unique_fit_claimed": False,
            "parameter_distribution": distributions,
        },
    }


def evaluate_episode_losses(
    episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
    parameters: Mapping[str, float],
    *,
    model_base_directory: Path | None = None,
) -> dict[str, Any]:
    by_episode: dict[str, Any] = {}
    losses: list[float] = []
    for episode in episodes:
        replay = simulate_and_align(
            episode,
            config,
            parameter_values=parameters,
            model_base_directory=model_base_directory,
        )
        metrics = calculate_metrics(replay, config)
        loss = float(metrics["aggregate"]["weighted_mean_huber_loss"])
        losses.append(loss)
        by_episode[episode.episode_id] = {
            "loss": loss,
            "weighted_observables": metrics["aggregate"]["weighted_observables"],
            "metrics": metrics,
        }
    if not losses:
        raise SystemIdentificationError("evaluation requires at least one episode")
    return {
        "episode_count": len(losses),
        "mean_loss": float(np.mean(losses)),
        "maximum_loss": float(np.max(losses)),
        "by_episode": by_episode,
    }


def held_out_improvement_gate(
    baseline_loss: float,
    candidate_loss: float,
    acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = float(baseline_loss)
    candidate = float(candidate_loss)
    if not (math.isfinite(baseline) and math.isfinite(candidate)):
        raise SystemIdentificationError("held-out losses must be finite")
    absolute_improvement = baseline - candidate
    relative_improvement = absolute_improvement / max(abs(baseline), 1e-15)
    minimum_absolute = float(acceptance["minimum_absolute_improvement"])
    minimum_relative = float(acceptance["minimum_relative_improvement"])
    passed = (
        candidate < baseline
        and absolute_improvement >= minimum_absolute
        and relative_improvement >= minimum_relative
    )
    return {
        "baseline_loss": baseline,
        "candidate_loss": candidate,
        "absolute_improvement": absolute_improvement,
        "relative_improvement": relative_improvement,
        "minimum_absolute_improvement": minimum_absolute,
        "minimum_relative_improvement": minimum_relative,
        "passed": passed,
        "claim": (
            "held_out_improvement_verified"
            if passed
            else "calibration_success_rejected_no_held_out_improvement"
        ),
    }


def fit_staged_parameters(
    train_episodes: Sequence[RecordedEpisode],
    held_out_episodes: Sequence[RecordedEpisode],
    config: Mapping[str, Any],
    *,
    backend: str = "auto",
    model_base_directory: Path | None = None,
) -> dict[str, Any]:
    if not train_episodes or not held_out_episodes:
        raise SystemIdentificationError(
            "staged fitting requires non-empty whole-episode train and held-out sets"
        )
    incomplete_physical_provenance = [
        episode.episode_id
        for episode in [*train_episodes, *held_out_episodes]
        if episode.proof_class_category == "physical_read_only"
        and not episode.source_provenance.get("chain_complete")
    ]
    if incomplete_physical_provenance:
        raise SystemIdentificationError(
            "physical fitting requires the full catalog/receipt/sample provenance chain: "
            f"{incomplete_physical_provenance}"
        )
    baseline_parameters = nominal_parameter_values(config)
    baseline_train = evaluate_episode_losses(
        train_episodes,
        config,
        baseline_parameters,
        model_base_directory=model_base_directory,
    )
    baseline_held_out = evaluate_episode_losses(
        held_out_episodes,
        config,
        baseline_parameters,
        model_base_directory=model_base_directory,
    )
    current = dict(baseline_parameters)
    stage_reports: list[dict[str, Any]] = []
    for expected_order, stage in enumerate(config["parameter_stages"], start=1):
        if int(stage["order"]) != expected_order:
            raise SystemIdentificationError("parameter stages are not in frozen order")
        report = fit_parameter_stage(
            stage,
            train_episodes,
            config,
            current,
            backend=backend,
            model_base_directory=model_base_directory,
        )
        stage_reports.append(report)
        if report["status"] == "optimized":
            current.update(report["best_parameters"])
    candidate_train = evaluate_episode_losses(
        train_episodes,
        config,
        current,
        model_base_directory=model_base_directory,
    )
    candidate_held_out = evaluate_episode_losses(
        held_out_episodes,
        config,
        current,
        model_base_directory=model_base_directory,
    )
    held_out_gate = held_out_improvement_gate(
        baseline_held_out["mean_loss"],
        candidate_held_out["mean_loss"],
        config["held_out_acceptance"],
    )
    all_stages_valid = all(
        report["status"] in {"optimized", "no_parameters"}
        for report in stage_reports
    )
    requires_all_stages = bool(
        config["held_out_acceptance"].get("success_requires_every_stage_valid")
    )
    official_exercised = any(
        attempt.get("status") == "completed"
        and attempt.get("backend") == "mujoco.sysid.optimize"
        for report in stage_reports
        for attempt in report.get("attempts", [])
    )
    calibration_success = bool(
        held_out_gate["passed"]
        and (all_stages_valid or not requires_all_stages)
        and any(report["status"] == "optimized" for report in stage_reports)
    )
    return {
        "baseline_parameters": baseline_parameters,
        "candidate_parameters": current,
        "stages": stage_reports,
        "baseline": {
            "train": baseline_train,
            "held_out": baseline_held_out,
        },
        "candidate": {
            "train": candidate_train,
            "held_out": candidate_held_out,
        },
        "held_out_gate": held_out_gate,
        "all_stages_valid": all_stages_valid,
        "official_sysid_exercised": official_exercised,
        "calibration_success": calibration_success,
        "parameters_promoted": False,
        "proof_class": "synthetic" if all(
            episode.proof_class_category == "synthetic"
            for episode in [*train_episodes, *held_out_episodes]
        ) else "replay",
    }


def _resolve_manifest_episode_path(
    source_path: str,
    *,
    manifest_path: Path,
    repo_root: Path | None = None,
) -> Path:
    candidate = Path(source_path)
    if candidate.is_absolute():
        return candidate
    repo_candidate = (repo_root or REPO_ROOT) / candidate
    if repo_candidate.exists():
        return repo_candidate
    return manifest_path.parent / candidate


def _resolve_manifest_repo_root(
    manifest: Mapping[str, Any],
    manifest_path: Path,
) -> Path | None:
    source_catalog = manifest.get("source_catalog") or {}
    relative = Path(str(source_catalog.get("path") or ""))
    expected_hash = str(source_catalog.get("sha256") or "")
    if relative.is_absolute() or not relative.parts:
        return None
    candidates = [*manifest_path.parents, REPO_ROOT.resolve()]
    seen: set[Path] = set()
    for root in candidates:
        root = root.resolve()
        if root in seen:
            continue
        seen.add(root)
        candidate = root / relative
        if candidate.is_file() and sha256_file(candidate) == expected_hash:
            return root
    return None


def load_manifest_episodes(
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, list[RecordedEpisode]]:
    manifest_path = Path(str(manifest.get("_manifest_path") or ".")).resolve()
    manifest_repo_root = _resolve_manifest_repo_root(manifest, manifest_path)
    bound_catalog_entries: dict[str, dict[str, Any]] = {}
    if manifest_repo_root is not None:
        catalog_path = manifest_repo_root / str(manifest["source_catalog"]["path"])
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        bound_catalog_entries = {
            entry["episode_id"]: entry
            for entry in (
                _catalog_episode_entry(episode) for episode in catalog["episodes"]
            )
        }
    result: dict[str, list[RecordedEpisode]] = {"train": [], "held_out": []}
    for entry in manifest["episodes"]:
        source_kind = str(entry["source_kind"])
        if source_kind == "physical_recording" and manifest_repo_root is None:
            raise SystemIdentificationError(
                "physical split source catalog cannot be resolved and hash-verified "
                "relative to the manifest checkout"
            )
        source_path = _resolve_manifest_episode_path(
            str(entry["source_path"]),
            manifest_path=manifest_path,
            repo_root=manifest_repo_root,
        )
        if not source_path.exists():
            raise SystemIdentificationError(
                f"split input is missing for episode {entry['episode_id']}: {source_path}; "
                "run `sim2claw sysid-input-report` for the exact manifest"
            )
        source_provenance: Mapping[str, Any] | None = None
        if source_kind == "physical_recording":
            assert manifest_repo_root is not None
            expected_entry = bound_catalog_entries.get(str(entry["episode_id"]))
            provenance_fields = (
                "source_kind",
                "source_path",
                "source_receipt_path",
                "source_receipt_sha256",
                "source_samples_path",
                "source_samples_sha256",
                "source_square",
                "destination_square",
                "source_column",
                "destination_column",
                "proof_class",
                "metadata_status",
                "column_adjudication",
            )
            if expected_entry is None or any(
                entry.get(field) != expected_entry.get(field)
                for field in provenance_fields
            ):
                raise SystemIdentificationError(
                    f"physical split provenance drifted from the bound catalog for {entry['episode_id']}"
                )
            receipt_path = manifest_repo_root / str(entry["source_receipt_path"])
            samples_path = manifest_repo_root / str(entry["source_samples_path"])
            if not receipt_path.is_file() or not samples_path.is_file():
                raise SystemIdentificationError(
                    f"physical provenance payload is missing for {entry['episode_id']}"
                )
            if sha256_file(receipt_path) != entry["source_receipt_sha256"]:
                raise SystemIdentificationError(
                    f"physical receipt provenance mismatch for {entry['episode_id']}"
                )
            if sha256_file(samples_path) != entry["source_samples_sha256"]:
                raise SystemIdentificationError(
                    f"physical sample provenance mismatch for {entry['episode_id']}"
                )
            source_provenance = {
                "episode_id": entry["episode_id"],
                "chain_complete": True,
                "catalog": {
                    "kind": "repo_relative",
                    "path": manifest["source_catalog"]["path"],
                    "catalog_id": manifest["source_catalog"].get("catalog_id"),
                    "sha256": manifest["source_catalog"]["sha256"],
                },
                "recording_receipt": {
                    "kind": "repo_relative",
                    "path": entry["source_receipt_path"],
                    "sha256": entry["source_receipt_sha256"],
                },
                "samples": {
                    "kind": "repo_relative",
                    "path": entry["source_samples_path"],
                    "sha256": entry["source_samples_sha256"],
                },
            }
        episode = load_recorded_episode(
            source_path,
            config,
            source_provenance=source_provenance,
        )
        if episode.episode_id != entry["episode_id"]:
            raise SystemIdentificationError(
                f"episode identity mismatch: manifest={entry['episode_id']} "
                f"source={episode.episode_id}"
            )
        if episode.source_sha256 != entry["source_samples_sha256"]:
            raise SystemIdentificationError(
                f"episode hash mismatch for {episode.episode_id}"
            )
        result[str(entry["split"])].append(episode)
    return result


def run_system_identification(
    split_manifest_path: Path,
    *,
    config_path: Path,
    output_directory: Path,
    backend: str = "auto",
) -> dict[str, Any]:
    """Fit staged parameters and gate every success claim on frozen held-out data."""

    split_manifest_path = split_manifest_path.resolve()
    config_path = config_path.resolve()
    output_directory = output_directory.resolve()
    config = load_sysid_config(config_path)
    manifest = load_split_manifest(split_manifest_path, config=config)
    declared_config = manifest.get("sysid_config") or {}
    if declared_config.get("sha256") != sha256_file(config_path):
        raise SystemIdentificationError(
            "split manifest is not bound to the supplied sysid config"
        )
    episodes = load_manifest_episodes(manifest, config)
    fit = fit_staged_parameters(
        episodes["train"],
        episodes["held_out"],
        config,
        backend=backend,
        model_base_directory=config_path.parent,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    baseline_path = output_directory / "baseline_metrics.json"
    candidate_path = output_directory / "candidate_metrics.json"
    parameters_path = output_directory / "candidate_parameters.json"
    _atomic_json(baseline_path, fit["baseline"])
    _atomic_json(candidate_path, fit["candidate"])
    _atomic_json(
        parameters_path,
        {
            "schema_version": "sim2claw.sysid_candidate_parameters.v1",
            "parameters": fit["candidate_parameters"],
            "held_out_gate": fit["held_out_gate"],
            "calibration_success": fit["calibration_success"],
            "promoted": False,
            "reason": "candidate output never mutates the frozen baseline config",
        },
    )
    replay_receipts: list[dict[str, Any]] = []
    for episode in episodes["held_out"]:
        replay = simulate_and_align(
            episode,
            config,
            parameter_values=fit["candidate_parameters"],
            model_base_directory=config_path.parent,
        )
        receipt = write_replay_receipt(
            replay,
            config,
            output_directory / "held_out_replays" / episode.episode_id,
        )
        replay_receipts.append(
            {
                "episode_id": episode.episode_id,
                "receipt_path": (
                    f"held_out_replays/{episode.episode_id}/{receipt['receipt_path']}"
                ),
                "receipt_sha256": receipt["receipt_sha256"],
            }
        )
    capability = mujoco_sysid_capability()
    if fit["official_sysid_exercised"]:
        capability["official_surface_exercised"] = True
        capability["claim"] = "official_sysid_exercised_by_staged_fit"
    ensemble = {
        report["name"]: report.get("near_equivalent")
        for report in fit["stages"]
        if report.get("near_equivalent") is not None
    }
    all_episodes = (*episodes["train"], *episodes["held_out"])
    receipt = {
        "schema_version": FIT_RECEIPT_SCHEMA,
        "split": {
            "sha256": sha256_file(split_manifest_path),
            "identity": portable_content_identity(
                split_manifest_path, sha256_file(split_manifest_path)
            ),
            "split_id": manifest["split_id"],
            "owner": manifest["owner"],
            "unit": manifest["unit"],
            "frozen": manifest["frozen"],
            "split_counts": manifest["split_counts"],
        },
        "config": {
            "sha256": sha256_file(config_path),
            "identity": portable_content_identity(
                config_path, sha256_file(config_path)
            ),
            "config_id": config["config_id"],
        },
        "backend_request": backend,
        "official_capability": capability,
        "baseline_parameters": fit["baseline_parameters"],
        "candidate_parameters": fit["candidate_parameters"],
        "stages": fit["stages"],
        "ensemble_and_uncertainty": ensemble,
        "baseline_metrics": {
            "path": baseline_path.name,
            "sha256": sha256_file(baseline_path),
        },
        "candidate_metrics": {
            "path": candidate_path.name,
            "sha256": sha256_file(candidate_path),
        },
        "candidate_parameter_artifact": {
            "path": parameters_path.name,
            "sha256": sha256_file(parameters_path),
            "promoted": False,
        },
        "held_out_replays": replay_receipts,
        "input_provenance": {
            "source_catalog": manifest["source_catalog"],
            "episodes": [
                {
                    "episode_id": episode.episode_id,
                    "split": next(
                        entry["split"]
                        for entry in manifest["episodes"]
                        if entry["episode_id"] == episode.episode_id
                    ),
                    "provenance": episode.source_provenance,
                }
                for episode in all_episodes
            ],
            "all_physical_chains_complete": all(
                episode.proof_class_category != "physical_read_only"
                or episode.source_provenance.get("chain_complete")
                for episode in all_episodes
            ),
        },
        "held_out_gate": fit["held_out_gate"],
        "all_stages_valid": fit["all_stages_valid"],
        "official_sysid_exercised": fit["official_sysid_exercised"],
        "calibration_success": fit["calibration_success"],
        "parameters_promoted": False,
        "proof": {
            "proof_class": fit["proof_class"],
            "simulation": True,
            "replay": True,
            "learned_policy": False,
            "physical_read_only_input": any(
                episode.proof_class_category == "physical_read_only"
                for episode in all_episodes
            ),
            "physical_task": False,
            "training_performed": False,
            "physical_motion": False,
        },
        "limitations": [
            "a near-equivalent ensemble is reported instead of a unique parameter claim",
            "candidate parameters are not promoted or written into the baseline config",
            "missing observables remain unavailable and cannot constrain a stage",
        ],
        "created_at": datetime.now(UTC).isoformat(),
    }
    receipt_path = output_directory / "fit_receipt.json"
    _atomic_json(receipt_path, receipt)
    result = copy.deepcopy(receipt)
    result["receipt_path"] = receipt_path.name
    result["receipt_sha256"] = sha256_file(receipt_path)
    return result
