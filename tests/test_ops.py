"""Independent operations tests using temporary, hardware-free repositories."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from sim2claw.ops import core


def _write(root: Path, relative: str, content: str | bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def ops_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-q")
    _write(root, ".gitignore", "outputs/\nruns/\n")
    _write(root, "docs/session-logs/a.md", "# Executor\nStatus: PASS\nneedle alpha\n")
    _write(
        root,
        "configs/decisions/a.json",
        json.dumps(
            {
                "schema_version": "test.closeout.v1",
                "status": "PASS_TASK_NEGATIVE",
                "proof_class": "retrospective_diagnostic",
                "authority": {"physical_motion": False},
                "claim_limits": {"task_success": False},
            },
            indent=2,
        ),
    )
    _git(root, "add", ".gitignore", "docs", "configs")
    _write(root, "outputs/worker.log", "worker started\nneedle beta\n")
    _write(
        root,
        "outputs/receipt.json",
        json.dumps(
            {
                "status": "completed_command_cycle_unverified_task_outcome",
                "proof_class": "unqualified_command_replay",
            }
        ),
    )
    return root


def _sources(coverage: dict) -> dict[str, dict]:
    return {source["path"]: source for source in coverage["sources"]}


def test_scan_accounts_for_tracked_and_ignored_text_without_self_ingestion(ops_repo: Path) -> None:
    _write(ops_repo, "outputs/photo.png", b"media payload")
    _write(ops_repo, "outputs/operations-audit/prior.json", '{"marker":"selfreference"}')
    _write(ops_repo, "docs/operations/generated.md", "selfreference")
    coverage = core.scan(ops_repo)
    sources = _sources(coverage)

    assert coverage["total"] == coverage["indexed"] == 4
    assert coverage["skipped"] == 0
    assert sources["docs/session-logs/a.md"]["tracked"]
    assert not sources["outputs/worker.log"]["tracked"]
    assert coverage["excluded_nontext_by_suffix"][".png"] == 1
    assert sources["docs/session-logs/a.md"]["kind"] == "session"
    assert sources["configs/decisions/a.json"]["kind"] == "decision"
    assert sources["outputs/worker.log"]["kind"] == "runtime"
    assert core.search(ops_repo, "selfreference") == []
    assert coverage["discovery_errors"] == []


def test_incremental_scan_hashes_same_length_same_timestamp_edits(ops_repo: Path) -> None:
    first = core.scan(ops_repo)
    same = core.scan(ops_repo)
    assert same["changed"] == 0
    assert same["unchanged"] == first["total"]

    path = ops_repo / "docs/session-logs/a.md"
    original = path.stat()
    _write(ops_repo, "docs/session-logs/a.md", "# Executor\nStatus: PASS\nneedle omega\n")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    changed = core.scan(ops_repo)
    assert changed["changed"] == 1
    assert changed["unchanged"] == 3
    assert _sources(first)["docs/session-logs/a.md"]["sha256"] != _sources(changed)["docs/session-logs/a.md"]["sha256"]
    assert core.search(ops_repo, "alpha") == []
    assert core.search(ops_repo, "omega")[0]["freshness"] == "current"


def test_missing_tracked_and_ignored_sources_become_tombstones(ops_repo: Path) -> None:
    core.scan(ops_repo)
    (ops_repo / "docs/session-logs/a.md").unlink()
    (ops_repo / "outputs/worker.log").unlink()

    assert core.search(ops_repo, "alpha")[0]["freshness"] == "missing"
    coverage = core.scan(ops_repo)
    sources = _sources(coverage)
    assert coverage["counts"]["missing"] == 2
    assert sources["docs/session-logs/a.md"]["status"] == "missing"
    assert sources["docs/session-logs/a.md"]["tracked"]
    assert sources["outputs/worker.log"]["status"] == "missing"
    assert core.search(ops_repo, "needle") == []
    assert core.show(ops_repo, "docs/session-logs/a.md")["spans"] == []


def test_size_cap_removes_prior_spans_and_does_not_silently_truncate(ops_repo: Path) -> None:
    core.scan(ops_repo)
    _write(ops_repo, "outputs/worker.log", "oversizemarker\n" * 100)
    coverage = core.scan(ops_repo, max_bytes=400)
    source = _sources(coverage)["outputs/worker.log"]
    assert source["status"] == "skipped_oversize"
    assert source["sha256"] is None
    assert source["bytes"] > 400
    assert source["lines"] == 0
    assert core.search(ops_repo, "oversizemarker") == []
    assert core.search(ops_repo, "beta") == []
    assert core.show(ops_repo, "outputs/worker.log")["spans"] == []

    expanded = core.scan(ops_repo, max_bytes=2000)
    assert _sources(expanded)["outputs/worker.log"]["status"] == "indexed"
    assert core.search(ops_repo, "oversizemarker")


def test_symlinks_and_nested_repositories_are_disclosed_and_not_read(ops_repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.log"
    outside.write_text("outsidesecret", encoding="utf-8")
    (ops_repo / "outputs/link.log").symlink_to(outside)
    (ops_repo / "outputs/linked-directory").symlink_to(tmp_path, target_is_directory=True)
    nested = ops_repo / "outputs/nested"
    nested.mkdir()
    _git(nested, "init", "-q")
    _write(nested, "nested.log", "nestedsecret")

    coverage = core.scan(ops_repo)
    assert _sources(coverage)["outputs/link.log"]["status"] == "skipped_symlink"
    assert "outputs/linked-directory" in coverage["excluded_boundaries"]
    assert "outputs/nested (nested repository)" in coverage["excluded_boundaries"]
    assert core.search(ops_repo, "outsidesecret") == []
    assert core.search(ops_repo, "nestedsecret") == []
    with pytest.raises(ValueError, match="symlink"):
        core.show(ops_repo, "outputs/link.log")


def test_existing_source_entering_nested_repository_boundary_loses_search_spans(ops_repo: Path) -> None:
    relative = "outputs/later-nested/worker.log"
    source = _write(ops_repo, relative, "oldnestedmarker")
    core.scan(ops_repo)
    assert core.search(ops_repo, "oldnestedmarker")
    _git(source.parent, "init", "-q")
    source.write_text("newnestedmarker", encoding="utf-8")

    coverage = core.scan(ops_repo)
    record = _sources(coverage)[relative]
    assert record["status"] == "skipped_boundary"
    assert record["sha256"] is None
    assert record["lines"] == 0
    assert core.search(ops_repo, "oldnestedmarker") == []
    assert core.search(ops_repo, "newnestedmarker") == []


def test_invalid_utf8_and_nul_sources_are_explicitly_unreadable(ops_repo: Path) -> None:
    _write(ops_repo, "outputs/invalid.log", b"\xff\xfe")
    _write(ops_repo, "outputs/nul.log", b"nulmarker\x00binary")
    coverage = core.scan(ops_repo)
    assert coverage["counts"]["decode_error"] == 2
    assert _sources(coverage)["outputs/invalid.log"]["status"] == "decode_error"
    assert _sources(coverage)["outputs/nul.log"]["status"] == "decode_error"
    assert core.search(ops_repo, "nulmarker") == []


def test_malformed_json_retains_text_but_discloses_parse_failure(ops_repo: Path) -> None:
    _write(ops_repo, "outputs/malformed.json", '{"status": "PASS", brokenmarker')
    coverage = core.scan(ops_repo)
    source = _sources(coverage)["outputs/malformed.json"]
    assert source["status"] == "indexed"
    assert source["metadata"]["parse_error"]
    assert "declared_status" not in source["metadata"]
    assert core.search(ops_repo, "brokenmarker")[0]["freshness"] == "current"


@pytest.mark.parametrize("query", ["\"' OR 1=1; DROP TABLE sources; --", '"needle" NEAR(', "*", "😀", "needle'", "αβγ"])
def test_arbitrary_search_text_cannot_execute_sql_or_fts_operators(ops_repo: Path, query: str) -> None:
    core.scan(ops_repo)
    assert isinstance(core.search(ops_repo, query), list)
    assert len(core.search(ops_repo, "needle")) == 2
    assert len(core.search(ops_repo, "needle", kind="session")) == 1
    assert core.status(ops_repo)["coverage"]["total"] == 4


def test_retrieval_marks_source_drift_and_retains_exact_indexed_citation(ops_repo: Path) -> None:
    core.scan(ops_repo)
    original = core.search(ops_repo, "alpha")[0]
    assert original["line"] == 3
    assert original["text"] == "needle alpha"
    assert original["freshness"] == "current"

    _write(ops_repo, "docs/session-logs/a.md", "changed after scan\n")
    stale = core.search(ops_repo, "alpha")[0]
    assert stale["freshness"] == "stale"
    assert stale["sha256"] == original["sha256"]
    shown = core.show(ops_repo, "docs/session-logs/a.md", start=3, end=3)
    assert shown["freshness"] == "stale"
    assert shown["spans"] == [{"line": 3, "text": "needle alpha"}]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_search_passes_document_only_matches_and_hashes_each_cited_source_once(
    ops_repo: Path, monkeypatch: pytest.MonkeyPatch, limit: int,
) -> None:
    # Equal term counts give all three documents the same FTS rank. The first
    # candidate contains both terms but has no line eligible for a citation.
    _write(ops_repo, "docs/a.md", "matrixboundary\nclockneedle\nmatrixboundary\nclockneedle\n")
    content = "matrixboundary clockneedle\nmatrixboundary clockneedle\n"
    _write(ops_repo, "docs/b.md", content)
    _write(ops_repo, "docs/c.md", content)
    core.scan(ops_repo)
    checked = []
    freshness = core._freshness

    def observe(root: Path, path: str, sha256: str) -> str:
        checked.append(path)
        return freshness(root, path, sha256)

    monkeypatch.setattr(core, "_freshness", observe)
    results = core.search(ops_repo, "matrixboundary clockneedle", kind="document", limit=limit)
    expected = [("docs/b.md", 1), ("docs/b.md", 2), ("docs/c.md", 1)][:limit]
    assert [(item["path"], item["line"]) for item in results] == expected
    assert checked == (["docs/b.md"] if limit <= 2 else ["docs/b.md", "docs/c.md"])
    assert all(item["text"] == "matrixboundary clockneedle" for item in results)
    assert all(item["sha256"] == hashlib.sha256(content.encode()).hexdigest() for item in results)
    assert all(item["freshness"] == "current" for item in results)
    assert all(item["kind"] == "document" and item["metadata"] == {
        "claim_state": "source_reported_unverified",
    } for item in results)


def test_search_keeps_rank_before_path_and_filters_kind_before_limit(ops_repo: Path) -> None:
    _write(ops_repo, "docs/a.md", "ranksentinel " + "filler " * 100)
    _write(ops_repo, "docs/z.md", "ranksentinel")
    _write(ops_repo, "docs/session-logs/rank.md", "ranksentinel")
    core.scan(ops_repo)
    results = core.search(ops_repo, "ranksentinel", kind="document", limit=2)
    assert [item["path"] for item in results] == ["docs/z.md", "docs/a.md"]
    assert core.search(ops_repo, "ranksentinel", kind="document", limit=1) == results[:1]
    session = core.search(ops_repo, "ranksentinel", kind="session", limit=1)
    assert [item["path"] for item in session] == ["docs/session-logs/rank.md"]


def test_search_uses_one_index_snapshot_during_concurrent_refresh(
    ops_repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    core.scan(ops_repo)
    relative = "docs/session-logs/a.md"
    original = (ops_repo / relative).read_bytes()
    opened = core._db
    refreshed = []

    class InterleavedConnection:
        def __init__(self, db: sqlite3.Connection) -> None:
            self.db = db

        def execute(self, sql: str, parameters: tuple = ()):
            # Refresh after ranking its only candidate but before retrieving its
            # content. SQLite's implicit read transaction can end at this point.
            if sql.lstrip().startswith("SELECT path, content") and not refreshed:
                _write(ops_repo, relative, "rewritten after ranking")
                core.scan(ops_repo)
                refreshed.append(True)
            return self.db.execute(sql, parameters)

    @contextmanager
    def interleave(root: Path):
        with opened(root) as db:
            yield InterleavedConnection(db)

    # The concurrent scan uses the original database opener, not this wrapper.
    scan = core.scan

    def refresh(root: Path) -> dict:
        with monkeypatch.context() as scoped:
            scoped.setattr(core, "_db", opened)
            return scan(root)

    monkeypatch.setattr(core, "_db", interleave)
    monkeypatch.setattr(core, "scan", refresh)
    results = core.search(ops_repo, "alpha", kind="session")
    assert refreshed == [True]
    assert len(results) == 1
    assert (results[0]["line"], results[0]["text"]) == (3, "needle alpha")
    assert results[0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert results[0]["freshness"] == "stale"


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\u2028"])
def test_search_retains_word_boundaries_line_numbers_and_text_limit(ops_repo: Path, separator: str) -> None:
    long_line = "exactmarker λογος " + "x" * 2100
    _write(ops_repo, "docs/boundaries.md", separator.join([
        "exactmarker_suffix λογος", "EXACTMARKER ΛΟΓΟΣ", long_line,
    ]))
    core.scan(ops_repo)
    results = core.search(ops_repo, "exactmarker λογος", kind="document")
    assert [(item["line"], item["text"]) for item in results] == [
        (2, "EXACTMARKER ΛΟΓΟΣ"), (3, long_line[:2000]),
    ]


def test_reported_pass_is_not_promoted_to_task_or_physical_success(ops_repo: Path) -> None:
    coverage = core.scan(ops_repo)
    metadata = _sources(coverage)["configs/decisions/a.json"]["metadata"]
    assert metadata["declared_status"] == "PASS_TASK_NEGATIVE"
    assert metadata["proof_class"] == "retrospective_diagnostic"
    assert metadata["claim_limits"]["task_success"] is False
    assert metadata["authority"]["physical_motion"] is False
    assert metadata["claim_state"] == "source_reported_unverified"
    receipt = _sources(coverage)["outputs/receipt.json"]["metadata"]
    assert receipt["declared_status"] == "completed_command_cycle_unverified_task_outcome"
    assert receipt["proof_class"] == "unqualified_command_replay"
    assert receipt["claim_state"] == "source_reported_unverified"
    assert "task_success" not in receipt


def test_runtime_search_preserves_digit_leading_recording_and_hash_identifiers(ops_repo: Path) -> None:
    recording_id = "20260719T202758Z"
    digest = "37a0aa946a7b69bb3feda14f7e8111949f6f4ec9308194c27b4126215079a4a7"
    _write(
        ops_repo,
        "outputs/provenance.json",
        json.dumps({"recording_id": recording_id, "sha256": digest}, indent=2),
    )
    core.scan(ops_repo)
    for identifier in (recording_id, digest):
        matches = core.search(ops_repo, identifier)
        assert len(matches) == 1
        assert matches[0]["path"] == "outputs/provenance.json"
        assert matches[0]["freshness"] == "current"
        assert identifier in matches[0]["text"]


def test_numeric_runtime_arrays_remain_inspectable_with_disclosed_search_exclusion(ops_repo: Path) -> None:
    relative = "outputs/numeric-trace.json"
    _write(ops_repo, relative, json.dumps({"sample_count": 531, "samples": [0.0123, 0.0456]}, indent=2))
    _write(ops_repo, "docs/run-logs/numeric-summary.md", "Observed 531 samples\n")
    coverage = core.scan(ops_repo)
    assert "not raw numeric arrays" in coverage["search_semantics"]
    assert core.search(ops_repo, "531", kind="runtime") == []
    assert core.search(ops_repo, "531", kind="run_log")[0]["text"] == "Observed 531 samples"
    shown = core.show(ops_repo, relative)
    assert shown["freshness"] == "current"
    assert "531" in "\n".join(span["text"] for span in shown["spans"])


def _lesson_catalog(root: Path, *, line: int = 3, end_line: int = 3) -> None:
    source = root / "docs/session-logs/a.md"
    _write(
        root,
        "configs/operations/lessons.v1.json",
        json.dumps(
            {
                "lessons": [
                    {
                        "id": "no-self-promotion",
                        "sources": [
                            {
                                "path": "docs/session-logs/a.md",
                                "line": line,
                                "end_line": end_line,
                                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ]
            }
        ),
    )


def test_lesson_hash_drift_and_missing_sources_require_review(ops_repo: Path) -> None:
    _lesson_catalog(ops_repo)
    lesson = core.lessons(ops_repo)[0]
    assert lesson["evidence_state"] == "current"
    assert lesson["authority"] == "advisory_only"
    assert lesson["sources"][0]["excerpt"] == "needle alpha"

    _write(ops_repo, "docs/session-logs/a.md", "changed evidence")
    stale = core.lessons(ops_repo)[0]
    assert stale["evidence_state"] == "needs_review"
    assert stale["sources"][0]["freshness"] == "stale"
    assert stale["sources"][0]["excerpt"] == ""
    (ops_repo / "docs/session-logs/a.md").unlink()
    missing = core.lessons(ops_repo)[0]
    assert missing["sources"][0]["freshness"] == "missing"
    assert missing["evidence_state"] == "needs_review"


@pytest.mark.parametrize("line,end_line", [(0, 1), (4, 4), (3, 2)])
def test_out_of_range_lesson_citations_cannot_look_current(ops_repo: Path, line: int, end_line: int) -> None:
    _lesson_catalog(ops_repo, line=line, end_line=end_line)
    lesson = core.lessons(ops_repo)[0]
    assert lesson["evidence_state"] == "needs_review"
    assert lesson["sources"][0]["freshness"] == "invalid_span"
    assert lesson["sources"][0]["excerpt"] == ""


def test_empty_source_cannot_support_nonexistent_lesson_lines(ops_repo: Path) -> None:
    _write(ops_repo, "docs/session-logs/a.md", "")
    _lesson_catalog(ops_repo, line=1, end_line=9)
    lesson = core.lessons(ops_repo)[0]
    assert lesson["evidence_state"] == "needs_review"
    assert lesson["sources"][0]["freshness"] == "invalid_span"
    assert lesson["sources"][0]["excerpt"] == ""


def test_lesson_excerpt_uses_the_same_bytes_as_its_verified_hash(ops_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _lesson_catalog(ops_repo)
    source = ops_repo / "docs/session-logs/a.md"
    original_open = Path.open
    changed = False

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, *args):
            nonlocal changed
            content = self.stream.read(*args)
            if content and not changed:
                changed = True
                source.write_text("# Changed\nStatus: PASS\nnew unverified excerpt\n", encoding="utf-8")
            return content

    def open_with_replacement(path: Path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return MutatingReader(stream) if path == source and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", open_with_replacement)
    lesson = core.lessons(ops_repo)[0]
    assert changed, "The test must replace the source immediately after its bytes are read"
    citation = lesson["sources"][0]
    if lesson["evidence_state"] == "current":
        assert citation["excerpt"] == "needle alpha"
    else:
        assert lesson["evidence_state"] == "needs_review"
        assert citation["excerpt"] == ""


def test_metadata_poll_detects_same_size_same_mtime_change_without_claiming_hash_verification(ops_repo: Path) -> None:
    first = core.scan(ops_repo)
    assert core.poll(ops_repo)["changed"] is False
    source = ops_repo / "docs/session-logs/a.md"
    before = source.stat()
    source.write_text("# Executor\nStatus: PASS\nneedle omega\n", encoding="utf-8")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert source.stat().st_size == before.st_size
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert core.poll(ops_repo)["changed"] is True
    refreshed = core.scan(ops_repo)
    assert _sources(refreshed)["docs/session-logs/a.md"]["sha256"] != _sources(first)["docs/session-logs/a.md"]["sha256"]
    assert core.poll(ops_repo)["changed"] is False


def test_explicitly_expanded_size_cap_is_respected_by_read_time_freshness(ops_repo: Path) -> None:
    relative = "outputs/expanded-cap.log"
    source = _write(ops_repo, relative, "padding " * (core.MAX_BYTES // 8 + 1) + "\nlargeproofmarker\n")
    assert core.MAX_BYTES < source.stat().st_size < 5 * 1024 * 1024
    coverage = core.scan(ops_repo, max_bytes=5 * 1024 * 1024)
    assert _sources(coverage)[relative]["status"] == "indexed"
    shown = core.show(ops_repo, relative, start=2, end=2)
    assert shown["freshness"] == "current"
    assert shown["spans"] == [{"line": 2, "text": "largeproofmarker"}]
    found = core.search(ops_repo, "largeproofmarker")
    assert len(found) == 1
    assert found[0]["path"] == relative
    assert found[0]["freshness"] == "current"


def test_human_events_append_without_granting_authority_or_mutating_sources(ops_repo: Path) -> None:
    source = ops_repo / "configs/decisions/a.json"
    before = source.read_bytes()
    first = core.record_event(ops_repo, kind="note", message="  Review this failure  ")
    second = core.record_event(
        ops_repo,
        kind="decision",
        message="Approve a physical retry",
        subject="OR156",
    )
    assert first["message"] == "Review this failure"
    assert second["id"] > first["id"]
    assert second["authority"] == "annotation_only"
    assert [event["id"] for event in core.events(ops_repo)] == [second["id"], first["id"]]
    core.scan(ops_repo)
    assert source.read_bytes() == before
    state = core.snapshot(ops_repo)
    assert state["operations_authority"] == "inspect_and_annotate_only"
    assert state["authority"]["execution_admitted"] is False
    assert state["event_count"] == 2
    assert len(state["events"]) == 2


def test_brief_combines_bounded_source_context_without_promoting_human_notes(ops_repo: Path) -> None:
    core.scan(ops_repo)
    note = core.record_event(ops_repo, kind="decision", message="Approve a physical retry", subject="OR156")
    decision = ops_repo / "configs/decisions/a.json"
    before = decision.read_bytes()
    packet = core.brief(ops_repo, "needle", max_bytes=1024)
    actual_bytes = len(json.dumps(packet, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    assert packet["bytes"] == actual_bytes <= packet["max_bytes"] == 1024
    assert packet["authority"]["execution_admitted"] is False
    assert len(packet["sources"]) + packet["omitted_sources"] == 2
    assert all(source["freshness"] == "current" and source["sha256"] for source in packet["sources"])
    assert core.events(ops_repo) == [note]
    assert decision.read_bytes() == before


def test_cache_cannot_be_reused_under_a_different_repository_root(ops_repo: Path, tmp_path: Path) -> None:
    core.scan(ops_repo)
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    destination = other / "outputs/operations/index.sqlite"
    destination.parent.mkdir(parents=True)
    with sqlite3.connect(ops_repo / "outputs/operations/index.sqlite") as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    with pytest.raises(ValueError, match="different repository"):
        core.search(other, "needle")
    assert len(core.search(ops_repo, "needle")) == 2


def test_independent_repositories_do_not_share_events_or_search_results(ops_repo: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q")
    _write(other, "outputs/worker.log", "othermarker")
    core.scan(ops_repo)
    core.scan(other)
    core.record_event(ops_repo, kind="note", message="local note")
    assert core.search(other, "needle") == []
    assert core.search(ops_repo, "othermarker") == []
    assert core.events(other) == []


@pytest.mark.parametrize("path", ["../outside.log", "/etc/passwd", "docs/../configs/decisions/a.json"])
def test_source_inspection_rejects_paths_outside_discovered_scope(ops_repo: Path, path: str) -> None:
    core.scan(ops_repo)
    with pytest.raises(ValueError, match="repository-relative"):
        core.show(ops_repo, path)


def test_cache_location_cannot_follow_a_symlink(ops_repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (ops_repo / "outputs/operations").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        core.scan(ops_repo)
    assert list(outside.iterdir()) == []


def test_architecture_reports_missing_components_without_inventing_them(ops_repo: Path) -> None:
    _write(
        ops_repo,
        "configs/operations/architecture.v1.json",
        json.dumps(
            {
                "nodes": [
                    {"id": "logs", "paths": ["docs/session-logs/a.md"]},
                    {"id": "future", "paths": ["src/future.py"]},
                ],
                "edges": [{"from": "logs", "to": "future"}],
            }
        ),
    )
    architecture = core.architecture(ops_repo)
    assert architecture["authority"] == "descriptive_and_proposed_only"
    assert architecture["nodes"][0]["path_state"][0]["exists"]
    assert not architecture["nodes"][1]["path_state"][0]["exists"]
    assert not (ops_repo / "src/future.py").exists()


def test_deleted_cache_can_be_rebuilt_to_the_same_source_index(ops_repo: Path) -> None:
    first = core.scan(ops_repo)
    shutil.rmtree(ops_repo / "outputs/operations")
    rebuilt = core.scan(ops_repo)
    assert rebuilt["sources"] == first["sources"]
    assert len(core.search(ops_repo, "needle")) == 2


def test_deleting_derived_index_preserves_human_notes(ops_repo: Path) -> None:
    core.scan(ops_repo)
    note = core.record_event(ops_repo, kind="feedback", message="Preserve this human intent")
    directory = ops_repo / "outputs/operations"
    for path in directory.glob("index.sqlite*"):
        path.unlink()

    assert (directory / "journal.sqlite").exists()
    assert core.events(ops_repo) == [note]
    assert core.status(ops_repo)["coverage"]["status"] == "not_indexed"
    core.scan(ops_repo)
    assert core.events(ops_repo) == [note]
    assert core.status(ops_repo)["event_count"] == 1


def test_concurrent_journal_appenders_preserve_every_note_with_unique_order(ops_repo: Path) -> None:
    def append(number: int) -> dict:
        return core.record_event(ops_repo, kind="note", message=f"concurrent note {number}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        written = list(pool.map(append, range(18)))
    observed = core.events(ops_repo)
    assert len(observed) == len(written) == 18
    assert {event["message"] for event in observed} == {event["message"] for event in written}
    assert [event["id"] for event in observed] == list(range(18, 0, -1))
    assert all(event["authority"] == "annotation_only" for event in observed)


def test_legacy_index_notes_migrate_once_without_duplicating_or_mutating_history(ops_repo: Path) -> None:
    core.scan(ops_repo)
    legacy_path = ops_repo / "outputs/operations/index.sqlite"
    legacy = (7, "2026-09-05T00:00:00+00:00", "note", "legacy intent", "OR156")
    with sqlite3.connect(legacy_path) as db:
        db.execute("INSERT INTO events(id,at,kind,message,subject) VALUES (?,?,?,?,?)", legacy)

    first = core.events(ops_repo)
    assert first == [{"id": 7, "at": legacy[1], "kind": "note", "message": "legacy intent", "subject": "OR156", "authority": "annotation_only"}]
    assert core.events(ops_repo) == first
    next_note = core.record_event(ops_repo, kind="note", message="new intent")
    assert next_note["id"] == 8
    assert len(core.events(ops_repo)) == 2
    with sqlite3.connect(legacy_path) as db:
        assert db.execute("SELECT * FROM events").fetchall() == [legacy]


def test_journal_rejects_foreign_root_and_symlink_destinations(ops_repo: Path, tmp_path: Path) -> None:
    core.record_event(ops_repo, kind="note", message="original repository")
    other = tmp_path / "other-journal-root"
    other.mkdir()
    destination = other / "outputs/operations/journal.sqlite"
    destination.parent.mkdir(parents=True)
    shutil.copy2(ops_repo / "outputs/operations/journal.sqlite", destination)
    with pytest.raises(ValueError, match="different repository"):
        core.events(other)
    destination.unlink()
    destination.symlink_to(ops_repo / "outputs/operations/journal.sqlite")
    with pytest.raises(ValueError, match="symlink"):
        core.record_event(other, kind="note", message="foreign write")
    assert len(core.events(ops_repo)) == 1
