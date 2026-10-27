import pathlib
import sys

# Make the src/ package importable for `pytest .tests/integration/` without an
# install or PYTHONPATH (mirrors how the shims add src/ inside Snakemake jobs).
# This file is .tests/integration/conftest.py, so the repo root is parents[2].
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
