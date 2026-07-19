"""Hash-bound runtime identity for a locally served GR00T checkpoint.

The checkpoint manifest is evidence only when its complete file inventory
matches the directory passed to the server.  The runtime identity then binds
that verified payload to the live process and its exact command line.  A
rollout must re-read the live process state before its first policy query.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .groot_evaluation_identity import (
    RUNTIME_MODULES,
    SERVER_ATTESTED_MODULES,
    SERVER_ENVIRONMENT_KEYS,
    load_evaluation_manifest,
    load_server_import_attestation,
    runtime_asset_inventory,
    selected_server_environment,
)


CHECKPOINT_MANIFEST_SCHEMA = "sim2claw.groot_checkpoint_manifest.v1"
CHECKPOINT_PREFLIGHT_SCHEMA = "sim2claw.groot_checkpoint_preflight.v1"
RUNTIME_IDENTITY_SCHEMA = "sim2claw.groot_server_runtime_identity.v2"
SHA256_HEX_LENGTH = 64
SERVER_ATTESTED_OPTION_ORDER = (
    "--model-path",
    "--processor-model-path",
    "--embodiment-tag",
    "--device",
    "--host",
    "--port",
    "--proposal-count",
    "--action-aggregation",
    "--noise-scale",
    "--num-inference-timesteps",
    "--checkpoint-manifest-sha256",
    "--checkpoint-payload-sha256",
    "--evaluation-manifest",
    "--evaluation-manifest-sha256",
    "--sim2claw-root",
    "--groot-root",
    "--server-import-identity",
    "--maximum-runtime-seconds",
)
SERVER_IDENTITY_OPTIONS = frozenset(SERVER_ATTESTED_OPTION_ORDER[10:])


@dataclass(frozen=True)
class ProcessSnapshot:
    """Evaluator-visible identity of one live Linux process."""

    pid: int
    process_start_ticks: int
    boot_id: str
    executable: str
    cwd: str
    argv: tuple[str, ...]
    cmdline_sha256: str
    environment: tuple[tuple[str, str | None], ...]
    environment_sha256: str
    listening_tcp_ports: tuple[int, ...]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class _RaisingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def seeded_server_argument_parser() -> argparse.ArgumentParser:
    """Return the sole parser for the seeded policy-server command line."""

    parser = _RaisingArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--processor-model-path")
    parser.add_argument("--embodiment-tag", default="new_embodiment")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--proposal-count", type=int, default=1)
    parser.add_argument(
        "--action-aggregation",
        choices=("mean", "median", "medoid", "trimmed_mean"),
        default="medoid",
    )
    parser.add_argument("--noise-scale", type=float, default=1.0)
    parser.add_argument("--num-inference-timesteps", type=int)
    parser.add_argument("--checkpoint-manifest-sha256")
    parser.add_argument("--checkpoint-payload-sha256")
    parser.add_argument("--evaluation-manifest")
    parser.add_argument("--evaluation-manifest-sha256")
    parser.add_argument("--sim2claw-root")
    parser.add_argument("--groot-root")
    parser.add_argument("--server-import-identity")
    parser.add_argument("--maximum-runtime-seconds", type=int)
    return parser


def parse_seeded_server_argv(
    argv: tuple[str, ...] | list[str],
    *,
    require_attested: bool = False,
) -> argparse.Namespace:
    """Parse one unambiguous argv, rejecting aliases and second meanings."""

    tokens = tuple(argv)
    if len(tokens) % 2:
        raise ValueError("seeded server argv must contain option/value pairs")
    known = frozenset(SERVER_ATTESTED_OPTION_ORDER)
    options: list[str] = []
    for index in range(0, len(tokens), 2):
        option = tokens[index]
        value = tokens[index + 1]
        if "=" in option or option not in known:
            raise ValueError(f"noncanonical seeded server option: {option}")
        if value.startswith("--"):
            raise ValueError(f"seeded server option has no value: {option}")
        if option in options:
            raise ValueError(f"duplicate seeded server option: {option}")
        options.append(option)
    attested = bool(set(options) & SERVER_IDENTITY_OPTIONS)
    if require_attested or attested:
        if tuple(options) != SERVER_ATTESTED_OPTION_ORDER:
            raise ValueError("attested seeded server argv is not canonical and complete")
    return seeded_server_argument_parser().parse_args(tokens)


def _require_sha256(value: object, label: str) -> str:
    text = str(value)
    if len(text) != SHA256_HEX_LENGTH:
        raise ValueError(f"{label} is not a SHA-256 digest")
    try:
        bytes.fromhex(text)
    except ValueError as error:
        raise ValueError(f"{label} is not a SHA-256 digest") from error
    return text


def load_checkpoint_manifest(
    path: Path,
    *,
    expected_step: int = 1000,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CHECKPOINT_MANIFEST_SCHEMA:
        raise ValueError("unsupported checkpoint manifest")
    if int(payload.get("checkpoint_step", -1)) != expected_step:
        raise ValueError(f"checkpoint manifest is not step {expected_step}")
    files = payload.get("files")
    sizes = payload.get("file_sizes_bytes")
    if not isinstance(files, dict) or not files:
        raise ValueError("checkpoint manifest has no file identities")
    if not isinstance(sizes, dict) or set(sizes) != set(files):
        raise ValueError("checkpoint manifest file-size inventory differs from hashes")
    for relative, digest in files.items():
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
        ):
            raise ValueError("checkpoint manifest contains an invalid relative path")
        if ".." in Path(relative).parts:
            raise ValueError("checkpoint manifest path escapes its checkpoint root")
        _require_sha256(digest, f"checkpoint file {relative}")
        if int(sizes[relative]) < 0:
            raise ValueError(f"checkpoint file has a negative size: {relative}")
    if int(payload.get("file_count", -1)) != len(files):
        raise ValueError("checkpoint manifest file count is inconsistent")
    if int(payload.get("total_size_bytes", -1)) != sum(
        int(value) for value in sizes.values()
    ):
        raise ValueError("checkpoint manifest total size is inconsistent")
    checkpoint_path = payload.get("checkpoint_path")
    if not isinstance(checkpoint_path, str) or not Path(checkpoint_path).is_absolute():
        raise ValueError("checkpoint manifest has no absolute checkpoint path")
    return payload


def checkpoint_payload_sha256(manifest: dict[str, Any]) -> str:
    """Return the path-independent identity of the checkpoint file payload."""

    payload = {
        "schema_version": manifest["schema_version"],
        "checkpoint_step": int(manifest["checkpoint_step"]),
        "files": manifest["files"],
        "file_sizes_bytes": {
            key: int(value) for key, value in manifest["file_sizes_bytes"].items()
        },
        "file_count": int(manifest["file_count"]),
        "total_size_bytes": int(manifest["total_size_bytes"]),
    }
    return canonical_sha256(payload)


def verify_checkpoint_directory(
    manifest_path: Path,
    checkpoint_directory: Path,
    *,
    expected_step: int = 1000,
) -> dict[str, Any]:
    """Rehash every checkpoint file and reject path or inventory drift."""

    resolved_manifest = manifest_path.resolve(strict=True)
    resolved_checkpoint = checkpoint_directory.resolve(strict=True)
    if not resolved_checkpoint.is_dir():
        raise ValueError("checkpoint path is not a directory")
    manifest = load_checkpoint_manifest(resolved_manifest, expected_step=expected_step)
    recorded_path = Path(manifest["checkpoint_path"]).resolve(strict=True)
    if recorded_path != resolved_checkpoint:
        raise ValueError(
            "checkpoint directory differs from the path recorded in its manifest"
        )

    expected_files = manifest["files"]
    actual_paths = {
        path.relative_to(resolved_checkpoint).as_posix(): path
        for path in resolved_checkpoint.rglob("*")
        if path.is_file()
    }
    if set(actual_paths) != set(expected_files):
        raise ValueError("checkpoint directory inventory differs from its manifest")
    for relative, path in actual_paths.items():
        expected_size = int(manifest["file_sizes_bytes"][relative])
        if path.stat().st_size != expected_size:
            raise ValueError(f"checkpoint file size drifted: {relative}")
        if sha256_file(path) != expected_files[relative]:
            raise ValueError(f"checkpoint file hash drifted: {relative}")

    return {
        "schema_version": CHECKPOINT_PREFLIGHT_SCHEMA,
        "checkpoint_step": int(manifest["checkpoint_step"]),
        "checkpoint_path": str(resolved_checkpoint),
        "checkpoint_manifest_path": str(resolved_manifest),
        "checkpoint_manifest_sha256": sha256_file(resolved_manifest),
        "checkpoint_payload_sha256": checkpoint_payload_sha256(manifest),
        "file_count": int(manifest["file_count"]),
        "total_size_bytes": int(manifest["total_size_bytes"]),
        "complete_file_inventory_verified": True,
    }


def _process_start_ticks(stat_text: str) -> int:
    closing_parenthesis = stat_text.rfind(")")
    if closing_parenthesis < 0:
        raise ValueError("Linux process stat is malformed")
    fields_after_name = stat_text[closing_parenthesis + 2 :].split()
    if len(fields_after_name) <= 19:
        raise ValueError("Linux process stat has no start-time field")
    return int(fields_after_name[19])


def read_process_snapshot(pid: int) -> ProcessSnapshot:
    """Read a live process identity from procfs and reject a vanished PID."""

    if pid <= 0:
        raise ValueError("server PID must be positive")
    process_root = Path("/proc") / str(pid)
    raw_cmdline = (process_root / "cmdline").read_bytes()
    argv = tuple(
        part.decode("utf-8", errors="surrogateescape")
        for part in raw_cmdline.split(b"\0")
        if part
    )
    if not argv:
        raise ValueError("server process has an empty command line")
    executable = str((process_root / "exe").resolve(strict=True))
    cwd = str((process_root / "cwd").resolve(strict=True))
    raw_environment = (process_root / "environ").read_bytes()
    environment_values: dict[str, str] = {}
    for entry in raw_environment.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        raw_name, raw_value = entry.split(b"=", 1)
        name = raw_name.decode("utf-8", errors="surrogateescape")
        environment_values[name] = raw_value.decode(
            "utf-8", errors="surrogateescape"
        )
    environment = tuple(
        selected_server_environment(environment_values).items()
    )
    start_ticks = _process_start_ticks(
        (process_root / "stat").read_text(encoding="utf-8")
    )
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    listening_tcp_ports = _listening_tcp_ports(process_root)
    return ProcessSnapshot(
        pid=pid,
        process_start_ticks=start_ticks,
        boot_id=boot_id,
        executable=executable,
        cwd=cwd,
        argv=argv,
        cmdline_sha256=hashlib.sha256(raw_cmdline).hexdigest(),
        environment=environment,
        environment_sha256=canonical_sha256(dict(environment)),
        listening_tcp_ports=listening_tcp_ports,
    )


def _listening_tcp_ports(process_root: Path) -> tuple[int, ...]:
    socket_inodes: set[str] = set()
    for descriptor in (process_root / "fd").iterdir():
        try:
            target = os.readlink(descriptor)
        except OSError:
            continue
        if target.startswith("socket:[") and target.endswith("]"):
            socket_inodes.add(target[8:-1])
    ports: set[int] = set()
    for table_name in ("tcp", "tcp6"):
        table = process_root / "net" / table_name
        try:
            rows = table.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) <= 9 or fields[3] != "0A" or fields[9] not in socket_inodes:
                continue
            ports.add(int(fields[1].rsplit(":", 1)[1], 16))
    return tuple(sorted(ports))


def expected_server_environment(
    *,
    repo_root: Path,
    groot_root: Path,
    processor_model_path: Path,
) -> tuple[tuple[str, str | None], ...]:
    values: dict[str, str | None] = {
        name: None for name in SERVER_ENVIRONMENT_KEYS
    }
    resolved_repo = repo_root.resolve(strict=True)
    resolved_groot = groot_root.resolve(strict=True)
    resolved_processor = processor_model_path.resolve(strict=True)
    values.update(
        {
            "GROOT_BACKBONE_MODEL_PATH": str(resolved_processor),
            "GROOT_DIR": str(resolved_groot),
            "GROOT_PROCESSOR_MODEL_PATH": str(resolved_processor),
            "HF_HUB_OFFLINE": "1",
            "NO_ALBUMENTATIONS_UPDATE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(resolved_repo / "src"),
            "PYTHONSAFEPATH": "1",
            "SIM2CLAW_ROOT": str(resolved_repo),
            "TRANSFORMERS_OFFLINE": "1",
            "VIRTUAL_ENV": str(resolved_groot / ".venv"),
        }
    )
    return tuple((name, values[name]) for name in SERVER_ENVIRONMENT_KEYS)


def _validate_server_import_attestation(
    *,
    attestation_path: Path,
    snapshot: ProcessSnapshot,
    evaluation_manifest_path: Path,
    evaluation_manifest: dict[str, Any],
    server_script: Path,
    repo_root: Path,
) -> dict[str, Any]:
    resolved_attestation = attestation_path.resolve(strict=True)
    attestation = load_server_import_attestation(resolved_attestation)
    process = attestation.get("process")
    if not isinstance(process, dict):
        raise ValueError("server import attestation has no process identity")
    expected_process = {
        "pid": snapshot.pid,
        "executable": snapshot.executable,
        "cwd": snapshot.cwd,
        "argv": list(snapshot.argv),
        "environment": dict(snapshot.environment),
    }
    for key, expected in expected_process.items():
        if process.get(key) != expected:
            raise ValueError(f"server import attestation process {key} differs")
    sys_path = process.get("sys_path")
    expected_python_path = str(repo_root.resolve(strict=True) / "src")
    if (
        not isinstance(sys_path, list)
        or not sys_path
        or sys_path[0] != expected_python_path
    ):
        raise ValueError("server import attestation Python path is not canonical")

    resolved_manifest = evaluation_manifest_path.resolve(strict=True)
    expected_evaluation = {
        "manifest_path": str(resolved_manifest),
        "manifest_sha256": sha256_file(resolved_manifest),
        "canonical_payload_sha256": evaluation_manifest[
            "canonical_payload_sha256"
        ],
        "implementation_inventory_sha256": evaluation_manifest[
            "implementation_inventory_sha256"
        ],
        "runtime_sha256": evaluation_manifest["runtime_sha256"],
        "runtime_assets_sha256": evaluation_manifest[
            "runtime_assets_sha256"
        ],
    }
    if attestation.get("evaluation_implementation") != expected_evaluation:
        raise ValueError("server import attestation evaluation identity differs")

    script = server_script.resolve(strict=True)
    expected_script = {
        "path": str(script),
        "sha256": sha256_file(script),
        "size_bytes": script.stat().st_size,
    }
    if attestation.get("server_script") != expected_script:
        raise ValueError("server import attestation script identity differs")

    modules = attestation.get("imported_modules")
    if not isinstance(modules, dict) or set(modules) != set(
        SERVER_ATTESTED_MODULES
    ):
        raise ValueError("server import attestation module inventory is incomplete")
    if canonical_sha256(modules) != attestation.get("imported_modules_sha256"):
        raise ValueError("server import attestation module inventory hash differs")
    expected_runtime_modules = evaluation_manifest["runtime"].get(
        "module_files", {}
    )
    implementation_files = evaluation_manifest["implementation_files"]
    resolved_repo = repo_root.resolve(strict=True)
    for name, row in modules.items():
        if not isinstance(row, dict):
            raise ValueError(f"server import attestation module is invalid: {name}")
        path = Path(str(row.get("path", ""))).resolve(strict=True)
        observed = {
            "path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        if row != observed:
            raise ValueError(f"server import attestation module drifted: {name}")
        if name in RUNTIME_MODULES:
            if row != expected_runtime_modules.get(name):
                raise ValueError(f"server runtime module identity differs: {name}")
            continue
        try:
            relative = path.relative_to(resolved_repo).as_posix()
        except ValueError as error:
            raise ValueError(
                f"server Sim2Claw import escaped its root: {name}"
            ) from error
        expected = implementation_files.get(relative)
        if expected != {
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
        }:
            raise ValueError(f"server Sim2Claw module is not frozen: {name}")
    return {
        "path": str(resolved_attestation),
        "sha256": sha256_file(resolved_attestation),
        "canonical_payload_sha256": attestation["canonical_payload_sha256"],
        "promotion_eligible_runtime_attestation": True,
        "attestation": attestation,
    }


def validate_server_process(
    snapshot: ProcessSnapshot,
    *,
    server_script: Path,
    checkpoint_path: Path,
    host: str,
    port: int,
    checkpoint_manifest_sha256_value: str,
    checkpoint_payload_sha256_value: str,
    evaluation_manifest_path: Path,
    evaluation_manifest: dict[str, Any],
    python_executable: Path,
    processor_model_path: Path,
) -> tuple[argparse.Namespace, dict[str, Any]]:
    """Require the live argv to name the expected server, model, and digests."""

    expected_script = server_script.resolve(strict=True)
    if Path(snapshot.executable).resolve() != python_executable.resolve(strict=True):
        raise ValueError("server process uses a different Python executable")
    if len(snapshot.argv) < 3 or snapshot.argv[1] != "-u":
        raise ValueError("server command line has a noncanonical Python prefix")
    if Path(snapshot.argv[0]).resolve() != python_executable.resolve(strict=True):
        raise ValueError("server argv names a different Python executable")
    if Path(snapshot.argv[2]).resolve(strict=True) != expected_script:
        raise ValueError("server command line names a different server script")
    args = parse_seeded_server_argv(snapshot.argv[3:], require_attested=True)
    observed_model = Path(args.model_path).resolve(strict=True)
    if observed_model != checkpoint_path.resolve(strict=True):
        raise ValueError("server command line names a different checkpoint path")
    observed_processor = Path(
        args.processor_model_path
    ).resolve(strict=True)
    if observed_processor != processor_model_path.resolve(strict=True):
        raise ValueError("server command line names a different processor model")
    if args.host != host:
        raise ValueError("server command line host differs from runtime identity")
    if args.port != port:
        raise ValueError("server command line port differs from runtime identity")
    if port not in snapshot.listening_tcp_ports:
        raise ValueError("server PID does not own the declared listening port")
    if args.checkpoint_manifest_sha256 != checkpoint_manifest_sha256_value:
        raise ValueError("server command line manifest digest differs")
    if args.checkpoint_payload_sha256 != checkpoint_payload_sha256_value:
        raise ValueError("server command line checkpoint payload digest differs")
    resolved_evaluation_manifest = evaluation_manifest_path.resolve(strict=True)
    if (
        Path(args.evaluation_manifest).resolve(strict=True)
        != resolved_evaluation_manifest
    ):
        raise ValueError("server command line evaluation manifest path differs")
    if args.evaluation_manifest_sha256 != sha256_file(resolved_evaluation_manifest):
        raise ValueError("server command line evaluation manifest digest differs")
    repo_root = Path(evaluation_manifest["sim2claw_git"]["root"])
    groot_root = Path(evaluation_manifest["runtime"]["groot_git"]["root"])
    if (
        Path(args.sim2claw_root).resolve(strict=True)
        != repo_root.resolve(strict=True)
    ):
        raise ValueError("server command line Sim2Claw root differs")
    if Path(args.groot_root).resolve(strict=True) != groot_root.resolve(strict=True):
        raise ValueError("server command line GR00T root differs")
    if args.embodiment_tag != "new_embodiment" or args.device != "cuda":
        raise ValueError("server command line policy configuration differs")
    if (
        args.proposal_count != 5
        or args.action_aggregation != "median"
        or args.noise_scale != 0.5
        or args.num_inference_timesteps != 4
    ):
        raise ValueError("server command line frozen sampler configuration differs")
    if args.maximum_runtime_seconds is None or args.maximum_runtime_seconds < 1:
        raise ValueError("server command line has no bounded runtime")
    expected_environment = expected_server_environment(
        repo_root=repo_root,
        groot_root=groot_root,
        processor_model_path=processor_model_path,
    )
    if snapshot.cwd != str(groot_root.resolve(strict=True)):
        raise ValueError("server process working directory differs")
    if snapshot.environment != expected_environment:
        raise ValueError("server process import environment differs")
    if snapshot.environment_sha256 != canonical_sha256(dict(expected_environment)):
        raise ValueError("server process environment hash differs")
    attestation = _validate_server_import_attestation(
        attestation_path=Path(args.server_import_identity),
        snapshot=snapshot,
        evaluation_manifest_path=resolved_evaluation_manifest,
        evaluation_manifest=evaluation_manifest,
        server_script=expected_script,
        repo_root=repo_root,
    )
    return args, attestation


def _snapshot_payload(snapshot: ProcessSnapshot) -> dict[str, Any]:
    payload = asdict(snapshot)
    payload["argv"] = list(snapshot.argv)
    payload["environment"] = [list(row) for row in snapshot.environment]
    payload["listening_tcp_ports"] = list(snapshot.listening_tcp_ports)
    return payload


def build_runtime_identity(
    *,
    manifest_path: Path,
    checkpoint_directory: Path,
    evaluation_manifest_path: Path,
    server_script: Path,
    pid: int,
    host: str,
    port: int,
    process_snapshot: ProcessSnapshot | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Bind a reverified checkpoint payload to one exact live process."""

    checkpoint = verify_checkpoint_directory(manifest_path, checkpoint_directory)
    resolved_evaluation_manifest = evaluation_manifest_path.resolve(strict=True)
    evaluation_manifest = load_evaluation_manifest(resolved_evaluation_manifest)
    evaluation_binding = {
        "manifest_path": str(resolved_evaluation_manifest),
        "manifest_sha256": sha256_file(resolved_evaluation_manifest),
        "canonical_payload_sha256": evaluation_manifest[
            "canonical_payload_sha256"
        ],
        "implementation_inventory_sha256": evaluation_manifest[
            "implementation_inventory_sha256"
        ],
        "runtime_sha256": evaluation_manifest["runtime_sha256"],
        "runtime_assets_sha256": evaluation_manifest[
            "runtime_assets_sha256"
        ],
        "manifest": evaluation_manifest,
    }
    processor_asset = evaluation_manifest.get("runtime_assets", {}).get(
        "processor_model"
    )
    if not isinstance(processor_asset, dict):
        raise ValueError("evaluation manifest does not bind the processor model")
    snapshot = process_snapshot or read_process_snapshot(pid)
    if snapshot.pid != pid:
        raise ValueError("live process PID differs from the requested server PID")
    _, server_import_attestation = validate_server_process(
        snapshot,
        server_script=server_script,
        checkpoint_path=Path(checkpoint["checkpoint_path"]),
        host=host,
        port=port,
        checkpoint_manifest_sha256_value=checkpoint["checkpoint_manifest_sha256"],
        checkpoint_payload_sha256_value=checkpoint["checkpoint_payload_sha256"],
        evaluation_manifest_path=resolved_evaluation_manifest,
        evaluation_manifest=evaluation_manifest,
        python_executable=Path(
            evaluation_manifest["runtime"]["python"]["executable"]
        ),
        processor_model_path=Path(processor_asset["root"]),
    )
    identity = {
        "schema_version": RUNTIME_IDENTITY_SCHEMA,
        "created_at_utc": created_at_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "network": {"host": host, "port": port},
        "process": _snapshot_payload(snapshot),
        "server_script": str(server_script.resolve(strict=True)),
        "checkpoint": checkpoint,
        "evaluation_implementation": evaluation_binding,
        "server_import_attestation": server_import_attestation,
        "promotion_eligible": True,
    }
    identity["canonical_payload_sha256"] = canonical_sha256(identity)
    return identity


