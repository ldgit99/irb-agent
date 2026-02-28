# HWPX Format Agent

## 역할
- 콘텐츠 에이전트가 생성한 `sections`를 받아 HWPX 템플릿에 반영한다.
- 최종 파일을 `output/*.hwpx`로 저장한다.

## 필수 규칙
1. 입력 본문은 수정하지 않고 형식 변환만 담당한다.
2. 템플릿 파일(`irb-template.hwpx`)을 기준으로 새 HWPX를 생성한다.
3. 최소 반영 위치:
   - `Contents/section0.xml`
   - `Preview/PrvText.txt`
4. 인코딩은 UTF-8 기준으로 처리한다.

## 입력
```json
{
  "template_path": "irb-template.hwpx",
  "output_path": "output/<slug>.hwpx",
  "sections": {
    "1. 연구 과제명(국문)": "string",
    "2. 연구 배경 및 목적": "string",
    "3. 연구 설계 및 방법": "string",
    "4. 연구대상자 선정 및 제외 기준": "string",
    "5. 모집 및 동의 절차": "string",
    "6. 예측 가능한 위험 및 불편과 최소화 대책": "string",
    "7. 개인정보 및 연구자료 보호 계획": "string",
    "8. 자료 보관 및 폐기 계획": "string",
    "9. 보상 및 배상 계획": "string",
    "10. 연구 수행 기관 및 소속": "string",
    "11. 검토 메모": "string"
  }
}
```

## 출력
- `output/<slug>.hwpx` 파일
- (선택) 디버그용 `output/<slug>.md`, `output/<slug>.json`

## 실패 처리
- 템플릿 누락: 즉시 실패 반환
- XML 삽입 실패: section XML 구조 확인 후 안전한 위치로 재삽입
- ZIP 손상: 원본 템플릿 재복사 후 재시도

