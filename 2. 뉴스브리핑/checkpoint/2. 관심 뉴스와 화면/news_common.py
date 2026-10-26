import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import csv
import io
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

TEMPLATE = (Path(__file__).resolve().parent / 'dashboard_template.html').read_text(encoding='utf-8-sig')

ROOT = Path(__file__).resolve().parent

KST = timezone(timedelta(hours=9))

RSS_URL = 'https://www.mcee.go.kr/home/web/board/rss.do?menuId=10598&boardMasterId=939'

DEFAULT_KEYWORDS = ['보일러', '난방', '히트펌프', '냉매', '에너지 효율']

def now():
    return datetime.now(KST).isoformat(timespec='seconds')

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def atomic_write(path, content):
    """한 파일을 모두 쓴 다음 교체해 중간에 잘린 파일을 남기지 않습니다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix='.writing-')
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode('utf-8'))
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2))

def digest(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

def plain(value):
    parser = PlainText()
    parser.feed(value)
    return re.sub(r'\s+', ' ', unescape(' '.join(parser.parts))).strip()

def normalize_date(raw):
    if not raw:
        return ''
    # RSS 원문의 KST는 Python의 날짜 해석기가 모르는 경우가 있습니다.
    try:
        value = parsedate_to_datetime(re.sub(r'\bKST\b', '+0900', raw))
        if value.tzinfo is None:
            return raw
        return value.astimezone(KST).isoformat(timespec='seconds')
    except (ValueError, TypeError, OverflowError):
        return raw

def parse_rss(body, source_url=RSS_URL):
    root = ET.fromstring(body)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise ValueError('응답이 RSS 2.0 문서가 아닙니다.')
    items, seen = [], set()
    for node in channel.findall('item'):
        title = plain(node.findtext('title', ''))
        url = urljoin(source_url, node.findtext('link', '').strip())
        url = re.sub(r';jsessionid=[^?/#]+', '', url, flags=re.IGNORECASE)
        parts = urlsplit(url)
        if not title or not node.findtext('link') or parts.scheme not in ('https', 'http') or not parts.netloc:
            raise ValueError('제목 또는 정상적인 원문 링크가 없는 항목이 있습니다.')
        if url in seen:
            continue
        seen.add(url)
        raw = node.findtext('pubDate', '').strip()
        items.append({'id': digest(url)[:16], 'title': title, 'url': url,
                      'published_at': normalize_date(raw), 'published_raw': raw,
                      'description': plain(node.findtext('description', ''))})
    # 기존 자료를 빈 응답으로 지우지 않습니다.
    if not items:
        raise ValueError('RSS에 게시물이 없습니다. 이전 자료를 유지합니다.')
    return {'source_name': '기후에너지환경부 보도자료', 'source_url': source_url,
            'collected_at': now(), 'items': items}

def excel_safe(value):
    # 외부 텍스트가 엑셀 수식으로 실행되지 않도록 CSV에서만 방어합니다.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value

def select_news(snapshot, keywords):
    items = []
    for item in snapshot['items']:
        text = (item['title'] + ' ' + item.get('description', '')).casefold()
        matches = [word for word in keywords if word.casefold() in text]
        if matches:
            items.append({**item, 'matched_keywords': matches})
    return {'collected_at': snapshot['collected_at'], 'source_url': snapshot['source_url'],
            'keywords': keywords, 'items': items}

def selection_id(selection):
    # 수집 시각만 바뀐 경우 기존 요약을 재사용합니다.
    return digest({'keywords': sorted(x.casefold() for x in selection['keywords']),
                   'items': [{k: x.get(k, '') for k in ('id', 'title', 'published_at', 'description', 'url')}
                             for x in selection['items']]})

def build(snapshot, keywords, briefing, output=None):
    selection = select_news(snapshot, keywords)
    payload = {**snapshot, 'keywords': keywords, 'selection_id': selection_id(selection), 'briefing': briefing}
    serialized = json.dumps(payload, ensure_ascii=False).replace('&', r'\u0026').replace('<', r'\u003c').replace('>', r'\u003e')
    output = output or ROOT / 'news_dashboard.html'
    atomic_write(output, TEMPLATE.replace('__NEWS_DATA__', serialized))
    return output
