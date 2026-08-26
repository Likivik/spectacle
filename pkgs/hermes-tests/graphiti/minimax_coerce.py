"""Hermetic unit test for MiniMaxToolCallClient._coerce_for_schema.

MiniMax-M3 tool-calling mangles two things — single-element primitive arrays
collapse to ``{"item": X}`` and numeric scalars come back as strings ("0",
"2.5"). ``_coerce_for_schema`` repairs both against the expected schema. This
imports the REAL function from the vendored mcp-workspace source (argv[1])
under the graphiti runtime venv (ships graphiti_core + openai + pydantic), so
it exercises production code, not a copy.

Usage: python minimax_coerce.py <path-to-minimax_client.py>
"""

from __future__ import annotations

import importlib.util
import sys


def _load(path: str):
    spec = importlib.util.spec_from_file_location("minimax_client", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# graphiti-shaped extraction schema (mirrors ExtractedEdges/ExtractedEntities).
SCHEMA = {
    "type": "object",
    "properties": {
        "edges": {"type": "array", "items": {"$ref": "#/$defs/Edge"}},
        "entities": {"type": "array", "items": {"$ref": "#/$defs/Entity"}},
    },
    "required": ["edges", "entities"],
    "$defs": {
        "Edge": {
            "type": "object",
            "properties": {
                "source_entity_name": {"type": "string"},
                "target_entity_name": {"type": "string"},
                "fact": {"type": "string"},
                "episode_index": {"type": "integer"},
            },
            "required": ["source_entity_name", "target_entity_name", "fact"],
        },
        "Entity": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "entity_type": {"type": "string"},
            },
            "required": ["name", "entity_type"],
        },
    },
}


def main() -> int:
    if len(sys.argv) < 2:
        print("FAIL: missing path to minimax_client.py")
        return 1
    mod = _load(sys.argv[1])
    coerce = mod._coerce_for_schema
    defs = SCHEMA["$defs"]

    failures: list[str] = []

    def eq(label: str, got, want) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # 1. {"item": X} collapse on an object array (the {"item":"0"} class of bug).
    out = coerce(
        {"edges": {"item": {"source_entity_name": "a", "target_entity_name": "b", "fact": "f"}},
         "entities": []},
        SCHEMA,
        defs,
    )
    eq(
        "object-array item collapse",
        out["edges"],
        [{"source_entity_name": "a", "target_entity_name": "b", "fact": "f"}],
    )

    # 2. {"item": "0"} -> [0] on an integer array.
    eq("int-array item collapse", coerce({"item": "0"}, {"type": "array", "items": {"type": "integer"}}, {}), [0])

    # 3. string "5" -> int 5 in an integer field.
    eq("str->int", coerce("5", {"type": "integer"}, {}), 5)

    # 4. string "2.5" -> float 2.5 in a number field.
    eq("str->float", coerce("2.5", {"type": "number"}, {}), 2.5)

    # 5. bool True -> 1 in an integer field.
    eq("bool->int", coerce(True, {"type": "integer"}, {}), 1)

    # 6. non-coercible strings preserved (never corrupt a correct payload).
    eq("unparseable-int", coerce("not-a-number", {"type": "integer"}, {}), "not-a-number")

    # 7. outside any schema, pass through unchanged.
    eq("passthrough", coerce("untouched", {}, {}), "untouched")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("MINIMAX COERCE OK (7 assertions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
