#!/usr/bin/env python
"""Validate that docs/api/openapi.yaml is well-formed and internally
consistent (every $ref resolves). This does NOT verify the spec matches
backend/app/http.py's actual routes -- the router is a chain of imperative
if-statements, not a declarative table, so that cross-check has to stay a
manual step when routes change (see the note at the top of the spec itself).
Catching syntax errors and dangling $ref here is still worth automating.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.yaml"
REF_PATTERN = re.compile(r'\$ref: "#/components/([a-zA-Z]+)/([a-zA-Z0-9]+)"')


def main() -> int:
    text = SPEC_PATH.read_text(encoding="utf-8")
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError as error:
        print(f"invalid YAML: {error}", file=sys.stderr)
        return 1

    if "paths" not in spec or "components" not in spec:
        print("spec is missing 'paths' or 'components'", file=sys.stderr)
        return 1

    missing = [
        f"{kind}/{name}"
        for kind, name in REF_PATTERN.findall(text)
        if name not in spec["components"].get(kind, {})
    ]
    if missing:
        print(f"unresolved $ref targets: {missing}", file=sys.stderr)
        return 1

    operation_count = sum(len(methods) for methods in spec["paths"].values())
    print(f"OK: {len(spec['paths'])} paths, {operation_count} operations, {len(spec['components']['schemas'])} schemas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
