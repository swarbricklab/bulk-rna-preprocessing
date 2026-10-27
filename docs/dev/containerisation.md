# Containerisation (absconda → GHCR)

The aggregation step runs in the conda environment defined once in
`env/environment.yaml` (anndata / pandas / numpy / pyyaml / h5py +
snakemake-minimal). All three rules (`gene_annotation`, `gene`, `transcript`)
reference it via `conda: "../env/environment.yaml"`.

We containerise that single environment with
[absconda](https://github.com/swarbricklab/absconda), which turns a conda env
file into an optimised multi-stage OCI image, and publish it to the GitHub
Container Registry at `ghcr.io/swarbricklab/bulk-rna-preprocessing`. This follows
the lab's "containerise every tool → GHCR" strategy (replacing ad-hoc,
DVC-tracked binaries and hand-written Dockerfiles).

## Phase 1 — publish the env image (this change)

`.github/workflows/container.yml` runs `absconda build` on a GitHub-hosted runner
(where Docker is available — NCI login/compute nodes have no Docker daemon):

- **pull request** → build only (validates the absconda build; no push),
- **push to `main`** → build + push `:latest` and `:sha-<short>`,
- **tag `v*`** → build + push `:<semver>` and `:latest`,
- **manual** (`workflow_dispatch`).

It uses the built-in `GITHUB_TOKEN` (with `packages: write`) to authenticate to
GHCR, so no extra secret is required.

## Phase 2 — run the workflow against the image (follow-up)

absconda can rewrite the per-rule `conda:` directives to `container:` referencing
the published image:

```bash
absconda workflow apply .        # scan → containerise → rewrite Snakefile
# then run with Singularity instead of --use-conda:
snakemake --use-singularity --singularity-args="--bind /scratch:/scratch" ...
```

This changes the execution model (Singularity instead of per-rule conda), so it
is kept as a separate, separately-validated change rather than folded into phase 1.

### Note: the package inside the container

The env image carries only the conda environment, **not** the installed
`bulk_rna_preprocessing` package. That is deliberate and sufficient for the
Snakemake `container:` path: the generic shim (`workflow/scripts/_run.py`) inserts
the repo's `src/` onto `sys.path` from the bind-mounted working directory, so the
package is imported from source at run time (no install needed in the image).

The standalone **CLI** image — the one that provides the `brp` command as an
entrypoint — remains the hand-written `containers/Dockerfile` (env **+** installed
package). A later step can fold the package into the absconda image (via a `pip:`
entry or an absconda template) so a single image serves both the workflow and the
CLI; until then the two images coexist and are documented in `containers/README.md`.
