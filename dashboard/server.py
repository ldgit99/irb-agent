#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "dashboard"
INPUT_PATH = ROOT / "input" / "input-form.md"
OUTPUT_DIR = ROOT / "output"
HISTORY_PATH = OUTPUT_DIR / "run_history.jsonl"
ALLOW_UI_API_KEY = os.getenv("IRB_DASHBOARD_ALLOW_UI_API_KEY", "0").strip() == "1"
RUNS: dict[str, dict] = {}
RUNS_LOCK = threading.Lock()
RUN_STEP_DEFS = [
    ("save-input", "입력 저장"),
    ("prepare", "실행 준비"),
    ("generate", "본문 생성"),
    ("postprocess", "결과 정리"),
    ("quality", "품질 점수"),
    ("history", "이력 기록"),
]

FIELDS = {
    "연구 주제": "research_topic",
    "연구 과제명(영문)": "research_topic_en",
    "연구 방법": "research_method",
    "연구 시작일": "study_start",
    "연구 종료일": "study_end",
    "연구 대상 유형": "target_type",
    "연구 대상 인원": "target_count",
    "연구 설계 유형": "study_design",
    "동의 방식": "consent_method",
    "자료 수집 도구": "data_tools",
    "연구 위험 수준": "risk_level",
    "수행기관": "institution",
    "소속": "department",
    "민감정보 수집 여부": "sensitive_data",
    "대면 진행 여부": "face_to_face",
    "연구책임자 성명": "pi_name",
    "연구책임자 전화번호": "pi_phone",
}

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


def parse_input_markdown(text: str) -> dict[str, str]:
    values = {v: "" for v in FIELDS.values()}
    for label, key in FIELDS.items():
        m = re.search(rf"^[\*\-]\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if m:
            values[key] = m.group(1).strip()
    return values


def render_input_markdown(v: dict[str, str]) -> str:
    return f"""# IRB 입력 양식

아래 항목을 작성하면 IRB 계획서 자동 생성에 사용됩니다.

## 필수 입력

* 연구 주제: {v.get("research_topic","")}
* 연구 과제명(영문): {v.get("research_topic_en","")}
* 연구 방법: {v.get("research_method","")}
* 연구 시작일: {v.get("study_start","")}
* 연구 종료일: {v.get("study_end","")}
* 연구 대상 유형: {v.get("target_type","")}
* 연구 대상 인원: {v.get("target_count","")}

## 추천 입력

* 연구 설계 유형: {v.get("study_design","")}
* 동의 방식: {v.get("consent_method","")}
* 자료 수집 도구: {v.get("data_tools","")}
* 연구 위험 수준: {v.get("risk_level","")}

## 선택 입력

* 수행기관: {v.get("institution","")}
* 소속: {v.get("department","")}
* 민감정보 수집 여부: {v.get("sensitive_data","")}
* 대면 진행 여부: {v.get("face_to_face","")}

## 연구책임자 정보

* 연구책임자 성명: {v.get("pi_name","")}
* 연구책임자 전화번호: {v.get("pi_phone","")}

## 작성 팁

* 연구 방법은 수업 절차, 자료수집, 분석 방법이 보이게 작성하세요.
* 시작일/종료일은 YYYY-MM-DD 형식 권장.
* 연구 대상 유형과 인원은 심의에서 자주 확인하는 핵심 항목입니다.
"""


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "_", (text or "").strip())
    return cleaned[:50].strip("_") or "irb_draft"


def parse_sample_size(raw: str) -> int:
    m = re.search(r"\d+", raw or "")
    return int(m.group(0)) if m else 100


def parse_duration_months(start_raw: str, end_raw: str) -> int:
    try:
        s_year, s_month = int(start_raw[:4]), int(start_raw[5:7])
        e_year, e_month = int(end_raw[:4]), int(end_raw[5:7])
        months = (e_year - s_year) * 12 + (e_month - s_month) + 1
        return max(months, 1)
    except Exception:
        return 6


