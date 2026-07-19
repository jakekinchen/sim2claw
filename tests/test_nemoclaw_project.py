from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from sim2claw.autonomous_pipeline import (
    PipelineStateError,
    pipeline_status,
    run_stage,
)
from sim2claw.cli import build_parser
from sim2claw.doctor import run_doctor
from sim2claw.deployment_receipt import DeploymentReceiptError, write_receipt
from sim2claw.project_bundle import (
    BUNDLE_METADATA_FILES,
    EXPECTED_BG_SKILL_IDS,
    EXPECTED_BG_SKILL_SPECS,
    PROJECT_AUTHORITY_CONTRACT,
    PROJECT_BUNDLE_ENTRIES,
    PROJECT_PIPELINE_CONTRACT,
    PROJECT_TRAINING_LOCK,
    ProjectBundleError,
    inspect_bundle,
    inspect_project,
    inspect_source_archive,
    pack_project,
    sha256_file,
)
from sim2claw.studio_server import create_server


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _refresh_bindings(repo: Path, project_path: Path) -> None:
    project_file = repo / project_path
    project = json.loads(project_file.read_text())
    source = project["source_of_truth"]
    contract_path = repo / source["evaluation_contract"]
    state_path = repo / source["project_state"]
    catalog_path = repo / source["physical_source_catalog"]
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    catalog_sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    state = json.loads(state_path.read_text())
    state["locked_product_evaluation"]["contract"] = source["evaluation_contract"]
    state["locked_product_evaluation"]["sha256"] = contract_sha
    _write_json(state_path, state)
    source["evaluation_contract_sha256"] = contract_sha
    source["physical_source_catalog_sha256"] = catalog_sha
    source["project_state_sha256"] = hashlib.sha256(state_path.read_bytes()).hexdigest()
    _write_json(project_file, project)


def _write_fixture(repo: Path, project_id: str = "fixture-bg") -> Path:
    contract_path = repo / "configs/evaluations/frozen.json"
    catalog_path = repo / "configs/data/physical_pawn_move_catalog_20260719.json"
    state_path = repo / "docs/autonomous-workflow/project_state.json"
    project_path = Path(f"configs/projects/{project_id}.json")
    _write_json(
        contract_path,
        {
            "schema_version": "sim2claw.pawn_bidirectional_composability_eval.v2",
            "evaluation_set_id": "fixture-bg-evaluation",
            "benchmark_scope": {
                "current_physical_corpus": (
                    "configs/data/physical_pawn_move_catalog_20260719.json"
                )
            },
            "skills": list(EXPECTED_BG_SKILL_SPECS),
        },
    )
    _write_json(
        catalog_path,
        {
            "schema_version": "sim2claw.physical_pawn_move_catalog.v1",
            "catalog_id": "fixture-catalog",
            "episodes": [{"recording_id": "fixture-episode"}],
        },
    )
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    _write_json(
        state_path,
        {
            "schema_version": "sim2claw.autonomous_project_state.v1",
            "locked_product_evaluation": {
                "evaluation_set_id": "fixture-bg-evaluation",
                "contract": "configs/evaluations/frozen.json",
                "sha256": contract_sha,
                "core_directed_cases": 12,
                "files": list("bcdefg"),
                "current_catalog_episode_count": 1,
            },
            "training_lock": PROJECT_TRAINING_LOCK,
            "promotion_owner": PROJECT_PIPELINE_CONTRACT["promotion_owner"],
            "workspace_registration": {"status": "unqualified"},
        },
    )
    _write_json(
        repo / "datasets/manipulation_source_recordings/fixture.json",
        {"proof_class": "physical_teleoperation_source_unqualified"},
    )
    _write_json(
        repo / "outputs/pawn_composability/recovered_corpus_v2/fixture.json",
        {"proof_class": "retrospective_source_score_and_review_material"},
    )
    _write_json(
        repo / project_path,
        {
            "schema_version": "sim2claw.project.v1",
            "project_id": project_id,
            "source_of_truth": {
                "project_state": "docs/autonomous-workflow/project_state.json",
                "project_state_sha256": hashlib.sha256(state_path.read_bytes()).hexdigest(),
                "evaluation_contract": "configs/evaluations/frozen.json",
                "evaluation_contract_sha256": contract_sha,
                "physical_source_catalog": (
                    "configs/data/physical_pawn_move_catalog_20260719.json"
                ),
                "physical_source_catalog_sha256": hashlib.sha256(
                    catalog_path.read_bytes()
                ).hexdigest(),
            },
            "scope": {
                "files": list("bcdefg"),
                "ranks": [1, 2],
                "directed_skill_count": 12,
                "directed_skill_ids": list(EXPECTED_BG_SKILL_IDS),
                "include_a_or_h": False,
            },
            "bundle_entries": list(PROJECT_BUNDLE_ENTRIES),
            "pipeline": copy.deepcopy(PROJECT_PIPELINE_CONTRACT),
            "authority": dict(PROJECT_AUTHORITY_CONTRACT),
        },
    )
    return project_path


