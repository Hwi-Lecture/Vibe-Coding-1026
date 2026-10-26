# 1. RSS 수집

이 폴더 전체를 작업 폴더로 사용하거나 새 빈 폴더에 복사합니다. Python 3.12 이상이 필요하며 추가 패키지는 없습니다.

## 실행

```powershell
python collect_news.py
```

## 저장 자료로 확인

2026-10-26에 실제 수집한 RSS가 data 폴더에 있습니다. `python collect_news.py --offline`은 외부 연결 없이 이 자료를 확인합니다.

수집 결과: data/news_rss.xml, data/news.json, data/news.csv.
