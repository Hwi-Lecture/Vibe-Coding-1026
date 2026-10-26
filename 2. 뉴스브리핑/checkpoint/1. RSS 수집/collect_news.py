"""Collect RSS to data/news_rss.xml, news.json and Excel-friendly news.csv."""
import argparse
import csv
import io
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from news_common import ROOT, RSS_URL, atomic_write, excel_safe, parse_rss, read_json, write_json


def collect(rss_file=None):
    if rss_file is not None:
        body = Path(rss_file).read_bytes()
    else:
        request = Request(RSS_URL, headers={'User-Agent': 'NewsBriefingTraining/1.0'})
        with urlopen(request, timeout=25) as response:
            body = response.read(5_000_001)
    if len(body) > 5_000_000:
        raise ValueError('RSS 응답이 허용 크기를 초과했습니다.')
    # Parse the entire response before replacing any previous valid files.
    snapshot = parse_rss(body)
    text = io.StringIO(newline='')
    fields = ['id', 'title', 'published_at', 'collected_at', 'url', 'description']
    writer = csv.DictWriter(text, fieldnames=fields)
    writer.writeheader()
    for item in snapshot['items']:
        row = {**item, 'collected_at': snapshot['collected_at']}
        writer.writerow({key: excel_safe(str(row[key])) for key in fields})
    atomic_write(ROOT / 'data' / 'news_rss.xml', body)
    atomic_write(ROOT / 'data' / 'news.csv', text.getvalue().encode('utf-8-sig'))
    write_json(ROOT / 'data' / 'news.json', snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='저장된 뉴스만 확인; 외부 연결 없음')
    parser.add_argument('--rss-file', type=Path, help='저장해 둔 실제 RSS 파일로 수집 결과 재현')
    args = parser.parse_args()
    try:
        snapshot = read_json(ROOT / 'data' / 'news.json') if args.offline else collect(args.rss_file)
        print(f"뉴스 {len(snapshot['items'])}건 / 수집 시각 {snapshot['collected_at']}")
        print(f"저장 위치: {ROOT / 'data'}")
        return 0
    except Exception as exc:
        print(f'수집 실패 ({type(exc).__name__}). 연결과 RSS 파일을 확인하세요. 이전 자료는 유지합니다.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
