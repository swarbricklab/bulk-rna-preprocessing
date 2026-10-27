#!/usr/bin/env python3
"""Compare two .h5ad files for semantic equality.

Reports shapes, X and per-layer max-abs-diff, and obs/var column-by-column
equality. Exits non-zero on any mismatch (NaN-aware). Use --ignore-var-cols to
exclude deliberately-changed var columns (e.g. the dropped PAM50 columns when
comparing the standalone module against the historical output).

Usage:
    compare_h5ad.py A.h5ad B.h5ad [--ignore-var-cols c1,c2] [--ignore-obs-cols ...]
"""
import argparse
import sys

import anndata as ad
import numpy as np
import pandas as pd


def arr(x):
    return x.toarray() if hasattr(x, "toarray") else np.asarray(x)


def max_abs_diff(a, b):
    a = arr(a).astype(np.float64)
    b = arr(b).astype(np.float64)
    if a.shape != b.shape:
        return float("inf")
    both_nan = np.isnan(a) & np.isnan(b)
    d = np.abs(np.where(both_nan, 0.0, a - b))
    return float(np.nanmax(d)) if d.size else 0.0


def series_equal(a: pd.Series, b: pd.Series):
    a = a.astype(object).where(~a.isna(), None)
    b = b.astype(object).where(~b.isna(), None)
    return bool((a.values == b.values).all())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--ignore-var-cols", default="")
    ap.add_argument("--ignore-obs-cols", default="")
    args = ap.parse_args()

    A = ad.read_h5ad(args.a)
    B = ad.read_h5ad(args.b)
    ign_var = {c for c in args.ignore_var_cols.split(",") if c}
    ign_obs = {c for c in args.ignore_obs_cols.split(",") if c}

    ok = True
    print(f"A: {args.a}  shape={A.shape}")
    print(f"B: {args.b}  shape={B.shape}")
    if A.shape != B.shape:
        print("MISMATCH: shapes differ"); sys.exit(1)

    if not (A.obs_names == B.obs_names).all():
        print("MISMATCH: obs_names differ"); ok = False
    if not (A.var_names == B.var_names).all():
        print("MISMATCH: var_names differ"); ok = False

    d = max_abs_diff(A.X, B.X)
    print(f"X max-abs-diff: {d:.3e}")
    ok &= d == 0.0
    for layer in sorted(set(A.layers) | set(B.layers)):
        if layer not in A.layers or layer not in B.layers:
            print(f"MISMATCH: layer {layer} present in only one"); ok = False; continue
        d = max_abs_diff(A.layers[layer], B.layers[layer])
        print(f"layer[{layer}] max-abs-diff: {d:.3e}")
        ok &= d == 0.0

    for frame_name, FA, FB, ignore in (("obs", A.obs, B.obs, ign_obs),
                                       ("var", A.var, B.var, ign_var)):
        cols_a = [c for c in FA.columns if c not in ignore]
        cols_b = [c for c in FB.columns if c not in ignore]
        if cols_a != cols_b:
            print(f"MISMATCH: {frame_name} columns differ (ignoring {sorted(ignore)}):")
            print(f"  A: {cols_a}")
            print(f"  B: {cols_b}")
            ok = False
        for c in cols_a:
            if c in cols_b and not series_equal(FA[c], FB[c]):
                print(f"MISMATCH: {frame_name}['{c}'] values differ"); ok = False
        print(f"{frame_name}: {len(cols_a)} columns compared"
              + (f" (ignored {sorted(ignore)})" if ignore else ""))

    if ok:
        print("RESULT: IDENTICAL" + (" (modulo ignored columns)" if (ign_var or ign_obs) else ""))
        sys.exit(0)
    print("RESULT: DIFFERENT")
    sys.exit(1)


if __name__ == "__main__":
    main()
