# Containers

`Dockerfile` builds an image carrying the python stack (anndata / pandas / numpy
/ pyyaml / h5py) that `workflow/scripts/preprocess.py` needs, with the CLI as the
entrypoint:

```
docker build -t ghcr.io/swarbricklab/bulk-rna-preprocessing:dev -f containers/Dockerfile .
docker run --rm -v "$PWD:/work" -w /work \
    ghcr.io/swarbricklab/bulk-rna-preprocessing:dev all --config config/config.yaml
```

Snakemake orchestration runs outside the container (as in sc_pileup); only the
aggregation step is containerised. Publishing to GHCR is a later step — this repo
is currently local-only.
