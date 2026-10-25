# Container for the bulk-rna-preprocessing aggregation step (the python h5ad builder).
# Snakemake orchestration itself runs outside the container (as in sc_pileup);
# this image carries the anndata/pandas/numpy stack plus the installed package and
# its CLI, so the heavy aggregation step is reproducible.
FROM mambaorg/micromamba:1.5.8

COPY env/environment.yaml /tmp/environment.yaml
RUN micromamba install -y -n base -f /tmp/environment.yaml && \
    micromamba clean --all --yes

# Install the package (adds the CLI + click). The scientific deps are already
# provided by the conda env above, so pip only pulls what is missing.
COPY --chown=$MAMBA_USER:$MAMBA_USER pyproject.toml README.md LICENSE /opt/bulk-rna-preprocessing/
COPY --chown=$MAMBA_USER:$MAMBA_USER src /opt/bulk-rna-preprocessing/src
ARG MAMBA_DOCKERFILE_ACTIVATE=1
RUN pip install /opt/bulk-rna-preprocessing

ENV PATH=/opt/conda/bin:$PATH
ENTRYPOINT ["python", "-m", "bulk_rna_preprocessing"]
