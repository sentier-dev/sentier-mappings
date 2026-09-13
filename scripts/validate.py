"""Validate committed mapping data against the repo schemas. Run in CI on every PR.

For each ``data/<source>__<target>/`` pair folder:
  - ``metadata.json`` is validated against ``schema/metadata.schema.json``.
  - the folder name must equal ``metadata.source + "__" + metadata.target``.
  - each package listed in ``metadata.packages`` is validated against
    ``schema/randonneur-package.schema.json``.
  - a package's ``entries`` must equal the real entry count of its file (``replace`` +
    ``update`` + ``delete`` + ``create``); ``entries: 0`` is the only count allowed for a
    package whose file is not present (a stub, e.g. the technosphere placeholder).
  - a package's ``order`` must equal its 1-based position in ``metadata.packages``, and,
    for a file named ``<kind>-<n>-<slug>.json``, ``n`` must equal ``order``. A pair with a
    single package of a kind names it ``<kind>.json``; a pair with several packages of one
    kind must use the numbered form for every one of them.
  - when ``metadata.target_proprietary`` is true, every entry's ``target`` dict must expose
    only ``{database, code}`` (no proprietary names leak into the open repo).
  - unit consistency (issue #8): when both ``source.unit`` and ``target.unit`` are
    recognised, a cross-dimension pair (e.g. activity kBq -> mass kilogram) must carry an
    explicit ``conversion_factor``, and a same-dimension magnitude change (Bq -> kBq) must
    carry exactly the right one -- unless the entry's ``comment`` names a "mass fraction"
    (a stoichiometric composite, e.g. kg TiO2 -> kg Ti), in which case any same-dimension
    factor is accepted. Unrecognised unit strings are skipped, not guessed at.
  - no two entries may share the same source key, either within one package file or across
    every package file of one pair (PR #10): randonneur applies entries in order, so
    duplicates silently shadow. The key is ``(source.code, source.context)`` when
    ``source.code`` is present, else ``(source.name, source.context)``; an entry with
    neither is not keyed on and is skipped.
  - every ``*.json`` file in a pair folder must be ``metadata.json``, a package listed in
    ``metadata.packages``, or a sidecar listed at package or pair level; anything else is a
    stray file and fails validation. A listed sidecar whose file is missing is likewise an
    error.

Empty scaffold pairs (metadata only, a single 0-entry package with no file) validate.
Malformed JSON in ``metadata.json`` or a package file is reported as an error line, not a
traceback. Exits non-zero on any error.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
DATA_DIR = ROOT / "data"
_VERBS = ("replace", "update", "delete", "create")

#: A numbered package filename: <kind>-<n>-<slug>.json, n from 1, slug lower-kebab.
_NUMBERED_NAME_RE = re.compile(
    r"^(?P<kind>biosphere|technosphere)-(?P<n>\d+)-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.json$"
)


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text())


def _entries(package: dict):
    for verb in _VERBS:
        yield from package.get(verb, [])


# Recognised unit spellings -> (dimension, scale relative to the dimension's base unit).
# Deliberately small: only spellings that actually appear in committed payloads belong
# here. An unrecognised spelling is skipped by the unit check, never guessed at.
_UNITS: dict[str, tuple[str, float]] = {
    "kg": ("mass", 1.0), "kilogram": ("mass", 1.0), "g": ("mass", 1e-3),
    "t": ("mass", 1e3), "ton": ("mass", 1e3), "tonne": ("mass", 1e3),
    "bq": ("activity", 1.0), "kbq": ("activity", 1e3), "kilo becquerel": ("activity", 1e3),
    "m3": ("volume", 1.0), "cubic meter": ("volume", 1.0), "nm3": ("volume", 1.0),
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

#: An entry comment containing this phrase (case-insensitive) asserts a deliberate
#: stoichiometric composite (e.g. kg TiO2 -> kg Ti), exempting it from the same-dimension
#: scale-ratio check.
_MASS_FRACTION_PHRASE = "mass fraction"


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
    if factor is None:
        actual = 1.0
    else:
        try:
            actual = float(factor)
        except (TypeError, ValueError):
            return f"conversion_factor {factor!r} is not numeric"
    if abs(actual - expected) > _REL_TOL * expected:
        comment = str(entry.get("comment") or "")
        if _MASS_FRACTION_PHRASE in comment.lower():
            return None  # stoichiometric composite (e.g. kg TiO2 -> kg Ti): a different ratio is expected
        return (
            f"'{source_unit}' -> '{target_unit}' needs conversion_factor "
            f"{expected:g}, entry carries {actual:g}"
        )
    return None


def _check_package_duplicate_keys(
    package: dict, file_name: str, seen: dict[tuple, tuple[str, int]], errors: list[str], pair_name: str
) -> None:
    """Two entries sharing the same source key are indistinguishable to a keyed consumer,
    and randonneur applies entries in order, so the later one silently shadows the earlier
    (issue found by Eaternity in PR #10). The key is (source.code, source.context) when
    source.code is present, else (source.name, source.context); an entry with neither is
    not keyed on and is skipped. Checked across every package file of the pair, not just
    within one file."""
    for i, entry in enumerate(_entries(package)):
        source = entry.get("source") or {}
        identifier = source.get("code") or source.get("name")
        if not identifier:
            continue  # nothing to key on
        key = (identifier, tuple(source.get("context") or ()))
        if key in seen:
            (other_file, other_i) = seen[key]
            errors.append(
                f"{pair_name}: source key ({identifier!r}, context={list(key[1])}) in "
                f"{file_name} entry {i} duplicates {other_file} entry {other_i}"
            )
        else:
            seen[key] = (file_name, i)


def _check_package_naming(pair_name: str, packages: list[dict], errors: list[str]) -> None:
    by_kind: dict[str, list[dict]] = {}
    for pkg in packages:
        by_kind.setdefault(pkg.get("kind"), []).append(pkg)
    for kind, group in by_kind.items():
        if len(group) == 1:
            expected = f"{kind}.json"
            if group[0].get("file") != expected:
                errors.append(
                    f"{pair_name}: single '{kind}' package must be named '{expected}', "
                    f"found '{group[0].get('file')}'"
                )
            continue
        for pkg in group:
            file_name = pkg.get("file", "")
            match = _NUMBERED_NAME_RE.match(file_name)
            if not match or match.group("kind") != kind:
                errors.append(
                    f"{pair_name}: with several '{kind}' packages, '{file_name}' must be "
                    f"named '{kind}-<n>-<slug>.json'"
                )
                continue
            n = int(match.group("n"))
            if n != pkg.get("order"):
                errors.append(
                    f"{pair_name}: '{file_name}' filename number {n} does not match "
                    f"declared order {pkg.get('order')}"
                )


def _load_json(path: Path, label: str, errors: list[str]) -> dict | None:
    """Parse a JSON file, or append one error line and return None on malformed JSON."""
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
        return None


def validate_pair(
    pair_dir: Path, errors: list[str], *, metadata_schema: dict, package_schema: dict
) -> None:
    meta_path = pair_dir / "metadata.json"
    if not meta_path.exists():
        errors.append(f"{pair_dir.name}: missing metadata.json")
        return
    meta = _load_json(meta_path, f"{pair_dir.name}/metadata.json", errors)
    if meta is None:
        return
    try:
        jsonschema.validate(meta, metadata_schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"{pair_dir.name}/metadata.json: {exc.message}")
        return

    expected_name = f"{meta['source']}__{meta['target']}"
    if pair_dir.name != expected_name:
        errors.append(
            f"{pair_dir.name}: folder name must equal source__target ('{expected_name}')"
        )

    proprietary = meta.get("target_proprietary", False)
    packages = meta.get("packages", [])

    for i, pkg in enumerate(packages, start=1):
        if pkg.get("order") != i:
            errors.append(
                f"{pair_dir.name}: package '{pkg.get('file')}' has order {pkg.get('order')}, "
                f"expected {i} (its position in packages)"
            )

    _check_package_naming(pair_dir.name, packages, errors)

    accounted: set[str] = {"metadata.json"}
    for sidecar_name in meta.get("sidecars", []):
        accounted.add(sidecar_name)
        if not (pair_dir / sidecar_name).exists():
            errors.append(
                f"{pair_dir.name}: sidecar '{sidecar_name}' listed at pair level but the file "
                f"is missing"
            )

    duplicate_seen: dict[tuple, tuple[str, int]] = {}

    for pkg in packages:
        file_name = pkg["file"]
        accounted.add(file_name)
        for sidecar_name in pkg.get("sidecars", []):
            accounted.add(sidecar_name)
            if not (pair_dir / sidecar_name).exists():
                errors.append(
                    f"{pair_dir.name}: sidecar '{sidecar_name}' listed for package "
                    f"'{file_name}' but the file is missing"
                )

        path = pair_dir / file_name
        declared_entries = pkg.get("entries", 0)
        if not path.exists():
            if declared_entries != 0:
                errors.append(
                    f"{pair_dir.name}: package '{file_name}' declares {declared_entries} "
                    f"entries but the file is missing"
                )
            continue

        package = _load_json(path, f"{pair_dir.name}/{file_name}", errors)
        if package is None:
            continue
        try:
            jsonschema.validate(package, package_schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"{pair_dir.name}/{file_name}: {exc.message}")
            continue

        actual_entries = sum(1 for _ in _entries(package))
        if actual_entries != declared_entries:
            errors.append(
                f"{pair_dir.name}/{file_name}: metadata declares {declared_entries} entries, "
                f"file holds {actual_entries}"
            )

        for i, entry in enumerate(_entries(package)):
            if proprietary:
                extra = set(entry.get("target") or {}) - {"database", "code"}
                if extra:
                    errors.append(
                        f"{pair_dir.name}/{file_name} entry {i}: target_proprietary pair must "
                        f"expose only {{database, code}}; found extra target keys {sorted(extra)}"
                    )
            unit_error = check_entry_units(entry)
            if unit_error:
                errors.append(f"{pair_dir.name}/{file_name} entry {i}: {unit_error}")

        _check_package_duplicate_keys(package, file_name, duplicate_seen, errors, pair_dir.name)

    for json_path in sorted(pair_dir.glob("*.json")):
        if json_path.name not in accounted:
            errors.append(
                f"{pair_dir.name}: stray file '{json_path.name}' is neither metadata.json, "
                f"a listed package, nor a listed sidecar"
            )


def main(data_dir: Path = DATA_DIR) -> int:
    metadata_schema = _load_schema("metadata.schema.json")
    package_schema = _load_schema("randonneur-package.schema.json")
    errors: list[str] = []
    pairs = sorted(p for p in data_dir.iterdir() if p.is_dir())
    for pair_dir in pairs:
        validate_pair(
            pair_dir, errors, metadata_schema=metadata_schema, package_schema=package_schema
        )
    if errors:
        print("Data validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"Data validation passed: {len(pairs)} pair(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
