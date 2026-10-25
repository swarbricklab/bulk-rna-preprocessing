#! /bin/bash
# Build the gene + transcript h5ad from the bundled PUBLIC test fixture (a tiny
# synthetic 3-sample Salmon cohort under test/fixtures/) and, with --check, assert
# the result matches the DVC-free golden produced by the SAME code
# (test/golden/). The fixture + golden are committed, so the test is fully
# self-contained and data-independent.
#
# Usage:
#   ./run_test.sh              # build into test/out/
#   ./run_test.sh --check      # build, then compare test/out to test/golden
#   ./run_test.sh -n           # dry run
set -euo pipefail

if ! command -v conda >/dev/null 2>&1; then
    source "${CONDA_PROFILE:-/g/data/a56/conda/miniconda/etc/profile.d/conda.sh}"
fi
eval "$(conda shell.bash hook)"
conda activate "${BULK_RNA_PREPROCESSING_ENV:-snakemake_7.32.4}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check=false
sm_args=()
for a in "$@"; do
    if [[ "$a" == "--check" ]]; then check=true; else sm_args+=("$a"); fi
done

snakemake \
    --snakefile "$HERE/workflow/Snakefile" \
    --configfile "$HERE/test/config.yaml" \
    --workflow-profile "$HERE/profiles/workflow" \
    --cores "${CORES:-2}" \
    ${sm_args[@]+"${sm_args[@]}"}

if [[ "$check" == true ]]; then
    echo "=== comparing test/out to test/golden ==="
    # compare_h5ad.py needs anndata. The launcher env (snakemake_7.32.4) only has
    # Snakemake, not anndata — the deps live in the per-rule conda env that
    # use-conda builds from env/environment.yaml. Run the comparison with that
    # env's python so --check works regardless of what launched run_test.sh.
    mapfile -t _envs < <(compgen -G "$HERE/.snakemake/conda/*/bin/python" || true)
    if [[ ${#_envs[@]} -eq 1 ]]; then
        PY="${_envs[0]}"
    else
        echo "warn: expected exactly one built conda env under .snakemake/conda," \
             "found ${#_envs[@]}; using 'python' (needs anndata on PATH)" >&2
        PY=python
    fi
    for h in gene_counts.h5ad transcript_counts.h5ad; do
        "$PY" "$HERE/test/compare_h5ad.py" "$HERE/test/golden/$h" "$HERE/test/out/$h"
    done
    echo "OK: test output matches golden"
fi
