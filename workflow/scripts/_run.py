"""The single Snakemake shim for every rule.

Snakemake's `script:` directive needs a file, so one generic shim serves all
rules: `dispatch_by_rule` maps `snakemake.rule` ->
`bulk_rna_preprocessing._steps.<rule>.run` and binds that step's typed `run()`
parameters from the rule's input/output/params and from config. (Hence rule name
== step module name — see each rule's `# impl:` comment.)

The package lives under src/ and is not pip-installed into the `--use-conda` rule
env, and Snakemake scrubs PYTHONPATH for those jobs — so we put src/ on sys.path
from inside the job, deriving it from `snakemake.scriptdir` (the original dir of
this file, i.e. workflow/scripts/ -> ../../src).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(snakemake.scriptdir).parent.parent / "src"))  # noqa: F821,E402

from bulk_rna_preprocessing._dispatch import dispatch_by_rule  # noqa: E402

dispatch_by_rule(globals(), "bulk_rna_preprocessing._steps")  # noqa: F821
