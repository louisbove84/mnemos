"""CLI entrypoint for the ingest Job/CronJob."""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from mnemos.ingest.pipeline import run_ingest


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        result = asyncio.run(run_ingest())
    except Exception:
        logging.exception("ingest failed")
        sys.exit(1)
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    main()
