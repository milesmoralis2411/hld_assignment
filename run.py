"""Single entry point: start the Search Typeahead server.

    python run.py                 # http://127.0.0.1:8000
    python run.py --port 9000
    python run.py --reload        # auto-reload during development

On first start it will (a) generate the dataset CSV if missing, (b) load it into
SQLite, and (c) build the in-memory index. Subsequent starts reuse the DB.
"""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
