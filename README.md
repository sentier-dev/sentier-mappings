# sentier-mappings

Cross-source **mappings** for the Sentier platform — the bridges that link
inventory, methods, and background databases at calculation time. A
cross-cutting **Data Layer** repo: it holds loadable artifacts only, no
fetch/parse/calculate code.

- **Fed by:** `sentier-importers` (PR / Push) and the Application Layer.
- **Read by:** `sentier-platform` (resolved link tables at calc time).
- **Format:** [randonneur](https://github.com/brightway-lca/randonneur) JSON
  datapackages — the Brightway data-migration format.

Keeping mappings in their own repo means a new inventory source or method can be
added without touching either side of a bridge, and upstream churn (renamed
flows, renamed processes) is absorbed in one isolated place.

## Layout

```
schema/   # randonneur version pin + conventions + JSON Schemas (the contract)
data/     # randonneur packages, one folder per source→target pair
```

## The three mapping kinds

| Kind | Bridge spans | File | Target encoding |
|---|---|---|---|
| **Foreground → background** | inventory source → ecoinvent | `technosphere.json` (or its numbered form `technosphere-<n>-<slug>.json`) | `{database, code}` — opaque code **only** |
| **Process → process** | inventory source → inventory source (Sentier) | `technosphere.json` (or its numbered form `technosphere-<n>-<slug>.json`) | full open identifiers |
| **Elementary flow ↔ CF** | inventory flows → method flow keys | `biosphere.json` (or its numbered form `biosphere-<n>-<slug>.json`) | full open identifiers |

## No proprietary ecoinvent data

Where a bridge targets ecoinvent, the target carries **only** the Brightway
activity `code` (an opaque, stable pointer) plus a `database` tag — never
`name`, `reference product`, `location`, amounts, or flows. A licensed ecoinvent
holder resolves the code locally at link time. Such bridges set
`"target_proprietary": true` in their `metadata.json`. All non-ecoinvent
identifiers (Sentier processes, method flow keys) are open and stored in full.

## Data

Organized **one folder per source→target pair**:

```
data/
  agribalyse-3.2__ecoinvent-3.9.1/   # foreground→background
  agribalyse-3.2__ef-3.1/            # elementary flow↔CF
  bafu-2026-v1__ef-3.1/              # elementary flow↔CF, four ordered packages (worked example below)
```

Convention: `data/<source>__<target>/`, where `<source>` and `<target>` are
lower-kebab, version-suffixed datasource ids. A pair with one package per kind
names it `<kind>.json`; a pair with several packages of one kind (built up over
time, e.g. `bafu-2026-v1__ef-3.1`) numbers them `<kind>-<n>-<slug>.json`, `n`
from 1. That number is **build order and precedence within the pair only**,
never a global rank across unrelated pairs: package `n` was built over what
packages `1..n-1` left unmapped, so a consumer applies them in that order (an
earlier file wins on the same source key), and the validator guarantees the
files of one pair never actually conflict. `bafu-2026-v1__ef-3.1` holds
`biosphere-1-curated.json` (hand-reviewed), `biosphere-2-inferred.json` (built
over what curated lacks), `biosphere-3-matched.json` (built over what curated
and inferred lack), and `biosphere-4-nomenclature.json` (built over what all
three lack), plus a pair-level `coverage.json` sidecar and per-package review
sidecars. Each pair folder holds one `metadata.json` identity file listing its
packages in order; package payloads are pushed by `sentier-importers`, and a
not-yet-populated pair ships `.gitkeep` + a `metadata.json` stub with a
0-entry package only.

## Schema

`schema/` is the contract `sentier-importers` validates against before opening a
delivery PR — a data artifact, not runtime code. It pins the randonneur version,
documents the conventions, and ships JSON Schemas for the package profile and for
`metadata.json`. See [schema/](./schema/).

## License

MIT — open by default, client-loadable.
