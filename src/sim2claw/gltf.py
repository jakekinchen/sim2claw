from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any


_COMPONENT_FORMATS = {
    5121: "B",
    5123: "H",
    5125: "I",
    5126: "f",
}
_TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _safe_relative_uri(uri: str) -> Path:
    path = Path(uri)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe glTF URI: {uri!r}")
    return path


def _read_accessor(
    document: dict[str, Any], accessor_index: int, root: Path
) -> list[tuple[float | int, ...]]:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    buffer = document["buffers"][view["buffer"]]
    component_type = accessor["componentType"]
    value_type = accessor["type"]
    try:
        component_format = _COMPONENT_FORMATS[component_type]
        width = _TYPE_WIDTHS[value_type]
    except KeyError as exc:
        raise ValueError(
            f"unsupported accessor component/type: {component_type}/{value_type}"
        ) from exc

    buffer_path = root / _safe_relative_uri(buffer["uri"])
    payload = buffer_path.read_bytes()
    item_format = "<" + (component_format * width)
    item_size = struct.calcsize(item_format)
    stride = view.get("byteStride", item_size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor["count"]
    end = start + ((count - 1) * stride) + item_size if count else start
    if end > len(payload):
        raise ValueError(f"accessor {accessor_index} exceeds buffer length")

    return [
        struct.unpack_from(item_format, payload, start + (index * stride))
        for index in range(count)
    ]


def convert_textured_gltf_to_obj(gltf_path: Path) -> tuple[Path, Path]:
    """Convert the capture's bounded single-primitive glTF into OBJ/MTL.

    This intentionally supports the small glTF contract recorded in the capture
    manifest. It is not a general-purpose converter.
    """

    gltf_path = gltf_path.resolve()
    root = gltf_path.parent
    document = json.loads(gltf_path.read_text(encoding="utf-8"))
    if document.get("asset", {}).get("version") != "2.0":
        raise ValueError("only glTF 2.0 is supported")
    meshes = document.get("meshes", [])
    if len(meshes) != 1 or len(meshes[0].get("primitives", [])) != 1:
        raise ValueError("expected exactly one mesh primitive")
    primitive = meshes[0]["primitives"][0]
    if primitive.get("mode", 4) != 4:
        raise ValueError("expected triangle-list glTF primitive")

    attributes = primitive["attributes"]
    positions = _read_accessor(document, attributes["POSITION"], root)
    texcoords = _read_accessor(document, attributes["TEXCOORD_0"], root)
    indices = _read_accessor(document, primitive["indices"], root)
    flat_indices = [int(value[0]) for value in indices]
    if len(positions) != len(texcoords):
        raise ValueError("capture position and texture-coordinate counts differ")
    if len(flat_indices) % 3:
        raise ValueError("capture index count is not divisible by three")
    if flat_indices and max(flat_indices) >= len(positions):
        raise ValueError("capture index is outside the vertex array")

    material = document["materials"][primitive["material"]]
    texture_index = material["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    texture = document["textures"][texture_index]
    texture_uri = document["images"][texture["source"]]["uri"]
    _safe_relative_uri(texture_uri)

    obj_path = root / "raw.obj"
    mtl_path = root / "raw.mtl"
    obj_lines = ["mtllib raw.mtl", "o polycam_reference", "usemtl capture_texture"]
    obj_lines.extend(f"v {x:.9g} {y:.9g} {z:.9g}" for x, y, z in positions)
    obj_lines.extend(f"vt {u:.9g} {1.0 - v:.9g}" for u, v in texcoords)
    for index in range(0, len(flat_indices), 3):
        a, b, c = (flat_indices[index + offset] + 1 for offset in range(3))
        obj_lines.append(f"f {a}/{a} {b}/{b} {c}/{c}")
    obj_path.write_text("\n".join(obj_lines) + "\n", encoding="utf-8")

    mtl_lines = [
        "newmtl capture_texture",
        "Ka 1.0 1.0 1.0",
        "Kd 1.0 1.0 1.0",
        "Ks 0.0 0.0 0.0",
        "d 1.0",
        "illum 1",
        f"map_Kd {texture_uri}",
    ]
    mtl_path.write_text("\n".join(mtl_lines) + "\n", encoding="utf-8")
    return obj_path, mtl_path

