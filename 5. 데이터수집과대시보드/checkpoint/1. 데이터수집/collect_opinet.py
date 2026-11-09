"""Save each Opinet API response as a CSV for two seven-day periods (no aggregation)."""

import argparse
import csv
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))


def load_key():
    values = {}
    project_root = ROOT.parent.parent if ROOT.parent.name == 'checkpoint' else ROOT.parent
    for path in dict.fromkeys([project_root / '.env', ROOT / '.env']):
        if path.is_file():
            for line in path.read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    name, value = line.split('=', 1)
                    values[name.strip().lower()] = value.strip().strip(chr(34)).strip(chr(39))
    key = os.environ.get('OPINET_API_KEY') or values.get('opinet_api_key')
    if not key:
        raise RuntimeError('Set opinet_api_key in .env or OPINET_API_KEY in the environment.')
    return key


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def save_csv(path, rows):
    """Keep original columns and values; use a BOM for Korean text in Excel."""
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat,
                        default=datetime.now(KST).date(), help='Reference day in Korea, YYYY-MM-DD')
    args = parser.parse_args()
    key = load_key()
    output = ROOT / 'data' / 'opinet' / args.as_of.isoformat()
    manifest = {'as_of': args.as_of.isoformat(),
                'collected_at': datetime.now(KST).isoformat(),
                'status': 'collecting', 'request_count': 0, 'files': [], 'warnings': []}

    def fetch(endpoint, filename, params=None, expected_dates=None):
        params = params or {}
        manifest['request_count'] += 1
        save_json(output / 'manifest.json', manifest)
        url = 'https://www.opinet.co.kr/api/' + endpoint + '?' + urlencode(
            {'code': key, 'out': 'json', **params})
        try:
            with urlopen(url, timeout=30) as response:
                payload = json.loads(response.read().decode('utf-8-sig'))
        except Exception as exc:
            # Exception messages can contain the request URL and API key.
            raise RuntimeError(f'{endpoint}: request failed ({type(exc).__name__})') from None
        rows = payload.get('RESULT', {}).get('OIL')
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f'{endpoint}: no data returned; stopping collection.')
        if key in json.dumps(payload, ensure_ascii=False):
            raise RuntimeError(f'{endpoint}: response unexpectedly contains the API key.')
        if expected_dates is not None:
            actual = {str(row.get('DATE')) for row in rows}
            if actual != expected_dates:
                raise RuntimeError(f'{endpoint}: unexpected date coverage: {sorted(actual)}')
            groups = {}
            for row in rows:
                group = (row.get('PRODCD'), row.get('POLL_DIV_CD'), row.get('AREA_CD'))
                group_dates = groups.setdefault(group, set())
                if row['DATE'] in group_dates:
                    raise RuntimeError(f'{endpoint}: duplicate daily record in {group}')
                group_dates.add(row['DATE'])
            for group, group_dates in groups.items():
                if group_dates != expected_dates:
                    manifest['warnings'].append({'file': filename, 'group': group,
                                                 'missing_dates': sorted(expected_dates - group_dates)})
        save_csv(output / filename, rows)
        manifest['files'].append({'path': filename, 'endpoint': endpoint,
                                  'parameters': params, 'row_count': len(rows)})
        save_json(output / 'manifest.json', manifest)
        print(f'{filename}: {len(rows)} records', flush=True)
        return rows

    try:
        areas = fetch('areaCode.do', 'area_codes.csv')
        codes = [str(row['AREA_CD']) for row in areas]
        if len(set(codes)) != len(codes) or any(len(code) != 2 or not code.isdigit() for code in codes):
            raise RuntimeError('Invalid province code list.')
        for period, days_back in [('recent', 1), ('previous', 8)]:
            end = args.as_of - timedelta(days=days_back)
            start = end - timedelta(days=6)
            dates = {(start + timedelta(days=n)).strftime('%Y%m%d') for n in range(7)}
            params = {'date': end.strftime('%Y%m%d')}
            manifest[period] = {'start': start.isoformat(), 'end': end.isoformat()}
            fetch('dateAvgRecentPrice.do', f'{period}/national.csv', params, dates)
            fetch('datePollAvgRecentPrice.do', f'{period}/brands.csv', params, dates)
            for code in codes:
                fetch('dateAreaAvgRecentPrice.do', f'{period}/areas/{code}.csv',
                      {**params, 'area': code}, dates)
        manifest['status'] = 'complete'
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['error'] = str(exc).replace(key, '[REDACTED]')
        print(manifest['error'], flush=True)
    finally:
        save_json(output / 'manifest.json', manifest)
    if manifest['status'] != 'complete':
        raise SystemExit(1)
    print(f"Saved {len(manifest['files'])} data files; {len(manifest['warnings'])} coverage warnings.")


if __name__ == '__main__':
    main()
