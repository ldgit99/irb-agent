#!/usr/bin/env python3
import argparse
import json
import os
import re
import urllib.error
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

PI_FIXED = {
    "name": "이동국",
    "position": "조교수",
    "affiliation": "경북대학교",
    "major": "교육공학",
    "tel": "053-950-5845",
    "hp": "010-2656-5132",
    "email": "dklee@knu.ac.kr",
}


TEMPLATE_GUIDELINES = [
    "계획서 작성 시 붉은색 이탤릭체 설명/예시는 최종 제출본에서 삭제한다.",
    "본 양식은 공통 양식이며, 2차자료 연구는 연구대상자를 2차자료로 보고 작성한다. (예: 연구대상자 수 -> 2차자료 문건 수)",
    "해당되지 않는 항목은 '해당없음'으로 기입한다.",
    "연구 목적, 가설, 선행연구 근거, 연구 정당성을 구체적으로 작성한다.",
    "연구대상자가 실제로 수행할 절차와 소요시간을 구체적으로 작성한다.",
    "윤리적 고려사항과 그 대응 방안을 명시한다.",
    "연구 수행 장소/절차 및 안전하고 적절한 수행을 위한 정보(보호 대책)를 포함한다.",
    "모집 방법(온/오프라인 공고, 기관 승인 등)과 동의 획득 절차를 구체적으로 작성한다.",
    "선정기준/제외기준을 구체적으로 작성한다.",
    "연구대상자 수는 최소 필요 규모로 산출하고 근거(선행연구, 통상 수치 등)를 제시한다.",
    "예측 부작용에는 개인정보 유출 및 인체유래물 유출 위험도 포함해 작성한다.",
    "대면 연구인 경우 코로나19 안전 대책을 포함한다.",
    "개인정보 보호 대책(암호화, 접근권한, 보관/폐기)을 구체적으로 작성한다.",
    "인체유래물 관련 항목은 해당 연구에서만 작성한다.",
    "보상(참여에 대한 금전적 보상)과 배상(손상 발생 시 조치)을 구분해 작성한다.",
]

TEMPLATE_EXAMPLES = [
    "모집 예시: 기관장 승인 후 담당자 협조를 받아 온/오프라인 게시판 및 단체 SNS에 모집 문건을 게시한다.",
    "부작용 예시: 설문지 작성에 따른 일상적 피로감/불편함이 있을 수 있다.",
    "중단권 예시: 연구대상자가 원하면 불이익 없이 언제든 연구 참여를 중단할 수 있음을 충분히 안내한다.",
]

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


def sanitize_filename(text: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "_", text.strip())
    return text[:50].strip("_") or "irb_draft"


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM 응답에서 JSON 객체를 찾지 못했습니다.")
    return json.loads(text[start : end + 1])


def extract_output_text_from_payload(payload: dict) -> str:
    # Preferred field in some SDK/endpoint responses.
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text

    # Fallback: parse structured output blocks.
    output = payload.get("output", [])
    chunks: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") in ("output_text", "text"):
                    t = c.get("text")
                    if isinstance(t, str) and t.strip():
                        chunks.append(t)
    if chunks:
        return "\n".join(chunks)
    return ""


