from __future__ import annotations

import argparse
import struct
from pathlib import Path

SPIRV_MAGIC = 0x07230203
OP_NAME = 5
OP_VARIABLE = 59
OP_DECORATE = 71
DECORATION_BINDING = 33
DECORATION_DESCRIPTOR_SET = 34
STORAGE_UNIFORM_CONSTANT = 0
STORAGE_UNIFORM = 2


def _decode_name(words: list[int]) -> str:
    raw = b"".join(struct.pack("<I", word) for word in words)
    return raw.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def normalize_bindings(path: Path) -> list[dict]:
    data = path.read_bytes()
    if len(data) < 20 or len(data) % 4:
        raise RuntimeError(f"invalid SPIR-V size: {path}")
    words = list(struct.unpack(f"<{len(data) // 4}I", data))
    if words[0] != SPIRV_MAGIC:
        raise RuntimeError(f"invalid SPIR-V magic: {path}")

    names: dict[int, str] = {}
    storage: dict[int, int] = {}
    bindings: dict[int, tuple[int, int]] = {}
    sets: dict[int, int] = {}

    offset = 5
    while offset < len(words):
        first = words[offset]
        word_count = first >> 16
        opcode = first & 0xFFFF
        if word_count <= 0 or offset + word_count > len(words):
            raise RuntimeError(f"corrupt SPIR-V instruction at word {offset}: {path}")
        inst = words[offset : offset + word_count]
        if opcode == OP_NAME and word_count >= 3:
            names[inst[1]] = _decode_name(inst[2:])
        elif opcode == OP_VARIABLE and word_count >= 4:
            storage[inst[2]] = inst[3]
        elif opcode == OP_DECORATE and word_count >= 4:
            target = inst[1]
            decoration = inst[2]
            if decoration == DECORATION_BINDING:
                bindings[target] = (offset + 3, inst[3])
            elif decoration == DECORATION_DESCRIPTOR_SET:
                sets[target] = inst[3]
        offset += word_count

    descriptors = []
    for target, (binding_word, old_binding) in bindings.items():
        storage_class = storage.get(target)
        if storage_class not in (STORAGE_UNIFORM, STORAGE_UNIFORM_CONSTANT):
            raise RuntimeError(
                f"unsupported descriptor storage class {storage_class} for id {target} in {path}"
            )
        descriptor_set = sets.get(target, 0)
        if descriptor_set != 0:
            raise RuntimeError(f"only descriptor set 0 is supported, got set {descriptor_set} in {path}")
        descriptors.append(
            {
                "id": target,
                "name": names.get(target, f"id_{target}"),
                "storage": "ubo" if storage_class == STORAGE_UNIFORM else "sampled",
                "old_binding": old_binding,
                "binding_word": binding_word,
            }
        )

    ubos = [row for row in descriptors if row["storage"] == "ubo"]
    sampled = [row for row in descriptors if row["storage"] == "sampled"]
    if len(ubos) > 1:
        raise RuntimeError(f"more than one UBO in {path}: {len(ubos)}")
    if len(sampled) > 8:
        raise RuntimeError(f"more than eight sampled resources in {path}: {len(sampled)}")

    normalized = []
    if ubos:
        row = ubos[0]
        words[row["binding_word"]] = 0
        normalized.append(
            {
                "name": row["name"],
                "storage": row["storage"],
                "old_binding": row["old_binding"],
                "binding": 0,
            }
        )

    sampled.sort(key=lambda row: (row["old_binding"], row["name"], row["id"]))
    for index, row in enumerate(sampled, start=1):
        words[row["binding_word"]] = index
        normalized.append(
            {
                "name": row["name"],
                "storage": row["storage"],
                "old_binding": row["old_binding"],
                "binding": index,
            }
        )

    used = [row["binding"] for row in normalized]
    if len(used) != len(set(used)):
        raise RuntimeError(f"descriptor binding collision after normalization: {path}")

    path.write_bytes(struct.pack(f"<{len(words)}I", *words))
    return normalized


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize X-Ray R2 SPIR-V descriptor bindings to UBO=0 and samplers=1..8.")
    ap.add_argument("spirv", type=Path, nargs="+")
    args = ap.parse_args()
    for shader in args.spirv:
        mapping = normalize_bindings(shader)
        print(f"[spirv-bindings] {shader}: {mapping}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
