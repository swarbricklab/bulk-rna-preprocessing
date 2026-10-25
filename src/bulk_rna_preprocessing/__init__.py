"""bulk-rna-preprocessing: aggregate per-sample Salmon quants into h5ad.

The algorithm lives in :mod:`bulk_rna_preprocessing.lib`; each workflow stage is
a typed ``run()`` in :mod:`bulk_rna_preprocessing._steps`, driven from both the
Snakemake ``script:`` shims and the CLI through
:mod:`bulk_rna_preprocessing._dispatch`.
"""

__version__ = "0.1.0"
