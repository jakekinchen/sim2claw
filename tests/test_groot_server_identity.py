from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from sim2claw.groot_evaluation_identity import build_evaluation_manifest
from sim2claw.groot_server_identity import (
    CHECKPOINT_MANIFEST_SCHEMA,
    ProcessSnapshot,
    build_runtime_identity,
    checkpoint_payload_sha256,
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
        implementation = self.root / "implementation.py"
        implementation.write_text("IDENTITY = 'v1'\n", encoding="utf-8")
        self.processor_model = self.root / "processor-model"
        self.processor_model.mkdir()
        (self.processor_model / "config.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        self.evaluation_manifest = self.root / "evaluation-manifest.json"
        evaluation_payload = build_evaluation_manifest(
            repo_root=self.root,
            groot_root=self.root,
            implementation_paths=(implementation.name,),
            sim2claw_git={
                "root": str(self.root.resolve()),
                "commit": "1" * 40,
                "tree": "2" * 40,
                "tracked_status": [],
                "clean": True,
            },
            runtime={
                "python": {
                    "version": "hermetic",
                    "executable": str(Path("/usr/bin/python3").resolve()),
                    "executable_sha256": "3" * 64,
                },
                "mujoco": "hermetic",
                "gr00t": "hermetic",
            },
            runtime_assets={"processor_model": self.processor_model},
        )
        write_json_exclusive(self.evaluation_manifest, evaluation_payload)
        manifest_payload = load_checkpoint_manifest(self.manifest)
        self.argv = (
            "/usr/bin/python3",
            "-u",
            str(self.server_script.resolve()),
            "--model-path",
            str(self.checkpoint.resolve()),
            "--processor-model-path",
            str(self.processor_model.resolve()),
            "--host",
            "127.0.0.1",
            "--port",
            "5555",
            "--checkpoint-manifest-sha256",
            sha256_file(self.manifest),
            "--checkpoint-payload-sha256",
            checkpoint_payload_sha256(manifest_payload),
            "--evaluation-manifest-sha256",
            sha256_file(self.evaluation_manifest),
        )
        self.snapshot = self._snapshot(self.argv)
        self.identity_path = self.root / "runtime-identity.json"
        identity = build_runtime_identity(
            manifest_path=self.manifest,
            checkpoint_directory=self.checkpoint,
            evaluation_manifest_path=self.evaluation_manifest,
            server_script=self.server_script,
            pid=self.snapshot.pid,
            host="127.0.0.1",
            port=5555,
            process_snapshot=self.snapshot,
            created_at_utc="2026-07-19T12:00:00Z",
        )
        write_json_exclusive(self.identity_path, identity)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _snapshot(argv: tuple[str, ...], *, pid: int = 4242) -> ProcessSnapshot:
        raw_cmdline = b"\0".join(value.encode() for value in argv) + b"\0"
        return ProcessSnapshot(
            pid=pid,
            process_start_ticks=987654,
            boot_id="00000000-1111-2222-3333-444444444444",
            executable=str(Path("/usr/bin/python3").resolve()),
            argv=argv,
            cmdline_sha256=hashlib.sha256(raw_cmdline).hexdigest(),
            listening_tcp_ports=(5555,),
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

    def test_accepts_exact_manifest_payload_process_and_port(self) -> None:
        identity = self._verify()
        self.assertTrue(
            identity["checkpoint"]["complete_file_inventory_verified"]
        )
        self.assertEqual(identity["process"]["pid"], 4242)

    def test_rejects_checkpoint_directory_path_mismatch(self) -> None:
        other = self.root / "other-checkpoint"
        other.mkdir()
        with self.assertRaisesRegex(ValueError, "path recorded"):
            verify_checkpoint_directory(self.manifest, other)

    def test_rejects_checkpoint_file_hash_mismatch(self) -> None:
        (self.checkpoint / "config.json").write_bytes(b"config-v2")
        with self.assertRaisesRegex(ValueError, "hash drifted"):
            verify_checkpoint_directory(self.manifest, self.checkpoint)

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

    def test_rejects_live_checkpoint_argv_mismatch(self) -> None:
        other = self.root / "other-model"
        other.mkdir()
        argv = list(self.argv)
        argv[argv.index("--model-path") + 1] = str(other.resolve())
        changed = self._snapshot(tuple(argv))
        with self.assertRaisesRegex(ValueError, "command line drifted"):
            self._verify(process_reader=lambda pid: changed)

    def test_rejects_processor_model_argv_mismatch_at_identity_creation(self) -> None:
        other = self.root / "other-processor"
        other.mkdir()
        argv = list(self.argv)
        argv[argv.index("--processor-model-path") + 1] = str(other.resolve())
        changed = self._snapshot(tuple(argv))
        with self.assertRaisesRegex(ValueError, "different processor model"):
            build_runtime_identity(
                manifest_path=self.manifest,
                checkpoint_directory=self.checkpoint,
                evaluation_manifest_path=self.evaluation_manifest,
                server_script=self.server_script,
                pid=changed.pid,
                host="127.0.0.1",
                port=5555,
                process_snapshot=changed,
            )

    def test_rejects_live_listener_port_mismatch(self) -> None:
        changed = replace(self.snapshot, listening_tcp_ports=(5556,))
        with self.assertRaisesRegex(ValueError, "command line drifted"):
            self._verify(process_reader=lambda pid: changed)

    def test_rejects_live_python_executable_mismatch(self) -> None:
        changed = replace(self.snapshot, executable="/usr/bin/false")
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
        changed = dict(identity)
        changed["created_at_utc"] = "2026-07-19T12:00:01Z"
        with self.assertRaisesRegex(ValueError, "differs from its receipt file"):
            runtime_identity_receipt_binding(self.identity_path, changed)


if __name__ == "__main__":
    unittest.main()
