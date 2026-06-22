"""Dataset bootstrap helpers.

Primary dataset is a REAL open dataset: the Google Web Trillion Word Corpus
unigram counts (`count_1w.txt`, published by Peter Norvig). It contains 333,333
real keywords with their real corpus frequencies in a simple ``word<TAB>count``
format, which we convert to the assignment's ``query,count`` CSV.

On first run the file is fetched automatically. If there is no network access we
fall back to a reproducible synthetic generator so the app still runs offline.
"""
from __future__ import annotations

import csv
import os
import urllib.request
from typing import List, Tuple

from .dataset import generate_dataset
from .store import PrimaryStore


def download_real_dataset(csv_path: str, url: str, limit: int = 0) -> int:
    """Download the real unigram dataset and write it as ``query,count`` CSV.

    ``limit`` > 0 keeps only the top-N most frequent keywords (the file is
    already sorted by descending frequency); 0 keeps all 333,333.
    """
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "typeahead-loader"})
    written = 0
    with urllib.request.urlopen(req, timeout=60) as resp, \
            open(csv_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["query", "count"])
        for raw in resp:
            line = raw.decode("utf-8", "ignore").strip()
            if not line:
                continue
            parts = line.split("\t") if "\t" in line else line.split()
            if len(parts) < 2:
                continue
            query = parts[0].strip().lower()
            try:
                count = int(parts[1])
            except ValueError:
                continue
            if not query:
                continue
            writer.writerow([query, count])
            written += 1
            if limit and written >= limit:
                break
    return written


def ensure_dataset(csv_path: str, url: str, limit: int = 0,
                   fallback_size: int = 120_000) -> str:
    """Make sure the dataset CSV exists. Returns the source actually used."""
    if os.path.exists(csv_path):
        return "existing"
    try:
        n = download_real_dataset(csv_path, url, limit)
        print(f"[dataset] downloaded {n} real keywords from {url}")
        return "real"
    except Exception as exc:  # offline / URL error -> reproducible fallback
        print(f"[dataset] download failed ({exc}); using synthetic fallback")
        generate_dataset(csv_path, fallback_size)
        return "synthetic"


def read_csv(csv_path: str) -> List[Tuple[str, int]]:
    rows: List[Tuple[str, int]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # tolerate files with or without a header
        if header and not (len(header) >= 2 and header[1].strip().isdigit()):
            pass  # header row, skip
        elif header:
            rows.append((header[0].strip().lower(), int(header[1])))
        for row in reader:
            if len(row) < 2:
                continue
            q = row[0].strip().lower()
            try:
                c = int(float(row[1]))
            except ValueError:
                continue
            if q:
                rows.append((q, c))
    return rows


def load_into_store(store: PrimaryStore, csv_path: str) -> int:
    rows = read_csv(csv_path)
    return store.bulk_load(rows)
