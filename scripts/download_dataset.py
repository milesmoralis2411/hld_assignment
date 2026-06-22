"""Download the REAL open dataset and write it as data/queries.csv.

Source: Google Web Trillion Word Corpus unigram counts (`count_1w.txt`),
published by Peter Norvig at https://norvig.com/ngrams/ . 333,333 real keywords
with real corpus frequencies, licensed for any use.

Usage:
    python -m scripts.download_dataset                  # all 333,333 rows
    python -m scripts.download_dataset --limit 150000   # top-N by frequency
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import config  # noqa: E402
from app.loader import download_real_dataset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Download the real query dataset.")
    ap.add_argument("--path", default="data/queries.csv")
    ap.add_argument("--url", default=config.dataset_url)
    ap.add_argument("--limit", type=int, default=0,
                    help="keep only the top-N most frequent (0 = all)")
    args = ap.parse_args()
    n = download_real_dataset(args.path, args.url, args.limit)
    print(f"Wrote {n} real keywords to {args.path}")


if __name__ == "__main__":
    main()
