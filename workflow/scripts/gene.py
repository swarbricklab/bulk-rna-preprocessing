"""Snakemake shim — see bulk_rna_preprocessing/_steps/gene.py."""

import sys

# src/ layout: make the package importable from inside the rule job. Snakemake
# scrubs PYTHONPATH for --use-conda jobs, so we add src/ here (params.pkg_src,
# set in the Snakefile) rather than relying on the environment.
sys.path.insert(0, snakemake.params.pkg_src)  # noqa: F821  (snakemake-injected)

from bulk_rna_preprocessing._dispatch import dispatch
from bulk_rna_preprocessing._steps.gene import run

dispatch(run, globals())
