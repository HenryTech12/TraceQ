"""Phase 1 CLI: `traceq analyze <file>` prints the FileRecord + verdict as JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyze import analyze_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traceq", description="TraceQ — the forensic layer for the internet.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze a single file and print its FileRecord as JSON.")
    analyze_parser.add_argument("file", type=Path, help="Path to the file to analyze.")
    analyze_parser.add_argument(
        "--pretty", action="store_true", default=True, help="Pretty-print the JSON output (default)."
    )

    args = parser.parse_args(argv)

    if args.command == "analyze":
        if not args.file.exists():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 1
        data = args.file.read_bytes()
        result = analyze_file(data, args.file.name)
        print(result.model_dump_json(indent=2 if args.pretty else None))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
