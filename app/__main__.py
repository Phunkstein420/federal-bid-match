"""python -m app — show how to run ingest and the query API."""

from __future__ import annotations


def main() -> None:
    print("federal-bid-match")
    print("  ingest:  python -m app.ingest")
    print("  query:   python -m app.query --naics 541511 --set-aside SBA")
    print("  api:     uvicorn app.api:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
