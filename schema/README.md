# schema/

The **contract** for the randonneur mapping packages in `../data/`. This is a
data artifact `sentier-importers` reads to validate packages against before
opening a delivery PR — not runtime code. No mapping logic ships here.

| file | describes |
|---|---|
| `randonneur-package.schema.json` | JSON Schema for a mapping package (our randonneur profile) |
| `metadata.schema.json` | JSON Schema for each pair's `metadata.json` |

## randonneur version

Mapping packages follow the [randonneur](https://github.com/brightway-lca/randonneur)
datapackage format. The exact randonneur spec version this repo targets is
recorded here.

## The three mapping kinds

| kind | verb(s) | file | target encoding |
|---|---|---|---|
| foreground → background | `replace` | `technosphere.json` (or its numbered form `technosphere-<n>-<slug>.json`) | `{database, code}` — opaque ecoinvent code only |
| process → process | `replace` | `technosphere.json` (or its numbered form `technosphere-<n>-<slug>.json`) | full open identifiers |
| elementary flow ↔ CF | `replace` / `update` | `biosphere.json` (or its numbered form `biosphere-<n>-<slug>.json`) | full open identifiers |

- **`replace`** — rewrite a source edge's target to the mapped target.
- **`update`** — adjust fields in place (e.g. unit normalization via
  `conversion_factor`) without changing identity.
- `delete` / `create` are available per the randonneur spec but unused by the
  current skeleton.

## No proprietary ecoinvent data

When a bridge targets ecoinvent (`metadata.json.target_proprietary: true`), every
`target` dict carries **only** `database` + `code` (the Brightway activity code,
an opaque pointer) — never `name`, `reference product`, `location`, amounts, or
flows. A licensed ecoinvent holder resolves the code locally. All other
identifiers (Sentier processes, method flow keys) are open and stored in full.

## Precedence

Precedence is per-pair, not global. A pair with several packages of one kind
numbers them `<kind>-<n>-<slug>.json`, `n` from 1: that number is build order
and precedence **within the pair only**, never a rank across unrelated pairs
(different pairs never conflict, so no global tie-break is needed). Package
`n` was built over what packages `1..n-1` left unmapped, so an earlier file
wins on a shared source key; `scripts/validate.py` enforces that the packages
of one pair never actually disagree, so the order records provenance and
confidence more than it resolves live conflicts. `metadata.json`'s `packages`
list carries this order explicitly, one entry per package.
