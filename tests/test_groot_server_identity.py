from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from sim2claw.groot_evaluation_identity import (
    RUNTIME_MODULES,
    SERVER_ATTESTED_MODULES,
    SERVER_IMPORT_ATTESTATION_SCHEMA,
    build_evaluation_manifest,
    validate_server_sys_path_prefix,
)
from sim2claw.groot_server_identity import (
    CHECKPOINT_MANIFEST_SCHEMA,
    ProcessSnapshot,
    build_runtime_identity,
    canonical_sha256,
    checkpoint_payload_sha256,
    expected_server_environment,
    load_checkpoint_manifest,
    runtime_identity_receipt_binding,
    sha256_file,
    verify_checkpoint_directory,
    verify_runtime_identity,
    write_json_exclusive,
)


class GrootServerRuntimeIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.checkpoint = self.root / "checkpoint-1000"
        self.checkpoint.mkdir()
        (self.checkpoint / "config.json").write_bytes(b"config-v1")
        (self.checkpoint / "model-00001-of-00001.safetensors").write_bytes(
            b"model-weights-v1"
        )
        files = {
            path.name: sha256_file(path)
            for path in sorted(self.checkpoint.iterdir())
        }
        sizes = {
            path.name: path.stat().st_size
            for path in sorted(self.checkpoint.iterdir())
        }
        self.manifest = self.root / "checkpoint-1000-manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": CHECKPOINT_MANIFEST_SCHEMA,
                    "checkpoint_step": 1000,
                    "checkpoint_path": str(self.checkpoint.resolve()),
                    "files": files,
                    "file_sizes_bytes": sizes,
                    "file_count": len(files),
                    "total_size_bytes": sum(sizes.values()),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.server_script = self.root / "run_groot_n17_chess_seeded_server.py"
        self.server_script.write_text("# hermetic server fixture\n", encoding="utf-8")
        self.sim2claw_modules: dict[str, Path] = {}
        package = self.root / "src" / "sim2claw"
        package.mkdir(parents=True)
        for module_name in SERVER_ATTESTED_MODULES:
            if not module_name.startswith("sim2claw."):
                continue
            path = package / f"{module_name.rsplit('.', 1)[1]}.py"
            path.write_text(f"# {module_name}\n", encoding="utf-8")
            self.sim2claw_modules[module_name] = path
        self.runtime_module = self.root / "runtime_module.py"
        self.runtime_module.write_text("RUNTIME = 'v1'\n", encoding="utf-8")
        runtime_row = self._file_row(self.runtime_module)
        runtime_modules = {name: dict(runtime_row) for name in RUNTIME_MODULES}
        self.processor_model = self.root / "processor-model"
        self.processor_model.mkdir()
        (self.processor_model / "config.json").write_text("{}\n", encoding="utf-8")
        self.evaluation_manifest = self.root / "evaluation-manifest.json"
        implementation_paths = (
            self.server_script.name,
            *(path.relative_to(self.root).as_posix() for path in self.sim2claw_modules.values()),
        )
        evaluation_payload = build_evaluation_manifest(
            repo_root=self.root,
            groot_root=self.root,
            implementation_paths=implementation_paths,
            sim2claw_git={
                "root": str(self.root.resolve()),
                "commit": "1" * 40,
                "tree": "2" * 40,
                "tracked_status": [],
                "tracked_diff_sha256": "0" * 64,
                "tracked_diff_size_bytes": 0,
                "clean": True,
            },
            runtime={
                "python": {
                    "version": "3.10.13",
                    "executable": str(Path("/usr/bin/python3").resolve()),
                    "executable_sha256": "3" * 64,
                },
                "module_files": runtime_modules,
                "groot_git": {
                    "root": str(self.root.resolve()),
                    "commit": "4" * 40,
                    "tree": "5" * 40,
                    "tracked_status": [],
                    "clean": True,
                },
            },
            runtime_assets={"processor_model": self.processor_model},
        )
        write_json_exclusive(self.evaluation_manifest, evaluation_payload)
        self.attestation_path = self.root / "server-import-attestation.json"
        manifest_payload = load_checkpoint_manifest(self.manifest)
        self.argv = (
            str(Path("/usr/bin/python3").resolve()),
            "-u",
            str(self.server_script.resolve()),
            "--model-path",
            str(self.checkpoint.resolve()),
            "--processor-model-path",
            str(self.processor_model.resolve()),
            "--embodiment-tag",
            "new_embodiment",
            "--device",
            "cuda",
            "--host",
            "127.0.0.1",
            "--port",
            "5555",
            "--proposal-count",
            "5",
            "--action-aggregation",
            "median",
            "--noise-scale",
            "0.5",
            "--num-inference-timesteps",
            "4",
            "--checkpoint-manifest-sha256",
            sha256_file(self.manifest),
            "--checkpoint-payload-sha256",
            checkpoint_payload_sha256(manifest_payload),
            "--evaluation-manifest",
            str(self.evaluation_manifest.resolve()),
            "--evaluation-manifest-sha256",
            sha256_file(self.evaluation_manifest),
            "--sim2claw-root",
            str(self.root.resolve()),
            "--groot-root",
            str(self.root.resolve()),
            "--server-import-identity",
            str(self.attestation_path.resolve()),
            "--maximum-runtime-seconds",
            "3600",
        )
        self.snapshot = self._snapshot(self.argv)
        write_json_exclusive(self.attestation_path, self._attestation(self.snapshot))
        self.identity_path = self.root / "runtime-identity.json"
        identity = self._build(self.snapshot)
        write_json_exclusive(self.identity_path, identity)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _file_row(path: Path) -> dict[str, object]:
        return {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }

    def _snapshot(
        self,
        argv: tuple[str, ...],
        *,
        pid: int = 4242,
    ) -> ProcessSnapshot:
        raw_cmdline = b"\0".join(value.encode() for value in argv) + b"\0"
        environment = expected_server_environment(
            repo_root=self.root,
            groot_root=self.root,
            processor_model_path=self.processor_model,
        )
        return ProcessSnapshot(
            pid=pid,
            process_start_ticks=987654,
            boot_id="00000000-1111-2222-3333-444444444444",
            executable=str(Path("/usr/bin/python3").resolve()),
            cwd=str(self.root.resolve()),
            argv=argv,
            cmdline_sha256=hashlib.sha256(raw_cmdline).hexdigest(),
            environment=environment,
            environment_sha256=canonical_sha256(dict(environment)),
            listening_tcp_ports=(5555,),
        )

    def _attestation(self, snapshot: ProcessSnapshot) -> dict[str, object]:
        evaluation = json.loads(self.evaluation_manifest.read_text(encoding="utf-8"))
        modules = {
            name: (
                self._file_row(self.runtime_module)
                if name in RUNTIME_MODULES
                else self._file_row(self.sim2claw_modules[name])
            )
            for name in SERVER_ATTESTED_MODULES
        }
        payload: dict[str, object] = {
            "schema_version": SERVER_IMPORT_ATTESTATION_SCHEMA,
            "created_at_utc": "2026-07-19T12:00:00Z",
            "promotion_eligible_runtime_attestation": True,
            "process": {
                "pid": snapshot.pid,
                "executable": snapshot.executable,
                "cwd": snapshot.cwd,
                "argv": list(snapshot.argv),
                "sys_path": [
                    str(self.server_script.resolve().parent),
                    str(self.root.resolve() / "src"),
                    "/hermetic/python310/stdlib",
                    "/hermetic/python310/site-packages",
                ],
                "environment": dict(snapshot.environment),
            },
            "server_script": self._file_row(self.server_script),
            "evaluation_implementation": {
                "manifest_path": str(self.evaluation_manifest.resolve()),
                "manifest_sha256": sha256_file(self.evaluation_manifest),
                "canonical_payload_sha256": evaluation["canonical_payload_sha256"],
                "implementation_inventory_sha256": evaluation[
                    "implementation_inventory_sha256"
                ],
                "runtime_sha256": evaluation["runtime_sha256"],
                "runtime_assets_sha256": evaluation["runtime_assets_sha256"],
            },
            "imported_modules": modules,
            "imported_modules_sha256": canonical_sha256(modules),
        }
        payload["server_script"] = {
            "path": str(self.server_script.resolve()),
            "sha256": sha256_file(self.server_script),
            "size_bytes": self.server_script.stat().st_size,
        }
        payload["canonical_payload_sha256"] = canonical_sha256(payload)
        return payload

    def _build(self, snapshot: ProcessSnapshot) -> dict[str, object]:
        return build_runtime_identity(
            manifest_path=self.manifest,
            checkpoint_directory=self.checkpoint,
            evaluation_manifest_path=self.evaluation_manifest,
            server_script=self.server_script,
            pid=snapshot.pid,
            host="127.0.0.1",
            port=5555,
            process_snapshot=snapshot,
            created_at_utc="2026-07-19T12:00:00Z",
        )

    def _verify(
        self,
        *,
        port: int = 5555,
        process_reader: Callable[[int], ProcessSnapshot] | None = None,
    ) -> dict[str, object]:
        reader = process_reader or (lambda pid: self.snapshot)
        return verify_runtime_identity(
            self.identity_path,
            expected_manifest_path=self.manifest,
            expected_evaluation_manifest_path=self.evaluation_manifest,
            expected_host="127.0.0.1",
            expected_port=port,
            process_reader=reader,
        )

    def _argv_with_appended(self, *tokens: str) -> ProcessSnapshot:
        return self._snapshot((*self.argv, *tokens))

    def test_accepts_exact_manifest_payload_process_imports_and_port(self) -> None:
        identity = self._verify()
        self.assertTrue(identity["checkpoint"]["complete_file_inventory_verified"])
        self.assertTrue(identity["promotion_eligible"])

    def test_accepts_python310_direct_script_import_prefix(self) -> None:
        payload = json.loads(self.attestation_path.read_text(encoding="utf-8"))
        sys_path = payload["process"]["sys_path"]
        expected = validate_server_sys_path_prefix(
            sys_path,
            repo_root=self.root,
            server_script=self.server_script,
        )
        self.assertEqual(
            expected,
            [
                str(self.server_script.resolve().parent),
                str(self.root.resolve() / "src"),
            ],
        )
        self.assertIsNone(dict(self.snapshot.environment)["PYTHONSAFEPATH"])

    def test_rejects_checkpoint_directory_path_mismatch(self) -> None:
        other = self.root / "other-checkpoint"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "path recorded"):
            verify_checkpoint_directory(self.manifest, other)

    def test_rejects_checkpoint_file_hash_mismatch(self) -> None:
        (self.checkpoint / "config.json").write_bytes(b"config-v2")
        with self.assertRaisesRegex(ValueError, "hash drifted"):
            verify_checkpoint_directory(self.manifest, self.checkpoint)

    def test_client_rejects_checkpoint_mutation_after_identity(self) -> None:
        (self.checkpoint / "config.json").write_bytes(b"post-identity-tamper")
        with self.assertRaisesRegex(ValueError, "checkpoint file"):
            self._verify()

    def test_client_rejects_processor_mutation_after_identity(self) -> None:
        (self.processor_model / "config.json").write_text(
            '{"tampered": true}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "processor directory"):
            self._verify()

    def test_rejects_equals_form_model_path_bypass(self) -> None:
        other = self.root / "other-model"
        other.mkdir()
        changed = self._argv_with_appended(f"--model-path={other}")
        with self.assertRaisesRegex(ValueError, "option/value pairs"):
            self._build(changed)

    def test_rejects_duplicate_model_path_bypass(self) -> None:
        other = self.root / "other-model"
        other.mkdir()
        changed = self._argv_with_appended("--model-path", str(other))
        with self.assertRaisesRegex(ValueError, "duplicate seeded server option"):
            self._build(changed)

    def test_rejects_abbreviated_model_path_bypass(self) -> None:
        other = self.root / "other-model"
        other.mkdir()
        changed = self._argv_with_appended("--model-pa", str(other))
        with self.assertRaisesRegex(ValueError, "noncanonical seeded server option"):
            self._build(changed)

    def test_rejects_shadowing_pythonpath_at_identity_creation(self) -> None:
        changed_environment = tuple(
            (name, "/shadow" if name == "PYTHONPATH" else value)
            for name, value in self.snapshot.environment
        )
        changed = replace(
            self.snapshot,
            environment=changed_environment,
            environment_sha256=canonical_sha256(dict(changed_environment)),
        )
        with self.assertRaisesRegex(ValueError, "import environment differs"):
            self._build(changed)

    def test_rejects_malicious_import_prefix_before_python310_layout(self) -> None:
        payload = json.loads(self.attestation_path.read_text(encoding="utf-8"))
        payload.pop("canonical_payload_sha256")
        payload["process"]["sys_path"].insert(0, "/shadow/site-packages")
        payload["canonical_payload_sha256"] = canonical_sha256(payload)
        self.attestation_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "noncanonical import prefix"):
            self._build(self.snapshot)

    def test_rejects_imported_module_tamper_after_identity(self) -> None:
        self.runtime_module.write_text("RUNTIME = 'shadowed'\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "module drifted"):
            self._verify()

    def test_rejects_missing_server_import_attestation(self) -> None:
        self.attestation_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self._verify()

    def test_rejects_explicitly_nonpromotable_server_attestation(self) -> None:
        payload = json.loads(self.attestation_path.read_text(encoding="utf-8"))
        payload.pop("canonical_payload_sha256")
        payload["promotion_eligible_runtime_attestation"] = False
        payload["canonical_payload_sha256"] = canonical_sha256(payload)
        self.attestation_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "not promotable"):
            self._build(self.snapshot)

    def test_rejects_manifest_hash_mismatch(self) -> None:
        self.manifest.write_text(
            self.manifest.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "manifest hash differs"):
            self._verify()

    def test_rejects_live_pid_identity_mismatch(self) -> None:
        different_pid = replace(self.snapshot, pid=9999)
        with self.assertRaisesRegex(ValueError, "live server PID"):
            self._verify(process_reader=lambda pid: different_pid)

    def test_rejects_rollout_port_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "host or port"):
            self._verify(port=5556)

    def test_rejects_live_listener_port_mismatch(self) -> None:
        changed = replace(self.snapshot, listening_tcp_ports=(5556,))
        with self.assertRaisesRegex(ValueError, "command line drifted"):
            self._verify(process_reader=lambda pid: changed)

    def test_rejects_evaluation_manifest_tamper(self) -> None:
        self.evaluation_manifest.write_text(
            self.evaluation_manifest.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "evaluation manifest hash differs"):
            self._verify()

    def test_receipt_binding_rejects_a_different_verified_identity(self) -> None:
        identity = self._verify()
        binding = runtime_identity_receipt_binding(self.identity_path, identity)
        self.assertEqual(binding["server_runtime_identity"], identity)
        self.assertTrue(binding["promotion_eligible_runtime_attestation"])
        changed = dict(identity)
        changed["created_at_utc"] = "2026-07-19T12:00:01Z"
        with self.assertRaisesRegex(ValueError, "differs from its receipt file"):
            runtime_identity_receipt_binding(self.identity_path, changed)


if __name__ == "__main__":
    unittest.main()