def _pack_fixture(repo: Path, project: Path) -> tuple[Path, str]:
    bundle = repo / "project.tar"
    receipt = pack_project(
        project,
        bundle,
        repo_root=repo,
        require_clean_git=False,
    )
    return bundle, receipt["bundle_sha256"]


def _inspect_fixture_bundle(bundle: Path, digest: str) -> dict[str, object]:
    return inspect_bundle(
        bundle,
        expected_sha256=digest,
        require_clean_source=False,
    )


def _rewrite_archive(
    source: Path,
    destination: Path,
    *,
    exclude: set[str] | None = None,
    replace: dict[str, bytes] | None = None,
    append: list[tuple[tarfile.TarInfo, bytes]] | None = None,
) -> None:
    exclude = exclude or set()
    replace = replace or {}
    append = append or []
    with tarfile.open(source, "r") as archive:
        rows = []
        for member in archive.getmembers():
            if member.name in exclude:
                continue
            handle = archive.extractfile(member)
            payload = handle.read() if handle is not None else b""
            rows.append((copy.copy(member), replace.get(member.name, payload)))
    with tarfile.open(destination, "w") as archive:
        for member, payload in rows + append:
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload) if member.isfile() else None)


def _regular_member(name: str, payload: bytes = b"extra") -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    return member, payload


