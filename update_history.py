#!/usr/bin/env python3
"""Update docs/results/history.json with the latest run result.

Usage:
  python update_history.py
"""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "0")
    run_result_path = Path(f"docs/results/run-{run_number}.json")
    history_path = Path("docs/results/history.json")

    if not run_result_path.exists():
        print(f"Run result not found: {run_result_path}", file=sys.stderr)
        sys.exit(1)

    entry = json.loads(run_result_path.read_text(encoding="utf-8"))

    history: list = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []

    # Remove existing entry for same run number, then prepend new entry (max 20)
    history = [h for h in history if h.get("run_number") != entry["run_number"]]
    history = [entry] + history[:19]

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"History updated: {len(history)} entries in {history_path}")


if __name__ == "__main__":
    main()
