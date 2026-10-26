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

## Wiring: one generic shim, routed by rule name

Every rule runs the same `workflow/scripts/_run.py`, which calls
`dispatch_by_rule(globals(), "bulk_rna_preprocessing._steps")` — mapping
`snakemake.rule` to `_steps.<rule>.run` (so **rule name == step module name**; each
rule carries an `# impl:` breadcrumb). No per-rule shim files; the rule name is the
pointer to the code.

### The `--use-conda` gotcha (why the shim bootstraps `sys.path`)

**Snakemake scrubs `PYTHONPATH` for `--use-conda` jobs** (verified: conda activation
itself preserves it; the job just doesn't receive it). So a non-installed src-layout
package can't be imported via a `PYTHONPATH` export. The shim puts `src/` on
`sys.path` *inside* the job, deriving it from `snakemake.scriptdir` (the original dir
of `_run.py`, i.e. `workflow/scripts/` → `../../src`). This keeps the rules free of
any `params` plumbing — `snakemake.rule` + `snakemake.scriptdir` are the clean,
purpose-built channels. Documented generically in trident's `docs/adopt.md`; the
concrete wiring is this repo's `workflow/Snakefile` + `workflow/scripts/_run.py`.
