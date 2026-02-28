# IRB Agent Orchestrator

## 목적
- 사용자 입력(주제/방법)을 바탕으로 IRB 계획서를 자동 생성한다.
- 본문은 반드시 ChatGPT(OpenAI API)로 작성한다.
- 최종 산출물은 `output/*.hwpx`로 저장한다.

## 하위 에이전트
- `agents/chatgpt-content-agent.md`: 템플릿 지침 기반 본문 작성
- `agents/method-specialist-agent.md`: 방법론 맞춤 보정
- `agents/irb-compliance-agent.md`: 템플릿 준수 점검
- `agents/privacy-risk-agent.md`: 개인정보/민감정보 위험 점검
- `agents/qa-redteam-agent.md`: 반려 리스크 탐지
- `agents/template-mapper-agent.md`: 템플릿 표/필드 매핑
- `agents/hwpx-format-agent.md`: HWPX 반영 및 파일 생성

## 핵심 운영 규칙
1. 템플릿의 작성 지침과 예시를 프롬프트에 포함한다.
2. 템플릿 예시 문구를 그대로 복사하지 말고, 연구 맥락에 맞게 구체화한다.
3. 미해당 항목은 `해당없음`으로 명시한다.
4. 위험/동의/개인정보/보관폐기/보상배상은 반드시 분리 서술한다.
5. 표본수와 분석 방법은 근거가 보이게 작성한다.

## 실행 순서
1. 입력 수집
2. ChatGPT 본문 생성
3. 방법론 보정
4. 템플릿 준수 점검
5. 개인정보/리스크 점검
6. 레드팀 QA
7. 템플릿 표 매핑
8. HWPX 생성

