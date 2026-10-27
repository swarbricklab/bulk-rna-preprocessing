# Containers

The aggregation step's conda environment (`env/environment.yaml`) is containerised
two ways. See `docs/dev/containerisation.md` for the design.

## Env image (absconda → GHCR)

`.github/workflows/container.yml` builds `env/environment.yaml` into an optimised
image with [absconda](https://github.com/swarbricklab/absconda) and publishes it to
`ghcr.io/swarbricklab/bulk-rna-preprocessing` (`:latest`, `:sha-<short>`, and
`:<semver>` on version tags). This is the image the Snakemake `container:` directive
will reference (phase 2): the workflow shim imports the package from the
bind-mounted `src/`, so the env image needs only the scientific stack.

To build it locally (needs a Docker daemon — not available on NCI nodes):

```
pip install absconda
absconda build --file env/environment.yaml \
    --repository ghcr.io/swarbricklab/bulk-rna-preprocessing --tag dev
```

## CLI image (`Dockerfile`)

`Dockerfile` builds an image carrying the python stack **plus** the installed
`bulk_rna_preprocessing` package, with its CLI (the `brp` command) as the
entrypoint — for running a stage standalone, without Snakemake:

```
docker build -t ghcr.io/swarbricklab/bulk-rna-preprocessing:cli -f containers/Dockerfile .
docker run --rm -v "$PWD:/work" -w /work \
    ghcr.io/swarbricklab/bulk-rna-preprocessing:cli gene --config config/config.yaml \
    --counts-dir ... --samplesheet ... --hgnc-complete-set ... \
    --gene-annotation ... --gene-h5ad ...
```

Snakemake orchestration itself runs outside the container (as in sc_pileup); only
the aggregation step is containerised. A later step may fold the package into the
absconda env image so a single image serves both the workflow and the CLI.
