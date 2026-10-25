"""Stage: aggregate transcript-level Salmon quants -> h5ad (no annotation/UQN)."""

from __future__ import annotations

import os
from pathlib import Path

from bulk_rna_preprocessing import lib


def run(
    counts_dir: Path,
    samplesheet: Path,
    transcript_h5ad: Path,
    config: dict,
    log_path: Path | None = None,
) -> None:
    """Build the transcript-level AnnData: counts + TPM/eff_length layers only."""
    p = lib.params(config)
    samplesheet_df = lib.samplesheet_from_config(config, samplesheet)

    print("=== Transcript counts ===")
    adata = lib.aggregate(str(counts_dir), p["transcript_quant_suffix"], samplesheet_df,
                          p["sample_id"], p["obs_from_samplesheet"])
    print(f"  Shape: {adata.shape}")
    lib.coerce_object_columns_for_h5ad(adata)
    out = str(transcript_h5ad)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    adata.write_h5ad(out)
    print(f"  Wrote {out}")
