"""Fail-closed, hash-bound project bundles for the NemoClaw deployment lane."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .paths import REPO_ROOT


BUNDLE_METADATA_ROOT = "_sim2claw_bundle"
BUNDLE_METADATA_FILES = (
    f"{BUNDLE_METADATA_ROOT}/project.json",
    f"{BUNDLE_METADATA_ROOT}/source_revision.json",
    f"{BUNDLE_METADATA_ROOT}/artifact_manifest.json",
    f"{BUNDLE_METADATA_ROOT}/sha256sums.txt",
)
SOURCE_ARCHIVE_IDENTITY_MEMBER = "_sim2claw_source/revision.json"
SOURCE_ARCHIVE_IDENTITY_SCHEMA = "sim2claw.source_archive_identity.v1"
PROJECT_SCHEMA = "sim2claw.project.v1"
PROJECT_INSPECTION_SCHEMA = "sim2claw.project_inspection.v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
GIT_OBJECT_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}")
PROJECT_AUTHORITY_CONTRACT: dict[str, bool | int] = {
    "physical_authority": False,
    "robot_motion_allowed": False,
    "retrospective_recordings_can_promote": False,
    "training_can_promote_itself": False,
    "held_out_rows_opened": 0,
}
PROJECT_BUNDLE_ENTRIES = (
    {
        "path": "configs/data/physical_pawn_move_catalog_20260719.json",
        "required": True,
        "proof_class": "physical_source_catalog_unqualified",
    },
    {
        "path": "datasets/manipulation_source_recordings",
        "required": True,
        "proof_class": "physical_teleoperation_source_unqualified",
    },
    {
        "path": "outputs/pawn_composability/recovered_corpus_v2",
        "required": True,
        "proof_class": "retrospective_source_score_and_review_material",
    },
)
PROJECT_PIPELINE_CONTRACT = {
    "stages": [
        "inspect",
        "calibrate-sim",
        "evaluate-skills",
        "train-candidates",
        "compare-candidates",
    ],
    "generated_roots": ["artifacts", "datasets", "outputs", "runs", "checkpoints"],
    "training_lock_source": "docs/autonomous-workflow/project_state.json",
    "promotion_owner": "separate_cpu_fp32_consequence_evaluator",
}
PROJECT_TRAINING_LOCK = "closed_until_m7_candidates_replay_and_pass_separate_evaluator"


def _expected_bg_skill_specs() -> tuple[dict[str, str], ...]:
    specs: list[dict[str, str]] = []
    for column in "bcdefg":
        forward = f"pawn_{column}1_to_{column}2"
        reverse = f"pawn_{column}2_to_{column}1"
        specs.extend(
            [
                {
                    "skill_id": forward,
                    "column": column,
                    "direction": "rank1_to_rank2",
                    "source_square": f"{column}1",
                    "destination_square": f"{column}2",
                    "reverse_skill_id": reverse,
                },
                {
                    "skill_id": reverse,
                    "column": column,
                    "direction": "rank2_to_rank1",
                    "source_square": f"{column}2",
                    "destination_square": f"{column}1",
                    "reverse_skill_id": forward,
                },
            ]
        )
    return tuple(specs)


EXPECTED_BG_SKILL_SPECS = _expected_bg_skill_specs()
EXPECTED_BG_SKILL_IDS = tuple(spec["skill_id"] for spec in EXPECTED_BG_SKILL_SPECS)


class ProjectBundleError(RuntimeError):
    """Raised when a project, source identity, or bundle violates its contract."""


def require_exact_authority(value: object, *, label: str) -> dict[str, bool | int]:
    """Require the complete authority object with exact keys, values, and types."""
    if not isinstance(value, dict):
        raise ProjectBundleError(f"{label} must be an object")
    expected_keys = set(PROJECT_AUTHORITY_CONTRACT)
    observed_keys = set(value)
    if observed_keys != expected_keys:
        raise ProjectBundleError(
            f"{label} keys mismatch: expected {sorted(expected_keys)!r}, "
            f"observed {sorted(observed_keys)!r}"
        )
    for key, expected in PROJECT_AUTHORITY_CONTRACT.items():
        observed = value[key]
        if type(observed) is not type(expected) or observed != expected:
            raise ProjectBundleError(
                f"{label} {key} mismatch: expected exact {type(expected).__name__} "
                f"{expected!r}, observed {type(observed).__name__} {observed!r}"
            )
    return dict(PROJECT_AUTHORITY_CONTRACT)


def _require_exact_typed_contract(value: object, expected: object, *, label: str) -> None:
    """Compare a JSON contract recursively without Python bool/int coercion."""
    if type(value) is not type(expected):
        raise ProjectBundleError(
            f"{label} type mismatch: expected {type(expected).__name__}, "
            f"observed {type(value).__name__}"
        )
    if isinstance(expected, dict):
        assert isinstance(value, dict)
        if set(value) != set(expected):
            raise ProjectBundleError(
                f"{label} keys mismatch: expected {sorted(expected)!r}, "
                f"observed {sorted(value)!r}"
            )
        for key, expected_item in expected.items():
            _require_exact_typed_contract(
                value[key], expected_item, label=f"{label}.{key}"
            )
        return
    if isinstance(expected, list):
        assert isinstance(value, list)
        if len(value) != len(expected):
            raise ProjectBundleError(
                f"{label} length mismatch: expected {len(expected)}, observed {len(value)}"
            )
        for index, (item, expected_item) in enumerate(zip(value, expected, strict=True)):
            _require_exact_typed_contract(
                item, expected_item, label=f"{label}[{index}]"
            )
        return
    if value != expected:
        raise ProjectBundleError(
            f"{label} mismatch: expected {expected!r}, observed {value!r}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectBundleError(f"cannot read JSON contract {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProjectBundleError(f"JSON contract must contain an object: {path}")
    return value


def _resolve_inside(repo_root: Path, relative: str) -> Path:
    declared = Path(relative)
    if not relative or declared.is_absolute() or ".." in declared.parts:
        raise ProjectBundleError(f"project path must be repo-relative: {relative!r}")
    candidate = (repo_root / declared).resolve()
    if not candidate.is_relative_to(repo_root.resolve()):
        raise ProjectBundleError(f"project path escapes repository: {relative}")
    return candidate


def _safe_archive_name(name: str) -> str:
    if not name or "\\" in name or name.startswith("/"):
        raise ProjectBundleError(f"unsafe archive member path: {name!r}")
    parsed = PurePosixPath(name)
    normalized = parsed.as_posix()
    if normalized != name or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ProjectBundleError(f"unsafe archive member path: {name!r}")
    return normalized


def _require_sha256(value: object, label: str) -> str:
    observed = str(value)
    if SHA256_PATTERN.fullmatch(observed) is None:
        raise ProjectBundleError(f"{label} must be a lowercase SHA-256 digest")
    return observed


def _iter_files(root: Path) -> Iterable[Path]:
    if root.is_symlink():
        raise ProjectBundleError(f"symlinked bundle entry is not allowed: {root}")
    if root.is_file():
        yield root
        return
    if not root.is_dir():
        raise ProjectBundleError(f"bundle entry is not a regular file or directory: {root}")
    for directory, names, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in names:
            if (directory_path / name).is_symlink():
                raise ProjectBundleError(
                    f"symlinked bundle directory is not allowed: {directory_path / name}"
                )
        for name in sorted(files):
            path = directory_path / name
            if path.is_symlink():
                raise ProjectBundleError(f"symlinked bundle file is not allowed: {path}")
            if not path.is_file():
                raise ProjectBundleError(f"non-regular bundle file is not allowed: {path}")
            yield path


def _expected_artifact_proof_class(path: str) -> str:
    matches: list[str] = []
    for entry in PROJECT_BUNDLE_ENTRIES:
        root = str(entry["path"])
        if path == root or (
            root != "configs/data/physical_pawn_move_catalog_20260719.json"
            and path.startswith(root + "/")
        ):
            matches.append(str(entry["proof_class"]))
    if len(matches) != 1:
        raise ProjectBundleError(
            f"artifact path is outside the exact bundle-entry contract: {path}"
        )
    return matches[0]


def _git_run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def git_source_revision(
    repo_root: Path,
    *,
    require_clean_git: bool,
) -> dict[str, Any]:
    inside = _git_run(repo_root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        if require_clean_git:
            raise ProjectBundleError(f"repository is not a readable Git worktree: {repo_root}")
        return {
            "schema_version": "sim2claw.source_revision.v1",
            "git_repository": False,
            "git_head": None,
            "git_branch": None,
            "working_tree_clean": None,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    head = _git_run(repo_root, "rev-parse", "HEAD")
    if head.returncode != 0 or not head.stdout.strip():
        raise ProjectBundleError("Git HEAD lookup failed")
    status = _git_run(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0:
        raise ProjectBundleError("Git working-tree status lookup failed")
    dirty = bool(status.stdout)
    if require_clean_git and dirty:
        raise ProjectBundleError(
            "deployment packing requires a clean committed HEAD; tracked or untracked changes exist"
        )
    branch_result = _git_run(repo_root, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
    return {
        "schema_version": "sim2claw.source_revision.v1",
        "git_repository": True,
        "git_head": head.stdout.strip(),
        "git_branch": branch,
        "working_tree_clean": not dirty,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def _require_equal(label: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise ProjectBundleError(
            f"{label} mismatch: expected {expected!r}, observed {observed!r}"
        )


def inspect_project(
    project_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    hash_artifacts: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    project_file = _resolve_inside(repo_root, str(project_path))
    project = _load_json(project_file)
    _require_equal("project schema", project.get("schema_version"), PROJECT_SCHEMA)
    project_id = str(project.get("project_id", ""))
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise ProjectBundleError(f"unsafe or missing project_id: {project_id!r}")
    authority = require_exact_authority(
        project.get("authority"), label="project authority contract"
    )

    source = project.get("source_of_truth")
    if not isinstance(source, dict):
        raise ProjectBundleError("project source_of_truth must be an object")
    state_relative = str(source.get("project_state", ""))
    state_path = _resolve_inside(repo_root, state_relative)
    state_sha256 = sha256_file(state_path)
    _require_equal(
        "project-state hash",
        state_sha256,
        _require_sha256(source.get("project_state_sha256"), "project_state_sha256"),
    )
    state = _load_json(state_path)
    _require_equal(
        "project-state schema",
        state.get("schema_version"),
        "sim2claw.autonomous_project_state.v1",
    )
    _require_equal(
        "project-state training lock", state.get("training_lock"), PROJECT_TRAINING_LOCK
    )
    _require_equal(
        "project-state promotion owner",
        state.get("promotion_owner"),
        PROJECT_PIPELINE_CONTRACT["promotion_owner"],
    )
    _require_exact_typed_contract(
        project.get("pipeline"), PROJECT_PIPELINE_CONTRACT, label="project pipeline contract"
    )
    locked = state.get("locked_product_evaluation")
    if not isinstance(locked, dict):
        raise ProjectBundleError("project state has no locked_product_evaluation object")

    contract_relative = str(source.get("evaluation_contract", ""))
    contract_path = _resolve_inside(repo_root, contract_relative)
    contract_sha256 = sha256_file(contract_path)
    declared_contract_sha256 = _require_sha256(
        source.get("evaluation_contract_sha256"), "evaluation_contract_sha256"
    )
    _require_equal("frozen evaluation contract hash", contract_sha256, declared_contract_sha256)
    contract = _load_json(contract_path)
    evaluation_set_id = str(contract.get("evaluation_set_id", ""))
    _require_equal("project-state evaluation ID", locked.get("evaluation_set_id"), evaluation_set_id)
    _require_equal("project-state evaluation path", locked.get("contract"), contract_relative)
    _require_equal("project-state evaluation hash", locked.get("sha256"), contract_sha256)

    scope = project.get("scope")
    if not isinstance(scope, dict):
        raise ProjectBundleError("project scope must be an object")
    _require_equal("project files", scope.get("files"), list("bcdefg"))
    _require_equal("project ranks", scope.get("ranks"), [1, 2])
    _require_equal("A/H exclusion", scope.get("include_a_or_h"), False)
    declared_skill_ids = scope.get("directed_skill_ids")
    _require_equal("project directed skill identities", declared_skill_ids, list(EXPECTED_BG_SKILL_IDS))
    _require_equal("project directed skill count", scope.get("directed_skill_count"), 12)

    raw_skills = contract.get("skills")
    if not isinstance(raw_skills, list):
        raise ProjectBundleError("evaluation contract skills must be a list")
    observed_specs = [
        {key: skill.get(key) for key in EXPECTED_BG_SKILL_SPECS[0]}
        for skill in raw_skills
        if isinstance(skill, dict)
    ]
    _require_equal(
        "frozen B-G bidirectional skill contract",
        observed_specs,
        list(EXPECTED_BG_SKILL_SPECS),
    )
    _require_equal("project-state directed case count", locked.get("core_directed_cases"), 12)
    _require_equal("project-state files", locked.get("files"), list("bcdefg"))

    catalog_relative = str(source.get("physical_source_catalog", ""))
    catalog_path = _resolve_inside(repo_root, catalog_relative)
    catalog_sha256 = sha256_file(catalog_path)
    declared_catalog_sha256 = _require_sha256(
        source.get("physical_source_catalog_sha256"), "physical_source_catalog_sha256"
    )
    _require_equal("physical source catalog hash", catalog_sha256, declared_catalog_sha256)
    catalog = _load_json(catalog_path)
    _require_equal(
        "physical source catalog schema",
        catalog.get("schema_version"),
        "sim2claw.physical_pawn_move_catalog.v1",
    )
    benchmark_scope = contract.get("benchmark_scope")
    if not isinstance(benchmark_scope, dict):
        raise ProjectBundleError("evaluation contract benchmark_scope must be an object")
    _require_equal(
        "evaluation physical source catalog path",
        benchmark_scope.get("current_physical_corpus"),
        catalog_relative,
    )
    episodes = catalog.get("episodes")
    if not isinstance(episodes, list):
        raise ProjectBundleError("physical source catalog episodes must be a list")
    _require_equal(
        "project-state catalog episode count",
        locked.get("current_catalog_episode_count"),
        len(episodes),
    )

    entries = project.get("bundle_entries")
    _require_exact_typed_contract(
        entries, list(PROJECT_BUNDLE_ENTRIES), label="project bundle-entry contract"
    )
    assert isinstance(entries, list)
    artifacts: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProjectBundleError("project bundle entry must be an object")
        relative = str(entry.get("path", ""))
        path = _resolve_inside(repo_root, relative)
        if not path.exists():
            if entry.get("required", True):
                raise ProjectBundleError(f"required bundle entry is missing: {relative}")
            continue
        for file_path in _iter_files(path):
            artifact_path = file_path.relative_to(repo_root).as_posix()
            _safe_archive_name(artifact_path)
            if artifact_path in seen_paths:
                raise ProjectBundleError(f"duplicate bundle artifact path: {artifact_path}")
            seen_paths.add(artifact_path)
            item = {
                "path": artifact_path,
                "bytes": file_path.stat().st_size,
                "proof_class": _expected_artifact_proof_class(artifact_path),
            }
            if hash_artifacts:
                item["sha256"] = sha256_file(file_path)
            artifacts.append(item)
    artifacts.sort(key=lambda item: item["path"])
    return {
        "schema_version": PROJECT_INSPECTION_SCHEMA,
        "project_id": project_id,
        "project_manifest_sha256": sha256_file(project_file),
        "project_path": project_file.relative_to(repo_root).as_posix(),
        "project_state": state_relative,
        "project_state_sha256": state_sha256,
        "evaluation_set_id": evaluation_set_id,
        "evaluation_contract_sha256": contract_sha256,
        "physical_source_catalog": catalog_relative,
        "physical_source_catalog_sha256": catalog_sha256,
        "directed_skill_ids": list(EXPECTED_BG_SKILL_IDS),
        "directed_skill_count": len(EXPECTED_BG_SKILL_IDS),
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(int(item["bytes"]) for item in artifacts),
        "artifacts": artifacts,
        "authority": authority,
        "claim_boundary": project.get("claim_boundary"),
        "ready": True,
    }


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(_safe_archive_name(name))
    info.size = len(payload)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(payload))


def _add_file(archive: tarfile.TarFile, name: str, path: Path) -> None:
    info = tarfile.TarInfo(_safe_archive_name(name))
    info.size = path.stat().st_size
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    with path.open("rb") as handle:
        archive.addfile(info, handle)


def pack_project(
    project_path: Path,
    output_path: Path,
    *,
    repo_root: Path = REPO_ROOT,
    require_clean_git: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    revision = git_source_revision(repo_root, require_clean_git=require_clean_git)
    inspection = inspect_project(project_path, repo_root=repo_root, hash_artifacts=True)
    project_file = _resolve_inside(repo_root, str(project_path))
    project = _load_json(project_file)
    metadata: dict[str, bytes] = {
        BUNDLE_METADATA_FILES[0]: project_file.read_bytes(),
        BUNDLE_METADATA_FILES[1]: (
            json.dumps(revision, indent=2, sort_keys=True) + "\n"
        ).encode(),
        BUNDLE_METADATA_FILES[2]: (
            json.dumps(inspection, indent=2, sort_keys=True) + "\n"
        ).encode(),
        BUNDLE_METADATA_FILES[3]: "".join(
            f"{item['sha256']}  {item['path']}\n" for item in inspection["artifacts"]
        ).encode(),
    }
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w", format=tarfile.PAX_FORMAT) as archive:
        for name in BUNDLE_METADATA_FILES:
            _add_bytes(archive, name, metadata[name])
        for item in inspection["artifacts"]:
            _add_file(archive, item["path"], repo_root / item["path"])
    bundle_sha256 = sha256_file(output_path)
    return {
        "schema_version": "sim2claw.project_bundle_receipt.v1",
        "project_id": project.get("project_id"),
        "project_manifest_sha256": inspection["project_manifest_sha256"],
        "bundle": str(output_path),
        "bundle_sha256": bundle_sha256,
        "bundle_bytes": output_path.stat().st_size,
        "artifact_count": inspection["artifact_count"],
        "artifact_bytes": inspection["artifact_bytes"],
        "source_revision": revision,
        "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        "physical_authority": False,
    }


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = archive.extractfile(member)
    if handle is None:
        raise ProjectBundleError(f"bundle member cannot be read: {member.name}")
    return handle.read()


def inspect_source_archive(
    archive_path: Path,
    *,
    expected_sha256: str,
    expected_revision: str,
) -> dict[str, Any]:
    """Audit the exact Git source archive before any deployment extraction."""
    archive_path = archive_path.resolve()
    expected_sha256 = _require_sha256(expected_sha256, "expected source archive SHA-256")
    if GIT_OBJECT_PATTERN.fullmatch(expected_revision) is None:
        raise ProjectBundleError("expected source revision is invalid")
    observed_sha256 = sha256_file(archive_path)
    _require_equal("source archive SHA-256", observed_sha256, expected_sha256)
    try:
        archive = tarfile.open(archive_path, "r:*")
    except (OSError, tarfile.TarError) as error:
        raise ProjectBundleError(f"cannot open source archive: {error}") from error
    with archive:
        members = archive.getmembers()
        by_name: dict[str, tarfile.TarInfo] = {}
        regular_file_count = 0
        directory_count = 0
        for member in members:
            name = _safe_archive_name(member.name)
            if name in by_name:
                raise ProjectBundleError(f"duplicate source archive member: {name}")
            if member.isfile():
                regular_file_count += 1
            elif member.isdir():
                directory_count += 1
            else:
                raise ProjectBundleError(
                    "source archive members must be regular files or directories, "
                    f"not type {member.type!r}: {name}"
                )
            by_name[name] = member
        identity_member = by_name.get(SOURCE_ARCHIVE_IDENTITY_MEMBER)
        if identity_member is None or not identity_member.isfile():
            raise ProjectBundleError("source archive identity member is missing or non-regular")
        forbidden_metadata = sorted(
            name
            for name in by_name
            if name.startswith("_sim2claw_source/")
            and name != SOURCE_ARCHIVE_IDENTITY_MEMBER
        )
        if forbidden_metadata:
            raise ProjectBundleError(
                f"unexpected source archive metadata members: {forbidden_metadata}"
            )
        try:
            identity = json.loads(_read_member(archive, identity_member))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProjectBundleError(f"source archive identity is invalid JSON: {error}") from error
        _require_exact_typed_contract(
            identity,
            {
                "git_head": expected_revision,
                "schema_version": SOURCE_ARCHIVE_IDENTITY_SCHEMA,
                "working_tree_clean": True,
            },
            label="source archive identity",
        )
    return {
        "schema_version": "sim2claw.source_archive_inspection.v1",
        "source_archive": str(archive_path),
        "source_archive_sha256": observed_sha256,
        "source_revision": expected_revision,
        "regular_file_count": regular_file_count,
        "directory_count": directory_count,
        "member_count": len(members),
        "member_types_accepted": ["regular_file", "directory"],
        "verified": True,
    }


def inspect_bundle(
    bundle_path: Path,
    *,
    expected_sha256: str,
    require_clean_source: bool = True,
) -> dict[str, Any]:
    bundle_path = bundle_path.resolve()
    expected_sha256 = _require_sha256(expected_sha256, "expected bundle SHA-256")
    observed_outer_sha256 = sha256_file(bundle_path)
    _require_equal("outer bundle SHA-256", observed_outer_sha256, expected_sha256)

    try:
        archive = tarfile.open(bundle_path, "r:*")
    except (OSError, tarfile.TarError) as error:
        raise ProjectBundleError(f"cannot open project bundle: {error}") from error
    with archive:
        members = archive.getmembers()
        names: list[str] = []
        by_name: dict[str, tarfile.TarInfo] = {}
        for member in members:
            name = _safe_archive_name(member.name)
            if name in by_name:
                raise ProjectBundleError(f"duplicate archive member: {name}")
            if not member.isfile():
                raise ProjectBundleError(
                    f"archive member must be a regular file, not type {member.type!r}: {name}"
                )
            names.append(name)
            by_name[name] = member
        missing_metadata = set(BUNDLE_METADATA_FILES) - set(names)
        if missing_metadata:
            raise ProjectBundleError(
                f"bundle metadata members are missing: {sorted(missing_metadata)}"
            )

        try:
            project = json.loads(_read_member(archive, by_name[BUNDLE_METADATA_FILES[0]]))
            revision = json.loads(_read_member(archive, by_name[BUNDLE_METADATA_FILES[1]]))
            manifest = json.loads(_read_member(archive, by_name[BUNDLE_METADATA_FILES[2]]))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ProjectBundleError(f"bundle metadata JSON is invalid: {error}") from error
        if not all(isinstance(value, dict) for value in (project, revision, manifest)):
            raise ProjectBundleError("bundle JSON metadata members must contain objects")
        _require_equal("bundle project schema", project.get("schema_version"), PROJECT_SCHEMA)
        _require_equal(
            "bundle inspection schema", manifest.get("schema_version"), PROJECT_INSPECTION_SCHEMA
        )
        _require_equal("bundle project ID", manifest.get("project_id"), project.get("project_id"))
        _require_equal(
            "bundle project manifest hash",
            manifest.get("project_manifest_sha256"),
            hashlib.sha256(_read_member(archive, by_name[BUNDLE_METADATA_FILES[0]])).hexdigest(),
        )
        source = project.get("source_of_truth")
        if not isinstance(source, dict):
            raise ProjectBundleError("bundle project source_of_truth must be an object")
        scope = project.get("scope")
        if not isinstance(scope, dict):
            raise ProjectBundleError("bundle project scope must be an object")
        _require_equal("bundle project files", scope.get("files"), list("bcdefg"))
        _require_equal("bundle project ranks", scope.get("ranks"), [1, 2])
        _require_equal("bundle project A/H exclusion", scope.get("include_a_or_h"), False)
        _require_equal(
            "bundle project directed skill count", scope.get("directed_skill_count"), 12
        )
        _require_equal(
            "bundle project directed skill identities",
            scope.get("directed_skill_ids"),
            list(EXPECTED_BG_SKILL_IDS),
        )
        _require_exact_typed_contract(
            project.get("bundle_entries"),
            list(PROJECT_BUNDLE_ENTRIES),
            label="bundle project bundle-entry contract",
        )
        _require_exact_typed_contract(
            project.get("pipeline"),
            PROJECT_PIPELINE_CONTRACT,
            label="bundle project pipeline contract",
        )
        for manifest_key, source_key in (
            ("project_state", "project_state"),
            ("project_state_sha256", "project_state_sha256"),
            ("evaluation_contract_sha256", "evaluation_contract_sha256"),
            ("physical_source_catalog", "physical_source_catalog"),
            ("physical_source_catalog_sha256", "physical_source_catalog_sha256"),
        ):
            _require_equal(
                f"bundle {manifest_key}", manifest.get(manifest_key), source.get(source_key)
            )
        _require_sha256(manifest.get("project_state_sha256"), "bundle project-state SHA-256")
        _require_sha256(
            manifest.get("evaluation_contract_sha256"),
            "bundle evaluation-contract SHA-256",
        )
        _require_sha256(
            manifest.get("physical_source_catalog_sha256"),
            "bundle physical-source-catalog SHA-256",
        )
        _require_equal(
            "bundle directed skill identities",
            manifest.get("directed_skill_ids"),
            list(EXPECTED_BG_SKILL_IDS),
        )
        _require_equal("bundle directed skill count", manifest.get("directed_skill_count"), 12)
        project_authority = require_exact_authority(
            project.get("authority"), label="bundle project authority contract"
        )
        manifest_authority = require_exact_authority(
            manifest.get("authority"), label="bundle inspection authority contract"
        )
        _require_equal(
            "bundle authority contract", manifest_authority, project_authority
        )
        _require_equal("bundle inspection readiness", manifest.get("ready"), True)
        _require_equal(
            "source revision schema",
            revision.get("schema_version"),
            "sim2claw.source_revision.v1",
        )
        if revision.get("git_repository") is False:
            _require_equal("non-Git working-tree cleanliness", revision.get("working_tree_clean"), None)
        elif revision.get("git_repository") is True:
            if GIT_OBJECT_PATTERN.fullmatch(str(revision.get("git_head"))) is None:
                raise ProjectBundleError("source revision Git HEAD is invalid")
            if not isinstance(revision.get("working_tree_clean"), bool):
                raise ProjectBundleError("Git source revision must declare boolean cleanliness")
        else:
            raise ProjectBundleError("source revision git_repository must be true or false")
        if require_clean_source and (
            revision.get("git_repository") is not True
            or revision.get("working_tree_clean") is not True
        ):
            raise ProjectBundleError(
                "deployment bundle requires a clean committed Git source revision"
            )

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list):
            raise ProjectBundleError("bundle artifact manifest artifacts must be a list")
        artifact_paths: list[str] = []
        canonical_sums: list[str] = []
        verified = 0
        for item in artifacts:
            if not isinstance(item, dict):
                raise ProjectBundleError("bundle artifact entry must be an object")
            path = _safe_archive_name(str(item.get("path", "")))
            if path.startswith(f"{BUNDLE_METADATA_ROOT}/"):
                raise ProjectBundleError(f"artifact path collides with metadata: {path}")
            if path in artifact_paths:
                raise ProjectBundleError(f"duplicate artifact manifest path: {path}")
            expected_artifact_sha256 = _require_sha256(
                item.get("sha256"), f"artifact SHA-256 for {path}"
            )
            expected_bytes = item.get("bytes")
            if not isinstance(expected_bytes, int) or expected_bytes < 0:
                raise ProjectBundleError(f"artifact byte count is invalid: {path}")
            _require_equal(
                f"artifact proof class for {path}",
                item.get("proof_class"),
                _expected_artifact_proof_class(path),
            )
            member = by_name.get(path)
            if member is None:
                raise ProjectBundleError(f"bundle artifact is missing: {path}")
            _require_equal(f"artifact byte count for {path}", member.size, expected_bytes)
            payload = _read_member(archive, member)
            _require_equal(
                f"bundle artifact hash for {path}",
                hashlib.sha256(payload).hexdigest(),
                expected_artifact_sha256,
            )
            artifact_paths.append(path)
            canonical_sums.append(f"{expected_artifact_sha256}  {path}\n")
            verified += 1

        expected_members = set(BUNDLE_METADATA_FILES) | set(artifact_paths)
        if set(names) != expected_members:
            extras = sorted(set(names) - expected_members)
            missing = sorted(expected_members - set(names))
            raise ProjectBundleError(
                f"bundle member set mismatch: extra={extras}, missing={missing}"
            )
        _require_equal("artifact count", manifest.get("artifact_count"), len(artifacts))
        observed_sums = _read_member(archive, by_name[BUNDLE_METADATA_FILES[3]]).decode()
        _require_equal("sha256sums.txt", observed_sums, "".join(canonical_sums))

    return {
        "schema_version": "sim2claw.project_bundle_inspection.v1",
        "bundle": str(bundle_path),
        "bundle_sha256": observed_outer_sha256,
        "project_id": manifest.get("project_id"),
        "project_manifest_sha256": manifest.get("project_manifest_sha256"),
        "evaluation_set_id": manifest.get("evaluation_set_id"),
        "evaluation_contract_sha256": manifest.get("evaluation_contract_sha256"),
        "artifact_count": manifest.get("artifact_count"),
        "verified_artifact_count": verified,
        "verified": verified == manifest.get("artifact_count"),
        "source_revision": revision,
        "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        "physical_authority": False,
    }
