#!/usr/bin/env python3
"""JACK3D1 binary format -> GLB converter (sub-mesh preserving).

Format spec (reverse-engineered from jackdaw-preview.j3d):
  Offset  Size   Field
  0       8      Magic "JACK3D1\\0"
  8       4      uint32 component_count
  12      4      uint32 zone_count
  16      28*N   Per-zone headers (19 zones)
                 uint32 component_id
                 uint32 zone_id
                 uint32 skip/reserved
                 uint64 material_id
                 uint32 vertex_count
                 uint32 index_count
  16+28*N  variable   Per-zone vertex+index data
                 vertex_count * 32 bytes (12B pos + 12B normal + 8B texcoord)
                 index_count * 4 bytes (uint32)

Conversion contract (required by the 3DGenStudio viewport):
  * Every JACK3D1 zone becomes its OWN glTF node + mesh, so the Hull, Deck,
    Masts, Sails etc. stay independently selectable and re-texturable.
    Zones are NEVER merged or flattened into a single buffer.
  * Indices are emitted as UNSIGNED_INT (componentType 5125), never
    UNSIGNED_SHORT: a single merged or even a large zone's index buffer can
    exceed 65535 indices, and 16-bit indices silently wrap -> a broken /
    invisible mesh in the viewport.
  * POSITION / NORMAL / TEXCOORD_0 accessors are preserved per zone with
    min/max computed from the ACTUAL vertex data.
  * Centering + scale-to-fit are applied as an offset on each vertex so the
    model sits at the origin where the viewport camera frames it, while each
    sub-mesh node keeps its own local geometry and name.
"""

import struct
import json
import sys

# Per-component display names. Index matches component_id. Keep them generic so
# the node graph reflects Hull / Deck / Masts / Sails structure even if the
# source JACK3D1 component ids differ slightly.
COMPONENT_NAMES = [
    "Outer hull",
    "Deck",
    "Bow structure",
    "Stern cabin",
    "Standing rigging",
    "Masts and yardarms",
    "Sails",
    "Mast flag",
]


def component_label(component_id: int) -> str:
    if 0 <= component_id < len(COMPONENT_NAMES):
        return COMPONENT_NAMES[component_id]
    return "Component_%d" % component_id


def parse_zones(data: bytes):
    magic = data[:8]
    if magic != b"JACK3D1\x00":
        raise ValueError("Invalid JACK3D1 magic: %r" % magic)
    comp_count, zone_count = struct.unpack("<II", data[8:16])
    offset = 16
    zones = []
    for _ in range(zone_count):
        comp_id = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        zone_id = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        offset += 4  # skip / reserved
        material_id = struct.unpack("<Q", data[offset : offset + 8])[0]
        offset += 8
        vcount = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4
        icount = struct.unpack("<I", data[offset : offset + 4])[0]
        offset += 4

        positions = []
        normals = []
        texcoords = []
        for _ in range(vcount):
            px, py, pz, nx, ny, nz, tx, ty = struct.unpack("<8f", data[offset : offset + 32])
            offset += 32
            positions.append((px, py, pz))
            normals.append((nx, ny, nz))
            texcoords.append((tx, ty))

        indices = list(struct.unpack("<%dI" % icount, data[offset : offset + 4 * icount]))
        offset += 4 * icount

        zones.append(
            {
                "component": comp_id,
                "zone": zone_id,
                "material": material_id,
                "positions": positions,
                "normals": normals,
                "texcoords": texcoords,
                "indices": indices,
            }
        )
    if offset != len(data):
        raise ValueError(
            "JACK3D1 data mismatch: consumed %d of %d bytes" % (offset, len(data))
        )
    return comp_count, zone_count, zones


def vec_minmax(values, axes):
    lo = [min(v[i] for v in values) for i in range(axes)]
    hi = [max(v[i] for v in values) for i in range(axes)]
    return lo, hi


