# 뉴스 브리핑 실습

노션의 3-1 → 3-2 → 3-3에 맞춘 누적 체크포인트입니다. 각 단계 폴더 안에서 직접 실행하거나, 내용 전체를 새 작업 폴더에 복사해 실행합니다.

| 단계 폴더 | 기능 |
| --- | --- |
| `checkpoint/1. RSS 수집` | RSS 수집 코드, 실제 RSS 원본·JSON·CSV |
| `checkpoint/2. 관심 뉴스와 화면` | 1단계 + 키워드 선별·HTML 생성 |
| `checkpoint/3. AI 뉴스 브리핑` | 2단계 + OpenAI 브리핑·재사용·실패 안내 |

각 폴더에는 2026-10-26에 실제 수집한 보도자료가 있습니다. 최신 목록에 관심 뉴스가 없을 수도 있으며 0건도 정상입니다. 미리 제공된 AI 요약은 없습니다.

## 실행

사용할 단계 폴더를 Antigravity에서 열고 터미널을 실행합니다. Python 3.12 이상을 사용합니다. 수집·화면 단계는 표준 라이브러리만 사용하고, AI 단계는 최상위 설치 목록의 openai 패키지를 사용합니다.

```powershell
python collect_news.py
```

2단계부터는 이어서 실행하고 `news_dashboard.html`을 더블클릭합니다.

```powershell
python make_news_dashboard.py
```

3단계에서는 `.env.example`을 `.env`로 복사해 `openai_api_key`, `openai_model`을 설정하고 실행합니다. 모델명은 강사가 안내한 값을 사용합니다.

```powershell
python make_news_briefing.py
```

수집 → 선별·화면 → 브리핑 순서입니다. 화면의 키워드 변경은 화면 내 필터이며 파일과 AI 요약을 갱신하지 않습니다. 같은 조건을 저장 파일에도 반영하려면 다음처럼 실행합니다.

```powershell
python make_news_dashboard.py --keywords "난방,히트펌프"
python make_news_briefing.py
```

## 연결 없이 확인하기

저장된 실제 자료를 사용하며 새 RSS나 AI API를 호출하지 않습니다.

```powershell
python collect_news.py --offline
python make_news_dashboard.py
python make_news_briefing.py --no-ai
```

화면 생성은 2단계부터, 브리핑 생성은 3단계에서 사용합니다. 키가 없거나 API가 실패해도 뉴스 목록은 표시됩니다. `--no-ai`는 브리핑 생성을 건너뛰었다고 표시합니다.

## 파일 구성

- `collect_news.py`: 수집과 중복 제거
- `news_common.py`: 해당 단계의 공통 처리
- `data/news_rss.xml`: 실제 RSS 원문
- `data/news.json`, `data/news.csv`: 뉴스 목록. CSV는 엑셀용 UTF-8 BOM 사용
- `make_news_dashboard.py`, `dashboard_template.html`: 선별과 HTML 생성
- `data/interest_news.json`: 관심 키워드와 선별 뉴스
- `make_news_briefing.py`: OpenAI 브리핑과 HTML 반영
- `data/news_briefing.json`: 현재 브리핑 또는 생성 상태
- `data/briefing_cache.json`: 실제 AI 생성 성공 시에만 만들어지는 재사용 자료

RSS는 최근 일부 글의 제목·설명만 제공합니다. 요약은 기사 본문 전체를 읽은 결과가 아니므로 원문과 대조합니다.
