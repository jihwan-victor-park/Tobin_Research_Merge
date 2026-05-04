"""CLI wrapper around backend.discovery.scout.scout()."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.discovery.scout import scout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--country", default="US")
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    found = scout(country=args.country, limit=args.limit)
    print(f"Registered {len(found)} new site(s):")
    for c in found:
        print(f"  {c.domain:35s}  cat={c.category:22s} conf={c.confidence:.2f}  url={c.url}")


if __name__ == "__main__":
    main()
