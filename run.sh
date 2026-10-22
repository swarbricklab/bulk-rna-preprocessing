#! /bin/bash
# Run the bulk-rna-preprocessing workflow.
#
# Standalone:   ./run.sh [extra snakemake args]
# As a submodule (installed under <parent>/modules/bulk-rna-preprocessing), set
# BULK_RNA_PREPROCESSING_CONFIG to the parent repo's config and invoke this script,
# mirroring sc_pileup's run.sh.

set -e
eval "$(conda shell.bash hook)"
conda activate snakemake_7.32.4

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$(hostname)" == *"nci"* ]]; then
    global_profile="--profile $HERE/profiles/global/nci"
    workflow_profile="--workflow-profile $HERE/profiles/workflow"
    mkdir -p logs/joblogs
else
    global_profile=""
    workflow_profile="--workflow-profile $HERE/profiles/workflow"
fi

snakemake $global_profile $workflow_profile \
    --snakefile "$HERE/workflow/Snakefile" \
    --configfile "${BULK_RNA_PREPROCESSING_CONFIG:-$HERE/config/config.yaml}" \
    "$@"
