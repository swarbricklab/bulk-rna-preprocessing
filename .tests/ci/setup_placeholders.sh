#!/bin/bash
# Touch empty placeholder inputs so `snakemake -n` can build the full DAG in CI
# without any real data.
set -eu
base=.tests/ci
mkdir -p "$base/individual/SAMPLE1"
touch "$base/individual/SAMPLE1/SAMPLE1.quant.genes.sf" \
      "$base/individual/SAMPLE1/SAMPLE1.quant.sf" \
      "$base/samplesheet.csv" \
      "$base/gencode.gtf.gz" \
      "$base/hgnc_complete_set.txt" \
      "$base/clinical.csv"
echo "placeholders touched"
