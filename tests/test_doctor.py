from __future__ import annotations

import unittest

from sim2claw.doctor import nvidia_preflight_requirements


class NvidiaPreflightTest(unittest.TestCase):
    def test_nvidia_preflight_fails_closed_without_egl(self) -> None:
        checks = nvidia_preflight_requirements(
            platform_name="Linux",
            nvidia_smi_path="/usr/bin/nvidia-smi",
            mujoco_gl=None,
        )
        self.assertTrue(checks[0]["passed"])
        self.assertTrue(checks[1]["passed"])
        self.assertFalse(checks[2]["passed"])

    def test_nvidia_preflight_accepts_explicit_egl_contract(self) -> None:
        checks = nvidia_preflight_requirements(
            platform_name="Linux",
            nvidia_smi_path="/usr/bin/nvidia-smi",
            mujoco_gl="egl",
        )
        self.assertTrue(all(check["passed"] for check in checks))

    def test_nvidia_preflight_accepts_jetson_device_without_nvidia_smi(self) -> None:
        checks = nvidia_preflight_requirements(
            platform_name="Linux",
            nvidia_smi_path=None,
            mujoco_gl="egl",
            jetson_gpu_path="/dev/nvidia0",
        )
        self.assertTrue(all(check["passed"] for check in checks))

    def test_nvidia_preflight_fails_without_smi_or_jetson_device(self) -> None:
        checks = nvidia_preflight_requirements(
            platform_name="Linux",
            nvidia_smi_path=None,
            mujoco_gl="egl",
            jetson_gpu_path=None,
        )
        self.assertFalse(checks[1]["passed"])


if __name__ == "__main__":
    unittest.main()

