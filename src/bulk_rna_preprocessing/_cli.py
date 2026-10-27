"""The ``bulk-rna-preprocessing`` CLI (installed as the ``brp`` command).

Built from the same typed ``run()`` functions the Snakemake shim dispatches to:
:func:`bulk_rna_preprocessing._dispatch.build_cli` discovers each stage in
:mod:`bulk_rna_preprocessing._steps` and exposes it as a subcommand, so the CLI
and the workflow are generated from one source and cannot drift. Runnable as the
installed ``brp`` command or as ``python -m bulk_rna_preprocessing``.
"""

from __future__ import annotations

from bulk_rna_preprocessing import __version__
from bulk_rna_preprocessing._dispatch import build_cli

# One-letter aliases for the most-typed options (the long names always work too).
# Applied per command, skipping any that would collide; -c/--config and -l/--log
# are built in. A param that appears in more than one step (e.g. the output h5ad)
# reuses the same letter, since the steps never share a single command.
_SHORT_FLAGS = {
    "counts_dir": "-i",        # per-sample Salmon quant dir (input)
    "samplesheet": "-s",
    "gencode_gtf": "-g",
    "gene_annotation": "-a",   # annotation TSV: output of gene-annotation, input to gene
    "gene_h5ad": "-o",         # output h5ad
    "transcript_h5ad": "-o",   # output h5ad
}

cli = build_cli(
    "bulk_rna_preprocessing._steps",
    name="brp",
    version=__version__,
    help="bulk-rna-preprocessing — aggregate per-sample Salmon quants into h5ad.",
    short_flags=_SHORT_FLAGS,
)


if __name__ == "__main__":
    cli()
