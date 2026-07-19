"""Freeze the implementation and software runtime used by a GR00T evaluator."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


EVALUATION_MANIFEST_SCHEMA = "sim2claw.groot_evaluation_implementation.v1"
EVALUATION_IMPLEMENTATION_PATHS = (
    "scripts/brev/launch_groot_n17_multisource_eval_server.sh",
    "scripts/brev/run_groot_n17_chess_seeded_server.py",
    "scripts/brev/run_groot_n17_pawn_closed_loop.py",
    "src/sim2claw/capture.py",
    "src/sim2claw/chess_task.py",
    "src/sim2claw/grasp.py",
    "src/sim2claw/groot_chess.py",
    "src/sim2claw/groot_consensus.py",
    "src/sim2claw/groot_evaluation_identity.py",
    "src/sim2claw/groot_execution.py",
    "src/sim2claw/gltf.py",
    "src/sim2claw/groot_rollout_trace.py",
    "src/sim2claw/groot_server_identity.py",
    "src/sim2claw/mass_profile.py",
    "src/sim2claw/paths.py",
    "src/sim2claw/pawn_source_evaluator.py",
    "src/sim2claw/render.py",
    "src/sim2claw/scene.py",
    "src/sim2claw/source_episode.py",
    "src/sim2claw/state_trace.py",
    "configs/experiments/groot_n17_multisource_v2.json",
    "configs/polycam/8873B66C-774C-48B1-B51D-338645867009.json",
    "configs/tasks/chess_pick_place_pawn_evaluator_v3.json",
    "configs/tasks/chess_pick_place_source_episode_v3.json",
    "calibration/so101/follower_mass_profile_v1.json",
    "third_party/mujoco_menagerie/robotstudio_so101",
)
RUNTIME_MODULES = (
    "mujoco",
    "mujoco._functions",
    "mujoco._structs",
    "numpy",
    "torch",
    "gr00t",
    "gr00t.data.types",
    "gr00t.policy.gr00t_policy",
    "gr00t.policy.policy",
    "gr00t.policy.server_client",
)


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


def _git(args: list[str], root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_bytes(args: list[str], root: Path) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    ).stdout


def git_identity(root: Path, *, require_clean: bool) -> dict[str, Any]:
    resolved = root.resolve(strict=True)
    commit = _git(["rev-parse", "HEAD"], resolved)
    tree = _git(["rev-parse", "HEAD^{tree}"], resolved)
    status = _git(["status", "--porcelain=v1", "--untracked-files=no"], resolved)
    tracked_diff = _git_bytes(["diff", "--binary", "HEAD", "--"], resolved)
    if require_clean and status:
        raise ValueError(f"Git worktree must be clean for evaluation: {resolved}")
    return {
        "root": str(resolved),
        "commit": commit,
        "tree": tree,
        "tracked_status": status.splitlines(),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "tracked_diff_size_bytes": len(tracked_diff),
        "clean": not bool(status),
    }


def implementation_inventory(
    repo_root: Path,
    paths: Iterable[str] = EVALUATION_IMPLEMENTATION_PATHS,
) -> dict[str, dict[str, Any]]:
    root = repo_root.resolve(strict=True)
    inventory: dict[str, dict[str, Any]] = {}
    for relative_text in paths:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid evaluation implementation path: {relative}")
        source = (root / relative).resolve(strict=True)
        candidates = [source] if source.is_file() else sorted(source.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            candidate_relative = candidate.relative_to(root).as_posix()
            if candidate_relative in inventory:
                continue
            inventory[candidate_relative] = {
                "sha256": sha256_file(candidate),
                "size_bytes": candidate.stat().st_size,
            }
    if not inventory:
        raise ValueError("evaluation implementation inventory is empty")
    return dict(sorted(inventory.items()))


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_package_inventory(root: Path) -> dict[str, Any]:
    """Hash a runtime package tree while excluding interpreter caches."""

    resolved = root.resolve(strict=True)
    files = {
        path.relative_to(resolved).as_posix(): {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(resolved.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    if not files:
        raise ValueError(f"runtime package inventory is empty: {resolved}")
    return {
        "root": str(resolved),
        "files": files,
        "inventory_sha256": canonical_sha256(files),
    }


def runtime_asset_inventory(path: Path) -> dict[str, Any]:
    """Hash an external model/runtime asset tree, including symlink identity."""

    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"runtime asset is not a directory: {root}")
    rows: list[dict[str, Any]] = []
    for entry in sorted(
        root.rglob("*"),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    ):
        if entry.is_dir():
            continue
        if entry.is_symlink() and not entry.exists():
            raise ValueError(f"runtime asset has a broken symlink: {entry}")
        if not entry.is_file():
            raise ValueError(f"runtime asset has an unsupported entry: {entry}")
        rows.append(
            {
                "path": entry.relative_to(root).as_posix(),
                "size_bytes": entry.stat().st_size,
                "sha256": sha256_file(entry),
                "is_symlink": entry.is_symlink(),
                "symlink_target": (
                    entry.readlink().as_posix() if entry.is_symlink() else None
                ),
            }
        )
    if not rows:
        raise ValueError(f"runtime asset inventory is empty: {root}")
    return {
        "root": str(root),
        "file_count": len(rows),
        "inventory": rows,
        "inventory_sha256": canonical_sha256(rows),
    }


def _runtime_asset_inventories(
    paths: Mapping[str, Path] | None,
) -> dict[str, dict[str, Any]]:
    if not paths:
        return {}
    inventories: dict[str, dict[str, Any]] = {}
    for name, path in sorted(paths.items()):
        if not name or not name.replace("_", "").isalnum():
            raise ValueError(f"invalid runtime asset name: {name}")
        inventories[name] = runtime_asset_inventory(path)
    return inventories


def _parse_runtime_assets(values: list[str]) -> dict[str, Path]:
    parsed: dict[str, Path] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path or name in parsed:
            raise ValueError(f"invalid or duplicate runtime asset: {value}")
        parsed[name] = Path(path)
    return parsed


def runtime_identity(groot_root: Path) -> dict[str, Any]:
    imported = {
        module_name: importlib.import_module(module_name)
        for module_name in RUNTIME_MODULES
    }
    module_files: dict[str, dict[str, Any]] = {}
    for module_name in RUNTIME_MODULES:
        module = imported[module_name]
        origin = getattr(module, "__file__", None)
        if origin is None:
            raise ValueError(
                f"runtime module has no import identity: {module_name}"
            )
        path = Path(origin).resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"runtime module has no import identity: {module_name}")
        module_files[module_name] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }

    mujoco = imported["mujoco"]
    numpy = imported["numpy"]
    torch = imported["torch"]
    package_inventories = {
        name: runtime_package_inventory(
            Path(imported[name].__file__).resolve(strict=True).parent
        )
        for name in ("mujoco", "gr00t")
    }
    groot_version = _distribution_version("gr00t") or _distribution_version(
        "nvidia-gr00t"
    )
    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": str(Path(sys.executable).resolve(strict=True)),
            "executable_sha256": sha256_file(Path(sys.executable).resolve(strict=True)),
        },
        "packages": {
            "mujoco": str(mujoco.__version__),
            "numpy": str(numpy.__version__),
            "torch": str(torch.__version__),
            "torch_cuda": str(torch.version.cuda),
            "gr00t": groot_version or "source-checkout",
        },
        "module_files": module_files,
        "package_inventories": package_inventories,
        "groot_git": git_identity(groot_root, require_clean=False),
    }


def build_evaluation_manifest(
    *,
    repo_root: Path,
    groot_root: Path,
    implementation_paths: Iterable[str] = EVALUATION_IMPLEMENTATION_PATHS,
    sim2claw_git: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    runtime_assets: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    inventory = implementation_inventory(repo_root, implementation_paths)
    asset_inventories = _runtime_asset_inventories(runtime_assets)
    manifest = {
        "schema_version": EVALUATION_MANIFEST_SCHEMA,
        "purpose": "future_learned_policy_simulation_evaluation",
        "sim2claw_git": sim2claw_git
        or git_identity(repo_root, require_clean=True),
        "implementation_files": inventory,
        "implementation_inventory_sha256": canonical_sha256(inventory),
        "runtime": runtime or runtime_identity(groot_root),
        "runtime_assets": asset_inventories,
        "runtime_assets_sha256": canonical_sha256(asset_inventories),
    }
    manifest["runtime_sha256"] = canonical_sha256(manifest["runtime"])
    manifest["canonical_payload_sha256"] = canonical_sha256(manifest)
    return manifest


def load_evaluation_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != EVALUATION_MANIFEST_SCHEMA:
        raise ValueError("unsupported GR00T evaluation implementation manifest")
    canonical = dict(manifest)
    recorded = canonical.pop("canonical_payload_sha256", None)
    if canonical_sha256(canonical) != recorded:
        raise ValueError("evaluation implementation manifest canonical hash is invalid")
    return manifest


def verify_evaluation_manifest(
    path: Path,
    *,
    repo_root: Path,
    groot_root: Path,
    implementation_paths: Iterable[str] = EVALUATION_IMPLEMENTATION_PATHS,
    sim2claw_git: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
    runtime_assets: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    manifest = load_evaluation_manifest(path.resolve(strict=True))
    observed_git = sim2claw_git or git_identity(repo_root, require_clean=True)
    if observed_git != manifest["sim2claw_git"]:
        raise ValueError("evaluation Sim2Claw Git identity drifted")
    inventory = implementation_inventory(repo_root, implementation_paths)
    if inventory != manifest["implementation_files"]:
        raise ValueError("evaluation implementation source inventory drifted")
    if canonical_sha256(inventory) != manifest["implementation_inventory_sha256"]:
        raise ValueError("evaluation implementation inventory hash is invalid")
    observed_runtime = runtime or runtime_identity(groot_root)
    if observed_runtime != manifest["runtime"]:
        raise ValueError("evaluation software runtime drifted")
    if canonical_sha256(observed_runtime) != manifest["runtime_sha256"]:
        raise ValueError("evaluation runtime hash is invalid")
    observed_assets = _runtime_asset_inventories(runtime_assets)
    if observed_assets != manifest["runtime_assets"]:
        raise ValueError("evaluation runtime asset inventory drifted")
    if canonical_sha256(observed_assets) != manifest["runtime_assets_sha256"]:
        raise ValueError("evaluation runtime asset hash is invalid")
    return manifest


def write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--repo-root", type=Path, required=True)
    freeze.add_argument("--groot-root", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--runtime-asset", action="append", default=[])
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--repo-root", type=Path, required=True)
    verify.add_argument("--groot-root", type=Path, required=True)
    verify.add_argument("--runtime-asset", action="append", default=[])
    args = parser.parse_args()
    try:
        runtime_assets = _parse_runtime_assets(args.runtime_asset)
    except ValueError as error:
        parser.error(str(error))

    if args.command == "freeze":
        payload = build_evaluation_manifest(
            repo_root=args.repo_root,
            groot_root=args.groot_root,
            runtime_assets=runtime_assets,
        )
        write_json_exclusive(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.command == "verify":
        payload = verify_evaluation_manifest(
            args.manifest,
            repo_root=args.repo_root,
            groot_root=args.groot_root,
            runtime_assets=runtime_assets,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