def _write_source_archive(path: Path, revision: str = "a" * 40) -> str:
    identity = json.dumps(
        {
            "git_head": revision,
            "schema_version": "sim2claw.source_archive_identity.v1",
            "working_tree_clean": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    with tarfile.open(path, "w") as archive:
        directory = tarfile.TarInfo("src")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        source = b"print('fixture')\n"
        file_member = tarfile.TarInfo("src/main.py")
        file_member.size = len(source)
        archive.addfile(file_member, io.BytesIO(source))
        identity_member = tarfile.TarInfo("_sim2claw_source/revision.json")
        identity_member.size = len(identity)
        archive.addfile(identity_member, io.BytesIO(identity))
    return sha256_file(path)


def test_project_bundle_round_trip_requires_outer_digest(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    inspection = inspect_project(project, repo_root=tmp_path)
    assert inspection["directed_skill_ids"] == list(EXPECTED_BG_SKILL_IDS)
    bundle, digest = _pack_fixture(tmp_path, project)
    verified = _inspect_fixture_bundle(bundle, digest)
    assert verified["verified"] is True
    assert verified["verified_artifact_count"] == 3
    assert verified["authority"] == PROJECT_AUTHORITY_CONTRACT
    with pytest.raises(ProjectBundleError, match="outer bundle SHA-256 mismatch"):
        _inspect_fixture_bundle(bundle, "0" * 64)


def test_source_archive_audit_accepts_only_bound_files_and_directories(
    tmp_path: Path,
) -> None:
    revision = "a" * 40
    archive = tmp_path / "source.tar"
    digest = _write_source_archive(archive, revision)
    result = inspect_source_archive(
        archive, expected_sha256=digest, expected_revision=revision
    )
    assert result["verified"] is True
    assert result["regular_file_count"] == 2
    assert result["directory_count"] == 1

    with tarfile.open(archive, "a") as handle:
        unsafe = tarfile.TarInfo("src/shadow.py")
        unsafe.type = tarfile.SYMTYPE
        unsafe.linkname = "src/main.py"
        handle.addfile(unsafe)
    with pytest.raises(ProjectBundleError, match="regular files or directories"):
        inspect_source_archive(
            archive,
            expected_sha256=sha256_file(archive),
            expected_revision=revision,
        )


def test_source_archive_audit_rejects_identity_and_member_drift(tmp_path: Path) -> None:
    revision = "b" * 40
    archive = tmp_path / "source.tar"
    _write_source_archive(archive, revision)
    with pytest.raises(ProjectBundleError, match="source archive identity.git_head"):
        inspect_source_archive(
            archive,
            expected_sha256=sha256_file(archive),
            expected_revision="c" * 40,
        )

    duplicate = tmp_path / "duplicate.tar"
    _rewrite_archive(
        archive,
        duplicate,
        append=[_regular_member("src/main.py", b"different")],
    )
    with pytest.raises(ProjectBundleError, match="duplicate source archive member"):
        inspect_source_archive(
            duplicate,
            expected_sha256=sha256_file(duplicate),
            expected_revision=revision,
        )


@pytest.mark.parametrize("name", ["../escape", "/absolute", "./not-normal"])
def test_bundle_rejects_unsafe_member_paths(tmp_path: Path, name: str) -> None:
    project = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project)
    malicious = tmp_path / "unsafe.tar"
    _rewrite_archive(bundle, malicious, append=[_regular_member(name)])
    with pytest.raises(ProjectBundleError, match="unsafe archive member path"):
        _inspect_fixture_bundle(malicious, sha256_file(malicious))


@pytest.mark.parametrize(
    "member_type",
    [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.DIRTYPE],
)
def test_bundle_rejects_links_devices_and_directories(
    tmp_path: Path, member_type: bytes
) -> None:
    project = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project)
    member = tarfile.TarInfo("unsafe-member")
    member.type = member_type
    member.linkname = "datasets/source/receipt.json"
    malicious = tmp_path / f"type-{member_type.hex()}.tar"
    _rewrite_archive(bundle, malicious, append=[(member, b"")])
    with pytest.raises(ProjectBundleError, match="must be a regular file"):
        _inspect_fixture_bundle(malicious, sha256_file(malicious))


def test_bundle_rejects_duplicate_and_extra_members(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project)
    with tarfile.open(bundle, "r") as archive:
        member = copy.copy(archive.getmembers()[0])
        payload = archive.extractfile(archive.getmembers()[0]).read()  # type: ignore[union-attr]
    duplicate = tmp_path / "duplicate.tar"
    _rewrite_archive(bundle, duplicate, append=[(member, payload)])
    with pytest.raises(ProjectBundleError, match="duplicate archive member"):
        _inspect_fixture_bundle(duplicate, sha256_file(duplicate))

    extra = tmp_path / "extra.tar"
    _rewrite_archive(bundle, extra, append=[_regular_member("extra.txt")])
    with pytest.raises(ProjectBundleError, match="member set mismatch"):
        _inspect_fixture_bundle(extra, sha256_file(extra))


def test_bundle_requires_exact_metadata_and_sums(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project)
    missing = tmp_path / "missing.tar"
    _rewrite_archive(bundle, missing, exclude={BUNDLE_METADATA_FILES[0]})
    with pytest.raises(ProjectBundleError, match="metadata members are missing"):
        _inspect_fixture_bundle(missing, sha256_file(missing))

    bad_sums = tmp_path / "bad-sums.tar"
    _rewrite_archive(
        bundle,
        bad_sums,
        replace={BUNDLE_METADATA_FILES[3]: b"0" * 64 + b"  wrong\n"},
    )
    with pytest.raises(ProjectBundleError, match="sha256sums.txt mismatch"):
        _inspect_fixture_bundle(bad_sums, sha256_file(bad_sums))


def test_bundle_rejects_internally_inconsistent_project_bindings(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project)
    with tarfile.open(bundle, "r") as archive:
        manifest = json.loads(
            archive.extractfile(BUNDLE_METADATA_FILES[2]).read()  # type: ignore[union-attr]
        )
    manifest["physical_source_catalog_sha256"] = "0" * 64
    inconsistent = tmp_path / "inconsistent.tar"
    _rewrite_archive(
        bundle,
        inconsistent,
        replace={
            BUNDLE_METADATA_FILES[2]: (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            ).encode()
        },
    )
    with pytest.raises(ProjectBundleError, match="bundle physical_source_catalog_sha256"):
        _inspect_fixture_bundle(inconsistent, sha256_file(inconsistent))


def test_bundle_rejects_unsafe_project_and_inspection_authority(tmp_path: Path) -> None:
    project_path = _write_fixture(tmp_path)
    bundle, _ = _pack_fixture(tmp_path, project_path)
    with tarfile.open(bundle, "r") as archive:
        project = json.loads(
            archive.extractfile(BUNDLE_METADATA_FILES[0]).read()  # type: ignore[union-attr]
        )
        manifest = json.loads(
            archive.extractfile(BUNDLE_METADATA_FILES[2]).read()  # type: ignore[union-attr]
        )
    original_manifest = copy.deepcopy(manifest)

    project["authority"]["robot_motion_allowed"] = True
    project_payload = (json.dumps(project, indent=2, sort_keys=True) + "\n").encode()
    manifest["project_manifest_sha256"] = hashlib.sha256(project_payload).hexdigest()
    unsafe_project = tmp_path / "unsafe-project-authority.tar"
    _rewrite_archive(
        bundle,
        unsafe_project,
        replace={
            BUNDLE_METADATA_FILES[0]: project_payload,
            BUNDLE_METADATA_FILES[2]: (
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            ).encode(),
        },
    )
    with pytest.raises(ProjectBundleError, match="bundle project authority contract"):
        _inspect_fixture_bundle(unsafe_project, sha256_file(unsafe_project))

    original_manifest["authority"]["held_out_rows_opened"] = 99
    unsafe_inspection = tmp_path / "unsafe-inspection-authority.tar"
    _rewrite_archive(
        bundle,
        unsafe_inspection,
        replace={
            BUNDLE_METADATA_FILES[2]: (
                json.dumps(original_manifest, indent=2, sort_keys=True) + "\n"
            ).encode()
        },
    )
    with pytest.raises(ProjectBundleError, match="bundle inspection authority contract"):
        _inspect_fixture_bundle(unsafe_inspection, sha256_file(unsafe_inspection))


def test_pack_requires_clean_committed_git_or_explicit_non_git(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    with pytest.raises(ProjectBundleError, match="not a readable Git worktree"):
        pack_project(project, tmp_path / "strict.tar", repo_root=tmp_path)
    receipt = pack_project(
        project,
        tmp_path / "non-git.tar",
        repo_root=tmp_path,
        require_clean_git=False,
    )
    assert receipt["source_revision"]["git_repository"] is False
    assert receipt["source_revision"]["working_tree_clean"] is None
    with pytest.raises(ProjectBundleError, match="clean committed Git source revision"):
        inspect_bundle(
            tmp_path / "non-git.tar",
            expected_sha256=receipt["bundle_sha256"],
        )

    (tmp_path / ".gitignore").write_text("datasets/\n*.tar\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    clean = pack_project(project, tmp_path / "clean.tar", repo_root=tmp_path)
    assert clean["source_revision"]["working_tree_clean"] is True
    assert inspect_bundle(
        tmp_path / "clean.tar", expected_sha256=clean["bundle_sha256"]
    )["verified"] is True
    inspector = (
        Path(__file__).parents[1]
        / "scripts/nemoclaw/inspect-project-bundle.py"
    )
    python_path = str(Path(__file__).parents[1] / "src")
    wrong_revision = subprocess.run(
        [
            sys.executable,
            str(inspector),
            str(tmp_path / "clean.tar"),
            clean["bundle_sha256"],
            "f" * 40,
        ],
        env={**os.environ, "PYTHONPATH": python_path},
        capture_output=True,
        text=True,
        check=False,
    )
    assert wrong_revision.returncode != 0
    assert "source revision does not match" in wrong_revision.stderr
    correct_revision = subprocess.run(
        [
            sys.executable,
            str(inspector),
            str(tmp_path / "clean.tar"),
            clean["bundle_sha256"],
            clean["source_revision"]["git_head"],
        ],
        env={**os.environ, "PYTHONPATH": python_path},
        capture_output=True,
        text=True,
        check=False,
    )
    assert correct_revision.returncode == 0, correct_revision.stderr
    (tmp_path / "untracked-secret.env").write_text("secret", encoding="utf-8")
    with pytest.raises(ProjectBundleError, match="clean committed HEAD"):
        pack_project(project, tmp_path / "dirty.tar", repo_root=tmp_path)


def test_project_rejects_count_only_skill_substitution(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    contract_path = tmp_path / "configs/evaluations/frozen.json"
    contract = json.loads(contract_path.read_text())
    contract["skills"][-1]["skill_id"] = "pawn_h1_to_h2"
    _write_json(contract_path, contract)
    _refresh_bindings(tmp_path, project)
    with pytest.raises(ProjectBundleError, match="frozen B-G bidirectional skill contract"):
        inspect_project(project, repo_root=tmp_path)


def test_project_rejects_state_evaluator_and_catalog_drift(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    state_path = tmp_path / "docs/autonomous-workflow/project_state.json"
    state = json.loads(state_path.read_text())
    state["locked_product_evaluation"]["evaluation_set_id"] = "different-evaluation"
    _write_json(state_path, state)
    project_payload = json.loads((tmp_path / project).read_text())
    project_payload["source_of_truth"]["project_state_sha256"] = hashlib.sha256(
        state_path.read_bytes()
    ).hexdigest()
    _write_json(tmp_path / project, project_payload)
    with pytest.raises(ProjectBundleError, match="project-state evaluation ID mismatch"):
        inspect_project(project, repo_root=tmp_path)

    project = _write_fixture(tmp_path)
    catalog_path = (
        tmp_path / "configs/data/physical_pawn_move_catalog_20260719.json"
    )
    catalog = json.loads(catalog_path.read_text())
    catalog["episodes"].append({"recording_id": "unbound"})
    _write_json(catalog_path, catalog)
    with pytest.raises(ProjectBundleError, match="physical source catalog hash mismatch"):
        inspect_project(project, repo_root=tmp_path)


def test_project_rejects_contract_catalog_path_drift(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    contract_path = tmp_path / "configs/evaluations/frozen.json"
    contract = json.loads(contract_path.read_text())
    contract["benchmark_scope"]["current_physical_corpus"] = "configs/data/other.json"
    _write_json(contract_path, contract)
    _refresh_bindings(tmp_path, project)
    with pytest.raises(ProjectBundleError, match="evaluation physical source catalog path"):
        inspect_project(project, repo_root=tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        "extra_root",
        "missing_root",
        "reordered_roots",
        "proof_class_substitution",
        "required_type_confusion",
    ],
)
def test_project_requires_exact_bundle_entry_contract(
    tmp_path: Path, mutation: str
) -> None:
    project_path = _write_fixture(tmp_path)
    project_file = tmp_path / project_path
    project = json.loads(project_file.read_text())
    entries = project["bundle_entries"]
    if mutation == "extra_root":
        entries.append(
            {"path": "README.md", "required": True, "proof_class": "documentation"}
        )
    elif mutation == "missing_root":
        entries.pop()
    elif mutation == "reordered_roots":
        entries[0], entries[1] = entries[1], entries[0]
    elif mutation == "proof_class_substitution":
        entries[1]["proof_class"] = "learned_policy_success"
    elif mutation == "required_type_confusion":
        entries[0]["required"] = 1
    _write_json(project_file, project)
    with pytest.raises(ProjectBundleError, match="project bundle-entry contract"):
        inspect_project(project_path, repo_root=tmp_path)


@pytest.mark.parametrize(
    ("surface", "value"),
    [
        ("stages", ["inspect"]),
        ("generated_roots", ["/"]),
        ("training_lock_source", "other.json"),
        ("promotion_owner", "training_loop"),
    ],
)
def test_project_requires_exact_pipeline_contract(
    tmp_path: Path, surface: str, value: object
) -> None:
    project_path = _write_fixture(tmp_path)
    project_file = tmp_path / project_path
    project = json.loads(project_file.read_text())
    project["pipeline"][surface] = value
    _write_json(project_file, project)
    with pytest.raises(ProjectBundleError, match="project pipeline contract"):
        inspect_project(project_path, repo_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("training_lock", "open"),
        ("promotion_owner", "training_loop"),
    ],
)
def test_project_requires_locked_state_promotion_contract(
    tmp_path: Path, field: str, value: str
) -> None:
    project_path = _write_fixture(tmp_path)
    state_path = tmp_path / "docs/autonomous-workflow/project_state.json"
    state = json.loads(state_path.read_text())
    state[field] = value
    _write_json(state_path, state)
    project_file = tmp_path / project_path
    project = json.loads(project_file.read_text())
    project["source_of_truth"]["project_state_sha256"] = hashlib.sha256(
        state_path.read_bytes()
    ).hexdigest()
    _write_json(project_file, project)
    with pytest.raises(ProjectBundleError, match=f"project-state {field.replace('_', ' ')}"):
        inspect_project(project_path, repo_root=tmp_path)


@pytest.mark.parametrize(
    "authority",
    [
        {**PROJECT_AUTHORITY_CONTRACT, "physical_authority": True},
        {**PROJECT_AUTHORITY_CONTRACT, "robot_motion_allowed": True},
        {**PROJECT_AUTHORITY_CONTRACT, "retrospective_recordings_can_promote": True},
        {**PROJECT_AUTHORITY_CONTRACT, "training_can_promote_itself": True},
        {**PROJECT_AUTHORITY_CONTRACT, "held_out_rows_opened": 99},
        {**PROJECT_AUTHORITY_CONTRACT, "physical_authority": 0},
        {**PROJECT_AUTHORITY_CONTRACT, "held_out_rows_opened": False},
        {
            key: value
            for key, value in PROJECT_AUTHORITY_CONTRACT.items()
            if key != "robot_motion_allowed"
        },
        {**PROJECT_AUTHORITY_CONTRACT, "unexpected_authority": False},
    ],
)
def test_project_rejects_unsafe_or_inexact_authority_contract(
    tmp_path: Path, authority: dict[str, object]
) -> None:
    project_path = _write_fixture(tmp_path)
    project = json.loads((tmp_path / project_path).read_text())
    project["authority"] = authority
    _write_json(tmp_path / project_path, project)
    with pytest.raises(ProjectBundleError, match="project authority contract"):
        inspect_project(project_path, repo_root=tmp_path)


def test_pipeline_status_is_project_scoped(tmp_path: Path) -> None:
    project_a = _write_fixture(tmp_path, "project-a")
    project_b = _write_fixture(tmp_path, "project-b")
    result_a = run_stage("inspect", project_a, repo_root=tmp_path)
    assert result_a["authority"] == PROJECT_AUTHORITY_CONTRACT
    status_a = pipeline_status(project_a, repo_root=tmp_path)
    assert status_a["latest_stage"] == "inspect"
    assert status_a["authority"] == PROJECT_AUTHORITY_CONTRACT
    assert pipeline_status(project_b, repo_root=tmp_path)["status"] == "not_started"

    b_path = (
        tmp_path
        / "runs/nemoclaw/projects/project-b/latest-stage-result.json"
    )
    _write_json(b_path, result_a)
    with pytest.raises(PipelineStateError, match="project_id mismatch"):
        pipeline_status(project_b, repo_root=tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "wrong", "schema_version mismatch"),
        ("stage", "open-held-outs", "invalid stage"),
        ("status", "success-ish", "invalid status"),
        (
            "authority",
            {**PROJECT_AUTHORITY_CONTRACT, "held_out_rows_opened": 99},
            "saved pipeline authority contract",
        ),
    ],
)
def test_pipeline_rejects_invalid_saved_contract(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    project = _write_fixture(tmp_path)
    run_stage("inspect", project, repo_root=tmp_path)
    latest = tmp_path / "runs/nemoclaw/projects/fixture-bg/latest-stage-result.json"
    result = json.loads(latest.read_text())
    result[field] = value
    _write_json(latest, result)
    with pytest.raises(PipelineStateError, match=message):
        pipeline_status(project, repo_root=tmp_path)


def test_pipeline_rejects_result_digest_tampering(tmp_path: Path) -> None:
    project = _write_fixture(tmp_path)
    run_stage("inspect", project, repo_root=tmp_path)
    latest = tmp_path / "runs/nemoclaw/projects/fixture-bg/latest-stage-result.json"
    result = json.loads(latest.read_text())
    result["summary"] = "inflated claim"
    _write_json(latest, result)
    with pytest.raises(PipelineStateError, match="digest mismatch"):
        pipeline_status(project, repo_root=tmp_path)


def test_read_only_studio_constructs_without_mutating_managers(tmp_path: Path) -> None:
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    with (
        patch(
            "sim2claw.studio_server.TeleopRecordingManager",
            side_effect=AssertionError("recorder must not be constructed"),
        ),
        patch(
            "sim2claw.studio_server.LiveWorkspaceService",
            side_effect=AssertionError("live workspace must not be constructed"),
        ),
    ):
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
    assert server.recorder is None
    assert server.live_workspace is None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(f"{base_url}/api/health") as response:
            health = json.load(response)
        assert health["service"] == "sim2claw-studio"
        assert health["mode"] == "read_only_evidence"
        assert health["read_only"] is True
        assert health["recorder_control"] == "disabled"
        assert health["physical_authority"] is False
        with pytest.raises(HTTPError) as error:
            urlopen(f"{base_url}/api/recorder")
        assert error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before


@pytest.mark.parametrize(
    ("surface", "key", "value", "message"),
    [
        ("health", "service", "wrong-service", "Studio health service mismatch"),
        ("health", "read_only", False, "Studio health read_only mismatch"),
        ("project", "evaluation_contract_sha256", "0" * 64, "project inspection"),
        (
            "project",
            "authority",
            {**PROJECT_AUTHORITY_CONTRACT, "training_can_promote_itself": True},
            "project inspection authority contract",
        ),
        ("pipeline", "project_id", "other-project", "pipeline status project_id"),
        ("pipeline", "project_path", "other.json", "pipeline status project_path"),
        (
            "pipeline",
            "authority",
            {**PROJECT_AUTHORITY_CONTRACT, "retrospective_recordings_can_promote": True},
            "pipeline status authority contract",
        ),
    ],
)
def test_receipt_rejects_mismatched_proof_before_writing(
    tmp_path: Path, surface: str, key: str, value: object, message: str
) -> None:
    project_path = _write_fixture(tmp_path)
    project = inspect_project(project_path, repo_root=tmp_path)
    run_stage("inspect", project_path, repo_root=tmp_path)
    pipeline = pipeline_status(project_path, repo_root=tmp_path)
    health = {
        "service": "sim2claw-studio",
        "read_only": True,
        "mode": "read_only_evidence",
        "recorder_control": "disabled",
        "physical_authority": False,
    }
    target = {"project": project, "pipeline": pipeline, "health": health}[surface]
    target[key] = value
    output = tmp_path / "receipt/deployment.json"
    with pytest.raises(DeploymentReceiptError, match=message):
        write_receipt(
            output,
            project_path=tmp_path / project_path,
            project=project,
            pipeline=pipeline,
            health=health,
            skill_sha256="1" * 64,
            source_revision="2" * 40,
            source_archive_sha256="3" * 64,
            project_bundle_sha256="4" * 64,
        )
    assert not output.exists()


def test_receipt_writes_only_validated_project_bound_proof(tmp_path: Path) -> None:
    project_path = _write_fixture(tmp_path)
    project = inspect_project(project_path, repo_root=tmp_path)
    run_stage("inspect", project_path, repo_root=tmp_path)
    pipeline = pipeline_status(project_path, repo_root=tmp_path)
    health = {
        "service": "sim2claw-studio",
        "read_only": True,
        "mode": "read_only_evidence",
        "recorder_control": "disabled",
        "physical_authority": False,
    }
    output = tmp_path / "receipt/deployment.json"
    receipt = write_receipt(
        output,
        project_path=tmp_path / project_path,
        project=project,
        pipeline=pipeline,
        health=health,
        skill_sha256="1" * 64,
        source_revision="2" * 40,
        source_archive_sha256="3" * 64,
        project_bundle_sha256="4" * 64,
    )
    assert output.is_file()
    assert receipt["project"]["project_id"] == "fixture-bg"
    assert receipt["studio_health"] == health
    assert receipt["authority"] == PROJECT_AUTHORITY_CONTRACT


def test_receipt_rejects_unsafe_latest_result_authority(tmp_path: Path) -> None:
    project_path = _write_fixture(tmp_path)
    project = inspect_project(project_path, repo_root=tmp_path)
    run_stage("inspect", project_path, repo_root=tmp_path)
    pipeline = pipeline_status(project_path, repo_root=tmp_path)
    pipeline["latest_stage_result"]["authority"]["robot_motion_allowed"] = True
    health = {
        "service": "sim2claw-studio",
        "read_only": True,
        "mode": "read_only_evidence",
        "recorder_control": "disabled",
        "physical_authority": False,
    }
    output = tmp_path / "receipt/deployment.json"
    with pytest.raises(
        DeploymentReceiptError, match="latest stage result authority contract"
    ):
        write_receipt(
            output,
            project_path=tmp_path / project_path,
            project=project,
            pipeline=pipeline,
            health=health,
            skill_sha256="1" * 64,
            source_revision="2" * 40,
            source_archive_sha256="3" * 64,
            project_bundle_sha256="4" * 64,
        )
    assert not output.exists()


def test_parser_and_linux_cpu_doctor_regression() -> None:
    args = build_parser().parse_args(["doctor", "--target", "linux-cpu"])
    assert args.target == "linux-cpu"
    bundle_args = build_parser().parse_args(
        [
            "project-inspect",
            "--project",
            "project.json",
            "--bundle",
            "project.tar",
            "--expected-bundle-sha256",
            "a" * 64,
        ]
    )
    assert bundle_args.expected_bundle_sha256 == "a" * 64
    with patch("sim2claw.doctor.platform.system", return_value="Linux"):
        report = run_doctor("linux-cpu")
    assert report["target"] == "linux-cpu"
    assert next(check for check in report["checks"] if check["name"] == "linux-host")[
        "passed"
    ] is True
    with pytest.raises(ValueError, match="unsupported doctor target"):
        run_doctor("unreviewed-target")


def test_deployment_scripts_are_fail_closed(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    deploy = (root / "scripts/nemoclaw/deploy.sh").read_text()
    source_inspector = (
        root / "scripts/nemoclaw/inspect-source-archive.py"
    ).read_text()
    bootstrap = (root / "scripts/nemoclaw/bootstrap.sh").read_text()
    studio = (root / "scripts/nemoclaw/start-studio.sh").read_text()
    verify = (root / "scripts/nemoclaw/verify-deployment.sh").read_text()
    receipt_module = (root / "src/sim2claw/deployment_receipt.py").read_text()

    assert "git archive" in deploy
    assert "REMOTE_IDENTIFIER_PATTERN" in deploy
    assert deploy.index(
        'validate_remote_identifier SIM2CLAW_BREV_INSTANCE "$REMOTE"'
    ) < deploy.index('cd "$REPO_ROOT"')
    assert deploy.index(
        'validate_remote_identifier SIM2CLAW_SANDBOX "$SANDBOX"'
    ) < deploy.index('cd "$REPO_ROOT"')
    assert 'REMOTE_STAGE="/tmp/sim2claw-nemoclaw-deploy/$source_revision"' in deploy
    assert "/home/ubuntu/nemoclaw-e3fca7" not in deploy
    assert "--add-virtual-file" in deploy
    assert "sim2claw.source_archive_identity.v1" in deploy
    assert "inspect-source-archive.py" in deploy
    assert deploy.index("inspect-source-archive.py") < deploy.index('brev exec "$REMOTE"')
    assert 'tar --exclude=\\"_sim2claw_source/*\\" -xf' in deploy
    assert "git ls-files" not in deploy
    assert "--untracked-files=all" in deploy
    assert "|| true" not in deploy
    assert "sha256sum --check --strict" in deploy
    assert "project bundle/source archive revision mismatch" in deploy
    digest_checks = [
        index
        for index in range(len(deploy))
        if deploy.startswith("sha256sum --check --strict", index)
    ]
    assert len(digest_checks) == 2
    source_extract = deploy.index(
        'tar --exclude=\\"_sim2claw_source/*\\" -xf '
        "/sandbox/inbox/sim2claw-source.tar"
    )
    assert all(index < source_extract for index in digest_checks)
    assert deploy.index("inspect-project-bundle.py") < deploy.index(
        "tar -xf /sandbox/inbox/sim2claw-project.tar"
    )
    assert "--exclude='_sim2claw_bundle/*'" in deploy
    assert "openshell service expose" in deploy
    assert "inspect_source_archive" in source_inspector

    assert "0.9.29" in bootstrap
    assert "curl" not in bootstrap
    assert "wget" not in bootstrap
    assert "uv sync --locked --no-dev" in bootstrap

    assert "/proc/$pid/exe" in studio
    assert "/proc/$pid/cmdline" in studio
    for required in (
        '"service": "sim2claw-studio"',
        '"read_only": True',
        '"mode": "read_only_evidence"',
        '"recorder_control": "disabled"',
        '"physical_authority": False',
    ):
        assert required in studio
        assert required in receipt_module
    assert "sim2claw.deployment_receipt" in verify
    assert "git rev-parse" not in verify
    assert "git status" not in verify

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nprintf 'uv 0.1.0\\n'\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["SIM2CLAW_REPO_ROOT"] = str(tmp_path)
    result = subprocess.run(
        ["bash", str(root / "scripts/nemoclaw/bootstrap.sh")],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "requires uv 0.9.29" in result.stderr


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SIM2CLAW_BREV_INSTANCE", "bad'quote"),
        ("SIM2CLAW_BREV_INSTANCE", 'bad"quote'),
        ("SIM2CLAW_BREV_INSTANCE", "bad;command"),
        ("SIM2CLAW_BREV_INSTANCE", "bad command"),
        ("SIM2CLAW_BREV_INSTANCE", "bad\ncommand"),
        ("SIM2CLAW_BREV_INSTANCE", "$(touch injected)"),
        ("SIM2CLAW_SANDBOX", "bad'quote"),
        ("SIM2CLAW_SANDBOX", 'bad"quote'),
        ("SIM2CLAW_SANDBOX", "bad;command"),
        ("SIM2CLAW_SANDBOX", "bad command"),
        ("SIM2CLAW_SANDBOX", "bad\ncommand"),
        ("SIM2CLAW_SANDBOX", "`touch injected`"),
    ],
)
def test_deploy_rejects_remote_identifier_injection(
    tmp_path: Path, variable: str, value: str
) -> None:
    root = Path(__file__).parents[1]
    deploy = (root / "scripts/nemoclaw/deploy.sh").read_text()
    validation_prefix = deploy[: deploy.index('cd "$REPO_ROOT"')]
    validation_script = validation_prefix + '\nprintf "%s\\n" "$REMOTE" "$SANDBOX"\n'
    env = os.environ.copy()
    env["SIM2CLAW_BREV_INSTANCE"] = "review-worker-02"
    env["SIM2CLAW_SANDBOX"] = "review-sandbox-02"
    sentinel = tmp_path / "injected"
    env[variable] = value.replace("injected", str(sentinel))
    result = subprocess.run(
        ["bash", "-c", validation_script, "deploy-identifier-validation"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert variable in result.stderr
    assert not sentinel.exists()


def test_deploy_accepts_non_default_narrow_remote_identifiers() -> None:
    root = Path(__file__).parents[1]
    deploy = (root / "scripts/nemoclaw/deploy.sh").read_text()
    validation_prefix = deploy[: deploy.index('cd "$REPO_ROOT"')]
    validation_script = validation_prefix + '\nprintf "%s\\n%s\\n" "$REMOTE" "$SANDBOX"\n'
    env = os.environ.copy()
    env["SIM2CLAW_BREV_INSTANCE"] = "review-worker-02"
    env["SIM2CLAW_SANDBOX"] = "review-sandbox-02"
    result = subprocess.run(
        ["bash", "-c", validation_script, "deploy-identifier-validation"],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["review-worker-02", "review-sandbox-02"]


def test_start_studio_rejects_live_foreign_pid(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = run ] && [ \"$2\" = python ]; then\n"
        "  shift 2\n"
        "  exec /usr/bin/python3 \"$@\"\n"
        "fi\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    run_root = tmp_path / "runs/nemoclaw/studio"
    run_root.mkdir(parents=True)
    foreign = subprocess.Popen(["sleep", "30"])
    try:
        (run_root / "studio.pid").write_text(f"{foreign.pid}\n", encoding="utf-8")
        env = os.environ.copy()
        env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
        env["SIM2CLAW_REPO_ROOT"] = str(tmp_path)
        result = subprocess.run(
            ["bash", str(root / "scripts/nemoclaw/start-studio.sh")],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "refusing stale or foreign Studio PID" in result.stderr
        assert foreign.poll() is None
    finally:
        foreign.terminate()
        foreign.wait(timeout=3)
