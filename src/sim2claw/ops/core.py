"""Local evidence index. Text is evidence to inspect, never executable authority.

SQLite is a disposable derived index; source files and the existing current-state
compiler remain authoritative. No simulator, device or provider is imported here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
import zlib
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

SCHEMA = "sim2claw.ops.v1"
INDEX_VERSION = "3-compressed-narrative-identifiers"
MAX_BYTES = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".log", ".txt", ".stdout", ".stderr", ".request"}
ROOTS = ("docs", "configs/decisions", "outputs", "runs", ".factory", ".inspect_ai", "output", "artifacts", "tmp")
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", "node_modules", "sealed", "heldout", "held-out"}
GENERATED = {"outputs/operations", "outputs/operations-audit", "docs/operations"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("path must be repository-relative without parent traversal")
    current = root.resolve()
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink paths are not admitted")
    return current


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "cannot inspect repository")
    return result.stdout


@contextmanager
def _db(root: Path) -> Iterator[sqlite3.Connection]:
    root = root.resolve()
    directory = _safe_path(root, "outputs/operations")
    directory.mkdir(parents=True, exist_ok=True)
    path = _safe_path(root, "outputs/operations/index.sqlite")
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources (
                path TEXT PRIMARY KEY, kind TEXT, tracked INTEGER, status TEXT,
                sha256 TEXT, bytes INTEGER, lines INTEGER, metadata TEXT, content TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS spans USING fts5(path UNINDEXED, line UNINDEXED, text);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                kind TEXT NOT NULL, message TEXT NOT NULL, subject TEXT NOT NULL
            );
        """)
        identity = db.execute("SELECT value FROM metadata WHERE key='root'").fetchone()
        if identity and identity[0] != str(root):
            raise ValueError("index belongs to a different repository; rebuild in its original root")
        version = db.execute("SELECT value FROM metadata WHERE key='index_version'").fetchone()
        if not version or version[0] != INDEX_VERSION:
            db.execute("DELETE FROM sources")
            db.execute("DELETE FROM spans")
            db.execute("DELETE FROM metadata WHERE key='coverage'")
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('index_version', ?)", (INDEX_VERSION,))
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('root', ?)", (str(root),))
        db.commit()
        yield db
    finally:
        db.close()


