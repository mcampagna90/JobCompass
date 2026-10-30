"""JobCompass CLI (Requirement 10.3). Single `run` command; `sources` helper.

No automated external actions.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .pipeline import run as run_pipeline


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jobcompass",
        description="JobCompass — discover and map companies from authorized public sources.",
    )
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Run the full pipeline (default).")
    sub.add_parser("sources", help="List configured sources.")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        cfg = load_config(args.config)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    command = args.command or "run"

    if command == "sources":
        if not cfg.sources:
            print("No sources configured.")
            return 0
        for s in cfg.sources:
            state = "enabled" if s.get("enabled") else "disabled"
            paid = " [paid]" if s.get("type") == "commercial" else ""
            print(f"- {s.get('name','?')} [{s.get('country','?')}/{s.get('type','?')}]"
                  f" ({state}){paid}")
        return 0

    if command == "run":
        stats = run_pipeline(cfg)
        print("Run complete.")
        print(f"  Sources queried: {stats['sources_queried']}  Found: {stats['found']}"
              f"  Skipped: {stats['skipped']}  Excluded: {stats['excluded']}")
        print(f"  New: {stats['new']}  Updated: {stats['updated']}"
              f"  Duplicates: {stats['duplicates']}")
        outs = stats.get("outputs", {})
        if outs:
            print(f"  IT-native map: {outs.get('it_native_html')}")
            print(f"  IT-adjacent map: {outs.get('it_adjacent_html')}")
            print(f"  Interchange export: {stats.get('interchange')}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
