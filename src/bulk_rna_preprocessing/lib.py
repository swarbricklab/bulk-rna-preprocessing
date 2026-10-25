"""bulk-rna-preprocessing core library: Salmon quants -> h5ad.

Pure, Snakemake-free functions — the counting, UQN/log2_uqn normalisation, obs
sample/clinical join, var GENCODE+HGNC annotation and transcript aggregation.
Both the workflow (`script:` shims via :mod:`bulk_rna_preprocessing._dispatch`)
and the CLI (:mod:`bulk_rna_preprocessing._cli`) call these through the thin
``_steps.*.run`` wrappers, so the algorithm lives in exactly one place.

This is the standalone, reusable, PAM50-agnostic extraction of
brca_mega_atlas-data's modules/preprocessing/scripts/preprocess.py: a faithful,
behaviour-preserving port with the PAM50 var stamping (is_pam50 / pam50_symbol /
in_proliferation) and its pam50_annotation.txt dependency removed. Downstream
PAM50 subtyping (intrinsix) self-identifies its 50 genes from var.entrez_id,
which this still stamps.
"""

from __future__ import annotations

import gzip
import os
import re
from glob import glob
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def params(cfg: dict) -> dict:
    return cfg.get("params") or {}


def samplesheet_from_config(cfg: dict, samplesheet_path) -> pd.DataFrame:
    """Load the samplesheet keyed by the configured id column, with the filter."""
    p = params(cfg)
    id_col = p.get("samplesheet_id_column") or p["sample_id"]
    return load_samplesheet(str(samplesheet_path), id_col, p.get("samplesheet_filter"))


# ---------------------------------------------------------------------------
# Sample sheet
# ---------------------------------------------------------------------------

def load_samplesheet(path, id_column, filt=None):
    """Load the project samplesheet, keyed by `id_column`.

    `filt`, if given, is a {"column", "value"} dict that restricts the sheet to
    rows where column == value (e.g. assay == "wts"). The id column must be
    unique after filtering.
    """
    df = pd.read_csv(path, dtype=str)
    if filt and filt.get("column") is not None:
        df = df[df[filt["column"]] == filt["value"]].copy()
    if df[id_column].duplicated().any():
        dups = df.loc[df[id_column].duplicated(keep=False), id_column].unique()
        raise ValueError(f"Duplicate {id_column} in samplesheet: {list(dups)}")
    return df.set_index(id_column)


# ---------------------------------------------------------------------------
# Gene annotation (GENCODE GTF -> TSV, HGNC complete set)
# ---------------------------------------------------------------------------

def extract_gene_annotation(gtf_path, tsv_path):
    """Extract gene-level annotation from a GENCODE GTF and write it to TSV.

    Parses gene records, extracting gene_id, gene_name, gene_type, hgnc_id.
    """
    attr_re = re.compile(r'(\w+) "([^"]+)"')
    records = []
    with gzip.open(gtf_path, "rt") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if fields[2] != "gene":
                continue
            attrs = dict(attr_re.findall(fields[8]))
            records.append({
                "gene_id": attrs["gene_id"],
                "gene_name": attrs["gene_name"],
                "gene_type": attrs["gene_type"],
                "hgnc_id": attrs.get("hgnc_id", ""),
            })
    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(tsv_path) or ".", exist_ok=True)
    df.to_csv(tsv_path, sep="\t", index=False)
    print(f"  Extracted {len(df)} gene records -> {tsv_path}")
    return df.set_index("gene_id")


def load_gene_annotation(path):
    """Load a GENCODE gene annotation TSV (gene_id, gene_name, gene_type, hgnc_id)."""
    df = pd.read_csv(path, sep="\t", dtype=str)
    return df.set_index("gene_id")


def load_hgnc(path):
    """Load the HGNC complete set, indexed by hgnc_id (entrez_id, ensembl_gene_id)."""
    df = pd.read_csv(path, sep="\t", dtype=str,
                     usecols=["hgnc_id", "entrez_id", "ensembl_gene_id"])
    df = df.replace("", float("nan"))
    return df.set_index("hgnc_id")


# ---------------------------------------------------------------------------
# Clinical metadata (optional obs join)
# ---------------------------------------------------------------------------

def load_clinical(path, index_column, columns, na_value="NA"):
    """Load a clinical metadata table indexed by `index_column`.

    `columns` are the columns fanned out onto obs. na_value entries become NaN.
    """
    df = pd.read_csv(path, dtype=str)
    if na_value is not None:
        df = df.replace(na_value, float("nan"))
    if df[index_column].duplicated().any():
        dups = df.loc[df[index_column].duplicated(keep=False), index_column].unique()
        raise ValueError(f"Duplicate {index_column} in clinical table: {list(dups)}")
    df = df.set_index(index_column)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise KeyError(f"Clinical table missing expected columns: {missing}")
    return df[columns]


# ---------------------------------------------------------------------------
# File discovery + aggregation
# ---------------------------------------------------------------------------

def discover_quant_files(base_dir, suffix):
    """Return sorted (sample_id, filepath) tuples for a given suffix.

    The tree is flat and sample-named: base_dir/<sample_id>/<*.suffix>.
    """
    pattern = os.path.join(base_dir, "*", f"*.{suffix}")
    results = []
    for fp in sorted(glob(pattern)):
        sample_id = Path(fp).parts[-2]
        results.append((sample_id, fp))
    return results