@contextmanager
def _journal(root: Path) -> Iterator[sqlite3.Connection]:
    """Durable human annotations, independent of the disposable evidence index.

    The first open migrates any pre-separation events exactly once. Both the
    migration and its marker commit in the same journal transaction, so retries
    cannot duplicate notes. A journal is user data and must not be cache-pruned.
    """
    root = root.resolve()
    directory = _safe_path(root, "outputs/operations")
    directory.mkdir(parents=True, exist_ok=True)
    path = _safe_path(root, "outputs/operations/journal.sqlite")
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                kind TEXT NOT NULL, message TEXT NOT NULL, subject TEXT NOT NULL
            );
        """)
        # Serialize initialization/migration with concurrent appenders.
        db.execute("BEGIN IMMEDIATE")
        identity = db.execute("SELECT value FROM metadata WHERE key='root'").fetchone()
        if identity and identity[0] != str(root):
            raise ValueError("journal belongs to a different repository; preserve it in its original root")
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('root', ?)", (str(root),))
        migrated = db.execute("SELECT value FROM metadata WHERE key='legacy_index_migration'").fetchone()
        if migrated is None:
            legacy_path = _safe_path(root, "outputs/operations/index.sqlite")
            if legacy_path.exists():
                legacy = sqlite3.connect(legacy_path.as_uri() + "?mode=ro", uri=True, timeout=30)
                try:
                    legacy_identity = legacy.execute("SELECT value FROM metadata WHERE key='root'").fetchone()
                    if legacy_identity is None or legacy_identity[0] != str(root):
                        raise ValueError("legacy index belongs to a different repository; annotation migration refused")
                    has_events = legacy.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
                    if has_events:
                        rows = legacy.execute("SELECT id,at,kind,message,subject FROM events ORDER BY id").fetchall()
                        db.executemany("INSERT INTO events(id,at,kind,message,subject) VALUES (?,?,?,?,?)", rows)
                finally:
                    legacy.close()
            db.execute("INSERT INTO metadata VALUES ('legacy_index_migration', ?)", (_utc(),))
        db.commit()
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _kind(path: str) -> str:
    for directory, kind in (("session-logs", "session"), ("reviewer-messages", "review"),
                            ("manager-log", "manager"), ("briefs", "brief"),
                            ("run-logs", "run_log"), ("configs/decisions", "decision")):
        if directory in path:
            return kind
    return "document" if path.startswith("docs/") else "runtime"


def _excluded(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in GENERATED)


def _admitted(root: Path, relative: str) -> bool:
    if _excluded(relative) or set(Path(relative).parts) & EXCLUDED_DIRS:
        return False
    path = _safe_path(root, relative)
    for parent in path.parents:
        if parent == root.resolve():
            break
        if (parent / ".git").exists():
            return False
    return True


def _discover(root: Path) -> tuple[dict[str, bool], dict[str, Any]]:
    tracked = set(_git(root, "ls-files", "-z").split("\0")) - {""}
    candidates: dict[str, bool] = {}
    exclusions: Counter[str] = Counter()
    errors: list[str] = []
    boundaries: list[str] = []
    def relevant(path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in ROOTS)
    for path in tracked:
        if relevant(path) and Path(path).suffix.lower() in TEXT_SUFFIXES and not _excluded(path):
            if not (set(Path(path).parts) & EXCLUDED_DIRS):
                candidates[path] = True
    for prefix in ROOTS:
        base = root / prefix
        if base.is_symlink():
            boundaries.append(prefix + " (symlink root)")
            continue
        if not base.exists():
            continue
        def onerror(error: OSError) -> None:
            errors.append(str(error))
        for directory, dirs, files in os.walk(base, followlinks=False, onerror=onerror):
            parent = Path(directory)
            if parent != root and (parent / ".git").exists():
                boundaries.append(parent.relative_to(root).as_posix() + " (nested repository)")
                dirs[:] = []
                continue
            admitted = []
            for name in sorted(dirs):
                path = (parent / name).relative_to(root).as_posix()
                if name in EXCLUDED_DIRS or _excluded(path) or (parent / name).is_symlink():
                    boundaries.append(path)
                else:
                    admitted.append(name)
            dirs[:] = admitted
            for name in sorted(files):
                path = (parent / name).relative_to(root).as_posix()
                if Path(name).suffix.lower() not in TEXT_SUFFIXES:
                    exclusions[Path(name).suffix.lower() or "no_extension"] += 1
                elif not _excluded(path):
                    candidates[path] = path in tracked
    return candidates, {"excluded_nontext_by_suffix": dict(exclusions), "excluded_boundaries": sorted(set(boundaries)),
                        "discovery_errors": errors, "roots": list(ROOTS),
                        "scope": "Repository-local operating documents, decisions and runtime text; no global agent sessions, nested checkouts, held-out directories, media or archives."}


def _metadata(path: str, content: str) -> dict[str, Any]:
    result: dict[str, Any] = {"claim_state": "source_reported_unverified"}
    if path.endswith(".json"):
        try:
            value = json.loads(content)
            if isinstance(value, dict):
                for key in ("schema_version", "status", "proof_class", "authority", "claim_limits", "next_transition"):
                    if key in value:
                        result["declared_status" if key == "status" else key] = value[key]
            else:
                result["json_type"] = type(value).__name__
        except (ValueError, RecursionError) as error:
            result["parse_error"] = str(error)
    else:
        for number, line in enumerate(content.splitlines(), 1):
            match = re.match(r"(?:Status|Disposition|Decision|Result):\s*(.+)", line, re.I)
            if match:
                result["reported_disposition"] = {"text": match[1][:500], "line": number}
                break
    return result


def _content(value: bytes | str) -> str:
    return zlib.decompress(value).decode("utf-8") if isinstance(value, bytes) else value


def _search_text(path: str, content: str) -> str:
    # Numeric sample arrays are data, not agent narrative. Preserve all original
    # bytes compressed for exact spans, while keeping runtime trace floats out
    # of the full-text dictionary. Operational documents/decisions stay verbatim.
    if _kind(path) == "runtime" and Path(path).suffix in {".json", ".jsonl"}:
        return " ".join(dict.fromkeys(re.findall(r"\b\w*[^\W\d_]\w*\b", content, re.UNICODE)))
    return content


def _fingerprint(root: Path, candidates: dict[str, bool], discovery: dict[str, Any]) -> str:
    # Own outputs and unrelated media cannot change the text corpus. Changes to
    # actual admission boundaries alter the candidate set below.
    hasher = hashlib.sha256(json.dumps(discovery["discovery_errors"], sort_keys=True).encode())
    for relative, tracked in sorted(candidates.items()):
        try:
            path = _safe_path(root, relative)
            observed = path.stat()
            value = (relative, tracked, observed.st_size, observed.st_mtime_ns, observed.st_ctime_ns,
                     observed.st_ino, _admitted(root, relative))
        except (OSError, ValueError) as error:
            value = (relative, tracked, type(error).__name__)
        hasher.update(json.dumps(value).encode())
    return hasher.hexdigest()


def poll(root: Path) -> dict[str, Any]:
    """Cheap change hint for watch; explicit scan always rehashes source bytes."""
    root = root.resolve()
    candidates, discovery = _discover(root)
    signature = _fingerprint(root, candidates, discovery)
    with _db(root) as db:
        row = db.execute("SELECT value FROM metadata WHERE key='poll_signature'").fetchone()
        coverage = db.execute("SELECT value FROM metadata WHERE key='coverage'").fetchone()
    return {"changed": not coverage or not row or row[0] != signature, "signature": signature,
            "observed_at": _utc(), "semantics": "metadata change hint; index performs content verification"}


def scan(root: Path, *, max_bytes: int = MAX_BYTES, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    if not 1 <= max_bytes <= MAX_SOURCE_BYTES:
        raise ValueError("max_bytes must be between 1 and 64 MiB")
    root = root.resolve()
    started = time.monotonic()
    candidates, discovery = _discover(root)
    fingerprint = _fingerprint(root, candidates, discovery)
    changed = unchanged = 0
    with _db(root) as db, db:
        previous = {row["path"]: dict(row) for row in db.execute("SELECT path,sha256,status FROM sources")}
        # Retain tombstones so disappearing ignored files remain accounted for.
        for path in previous:
            candidates.setdefault(path, False)
        last_progress = started
        for number, (relative, tracked) in enumerate(sorted(candidates.items()), 1):
            if progress and time.monotonic() - last_progress >= 0.5:
                progress({"processed": number - 1, "total": len(candidates), "path": relative})
                last_progress = time.monotonic()
            state, data, content, metadata, size = "indexed", b"", "", {}, 0
            try:
                path = _safe_path(root, relative)
                size = path.stat().st_size
                if not _admitted(root, relative):
                    state = "skipped_boundary"
                elif not path.is_file():
                    state = "missing"
                elif size > max_bytes:
                    state = "skipped_oversize"
                else:
                    with path.open("rb") as stream:
                        data = stream.read(max_bytes + 1)
                    if len(data) > max_bytes:
                        state = "skipped_oversize"
                    else:
                        content = data.decode("utf-8")
                        if "\x00" in content:
                            raise UnicodeError("NUL bytes in text source")
            except FileNotFoundError:
                state = "missing"
            except UnicodeError:
                state = "decode_error"
            except ValueError:
                state = "skipped_symlink"
            except OSError as error:
                state, metadata = "read_error", {"error": str(error)}
            digest = _digest(data) if state == "indexed" else None
            old = previous.get(relative)
            if old and old["sha256"] == digest and old["status"] == state:
                unchanged += 1
                db.execute("UPDATE sources SET tracked=?,bytes=? WHERE path=?", (tracked, size, relative))
                continue
            changed += 1
            if old is not None:
                db.execute("DELETE FROM spans WHERE path=?", (relative,))
            lines = content.splitlines() if state == "indexed" else []
            if state == "indexed":
                metadata = _metadata(relative, content)
            db.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                       (relative, _kind(relative), tracked, state, digest, size, len(lines), json.dumps(metadata), zlib.compress(content.encode("utf-8"), 1) if state == "indexed" else ""))
            if content and state == "indexed":
                db.execute("INSERT INTO spans VALUES (?,?,?)", (relative, 1, _search_text(relative, content)))
        rows = [dict(row) for row in db.execute("SELECT path,kind,tracked,status,sha256,bytes,lines,metadata FROM sources ORDER BY path")]
        for row in rows:
            row["metadata"] = json.loads(row["metadata"])
        counts = dict(Counter(row["status"] for row in rows))
        coverage = {"schema_version": SCHEMA, "at": _utc(), "root": str(root), "head": _git(root, "rev-parse", "--verify", "HEAD").strip() if _has_head(root) else None,
                    "total": len(rows), "indexed": counts.get("indexed", 0), "skipped": len(rows) - counts.get("indexed", 0),
                    "counts": counts, "by_kind": dict(Counter(row["kind"] for row in rows)),
                    "bytes_indexed": sum(row["bytes"] for row in rows if row["status"] == "indexed"),
                    "changed": changed, "unchanged": unchanged, "max_bytes": max_bytes,
                    "duration_seconds": round(time.monotonic() - started, 3), **discovery}
        coverage["search_semantics"] = "Full text for documents and decisions; runtime JSON indexes narrative word tokens, not raw numeric arrays. Full source spans remain available through show."
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('coverage', ?)", (json.dumps(coverage),))
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('poll_signature', ?)", (fingerprint,))
    return {**coverage, "sources": rows}


def _has_head(root: Path) -> bool:
    try:
        _git(root, "rev-parse", "--verify", "HEAD")
        return True
    except ValueError:
        return False


def _freshness(root: Path, path: str, digest: str | None) -> str:
    try:
        if not _admitted(root, path):
            return "unavailable"
        source = _safe_path(root, path)
        # Bound checks even if an indexed source subsequently grows.
        if source.stat().st_size > MAX_SOURCE_BYTES:
            return "stale"
        hasher = hashlib.sha256()
        read = 0
        with source.open("rb") as stream:
            while data := stream.read(1024 * 1024):
                read += len(data)
                if read > MAX_SOURCE_BYTES:
                    return "stale"
                hasher.update(data)
        return "current" if hasher.hexdigest() == digest else "stale"
    except FileNotFoundError:
        return "missing"
    except (OSError, ValueError):
        return "unavailable"


def status(root: Path) -> dict[str, Any]:
    root = root.resolve()
    with _db(root) as db:
        row = db.execute("SELECT value FROM metadata WHERE key='coverage'").fetchone()
        coverage = json.loads(row[0]) if row else {"status": "not_indexed", "total": 0, "indexed": 0}
    with _journal(root) as db:
        event_count = db.execute("SELECT count(*) FROM events").fetchone()[0]
    try:
        from ..agent_context import compile_agent_context
        authority = compile_agent_context(root, role="manager")
    except Exception as error:
        authority = {"status": "unavailable", "execution_admitted": False, "error": str(error)}
    return {"schema_version": SCHEMA, "observed_at": _utc(), "root": str(root), "coverage": coverage,
            "authority": authority, "event_count": event_count,
            "operations_authority": "inspect_and_annotate_only", "index_semantics": "historical source text; scan refreshes index; retrieved spans are hash-checked on read"}


def search(root: Path, query: str, *, kind: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    terms = re.findall(r"\w+", query, flags=re.UNICODE)
    if not terms:
        return []
    match = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms[:32])
    result = []
    patterns = [re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I) for term in terms[:32]]
    with _db(root) as db:
        rows = db.execute("""SELECT spans.path, sources.content, sources.sha256, sources.kind,
                              sources.metadata FROM spans JOIN sources ON sources.path=spans.path
                              WHERE spans MATCH ? AND (? IS NULL OR sources.kind=?)
                              ORDER BY rank, spans.path""", (match, kind, kind))
        for row in rows:
            item = dict(row)
            content = _content(item.pop("content"))
            item["metadata"] = json.loads(item["metadata"])
            item["freshness"] = _freshness(root, item["path"], item["sha256"])
            for number, line in enumerate(content.splitlines(), 1):
                if all(pattern.search(line) for pattern in patterns):
                    result.append({**item, "line": number, "text": line[:2000]})
                    if len(result) == limit:
                        return result
    return result


def show(root: Path, path: str, *, start: int = 1, end: int = 80) -> dict[str, Any]:
    _safe_path(root, path)
    if start < 1 or end < start or end - start >= 500:
        raise ValueError("source span must contain 1 to 500 lines starting at line 1 or later")
    with _db(root) as db:
        row = db.execute("SELECT * FROM sources WHERE path=?", (path,)).fetchone()
    if row is None:
        raise ValueError("source is not indexed; run index and use a discovered path")
    item = dict(row)
    item["metadata"] = json.loads(item["metadata"])
    item["freshness"] = _freshness(root, path, item["sha256"])
    item["spans"] = [{"line": n, "text": line} for n, line in enumerate(_content(item.pop("content")).splitlines(), 1) if start <= n <= end]
    return item


def _catalog(root: Path, name: str) -> dict[str, Any]:
    path = _safe_path(root, "configs/operations/" + name + ".v1.json")
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("operations catalog must be an object")
    return value


def lessons(root: Path) -> list[dict[str, Any]]:
    result = []
    for raw in _catalog(root, "lessons").get("lessons", []):
        item = dict(raw)
        citations = []
        for source in item.get("sources", []):
            citation = dict(source)
            try:
                path = _safe_path(root, source["path"])
                if not _admitted(root, source["path"]):
                    raise ValueError("citation is outside admitted source boundaries")
                with path.open("rb") as stream:
                    data = stream.read(MAX_SOURCE_BYTES + 1)
                citation["freshness"] = "current" if len(data) <= MAX_SOURCE_BYTES and _digest(data) == source.get("sha256") else "stale"
                lines = data.decode("utf-8").splitlines() if citation["freshness"] == "current" else []
                start, end = source["line"], source.get("end_line", source["line"])
                typed_span = type(start) is int and type(end) is int
                if citation["freshness"] == "current" and (not typed_span or start < 1 or end < start or end > len(lines)):
                    citation["freshness"] = "invalid_span"
                citation["excerpt"] = "\n".join(lines[start - 1:end])[:3000] if citation["freshness"] == "current" else ""
            except FileNotFoundError:
                citation["freshness"] = "missing"
            except (KeyError, OSError, ValueError, TypeError):
                citation["freshness"] = "unavailable"
            citations.append(citation)
        item["sources"] = citations
        item["evidence_state"] = "current" if citations and all(c["freshness"] == "current" for c in citations) else "needs_review"
        item["authority"] = "advisory_only"
        result.append(item)
    return result


def architecture(root: Path) -> dict[str, Any]:
    value = _catalog(root, "architecture")
    nodes = value.get("nodes", [])
    ids = [node["id"] for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate architecture node id")
    for node in nodes:
        node["path_state"] = [{"path": path, "exists": _safe_path(root, path).exists()} for path in node.get("paths", [])]
    for edge in value.get("edges", []):
        if edge["from"] not in ids or edge["to"] not in ids:
            raise ValueError("architecture edge references an unknown node")
    return {"schema_version": "sim2claw.ops.architecture.v1", **value,
            "authority": "descriptive_and_proposed_only"}


def brief(root: Path, query: str, *, max_bytes: int = 12000) -> dict[str, Any]:
    """Prepare inspectable evidence context, without authorizing an Executor."""
    if not 1024 <= max_bytes <= 64000 or not query.strip() or len(query) > 2000:
        raise ValueError("brief requires a query of 1 to 2000 characters and a 1024 to 64000 byte budget")
    current = status(root)
    context = current["authority"]
    authority = {key: context[key] for key in ("status", "error", "campaign", "execution_admitted", "authority", "source_identities", "context_digest") if key in context}
    stopwords = {"the", "a", "an", "how", "do", "to", "and", "of", "for", "in", "we", "can", "with", "is"}
    terms = set(re.findall(r"\w+", query.lower())) - stopwords
    found = search(root, query, limit=20)
    if not found:
        seen = set()
        for term in sorted(terms)[:8]:
            for item in search(root, term, limit=4):
                identity = (item["path"], item["line"])
                if identity not in seen:
                    found.append(item)
                    seen.add(identity)
    candidates = []
    for lesson in lessons(root):
        text = " ".join(str(lesson.get(key, "")) for key in ("title", "domain", "lesson", "action"))
        score = len(terms & set(re.findall(r"\w+", text.lower())))
        if score:
            compact = {key: lesson[key] for key in ("id", "title", "status", "action", "validation", "evidence_state") if key in lesson}
            compact["sources"] = [{key: citation[key] for key in ("path", "line", "end_line", "sha256", "freshness") if key in citation} for citation in lesson["sources"]]
            candidates.append((score, compact))
    candidates.sort(key=lambda row: (-row[0], row[1]["id"]))
    feedback = [event for event in events(root, limit=30)
                if terms & set(re.findall(r"\w+", (event["subject"] + " " + event["message"]).lower()))]
    packet: dict[str, Any] = {"schema_version": "sim2claw.ops.brief.v1", "query": query, "authority": authority,
                             "use": "Historical evidence and proposed advice; follow the current role packet before execution.",
                             "sources": [], "lessons": [], "events": [], "omitted_sources": len(found), "omitted_lessons": len(candidates), "omitted_events": len(feedback),
                             "max_bytes": max_bytes, "bytes": 0}
    def size() -> int:
        return len(json.dumps(packet, ensure_ascii=True, sort_keys=True).encode("utf-8"))
    if size() > max_bytes:
        packet["authority"] = {"status": context.get("status", "unavailable"), "execution_admitted": False,
                               "detail": "Full authority packet exceeds budget; run agent-context --role executor separately."}
    # Interleave lessons and evidence so a large list cannot hide either.
    for index in range(max(len(found), len(candidates), len(feedback))):
        for key, items in (("sources", found), ("lessons", [row[1] for row in candidates]), ("events", feedback)):
            if index < len(items):
                packet[key].append(items[index])
                packet["omitted_" + key] -= 1
                if size() + 20 > max_bytes:
                    packet[key].pop()
                    packet["omitted_" + key] += 1
    packet["bytes"] = size()
    while packet["bytes"] != size():
        packet["bytes"] = size()
    if packet["bytes"] > max_bytes:
        raise ValueError("query and required provenance exceed requested byte budget")
    return packet


def record_event(root: Path, *, kind: str, message: str, subject: str = "") -> dict[str, Any]:
    if kind not in {"note", "hypothesis", "decision", "feedback", "milestone"}:
        raise ValueError("unsupported annotation kind")
    if not message.strip() or len(message) > 4000 or len(subject) > 300:
        raise ValueError("message must contain 1 to 4000 characters; subject is limited to 300")
    with _journal(root) as db, db:
        at = _utc()
        cursor = db.execute("INSERT INTO events(at,kind,message,subject) VALUES (?,?,?,?)", (at, kind, message.strip(), subject))
        return {"id": cursor.lastrowid, "at": at, "kind": kind, "message": message.strip(), "subject": subject, "authority": "annotation_only"}


def events(root: Path, *, limit: int = 30) -> list[dict[str, Any]]:
    if not 1 <= limit <= 1000:
        raise ValueError("event limit must be between 1 and 1000")
    with _journal(root) as db:
        return [{**dict(row), "authority": "annotation_only"} for row in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]


def snapshot(root: Path) -> dict[str, Any]:
    result = status(root)
    with _db(root) as db:
        sources = []
        for row in db.execute("SELECT path,kind,status,sha256,bytes,lines,metadata,content FROM sources ORDER BY path"):
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            raw = item.pop("content")
            item["excerpt"] = zlib.decompressobj().decompress(raw, 2400).decode("utf-8", errors="replace")[:600] if isinstance(raw, bytes) else raw[:600]
            sources.append(item)
    return {**result, "sources": sources, "lessons": lessons(root), "architecture": architecture(root), "events": events(root),
            "source_freshness": "indexed_at_scan_time; CLI search/show recheck selected source hashes"}
