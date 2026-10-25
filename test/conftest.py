import pathlib
import sys

# Make the src/ package importable for `pytest test/` without an install or
# PYTHONPATH (mirrors how the shims add src/ inside Snakemake jobs).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
