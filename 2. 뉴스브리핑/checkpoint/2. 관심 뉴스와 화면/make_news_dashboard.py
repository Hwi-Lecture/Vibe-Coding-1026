"""Filter saved news and create a standalone HTML page; no network calls."""
import argparse
import sys
from news_common import ROOT, DEFAULT_KEYWORDS, build, read_json, select_news, selection_id, write_json


def make_dashboard(keywords=None):
    snapshot = read_json(ROOT / 'data' / 'news.json')
    keywords = DEFAULT_KEYWORDS if keywords is None else keywords
    selection = select_news(snapshot, keywords)
    write_json(ROOT / 'data' / 'interest_news.json', selection)
    path = ROOT / 'data' / 'news_briefing.json'
    briefing = read_json(path) if path.exists() else {
        'status': 'disabled', 'items': [], 'keywords': keywords, 'selection_id': selection_id(selection),
        'message': '이 단계에서는 뉴스 목록과 관심 키워드를 확인합니다. AI 브리핑은 다음 단계에서 추가합니다.'}
    return build(snapshot, keywords, briefing), selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keywords', help='쉼표로 구분한 관심 키워드; 빈 문자열이면 전체 소식만 표시')
    args = parser.parse_args()
    try:
        keywords = None if args.keywords is None else list(dict.fromkeys(x.strip() for x in args.keywords.split(',') if x.strip()))
        output, selection = make_dashboard(keywords)
        print(f"관심 뉴스 {len(selection['items'])}건 / 완성 화면: {output}")
        return 0
    except Exception as exc:
        print(f'화면 생성 실패 ({type(exc).__name__}). 먼저 collect_news.py를 실행하세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
