"""Summarize selected news with OpenAI; preserve the news screen on failure."""
import argparse
import sys
from news_common import (ROOT, DEFAULT_KEYWORDS, build, generate, read_json,
                         select_news, selection_id, write_json)


def make_briefing(keywords=None, enabled=True):
    snapshot = read_json(ROOT / 'data' / 'news.json')
    interest_path = ROOT / 'data' / 'interest_news.json'
    if keywords is None:
        keywords = read_json(interest_path)['keywords'] if interest_path.exists() else DEFAULT_KEYWORDS
    selection = select_news(snapshot, keywords)
    write_json(interest_path, selection)
    cache_path = ROOT / 'data' / 'briefing_cache.json'
    state = {'briefing_cache': read_json(cache_path)} if cache_path.exists() else {}
    result = generate(selection, state, enabled=enabled)
    if result['status'] == 'success':
        write_json(cache_path, state['briefing_cache'])
    write_json(ROOT / 'data' / 'news_briefing.json', result)
    output = build(snapshot, keywords, result)
    return result, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--keywords', help='생략하면 저장된 관심 키워드 사용')
    parser.add_argument('--no-ai', action='store_true', help='API 호출 없이 목록·안내 화면만 생성')
    args = parser.parse_args()
    try:
        keywords = None if args.keywords is None else list(dict.fromkeys(x.strip() for x in args.keywords.split(',') if x.strip()))
        result, output = make_briefing(keywords, enabled=not args.no_ai)
        print(result['message'])
        print(f'완성 화면: {output}')
        return 1 if result['status'] == 'error' else 0
    except Exception as exc:
        print(f'브리핑 생성 실패 ({type(exc).__name__}). 수집 자료와 설정을 확인하세요.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
