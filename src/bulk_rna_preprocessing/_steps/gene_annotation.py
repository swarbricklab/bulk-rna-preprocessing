"""Stage: GENCODE GTF -> gene-level annotation TSV."""

from __future__ import annotations

from pathlib import Path

from bulk_rna_preprocessing import lib


def run(gencode_gtf: Path, gene_annotation: Path, log_path: Path | None = None) -> None:
    """Extract gene_id, gene_name, gene_type, hgnc_id from a GENCODE GTF to TSV."""
    print("=== Gene annotation ===")
    lib.extract_gene_annotation(str(gencode_gtf), str(gene_annotation))
