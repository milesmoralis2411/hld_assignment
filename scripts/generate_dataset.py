"""CLI wrapper to generate the query dataset.

Usage:
    python -m scripts.generate_dataset --size 120000 --path data/queries.csv
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.dataset import generate_dataset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a typeahead query dataset.")
    ap.add_argument("--path", default="data/queries.csv")
    ap.add_argument("--size", type=int, default=120_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    n = generate_dataset(args.path, args.size, args.seed)
    print(f"Wrote {n} queries to {args.path}")


if __name__ == "__main__":
    main()
