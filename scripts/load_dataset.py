"""Pre-load the CSV dataset into the SQLite primary store (optional).

The server does this automatically on first start, but you can run it ahead of
time:

    python -m scripts.load_dataset --csv data/queries.csv --db data/typeahead.db
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.loader import ensure_dataset, load_into_store  # noqa: E402
from app.store import PrimaryStore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Load dataset CSV into SQLite.")
    ap.add_argument("--csv", default="data/queries.csv")
    ap.add_argument("--db", default="data/typeahead.db")
    ap.add_argument("--size", type=int, default=120_000,
                    help="dataset size to generate if the CSV is missing")
    ap.add_argument("--force", action="store_true",
                    help="reload even if the store already has rows")
    args = ap.parse_args()

    ensure_dataset(args.csv, args.size)
    store = PrimaryStore(args.db)
    if not store.is_empty() and not args.force:
        print(f"Store already has {store.count_rows()} rows (use --force to reload).")
        return
    t0 = time.time()
    n = load_into_store(store, args.csv)
    print(f"Loaded {n} rows into {args.db} in {time.time() - t0:.2f}s")
    store.close()


if __name__ == "__main__":
    main()
