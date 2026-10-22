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
    python3 "$HERE/test/compare_h5ad.py" "$HERE/test/golden/gene_counts.h5ad" "$HERE/test/out/gene_counts.h5ad"
    python3 "$HERE/test/compare_h5ad.py" "$HERE/test/golden/transcript_counts.h5ad" "$HERE/test/out/transcript_counts.h5ad"
    echo "OK: test output matches golden"
fi
