"""Dataset bootstrap helpers: ensure CSV exists and load it into the store."""
from __future__ import annotations

import csv
import os
from typing import List, Tuple

from .dataset import generate_dataset
from .store import PrimaryStore


def ensure_dataset(csv_path: str, size: int) -> None:
    if not os.path.exists(csv_path):
        generate_dataset(csv_path, size)


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
