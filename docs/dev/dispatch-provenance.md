# `_dispatch.py` provenance & generic-vs-specific inventory

`src/bulk_rna_preprocessing/_dispatch.py` is **vendored** from
[`swarbricklab/spotty`](https://github.com/swarbricklab/spotty)
(`src/spotty/_dispatch.py`, commit `006747fc`). This repo is the **second**
consumer of the "workflow / CLI / library trinity" pattern; the intent is to
extract the proven, generalised core into a standalone package (working name
**`trident`**) once two real, differently-shaped workflows (spotty = ~17 steps,
Snakemake 9; bulk-rna-preprocessing = 3 steps, Snakemake 7) agree on the API.

This file is the running log of what is **generic** (lift as-is into the shared
package) vs. **spotty-specific** (generalise before publishing). Every change
made while vendoring is marked `# [vendor]` in the source.

## The pattern (generic — the whole point)

One typed `run(...)` per stage is the single source of truth. Two thin adapters
feed it, both in `_dispatch.py`:

- `dispatch(run, globals())` — binds `run`'s params from the Snakemake-injected
  `snakemake` object (`input` → `output` → `wildcards` → `params`, first hit
  wins; `config` → `snakemake.config`; `log_path` → `snakemake.log[0]`), with a
  pre-flight input check and a telemetry banner.
- `as_click_command(run)` — builds a `click` command from the *same* signature,
  so the CLI and the Snakemake shims never drift.

Shims are 3 lines (`dispatch(run, globals())`); the CLI is `as_click_command`
per step. This core is **cleanly portable** — it only touches the stable
script-level `snakemake` object, not Snakemake internals, so one copy serves
Snakemake 7, 8 and 9. That is the main finding from this second port: the
mechanism moved repos **without touching the resolution/telemetry logic at all**.

### Generic, used as-is here
- `dispatch`, `_resolve_snakemake_kwargs`, `_lookup_in_snakemake_namespaces`
- `as_click_command` option synthesis + callback
- `_coerce`, `_unwrap_optional`, `_is_list_annotation`, `_safe_get_type_hints`
- `_run_with_telemetry`, `_make_logmsg`, `_format_kwargs`, `_preflight`,
  `_fmt_elapsed` / `_fmt_size` — all domain-neutral.

## Spotty-specific (generalise before publishing `trident`)

1. **CLI config loader was JSON-only.** spotty's `as_click_command` exposed
   `--config-json` and did `json.loads`. This repo's configs are YAML, so the
   **one behavioural change** on vendoring was a format-agnostic loader
   (`_load_config_file`, `--config`, YAML or JSON by extension). → In `trident`,
   the config loader should be format-agnostic (or caller-supplied) from the
   start.

2. **`_SHORT_BY_PARAM`** hardcodes spotty's domain vocabulary
   (`gussid`, `dashboard`, `summary_json`, `in_h5ad`, …). Inert for param names
   this repo doesn't use, so kept verbatim. → In `trident`, short-flag mapping
   should be **caller-registrable**, not a baked-in dict.

3. **`_classify_by_name`** output heuristics (`_pdf`, `_dashboard`, `dashboard`,
   `_json`, `_csv`). Only affects CLI-mode telemetry input/output *labelling*
   (not correctness; the Snakemake path classifies by source namespace). → In
   `trident`, make the suffix set configurable or drop the CLI-mode name
   heuristic in favour of explicit param roles.

4. **Package-name references** — docstrings, the `dispatch()` out-of-Snakemake
   error, the telemetry banner, and `_pkg_version()`'s
   `from spotty import __version__`. Mechanical renames here (`# [vendor]`), but
   in `trident` the version/banner should read the **consuming** package's name
   (e.g. via `__package__` / an injected name), not a hardcoded import.

## Portability finding: shims need the package importable

spotty's shims are 3 lines (`dispatch(run, globals())`) because spotty is
**pip-installed**, so `import spotty` resolves everywhere. This repo is not
installed into the per-rule conda env, and **Snakemake scrubs `PYTHONPATH` for
`--use-conda` jobs** (deliberate env isolation — verified: conda activation
itself preserves `PYTHONPATH`; the job just doesn't receive it). So a `PYTHONPATH`
export in `run.sh` does not reach the rule job.

Fix used here: each rule passes `params.pkg_src` (the `src/` dir, from
`workflow.basedir`) and the shim does `sys.path.insert(0, snakemake.params.pkg_src)`
*inside* the job before importing — immune to the scrub. → In `trident`, a
`dispatch_by_rule`/bootstrap helper should encapsulate this, or document that the
consuming package must be pip-installed into the rule env. Either way: **"3-line
shim" assumes an installed package; a src-layout, non-installed workflow needs the
bootstrap.**

## Candidate additions for `trident` (not needed yet here)
- `dispatch_by_rule(globals())` — a single generic shim that maps
  `snakemake.rule` → `<pkg>._steps.<rule>.run`, collapsing N shim files to 1.
- `build_cli(steps_pkg)` — auto-discover `_steps/*.run` and assemble the click
  group, so `_cli.py` collapses to near-zero.