def aggregate(base_dir, suffix, samplesheet, id_name, obs_columns):
    """Read all quant files with *suffix* into an AnnData.

    obs is keyed by the quant subdir name (`id_name`) and joined to the
    samplesheet, carrying `obs_columns`. Raises KeyError if a sample is missing.
    """
    files = discover_quant_files(base_dir, suffix)
    if not files:
        raise FileNotFoundError(f"No *.{suffix} files found under {base_dir}")
    print(f"  Found {len(files)} {suffix} files")

    first = pd.read_csv(files[0][1], sep="\t")
    var_names = first["Name"].values
    var_df = pd.DataFrame(
        {"Length": first["Length"].values},
        index=pd.Index(var_names, name="gene_id"),
    )

    n_obs = len(files)
    n_var = len(var_names)
    raw_counts = np.empty((n_obs, n_var), dtype=np.float32)
    tpm = np.empty((n_obs, n_var), dtype=np.float64)
    eff_length = np.empty((n_obs, n_var), dtype=np.float64)

    obs_records = []
    for i, (sid, fp) in enumerate(files):
        if i % 50 == 0:
            print(f"  Reading {i + 1}/{n_obs} ...")
        df = pd.read_csv(fp, sep="\t")
        raw_counts[i, :] = df["NumReads"].values
        tpm[i, :] = df["TPM"].values
        eff_length[i, :] = df["EffectiveLength"].values

        if sid not in samplesheet.index:
            raise KeyError(f"{sid} not found in samplesheet")
        row = samplesheet.loc[sid]
        rec = {id_name: sid}
        for col in obs_columns:
            rec[col] = row[col]
        obs_records.append(rec)

    obs_df = pd.DataFrame(obs_records)
    obs_df.index = pd.Index(obs_df.pop(id_name), name=id_name)

    return ad.AnnData(
        X=raw_counts,
        obs=obs_df,
        var=var_df,
        layers={"tpm": tpm, "eff_length": eff_length},
    )


# ---------------------------------------------------------------------------
# Annotation / normalisation / obs join
# ---------------------------------------------------------------------------

def annotate_genes(adata, gene_annot, hgnc_df):
    """Add GENCODE gene annotation + Entrez ID to adata.var in-place.

    (PAM50-agnostic: the former is_pam50 / pam50_symbol / in_proliferation var
    stamping and its pam50_annotation.txt input have been removed. gene_name,
    gene_type, hgnc_id, entrez_id are stamped exactly as before.)
    """
    for col in ["gene_name", "gene_type", "hgnc_id"]:
        adata.var[col] = adata.var.index.map(
            lambda gid: gene_annot.at[gid, col] if gid in gene_annot.index else ""
        )
    adata.var["entrez_id"] = adata.var["hgnc_id"].map(
        lambda hid: hgnc_df.at[hid, "entrez_id"] if hid in hgnc_df.index else float("nan")
    )
    n_entrez = adata.var["entrez_id"].notna().sum()
    print(f"  Entrez IDs mapped: {n_entrez}/{adata.n_vars}")
    print(f"  Gene annotations: {(adata.var['gene_name'] != '').sum()}/{adata.n_vars} annotated")


def add_uqn_layers(adata, quantile=75, target=1000.0):
    """Add upper-quartile normalised (UQN) and log2(UQN) layers in-place.

    For each sample, compute the `quantile`th percentile of its non-zero counts
    (the upper quartile), then scale counts so that percentile equals `target`.
    log2_uqn: zeros are replaced with 1 before log2 (so log2(0) -> 0).
    """
    X = adata.X.astype(np.float64)
    uqs = np.array([np.percentile(row[row > 0], quantile) for row in X])
    print(f"  UQ range: {uqs.min():.1f} - {uqs.max():.1f}")
    uqn = X * (target / uqs[:, np.newaxis])
    uqn_log = uqn.copy()
    uqn_log[uqn_log == 0] = 1.0
    log2_uqn = np.log2(uqn_log)
    adata.layers["uqn"] = uqn
    adata.layers["log2_uqn"] = log2_uqn


def annotate_obs_with_clinical(adata, clinical_df, columns, join_on,
                               eligibility_report_column=None):
    """Join clinical columns onto adata.obs by the `join_on` obs column.

    Each obs row is matched to clinical_df via obs[join_on], so replicates of the
    same group inherit identical clinical values; unmatched rows receive NaN.
    """
    aligned = clinical_df.reindex(adata.obs[join_on].values)
    missing = set(adata.obs[join_on]) - set(clinical_df.index)
    if missing:
        head = sorted(missing)[:5]
        tail = "..." if len(missing) > 5 else ""
        print(f"  WARNING: {len(missing)} {join_on} values missing from clinical table: {head}{tail}")
    for col in columns:
        adata.obs[col] = aligned[col].values
    if eligibility_report_column and eligibility_report_column in columns:
        eligible = adata.obs[eligibility_report_column].isna().sum()
        print(f"  Eligible samples ({eligibility_report_column} is NA): {eligible}/{adata.n_obs}")


def coerce_object_columns_for_h5ad(adata):
    """Make obs/var h5ad-writable: cast mixed object columns to categorical.

    anndata >=0.10 refuses to serialise object columns mixing strings with NaN.
    Casting to categorical is written natively, preserves NaN, and keeps string
    comparisons valid downstream.
    """
    for frame in (adata.obs, adata.var):
        for col in frame.columns:
            if frame[col].dtype == object:
                frame[col] = frame[col].astype("category")
