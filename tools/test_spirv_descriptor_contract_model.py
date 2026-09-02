from __future__ import annotations

from dataclasses import dataclass


OP_TYPE_IMAGE = 25
OP_TYPE_SAMPLED_IMAGE = 27
OP_TYPE_ARRAY = 28
OP_TYPE_STRUCT = 30
OP_TYPE_POINTER = 32
OP_CONSTANT = 43
OP_VARIABLE = 59
OP_DECORATE = 71
DEC_BLOCK = 2
DEC_BINDING = 33
DEC_SET = 34
STORAGE_UNIFORM_CONSTANT = 0
STORAGE_UNIFORM = 2
STAGE_VERTEX = 1
STAGE_FRAGMENT = 2


@dataclass
class TypeInfo:
    opcode: int = 0
    storage: int = -1
    element: int = 0
    length_id: int = 0
    sampled: int = 0
    block: bool = False


@dataclass
class Variable:
    result_type: int = 0
    storage: int = -1
    valid: bool = False


def ins(opcode: int, *operands: int) -> list[int]:
    return [((1 + len(operands)) << 16) | opcode, *operands]


def module(instructions: list[list[int]], bound: int = 64) -> list[int]:
    words = [0x07230203, 0x00010000, 0, bound, 0]
    for inst in instructions:
        words.extend(inst)
    return words


def validate(words: list[int], stage: int) -> bool:
    if len(words) < 5 or words[0] != 0x07230203 or stage not in (STAGE_VERTEX, STAGE_FRAGMENT):
        return False
    bound = words[3]
    if bound < 1 or bound > 65536:
        return False
    types = [TypeInfo() for _ in range(bound)]
    variables = [Variable() for _ in range(bound)]
    constants = [None] * bound
    decorations: dict[int, dict[str, int]] = {}

    offset = 5
    while offset < len(words):
        head = words[offset]
        wc, op = head >> 16, head & 0xFFFF
        if wc == 0 or offset + wc > len(words):
            return False
        a = words[offset + 1 : offset + wc]
        if op == OP_DECORATE and len(a) >= 2:
            target, dec = a[0], a[1]
            if target >= bound:
                return False
            if dec == DEC_BLOCK:
                types[target].block = True
            elif dec in (DEC_BINDING, DEC_SET) and len(a) >= 3:
                entry = decorations.setdefault(target, {})
                key = "binding" if dec == DEC_BINDING else "set"
                if key in entry and entry[key] != a[2]:
                    return False
                entry[key] = a[2]
        elif op == OP_TYPE_IMAGE and len(a) >= 8:
            result = a[0]
            if result >= bound:
                return False
            types[result].opcode = op
            types[result].sampled = a[6]
        elif op == OP_TYPE_SAMPLED_IMAGE and len(a) >= 2:
            result = a[0]
            if result >= bound:
                return False
            types[result].opcode = op
            types[result].element = a[1]
        elif op == OP_TYPE_ARRAY and len(a) >= 3:
            result = a[0]
            if result >= bound:
                return False
            types[result].opcode = op
            types[result].element = a[1]
            types[result].length_id = a[2]
        elif op == OP_TYPE_STRUCT and len(a) >= 1:
            result = a[0]
            if result >= bound:
                return False
            types[result].opcode = op
        elif op == OP_TYPE_POINTER and len(a) >= 3:
            result = a[0]
            if result >= bound:
                return False
            types[result].opcode = op
            types[result].storage = a[1]
            types[result].element = a[2]
        elif op == OP_CONSTANT and len(a) == 3:
            result = a[1]
            if result >= bound:
                return False
            constants[result] = a[2]
        elif op == OP_VARIABLE and len(a) >= 3:
            result_type, result, storage = a[0], a[1], a[2]
            if result_type >= bound or result >= bound:
                return False
            variables[result] = Variable(result_type, storage, True)
        offset += wc

    def uniform_block(v: Variable) -> bool:
        if v.storage != STORAGE_UNIFORM or v.result_type >= bound:
            return False
        ptr = types[v.result_type]
        return (
            ptr.opcode == OP_TYPE_POINTER
            and ptr.storage == STORAGE_UNIFORM
            and ptr.element < bound
            and types[ptr.element].opcode == OP_TYPE_STRUCT
            and types[ptr.element].block
        )

    def sampled_array(v: Variable, length: int) -> bool:
        if v.storage != STORAGE_UNIFORM_CONSTANT or v.result_type >= bound:
            return False
        ptr = types[v.result_type]
        if ptr.opcode != OP_TYPE_POINTER or ptr.storage != STORAGE_UNIFORM_CONSTANT or ptr.element >= bound:
            return False
        arr = types[ptr.element]
        if arr.opcode != OP_TYPE_ARRAY or arr.length_id >= bound or constants[arr.length_id] != length or arr.element >= bound:
            return False
        sampled = types[arr.element]
        if sampled.opcode != OP_TYPE_SAMPLED_IMAGE or sampled.element >= bound:
            return False
        image = types[sampled.element]
        return image.opcode == OP_TYPE_IMAGE and image.sampled == 1

    for target, dec in decorations.items():
        if dec.get("set") != 0 or "binding" not in dec or target >= bound or not variables[target].valid:
            return False
        binding = dec["binding"]
        variable = variables[target]
        if binding == 0:
            if not uniform_block(variable):
                return False
        elif stage == STAGE_VERTEX and binding == 2:
            if not sampled_array(variable, 5):
                return False
        elif stage == STAGE_FRAGMENT and binding == 1:
            if not sampled_array(variable, 16):
                return False
        else:
            return False
    return True


