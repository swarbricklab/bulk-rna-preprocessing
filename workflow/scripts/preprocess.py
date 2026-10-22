#!/usr/bin/env python3
"""bulk-rna-preprocessing: aggregate per-sample Salmon quant files into h5ad.

Config-driven CLI (sub-commands `gene-annotation`, `gene`, `transcript`, `all`)
that turns a tree of per-sample Salmon quantifications into gene- and
transcript-level AnnData (.h5ad) objects with normalisation layers.

This is the standalone, reusable, PAM50-agnostic extraction of
brca_mega_atlas-data's modules/preprocessing/scripts/preprocess.py. The counting,
UQN/log2_uqn normalisation, obs sample/clinical join, var GENCODE+HGNC annotation
and transcript aggregation are a faithful, behaviour-preserving port; the only
intentional change is that the PAM50 var stamping (is_pam50 / pam50_symbol /
in_proliferation) and its pam50_annotation.txt dependency have been removed.
Downstream PAM50 subtyping (intrinsix) self-identifies its 50 genes from
var.entrez_id, which this module still stamps.

Everything that was hard-coded to one dataset (paths, the sample-id column, the
samplesheet row filter, which samplesheet/clinical columns land in obs, and the
UQN quantile/target) is now read from the config, so both bcarc_wts and
brca_mega_atlas-data (and any Salmon WTS cohort) can drive it.

Outputs
-------
gene <gene_h5ad>
    X                 = NumReads (raw counts, float32)
    layers.tpm        = TPM
    layers.eff_length = EffectiveLength
    layers.uqn        = upper-quartile normalised counts (UQ scaled to `target`)
    layers.log2_uqn   = log2(UQN) with 0 -> 1 substitution
    obs index         = params.sample_id (from the quant subdir name)
    obs.<...>         = params.obs_from_samplesheet columns + optional clinical join
    var index         = gene IDs (e.g. versioned ENSG, from the quant `Name` column)
    var.Length        = gene length (from the quant `Length` column)
    var.gene_name     = HGNC symbol (GENCODE GTF)
    var.gene_type     = biotype (GENCODE GTF)
    var.hgnc_id       = HGNC ID (GENCODE GTF)
    var.entrez_id     = NCBI Entrez gene ID (HGNC complete set, via hgnc_id)

transcript <transcript_h5ad>
    X / layers.tpm / layers.eff_length as above; var index = transcript IDs; no
    annotation / UQN / clinical join (unchanged from the original).

Usage
-----
    preprocess.py gene-annotation --config config.yaml
    preprocess.py gene            --config config.yaml
    preprocess.py transcript      --config config.yaml
    preprocess.py all             --config config.yaml
"""

import argparse
import gzip
import os
import re
from glob import glob
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import yaml


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def read_config(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def _params(cfg):
    return cfg.get("params") or {}


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


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def _resolve_gene_annotation(cfg):
    """Return the gene-annotation DataFrame, extracting the TSV if absent."""
    tsv = cfg["outs"]["gene_annotation"]
    if os.path.exists(tsv):
        print(f"  Loading cached {tsv}")
        return load_gene_annotation(tsv)
    print(f"  Extracting from {cfg['deps']['gencode_gtf']} ...")
    return extract_gene_annotation(cfg["deps"]["gencode_gtf"], tsv)


def cmd_gene_annotation(cfg):
    print("=== Gene annotation ===")
    tsv = cfg["outs"]["gene_annotation"]
    if os.path.exists(tsv):
        print(f"  {tsv} already exists; nothing to do")
        return
    extract_gene_annotation(cfg["deps"]["gencode_gtf"], tsv)


def _sample_sheet(cfg):
    p = _params(cfg)
    id_col = p.get("samplesheet_id_column") or p["sample_id"]
    return load_samplesheet(cfg["deps"]["samplesheet"], id_col, p.get("samplesheet_filter"))


def cmd_gene(cfg):
    p = _params(cfg)
    samplesheet = _sample_sheet(cfg)
    gene_annot = _resolve_gene_annotation(cfg)
    hgnc_df = load_hgnc(cfg["deps"]["hgnc_complete_set"])

    print("=== Gene counts ===")
    adata = aggregate(cfg["deps"]["counts_dir"], p["gene_quant_suffix"], samplesheet,
                      p["sample_id"], p["obs_from_samplesheet"])
    print(f"  Shape: {adata.shape}")
    print("  Annotating genes ...")
    annotate_genes(adata, gene_annot, hgnc_df)
    uqn = p.get("uqn") or {}
    if uqn.get("enabled", True):
        print("  Computing UQN + log2(UQN) ...")
        add_uqn_layers(adata, uqn.get("quantile", 75), uqn.get("target", 1000.0))
    clinical = p.get("clinical")
    if clinical:
        print("  Joining clinical metadata ...")
        clinical_df = load_clinical(cfg["deps"]["clinical"], clinical["index_column"],
                                    clinical["columns"], clinical.get("na_value", "NA"))
        annotate_obs_with_clinical(adata, clinical_df, clinical["columns"],
                                   clinical["join_on"],
                                   clinical.get("eligibility_report_column"))
    coerce_object_columns_for_h5ad(adata)
    out = cfg["outs"]["gene_h5ad"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    adata.write_h5ad(out)
    print(f"  Wrote {out}")


def cmd_transcript(cfg):
    p = _params(cfg)
    samplesheet = _sample_sheet(cfg)
    print("=== Transcript counts ===")
    adata = aggregate(cfg["deps"]["counts_dir"], p["transcript_quant_suffix"], samplesheet,
                      p["sample_id"], p["obs_from_samplesheet"])
    print(f"  Shape: {adata.shape}")
    coerce_object_columns_for_h5ad(adata)
    out = cfg["outs"]["transcript_h5ad"]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    adata.write_h5ad(out)
    print(f"  Wrote {out}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="bulk-rna-preprocessing: Salmon quants -> h5ad")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("gene-annotation", "gene", "transcript", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--config", required=True, help="Path to config.yaml")
    args = ap.parse_args(argv)
    cfg = read_config(args.config)

    if args.command == "gene-annotation":
        cmd_gene_annotation(cfg)
    elif args.command == "gene":
        cmd_gene(cfg)
    elif args.command == "transcript":
        cmd_transcript(cfg)
    elif args.command == "all":
        cmd_gene(cfg)
        print()
        cmd_transcript(cfg)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
