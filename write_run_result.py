#!/usr/bin/env python3
"""Write a run result JSON for GitHub Pages history display.

Reads metadata from environment variables set by GitHub Actions.
Usage:
  python write_run_result.py
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "0")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    topic = os.environ.get("IRB_TOPIC", "")
    model = os.environ.get("IRB_MODEL", "gpt-4.1-mini")
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else ""

    quality_path = Path(f"docs/results/quality-{run_number}.json")
    quality: dict = {"total": 0.0, "sentence_score": 0.0, "required_score": 0.0, "details": []}
    if quality_path.exists():
        try:
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"품질 JSON 읽기 실패: {e}", file=sys.stderr)

    result = {
        "run_number": int(run_number),
        "run_id": run_id,
        "run_url": run_url,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "topic": topic,
        "model": model,
        "quality": quality,
        "files": {
            "hwpx": f"results/irb-{run_number}.hwpx",
            "md":   f"results/irb-{run_number}.md",
            "json": f"results/irb-{run_number}.json",
        },
    }

    out_path = Path(f"docs/results/run-{run_number}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
