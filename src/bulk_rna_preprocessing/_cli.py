"""The ``bulk-rna-preprocessing`` CLI.

Built from the same typed ``run()`` functions the Snakemake shim dispatches to:
:func:`bulk_rna_preprocessing._dispatch.build_cli` discovers each stage in
:mod:`bulk_rna_preprocessing._steps` and exposes it as a subcommand, so the CLI
and the workflow are generated from one source and cannot drift. Invoke as
``python -m bulk_rna_preprocessing``.
"""

from __future__ import annotations

from bulk_rna_preprocessing import __version__
from bulk_rna_preprocessing._dispatch import build_cli

cli = build_cli(
    "bulk_rna_preprocessing._steps",
    name="bulk-rna-preprocessing",
    version=__version__,
    help="bulk-rna-preprocessing — aggregate per-sample Salmon quants into h5ad.",
)


if __name__ == "__main__":
    cli()
