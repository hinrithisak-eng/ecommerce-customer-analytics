"""
run_pipeline.py
---------------
One-command reproduction of the whole project (handy for the live demo):

    python src/run_pipeline.py            # generate -> clean -> execute notebook
    python src/run_pipeline.py --skip-notebook

Steps
  1. Regenerate the raw dataset (data/raw/ecommerce_orders_raw.csv)
  2. Run the cleaning pipeline (data/processed/ecommerce_orders_clean.csv)
  3. Execute the analysis notebook in place, refreshing outputs/figures/
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, **kw):
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-notebook", action="store_true", help="only regenerate and clean the data")
    args = ap.parse_args()

    run([sys.executable, "src/generate_dataset.py"])
    run([sys.executable, "src/data_cleaning.py"])
    if not args.skip_notebook:
        run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             "notebooks/ecommerce_customer_analytics.ipynb", "--ExecutePreprocessor.timeout=600"])
    print("\nPipeline finished successfully.")


if __name__ == "__main__":
    main()
