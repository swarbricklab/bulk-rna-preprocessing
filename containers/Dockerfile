# Container for the bulk-rna-preprocessing aggregation step (the python h5ad builder).
# Snakemake orchestration itself runs outside the container (as in sc_pileup);
# this image carries the anndata/pandas/numpy stack the CLI needs so the heavy
# aggregation step is reproducible.
FROM mambaorg/micromamba:1.5.8

COPY env/environment.yaml /tmp/environment.yaml
RUN micromamba install -y -n base -f /tmp/environment.yaml && \
    micromamba clean --all --yes

COPY workflow/scripts/preprocess.py /opt/bulk-rna-preprocessing/preprocess.py

ENV PATH=/opt/conda/bin:$PATH
ENTRYPOINT ["python", "/opt/bulk-rna-preprocessing/preprocess.py"]
