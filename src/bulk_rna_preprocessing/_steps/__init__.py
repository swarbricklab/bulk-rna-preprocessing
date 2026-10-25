"""Workflow stages: one typed ``run(...)`` per step.

Each module's ``run`` is the single source of truth for that stage, driven from
both the Snakemake ``script:`` shims (via :mod:`bulk_rna_preprocessing._dispatch`)
and the CLI (:mod:`bulk_rna_preprocessing._cli`). Parameter names match the
rule's input/output/params attribute names.
"""
