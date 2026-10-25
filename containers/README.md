# Containers

`Dockerfile` builds an image carrying the python stack (anndata / pandas / numpy
/ pyyaml / h5py) plus the installed `bulk_rna_preprocessing` package, with its CLI
(`python -m bulk_rna_preprocessing`) as the entrypoint:

```
docker build -t ghcr.io/swarbricklab/bulk-rna-preprocessing:dev -f containers/Dockerfile .
docker run --rm -v "$PWD:/work" -w /work \
    ghcr.io/swarbricklab/bulk-rna-preprocessing:dev gene --config config/config.yaml \
    --counts-dir ... --samplesheet ... --hgnc-complete-set ... \
    --gene-annotation ... --gene-h5ad ...
```

Snakemake orchestration runs outside the container (as in sc_pileup); only the
aggregation step is containerised. Publishing to GHCR is a later step — this repo
is currently local-only.