def convert_j3d_to_glb(j3d_path, glb_path):
    with open(j3d_path, "rb") as f:
        data = f.read()

    comp_count, zone_count, zones = parse_zones(data)
    print("Converting JACK3D1: %d components, %d zones" % (comp_count, zone_count))

    # Global bounding box across every zone (used only for centering/scale).
    all_pos = [p for z in zones if z["positions"] for p in z["positions"]]
    if not all_pos:
        raise ValueError("JACK3D1 contains no vertices")
    pos_min, pos_max = vec_minmax(all_pos, 3)
    center = [(pos_min[i] + pos_max[i]) / 2.0 for i in range(3)]
    size = [pos_max[i] - pos_min[i] for i in range(3)]
    max_size = max(size)
    scale = 100.0 / max_size if max_size > 0 else 1.0
    print("Centering at (%s), scale %.4f (max dim %.2f -> 100)" % (", ".join("%.2f" % c for c in center), scale, max_size))

    def transform(p):
        return ((p[0] - center[0]) * scale, (p[1] - center[1]) * scale, (p[2] - center[2]) * scale)

    def align4(n):
        return (n + 3) & ~3

    # Per-zone builder state. Each zone produces an independent node + mesh.
    accessors = []
    buffer_views = []
    meshes = []
    nodes = []
    materials = []
    material_slots = {}  # zone material_id -> glTF material index
    binary = b""

    for zone in zones:
        positions = [transform(p) for p in zone["positions"]]
        normals = zone["normals"]
        texcoords = zone["texcoords"]
        indices = zone["indices"]
        if not positions:
            continue

        pos_bytes = b"".join(struct.pack("<fff", *p) for p in positions)
        norm_bytes = b"".join(struct.pack("<fff", *n) for n in normals)
        tex_bytes = b"".join(struct.pack("<ff", *t) for t in texcoords)
        idx_bytes = struct.pack("<%dI" % len(indices), *indices)

        pos_align, norm_align, tex_align = align4(len(pos_bytes)), align4(len(norm_bytes)), align4(len(tex_bytes))
        pos_offset = len(binary)
        binary += pos_bytes + b"\x00" * (pos_align - len(pos_bytes))
        norm_offset = len(binary)
        binary += norm_bytes + b"\x00" * (norm_align - len(norm_bytes))
        tex_offset = len(binary)
        binary += tex_bytes + b"\x00" * (tex_align - len(tex_bytes))
        idx_offset = len(binary)
        binary += idx_bytes

        vcount = len(positions)
        pmin, pmax = vec_minmax(positions, 3)
        nmin, nmax = vec_minmax(normals, 3)
        tmin, tmax = vec_minmax(texcoords, 2)

        pos_accessor = len(accessors)
        accessors.append({"bufferView": len(buffer_views), "componentType": 5126, "count": vcount, "type": "VEC3", "min": pmin, "max": pmax})
        buffer_views.append({"buffer": 0, "byteOffset": pos_offset, "byteLength": len(pos_bytes)})
        norm_accessor = len(accessors)
        accessors.append({"bufferView": len(buffer_views), "componentType": 5126, "count": vcount, "type": "VEC3", "min": nmin, "max": nmax})
        buffer_views.append({"buffer": 0, "byteOffset": norm_offset, "byteLength": len(norm_bytes)})
        tex_accessor = len(accessors)
        accessors.append({"bufferView": len(buffer_views), "componentType": 5126, "count": vcount, "type": "VEC2", "min": tmin, "max": tmax})
        buffer_views.append({"buffer": 0, "byteOffset": tex_offset, "byteLength": len(tex_bytes)})
        index_accessor = len(accessors)
        # IMPORTANT: 5125 = UNSIGNED_INT. Never use 5123 (UINT16) here: the
        # index count can exceed 65535 and 16-bit indices would wrap, breaking
        # (or hiding) the mesh in the 3DGenStudio viewport.
        accessors.append({"bufferView": len(buffer_views), "componentType": 5125, "count": len(indices), "type": "SCALAR"})
        buffer_views.append({"buffer": 0, "byteOffset": idx_offset, "byteLength": len(idx_bytes)})

        material_slot = zone["material"]
        if material_slot not in material_slots:
            material_index = len(materials)
            materials.append(
                {
                    "name": "Slot_%s" % material_slot,
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [0.85, 0.82, 0.78, 1.0],
                        "metallicFactor": 0.0,
                        "roughnessFactor": 0.85,
                    },
                    "extras": {"materialId": material_slot},
                }
            )
            material_slots[material_slot] = material_index
        else:
            material_index = material_slots[material_slot]

        mesh_index = len(meshes)
        meshes.append(
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": pos_accessor, "NORMAL": norm_accessor, "TEXCOORD_0": tex_accessor},
                        "indices": index_accessor,
                        "material": material_index,
                    }
                ]
            }
        )

        component = zone["component"]
        # Keep the zone count per component so named parts with >1 zone are
        # suffixed; single-zone parts keep the plain Hull/Deck/Masts/Sails name.
        sibling_zones = sum(1 for z in zones if z["component"] == component and z["positions"])
        if sibling_zones > 1:
            node_label = "%s_%d" % (component_label(component), zone["zone"])
        else:
            node_label = component_label(component)

        nodes.append(
            {
                "name": node_label,
                "mesh": mesh_index,
                "translation": [0.0, 0.0, 0.0],
                "extras": {
                    "component": component,
                    "componentName": component_label(component),
                    "zone": zone["zone"],
                    "materialSlot": material_slot,
                    "localOrigin": pmin,
                    "vertexCount": vcount,
                    "indexCount": len(indices),
                },
            }
        )

    gltf = {
        "asset": {"version": "2.0", "generator": "Jackdaw Workshop - JACK3D1 Converter"},
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary)}],
        "materials": materials,
        "meshes": meshes,
        "nodes": nodes,
        "scenes": [{"name": "Scene", "nodes": list(range(len(nodes)))}],
        "scene": 0,
        "extras": {
            "sourceFormat": "JACK3D1",
            "componentCount": comp_count,
            "zoneCount": zone_count,
            "subMeshCount": len(nodes),
        },
    }

    # GLB 2.0 requires the JSON chunk to be padded with ASCII spaces. NUL
    # padding makes strict loaders reject an otherwise valid model.
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_padded = json_bytes + b" " * ((4 - len(json_bytes) % 4) % 4)
    binary += b"\x00" * ((4 - len(binary) % 4) % 4)

    glb_header = b"glTF" + struct.pack("<I", 2) + struct.pack("<I", 12 + 8 + len(json_padded) + 8 + len(binary))
    json_chunk = struct.pack("<I", len(json_padded)) + b"JSON" + json_padded
    bin_chunk = struct.pack("<I", len(binary)) + b"BIN\0" + binary

    with open(glb_path, "wb") as f:
        f.write(glb_header + json_chunk + bin_chunk)

    print("GLB written: %s (%d sub-meshes, %d bytes)" % (glb_path, len(nodes), len(glb_header + json_chunk + bin_chunk)))
    return glb_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: %s <input.j3d> <output.glb>" % sys.argv[0])
        sys.exit(1)
    convert_j3d_to_glb(sys.argv[1], sys.argv[2])
