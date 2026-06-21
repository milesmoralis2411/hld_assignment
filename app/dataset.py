"""Synthetic-but-realistic search dataset generator.

The assignment allows any open-source dataset with (query, count) and asks for
>= 100,000 rows. To keep the project self-contained and reproducible (no large
binary checked in, no network needed), we GENERATE a Zipf-distributed dataset
from an open vocabulary of brands / products / categories / tech terms, etc.

- Counts follow a Zipf-like curve (a few very popular queries, a long tail) -
  the realistic shape of real query logs.
- Output is a plain CSV: ``query,count`` - so you can swap in any real dataset
  (AOL query log, Google Trends export, a Kaggle e-commerce query set, ...) in
  the same format without touching the rest of the code. See README "Dataset".
"""
from __future__ import annotations

import csv
import os
import random
from typing import List, Tuple

# A few well-known head queries with hand-set high counts (mirrors the sample
# table in the assignment). The rest of the long tail is generated.
HEAD: List[Tuple[str, int]] = [
    ("iphone", 100000), ("iphone 15", 85000), ("iphone charger", 60000),
    ("java tutorial", 40000), ("python tutorial", 39000), ("samsung galaxy", 38000),
    ("laptop deals", 36000), ("airpods pro", 34000), ("nike shoes", 33000),
    ("amazon prime", 31000), ("netflix", 30000), ("youtube", 29000),
]

BRANDS = ["apple", "samsung", "sony", "nike", "adidas", "dell", "hp", "lenovo",
          "asus", "google", "amazon", "microsoft", "logitech", "bose", "canon",
          "lg", "intel", "nvidia", "puma", "reebok", "xiaomi", "oneplus",
          "realme", "boat", "jbl", "philips", "panasonic", "acer", "msi"]

PRODUCTS = ["phone", "laptop", "headphones", "earbuds", "charger", "cable",
            "monitor", "keyboard", "mouse", "watch", "tablet", "camera",
            "speaker", "tv", "router", "ssd", "hard drive", "power bank",
            "shoes", "backpack", "jacket", "smartwatch", "printer", "webcam",
            "microphone", "controller", "graphics card", "processor", "ram"]

ADJECTIVES = ["best", "cheap", "wireless", "gaming", "portable", "new", "used",
              "refurbished", "premium", "budget", "fast", "mini", "pro", "ultra",
              "smart", "waterproof", "noise cancelling", "4k", "hd", "compact"]

CATEGORIES = ["deals", "review", "price", "online", "near me", "offers",
              "comparison", "specs", "discount", "sale", "for sale", "2024",
              "2025", "in india", "amazon", "flipkart"]

TECH = ["python", "java", "javascript", "react", "node", "docker", "kubernetes",
        "sql", "mongodb", "redis", "aws", "azure", "git", "linux", "spring",
        "django", "flask", "fastapi", "rust", "golang", "typescript", "kafka",
        "system design", "data structures", "algorithms", "machine learning"]

TECH_TOPICS = ["tutorial", "interview questions", "cheat sheet", "examples",
               "documentation", "for beginners", "advanced", "course",
               "roadmap", "vs", "best practices", "project ideas", "certification"]

ACTIONS = ["how to", "what is", "download", "install", "buy", "fix", "learn",
           "compare", "build", "convert", "remove", "setup"]


def _build_pool(size: int, rng: random.Random) -> List[str]:
    pool: "dict[str, None]" = {}

    def add(q: str) -> None:
        q = q.strip().lower()
        if q:
            pool.setdefault(q, None)

    for q, _ in HEAD:
        add(q)
    for w in BRANDS + PRODUCTS + TECH:
        add(w)

    templates = [
        lambda: f"{rng.choice(BRANDS)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(ADJECTIVES)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(PRODUCTS)} {rng.choice(CATEGORIES)}",
        lambda: f"{rng.choice(BRANDS)} {rng.choice(PRODUCTS)} {rng.choice(CATEGORIES)}",
        lambda: f"{rng.choice(ADJECTIVES)} {rng.choice(BRANDS)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(ADJECTIVES)} {rng.choice(PRODUCTS)} {rng.choice(CATEGORIES)}",
        lambda: f"{rng.choice(BRANDS)} {rng.choice(ADJECTIVES)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(ACTIONS)} {rng.choice(BRANDS)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(TECH)} {rng.choice(TECH_TOPICS)}",
        lambda: f"{rng.choice(ACTIONS)} {rng.choice(TECH)}",
        lambda: f"{rng.choice(ACTIONS)} {rng.choice(PRODUCTS)}",
        lambda: f"{rng.choice(TECH)} {rng.choice(TECH)} {rng.choice(TECH_TOPICS)}",
        lambda: f"{rng.choice(BRANDS)} {rng.choice(PRODUCTS)} {rng.randint(1, 30)}",
        lambda: f"{rng.choice(ADJECTIVES)} {rng.choice(PRODUCTS)} {rng.randint(1, 30)}",
        # large-cardinality 4-word templates ensure we can exceed 120k uniques
        lambda: f"{rng.choice(ADJECTIVES)} {rng.choice(BRANDS)} {rng.choice(PRODUCTS)} {rng.choice(CATEGORIES)}",
        lambda: f"{rng.choice(ACTIONS)} {rng.choice(ADJECTIVES)} {rng.choice(BRANDS)} {rng.choice(PRODUCTS)}",
    ]

    # keep sampling templates until we have enough unique queries
    guard = 0
    max_guard = size * 60
    while len(pool) < size and guard < max_guard:
        add(rng.choice(templates)())
        guard += 1

    return list(pool.keys())


def generate_dataset(path: str, size: int = 120_000, seed: int = 42) -> int:
    """Write ``size`` unique (query, count) rows to ``path`` as CSV."""
    rng = random.Random(seed)
    head_map = dict(HEAD)
    pool = _build_pool(size, rng)

    # Reserve the head queries at the top; shuffle the rest for the long tail.
    head_queries = [q for q, _ in HEAD if q in pool]
    rest = [q for q in pool if q not in head_map]
    rng.shuffle(rest)
    ordered = head_queries + rest
    ordered = ordered[:size]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["query", "count"])
        for rank, query in enumerate(ordered):
            if query in head_map:
                count = head_map[query]
            else:
                jitter = rng.uniform(0.7, 1.35)
                count = max(1, int(100_000 / ((rank + 1) ** 0.8) * jitter))
            writer.writerow([query, count])
    return len(ordered)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Generate a typeahead query dataset.")
    ap.add_argument("--path", default="data/queries.csv")
    ap.add_argument("--size", type=int, default=120_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    n = generate_dataset(args.path, args.size, args.seed)
    print(f"Wrote {n} queries to {args.path}")