def make_shader(stage: int, texture_count: int, *, sampled: int = 1, binding: int | None = None,
                storage: int = STORAGE_UNIFORM_CONSTANT, block: bool = True) -> list[int]:
    texture_binding = binding if binding is not None else (2 if stage == STAGE_VERTEX else 1)
    instructions = [
        ins(OP_TYPE_STRUCT, 1),
        ins(OP_DECORATE, 1, DEC_BLOCK if block else 99),
        ins(OP_TYPE_POINTER, 2, STORAGE_UNIFORM, 1),
        ins(OP_VARIABLE, 2, 3, STORAGE_UNIFORM),
        ins(OP_DECORATE, 3, DEC_SET, 0),
        ins(OP_DECORATE, 3, DEC_BINDING, 0),
        # OpTypeImage result=4, sampled-type=20, Dim=2D(1), Depth=0, Arrayed=0, MS=0,
        # Sampled=1, Format=Unknown(0).
        ins(OP_TYPE_IMAGE, 4, 20, 1, 0, 0, 0, sampled, 0),
        ins(OP_TYPE_SAMPLED_IMAGE, 5, 4),
        ins(OP_CONSTANT, 21, 6, texture_count),
        ins(OP_TYPE_ARRAY, 7, 5, 6),
        ins(OP_TYPE_POINTER, 8, storage, 7),
        ins(OP_VARIABLE, 8, 9, storage),
        ins(OP_DECORATE, 9, DEC_SET, 0),
        ins(OP_DECORATE, 9, DEC_BINDING, texture_binding),
    ]
    return module(instructions)


def main() -> int:
    assert validate(make_shader(STAGE_VERTEX, 5), STAGE_VERTEX)
    assert validate(make_shader(STAGE_FRAGMENT, 16), STAGE_FRAGMENT)

    assert not validate(make_shader(STAGE_VERTEX, 16), STAGE_VERTEX), "VS array length mismatch accepted"
    assert not validate(make_shader(STAGE_FRAGMENT, 5), STAGE_FRAGMENT), "PS array length mismatch accepted"
    assert not validate(make_shader(STAGE_VERTEX, 5, sampled=2), STAGE_VERTEX), "storage image accepted as sampled image"
    assert not validate(make_shader(STAGE_FRAGMENT, 16, binding=2), STAGE_FRAGMENT), "wrong fragment binding accepted"
    assert not validate(make_shader(STAGE_VERTEX, 5, storage=STORAGE_UNIFORM), STAGE_VERTEX), "wrong texture storage class accepted"
    assert not validate(make_shader(STAGE_FRAGMENT, 16, block=False), STAGE_FRAGMENT), "non-Block UBO accepted"

    malformed = make_shader(STAGE_VERTEX, 5)
    malformed[-1] = (0 << 16) | OP_DECORATE
    assert not validate(malformed, STAGE_VERTEX), "zero-word instruction accepted"

    print("[test-spirv-descriptor-contract] strict UBO + stage binding + sampled-image array shape cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
