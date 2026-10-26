# 2. 관심 뉴스와 화면

이 폴더 전체를 작업 폴더로 사용하거나 새 빈 폴더에 복사합니다. Python 3.12 이상이 필요하며 추가 패키지는 없습니다.

## 실행

```powershell
python collect_news.py
python make_news_dashboard.py
```

완성된 `news_dashboard.html`을 더블클릭합니다. `--keywords "난방,히트펌프"` 옵션으로 관심 키워드를 지정할 수 있습니다. 화면에서 키워드를 바꾼 것만으로 저장 파일이나 AI 요약이 갱신되지는 않습니다.

## 저장 자료로 확인

2026-10-26에 실제 수집한 RSS가 data 폴더에 있습니다. `python collect_news.py --offline`은 외부 연결 없이 이 자료를 확인합니다.

수집 결과: data/news_rss.xml, data/news.json, data/news.csv.
선별 결과: data/interest_news.json, news_dashboard.html.
