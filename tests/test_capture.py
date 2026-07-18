from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from sim2claw.capture import load_capture_config
from sim2claw.gltf import convert_textured_gltf_to_obj


class CaptureContractTest(unittest.TestCase):
    def test_recorded_table_measurements_and_hashes(self) -> None:
        config = load_capture_config()
        table = config["roomplan_measurements"]["table"]
        self.assertEqual(table["confidence"], "high")
        self.assertAlmostEqual(table["length_m"], 1.3513037)
        self.assertAlmostEqual(table["width_m"], 0.79171795)
        self.assertAlmostEqual(table["height_m"], 0.7799972)
        for artifact in config["artifacts"]:
            self.assertEqual(len(artifact["sha256"]), 64)
        self.assertFalse(config["asset_policy"]["redistribute"])

    def test_bounded_gltf_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
            texcoords = struct.pack("<6f", 0, 0, 1, 0, 0, 1)
            indices = struct.pack("<3H", 0, 1, 2)
            (root / "mesh.bin").write_bytes(indices + positions + texcoords)
            (root / "texture.jpg").write_bytes(b"fixture")
            document = {
                "asset": {"version": "2.0"},
                "buffers": [{"uri": "mesh.bin", "byteLength": 66}],
                "bufferViews": [
                    {"buffer": 0, "byteOffset": 0, "byteLength": 6},
                    {"buffer": 0, "byteOffset": 6, "byteLength": 36},
                    {"buffer": 0, "byteOffset": 42, "byteLength": 24},
                ],
                "accessors": [
                    {"bufferView": 0, "componentType": 5123, "count": 3, "type": "SCALAR"},
                    {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
                    {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC2"},
                ],
                "images": [{"uri": "texture.jpg"}],
                "textures": [{"source": 0}],
                "materials": [
                    {"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
                ],
                "meshes": [
                    {
                        "primitives": [
                            {
                                "attributes": {"POSITION": 1, "TEXCOORD_0": 2},
                                "indices": 0,
                                "material": 0,
                                "mode": 4,
                            }
                        ]
                    }
                ],
            }
            gltf = root / "raw.gltf"
            gltf.write_text(json.dumps(document), encoding="utf-8")
            obj, mtl = convert_textured_gltf_to_obj(gltf)
            self.assertIn("f 1/1 2/2 3/3", obj.read_text(encoding="utf-8"))
            self.assertIn("map_Kd texture.jpg", mtl.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