def call_responses_api(api_key: str, model: str, user_payload: dict, system_prompt: str) -> str:
    request_body = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI API 오류: {e.code} {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenAI API 연결 오류: {e}") from e
    payload = json.loads(raw)
    return extract_output_text_from_payload(payload)


def sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return len([p for p in parts if p.strip()])


def validate_section_constraints(sections: dict) -> list[str]:
    issues = []
    s2 = sections.get("2. 연구 배경 및 목적", "")
    s3 = sections.get("3. 연구 설계 및 방법", "")
    if sentence_count(s2) < 10:
        issues.append("섹션 2 문장 수가 10 미만")
    if sentence_count(s3) < 30:
        issues.append("섹션 3 문장 수가 30 미만")
    required_tokens = ["1.", "2.", "3.", "4.", "5."]
    if not all(tok in s3 for tok in required_tokens):
        issues.append("섹션 3에 권고 순서(1~5) 표기가 누락됨")
    return issues


def generate_sections_with_llm(
    *,
    topic: str,
    method: str,
    institution: str,
    department: str,
    sample_size: int,
    duration_months: int,
    model: str,
) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 환경변수가 필요합니다.")

    prompt = {
        "input": {
            "research_topic": topic,
            "research_method": method,
            "institution": institution,
            "department": department,
            "sample_size": sample_size,
            "duration_months": duration_months,
            "template_guidelines": TEMPLATE_GUIDELINES,
            "template_examples": TEMPLATE_EXAMPLES,
        },
        "task": (
            "위 정보를 바탕으로 IRB 연구계획서 초안을 한국어로 작성하라. "
            "아래 섹션 제목 11개를 정확히 key로 가지는 JSON만 출력하라. "
            "각 value는 문단 텍스트(필요시 여러 문장)로 작성하라."
        ),
        "required_section_titles": SECTION_TITLES,
        "writing_rules": [
            "템플릿 지침을 반영하라.",
            "해당없음 항목이 필요하면 명시하라.",
            "과도한 단정 대신 IRB 제출용 신중한 문체를 사용하라.",
            "개인정보 보호/보관/폐기/동의철회/위험 최소화를 구체적으로 작성하라.",
            "섹션 '2. 연구 배경 및 목적'은 최소 10문장으로 작성하라.",
            "섹션 '2. 연구 배경 및 목적'에는 연구 목적의 구체성, 가설(있다면), 가설 입증 설명, 선행연구로서의 성격(해당 시)을 포함하라.",
            "섹션 '3. 연구 설계 및 방법'은 최소 30문장으로 작성하라.",
            "섹션 '3. 연구 설계 및 방법'에는 연구대상자가 수행할 일과 소요시간, 계획/절차를 구체적으로 포함하라.",
            "섹션 '3. 연구 설계 및 방법'에는 윤리적 고려사항과 대응방안, 연구 장소 및 안전한 수행 절차를 포함하라.",
            "섹션 '3. 연구 설계 및 방법'은 다음 순서를 명시적으로 포함하라: 1. 연구 설계 및 연구 대상, 2. 자료수집 방법, 3. 연구도구, 4. 연구 계획 및 절차, 5. 자료분석 방법.",
        ],
    }

    feedback = None
    last_issues = []
    for _attempt in range(3):
        payload_prompt = dict(prompt)
        if feedback:
            payload_prompt["constraint_feedback"] = feedback

        output_text = call_responses_api(
            api_key=api_key,
            model=model,
            user_payload=payload_prompt,
            system_prompt="You are an expert IRB document drafter. Return valid JSON only, no markdown.",
        )
        if not output_text:
            raise RuntimeError("LLM 응답에서 텍스트를 찾지 못했습니다.")

        sections = extract_json_object(output_text)
        missing = [k for k in SECTION_TITLES if k not in sections]
        if missing:
            feedback = {"missing_sections": missing, "instruction": "누락 섹션을 모두 채워 JSON만 다시 출력하라."}
            continue

        normalized = {k: str(sections[k]).strip() for k in SECTION_TITLES}
        issues = validate_section_constraints(normalized)
        if not issues:
            return normalized
        last_issues = issues
        feedback = {"issues": issues, "instruction": "문장 수/구성 제약을 모두 만족하도록 전체를 다시 작성하라."}

    # Final recovery: expand section 2/3 only, then re-check.
    if "normalized" in locals():
        sec2 = normalized.get("2. 연구 배경 및 목적", "")
        sec3 = normalized.get("3. 연구 설계 및 방법", "")
        if sentence_count(sec2) < 10:
            expand2 = call_responses_api(
                api_key=api_key,
                model=model,
                user_payload={
                    "section_name": "2. 연구 배경 및 목적",
                    "current_text": sec2,
                    "requirement": "최소 10문장, 목적·가설·가설검증 설명·선행연구 성격 포함",
                    "output": "plain text only",
                },
                system_prompt="Expand and rewrite the given Korean section text to satisfy constraints. Return plain text only.",
            )
            if expand2.strip():
                normalized["2. 연구 배경 및 목적"] = expand2.strip()
        if sentence_count(sec3) < 30:
            expand3 = call_responses_api(
                api_key=api_key,
                model=model,
                user_payload={
                    "section_name": "3. 연구 설계 및 방법",
                    "current_text": sec3,
                    "requirement": "최소 30문장. 반드시 1.연구 설계 및 연구 대상 2.자료수집 방법 3.연구도구 4.연구 계획 및 절차 5.자료분석 방법 순서로 작성",
                    "output": "plain text only",
                },
                system_prompt="Expand and rewrite the given Korean section text to satisfy constraints. Return plain text only.",
            )
            if expand3.strip():
                normalized["3. 연구 설계 및 방법"] = expand3.strip()

        final_issues = validate_section_constraints(normalized)
        if not final_issues:
            return normalized
        raise RuntimeError(f"LLM 응답이 제약을 만족하지 못함: {final_issues}")

    raise RuntimeError(f"LLM 응답이 제약을 만족하지 못함: {last_issues}")


def build_irb_draft(
    *,
    topic: str,
    method: str,
    institution: str,
    department: str,
    sample_size: int,
    duration_months: int,
    model: str,
) -> dict:
    today = date.today().isoformat()
    sections = generate_sections_with_llm(
        topic=topic,
        method=method,
        institution=institution,
        department=department,
        sample_size=sample_size,
        duration_months=duration_months,
        model=model,
    )
    return {
        "meta": {
            "created_at": today,
            "topic": topic,
            "method": method,
            "institution": institution,
            "department": department,
            "llm_model": model,
        },
        "sections": sections,
    }


def render_markdown(draft: dict) -> str:
    lines = ["# IRB 연구계획서 초안", ""]
    for title, body in draft["sections"].items():
        lines.append(f"## {title}")
        lines.append(body)
        lines.append("")
    lines.append("## 템플릿 작성 지침 반영")
    for i, item in enumerate(TEMPLATE_GUIDELINES, start=1):
        lines.append(f"{i}. {item}")
    lines.append("")
    lines.append("## 템플릿 예시 반영")
    for i, item in enumerate(TEMPLATE_EXAMPLES, start=1):
        lines.append(f"{i}. {item}")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_hwpx_lines(draft: dict) -> list[str]:
    lines = ["[LLM 자동작성 IRB 초안]"]
    lines.append("")
    for title, body in draft["sections"].items():
        lines.append(title)
        lines.append(body)
        lines.append("")
    lines.append("템플릿 작성 지침 반영")
    for i, item in enumerate(TEMPLATE_GUIDELINES, start=1):
        lines.append(f"{i}. {item}")
    lines.append("")
    lines.append("템플릿 예시 반영")
    for i, item in enumerate(TEMPLATE_EXAMPLES, start=1):
        lines.append(f"{i}. {item}")
    return lines


def append_text_to_section_xml(section_xml: str, lines: list[str]) -> str:
    paragraphs = []
    for line in lines:
        safe = escape(line) if line else ""
        paragraphs.append(
            '<hp:p id="2147483648" paraPrIDRef="29" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="21"><hp:t>{safe}</hp:t></hp:run>'
            "</hp:p>"
        )
    block = "".join(paragraphs)
    marker = "</hs:sec>"
    if marker not in section_xml:
        raise RuntimeError("템플릿 section0.xml 구조를 찾지 못했습니다.")
    return section_xml.replace(marker, block + marker)


def _tc_text(tc: ET.Element, ns: dict) -> str:
    texts = []
    for t in tc.findall(".//hp:t", ns):
        val = (t.text or "").strip()
        if val:
            texts.append(val)
    return " ".join(texts)


def _set_tc_text(tc: ET.Element, text: str, ns_uri: str, char_pr_id: str = "12") -> None:
    sub = tc.find(f"{{{ns_uri}}}subList")
    if sub is None:
        sub = ET.SubElement(tc, f"{{{ns_uri}}}subList")
    for child in list(sub):
        sub.remove(child)
    p = ET.SubElement(
        sub,
        f"{{{ns_uri}}}p",
        {"id": "2147483648", "paraPrIDRef": "30", "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"},
    )
    # Force a normal black-ish body style by using a dedicated char property id.
    run = ET.SubElement(p, f"{{{ns_uri}}}run", {"charPrIDRef": char_pr_id})
    t = ET.SubElement(run, f"{{{ns_uri}}}t")
    t.text = text


def fill_template_tables(section_xml: str, draft: dict) -> str:
    ns_uri = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    ns = {"hp": ns_uri}
    root = ET.fromstring(section_xml)
    sections = draft["sections"]
    meta = draft.get("meta", {})
    study_period_text = str(meta.get("study_period_text", "")).strip() or "해당없음"

    row_map = {
        "연구목적": sections.get("2. 연구 배경 및 목적", "") or "해당없음",
        "연구배경": sections.get("2. 연구 배경 및 목적", "") or "해당없음",
        "연구 예정기간": study_period_text,
        "연구내용": sections.get("3. 연구 설계 및 방법", "") or "해당없음",
        "연구대상자 모집방법": sections.get("5. 모집 및 동의 절차", "") or "해당없음",
        "연구대상자 연구 설명 방법 및 동의 취득 절차": sections.get("5. 모집 및 동의 절차", "") or "해당없음",
        "연구 자료 (설문지, 면담결과, 검사결과, 인체유래물 등) 수집 방법": sections.get("3. 연구 설계 및 방법", "") or "해당없음",
        "연구대상자 선정기준 및 정당성": sections.get("4. 연구대상자 선정 및 제외 기준", "") or "해당없음",
        "연구대상자 제외기준": sections.get("4. 연구대상자 선정 및 제외 기준", "") or "해당없음",
        "연구대상자 및 인체유래물의 수(량)": sections.get("3. 연구 설계 및 방법", "") or "해당없음",
        "연구대상자 및 인체유래물의 수(량) 산출근거 및 통계방법 (실험결과에 기초한 N수 계산)": sections.get("3. 연구 설계 및 방법", "") or "해당없음",
        "자료분석 및 통계적 방법": sections.get("3. 연구 설계 및 방법", "") or "해당없음",
        "예측 효능효과": "종속 변인이 사전 대비 사후 측정에서 통계적으로 유의하게 상승할 것으로 예측된다.",
        "예측 부작용 및 주의사항": sections.get("6. 예측 가능한 위험 및 불편과 최소화 대책", "") or "해당없음",
        "연구대상자 안전보호에 관한 대책 (시험중지, 부작용에 대한 대처 사항 등)": sections.get("6. 예측 가능한 위험 및 불편과 최소화 대책", "") or "해당없음",
        "연구대상자 개인정보 및 연구 관련 자료 보호(관리, 보관 및 폐기 등)에 관한 대책": sections.get("7. 개인정보 및 연구자료 보호 계획", "") or "해당없음",
        "인체유래물의 관리, 보관 및 폐기에 관한 계획": "해당없음",
        "연구대상자 보 상 및 배상에 관한 계획": sections.get("9. 보상 및 배상 계획", "") or "해당없음",
    }

    # Fill row-based 2-column tables: first cell is label, second cell is content.
    for tr in root.findall(".//hp:tr", ns):
        tcs = tr.findall("./hp:tc", ns)
        if len(tcs) < 2:
            continue
        label = _tc_text(tcs[0], ns)
        if label in row_map:
            _set_tc_text(tcs[1], row_map[label] or "해당없음", ns_uri, char_pr_id="12")

    # Fill top metadata table (table id=1882751667)
    for tbl in root.findall(".//hp:tbl", ns):
        if tbl.get("id") == "1882751666":
            # Row layout: [연구책임자 성명][value][연구책임자 소속대학/학과][value]
            rows = tbl.findall("./hp:tr", ns)
            if rows:
                tcs = rows[0].findall("./hp:tc", ns)
                if len(tcs) >= 4:
                    pi_name = str(meta.get("pi_name", "")).strip() or "해당없음"
                    pi_aff = str(meta.get("pi_affiliation", "")).strip() or str(meta.get("department", "")).strip() or "해당없음"
                    _set_tc_text(tcs[1], pi_name, ns_uri, char_pr_id="12")
                    _set_tc_text(tcs[3], pi_aff, ns_uri, char_pr_id="12")
            continue
        if tbl.get("id") != "1882751667":
            continue
        rows = tbl.findall("./hp:tr", ns)
        for tr in rows:
            tcs = tr.findall("./hp:tc", ns)
            if len(tcs) < 2:
                continue
            first = _tc_text(tcs[0], ns)
            second = _tc_text(tcs[1], ns) if len(tcs) > 1 else ""
            if "연구 과제명" in first and "국문" in second and len(tcs) >= 3:
                _set_tc_text(tcs[2], sections.get("1. 연구 과제명(국문)", ""), ns_uri, char_pr_id="12")
            elif first == "영문" and len(tcs) >= 2:
                _set_tc_text(tcs[1], "Not provided", ns_uri, char_pr_id="12")
            elif "연구 실시기관" in first and "실시기관명" in second and len(tcs) >= 3:
                inst = sections.get("10. 연구 수행 기관 및 소속", "")
                _set_tc_text(tcs[2], inst, ns_uri, char_pr_id="12")
            elif "실시기관 주소" in first and len(tcs) >= 2:
                _set_tc_text(tcs[1], "해당없음", ns_uri, char_pr_id="12")
            elif "연구 책임자" in first and len(tcs) >= 2:
                fixed = (
                    f"성명: {PI_FIXED['name']} / 직위: {PI_FIXED['position']} / 소속: {PI_FIXED['affiliation']} "
                    f"/ 전공분야: {PI_FIXED['major']} / 전화번호(Tel): {PI_FIXED['tel']} / (H.P): {PI_FIXED['hp']} "
                    f"/ e-mail: {PI_FIXED['email']}"
                )
                _set_tc_text(tcs[1], fixed, ns_uri, char_pr_id="12")

    # Special handling for single-column explanatory tables.
    for tbl in root.findall(".//hp:tbl", ns):
        tid = tbl.get("id")
        rows = tbl.findall("./hp:tr", ns)
        if tid == "1882751690" and len(rows) >= 4:
            # Row 2: 예측 효능효과 상세 내용
            tcs = rows[1].findall("./hp:tc", ns)
            if tcs:
                _set_tc_text(
                    tcs[0],
                    "종속 변인이 사전 대비 사후 측정에서 통계적으로 유의하게 상승할 것으로 예측된다.",
                    ns_uri,
                    char_pr_id="12",
                )
            # Row 4: 예측 부작용 및 주의사항 상세 내용
            tcs = rows[3].findall("./hp:tc", ns)
            if tcs:
                _set_tc_text(
                    tcs[0],
                    sections.get("6. 예측 가능한 위험 및 불편과 최소화 대책", "") or "해당없음",
                    ns_uri,
                    char_pr_id="12",
                )
        if tid == "1882751691" and len(rows) >= 8:
            # Row 6: 인체유래물 계획(미해당 시 해당없음)
            tcs = rows[5].findall("./hp:tc", ns)
            if tcs:
                _set_tc_text(tcs[0], "해당없음", ns_uri, char_pr_id="12")
            # Row 8: 보상/배상 상세
            tcs = rows[7].findall("./hp:tc", ns)
            if tcs:
                _set_tc_text(
                    tcs[0],
                    sections.get("9. 보상 및 배상 계획", "") or "해당없음",
                    ns_uri,
                    char_pr_id="12",
                )

    ET.register_namespace("hp", ns_uri)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def write_hwpx_from_template(template_path: Path, output_path: Path, draft: dict) -> None:
    lines = build_hwpx_lines(draft)
    preview_text = "\n".join(lines).rstrip() + "\n"
    with zipfile.ZipFile(template_path, "r") as zin:
        with zipfile.ZipFile(output_path, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "Preview/PrvText.txt":
                    data = preview_text.encode("utf-8")
                elif item.filename == "Contents/section0.xml":
                    section_xml = data.decode("utf-8")
                    section_xml = fill_template_tables(section_xml, draft)
                    data = section_xml.encode("utf-8")
                zout.writestr(item, data)


def ask_if_missing(args: argparse.Namespace) -> argparse.Namespace:
    if not args.topic:
        args.topic = input("연구 주제를 입력하세요: ").strip()
    if not args.method:
        args.method = input("연구 방법을 입력하세요(예: 설문조사, 인터뷰, 실험): ").strip()
    if not args.institution:
        args.institution = input("수행기관을 입력하세요: ").strip() or "미정"
    if not args.department:
        args.department = input("소속을 입력하세요: ").strip() or "미정"
    if args.sample_size is None:
        raw = input("예상 표본 수(숫자)를 입력하세요 [기본값 100]: ").strip()
        args.sample_size = int(raw) if raw else 100
    if args.duration_months is None:
        raw = input("예상 연구기간(개월)을 입력하세요 [기본값 6]: ").strip()
        args.duration_months = int(raw) if raw else 6
    return args


def main() -> None:
    parser = argparse.ArgumentParser(description="간단 입력으로 IRB 연구계획서 초안을 생성합니다.")
    parser.add_argument("--topic", type=str, help="연구 주제")
    parser.add_argument("--method", type=str, help="연구 방법")
    parser.add_argument("--institution", type=str, default="", help="수행기관")
    parser.add_argument("--department", type=str, default="", help="소속")
    parser.add_argument("--sample-size", type=int, default=None, help="표본 수")
    parser.add_argument("--duration-months", type=int, default=None, help="연구기간(개월)")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        help="OpenAI 모델명 (기본: OPENAI_MODEL 또는 gpt-4.1-mini)",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("irb-template.hwpx"),
        help="원본 HWPX 템플릿 경로",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="출력 디렉터리")

    args = ask_if_missing(parser.parse_args())

    draft = build_irb_draft(
        topic=args.topic,
        method=args.method,
        institution=args.institution,
        department=args.department,
        sample_size=args.sample_size,
        duration_months=args.duration_months,
        model=args.model,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(args.topic)
    json_path = args.output_dir / f"{stem}.json"
    md_path = args.output_dir / f"{stem}.md"
    hwpx_path = args.output_dir / f"{stem}.hwpx"

    json_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(draft), encoding="utf-8")
    write_hwpx_from_template(args.template, hwpx_path, draft)

    print(f"생성 완료: {json_path}")
    print(f"생성 완료: {md_path}")
    print(f"생성 완료: {hwpx_path}")


if __name__ == "__main__":
    main()
