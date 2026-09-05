#!/usr/bin/env python3
"""Compare source search implementations against an existing read-only index.

Example (save the baseline core.py before making changes):
    PYTHONPATH=src python scripts/benchmark_ops.py --baseline /path/to/core.py \
        --output outputs/operations-audit/performance-search.json

No indexing, journal access, page-cache flushing, or source writes are performed.
This measures the full search function with read-only SQLite connection setup,
excluding the production write-capable database bootstrap and CLI startup.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import sqlite3
import statistics
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sim2claw.ops import core


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--query", action="append", help="Repeat for each query; default: action, contact timing")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("--repeats must be between 1 and 10")
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        relative = output.relative_to(root / "outputs/operations-audit")
    except ValueError:
        parser.error("--output must be inside outputs/operations-audit")
    if not relative.name.startswith("performance-") or relative.suffix != ".json":
        parser.error("--output name must be performance-*.json")
    output = core._safe_path(root, str(output.relative_to(root)))
    if output.exists():
        parser.error("--output already exists; preserve the prior receipt")
    output.parent.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("sim2claw.ops._benchmark_baseline", args.baseline)
    if spec is None or spec.loader is None:
        parser.error("--baseline must name a Python module file")
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)

    index = root / "outputs/operations/index.sqlite"

    @contextmanager
    def readonly(_root: Path):
        db = sqlite3.connect(index.as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    baseline._db = readonly
    core._db = readonly
    with readonly(root) as db:
        data_version_before = db.execute("PRAGMA data_version").fetchone()[0]
        metadata = dict(db.execute("SELECT key,value FROM metadata"))
        if metadata.get("root") != str(root) or metadata.get("index_version") != core.INDEX_VERSION:
            parser.error("existing index root/version does not match this checkout")
        discovered_rows, discovered_bytes = db.execute("SELECT count(*),sum(bytes) FROM sources").fetchone()
        indexed_rows, indexed_bytes = db.execute(
            "SELECT count(*),sum(bytes) FROM sources WHERE status='indexed'").fetchone()
        before = index.stat()
        receipt = {
            "started_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "python": sys.version, "platform": platform.platform(),
            "measurement": "unprofiled full search with read-only database connection; excludes CLI and write-capable bootstrap",
            "cache_conditions": "existing resident index; no cache flush; alternating baseline/candidate order each repetition",
            "host_load_caveat": "shared host; other workloads may remain active; load recorded per trial",
            "index": {"discovered_rows": discovered_rows, "discovered_source_bytes": discovered_bytes,
                      "indexed_rows": indexed_rows, "indexed_source_bytes": indexed_bytes,
                      "sqlite_bytes": before.st_size,
                      "version": metadata["index_version"],
                      "coverage_sha256": hashlib.sha256(metadata.get("coverage", "").encode()).hexdigest()},
            "source_sha256": {"baseline": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                              "candidate": hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest(),
                              "harness": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "trials": [], "summaries": [],
        }
        queries = args.query or ["action", "contact timing"]
        equivalent = True
        for query in queries:
            expected = None
            for repeat in range(args.repeats):
                variants = [("baseline", baseline), ("candidate", core)]
                if repeat % 2:
                    variants.reverse()
                for name, module in variants:
                    load_before = os.getloadavg()
                    started, cpu = time.perf_counter(), time.process_time()
                    results = module.search(root, query, limit=20)
                    seconds, cpu_seconds = time.perf_counter() - started, time.process_time() - cpu
                    encoded = json.dumps(results, ensure_ascii=True, sort_keys=True).encode()
                    if expected is None:
                        expected = encoded
                    equivalent = equivalent and encoded == expected
                    trial = {"query": query, "repeat": repeat + 1, "variant": name,
                             "seconds": seconds, "cpu_seconds": cpu_seconds, "results": len(results),
                             "sha256": hashlib.sha256(encoded).hexdigest(), "equals_first": encoded == expected,
                             "load_before": load_before, "load_after": os.getloadavg()}
                    receipt["trials"].append(trial)
                    print(json.dumps(trial), flush=True)
            medians = {name: statistics.median(t["seconds"] for t in receipt["trials"]
                                              if t["query"] == query and t["variant"] == name)
                       for name in ("baseline", "candidate")}
            receipt["summaries"].append({"query": query, "median_seconds": medians,
                                         "speedup": medians["baseline"] / medians["candidate"]})
        after = index.stat()
        receipt["index_stat_unchanged"] = (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        data_version_after = db.execute("PRAGMA data_version").fetchone()[0]
        receipt["index_data_version"] = {"before": data_version_before, "after": data_version_after}
        receipt["index_data_version_unchanged"] = data_version_before == data_version_after
    receipt["outputs_equivalent"] = equivalent
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    with output.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"receipt": str(output), "outputs_equivalent": equivalent,
                      "summaries": receipt["summaries"]}))
    return 0 if equivalent and receipt["index_stat_unchanged"] and receipt["index_data_version_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
