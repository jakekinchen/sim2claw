from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import mujoco

from .render import render_scene


REQUIRED_PYTHON = (3, 12)
REQUIRED_MUJOCO = "3.10.0"


def _detect_jetson_gpu() -> str | None:
    """Jetson/Tegra boards expose their GPU via /dev/nvidia0 and never ship
    nvidia-smi. Treat that device node (backed by the Tegra release file) as
    equivalent proof of a working NVIDIA accelerator."""
    if Path("/dev/nvidia0").exists() and Path("/etc/nv_tegra_release").is_file():
        return "/dev/nvidia0"
    return None


def nvidia_preflight_requirements(
    *,
    platform_name: str,
    nvidia_smi_path: str | None,
    mujoco_gl: str | None,
    jetson_gpu_path: str | None = None,
) -> list[dict[str, Any]]:
    gpu_present = nvidia_smi_path or jetson_gpu_path
    return [
        {
            "name": "linux-host",
            "passed": platform_name == "Linux",
            "observed": platform_name,
            "required": "Linux",
        },
        {
            "name": "nvidia-gpu-present",
            "passed": bool(gpu_present),
            "observed": gpu_present,
            "required": "nvidia-smi on PATH, or /dev/nvidia0 on a Tegra/Jetson host",
        },
        {
            "name": "egl-selected",
            "passed": mujoco_gl == "egl",
            "observed": mujoco_gl,
            "required": "MUJOCO_GL=egl",
        },
    ]


def run_doctor(target: str = "auto", render_probe: bool = False) -> dict[str, Any]:
    if target not in {"auto", "mac", "nvidia", "linux-cpu"}:
        raise ValueError(f"unsupported doctor target: {target}")
    platform_name = platform.system()
    machine = platform.machine()
    if target == "auto":
        target = "mac" if platform_name == "Darwin" else "nvidia"

    checks: list[dict[str, Any]] = [
        {
            "name": "python-version",
            "passed": platform.python_version_tuple()[:2]
            == tuple(str(value) for value in REQUIRED_PYTHON),
            "observed": platform.python_version(),
            "required": "3.12.x",
        },
        {
            "name": "mujoco-version",
            "passed": mujoco.__version__ == REQUIRED_MUJOCO,
            "observed": mujoco.__version__,
            "required": REQUIRED_MUJOCO,
        },
    ]
    accelerator: dict[str, Any] = {"target": target}
    if target == "mac":
        checks.extend(
            [
                {
                    "name": "macos-host",
                    "passed": platform_name == "Darwin",
                    "observed": platform_name,
                    "required": "Darwin",
                },
                {
                    "name": "apple-silicon",
                    "passed": machine == "arm64",
                    "observed": machine,
                    "required": "arm64",
                },
            ]
        )
        accelerator["simulation"] = "CPU"
        accelerator["render"] = os.environ.get("MUJOCO_GL", "platform-default")
    elif target == "linux-cpu":
        checks.append(
            {
                "name": "linux-host",
                "passed": platform_name == "Linux",
                "observed": platform_name,
                "required": "Linux",
            }
        )
        accelerator["simulation"] = "CPU"
        accelerator["render"] = os.environ.get("MUJOCO_GL", "platform-default")
    else:
        nvidia_smi_path = shutil.which("nvidia-smi")
        jetson_gpu_path = None if nvidia_smi_path else _detect_jetson_gpu()
        checks.extend(
            nvidia_preflight_requirements(
                platform_name=platform_name,
                nvidia_smi_path=nvidia_smi_path,
                mujoco_gl=os.environ.get("MUJOCO_GL"),
                jetson_gpu_path=jetson_gpu_path,
            )
        )
        if nvidia_smi_path:
            result = subprocess.run(
                [
                    nvidia_smi_path,
                    "--query-gpu=name,driver_version",
                    "--format=csv,noheader",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            accelerator["nvidia_smi"] = result.stdout.strip() or result.stderr.strip()
        elif jetson_gpu_path:
            accelerator["jetson_gpu"] = jetson_gpu_path
            accelerator["nv_tegra_release"] = Path(
                "/etc/nv_tegra_release"
            ).read_text().strip()

    proof_artifact: str | None = None
    if render_probe and all(check["passed"] for check in checks):
        with tempfile.TemporaryDirectory(prefix="sim2claw-doctor-") as temporary:
            proof_path = Path(temporary) / "doctor.png"
            probe = render_scene(
                output_path=proof_path,
                width=160,
                height=120,
                settle_steps=2,
            )
            checks.append(
                {
                    "name": "compile-step-render",
                    "passed": proof_path.is_file() and proof_path.stat().st_size > 0,
                    "observed": probe["render"]["image_sha256"],
                    "required": "non-empty deterministic proof image",
                }
            )
            proof_artifact = "ephemeral doctor render verified"

    passed = all(check["passed"] for check in checks)
    return {
        "schema_version": 1,
        "passed": passed,
        "target": target,
        "host": {
            "platform": platform_name,
            "release": platform.release(),
            "machine": machine,
        },
        "accelerator": accelerator,
        "checks": checks,
        "render_probe": proof_artifact,
        "physical_authority": False,
    }


def format_doctor(report: dict[str, Any]) -> str:
    lines = [
        f"sim2claw doctor: {'PASS' if report['passed'] else 'FAIL'}",
        f"target: {report['target']}",
    ]
    for check in report["checks"]:
        marker = "PASS" if check["passed"] else "FAIL"
        lines.append(
            f"[{marker}] {check['name']}: {check['observed']} "
            f"(required: {check['required']})"
        )
    lines.append("physical authority: closed")
    return "\n".join(lines)


def doctor_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)
