# `_dispatch.py` provenance — a vendored copy of trident

`src/bulk_rna_preprocessing/_dispatch.py` is a **vendored copy** of
[`swarbricklab/trident`](https://github.com/swarbricklab/trident)
(`src/trident/_dispatch.py` @ `85de91d`, v0.0.1). trident is the standalone
"workflow / CLI / library trinity" dispatcher; this workflow does not install it as
a runtime dependency, so the dispatcher travels *inside* the package instead.

## Why vendored (not a dependency)

The shim runs inside the rule's execution environment, so the dispatcher must be
importable there. This workflow is **not** pip-installed into its `--use-conda`
rule env — the shims bootstrap `sys.path` to `src/` via `params.pkg_src` (see
below). Vendoring lets trident ride along with the package through that same
mechanism, so there is nothing extra to add to `env/environment.yaml`. The
trade-off is drift: **do not edit this copy** — change trident and re-sync.

### Re-syncing

```bash
cp ../trident/src/trident/_dispatch.py src/bulk_rna_preprocessing/_dispatch.py
# then re-apply the two vendored-copy deltas below and bump the pinned sha/version.
```

The only deltas from upstream are provenance, not behaviour:
1. the module docstring header (marks it a vendored copy + records the trident sha);
2. `_pkg_version()` returns the pinned `"0.0.1+vendored"` string, because trident
   is not importable here (upstream reads `trident.__version__`).

Everything else — `dispatch`, `dispatch_by_rule`, `as_click_command`, `build_cli`,
the binding/coercion/telemetry — is byte-identical to trident. The spotty-specific
bits that an earlier vendoring carried (a hardcoded `_SHORT_BY_PARAM`, JSON-only
config loader, tool-specific output-name heuristics) were **generalised upstream in
trident** and are gone here as a result.

## Field finding that still lives here (not in trident): the `--use-conda` gotcha

**Snakemake scrubs `PYTHONPATH` for `--use-conda` jobs** (verified: conda
activation itself preserves it; the job just doesn't receive it). So a non-installed
src-layout package can't be imported via a `PYTHONPATH` export. Each rule passes
`params.pkg_src` (the `src/` dir, from `workflow.basedir`) and the shim does
`sys.path.insert(0, snakemake.params.pkg_src)` *inside* the job. This is documented
generically in trident's `docs/adopt.md`; the concrete wiring lives in this repo's
`workflow/Snakefile` + `workflow/scripts/*.py`.
