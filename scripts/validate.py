"""Validate committed mapping data against the repo schemas. Run in CI on every PR.

For each ``data/<NN>-<source>__<target>/`` bridge folder:
  - ``metadata.json`` is validated against ``schema/metadata.schema.json``.
  - each present ``biosphere.json`` / ``technosphere.json`` randonneur package is validated
    against ``schema/randonneur-package.schema.json``.
  - when ``metadata.target_proprietary`` is true, every entry's ``target`` dict must expose
    only ``{database, code}`` (no proprietary names leak into the open repo).
  - each ``kind`` declared in metadata whose ``entry_counts`` is > 0 must have its package
    file present.
  - unit consistency (issue #8): when both ``source.unit`` and ``target.unit`` are
    recognised, a cross-dimension pair (e.g. activity kBq -> mass kilogram) must carry an
    explicit ``conversion_factor``, and a same-dimension magnitude change (Bq -> kBq) must
    carry exactly the right one. Unrecognised unit strings are skipped, not guessed at.

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


# Recognised unit spellings -> (dimension, scale relative to the dimension's base unit).
# Deliberately small: only spellings that actually appear in committed payloads belong
# here. An unrecognised spelling is skipped by the unit check, never guessed at.
_UNITS: dict[str, tuple[str, float]] = {
    "kg": ("mass", 1.0), "kilogram": ("mass", 1.0), "g": ("mass", 1e-3),
    "t": ("mass", 1e3), "ton": ("mass", 1e3), "tonne": ("mass", 1e3),
    "bq": ("activity", 1.0), "kbq": ("activity", 1e3), "kilo becquerel": ("activity", 1e3),
    "m3": ("volume", 1.0), "cubic meter": ("volume", 1.0),
    "l": ("volume", 1e-3), "litre": ("volume", 1e-3),
    "m2": ("area", 1.0), "square meter": ("area", 1.0),
    "m2a": ("area-time", 1.0), "m2*a": ("area-time", 1.0),
    "square meter-year": ("area-time", 1.0),
    "m3y": ("volume-time", 1.0), "m3*a": ("volume-time", 1.0),
    "cubic meter-year": ("volume-time", 1.0),
    "mj": ("energy", 1.0), "megajoule": ("energy", 1.0), "kwh": ("energy", 3.6),
}

#: Same-dimension factors are checked against the scale ratio to this tolerance.
_REL_TOL = 1e-9


def _entries(package: dict):
    for verb in _VERBS:
        yield from package.get(verb, [])


def check_entry_units(entry: dict) -> str | None:
    """One error string for a unit-inconsistent entry, or None.

    Only judges entries whose two unit spellings are both recognised; randonneur
    treats a missing ``conversion_factor`` as 1.0, so a silent cross-dimension or
    cross-magnitude pair corrupts every downstream calculation.
    """
    source_unit = str((entry.get("source") or {}).get("unit") or "").strip().lower()
    target_unit = str((entry.get("target") or {}).get("unit") or "").strip().lower()
    if source_unit not in _UNITS or target_unit not in _UNITS:
        return None
    (source_dim, source_scale) = _UNITS[source_unit]
    (target_dim, target_scale) = _UNITS[target_unit]
    factor = entry.get("conversion_factor")
    if source_dim != target_dim:
        if factor is None:
            return (
                f"source unit '{source_unit}' ({source_dim}) -> target unit "
                f"'{target_unit}' ({target_dim}) crosses dimensions without a "
                f"conversion_factor"
            )
        return None  # an explicit factor asserts a deliberate conversion (e.g. water kg -> m3)
    expected = source_scale / target_scale
    actual = 1.0 if factor is None else float(factor)
    if abs(actual - expected) > _REL_TOL * expected:
        return (
            f"'{source_unit}' -> '{target_unit}' needs conversion_factor "
            f"{expected:g}, entry carries {actual:g}"
        )
    return None


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
        for i, entry in enumerate(_entries(package)):
            if proprietary:
                extra = set(entry.get("target") or {}) - {"database", "code"}
                if extra:
                    errors.append(
                        f"{bridge.name}/{kind}.json entry {i}: target_proprietary bridge must "
                        f"expose only {{database, code}}; found extra target keys {sorted(extra)}"
                    )
            unit_error = check_entry_units(entry)
            if unit_error:
                errors.append(f"{bridge.name}/{kind}.json entry {i}: {unit_error}")


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
