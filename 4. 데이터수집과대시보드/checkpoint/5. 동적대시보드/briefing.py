"""Server-only OpenAI briefing with data-keyed cache and a keyless preview."""
import hashlib
import json
import math
import os
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from settings import env_values
from urllib.request import Request, urlopen

from filelock import FileLock, Timeout
from service import HERE, now, read_json, write_json

MODEL = 'gpt-6-luna'
PROMPT_VERSION = 1
INSTRUCTIONS = '''당신은 유가 대시보드의 한국어 브리핑 작성자입니다.
제공된 집계 수치만 사용하여 3~4문장, 450자 이내의 간결한 평문을 작성하세요.
최근 7일과 직전 7일은 달력상 이번 주/지난주와 다를 수 있으므로 실제 기간을 명시하세요.
전국 실내등유 평균과 증감, 휘발유·경유 변화, 난방비 상담 시 참고점을 요약하세요.
가격은 소수 둘째 자리로 표시하며 수치는 직접 재계산하지 마세요.
환율·국제유가 등 원인을 추측하거나 향후 가격·절감 효과를 예측하지 마세요.
실내등유 200L 가격 변화는 단순 예시이며 실제 구매·배달 가격과 다를 수 있습니다.
자료 부족인 유종은 비교하지 마세요. 마크다운, 인사말, 제목은 생략하세요.'''


def load_settings():
    values = env_values()
    key = os.environ.get('OPENAI_API_KEY') or values.get('openai_api_key', '')
    model = os.environ.get('OPENAI_MODEL') or values.get('openai_model') or MODEL
    return key, model


def summarize(snapshot):
    grouped = defaultdict(lambda: defaultdict(list))
    for row in snapshot['records']:
        if row['kind'] == 'national' and math.isfinite(row['price']) and row['price'] > 0:
            grouped[row['product']][row['period']].append(row)
    products = []
    for product, periods in sorted(grouped.items()):
        averages = {}
        for period in ['recent', 'previous']:
            rows = periods[period]
            averages[period] = sum(r['price'] for r in rows) / 7 if len(rows) == 7 and len({r['date'] for r in rows}) == 7 else None
        recent, previous = averages['recent'], averages['previous']
        valid = recent is not None and previous is not None
        products.append({'product': product, 'recent': round(recent, 2) if recent is not None else None,
                         'previous': round(previous, 2) if previous is not None else None,
                         'delta': round(recent - previous, 2) if valid else None,
                         'example_200L_delta': round((recent - previous) * 200) if valid else None})
    return {'as_of': snapshot['as_of'], 'periods': snapshot['periods'],
            'scope': '전국 평균 · 원/L', 'products': products}


def fingerprint(summary, model):
    raw = json.dumps({'summary': summary, 'model': model, 'prompt_version': PROMPT_VERSION},
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def generate(summary, key, model, instructions=INSTRUCTIONS, max_output_tokens=900):
    body = {'model': model, 'instructions': instructions,
            'input': json.dumps(summary, ensure_ascii=False),
            'reasoning': {'effort': 'none'}, 'max_output_tokens': max_output_tokens, 'store': False}
    request = Request('https://api.openai.com/v1/responses',
                      data=json.dumps(body).encode(),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                      method='POST')
    with urlopen(request, timeout=40) as response:
        payload = json.load(response)
    if payload.get('status') != 'completed':
        raise ValueError('Incomplete model response')
    text = '\n'.join(part['text'] for item in payload.get('output', []) if item.get('type') == 'message'
                     for part in item.get('content', []) if part.get('type') == 'output_text').strip()
    if not text or len(text) > 2000 or key in text:
        raise ValueError('Invalid model response')
    return text


def basic_summary(summary):
    parts = []
    for name in ['실내등유', '보통휘발유', '자동차용경유']:
        item = next((p for p in summary['products'] if p['product'] == name and p['delta'] is not None), None)
        if item:
            delta = item['delta']
            change = f"{abs(delta):.2f}원 {'상승' if delta > 0 else '하락'}" if delta else '변동 없음'
            parts.append(f"{name} 전국 평균은 {item['recent']:,.2f}원/L로 직전 7일 대비 {change}입니다.")
    return ' '.join(parts) or '비교에 필요한 전국 7일 관측 자료가 부족합니다.'


class BriefingService:
    def __init__(self, storage, settings=load_settings, generator=generate, clock=now):
        self.storage = Path(storage) / 'briefings'
        self.storage.mkdir(parents=True, exist_ok=True)
        self.settings, self.generator, self.clock = settings, generator, clock
        self.guard = threading.Lock()
        self.running = set()
        self.worker = None

    def response(self, snapshot):
        if snapshot is None:
            return {'text': '유가 자료를 불러온 뒤 브리핑을 표시합니다.', 'source': 'pending', 'refreshing': False}
        summary = summarize(snapshot)
        key, model = self.settings()
        identity = fingerprint(summary, model)
        path = self.storage / (identity + '.json')
        with self.guard:
            try:
                cached = read_json(path)
            except (ValueError, OSError):
                cached = {}
            if cached.get('source') == 'openai' and cached.get('text'):
                return {**cached, 'refreshing': False}
            retry_at = cached.get('retry_at')
            allowed = not retry_at or self.clock() >= datetime.fromisoformat(retry_at)
            if key and allowed and identity not in self.running:
                self.running.add(identity)
                self.worker = threading.Thread(target=self.refresh,
                    args=(path, identity, summary, key, model), daemon=True)
                self.worker.start()
            refreshing = identity in self.running
        text, source = basic_summary(summary), 'calculated'
        try:
            preview = read_json(HERE / 'briefing_preview.json')
            if preview['fingerprint'] == fingerprint(summary, MODEL):
                text, source = preview['text'], 'preview'
        except (ValueError, KeyError, OSError):
            pass
        return {'text': text, 'source': source, 'model': model, 'as_of': snapshot['as_of'],
                'periods': summary['periods'], 'refreshing': refreshing,
                'error': cached.get('error') if key else None, 'retry_at': retry_at if key else None}

    def refresh(self, path, identity, summary, key, model):
        try:
            with FileLock(str(path) + '.lock', timeout=0):
                try:
                    cached = read_json(path)
                except (ValueError, OSError):
                    cached = {}
                if cached.get('source') == 'openai':
                    return
                if cached.get('retry_at') and self.clock() < datetime.fromisoformat(cached['retry_at']):
                    return
                try:
                    text = self.generator(summary, key, model)
                    write_json(path, {'text': text, 'source': 'openai', 'model': model,
                                     'as_of': summary['as_of'], 'periods': summary['periods'],
                                     'generated_at': self.clock().isoformat()})
                except Exception:
                    write_json(path, {'error': 'AI 브리핑 생성에 실패해 준비된 요약을 표시합니다.',
                                     'retry_at': (self.clock() + timedelta(minutes=30)).isoformat()})
        except Timeout:
            pass
        finally:
            with self.guard:
                self.running.discard(identity)
