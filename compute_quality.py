#!/usr/bin/env python3
"""Standalone quality scorer for IRB drafts produced by irb_agent.py.

Usage:
  python compute_quality.py --json-path output/irb_42.json --out docs/results/quality-42.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

SECTION_TITLES = [
    "1. 연구 과제명(국문)",
    "2. 연구 배경 및 목적",
    "3. 연구 설계 및 방법",
    "4. 연구대상자 선정 및 제외 기준",
    "5. 모집 및 동의 절차",
    "6. 예측 가능한 위험 및 불편과 최소화 대책",
    "7. 개인정보 및 연구자료 보호 계획",
    "8. 자료 보관 및 폐기 계획",
    "9. 보상 및 배상 계획",
    "10. 연구 수행 기관 및 소속",
    "11. 검토 메모",
]


def count_sentences(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return len([p for p in parts if p.strip()])


def compute(json_path: Path) -> dict:
    if not json_path.exists():
        return {"total": 0.0, "sentence_score": 0.0, "required_score": 0.0, "details": ["출력 JSON 없음"]}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"total": 0.0, "sentence_score": 0.0, "required_score": 0.0, "details": [f"JSON 파싱 실패: {e}"]}

    sections = data.get("sections", {})
    s2 = sections.get("2. 연구 배경 및 목적", "")
    s3 = sections.get("3. 연구 설계 및 방법", "")
    s2_count = count_sentences(s2)
    s3_count = count_sentences(s3)

    sentence_score = ((min(s2_count / 10.0, 1.0) + min(s3_count / 30.0, 1.0)) / 2.0) * 100.0

    checks = [
        ("섹션 11개 완전성", all(k in sections and str(sections.get(k, "")).strip() for k in SECTION_TITLES)),
        ("목적 섹션 10문장 이상", s2_count >= 10),
        ("방법 섹션 30문장 이상", s3_count >= 30),
        ("방법 섹션 1~5 순서 포함", all(tok in s3 for tok in ["1.", "2.", "3.", "4.", "5."])),
        ("방법 섹션 소요시간 언급", "소요시간" in s3),
        ("방법 섹션 윤리 고려 언급", "윤리" in s3),
        ("방법 섹션 안전 절차 언급", "안전" in s3),
    ]
    passed = sum(1 for _, ok in checks if ok)
    required_score = (passed / len(checks)) * 100.0
    total = round(sentence_score * 0.5 + required_score * 0.5, 1)

    details = [f"{name}: {'충족' if ok else '미충족'}" for name, ok in checks]
    details.insert(0, f"문장수 - 섹션2: {s2_count}, 섹션3: {s3_count}")

    return {
        "total": total,
        "sentence_score": round(sentence_score, 1),
        "required_score": round(required_score, 1),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="IRB 초안 품질 점수 계산")
    parser.add_argument("--json-path", type=Path, required=True, help="irb_agent.py 출력 JSON 경로")
    parser.add_argument("--out", type=Path, default=None, help="품질 점수 출력 JSON 경로")
    args = parser.parse_args()

    result = compute(args.json_path)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"품질 점수 저장: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
