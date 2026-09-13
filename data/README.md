# data/

[randonneur](https://github.com/brightway-lca/randonneur) JSON mapping packages,
**one subfolder per source→target pair**:

```
data/
  agribalyse-3.2__ecoinvent-3.9.1/
  agribalyse-3.2__ef-3.1/
  bafu-2026-v1__ef-3.1/
```

Convention: `data/<source>__<target>/`, where `<source>` and `<target>` are
lower-kebab, version-suffixed datasource ids (`agribalyse-3.2`,
`ecoinvent-3.9.1`, `ef-3.1`, `bafu-2026-v1`). There is no rank prefix on the
folder name; different pairs never conflict, so no global tie-break is needed.

A **pair** maps one source identifier space onto one target space. Each folder
holds an ordered set of randonneur package files, one `metadata.json` identity
file, and any non-normative sidecars:

| kind of file | naming | meaning |
|---|---|---|
| package, one per kind | `technosphere.json` / `biosphere.json` | the only package of that kind in the pair |
| package, several per kind | `<kind>-<n>-<slug>.json`, `n` from 1 | build order **and** precedence within this pair only |
| identity | `metadata.json` | pair source/target/title + the ordered `packages` list |
| sidecar | any other flat filename, listed in `metadata.json` | non-normative review or coverage data |

The `<n>` on a numbered package is never a global rank: it only orders the
files within one pair. Package `n` was built over what packages `1..n-1` left
unmapped for that same pair, so applying them in file order and letting an
earlier file win on a shared source key reproduces the intended precedence,
and the validator (`scripts/validate.py`) enforces that the packages of one
pair never actually disagree on a source key, so in practice this is a
provenance and confidence record, not a live conflict resolver.

## Worked example: `bafu-2026-v1__ef-3.1`

Four biosphere packages, each built over what the earlier ones leave unmapped:

```
bafu-2026-v1__ef-3.1/
  metadata.json                   identity + the four packages in order
  biosphere-1-curated.json        hand-reviewed reference bridge
  biosphere-2-inferred.json       inferred via Eaternity's biosphere3 pair family
  biosphere-3-matched.json        public name/synonym/CAS/land/alias matching
  biosphere-4-nomenclature.json   EF flows with no characterization factor, names only
  coverage.json                   pair-level sidecar: one row per BAFU flow, which package (if any) covers it
  land_use_review.json, subcompartment_review.json, inference_review.json   per-package review sidecars
```

See [../schema/](../schema/) for the package profile and the `metadata.json`
schema. Package payloads are pushed by `sentier-importers`; a pair not yet
populated ships `.gitkeep` + a `metadata.json` stub whose single package
declares `entries: 0` with no file present.
