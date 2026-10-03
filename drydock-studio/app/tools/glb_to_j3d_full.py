"""Build the Drydock native preview from the verified Jackdaw GLB.

Unlike the retired preview converters, this walks the glTF scene graph and
bakes every authored node transform into the vertex data.  That is essential
for the verified assembly: its hull layers, ram, rudder, rig, and corrected
sails are separate selectable nodes with authoritative placement matrices.

The output is a viewer bridge only.  The verified GLB remains the canonical
release model and is never modified by this conversion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

import numpy as np


COMPONENT_NAMES = (
    "Outer hull",
    "Deck",
    "Bow structure",
    "Stern cabin",
    "Standing rigging",
    "Masts and yardarms",
    "Sails",
    "Mast flag",
    "Cannons",
    "Swivel guns",
    "Light mortar",
    "Ship lanterns",
    "Rigging parts",
    "Ship greebles",
    "Ram",
    "Rudder",
)

GROUP_COMPONENTS = {
    "AUTHORED_DEFAULT_BUILD_GRAPH": 13,
    "DEFAULT_LANTERNS": 11,
    "EXACT_ADDITIONAL_RIGGING": 12,
    "HULL_DECK_AND_FIXED_DETAIL": 0,
    "MASTS_YARDS_PLATFORMS_AND_RIGGING": 5,
    "MAST_FLAG": 7,
    "PROTECTED_SAILS": 6,
    "RAM": 14,
    "RUDDER": 15,
}

# Keep the app's established per-panel labels/selection order.
SAIL_ZONE_ORDER = (
    "main-spanker",
    "main-topsail-starboard-wing",
    "main-topsail-port-wing",
    "main-topsail",
    "main-topgallant-starboard-wing",
    "main-topgallant-port-wing",
    "main-topgallant",
    "main-course-starboard-wing",
    "main-course-port-wing",
    "main-course",
    "main-course-staysail",
    "fore-topsail-starboard-wing",
    "fore-topsail-port-wing",
    "fore-topsail",
    "fore-topgallant-starboard-wing",
    "fore-topgallant-port-wing",
    "fore-topgallant",
    "fore-royal-starboard-wing",
    "fore-royal-port-wing",
    "fore-royal",
    "fore-course-starboard-wing",
    "fore-course-port-wing",
    "fore-course",
    "top-jib",
    "flying-jib",
    "course-jib",
)
SAIL_ZONES = {name: index for index, name in enumerate(SAIL_ZONE_ORDER)}

COMPONENT_DTYPES = {
    5120: np.dtype("<i1"),
    5121: np.dtype("<u1"),
    5122: np.dtype("<i2"),
    5123: np.dtype("<u2"),
    5125: np.dtype("<u4"),
    5126: np.dtype("<f4"),
}
ARITY = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load_glb(path: Path) -> tuple[dict, bytes]:
    blob = path.read_bytes()
    magic, version, declared_size = struct.unpack_from("<4sII", blob, 0)
    if magic != b"glTF" or version != 2 or declared_size != len(blob):
        raise ValueError(f"{path} is not a valid GLB 2.0 file")
    chunks: dict[int, bytes] = {}
    offset = 12
    while offset < len(blob):
        size, kind = struct.unpack_from("<II", blob, offset)
        chunks[kind] = blob[offset + 8 : offset + 8 + size]
        offset += 8 + size
    if 0x4E4F534A not in chunks or 0x004E4942 not in chunks:
        raise ValueError("GLB must contain JSON and BIN chunks")
    document = json.loads(chunks[0x4E4F534A].rstrip(b" \0"))
    return document, chunks[0x004E4942]


def read_accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    if "sparse" in accessor:
        raise ValueError("Sparse accessors are not supported by the native viewer bridge")
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = COMPONENT_DTYPES[accessor["componentType"]]
    width = ARITY[accessor["type"]]
    item_bytes = dtype.itemsize * width
    stride = int(view.get("byteStride", item_bytes))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    values = np.ndarray(
        shape=(int(accessor["count"]), width),
        dtype=dtype,
        buffer=binary,
        offset=start,
        strides=(stride, dtype.itemsize),
    ).copy()
    return values


def quaternion_matrix(value: list[float]) -> np.ndarray:
    x, y, z, w = (float(part) for part in value)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 1e-12:
        return np.identity(4, dtype=np.float64)
    x, y, z, w = x / length, y / length, z / length, w / length
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        # glTF stores matrices column-major.
        return np.asarray(node["matrix"], dtype=np.float64).reshape((4, 4), order="F")
    translation = np.identity(4, dtype=np.float64)
    translation[:3, 3] = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
    rotation = quaternion_matrix(node.get("rotation", [0, 0, 0, 1]))
    scale = np.identity(4, dtype=np.float64)
    scale[0, 0], scale[1, 1], scale[2, 2] = (
        float(part) for part in node.get("scale", [1, 1, 1])
    )
    return translation @ rotation @ scale


def group_from_name(name: str | None, inherited: str | None) -> str | None:
    if not name:
        return inherited
    if name.startswith("GROUP :: "):
        return name.split(" :: ", 1)[1].strip()
    if name.startswith("COMPONENT :: "):
        fields = name.split(" :: ")
        if len(fields) >= 2 and fields[1] in GROUP_COMPONENTS:
            return fields[1]
    return inherited


def sail_zone_from_name(name: str) -> int | None:
    match = re.search(r"SAIL PANEL :: ([^:]+)$", name, flags=re.IGNORECASE)
    if not match:
        return None
    return SAIL_ZONES.get(match.group(1).strip().lower())


def material_resource_id(document: dict, primitive: dict) -> int:
    material_index = primitive.get("material")
    if material_index is None:
        return 0
    material = document.get("materials", [])[int(material_index)]
    for value in (material.get("name"), material.get("extras")):
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str):
            token = value.strip()
            try:
                return int(token, 16) if token.lower().startswith("0x") else int(token)
            except ValueError:
                pass
    return 0


def triangle_indices(primitive: dict, document: dict, binary: bytes, vertex_count: int) -> np.ndarray:
    if "indices" in primitive:
        raw = read_accessor(document, binary, int(primitive["indices"])).reshape(-1).astype(np.uint32)
    else:
        raw = np.arange(vertex_count, dtype=np.uint32)
    mode = int(primitive.get("mode", 4))
    if mode == 4:  # TRIANGLES
        return raw
    if mode == 5:  # TRIANGLE_STRIP
        triangles = []
        for i in range(len(raw) - 2):
            a, b, c = int(raw[i]), int(raw[i + 1]), int(raw[i + 2])
            triangles.extend((b, a, c) if i & 1 else (a, b, c))
        return np.asarray(triangles, dtype=np.uint32)
    if mode == 6:  # TRIANGLE_FAN
        triangles = []
        for i in range(1, len(raw) - 1):
            triangles.extend((int(raw[0]), int(raw[i]), int(raw[i + 1])))
        return np.asarray(triangles, dtype=np.uint32)
    raise ValueError(f"Unsupported glTF primitive mode {mode}; expected triangles")


def collect_records(document: dict, binary: bytes) -> list[dict]:
    records: list[dict] = []
    next_zone = [0] * len(COMPONENT_NAMES)
    visited: set[int] = set()

    def visit(node_index: int, parent_world: np.ndarray, inherited_group: str | None) -> None:
        # A valid glTF scene graph should not instance a node under two parents.
        # Avoid silently duplicating malformed cyclic nodes in the native file.
        if node_index in visited:
            return
        visited.add(node_index)
        node = document["nodes"][node_index]
        name = str(node.get("name", ""))
        group = group_from_name(name, inherited_group)
        world = parent_world @ node_matrix(node)

        if "mesh" in node:
            component = GROUP_COMPONENTS.get(group or "", 13)
            mesh = document["meshes"][int(node["mesh"])]
            for primitive in mesh.get("primitives", []):
                positions = read_accessor(document, binary, int(primitive["attributes"]["POSITION"])).astype(np.float64)
                ones = np.ones((positions.shape[0], 1), dtype=np.float64)
                positions = (world @ np.concatenate((positions, ones), axis=1).T).T[:, :3]

                if "NORMAL" in primitive["attributes"]:
                    normals = read_accessor(document, binary, int(primitive["attributes"]["NORMAL"])).astype(np.float64)
                    normal_matrix = np.linalg.inv(world[:3, :3]).T
                    normals = (normal_matrix @ normals.T).T
                    lengths = np.linalg.norm(normals, axis=1)
                    lengths[lengths < 1e-12] = 1.0
                    normals /= lengths[:, None]
                else:
                    normals = np.zeros_like(positions)
                    normals[:, 2] = 1.0

                if "TEXCOORD_0" in primitive["attributes"]:
                    uvs = read_accessor(document, binary, int(primitive["attributes"]["TEXCOORD_0"])).astype(np.float64)[:, :2]
                else:
                    uvs = np.zeros((positions.shape[0], 2), dtype=np.float64)

                indices = triangle_indices(primitive, document, binary, positions.shape[0])
                explicit_sail_zone = sail_zone_from_name(name) if component == 6 else None
                if explicit_sail_zone is not None:
                    zone = explicit_sail_zone
                else:
                    zone = next_zone[component]
                    next_zone[component] += 1
                records.append(
                    {
                        "component": component,
                        "zone": zone,
                        "material": material_resource_id(document, primitive),
                        "positions": positions.astype("<f4"),
                        "normals": normals.astype("<f4"),
                        "uvs": uvs.astype("<f4"),
                        "indices": indices.astype("<u4"),
                        "node": name,
                        "group": group,
                    }
                )

        for child in node.get("children", []):
            visit(int(child), world, group)

    scene_index = int(document.get("scene", 0))
    scene = document["scenes"][scene_index]
    # glTF is Y-up, while the Drydock native camera and every legacy JACK3D1
    # control are Z-up. Rotate once at the scene root: (x, y, z) -> (x, -z, y).
    identity = np.array(
        [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]],
        dtype=np.float64,
    )
    for root in scene.get("nodes", []):
        visit(int(root), identity, None)
    return records


def write_j3d(records: list[dict], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as stream:
        stream.write(b"JACK3D1\0")
        stream.write(struct.pack("<II", len(COMPONENT_NAMES), len(records)))
        for record in records:
            positions = record["positions"]
            normals = record["normals"]
            uvs = record["uvs"]
            indices = record["indices"]
            interleaved = np.concatenate((positions, normals, uvs), axis=1).astype("<f4", copy=False)
            stream.write(
                struct.pack(
                    "<IIIQII",
                    int(record["component"]),
                    int(record["zone"]),
                    0,
                    int(record["material"]),
                    int(positions.shape[0]),
                    int(indices.size),
                )
            )
            stream.write(interleaved.tobytes(order="C"))
            stream.write(indices.tobytes(order="C"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source_sha256 = hashlib.sha256(args.source.read_bytes()).hexdigest()
    document, binary = load_glb(args.source)
    records = collect_records(document, binary)
    if not records:
        raise RuntimeError("The verified GLB contains no renderable mesh primitives")
    write_j3d(records, args.destination)
    if hashlib.sha256(args.source.read_bytes()).hexdigest() != source_sha256:
        raise RuntimeError("Source GLB changed during conversion; do not deploy this preview")

    mins = np.min(np.vstack([record["positions"] for record in records]), axis=0)
    maxs = np.max(np.vstack([record["positions"] for record in records]), axis=0)
    component_counts = {
        COMPONENT_NAMES[index]: sum(record["component"] == index for record in records)
        for index in range(len(COMPONENT_NAMES))
        if any(record["component"] == index for record in records)
    }
    report = {
        "format": "jackdaw-native-viewer-bridge-v1",
        "canonical_source": str(args.source.resolve()),
        "source_sha256": source_sha256,
        "output": str(args.destination.resolve()),
        "output_sha256": hashlib.sha256(args.destination.read_bytes()).hexdigest(),
        "components": len(COMPONENT_NAMES),
        "zones": len(records),
        "vertices": int(sum(record["positions"].shape[0] for record in records)),
        "indices": int(sum(record["indices"].size for record in records)),
        "bounds_min": [float(value) for value in mins],
        "bounds_max": [float(value) for value in maxs],
        "component_zones": component_counts,
        "node_transforms_baked": True,
        "viewer_axis_conversion": "glTF Y-up to Drydock Z-up: (x,y,z)->(x,-z,y)",
        "canonical_glb_unchanged": True,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
