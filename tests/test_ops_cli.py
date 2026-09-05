"""CLI and portable-view boundaries using temporary software-only repositories."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from sim2claw.ops import cli, core
from sim2claw.ops.view import render_report


@pytest.fixture
def cli_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / ".gitignore").write_text("outputs/\n", encoding="utf-8")
    (root / "docs/session-logs").mkdir(parents=True)
    (root / "docs/session-logs/attempt.md").write_text(
        "# Software attempt\nA duplicate process failed.\nneedle evidence\n", encoding="utf-8"
    )
    core.scan(root)
    return root


@pytest.mark.parametrize("command", [
    ["index"], ["status"], ["search", "duplicate"],
    ["show", "docs/session-logs/attempt.md", "--start", "2", "--end", "2"],
    ["lessons"], ["map"], ["note", "Consider the failure", "--kind", "feedback", "--subject", "software"],
    ["events"], ["brief", "duplicate"], ["report"],
])
def test_commands_emit_valid_json(cli_repo: Path, capsys: pytest.CaptureFixture[str], command: list[str]) -> None:
    assert cli.main(["--root", str(cli_repo), "--json", *command]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert isinstance(result, (dict, list))
    assert captured.err == ""
    if command[0] == "show":
        assert result["spans"] == [{"line": 2, "text": "A duplicate process failed."}]
    if command[0] == "note":
        assert result["kind"] == "feedback"
        assert result["authority"] == "annotation_only"
    if command[0] == "report":
        output = Path(result["path"])
        assert output == cli_repo / "outputs/operations/report.html"
        assert output.is_file()


@pytest.mark.parametrize("surface", ["module", "main"])
def test_module_and_main_cli_do_not_import_simulator_for_operations(cli_repo: Path, surface: str) -> None:
    script = """
import json, runpy, sys
root, surface = sys.argv[1:]
if surface == 'module':
    sys.argv = ['sim2claw.ops', '--root', root, '--json', 'status']
    try:
        runpy.run_module('sim2claw.ops', run_name='__main__')
    except SystemExit as error:
        assert error.code == 0
else:
    from sim2claw.cli import main
    assert main(['ops', '--root', root, '--json', 'status']) == 0
