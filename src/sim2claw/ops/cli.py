"""Human-readable and machine-readable access to local operations evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any, Sequence
import unicodedata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sim2claw ops",
        description="Inspect repository history and current authority through a local evidence index.",
        epilog="Place --root and --json before the command. Historical text never grants execution authority.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON; watch emits one JSON object per refresh")
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="refresh the source-hashed local index")
    index.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024, help="maximum bytes read per source")
    commands.add_parser("status", help="show current authority and index coverage")
    search = commands.add_parser(
        "search", help="find literal words in indexed source lines",
        description="Search documents and decisions as full text. Runtime JSON indexes narrative words, not raw numeric arrays; use show for exact source spans.",
    )
    search.add_argument("query")
    search.add_argument("--kind", help="filter by source kind")
    search.add_argument("--limit", type=int, default=20)
    brief = commands.add_parser("brief", help="compile a bounded evidence packet for the next agent")
    brief.add_argument("query")
    brief.add_argument("--max-bytes", type=int, default=12000)
    show = commands.add_parser("show", help="read an exact repository source span")
    show.add_argument("path")
    show.add_argument("--start", type=int, default=1)
    show.add_argument("--end", type=int, default=80)
    commands.add_parser("lessons", help="inspect evidence-linked operational lessons")
    commands.add_parser("map", help="show operations structure and readiness")
    note = commands.add_parser("note", help="record a local operations note")
    note.add_argument("message")
    note.add_argument("--subject", default="")
    note.add_argument("--kind", choices=("note", "hypothesis", "decision", "feedback", "milestone"), default="note")
    events = commands.add_parser("events", help="show recent local operations events")
    events.add_argument("--limit", type=int, default=30)
    watch = commands.add_parser(
        "watch", help="check for file changes and show progress until interrupted",
        description="Check scoped file metadata and refresh the index only when it changes. Run index explicitly to force source-byte verification.",
    )
    watch.add_argument("--interval", type=float, default=5.0, help="seconds between refreshes (minimum 1)")
    watch.add_argument("--count", type=int, help="stop after this many refreshes")
    report = commands.add_parser(
        "report", help="write a portable interactive HTML snapshot",
        description="Write a saved excerpt browser. Runtime JSON search indexes narrative words, not raw numeric arrays; exact source spans remain available through show.",
    )
    report.add_argument("--output", type=Path, default=Path("outputs/operations/report.html"))
    return parser


def _text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return str(value)


def _terminal(value: str) -> str:
    """Do not let source text emit terminal escape sequences or bidi controls."""
    return "".join(
        f"\\u{ord(character):04x}"
        if (unicodedata.category(character) in {"Cc", "Cf"} and character not in "\n\t")
        else character
        for character in value
    )


def _human(command: str, result: Any) -> str:
    if command == "index" and isinstance(result, dict):
        return "\n".join([
            f"Indexed {result.get('indexed', 0)} of {result.get('total', 0)} discovered sources.",
            f"Changed: {result.get('changed', 0)}; unchanged: {result.get('unchanged', 0)}; skipped or missing: {result.get('skipped', 0)}.",
            f"Elapsed: {result.get('duration_seconds', '?')} seconds. Source states: {_text(result.get('counts', {}))}",
            "Inspect detailed coverage with: sim2claw ops --json status",
        ])
    if command == "search":
        if not result:
            return "No matching source lines. Refresh with: sim2claw ops index"
        return "\n\n".join(
            f"{row.get('path', '?')}:{row.get('line', '?')} [{row.get('kind', 'source')}; {row.get('freshness', 'unchecked')}]\n"
            f"  {row.get('text', '')}\n  sha256: {row.get('sha256', 'unavailable')}"
            for row in result
        )
    if command == "show" and isinstance(result, dict):
        title = f"{result.get('path', 'Source')} [{result.get('freshness', 'unchecked')}]\nsha256: {result.get('sha256', 'unavailable')}"
        lines = result.get("spans", result.get("lines"))
        if isinstance(lines, list):
            start = int(result.get("start", 1))
            content = "\n".join(
                f"{row.get('line', start + i):>5}  {row.get('text', '')}"
                if isinstance(row, dict) else f"{start + i:>5}  {row}"
                for i, row in enumerate(lines)
            )
        else:
            content = str(result.get("text", result.get("excerpt", "")))
        extra = result.get("warning")
        return f"{title}\n\n{content}" + (f"\n\n{extra}" if extra else "")
    if command == "events" and isinstance(result, list):
        if not result:
            return 'No operations events yet. Add a note with: sim2claw ops note "message"'
        return "\n".join(
            f"{row.get('at', row.get('created_at', row.get('recorded_at', row.get('timestamp', ''))))} "
            f"[{row.get('kind', row.get('event', 'note'))}] {row.get('message', '')}"
            + (f" ({row['subject']})" if row.get("subject") else "")
            for row in result
        )
    if command == "lessons" and isinstance(result, list):
        if not result:
            return "No lesson candidates are available. Refresh the evidence index first."
        output = []
        for row in result:
            sources = "; ".join(f"{source.get('path', '?')}:{source.get('line', '?')} [{source.get('freshness', 'unchecked')}]" for source in row.get("sources", []))
            output.append(f"{row.get('title', row.get('id', 'Lesson'))} [{row.get('status', 'proposed')}]\n"
                          f"  Action: {_text(row.get('action', row.get('lesson', '')))}\n"
                          f"  Validation: {_text(row.get('validation', ''))}\n"
                          f"  Evidence: {sources or 'No source citations supplied'}")
        return "\n\n".join(output)
    if command == "report" and isinstance(result, dict):
        return f"Report written: {result['path']}\nSnapshot generated: {result['generated_at']}\nRefresh with: sim2claw ops report"
    if command == "status" and isinstance(result, dict):
        authority = result.get("authority", {})
        campaign = authority.get("campaign", {})
        coverage = result.get("coverage", {})
        lines = [f"Operations evidence: {result.get('root', '')}", f"Observed: {result.get('observed_at', '')}"]
        lines.append(f"Index: {coverage.get('indexed', 0)} indexed sources / {coverage.get('total', 0)} discovered")
        lines.append(f"Campaign: {campaign.get('current_milestone', campaign.get('status', 'unavailable'))}")
        lines.append(f"Campaign execution admitted: {authority.get('execution_admitted', False)}")
        if authority.get("error"):
            lines.append(f"Authority check unavailable: {authority['error']}")
        for blocker in authority.get("blockers", []):
            lines.append(f"Boundary: {blocker}")
        lines.append(f"Local annotations: {result.get('event_count', 0)}")
        lines.append("Historical sources support inspection; annotations do not grant authority.")
        return "\n".join(lines)
    if command == "watch" and isinstance(result, dict):
        change = "index unchanged after metadata check" if result.get("refresh", {}).get("status") == "unchanged" else "source index refreshed"
        return f"\nObserved {result.get('observed_at', '')} ({change})\n" + _human("status", result.get("status", {}))
    if command == "map" and isinstance(result, dict):
        nodes = result.get("nodes", [])
        lines = [str(result.get("description", "Operations structure"))]
        for node in nodes:
            lines.extend([f"\n{node.get('title', node.get('id', 'Component'))} [{node.get('state', 'unknown')}]", f"  Layer: {node.get('layer', '')}", f"  Next: {node.get('next_action', '')}", f"  Gate: {node.get('gate', '')}"])
        return "\n".join(lines)
    return _text(result)


def _emit(command: str, result: Any, *, as_json: bool) -> None:
    print(json.dumps(result, ensure_ascii=True, sort_keys=True) if as_json else _terminal(_human(command, result)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "max_bytes", 1) < 1:
        parser.error("--max-bytes must be positive")
    if getattr(args, "limit", 1) < 1:
        parser.error("--limit must be positive")
    if args.command == "show" and (args.start < 1 or args.end < args.start):
        parser.error("source lines must satisfy 1 <= --start <= --end")
    if args.command == "watch":
        if not math.isfinite(args.interval) or args.interval < 1:
            parser.error("--interval must be finite and at least 1 second")
        if args.count is not None and args.count < 1:
            parser.error("--count must be positive")
    from . import core

    root = args.root.expanduser().resolve()
    last_progress = 0.0

    def progress(update: dict[str, Any]) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if not args.as_json and (now - last_progress >= 5 or update.get("processed") == update.get("total")):
            print(_terminal(f"Indexing {update.get('processed', 0)}/{update.get('total', '?')}: {update.get('path', '')}"), file=sys.stderr)
            last_progress = now

    try:
        if args.command == "index":
            result = core.scan(root, max_bytes=args.max_bytes, progress=progress)
        elif args.command == "status":
            result = core.status(root)
        elif args.command == "search":
            result = core.search(root, args.query, kind=args.kind, limit=args.limit)
        elif args.command == "brief":
            result = core.brief(root, args.query, max_bytes=args.max_bytes)
        elif args.command == "show":
            result = core.show(root, args.path, start=args.start, end=args.end)
        elif args.command == "lessons":
            result = core.lessons(root)
        elif args.command == "map":
            result = core.architecture(root)
        elif args.command == "note":
            result = core.record_event(root, kind=args.kind, message=args.message, subject=args.subject)
        elif args.command == "events":
            result = core.events(root, limit=args.limit)
        elif args.command == "report":
            from .view import write_report

            output = args.output.expanduser()
            if not output.is_absolute():
                output = root / output
            try:
                relative_output = output.relative_to(root).as_posix()
            except ValueError as error:
                raise ValueError("report output must stay under outputs/operations in the repository") from error
            if not relative_output.startswith("outputs/operations/"):
                raise ValueError("report output must stay under outputs/operations in the repository")
            output = core._safe_path(root, relative_output)
            if output.suffix.lower() != ".html":
                raise ValueError("report output must have an .html extension")
            if core._git(root, "ls-files", "--", relative_output).strip():
                raise ValueError("report output must not overwrite a tracked file")
            try:
                core._git(root, "check-ignore", "-q", "--", relative_output)
            except ValueError as error:
                raise ValueError("report output must be ignored by Git under outputs/operations") from error
            core.scan(root, progress=progress)
            snapshot = core.snapshot(root)
            write_report(snapshot, output)
            result = {
                "status": "written",
                "path": str(output),
                "generated_at": snapshot.get("generated_at", snapshot.get("observed_at", datetime.now(timezone.utc).isoformat())),
            }
        elif args.command == "watch":
            iteration = 0
            while args.count is None or iteration < args.count:
                observation = core.poll(root)
                if observation["changed"]:
                    refresh = core.scan(root, progress=progress)
                    refresh = {key: value for key, value in refresh.items() if key != "sources"}
                    refresh["status"] = "refreshed"
                else:
                    refresh = {**observation, "status": "unchanged"}
                result = {
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "refresh": refresh,
                    "status": core.status(root),
                }
                _emit("watch", result, as_json=args.as_json)
                sys.stdout.flush()
                iteration += 1
                if args.count is None or iteration < args.count:
                    time.sleep(args.interval)
            return 0
        else:
            parser.error("unknown operations command")
        _emit(args.command, result, as_json=args.as_json)
        return 0
    except KeyboardInterrupt:
        if not args.as_json:
            print("Stopped watching.", file=sys.stderr)
        return 130
    except (OSError, ValueError, sqlite3.Error) as error:
        result = {"status": "error", "error": str(error)}
        if args.as_json:
            print(json.dumps(result, ensure_ascii=True, sort_keys=True))
        else:
            print(_terminal(f"Operations error: {error}"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