def write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_runtime_identity(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != RUNTIME_IDENTITY_SCHEMA:
        raise ValueError("unsupported GR00T server runtime identity")
    canonical = dict(payload)
    recorded = _require_sha256(
        canonical.pop("canonical_payload_sha256", None),
        "runtime identity canonical payload",
    )
    if canonical_sha256(canonical) != recorded:
        raise ValueError("GR00T server runtime identity canonical hash is invalid")
    return payload


def runtime_identity_receipt_binding(
    identity_path: Path,
    verified_identity: dict[str, Any],
) -> dict[str, Any]:
    """Return immutable receipt fields for an already verified live identity."""

    resolved = identity_path.resolve(strict=True)
    on_disk = load_runtime_identity(resolved)
    if on_disk != verified_identity:
        raise ValueError("verified runtime identity differs from its receipt file")
    evaluation = on_disk.get("evaluation_implementation")
    if not isinstance(evaluation, dict):
        raise ValueError("runtime identity has no evaluation implementation binding")
    server_import = on_disk.get("server_import_attestation")
    if not isinstance(server_import, dict):
        raise ValueError("runtime identity has no server import attestation")
    return {
        "server_runtime_identity_path": str(resolved),
        "server_runtime_identity_sha256": sha256_file(resolved),
        "server_runtime_identity_canonical_sha256": on_disk[
            "canonical_payload_sha256"
        ],
        "server_runtime_identity": on_disk,
        "evaluation_implementation_manifest_sha256": evaluation[
            "manifest_sha256"
        ],
        "evaluation_implementation_manifest_canonical_sha256": evaluation[
            "canonical_payload_sha256"
        ],
        "evaluation_implementation_inventory_sha256": evaluation[
            "implementation_inventory_sha256"
        ],
        "evaluation_runtime_sha256": evaluation["runtime_sha256"],
        "evaluation_runtime_assets_sha256": evaluation[
            "runtime_assets_sha256"
        ],
        "server_import_attestation_sha256": server_import["sha256"],
        "server_import_attestation_canonical_sha256": server_import[
            "canonical_payload_sha256"
        ],
        "promotion_eligible_runtime_attestation": server_import[
            "promotion_eligible_runtime_attestation"
        ],
    }


def _snapshot_from_payload(payload: dict[str, Any]) -> ProcessSnapshot:
    return ProcessSnapshot(
        pid=int(payload["pid"]),
        process_start_ticks=int(payload["process_start_ticks"]),
        boot_id=str(payload["boot_id"]),
        executable=str(payload["executable"]),
        cwd=str(payload["cwd"]),
        argv=tuple(str(value) for value in payload["argv"]),
        cmdline_sha256=_require_sha256(
            payload["cmdline_sha256"], "runtime process command line"
        ),
        environment=tuple(
            (str(row[0]), None if row[1] is None else str(row[1]))
            for row in payload["environment"]
        ),
        environment_sha256=_require_sha256(
            payload["environment_sha256"], "runtime process environment"
        ),
        listening_tcp_ports=tuple(
            int(value) for value in payload["listening_tcp_ports"]
        ),
    )


def verify_runtime_identity(
    identity_path: Path,
    *,
    expected_manifest_path: Path,
    expected_evaluation_manifest_path: Path,
    expected_host: str,
    expected_port: int,
    process_reader: Callable[[int], ProcessSnapshot] = read_process_snapshot,
) -> dict[str, Any]:
    """Revalidate the identity, manifest, and live process before inference."""

    identity = load_runtime_identity(identity_path.resolve(strict=True))
    network = identity.get("network")
    if network != {"host": expected_host, "port": expected_port}:
        raise ValueError("runtime identity host or port differs from the rollout")

    expected_manifest = expected_manifest_path.resolve(strict=True)
    manifest = load_checkpoint_manifest(expected_manifest)
    checkpoint = identity.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("runtime identity has no checkpoint binding")
    if (
        Path(checkpoint.get("checkpoint_manifest_path", "")).resolve()
        != expected_manifest
    ):
        raise ValueError("runtime identity names a different checkpoint manifest")
    if checkpoint.get("checkpoint_manifest_sha256") != sha256_file(expected_manifest):
        raise ValueError("runtime identity checkpoint manifest hash differs")
    if checkpoint.get("checkpoint_payload_sha256") != checkpoint_payload_sha256(
        manifest
    ):
        raise ValueError("runtime identity checkpoint payload hash differs")
    manifest_checkpoint_path = Path(manifest["checkpoint_path"]).resolve(strict=True)
    if (
        Path(checkpoint.get("checkpoint_path", "")).resolve(strict=True)
        != manifest_checkpoint_path
    ):
        raise ValueError("runtime identity names a different checkpoint directory")
    current_checkpoint = verify_checkpoint_directory(
        expected_manifest,
        manifest_checkpoint_path,
    )
    if current_checkpoint != checkpoint:
        raise ValueError("runtime identity checkpoint directory revalidation differs")

    expected_evaluation_manifest = expected_evaluation_manifest_path.resolve(
        strict=True
    )
    evaluation_manifest = load_evaluation_manifest(expected_evaluation_manifest)
    processor_asset = evaluation_manifest.get("runtime_assets", {}).get(
        "processor_model"
    )
    if not isinstance(processor_asset, dict):
        raise ValueError("evaluation manifest does not bind the processor model")
    observed_processor_asset = runtime_asset_inventory(
        Path(processor_asset["root"])
    )
    if observed_processor_asset != processor_asset:
        raise ValueError("runtime identity processor directory revalidation differs")
    evaluation_binding = identity.get("evaluation_implementation")
    if not isinstance(evaluation_binding, dict):
        raise ValueError("runtime identity has no evaluation implementation binding")
    if (
        Path(evaluation_binding.get("manifest_path", "")).resolve()
        != expected_evaluation_manifest
    ):
        raise ValueError("runtime identity names a different evaluation manifest")
    if evaluation_binding.get("manifest_sha256") != sha256_file(
        expected_evaluation_manifest
    ):
        raise ValueError("runtime identity evaluation manifest hash differs")
    if evaluation_binding.get("manifest") != evaluation_manifest:
        raise ValueError("runtime identity embedded evaluation manifest differs")

    recorded_snapshot = _snapshot_from_payload(identity["process"])
    try:
        live_snapshot = process_reader(recorded_snapshot.pid)
    except (OSError, ValueError) as error:
        raise ValueError("runtime identity server PID is not live") from error
    if live_snapshot != recorded_snapshot:
        raise ValueError(
            "live server PID, start time, executable, or command line drifted"
        )
    _, server_import_attestation = validate_server_process(
        live_snapshot,
        server_script=Path(identity["server_script"]),
        checkpoint_path=manifest_checkpoint_path,
        host=expected_host,
        port=expected_port,
        checkpoint_manifest_sha256_value=checkpoint["checkpoint_manifest_sha256"],
        checkpoint_payload_sha256_value=checkpoint["checkpoint_payload_sha256"],
        evaluation_manifest_path=expected_evaluation_manifest,
        evaluation_manifest=evaluation_manifest,
        python_executable=Path(
            evaluation_manifest["runtime"]["python"]["executable"]
        ),
        processor_model_path=Path(processor_asset["root"]),
    )
    if identity.get("server_import_attestation") != server_import_attestation:
        raise ValueError("runtime identity server import attestation differs")
    if identity.get("promotion_eligible") is not True:
        raise ValueError("runtime identity is not promotion eligible")
    return identity


def wait_for_server(*, pid: int, host: str, port: int, timeout_seconds: float) -> None:
    # Host remains part of the argv/runtime check; procfs proves port ownership.
    del host
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            snapshot = read_process_snapshot(pid)
        except (OSError, ValueError) as error:
            raise RuntimeError("GR00T server exited before binding its port") from error
        if port in snapshot.listening_tcp_ports:
            return
        time.sleep(0.1)
    raise TimeoutError("GR00T server did not bind before the launch deadline")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("checkpoint-preflight")
    preflight.add_argument("--manifest", type=Path, required=True)
    preflight.add_argument("--checkpoint", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)

    wait = subparsers.add_parser("wait")
    wait.add_argument("--pid", type=int, required=True)
    wait.add_argument("--host", required=True)
    wait.add_argument("--port", type=int, required=True)
    wait.add_argument("--timeout-seconds", type=float, default=300.0)

    emit = subparsers.add_parser("emit")
    emit.add_argument("--manifest", type=Path, required=True)
    emit.add_argument("--checkpoint", type=Path, required=True)
    emit.add_argument("--evaluation-manifest", type=Path, required=True)
    emit.add_argument("--server-script", type=Path, required=True)
    emit.add_argument("--pid", type=int, required=True)
    emit.add_argument("--host", required=True)
    emit.add_argument("--port", type=int, required=True)
    emit.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--identity", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--evaluation-manifest", type=Path, required=True)
    verify.add_argument("--host", required=True)
    verify.add_argument("--port", type=int, required=True)

    args = parser.parse_args()
    if args.command == "checkpoint-preflight":
        payload = verify_checkpoint_directory(args.manifest, args.checkpoint)
        payload["canonical_payload_sha256"] = canonical_sha256(payload)
        write_json_exclusive(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command == "wait":
        wait_for_server(
            pid=args.pid,
            host=args.host,
            port=args.port,
            timeout_seconds=args.timeout_seconds,
        )
        return
    if args.command == "emit":
        payload = build_runtime_identity(
            manifest_path=args.manifest,
            checkpoint_directory=args.checkpoint,
            evaluation_manifest_path=args.evaluation_manifest,
            server_script=args.server_script,
            pid=args.pid,
            host=args.host,
            port=args.port,
        )
        write_json_exclusive(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command == "verify":
        payload = verify_runtime_identity(
            args.identity,
            expected_manifest_path=args.manifest,
            expected_evaluation_manifest_path=args.evaluation_manifest,
            expected_host=args.host,
            expected_port=args.port,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
