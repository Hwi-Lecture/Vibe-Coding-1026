# 3. AI 뉴스 브리핑

이 폴더 전체를 작업 폴더로 사용하거나 새 빈 폴더에 복사합니다. Python 3.12 이상이 필요하며 AI 단계에는 openai 패키지가 필요합니다. 최상위 install.bat 또는 requirements.txt로 설치합니다.

## 실행

```powershell
python collect_news.py
python make_news_dashboard.py
python make_news_briefing.py
```

브리핑 실행 전 `.env.example`을 `.env`로 복사해 `openai_api_key`와 강사가 안내한 `openai_model`을 입력합니다. API 키를 공유하지 않습니다.

완성된 `news_dashboard.html`을 더블클릭합니다. `--keywords "난방,히트펌프"` 옵션으로 관심 키워드를 지정할 수 있습니다. 화면에서 키워드를 바꾼 것만으로 저장 파일이나 AI 요약이 갱신되지는 않습니다.

## 저장 자료로 확인

2026-10-26에 실제 수집한 RSS가 data 폴더에 있습니다. `python collect_news.py --offline`은 외부 연결 없이 이 자료를 확인합니다.

`python make_news_briefing.py --no-ai`는 API 호출 없이 목록과 안내 화면을 생성합니다. 미리 제공된 AI 요약은 없으며, 키가 없거나 API가 실패해도 목록은 볼 수 있습니다.

수집 결과: data/news_rss.xml, data/news.json, data/news.csv.
선별 결과: data/interest_news.json, news_dashboard.html.
브리핑 결과: data/news_briefing.json. 성공한 AI 요약은 data/briefing_cache.json에 보관해 재사용합니다.

이 단계별 참고 코드는 실제 제공되는 OpenAI 키를 사용합니다. 노션의 Gemini 지시문과 기존 통합 예제는 그대로 유지합니다.
