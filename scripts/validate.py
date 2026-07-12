"""Validate committed mapping data against the repo schemas. Run in CI on every PR.

For each ``data/<NN>-<source>__<target>/`` bridge folder:
  - ``metadata.json`` is validated against ``schema/metadata.schema.json``.
  - each present ``biosphere.json`` / ``technosphere.json`` randonneur package is validated
    against ``schema/randonneur-package.schema.json``.
  - when ``metadata.target_proprietary`` is true, every entry's ``target`` dict must expose
    only ``{database, code}`` (no proprietary names leak into the open repo).
  - each ``kind`` declared in metadata whose ``entry_counts`` is > 0 must have its package
    file present.

Empty scaffold bridges (metadata only, all counts 0) validate. Exits non-zero on any error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
PACKAGE_SCHEMA = json.loads((SCHEMA_DIR / "randonneur-package.schema.json").read_text())
METADATA_SCHEMA = json.loads((SCHEMA_DIR / "metadata.schema.json").read_text())
KINDS = ("biosphere", "technosphere")
_VERBS = ("replace", "update", "delete", "create")


def _entries(package: dict):
    for verb in _VERBS:
        yield from package.get(verb, [])


def validate_bridge(bridge: Path, errors: list[str]) -> None:
    meta_path = bridge / "metadata.json"
    if not meta_path.exists():
        errors.append(f"{bridge.name}: missing metadata.json")
        return
    meta = json.loads(meta_path.read_text())
    try:
        jsonschema.validate(meta, METADATA_SCHEMA)
    except jsonschema.ValidationError as exc:
        errors.append(f"{bridge.name}/metadata.json: {exc.message}")
        return

    proprietary = meta.get("target_proprietary", False)
    counts = meta.get("entry_counts") or {}

    for kind in KINDS:
        path = bridge / f"{kind}.json"
        if not path.exists():
            if counts.get(kind, 0) > 0:
                errors.append(
                    f"{bridge.name}: metadata declares {counts[kind]} '{kind}' entries "
                    f"but {kind}.json is missing"
                )
            continue
        package = json.loads(path.read_text())
        try:
            jsonschema.validate(package, PACKAGE_SCHEMA)
        except jsonschema.ValidationError as exc:
            errors.append(f"{bridge.name}/{kind}.json: {exc.message}")
            continue
        if proprietary:
            for i, entry in enumerate(_entries(package)):
                extra = set(entry.get("target") or {}) - {"database", "code"}
                if extra:
                    errors.append(
                        f"{bridge.name}/{kind}.json entry {i}: target_proprietary bridge must "
                        f"expose only {{database, code}}; found extra target keys {sorted(extra)}"
                    )


def main() -> int:
    errors: list[str] = []
    bridges = sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    for bridge in bridges:
        validate_bridge(bridge, errors)
    if errors:
        print("Data validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"Data validation passed: {len(bridges)} bridge(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
