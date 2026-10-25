"""Fast unit tests over the importable library + stage functions.

The payoff of the trident pattern: the code that the Snakemake rules and the CLI
both run is plain Python, so it is tested here directly on the tiny committed
fixtures — no Snakemake process, no subprocess. The slow end-to-end wiring (DAG +
conda envs) is covered separately by `run_test.sh --check` against the golden.
"""

from pathlib import Path
from types import SimpleNamespace

import anndata as ad
import numpy as np
import yaml

from bulk_rna_preprocessing import lib
from bulk_rna_preprocessing._dispatch import dispatch
from bulk_rna_preprocessing._steps import gene, gene_annotation, transcript

HERE = Path(__file__).parent
FIX = HERE / "fixtures"
GOLD = HERE / "golden"


def _load_test_config() -> dict:
    """The committed test config, with the clinical path made absolute so the
    test does not depend on the working directory."""
    cfg = yaml.safe_load((HERE / "config.yaml").read_text())
    cfg["deps"]["clinical"] = str(FIX / "clinical.csv")
    return cfg


def _assert_h5ad_identical(a_path: Path, b_path: Path) -> None:
    a, b = ad.read_h5ad(a_path), ad.read_h5ad(b_path)
    assert a.shape == b.shape
    assert list(a.obs_names) == list(b.obs_names)
    assert list(a.var_names) == list(b.var_names)
    assert np.array_equal(np.asarray(a.X), np.asarray(b.X))
    assert set(a.layers) == set(b.layers)
    for layer in a.layers:
        assert np.allclose(a.layers[layer], b.layers[layer], equal_nan=True), layer
    assert list(a.obs.columns) == list(b.obs.columns)
    assert list(a.var.columns) == list(b.var.columns)


# --- library functions -------------------------------------------------------

def test_extract_gene_annotation_matches_golden(tmp_path):
    out = tmp_path / "genes.tsv"
    lib.extract_gene_annotation(str(FIX / "gencode.gtf.gz"), str(out))
    assert out.read_text() == (GOLD / "genes.tsv").read_text()


def test_add_uqn_layers_scales_to_target():
    X = np.array([[0, 2, 4, 6, 8], [0, 1, 2, 3, 4]], dtype=np.float32)
    adata = ad.AnnData(X=X.copy())
    lib.add_uqn_layers(adata, quantile=75, target=1000.0)
    for i in range(adata.n_obs):
        nz = adata.X[i] > 0
        assert abs(np.percentile(adata.layers["uqn"][i][nz], 75) - 1000.0) < 1e-6
    # log2_uqn substitutes 0 -> 1 before log2, so zeros map to 0.
    zeros = adata.layers["uqn"] == 0
    assert np.all(adata.layers["log2_uqn"][zeros] == 0)


def test_load_samplesheet_filter_and_dedup():
    sheet = lib.load_samplesheet(str(FIX / "samplesheet.csv"), "gussid",
                                 {"column": "assay", "value": "wts"})
    assert "DNA_X" not in sheet.index  # wgs row filtered out
    assert len(sheet.index) == len(set(sheet.index))


# --- stage run() functions, called directly (no Snakemake) -------------------

def test_gene_and_transcript_runs_match_golden(tmp_path):
    cfg = _load_test_config()
    tsv = tmp_path / "genes.tsv"
    gene_annotation.run(gencode_gtf=FIX / "gencode.gtf.gz", gene_annotation=tsv)

    gene_out = tmp_path / "gene.h5ad"
    gene.run(counts_dir=FIX / "individual", samplesheet=FIX / "samplesheet.csv",
             hgnc_complete_set=FIX / "hgnc_complete_set.txt", gene_annotation=tsv,
             gene_h5ad=gene_out, config=cfg)
    _assert_h5ad_identical(GOLD / "gene_counts.h5ad", gene_out)

    tx_out = tmp_path / "transcript.h5ad"
    transcript.run(counts_dir=FIX / "individual", samplesheet=FIX / "samplesheet.csv",
                   transcript_h5ad=tx_out, config=cfg)
    _assert_h5ad_identical(GOLD / "transcript_counts.h5ad", tx_out)


# --- the dispatch binding the shim relies on, via a fake snakemake object -----

def test_dispatch_binds_gene_annotation(tmp_path):
    out = tmp_path / "genes.tsv"
    ns = lambda d: SimpleNamespace(**d)  # noqa: E731
    snake = SimpleNamespace(
        input=ns({"gencode_gtf": str(FIX / "gencode.gtf.gz")}),
        output=ns({"gene_annotation": str(out)}),
        params=ns({}), wildcards=ns({}), config={}, log=[], rule="gene_annotation",
    )
    dispatch(gene_annotation.run, {"snakemake": snake})  # exactly what the shim does
    assert out.read_text() == (GOLD / "genes.tsv").read_text()
