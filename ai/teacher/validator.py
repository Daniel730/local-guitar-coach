"""Schema validation for TeacherAction (MVP-5).

Validates that the LLM's JSON conforms to the closed TeacherAction contract:
correct enum, no extra fields, types right. Does NOT decide whether the action
is *allowed* in the current state — that is PolicyValidator's job. Schema
validation failing means the model output is unusable -> fallback.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "teacher_action.json"


def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_action(raw_text: str, schema: dict = None) -> Tuple[bool, object, str]:
    """Return (ok, parsed_dict_or_None, error_message).

    ok=False means schema invalid -> caller should fall back.
    """
    if schema is None:
        schema = load_schema()
    # Must be parseable JSON.
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        return False, None, "invalid JSON"
    if not isinstance(data, dict):
        return False, None, "not a JSON object"

    # Closed enum + no extra properties.
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    additional = schema.get("additionalProperties", True)

    if additional is False:
        for key in data:
            if key not in props:
                return False, None, f"unknown field: {key}"

    for field in required:
        if field not in data:
            return False, None, f"missing required field: {field}"

    # action enum
    action = data.get("action")
    allowed = props.get("action", {}).get("enum", [])
    if action not in allowed:
        return False, None, f"invalid action: {action}"

    # type checks for known fields
    type_map = {"string": str, "number": (int, float), "integer": int, "null": type(None)}
    for key, spec in props.items():
        if key not in data:
            continue
        val = data[key]
        tname = spec.get("type")
        if isinstance(tname, list):
            ok = any(_matches(val, t) for t in tname)
        else:
            ok = _matches(val, tname)
        if not ok:
            return False, None, f"field {key} wrong type"

    return True, data, ""


def _matches(val, tname) -> bool:
    if tname == "null":
        return val is None
    if tname == "string":
        return isinstance(val, str)
    if tname == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if tname == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    return True
