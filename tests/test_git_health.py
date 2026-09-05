"""Prospective Git payload checks against disposable repositories only."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import pytest

from sim2claw.ops import cli, git_health


def git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], input=input_data,
                            capture_output=True, check=True)
    return result.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Metadata Test")
    git(root, "config", "user.email", "metadata@example.invalid")
    return root


def stage(root: Path, name: str, data: bytes) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    git(root, "add", "--", name)


def commit(root: Path) -> None:
    git(root, "commit", "-q", "-m", "fixture")


def test_unborn_empty_repository_is_valid_and_non_authorizing(repo: Path) -> None:
    result = git_health.inspect_git(repo)
    assert result["head_commit"] is None
    assert result["branch"] == "main"
    assert result["upstream"] is result["ahead"] is result["behind"] is None
    assert result["head"]["files"] == result["index"]["files"] == 0
    assert result["staged_unique_byte_delta"] == result["added_unique_blob_bytes"] == 0
    assert result["snapshot_consistent"] and not result["review_required"]
    assert result["advisory_only"] and result["execution_authorized"] is False


def test_unique_byte_growth_deduplicates_copies_and_keeps_logical_cost(repo: Path) -> None:
    stage(repo, "one.pt", b"same payload")
    stage(repo, "copy.pt", b"same payload")
    result = git_health.inspect_git(repo, max_added_bytes=11, max_blob_bytes=100)
    assert result["index"]["files"] == 2
    assert result["index"]["logical_bytes"] == 24
    assert result["index"]["unique_blob_bytes"] == 12
    assert result["added_unique_blobs"] == 1
    assert result["added_unique_blob_bytes"] == 12
    assert result["reasons"] == ["added_unique_blob_bytes_exceed_budget"]
    blob = result["largest_new_blobs"][0]
    assert set(blob["paths"]) == {"one.pt", "copy.pt"}
    assert blob["path_count"] == 2


def test_large_existing_receipt_is_grandfathered_and_index_is_unchanged(repo: Path) -> None:
    stage(repo, "receipts/immutable.pt", b"preserved evidence" * 20)
    commit(repo)
    index = (repo / ".git/index").read_bytes()
    head = git(repo, "rev-parse", "HEAD")
    result = git_health.inspect_git(repo, max_added_bytes=1, max_blob_bytes=1)
    assert not result["review_required"]
    assert result["largest_new_blobs"] == []
    assert result["head"] == result["index"]
    assert (repo / ".git/index").read_bytes() == index
    assert git(repo, "rev-parse", "HEAD") == head


def test_changed_blob_reports_added_and_removed_even_when_net_shrinks(repo: Path) -> None:
    stage(repo, "policy.pt", b"A" * 200)
    commit(repo)
    stage(repo, "policy.pt", b"B" * 120)
    result = git_health.inspect_git(repo, max_added_bytes=100, max_blob_bytes=110)
    assert result["staged_unique_byte_delta"] == -80
    assert result["added_unique_blob_bytes"] == 120
    assert result["removed_unique_blob_bytes"] == 200
    assert result["review_required"]
    assert set(result["reasons"]) == {"added_unique_blob_bytes_exceed_budget", "new_blob_exceeds_budget"}


def test_deletion_and_identical_rename_do_not_create_payload_growth(repo: Path) -> None:
    stage(repo, "delete.txt", b"delete")
    stage(repo, "old.txt", b"rename")
    commit(repo)
    git(repo, "rm", "delete.txt")
    git(repo, "mv", "old.txt", "new.txt")
    result = git_health.inspect_git(repo, max_added_bytes=0, max_blob_bytes=0)
    assert result["staged_unique_byte_delta"] == -6
    assert result["added_unique_blob_bytes"] == 0
    assert result["largest_new_blobs"] == []
    assert not result["review_required"]


def test_existing_duplicate_path_addition_is_logical_growth_only(repo: Path) -> None:
    stage(repo, "original", b"known")
    commit(repo)
    stage(repo, "copy", b"known")
    result = git_health.inspect_git(repo, max_added_bytes=0, max_blob_bytes=0)
    assert result["index"]["logical_bytes"] - result["head"]["logical_bytes"] == 5
    assert result["staged_unique_byte_delta"] == result["added_unique_blob_bytes"] == 0
    assert not result["review_required"]


def test_only_staged_bytes_count_with_dirty_and_untracked_paths(repo: Path) -> None:
    stage(repo, "tracked", b"old")
    commit(repo)
    stage(repo, "tracked", b"staged")
    (repo / "tracked").write_bytes(b"unstaged payload" * 100)
    (repo / "untracked.pt").write_bytes(b"untracked" * 100)
    (repo / "untracked-directory").mkdir()
    (repo / "untracked-directory/one").write_bytes(b"one")
    (repo / "untracked-directory/two").write_bytes(b"two")
    result = git_health.inspect_git(repo)
    assert result["index"]["logical_bytes"] == 6
    assert result["added_unique_blob_bytes"] == 6
    assert result["dirty_counts"] == {"staged": 1, "unstaged": 1, "untracked": 2, "unmerged": 0}


def test_unusual_paths_are_exact_and_never_shell_interpreted(repo: Path) -> None:
    names = ["space name", "line\nbreak", "tab\tname", "--help", "$(touch PWNED)", "quote'\"name"]
    for name in names:
        stage(repo, name, name.encode())
    result = git_health.inspect_git(repo)
    assert {path for item in result["largest_new_blobs"] for path in item["paths"]} == set(names)
    assert not (repo / "PWNED").exists()
    assert result["dirty_counts"]["staged"] == len(names)


def test_symlink_blob_counts_link_text_without_following_target(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(b"private payload" * 100)
    (repo / "link").symlink_to(outside)
    git(repo, "add", "link")
    result = git_health.inspect_git(repo)
    assert result["added_unique_blob_bytes"] == len(os.fsencode(outside))
    assert result["largest_new_blobs"][0]["paths"] == ["link"]


def test_gitlink_can_reference_missing_commit_without_recursing(repo: Path) -> None:
    git(repo, "update-index", "--add", "--cacheinfo", "160000," + "f" * 40 + ",foreign-submodule")
    result = git_health.inspect_git(repo)
    assert result["index"]["submodules"] == 1
    assert result["index"]["files"] == result["added_unique_blob_bytes"] == 0
    commit(repo)
    assert git_health.inspect_git(repo)["head"]["submodules"] == 1


def test_detached_head_and_missing_upstream_are_supported(repo: Path) -> None:
    stage(repo, "file", b"one")
    commit(repo)
    git(repo, "checkout", "--detach", "-q")
    result = git_health.inspect_git(repo)
    assert result["branch"] is None and result["head_commit"]
    assert result["upstream"] is result["ahead"] is result["behind"] is None


def test_ahead_and_behind_are_relative_to_configured_local_upstream(repo: Path) -> None:
    stage(repo, "base", b"base")
    commit(repo)
    git(repo, "branch", "upstream")
    git(repo, "branch", "--set-upstream-to=upstream", "main")
    stage(repo, "local", b"local")
    commit(repo)
    result = git_health.inspect_git(repo)
    assert (result["ahead"], result["behind"], result["upstream"]) == (1, 0, "upstream")
    git(repo, "checkout", "-q", "upstream")
    stage(repo, "peer", b"peer")
    commit(repo)
    git(repo, "checkout", "-q", "main")
    result = git_health.inspect_git(repo)
    assert (result["ahead"], result["behind"]) == (1, 1)


def test_unmerged_index_is_explicitly_incomplete(repo: Path) -> None:
    stage(repo, "conflict", b"base\n")
    commit(repo)
    git(repo, "branch", "other")
    stage(repo, "conflict", b"main\n")
    commit(repo)
    git(repo, "checkout", "-q", "other")
    stage(repo, "conflict", b"other\n")
    commit(repo)
    subprocess.run(["git", "-C", str(repo), "merge", "main"], capture_output=True, check=False)
    result = git_health.inspect_git(repo)
    assert result["dirty_counts"]["unmerged"] == 1
    assert result["index"]["files"] == 0
    assert "unmerged_index_has_no_complete_commit_payload" in result["reasons"]
    assert result["review_required"]


def test_root_isolation_even_with_inherited_git_environment(repo: Path, tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    git(foreign, "init", "-q")
    stage(foreign, "foreign", b"foreign payload")
    stage(repo, "local", b"local")
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(foreign / ".git/index"))
    child = repo / "subdir"
    child.mkdir()
    result = git_health.inspect_git(child)
    assert result["root"] == str(repo)
    assert result["index"]["logical_bytes"] == 5
    assert result["largest_new_blobs"][0]["paths"] == ["local"]


def test_report_limits_keep_aggregate_totals_complete(repo: Path) -> None:
    for i in range(25):
        stage(repo, f"unique-{i}", bytes([i]) * (i + 1))
    for i in range(10):
        stage(repo, f"duplicate-{i}", b"Z" * 100)
    result = git_health.inspect_git(repo)
    assert result["added_unique_blobs"] == 26
    assert result["added_unique_blob_bytes"] == sum(range(1, 26)) + 100
    assert len(result["largest_new_blobs"]) == 20
    assert result["largest_new_blobs_truncated"]
    largest = result["largest_new_blobs"][0]
    assert largest["path_count"] == 10 and len(largest["paths"]) == 5


def test_thresholds_are_strictly_greater_than_budget(repo: Path) -> None:
    stage(repo, "file", b"12345")
    assert not git_health.inspect_git(repo, 5, 5)["review_required"]
    assert git_health.inspect_git(repo, 5, 4)["reasons"] == ["new_blob_exceeds_budget"]


@pytest.mark.parametrize("value", [-1, True, 1.5, "12", None])
def test_invalid_thresholds_rejected(repo: Path, value: object) -> None:
    with pytest.raises(ValueError, match="nonnegative integer"):
        git_health.inspect_git(repo, max_added_bytes=value)
    with pytest.raises(ValueError, match="nonnegative integer"):
        git_health.inspect_git(repo, max_blob_bytes=value)


def test_metadata_limit_fails_explicitly_without_partial_result(repo: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    stage(repo, "file", b"one")
    monkeypatch.setattr(git_health, "MAX_METADATA_BYTES", 2)
    with pytest.raises(ValueError, match="inspection limit"):
        git_health.inspect_git(repo)


def test_entry_limit_fails_explicitly(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage(repo, "one", b"one")
    stage(repo, "two", b"two")
    monkeypatch.setattr(git_health, "MAX_ENTRIES", 1)
    with pytest.raises(ValueError, match="entry inspection limit"):
        git_health.inspect_git(repo)


def test_index_changes_during_read_require_review(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage(repo, "file", b"one")
    original = git_health._git
    changed = False

    def changing(root: Path, *args: str, **kwargs: object) -> bytes | None:
        nonlocal changed
        result = original(root, *args, **kwargs)
        if args[0] == "status" and not changed:
            stage(repo, "new", b"new")
            changed = True
        return result

    monkeypatch.setattr(git_health, "_git", changing)
    result = git_health.inspect_git(repo)
    assert changed and not result["snapshot_consistent"]
    assert result["reasons"] == ["head_or_index_changed_during_inspection"]


def test_non_repository_returns_clean_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Git metadata inspection failed"):
        git_health.inspect_git(tmp_path)


def test_status_never_invokes_configured_clean_or_process_filters(repo: Path) -> None:
    git(repo, "config", "filter.custom.clean", "touch FILTER_EXECUTED; cat")
    stage(repo, ".gitattributes", b"*.dat filter=custom\n")
    stage(repo, "payload.dat", b"payload\n")
    (repo / "FILTER_EXECUTED").unlink()
    # Force status to compare the touched worktree file against the index.
    (repo / "payload.dat").write_bytes(b"payload\n")
    result = git_health.inspect_git(repo)
    assert not (repo / "FILTER_EXECUTED").exists()
    assert result["snapshot_consistent"]
    git(repo, "config", "filter.custom.process", "touch PROCESS_EXECUTED; false")
    git(repo, "config", "filter.custom.required", "true")
    (repo / "payload.dat").write_bytes(b"changed payload\n")
    result = git_health.inspect_git(repo)
    assert not (repo / "PROCESS_EXECUTED").exists()
    assert not (repo / "FILTER_EXECUTED").exists()
    assert result["dirty_counts"]["unstaged"] == 1


def test_cli_json_advisory_succeeds_while_check_returns_review_exit(repo: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    stage(repo, "receipt.pt", b"retained evidence")
    args = ["--root", str(repo), "--json", "git-health", "--max-added-mib", "0", "--max-blob-mib", "0"]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["review_required"] and result["execution_authorized"] is False
    assert result["root"] == str(repo)
    assert cli.main([*args, "--check"]) == 1
    assert json.loads(capsys.readouterr().out)["review_required"]
    assert git(repo, "ls-files").decode().strip() == "receipt.pt"


def test_cli_check_zero_when_no_new_payload_and_human_paths_are_escaped(repo: Path,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    stage(repo, "line\nbreak\x1bname", b"one")
    assert cli.main(["--root", str(repo), "git-health", "--check"]) == 0
    output = capsys.readouterr().out
    assert "Artifact review required: False" in output
    assert "line\\nbreak" in output and "\x1b" not in output
    commit(repo)
    assert cli.main(["--root", str(repo), "--json", "git-health", "--check", "--max-added-mib", "0", "--max-blob-mib", "0"]) == 0
    assert not json.loads(capsys.readouterr().out)["review_required"]


@pytest.mark.parametrize("option", ["--max-added-mib", "--max-blob-mib"])
@pytest.mark.parametrize("value", ["nan", "inf", "-1", "1e308"])
def test_cli_rejects_invalid_or_overflow_thresholds(repo: Path, option: str, value: str) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--root", str(repo), "git-health", option, value])
    assert exc.value.code == 2
