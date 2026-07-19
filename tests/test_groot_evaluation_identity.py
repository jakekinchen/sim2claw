from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sim2claw.groot_evaluation_identity import (
    build_evaluation_manifest,
    load_evaluation_manifest,
    runtime_package_inventory,
    verify_evaluation_manifest,
    write_json_exclusive,
)


class GrootEvaluationIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "implementation.py"
        self.source.write_text("IDENTITY = 'v1'\n", encoding="utf-8")
        self.manifest_path = self.root / "evaluation-manifest.json"
        self.git_identity = {
            "root": str(self.root.resolve()),
            "commit": "1" * 40,
            "tree": "2" * 40,
            "tracked_status": [],
            "clean": True,
        }
        self.runtime = {
            "python": {"version": "3.10.0", "sha256": "3" * 64},
            "mujoco": {"version": "3.3.7", "sha256": "4" * 64},
            "gr00t": {"commit": "5" * 40, "tree": "6" * 40},
        }
        payload = build_evaluation_manifest(
            repo_root=self.root,
            groot_root=self.root,
            implementation_paths=(self.source.name,),
            sim2claw_git=self.git_identity,
            runtime=self.runtime,
        )
        write_json_exclusive(self.manifest_path, payload)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_exact_source_git_and_runtime_identity(self) -> None:
        manifest = verify_evaluation_manifest(
            self.manifest_path,
            repo_root=self.root,
            groot_root=self.root,
            implementation_paths=(self.source.name,),
            sim2claw_git=self.git_identity,
            runtime=self.runtime,
        )
        self.assertEqual(manifest, load_evaluation_manifest(self.manifest_path))

    def test_rejects_source_payload_drift(self) -> None:
        self.source.write_text("IDENTITY = 'v2'\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source inventory drifted"):
            verify_evaluation_manifest(
                self.manifest_path,
                repo_root=self.root,
                groot_root=self.root,
                implementation_paths=(self.source.name,),
                sim2claw_git=self.git_identity,
                runtime=self.runtime,
            )

    def test_rejects_manifest_tamper(self) -> None:
        payload = load_evaluation_manifest(self.manifest_path)
        payload["purpose"] = "tampered"
        self.manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "canonical hash"):
            load_evaluation_manifest(self.manifest_path)

    def test_refuses_manifest_overwrite(self) -> None:
        payload = load_evaluation_manifest(self.manifest_path)
        with self.assertRaises(FileExistsError):
            write_json_exclusive(self.manifest_path, payload)

    def test_runtime_package_inventory_hashes_files_but_not_caches(self) -> None:
        package = self.root / "package"
        package.mkdir()
        (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        cache = package / "__pycache__"
        cache.mkdir()
        (cache / "module.pyc").write_bytes(b"cache")
        inventory = runtime_package_inventory(package)
        self.assertEqual(set(inventory["files"]), {"module.py"})
        original_hash = inventory["inventory_sha256"]
        (package / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
        self.assertNotEqual(
            original_hash,
            runtime_package_inventory(package)["inventory_sha256"],
        )

    def test_rejects_external_runtime_asset_drift(self) -> None:
        asset = self.root / "processor-model"
        asset.mkdir()
        model_file = asset / "config.json"
        model_file.write_text("{}\n", encoding="utf-8")
        path = self.root / "asset-bound-manifest.json"
        payload = build_evaluation_manifest(
            repo_root=self.root,
            groot_root=self.root,
            implementation_paths=(self.source.name,),
            sim2claw_git=self.git_identity,
            runtime=self.runtime,
            runtime_assets={"processor_model": asset},
        )
        write_json_exclusive(path, payload)
        model_file.write_text('{"tampered":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "runtime asset inventory drifted"):
            verify_evaluation_manifest(
                path,
                repo_root=self.root,
                groot_root=self.root,
                implementation_paths=(self.source.name,),
                sim2claw_git=self.git_identity,
                runtime=self.runtime,
                runtime_assets={"processor_model": asset},
            )


if __name__ == "__main__":
    unittest.main()
