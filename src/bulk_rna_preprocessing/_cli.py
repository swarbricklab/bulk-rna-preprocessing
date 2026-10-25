"""The ``bulk-rna-preprocessing`` CLI.

Each stage's ``run(...)`` in :mod:`bulk_rna_preprocessing._steps` becomes a
subcommand via :func:`bulk_rna_preprocessing._dispatch.as_click_command`, so the
CLI is rebuilt from the same typed signatures the Snakemake shims dispatch to —
one source of truth for both. Invoke as ``python -m bulk_rna_preprocessing``.
"""

from __future__ import annotations

import click

from bulk_rna_preprocessing import __version__
from bulk_rna_preprocessing._dispatch import as_click_command
from bulk_rna_preprocessing._steps import gene, gene_annotation, transcript


@click.group(
    help="bulk-rna-preprocessing — aggregate per-sample Salmon quants into h5ad.",
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog=(
        "Run a stage standalone (the Snakemake pipeline runs the same steps):\n"
        "  gene-annotation  GENCODE GTF -> gene annotation TSV (run first)\n"
        "  gene             gene-level counts -> annotated, UQN-normalised h5ad\n"
        "  transcript       transcript-level counts -> h5ad\n"
    ),
)
@click.version_option(__version__, prog_name="bulk-rna-preprocessing")
def cli() -> None:
    pass


cli.add_command(as_click_command(gene_annotation.run, name="gene-annotation"))
cli.add_command(as_click_command(gene.run, name="gene"))
cli.add_command(as_click_command(transcript.run, name="transcript"))


if __name__ == "__main__":
    cli()
