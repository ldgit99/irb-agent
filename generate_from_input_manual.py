#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import irb_agent

PI_FIXED = {
    "pi_name": "이동국",
    "pi_position": "조교수",
    "pi_affiliation": "경북대학교",
    "pi_major": "교육공학",
    "pi_tel": "053-950-5845",
    "pi_hp": "010-2656-5132",
    "pi_email": "dklee@knu.ac.kr",
}


def parse_input_form(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    fields = {
        "연구 주제": "",
        "연구 방법": "",
        "수행기관": "",
        "소속": "",
        "연구책임자 소속대학/학과": "",
        "예상 대상자 수": "",
        "연구기간(개월)": "",
        "연구 시작일": "",
        "연구 종료일": "",
        "민감정보 수집 여부": "",
        "대면 진행 여부": "",
        "연구책임자 성명": "",
        "성명": "",
        "연구책임자 전화번호": "",
        "전화번호": "",
    }
    for key in fields:
        m = re.search(rf"^[\*\-]\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if m:
            fields[key] = m.group(1).strip()
    return fields


def to_int_or_default(raw: str, default: int) -> int:
    m = re.search(r"\d+", raw or "")
    return int(m.group(0)) if m else default


def main() -> None:
    root = Path(r"d:\irb agent")
    inp = parse_input_form(root / "input" / "input-form.md")

    topic = inp["연구 주제"] or "연구 주제 미입력"
    method = inp["연구 방법"] or "연구 방법 미입력"
    institution = inp["수행기관"] or "미정"
    department = inp["소속"] or "미정"
    pi_name = inp["연구책임자 성명"] or inp["성명"] or "해당없음"
    pi_phone = inp["연구책임자 전화번호"] or inp["전화번호"] or "해당없음"
    pi_aff = inp["연구책임자 소속대학/학과"] or department
    sample_size = to_int_or_default(inp["예상 대상자 수"], 100)
    duration = inp["연구기간(개월)"] or "미정"
    start_date = inp["연구 시작일"]
    end_date = inp["연구 종료일"]
    sensitive = inp["민감정보 수집 여부"] or "미정"
    face_to_face = inp["대면 진행 여부"] or "미정"
    study_period_text = (
        f"{start_date} ~ {end_date}" if start_date and end_date else (duration if duration and duration != "미정" else "해당없음")
    )

    sections = {
        "1. 연구 과제명(국문)": topic,
        "2. 연구 배경 및 목적": (
            "본 연구는 과학교육 맥락에서 인공지능 챗봇 기반 수업의 교육적 효과를 검토하기 위해 수행한다. "
            "특히 학생의 과학긍정 경험과 인공지능 태도 변화에 주목하여, 수업 설계 및 학교 현장 적용에 필요한 근거를 제시하는 것을 목적으로 한다."
        ),
        "3. 연구 설계 및 방법": (
            f"본 연구는 혼합연구 설계를 따른다. 연구 방법은 다음과 같다: {method}. "
            f"사전·사후 설문 자료는 기술통계 및 비교 분석으로 처리하고, 학습 로그 및 성찰일지는 코딩 기반 주제 분석을 수행한다. "
            f"예상 연구대상자는 {sample_size}명이며, 연구기간은 {duration}이다."
        ),
        "4. 연구대상자 선정 및 제외 기준": (
            "연구대상자는 해당 수업에 참여하는 학생 중 연구 설명을 듣고 자발적으로 참여에 동의한 자로 선정한다. "
            "연구 참여 동의가 없거나 연구 중 철회한 경우, 또는 핵심 자료가 과도하게 누락된 경우 분석에서 제외한다."
        ),
        "5. 모집 및 동의 절차": (
            "학교 관리자 및 담당 교사와 협의 후 모집 안내를 실시한다. 연구 목적, 절차, 자료 수집 범위, 예상 위험 및 이익, "
            "개인정보 처리, 보관·폐기, 문의처를 사전 설명하고 동의를 받는다. 참여자는 언제든 불이익 없이 참여를 철회할 수 있다."
        ),
        "6. 예측 가능한 위험 및 불편과 최소화 대책": (
            "예상 가능한 위험은 설문·수업 참여에 따른 경미한 피로감, 기술 사용 과정의 불편, 자료 노출에 대한 심리적 부담이다. "
            "이를 줄이기 위해 최소정보 수집, 중단권 고지, 비식별화 처리, 연구진 접근권한 제한을 적용한다. "
            + ("대면 연구이므로 학교 안전·보건 지침과 감염예방 수칙을 준수한다." if face_to_face == "예" else "비대면 또는 혼합 상황에서는 플랫폼 보안 및 접근 통제를 강화한다.")
        ),
        "7. 개인정보 및 연구자료 보호 계획": (
            "자료는 연구식별코드로 가명처리하고, 직접식별정보는 분리 보관한다. "
            "연구자료 저장소의 접근권한을 제한하며 계정 보안과 비밀번호 정책을 적용한다. "
            + ("본 연구는 민감정보 수집을 포함하지 않는다." if sensitive == "아니오" else "민감정보 수집이 포함될 경우 별도 동의 절차를 적용한다.")
        ),
        "8. 자료 보관 및 폐기 계획": (
            "연구 종료 후 기관 지침에 따른 보관기간 동안 자료를 안전하게 보관한다. "
            "전자자료는 복구가 어려운 방식으로 안전삭제하고, 종이문서는 파쇄한다. "
            "식별키는 분석자료와 분리 보관 후 동일 기준으로 폐기한다."
        ),
        "9. 보상 및 배상 계획": (
            "연구 참여에 대한 금전적 보상은 해당없음으로 한다. "
            "다만 연구와 관련된 예기치 않은 손상 또는 권익 침해가 발생할 경우 기관 절차에 따라 사실관계를 확인하고 필요한 조치를 제공한다."
        ),
        "10. 연구 수행 기관 및 소속": f"수행기관: {institution} / 소속: {department}",
        "11. 검토 메모": (
            "본 문서는 자동작성 초안이며, 최종 제출 전 연구책임자가 기관 IRB 양식 및 최신 지침에 맞게 문구와 절차를 최종 검토·수정한다."
        ),
    }

    draft = {
        "meta": {
            "topic": topic,
            "method": method,
            "institution": institution,
            "department": department,
            "pi_name": PI_FIXED["pi_name"],
            "pi_phone": PI_FIXED["pi_tel"],
            "pi_affiliation": PI_FIXED["pi_affiliation"],
            "study_period_text": study_period_text,
            "source": "manual-utf8-file",
        },
        "sections": sections,
    }

    out_dir = root / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "irb_from_input_final.json"
    md_path = out_dir / "irb_from_input_final.md"
    hwpx_path = out_dir / "irb_from_input_final.hwpx"

    json_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(irb_agent.render_markdown(draft), encoding="utf-8")
    irb_agent.write_hwpx_from_template(root / "irb-template.hwpx", hwpx_path, draft)

    print(json_path)
    print(md_path)
    print(hwpx_path)


if __name__ == "__main__":
    main()
