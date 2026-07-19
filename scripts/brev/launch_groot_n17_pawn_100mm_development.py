#!/usr/bin/env python3
"""Fail-closed orchestration for the one frozen pawn GR00T rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def checkpoint_manifest(checkpoint: Path) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for path in sorted(
        (path for path in checkpoint.rglob("*") if path.is_file()),
        key=lambda item: item.relative_to(checkpoint).as_posix(),
    ):
        rows.append(
            {
                "path": path.relative_to(checkpoint).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return canonical_sha256(rows), rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def wait_for_server(process: subprocess.Popen[bytes], log_path: Path, host: str, port: int) -> None:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"policy server exited before readiness: {process.returncode}")
        marker = b"Seeded-reset GR00T server ready"
        marker_ready = log_path.exists() and marker in log_path.read_bytes()
        socket_ready = False
        if marker_ready:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    socket_ready = True
            except OSError:
                pass
        if marker_ready and socket_ready:
            return
        time.sleep(0.25)
    raise TimeoutError("policy server did not become socket-ready")


def validate_geometry(repo: Path, contract: dict[str, Any]) -> None:
    manifest_path = repo / contract["identities"]["geometry_manifest_path"]
    if sha256_file(manifest_path) != contract["identities"]["geometry_manifest_sha256"]:
        raise SystemExit("runtime geometry manifest drifted")
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["inventory"]) != 19 or manifest["xml_mesh_reference_count"] != 18:
        raise SystemExit("runtime geometry inventory count drifted")
    xml_path = repo / manifest["xml_path"]
    references = sorted(set(re.findall(r'file="([^"]+)"', xml_path.read_text())))
    if len(references) != 18:
        raise SystemExit("SO-101 XML mesh references drifted")
    referenced_paths = {
        (Path(manifest["xml_path"]).parent / "assets" / name).as_posix()
        for name in references
    }
    inventory_paths = {row["path"] for row in manifest["inventory"]}
    if referenced_paths != inventory_paths - {manifest["xml_path"]}:
        raise SystemExit("runtime mesh inventory differs from XML references")
    for row in manifest["inventory"]:
        path = repo / row["path"]
        if path.stat().st_size != int(row["size"]):
            raise SystemExit(f"runtime asset size drifted: {row['path']}")
        if sha256_file(path) != row["sha256"]:
            raise SystemExit(f"runtime asset bytes drifted: {row['path']}")


def validate_inputs(contract_path: Path, expected_hash: str) -> dict[str, Any]:
    if sha256_file(contract_path) != expected_hash:
        raise SystemExit("development contract hash drifted")
    contract = json.loads(contract_path.read_text())
    repo = Path(contract["runtime"]["repo_root"])
    if sha256_file(Path(__file__).resolve()) != contract["identities"]["orchestrator_sha256"]:
        raise SystemExit("development orchestrator drifted")
    for relative, expected in contract["identities"]["repo_file_sha256"].items():
        if sha256_file(repo / relative) != expected:
            raise SystemExit(f"development implementation drifted: {relative}")
    validate_geometry(repo, contract)

    selector_path = Path(contract["selector"]["receipt_path"])
    if sha256_file(selector_path) != contract["selector"]["receipt_sha256"]:
        raise SystemExit("selector receipt drifted")
    selector = json.loads(selector_path.read_text())
    selected = contract["selected_checkpoint"]
    for key, expected in (
        ("contract_sha256", contract["identities"]["selector_contract_sha256"]),
        ("experiment_sha256", contract["identities"]["experiment_sha256"]),
        ("selected_checkpoint_step", selected["step"]),
        ("selected_checkpoint_path", selected["path"]),
        ("selected_checkpoint_manifest_sha256", selected["manifest_sha256"]),
        ("held_out_rows_used", 0),
    ):
        if selector.get(key) != expected:
            raise SystemExit(f"selector receipt field drifted: {key}")
    manifest_sha, manifest = checkpoint_manifest(Path(selected["path"]))
    if manifest_sha != selected["manifest_sha256"] or len(manifest) != 16:
        raise SystemExit("selected checkpoint manifest drifted")

    groot_root = Path(contract["runtime"]["groot_root"])
    head = subprocess.check_output(
        ["git", "-C", str(groot_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != contract["identities"]["nvidia_commit"]:
        raise SystemExit("NVIDIA source commit drifted")
    dirty = subprocess.check_output(
        [
            "git", "-C", str(groot_root), "status", "--porcelain=v1",
            "--untracked-files=no",
        ],
        text=True,
    ).rstrip("\n")
    if dirty != contract["runtime"]["expected_nvidia_tracked_dirtiness"]:
        raise SystemExit("NVIDIA tracked dirtiness drifted")
    processor_module = groot_root / "gr00t/model/gr00t_n1d7/processing_gr00t_n1d7.py"
    if sha256_file(processor_module) != contract["identities"]["patched_processor_sha256"]:
        raise SystemExit("NVIDIA processor patch drifted")
    if not Path(contract["runtime"]["processor_path"]).is_dir():
        raise SystemExit("offline processor snapshot is missing")
    mujoco_version = subprocess.check_output(
        [sys.executable, "-c", "import mujoco; print(mujoco.__version__)"],
        text=True,
    ).strip()
    if mujoco_version != contract["runtime"]["mujoco_version"]:
        raise SystemExit("MuJoCo runtime version drifted")
    if not Path("/usr/bin/ffmpeg").is_file():
        raise SystemExit("frozen rollout video encoder is missing")

    output = Path(contract["rollout"]["output_directory"])
    if output.exists():
        raise SystemExit("development output already exists")
    if not port_is_free(contract["server"]["host"], int(contract["server"]["port"])):
        raise SystemExit("policy-server port is already occupied")
    gpu_processes = subprocess.check_output(
        [
            "nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"
        ],
        text=True,
    ).strip()
    if gpu_processes:
        raise SystemExit("another GPU process is active before development launch")
    return contract


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    contract = validate_inputs(args.contract, args.expected_contract_sha256)
    if args.preflight_only:
        print("pawn GR00T development no-query preflight passed")
        return 0
    repo = Path(contract["runtime"]["repo_root"])
    evidence = Path(contract["rollout"]["evidence_directory"])
    evidence.mkdir(parents=True, exist_ok=False)
    output = Path(contract["rollout"]["output_directory"])
    host, port = contract["server"]["host"], int(contract["server"]["port"])
    selected = contract["selected_checkpoint"]
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(repo / "src"),
            "GROOT_PROCESSOR_MODEL_PATH": contract["runtime"]["processor_path"],
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "NO_ALBUMENTATIONS_UPDATE": "1",
            "MUJOCO_GL": "osmesa",
            "PYOPENGL_PLATFORM": "osmesa",
        }
    )
    server_script = repo / "scripts/brev/run_groot_n17_chess_seeded_server.py"
    server_command = [
        sys.executable, "-u", str(server_script),
        "--model-path", selected["path"],
        "--embodiment-tag", "new_embodiment",
        "--device", "cuda",
        "--host", host,
        "--port", str(port),
        "--proposal-count", "5",
        "--action-aggregation", "median",
        "--noise-scale", "0.5",
        "--num-inference-timesteps", "4",
    ]
    server_log_path = evidence / "server.log"
    server_log = server_log_path.open("wb")
    server = subprocess.Popen(
        server_command,
        cwd=contract["runtime"]["groot_root"],
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    server_exit: int | None = None
    try:
        wait_for_server(server, server_log_path, host, port)
        runtime_receipt = {
            "schema_version": "sim2claw.groot_n17_pawn_server_runtime.v1",
            "contract_sha256": args.expected_contract_sha256,
            "pid": server.pid,
            "command": server_command,
            "cwd": contract["runtime"]["groot_root"],
            "environment": {key: env[key] for key in (
                "PYTHONPATH", "GROOT_PROCESSOR_MODEL_PATH", "HF_HUB_OFFLINE",
                "TRANSFORMERS_OFFLINE", "MUJOCO_GL", "PYOPENGL_PLATFORM",
            )},
            "checkpoint_manifest_sha256": selected["manifest_sha256"],
            "ready_prefix_log_sha256": sha256_file(server_log_path),
        }
        runtime_path = evidence / "server_runtime_receipt.json"
        write_json(runtime_path, runtime_receipt)

        runner_command = [
            sys.executable,
            str(repo / "scripts/brev/run_groot_n17_pawn_100mm_development.py"),
            "--host", host,
            "--port", str(port),
            "--checkpoint-id", f"checkpoint-{selected['step']}",
            "--checkpoint-manifest-sha256", selected["manifest_sha256"],
            "--selector-receipt-sha256", contract["selector"]["receipt_sha256"],
            "--experiment-sha256", contract["identities"]["experiment_sha256"],
            "--inference-seed", "0",
            "--output", str(output),
        ]
        runner_log_path = evidence / "runner.log"
        with runner_log_path.open("wb") as runner_log:
            completed = subprocess.run(
                runner_command,
                cwd=repo,
                env=env,
                stdout=runner_log,
                stderr=subprocess.STDOUT,
                timeout=int(contract["rollout"]["maximum_runtime_seconds"]),
                check=False,
            )
        (evidence / "runner_exit_code.txt").write_text(f"{completed.returncode}\n")
        if completed.returncode != 0:
            raise RuntimeError(f"pawn development runner exited {completed.returncode}")
    finally:
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=10)
        server_exit = server.returncode
        server_log.close()
        write_json(
            evidence / "server_exit_receipt.json",
            {
                "schema_version": "sim2claw.groot_n17_pawn_server_exit.v1",
                "pid": server.pid,
                "returncode": server_exit,
                "final_server_log_sha256": sha256_file(server_log_path),
                "server_stopped": server.poll() is not None,
            },
        )

    evaluator_output = output / "evaluation_receipt.json"
    evaluator_command = [
        sys.executable,
        str(repo / "scripts/brev/evaluate_groot_n17_pawn_100mm_development.py"),
        "--rollout", str(output),
        "--output", str(evaluator_output),
    ]
    evaluator_log_path = evidence / "evaluator.log"
    with evaluator_log_path.open("wb") as evaluator_log:
        evaluated = subprocess.run(
            evaluator_command,
            cwd=repo,
            env=env,
            stdout=evaluator_log,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False,
        )
    (evidence / "evaluator_exit_code.txt").write_text(f"{evaluated.returncode}\n")
    if evaluated.returncode != 0:
        raise RuntimeError(f"pawn evaluator exited {evaluated.returncode}")
    evaluation = json.loads(evaluator_output.read_text())
    summary = {
        "schema_version": "sim2claw.groot_n17_pawn_100mm_development_summary.v1",
        "contract_sha256": args.expected_contract_sha256,
        "selector_receipt_sha256": contract["selector"]["receipt_sha256"],
        "checkpoint_manifest_sha256": selected["manifest_sha256"],
        "rollout_receipt_sha256": sha256_file(output / "rollout_receipt.json"),
        "evaluation_receipt_sha256": sha256_file(evaluator_output),
        "strict_success": bool(evaluation["strict_success"]),
        "failed_gates": evaluation["failed_gates"],
        "held_out_rows_used": 0,
        "physical_reach_authority": False,
        "rank_1_2_generalization_authority": False,
        "server_stopped": True,
    }
    summary_path = evidence / "summary.json"
    write_json(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
