"""Seeded deterministic benchmark for development-loop control mechanics."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .contracts import REPO_ROOT


CONFIG_SCHEMA = "sim2claw.dev_loop_benchmark_config.v1"
CASE_SCHEMA = "sim2claw.dev_loop_benchmark_case_set.v1"
SCORECARD_SCHEMA = "sim2claw.dev_loop_benchmark_scorecard.v1"
RECEIPT_SCHEMA = "sim2claw.dev_loop_benchmark_receipt.v1"
REQUIRED_MODES = (
    "single_worker",
    "worker_self_review",
    "independent_receipt_gated",
)
EXTERNAL_AUTHORITY = (
    "provider",
    "paid_compute",
    "training",
    "simulator_campaign",
    "simulator_promotion",
    "physical_capture",
    "robot_gateway",
    "robot_motion",
)


class DevLoopBenchmarkError(ValueError):
    """The deterministic development-loop benchmark contract failed."""


def _load(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DevLoopBenchmarkError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise DevLoopBenchmarkError(f"{label} must contain an object")
    return value


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    raw = Path(str(value))
    if raw.is_absolute():
        raise DevLoopBenchmarkError(f"{label} must be repository-relative")
    root = repo_root.resolve()
    resolved = (root / raw).resolve()
    if root not in resolved.parents:
        raise DevLoopBenchmarkError(f"{label} escapes repository")
    return resolved


def load_benchmark_contract(
    config_path: Path, *, repo_root: Path = REPO_ROOT
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    config = _load(config_path, label="development-loop benchmark config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise DevLoopBenchmarkError("unexpected development-loop benchmark config schema")
    authority = config.get("authority")
    if not isinstance(authority, dict) or any(authority.get(name) is not False for name in EXTERNAL_AUTHORITY):
        raise DevLoopBenchmarkError("development-loop benchmark widened authority")
    modes = config.get("modes")
    if not isinstance(modes, list) or [row.get("id") for row in modes if isinstance(row, dict)] != list(REQUIRED_MODES):
        raise DevLoopBenchmarkError("development-loop benchmark modes changed")
    for mode in modes:
        controls = mode.get("controls")
        if not isinstance(controls, list) or not controls or len(set(controls)) != len(controls):
            raise DevLoopBenchmarkError("development-loop benchmark controls are invalid")

    cases_path = _repo_path(repo_root, config.get("cases"), label="benchmark cases")
    cases = _load(cases_path, label="development-loop benchmark cases")
    if cases.get("schema_version") != CASE_SCHEMA or not isinstance(cases.get("cases"), list):
        raise DevLoopBenchmarkError("unexpected development-loop benchmark case schema")
    ids: set[str] = set()
    kinds: set[str] = set()
    for case in cases["cases"]:
        if not isinstance(case, dict) or not str(case.get("case_id", "")):
            raise DevLoopBenchmarkError("benchmark case identity is invalid")
        case_id = str(case["case_id"])
        if case_id in ids:
            raise DevLoopBenchmarkError("duplicate benchmark case")
        ids.add(case_id)
        defects = case.get("defects")
        if not isinstance(defects, list):
            raise DevLoopBenchmarkError("benchmark defects must be a list")
        for defect in defects:
            if not isinstance(defect, dict) or not defect.get("required_controls"):
                raise DevLoopBenchmarkError("benchmark defect contract is invalid")
            kind = str(defect.get("kind", ""))
            if not kind or kind in kinds:
                raise DevLoopBenchmarkError("benchmark defect kinds must be unique")
            kinds.add(kind)
    expected = config.get("expected") or {}
    if len(ids) != int(expected.get("case_count", -1)) or len(kinds) != int(
        expected.get("seeded_defect_count", -1)
    ):
        raise DevLoopBenchmarkError("benchmark expected counts changed")
    return config, cases_path, cases


def _score_mode(mode: Mapping[str, Any], cases: Mapping[str, Any]) -> dict[str, Any]:
    controls = set(str(value) for value in mode["controls"])
    case_rows: list[dict[str, Any]] = []
    detected_total = 0
    escaped_total = 0
    false_completion = 0
    duplicate_work = 0
    repairs = 0
    for case in cases["cases"]:
        detected: list[str] = []
        escaped: list[str] = []
        for defect in case["defects"]:
            required = set(str(value) for value in defect["required_controls"])
            if required <= controls:
                detected.append(str(defect["kind"]))
                repairs += int(bool(defect.get("requires_repair")))
            else:
                escaped.append(str(defect["kind"]))
                duplicate_work += int(defect["kind"] == "duplicate_process_launch")
        detected_total += len(detected)
        escaped_total += len(escaped)
        false_completion += int(bool(case["completion_claimed"]) and bool(escaped))
        case_rows.append(
            {
                "case_id": str(case["case_id"]),
                "detected_defects": detected,
                "escaped_defects": escaped,
                "terminal_status": "blocked_for_repair" if detected else (
                    "false_complete" if escaped else "merge_ready"
                ),
            }
        )
    return {
        "mode": str(mode["id"]),
        "control_count": len(controls),
        "case_count": len(case_rows),
        "seeded_defect_count": detected_total + escaped_total,
        "detected_defect_count": detected_total,
        "escaped_defect_count": escaped_total,
        "false_completion_count": false_completion,
        "duplicate_work_count": duplicate_work,
        "required_repair_count": repairs,
        "cases": case_rows,
    }


def run_dev_loop_benchmark(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config, cases_path, cases = load_benchmark_contract(config_path, repo_root=repo_root)
    modes = [_score_mode(mode, cases) for mode in config["modes"]]
    independent = next(row for row in modes if row["mode"] == "independent_receipt_gated")
    expected_escaped = int(config["expected"]["independent_receipt_gated_escaped_defects"])
    if independent["escaped_defect_count"] != expected_escaped:
        raise DevLoopBenchmarkError("independent receipt-gated containment regressed")
    unsigned_scorecard = {
        "schema_version": SCORECARD_SCHEMA,
        "benchmark_id": str(config["benchmark_id"]),
        "proof_class": "deterministic_seeded_control_plane_defect_containment",
        "claim_boundary": "This benchmark measures configured control-label coverage over seeded fixtures. It does not execute every named validator and does not measure general model intelligence, coding quality, research effectiveness, or physical capability.",
        "modes": modes,
        "authority": copy.deepcopy(config["authority"]),
    }
    scorecard = {
        **unsigned_scorecard,
        "scorecard_digest": canonical_digest(unsigned_scorecard),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    scorecard_path = output_root / "scorecard.json"
    atomic_write_json(scorecard_path, scorecard)

    compiler_paths = (
        "src/sim2claw/dev_loop/bench.py",
        "src/sim2claw/dev_loop/contracts.py",
    )
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "benchmark_id": str(config["benchmark_id"]),
        "config": {
            "path": config_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(config_path),
        },
        "cases": {
            "path": cases_path.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(cases_path),
        },
        "compiler": {
            path: sha256_file(repo_root / path) for path in compiler_paths
        },
        "scorecard": {"path": "scorecard.json", "sha256": sha256_file(scorecard_path)},
        "scorecard_digest": scorecard["scorecard_digest"],
        "authority": copy.deepcopy(config["authority"]),
        "proof_class": scorecard["proof_class"],
    }
    receipt = {
        **unsigned_receipt,
        "receipt_digest": canonical_digest(unsigned_receipt),
    }
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_dev_loop_benchmark_receipt(receipt_path, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.dev_loop_benchmark_run.v1",
        "status": "pass",
        "scorecard_path": str(scorecard_path),
        "receipt_path": str(receipt_path),
        "scorecard_digest": scorecard["scorecard_digest"],
        "receipt_digest": receipt["receipt_digest"],
        "modes": [
            {
                "mode": row["mode"],
                "detected_defect_count": row["detected_defect_count"],
                "escaped_defect_count": row["escaped_defect_count"],
                "false_completion_count": row["false_completion_count"],
            }
            for row in modes
        ],
    }


def verify_dev_loop_benchmark_receipt(
    receipt_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt = _load(receipt_path, label="development-loop benchmark receipt")
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise DevLoopBenchmarkError("unexpected development-loop benchmark receipt schema")
    normalized = copy.deepcopy(receipt)
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise DevLoopBenchmarkError("development-loop benchmark receipt digest mismatch")
    if any(receipt.get("authority", {}).get(name) is not False for name in EXTERNAL_AUTHORITY):
        raise DevLoopBenchmarkError("development-loop benchmark receipt widened authority")
    for group, base in (("config", repo_root), ("cases", repo_root), ("scorecard", output_root)):
        binding = receipt[group]
        path = base / str(binding["path"])
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise DevLoopBenchmarkError(f"development-loop benchmark {group} changed")
    for relative, digest in receipt["compiler"].items():
        path = repo_root / str(relative)
        if not path.is_file() or sha256_file(path) != digest:
            raise DevLoopBenchmarkError("development-loop benchmark compiler changed")
    return receipt


__all__ = [
    "DevLoopBenchmarkError",
    "load_benchmark_contract",
    "run_dev_loop_benchmark",
    "verify_dev_loop_benchmark_receipt",
]