assert 'mujoco' not in sys.modules
assert 'numpy' not in sys.modules
assert 'torch' not in sys.modules
print(json.dumps({'imports': 'lightweight'}))
"""
    result = subprocess.run([sys.executable, "-c", script, str(cli_repo), surface], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {"imports": "lightweight"}


@pytest.mark.parametrize("destination", ["docs/overwrite.html", "outputs/operations/../outside.html", "outputs/operations/report.json", "/tmp/unscoped-operations-report.html"])
def test_report_output_is_confined_to_ignored_operations_html(cli_repo: Path, capsys: pytest.CaptureFixture[str], destination: str) -> None:
    source = cli_repo / "docs/session-logs/attempt.md"
    original = source.read_bytes()
    assert cli.main(["--root", str(cli_repo), "--json", "report", "--output", destination]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert source.read_bytes() == original
    assert not (cli_repo / "docs/overwrite.html").exists()
    assert not (cli_repo / "outputs/outside.html").exists()


def test_report_refuses_tracked_or_symlinked_destination(cli_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = cli_repo / "outputs/operations/tracked.html"
    target.write_text("preserve", encoding="utf-8")
    subprocess.run(["git", "-C", str(cli_repo), "add", "-f", "outputs/operations/tracked.html"], check=True)
    assert cli.main(["--root", str(cli_repo), "--json", "report", "--output", "outputs/operations/tracked.html"]) == 1
    assert target.read_text() == "preserve"
    outside = tmp_path / "outside"
    outside.mkdir()
    (cli_repo / "outputs/operations/link").symlink_to(outside, target_is_directory=True)
    assert cli.main(["--root", str(cli_repo), "--json", "report", "--output", "outputs/operations/link/report.html"]) == 1
    assert list(outside.iterdir()) == []
    capsys.readouterr()


def test_terminal_source_controls_are_escaped(cli_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = cli_repo / "docs/session-logs/attempt.md"
    source.write_text("needle \x1b]52;c;ZXZpbA==\x07\n\u202ehidden direction\n", encoding="utf-8")
    core.scan(cli_repo)
    assert cli.main(["--root", str(cli_repo), "show", "docs/session-logs/attempt.md"]) == 0
    output = capsys.readouterr().out
    assert "\x1b" not in output and "\x07" not in output and "\u202e" not in output
    assert "\\u001b" in output and "\\u0007" in output and "\\u202e" in output


def test_watch_count_is_bounded_and_json_refresh_omits_source_dump(cli_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)
    assert cli.main(["--root", str(cli_repo), "--json", "watch", "--count", "3", "--interval", "1"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 3
    assert sleeps == [1.0, 1.0]
    assert all("sources" not in row["refresh"] for row in rows)
    assert all(row["status"]["authority"]["execution_admitted"] is False for row in rows)


def test_watch_does_not_rehash_sources_when_poll_is_unchanged(cli_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_scan(*args: object, **kwargs: object) -> None:
        pytest.fail("unchanged watch must not scan source contents")

    monkeypatch.setattr(core, "scan", unexpected_scan)
    monkeypatch.setattr(core, "poll", lambda root: {"changed": False, "signature": "same", "observed_at": "2026-09-05T00:00:00Z"})
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    assert cli.main(["--root", str(cli_repo), "--json", "watch", "--count", "2"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 2
    assert all(row["refresh"]["status"] == "unchanged" for row in rows)


def test_watch_refreshes_after_a_real_source_change(cli_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    scan_calls: list[Path] = []
    scan = core.scan

    def observed_scan(root: Path, **kwargs: object) -> dict:
        scan_calls.append(root)
        return scan(root, **kwargs)

    def change_source(_: float) -> None:
        (cli_repo / "docs/session-logs/attempt.md").write_text("Changed evidence with newmarker\n", encoding="utf-8")

    monkeypatch.setattr(core, "scan", observed_scan)
    monkeypatch.setattr(cli.time, "sleep", change_source)
    assert cli.main(["--root", str(cli_repo), "--json", "watch", "--count", "2"]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [row["refresh"]["status"] for row in rows] == ["unchanged", "refreshed"]
    assert scan_calls == [cli_repo]
    assert core.search(cli_repo, "newmarker")[0]["freshness"] == "current"


@pytest.mark.parametrize("args", [["--count", "0"], ["--interval", "0"], ["--interval", "nan"], ["--interval", "inf"]])
def test_watch_rejects_invalid_bounds(cli_repo: Path, args: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["--root", str(cli_repo), "watch", *args])
    assert error.value.code == 2


def test_brief_reports_actual_emitted_json_bytes_for_unicode(cli_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--root", str(cli_repo), "--json", "brief", "needle 数据\u202e", "--max-bytes", "2048"]) == 0
    encoded = capsys.readouterr().out.rstrip("\n").encode("utf-8")
    packet = json.loads(encoded)
    assert packet["bytes"] == len(encoded)
    assert len(encoded) <= packet["max_bytes"] == 2048
    assert packet["authority"]["execution_admitted"] is False


def test_report_embedded_hostile_text_stays_data_and_is_offline() -> None:
    hostile = '</script><img src="https://example.invalid" onerror="alert(1)"> & \u202e'
    payload = {"observed_at": "2026-09-05T00:00:00Z", "sources": [{"path": hostile, "excerpt": hostile}], "events": [{"message": hostile}]}
    html = render_report(payload)
    prefix = '<script type="application/json" id="snapshot-data">'
    embedded = html.split(prefix, 1)[1].split("</script>", 1)[0]
    decoded = json.loads(embedded)
    assert decoded["sources"][0]["excerpt"] == hostile
    assert decoded["events"][0]["message"] == hostile
    assert "<img" not in html
    assert html.count("<script") == 2
    assert "innerHTML" not in html and "eval(" not in html and "fetch(" not in html
    assert "connect-src 'none'" in html
    assert "It does not update while agents run." in html
    assert 'id="source-list"' in html and 'id="node-detail"' in html
    assert "runtime JSON indexes narrative words, not raw numeric arrays" in html


def test_lesson_navigation_preserves_exact_citation_span_in_report() -> None:
    citation = {"path": "docs/session-logs/attempt.md", "line": 47, "end_line": 51,
                "excerpt": "The actual cited evidence", "sha256": "b" * 64, "freshness": "current"}
    html = render_report({
        "sources": [{"path": citation["path"], "excerpt": "Different opening excerpt"}],
        "lessons": [{"title": "Evidence lesson", "sources": [citation]}],
    })
    embedded = html.split('<script type="application/json" id="snapshot-data">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded)["lessons"][0]["sources"][0] == citation
    assert "function selectSource(path, citation=null)" in html
    assert "selectSource(source.path, source)" in html
    assert 'citation.excerpt||"The cited excerpt is unavailable' in html
    assert '" --start "+firstLine+" --end "+lastLine' in html
    assert "Number(citation.end_line)||firstLine" in html
    assert "citation?citation.sha256:source.sha256" in html
