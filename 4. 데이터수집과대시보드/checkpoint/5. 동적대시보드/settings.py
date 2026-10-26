"""Find project settings and saved data before and after copying a checkpoint."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent if HERE.parent.name == 'checkpoint' else HERE.parent


def env_values():
    values = {}
    for path in dict.fromkeys([PROJECT_ROOT / '.env', HERE / '.env']):
        if path.is_file():
            for raw in path.read_text(encoding='utf-8-sig').splitlines():
                line = raw.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    values[key.strip().lower()] = value.strip().strip(chr(34)).strip(chr(39))
    return values


def default_seed():
    candidates = [PROJECT_ROOT / 'data' / 'opinet', HERE / 'data' / 'opinet']
    if HERE.parent.name == 'checkpoint':
        candidates += [HERE.parent / name / 'data' / 'opinet' for name in [
            '4. 정적대시보드', '3. 메일전송기능추가', '2. 수집결과정리', '1. 데이터수집']]
    return next((path for path in candidates if path.is_dir()), candidates[0])
