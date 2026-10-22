# Shared helpers for the bulk-rna-preprocessing workflow.


def gene_extra_inputs():
    """Optional extra inputs for the gene_h5ad rule.

    The clinical obs-join is optional: include data/deps.clinical in the DAG only
    when a `params.clinical` block is configured, so the workflow also runs for
    cohorts without a clinical table.
    """
    params = config.get("params") or {}
    if params.get("clinical"):
        return [config["deps"]["clinical"]]
    return []