def run_subprocess(cmd: list[str], timeout: int = 240, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    if env_extra:
        env.update({k: v for k, v in env_extra.items() if v is not None})
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def normalize_outputs_from_slug(slug: str) -> dict[str, str]:
    source = {
        "json": OUTPUT_DIR / f"{slug}.json",
        "md": OUTPUT_DIR / f"{slug}.md",
        "hwpx": OUTPUT_DIR / f"{slug}.hwpx",
    }
    target = {
        "json": OUTPUT_DIR / "irb_from_input_final.json",
        "md": OUTPUT_DIR / "irb_from_input_final.md",
        "hwpx": OUTPUT_DIR / "irb_from_input_final.hwpx",
    }
    for ext in ("json", "md", "hwpx"):
        if source[ext].exists():
            shutil.copyfile(source[ext], target[ext])
    return {k: f"output/{v.name}" for k, v in target.items()}


def count_sentences(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return len([p for p in parts if p.strip()])


def compute_quality_scores(json_path: Path) -> dict:
    if not json_path.exists():
        return {"total": 0.0, "sentence_score": 0.0, "required_score": 0.0, "details": ["출력 JSON 없음"]}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {"total": 0.0, "sentence_score": 0.0, "required_score": 0.0, "details": ["출력 JSON 파싱 실패"]}

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


def append_history(entry: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_history(limit: int = 20) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(entries))


def _make_run_stages() -> list[dict]:
    return [{"id": sid, "title": title, "cls": "wait", "status": "대기"} for sid, title in RUN_STEP_DEFS]


def _update_run_stage(run_id: str, stage_id: str, cls: str, message: str = "") -> None:
    status_map = {"wait": "대기", "run": "실행중", "ok": "완료", "bad": "실패"}
    with RUNS_LOCK:
        run = RUNS.get(run_id)
        if not run:
            return
        for stage in run["stages"]:
            if stage["id"] == stage_id:
                stage["cls"] = cls
                stage["status"] = status_map.get(cls, "대기")
                break
        run["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if message:
            run["message"] = message


def _normalize_run_summary(run: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "mode": run.get("mode", "api"),
        "stages": run.get("stages", []),
        "message": run.get("message", ""),
        "warnings": run.get("warnings", []),
        "started_at": run.get("started_at"),
        "updated_at": run.get("updated_at"),
        "finished_at": run.get("finished_at"),
        "result": run.get("result"),
    }


def run_api_pipeline(
    values: dict[str, str],
    api_key: str = "",
    model_override: str = "",
    run_id: str = "",
) -> dict:
    progress = (lambda stage, cls, msg="": _update_run_stage(run_id, stage, cls, msg)) if run_id else None

    if progress:
        progress("prepare", "run", "입력 파라미터를 계산하고 있습니다.")
    topic = values.get("research_topic", "").strip()
    topic_en = values.get("research_topic_en", "").strip()
    method = values.get("research_method", "").strip()
    institution = values.get("institution", "").strip() or "미정"
    department = values.get("department", "").strip() or "미정"
    sample_size = parse_sample_size(values.get("target_count", ""))
    duration_months = parse_duration_months(values.get("study_start", ""), values.get("study_end", ""))
    model = model_override.strip() or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    if progress:
        progress("prepare", "ok", "실행 준비가 완료되었습니다.")

    cmd = [
        sys.executable,
        str(ROOT / "irb_agent.py"),
        "--topic",
        topic,
        "--method",
        method,
        "--topic-en",
        topic_en,
        "--institution",
        institution,
        "--department",
        department,
        "--sample-size",
        str(sample_size),
        "--duration-months",
        str(duration_months),
        "--model",
        model,
        "--output-dir",
        str(OUTPUT_DIR),
    ]

    env_extra = {}
    if api_key.strip():
        env_extra["OPENAI_API_KEY"] = api_key.strip()
    if model.strip():
        env_extra["OPENAI_MODEL"] = model.strip()

    if progress:
        progress("generate", "run", "IRB 본문 생성을 실행하고 있습니다.")
    code, out, err = run_subprocess(cmd, env_extra=env_extra)
    now = datetime.now().isoformat(timespec="seconds")

    if code == 0:
        if progress:
            progress("generate", "ok", "본문 생성이 완료되었습니다.")
            progress("postprocess", "run", "출력 파일을 정리하고 있습니다.")
        slug = sanitize_filename(topic)
        outputs = normalize_outputs_from_slug(slug)
        if progress:
            progress("postprocess", "ok", "출력 파일 정리가 완료되었습니다.")
            progress("quality", "run", "품질 점수를 계산하고 있습니다.")
        quality = compute_quality_scores(OUTPUT_DIR / "irb_from_input_final.json")
        if progress:
            progress("quality", "ok", "품질 점수 계산이 완료되었습니다.")
            progress("history", "run", "실행 이력을 기록하고 있습니다.")
        result = {"ok": True, "mode": "api", "outputs": outputs, "quality": quality, "stdout": out}
        append_history(
            {
                "timestamp": now,
                "ok": True,
                "mode": "api",
                "topic": topic,
                "model": model,
                "quality_total": quality["total"],
                "quality_sentence": quality["sentence_score"],
                "quality_required": quality["required_score"],
                "outputs": outputs,
            }
        )
        if progress:
            progress("history", "ok", "실행 이력 기록이 완료되었습니다.")
        return result

    if progress:
        progress("generate", "bad", "본문 생성 단계에서 오류가 발생했습니다.")
        progress("history", "run", "실패 이력을 기록하고 있습니다.")
    result = {
        "ok": False,
        "mode": "api",
        "error": "API 실행 실패",
        "api_stdout": out,
        "api_stderr": err,
    }
    append_history(
        {
            "timestamp": now,
            "ok": False,
            "mode": "api",
            "topic": topic,
            "model": model,
            "error": (err or out)[:500],
        }
    )
    if progress:
        progress("history", "ok", "실패 이력 기록이 완료되었습니다.")
    return result


def _start_run(values: dict[str, str], api_key: str = "", model_override: str = "", warnings: list[str] | None = None) -> str:
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat(timespec="seconds")
    run = {
        "run_id": run_id,
        "status": "running",
        "mode": "api",
        "stages": _make_run_stages(),
        "message": "작업을 시작합니다.",
        "warnings": warnings or [],
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "result": None,
    }
    with RUNS_LOCK:
        RUNS[run_id] = run

    def worker() -> None:
        try:
            _update_run_stage(run_id, "save-input", "run", "입력 스냅샷을 저장하고 있습니다.")
            markdown = render_input_markdown(values)
            INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            INPUT_PATH.write_text(markdown, encoding="utf-8")
            _update_run_stage(run_id, "save-input", "ok", "입력 스냅샷 저장이 완료되었습니다.")

            result = run_api_pipeline(
                values,
                api_key=api_key,
                model_override=model_override,
                run_id=run_id,
            )
            with RUNS_LOCK:
                run = RUNS.get(run_id)
                if not run:
                    return
                run["result"] = result
                run["status"] = "succeeded" if result.get("ok") else "failed"
                run["finished_at"] = datetime.now().isoformat(timespec="seconds")
                run["updated_at"] = run["finished_at"]
                if result.get("ok"):
                    run["message"] = "실행이 완료되었습니다."
                else:
                    run["message"] = result.get("error", "실행에 실패했습니다.")
        except Exception as e:
            with RUNS_LOCK:
                run = RUNS.get(run_id)
                if not run:
                    return
                run["status"] = "failed"
                run["finished_at"] = datetime.now().isoformat(timespec="seconds")
                run["updated_at"] = run["finished_at"]
                run["message"] = f"서버 내부 오류: {e}"
                run["result"] = {"ok": False, "mode": "api", "error": str(e)}
                for stage in run["stages"]:
                    if stage["cls"] in ("wait", "run"):
                        stage["cls"] = "bad"
                        stage["status"] = "실패"

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return run_id


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _text(self, payload: str, code: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        body = payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file_download(self, path: Path, download_name: str) -> None:
        if not path.exists():
            self._text("File not found", code=404, ctype="text/plain; charset=utf-8")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            html = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
            self._text(html)
            return
        if path == "/api/input":
            markdown = INPUT_PATH.read_text(encoding="utf-8")
            self._json({"ok": True, "values": parse_input_markdown(markdown), "markdown": markdown})
            return
        if path == "/api/history":
            self._json({"ok": True, "items": load_history(limit=20)})
            return
        if path == "/api/run-status":
            run_id = parse_qs(parsed.query).get("run_id", [""])[0].strip()
            if not run_id:
                self._json({"ok": False, "error": "run_id가 필요합니다."}, code=400)
                return
            with RUNS_LOCK:
                run = RUNS.get(run_id)
                payload = _normalize_run_summary(run) if run else None
            if not payload:
                self._json({"ok": False, "error": "해당 run_id를 찾을 수 없습니다."}, code=404)
                return
            self._json({"ok": True, "run": payload})
            return
        if path == "/api/download/hwpx":
            candidates = [OUTPUT_DIR / "irb_from_input_final.hwpx", OUTPUT_DIR / "irb_from_input.hwpx"]
            target = next((p for p in candidates if p.exists()), None)
            if target is None:
                self._json({"ok": False, "error": "다운로드할 HWPX 파일이 없습니다."}, code=404)
                return
            self._file_download(target, "irb_application.hwpx")
            return
        self._text("Not found", code=404, ctype="text/plain; charset=utf-8")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/run":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                run_payload = json.loads(raw) if raw.strip() else {}
            except Exception:
                run_payload = {}

            values_raw = run_payload.get("values")
            if isinstance(values_raw, dict):
                values = {v: str(values_raw.get(v, "")).strip() for v in FIELDS.values()}
            else:
                try:
                    markdown = INPUT_PATH.read_text(encoding="utf-8")
                    values = parse_input_markdown(markdown)
                except Exception as e:
                    self._json({"ok": False, "error": f"입력 파일 로드 실패: {e}"}, code=500)
                    return

            required = ["research_topic", "research_method", "study_start", "study_end", "target_type", "target_count"]
            missing = [k for k in required if not str(values.get(k, "")).strip()]
            if missing:
                self._json({"ok": False, "error": f"필수 항목 누락: {', '.join(missing)}"}, code=400)
                return

            ui_api_key = str(run_payload.get("api_key", "")).strip()
            warnings: list[str] = []
            effective_api_key = ""
            if ui_api_key:
                if ALLOW_UI_API_KEY:
                    effective_api_key = ui_api_key
                else:
                    warnings.append("UI API Key 입력은 비활성화되어 무시되었습니다. 서버 환경변수 OPENAI_API_KEY를 사용하세요.")

            run_id = _start_run(
                values,
                api_key=effective_api_key,
                model_override=str(run_payload.get("model", "")),
                warnings=warnings,
            )
            self._json(
                {
                    "ok": True,
                    "accepted": True,
                    "run_id": run_id,
                    "status": "running",
                    "mode": "api",
                    "warnings": warnings,
                },
                code=202,
            )
            return

        if path != "/api/input":
            self._json({"ok": False, "error": "Not found"}, code=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
        except Exception:
            self._json({"ok": False, "error": "잘못된 JSON 요청"}, code=400)
            return

        required = ["research_topic", "research_method", "study_start", "study_end", "target_type", "target_count"]
        missing = [k for k in required if not str(payload.get(k, "")).strip()]
        if missing:
            self._json({"ok": False, "error": f"필수 항목 누락: {', '.join(missing)}"}, code=400)
            return

        values = {v: str(payload.get(v, "")).strip() for v in FIELDS.values()}
        markdown = render_input_markdown(values)
        INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        INPUT_PATH.write_text(markdown, encoding="utf-8")
        self._json({"ok": True, "path": str(INPUT_PATH.relative_to(ROOT)), "markdown": markdown})


def main() -> None:
    host = os.getenv("IRB_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("IRB_DASHBOARD_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Dashboard server running: http://{host}:{port}")
    print(f"Target file: {INPUT_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
