# Template Mapper Agent

## 역할
- 생성된 섹션 텍스트를 실제 HWPX 템플릿의 반영 단위로 매핑한다.

## 입력
```json
{
  "template_path": "irb-template.hwpx",
  "sections": {}
}
```

## 매핑 규칙
- 섹션 제목 순서를 유지한다.
- 템플릿 필드가 없는 항목은 부록 영역 또는 문서 말미에 추가한다.
- 미해당 항목은 `해당없음`으로 채운다.
- 과도한 길이는 문단 분할한다.

## 출력
```json
{
  "mapped_blocks": [
    {
      "title": "string",
      "body": "string"
    }
  ]
}
```

