#!/usr/bin/env python3
"""Write a markdown job summary for GitHub Actions.

Usage:
  python write_summary.py
"""
import json
import os
from pathlib import Path


def main() -> None:
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "0")
    topic = os.environ.get("IRB_TOPIC", "(주제 없음)")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

    quality_path = Path(f"docs/results/quality-{run_number}.json")
    quality: dict = {"total": "-", "sentence_score": "-", "required_score": "-", "details": []}
    if quality_path.exists():
        try:
            quality = json.loads(quality_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    lines = [
        f"## ✅ IRB 생성 완료 (Run #{run_number})",
        "",
        f"**연구 주제**: {topic}",
        "",
        "| 지표 | 점수 |",
        "| --- | --- |",
        f"| 종합 점수 | **{quality['total']}** |",
        f"| 문장수 점수 | {quality['sentence_score']} |",
        f"| 필수항목 점수 | {quality['required_score']} |",
        "",
        "### 세부 항목",
        "",
    ]
    for detail in quality.get("details", []):
        icon = "✅" if "충족" in detail else "❌"
        lines.append(f"- {icon} {detail}")

    lines += [
        "",
        "### 결과 파일",
        f"- `docs/results/irb-{run_number}.hwpx` (한글 문서)",
        f"- `docs/results/irb-{run_number}.md` (마크다운)",
        f"- `docs/results/irb-{run_number}.json` (JSON)",
    ]

    summary = "\n".join(lines) + "\n"
    print(summary)

    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(summary)


if __name__ == "__main__":
    main()
