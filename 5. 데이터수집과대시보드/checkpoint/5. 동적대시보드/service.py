"""Persistent daily snapshots. External collection runs only on a cache miss."""
import csv
import json
import math
import os
import shutil
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout
from settings import default_seed

HERE = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
PRODUCTS = {'B027': '보통휘발유', 'B034': '고급휘발유', 'D047': '자동차용경유',
            'C004': '실내등유', 'K015': '자동차용부탄'}
BRANDS = {'SKE': 'SK에너지', 'GSC': 'GS칼텍스', 'HDO': 'HD현대오일뱅크',
          'SOL': 'S-OIL', 'RTO': '알뜰주유소', 'RTE': '자영알뜰',
          'RTX': '알뜰(ex)', 'NHO': 'NH-OIL', 'SKG': 'SK가스', 'E1G': 'E1', 'ETC': '자가상표'}


def now():
    return datetime.now(KST)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def build_snapshot(folder, as_of):
    manifest = read_json(folder / 'manifest.json')
    if manifest.get('status') != 'complete' or manifest.get('as_of') != as_of.isoformat():
        raise ValueError('Incomplete or mismatched collection')
    entries = manifest.get('files', [])
    if entries and all(e['path'].endswith('.csv') for e in entries):
        paths = [folder / e['path'] for e in entries]
    else:  # Existing converted CSV data has an older JSON manifest.
        paths = sorted((folder / 'csv').rglob('*.csv'))
    records, seen, coverage = [], set(), {}
    for path in paths:
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Invalid source path')
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if 'DATE' not in row:
                    continue
                day = datetime.strptime(row['DATE'], '%Y%m%d').date()
                age = (as_of - day).days
                if not 1 <= age <= 14:
                    raise ValueError('Unexpected source date')
                kind = 'region' if 'AREA_CD' in row else 'brand' if 'POLL_DIV_CD' in row else 'national'
                category_code = row.get('AREA_CD', row.get('POLL_DIV_CD', 'national'))
                identity = (kind, category_code, row['PRODCD'], day)
                if identity in seen:
                    raise ValueError('Duplicate observation')
                seen.add(identity)
                price = float(row['PRICE'])
                if not math.isfinite(price):
                    raise ValueError('Invalid price')
                coverage.setdefault((kind, category_code), set()).add(day)
                records.append({'kind': kind, 'period': 'recent' if age <= 7 else 'previous',
                                'date': day.isoformat(), 'product': PRODUCTS.get(row['PRODCD'], row['PRODCD']),
                                'code': row['PRODCD'], 'category_code': category_code, 'price': price,
                                'category': row['AREA_NM'] if kind == 'region' else
                                BRANDS.get(category_code, category_code) if kind == 'brand' else '전국'})
    expected = {as_of - timedelta(days=i) for i in range(1, 15)}
    if {k[0] for k in coverage} != {'national', 'brand', 'region'}:
        raise ValueError('Missing dataset')
    if any(days != expected for days in coverage.values()):
        raise ValueError('Incomplete date coverage')
    # Verify that every region in the lookup has price data, including legacy CSVs.
    area_codes = set()
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                if 'DATE' not in row and 'AREA_CD' in row:
                    area_codes.add(row['AREA_CD'])
    if not area_codes or area_codes != {k[1] for k in coverage if k[0] == 'region'}:
        raise ValueError('Missing region dataset')
    periods = {name: {'start': (as_of - timedelta(days=end + 6)).isoformat(),
                      'end': (as_of - timedelta(days=end)).isoformat()}
               for name, end in [('recent', 1), ('previous', 8)]}
    return {'version': 1, 'as_of': as_of.isoformat(), 'collected_at': manifest['collected_at'],
            'periods': periods, 'records': records, 'warnings': manifest.get('warnings', [])}


