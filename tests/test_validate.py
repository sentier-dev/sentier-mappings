"""Tests for scripts/validate.py: pair-folder validation, metadata schema, package
naming/order rules, entry counts, cross-file duplicate keys, unit consistency, and the
mass-fraction stoichiometric exemption. Each test builds a small pair folder under
tmp_path and calls the validator functions directly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _metadata_schema() -> dict:
    return validate._load_schema("metadata.schema.json")


def _package_schema() -> dict:
    return validate._load_schema("randonneur-package.schema.json")


def _validate(pair_dir: Path) -> list[str]:
    errors: list[str] = []
    validate.validate_pair(
        pair_dir, errors, metadata_schema=_metadata_schema(), package_schema=_package_schema()
    )
    return errors


def _entry(code="e1", unit=None, target_unit=None, factor=None, comment=None) -> dict:
    entry: dict = {"source": {"code": code, "context": ["air"]}, "target": {"flow": "x"}}
    if unit:
        entry["source"]["unit"] = unit
    if target_unit:
        entry["target"]["unit"] = target_unit
    if factor is not None:
        entry["conversion_factor"] = factor
    if comment is not None:
        entry["comment"] = comment
    return entry


def _basic_metadata(packages: list[dict]) -> dict:
    return {
        "source": "source-1",
        "target": "target-1",
        "title": "t",
        "target_proprietary": False,
        "schema_version": "0.2.0",
        "packages": packages,
    }


def test_valid_single_package_pair_passes(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 2}]),
    )
    _write_json(
        pair / "biosphere.json",
        {"name": "x", "version": "0.1.0", "replace": [_entry("e1"), _entry("e2")]},
    )
    assert _validate(pair) == []


def test_zero_entry_stub_with_absent_file_passes(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "technosphere.json", "kind": "technosphere", "order": 1, "entries": 0}])
    meta["target_proprietary"] = True
    _write_json(pair / "metadata.json", meta)
    assert _validate(pair) == []


def test_stray_json_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}]),
    )
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0"})
    _write_json(pair / "stray.json", {"whatever": True})
    errors = _validate(pair)
    assert any("stray" in e for e in errors)


def test_entries_mismatch_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 5}]),
    )
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0", "replace": [_entry("e1")]})
    errors = _validate(pair)
    assert any("declares 5 entries" in e for e in errors)


def test_cross_file_duplicate_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata(
            [
                {"file": "biosphere-1-a.json", "kind": "biosphere", "order": 1, "entries": 1},
                {"file": "biosphere-2-b.json", "kind": "biosphere", "order": 2, "entries": 1},
            ]
        ),
    )
    _write_json(pair / "biosphere-1-a.json", {"name": "a", "version": "0.1.0", "replace": [_entry("dup")]})
    _write_json(pair / "biosphere-2-b.json", {"name": "b", "version": "0.1.0", "replace": [_entry("dup")]})
    errors = _validate(pair)
    assert any(
        "duplicates" in e and "biosphere-1-a.json" in e and "biosphere-2-b.json" in e for e in errors
    )


def test_folder_name_mismatch_fails(tmp_path):
    pair = tmp_path / "wrong-name"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}]),
    )
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0"})
    errors = _validate(pair)
    assert any("folder name must equal source__target" in e for e in errors)


def test_single_package_must_not_use_numbered_name(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere-1-x.json", "kind": "biosphere", "order": 1, "entries": 0}]),
    )
    _write_json(pair / "biosphere-1-x.json", {"name": "x", "version": "0.1.0"})
    errors = _validate(pair)
    assert any("must be named 'biosphere.json'" in e for e in errors)


def test_several_packages_require_numbered_form(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata(
            [
                {"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0},
                {"file": "biosphere-2-b.json", "kind": "biosphere", "order": 2, "entries": 0},
            ]
        ),
    )
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0"})
    _write_json(pair / "biosphere-2-b.json", {"name": "y", "version": "0.1.0"})
    errors = _validate(pair)
    assert any("must be named 'biosphere-<n>-<slug>.json'" in e for e in errors)


def test_stoichiometric_factor_accepted_with_phrase(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 1}]),
    )
    entry = _entry("e1", unit="kg", target_unit="kg", factor=0.6, comment="mass fraction Ti in TiO2")
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0", "replace": [entry]})
    assert _validate(pair) == []


def test_stoichiometric_factor_rejected_without_phrase(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 1}]),
    )
    entry = _entry("e1", unit="kg", target_unit="kg", factor=0.6)
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0", "replace": [entry]})
    errors = _validate(pair)
    assert any("needs conversion_factor" in e for e in errors)


def test_proprietary_leak_fails_and_clean_target_passes(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "technosphere.json", "kind": "technosphere", "order": 1, "entries": 1}])
    meta["target_proprietary"] = True
    _write_json(pair / "metadata.json", meta)
    leaky_entry = {"source": {"code": "e1"}, "target": {"database": "ecoinvent-3.9.1", "code": "abc", "name": "leaked"}}
    _write_json(pair / "technosphere.json", {"name": "x", "version": "0.1.0", "replace": [leaky_entry]})
    errors = _validate(pair)
    assert any("expose only {database, code}" in e for e in errors)


def test_proprietary_clean_target_passes(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "technosphere.json", "kind": "technosphere", "order": 1, "entries": 1}])
    meta["target_proprietary"] = True
    _write_json(pair / "metadata.json", meta)
    clean_entry = {"source": {"code": "e1"}, "target": {"database": "ecoinvent-3.9.1", "code": "abc"}}
    _write_json(pair / "technosphere.json", {"name": "x", "version": "0.1.0", "replace": [clean_entry]})
    assert _validate(pair) == []


def test_numbered_filename_number_mismatches_order_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata(
            [
                {"file": "biosphere-1-a.json", "kind": "biosphere", "order": 1, "entries": 0},
                {"file": "biosphere-3-b.json", "kind": "biosphere", "order": 2, "entries": 0},
            ]
        ),
    )
    _write_json(pair / "biosphere-1-a.json", {"name": "a", "version": "0.1.0"})
    _write_json(pair / "biosphere-3-b.json", {"name": "b", "version": "0.1.0"})
    errors = _validate(pair)
    assert any("filename number 3 does not match declared order 2" in e for e in errors)


def test_order_not_equal_to_list_position_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata(
            [
                {"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0},
                {"file": "technosphere.json", "kind": "technosphere", "order": 3, "entries": 0},
            ]
        ),
    )
    errors = _validate(pair)
    assert any("expected 2 (its position in packages)" in e for e in errors)


def test_entries_positive_with_missing_file_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 5}]),
    )
    errors = _validate(pair)
    assert any("declares 5 entries but the file is missing" in e for e in errors)


def test_cross_dimension_pair_without_conversion_factor_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 1}]),
    )
    entry = _entry("e1", unit="kg", target_unit="bq")
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0", "replace": [entry]})
    errors = _validate(pair)
    assert any("crosses dimensions without a conversion_factor" in e for e in errors)


def test_metadata_with_leftover_rank_key_rejected(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}])
    meta["rank"] = 3
    _write_json(pair / "metadata.json", meta)
    errors = _validate(pair)
    assert any("rank" in e for e in errors)


def test_listed_sidecar_missing_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}])
    meta["sidecars"] = ["coverage.json"]
    _write_json(pair / "metadata.json", meta)
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0"})
    # coverage.json is listed but never written to disk.
    errors = _validate(pair)
    assert any(
        "sidecar 'coverage.json' listed at pair level but the file is missing" in e for e in errors
    )


def test_name_keyed_duplicate_across_files_fails(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata(
            [
                {"file": "biosphere-1-a.json", "kind": "biosphere", "order": 1, "entries": 1},
                {"file": "biosphere-2-b.json", "kind": "biosphere", "order": 2, "entries": 1},
            ]
        ),
    )
    dup_entry = {"source": {"name": "Carbon dioxide", "context": ["air"]}, "target": {"flow": "x"}}
    _write_json(pair / "biosphere-1-a.json", {"name": "a", "version": "0.1.0", "replace": [dup_entry]})
    _write_json(pair / "biosphere-2-b.json", {"name": "b", "version": "0.1.0", "replace": [dup_entry]})
    errors = _validate(pair)
    assert any(
        "duplicates" in e and "biosphere-1-a.json" in e and "biosphere-2-b.json" in e for e in errors
    )


def test_malformed_metadata_json_reported_cleanly(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    (pair / "metadata.json").write_text("{not valid json")
    errors = _validate(pair)
    assert any("invalid JSON" in e for e in errors)


def test_malformed_package_json_reported_cleanly(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}]),
    )
    (pair / "biosphere.json").write_text("{not valid json")
    errors = _validate(pair)
    assert any("invalid JSON" in e for e in errors)


def test_schema_version_0_1_0_rejected(tmp_path):
    pair = tmp_path / "source-1__target-1"
    pair.mkdir()
    meta = _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}])
    meta["schema_version"] = "0.1.0"
    _write_json(pair / "metadata.json", meta)
    errors = _validate(pair)
    assert any("metadata.json" in e for e in errors) and any("0.2.0" in e for e in errors)


def test_main_runs_over_a_data_directory(tmp_path):
    data_dir = tmp_path / "data"
    pair = data_dir / "source-1__target-1"
    pair.mkdir(parents=True)
    _write_json(
        pair / "metadata.json",
        _basic_metadata([{"file": "biosphere.json", "kind": "biosphere", "order": 1, "entries": 0}]),
    )
    _write_json(pair / "biosphere.json", {"name": "x", "version": "0.1.0"})
    assert validate.main(data_dir) == 0
