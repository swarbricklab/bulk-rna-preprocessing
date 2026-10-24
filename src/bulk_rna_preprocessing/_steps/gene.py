"""Stage: aggregate gene-level Salmon quants -> annotated, UQN-normalised h5ad."""

from __future__ import annotations

import os
from pathlib import Path

from bulk_rna_preprocessing import lib


def run(
    counts_dir: Path,
    samplesheet: Path,
    hgnc_complete_set: Path,
    gene_annotation: Path,
    gene_h5ad: Path,
    config: dict,
    log_path: Path | None = None,
) -> None:
    """Build the gene-level AnnData: counts + TPM/eff_length layers, GENCODE+HGNC
    var annotation, optional UQN/log2_uqn layers, and optional clinical obs-join.
    """
    p = lib.params(config)
    samplesheet_df = lib.samplesheet_from_config(config, samplesheet)
    gene_annot = lib.load_gene_annotation(str(gene_annotation))
    hgnc_df = lib.load_hgnc(str(hgnc_complete_set))

    print("=== Gene counts ===")
    adata = lib.aggregate(str(counts_dir), p["gene_quant_suffix"], samplesheet_df,
                          p["sample_id"], p["obs_from_samplesheet"])
    print(f"  Shape: {adata.shape}")
    print("  Annotating genes ...")
    lib.annotate_genes(adata, gene_annot, hgnc_df)

    uqn = p.get("uqn") or {}
    if uqn.get("enabled", True):
        print("  Computing UQN + log2(UQN) ...")
        lib.add_uqn_layers(adata, uqn.get("quantile", 75), uqn.get("target", 1000.0))

    clinical = p.get("clinical")
    if clinical:
        print("  Joining clinical metadata ...")
        clinical_df = lib.load_clinical(config["deps"]["clinical"], clinical["index_column"],
                                        clinical["columns"], clinical.get("na_value", "NA"))
        lib.annotate_obs_with_clinical(adata, clinical_df, clinical["columns"],
                                       clinical["join_on"],
                                       clinical.get("eligibility_report_column"))

    lib.coerce_object_columns_for_h5ad(adata)
    out = str(gene_h5ad)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    adata.write_h5ad(out)
    print(f"  Wrote {out}")