class DashboardService:
    def __init__(self, storage=None, seed=None, collector=None, clock=now, retry_seconds=1800):
        self.storage = Path(storage or os.environ.get('DASHBOARD_STORAGE', HERE / 'storage')).resolve()
        self.seed = Path(seed) if seed is not None else default_seed()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.retry_seconds = retry_seconds
        self.collector = collector or self.collect
        self.guard = threading.Lock()
        self.running = False
        self.worker = None

    @staticmethod
    def collect(as_of, output):
        from collector import collect
        collect(as_of, output)

    def latest(self, today):
        for path in sorted((self.storage / 'snapshots').glob('*.json'), reverse=True):
            if path.stem > today.isoformat():
                continue
            try:
                payload = read_json(path)
                if payload['version'] == 1 and payload['as_of'] == path.stem and payload['records']:
                    # Enrich older snapshots from the original CSV for Excel code columns.
                    if any('category_code' not in r for r in payload['records']) and (self.seed / path.stem).is_dir():
                        try:
                            payload = build_snapshot(self.seed / path.stem, date.fromisoformat(path.stem))
                            write_json(path, payload)
                        except (ValueError, KeyError, OSError):
                            pass
                    return payload
            except (ValueError, KeyError, OSError, TypeError):
                continue
        return None

    def seed_latest(self, today):
        # Only import validated saved observations; never call an external API here.
        current = self.latest(today)
        for folder in sorted(self.seed.glob('????-??-??'), reverse=True):
            if folder.name > today.isoformat() or (current and folder.name <= current['as_of']):
                continue
            try:
                payload = build_snapshot(folder, date.fromisoformat(folder.name))
                write_json(self.storage / 'snapshots' / (folder.name + '.json'), payload)
                return payload
            except (ValueError, KeyError, OSError, TypeError):
                continue
        return current

    def state(self):
        try:
            return read_json(self.storage / 'refresh.json')
        except (ValueError, OSError):
            return {}

    def response(self):
        today = self.clock().date()
        with self.guard:
            payload = self.seed_latest(today)
            fresh = payload is not None and payload['as_of'] == today.isoformat()
            state = self.state()
            retry_at = state.get('retry_at')
            allowed = not retry_at or self.clock() >= datetime.fromisoformat(retry_at)
            if not fresh and not self.running and allowed:
                self.running = True
                self.worker = threading.Thread(target=self.refresh, args=(today,), daemon=True)
                self.worker.start()
            refreshing = self.running
        return {'data': payload, 'meta': {'today': today.isoformat(), 'stale': not fresh,
                'refreshing': refreshing, 'retry_at': None if fresh else retry_at,
                'error': None if fresh else state.get('error')}}

    def refresh(self, today):
        staging = None
        try:
            # Cross-process lock also protects daily collection when workers overlap.
            with FileLock(self.storage / 'refresh.lock', timeout=0):
                existing = self.latest(today)
                state = self.state()
                if existing and existing['as_of'] == today.isoformat():
                    return
                if state.get('retry_at') and self.clock() < datetime.fromisoformat(state['retry_at']):
                    return
                try:
                    staging = self.storage / 'raw' / (today.isoformat() + '-' + uuid4().hex)
                    self.collector(today, staging)
                    payload = build_snapshot(staging, today)
                    write_json(self.storage / 'snapshots' / (today.isoformat() + '.json'), payload)
                    write_json(self.storage / 'refresh.json', {})
                except Exception:
                    # Save retry state before releasing the cross-process lock.
                    # Never expose upstream URLs, credentials or exception text.
                    write_json(self.storage / 'refresh.json', {
                        'error': '최신 자료를 가져오지 못했습니다. 저장된 자료를 유지하며 잠시 후 다시 시도합니다.',
                        'retry_at': (self.clock() + timedelta(seconds=self.retry_seconds)).isoformat()})
        except Timeout:
            pass  # Another process owns collection. Its completed snapshot is shared.
        finally:
            try:
                if staging and staging.exists():
                    shutil.rmtree(staging)
            finally:
                with self.guard:
                    self.running = False
