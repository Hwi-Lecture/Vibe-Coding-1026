"""collector.js 와 같은 로직을 수행하는 파이썬 버전 (표준 라이브러리만 사용).

오피넷 유가 + 구글 뉴스 RSS를 수집하고, Gemini로 브리핑을 만들어
data/dashboard-data.js 로 저장한다.
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ENV_PATH = next((p for p in (ROOT / ".env", ROOT.parent / ".env") if p.exists()), None)

PRODUCTS = {
    "C004": "실내등유",
    "D047": "자동차경유",
    "B027": "보통휘발유",
    "B034": "고급휘발유",
    "K015": "자동차부탄",
}
KEYWORDS = ["보일러", "난방비", "등유", "가스요금", "에어컨"]
NEWS_PER_KEYWORD = 8
WINDOW_DAYS = 7
GEMINI_MODEL = "gemini-flash-latest"  # 모델이 종료돼도 깨지지 않도록 "최신 flash" 별칭 사용
USER_AGENT = "Mozilla/5.0 (collector.py)"


def read_env(file):
    env = {}
    if not file:
        return env
    for line in Path(file).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            value = m.group(2).strip()
            value = re.sub(r"^[\"']|[\"']$", "", value).strip()
            env[m.group(1).lower()] = value
    return env


def read_json(file, fallback):
    try:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def ymd(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def iso_z(dt):
    """JS의 toISOString() 형식 (예: 2026-10-15T13:30:35.442Z)"""
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def kst_date(dt):
    return (dt.astimezone(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


def decode(s):
    s = re.sub(r"^<!\[CDATA\[|\]\]>$", "", s)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s.strip()


def tag(block, name):
    m = re.search(rf"<{name}[^>]*>([\s\S]*?)</{name}>", block)
    return decode(m.group(1)) if m else ""


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8")


def collect_prices(key):
    url = f"http://www.opinet.co.kr/api/avgRecentPrice.do?code={urllib.parse.quote(key, safe='')}&out=json"
    try:
        body = http(url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"오피넷 응답 오류: HTTP {e.code}")
    rows = json.loads(body)["RESULT"]["OIL"]
    history_file = DATA_DIR / "prices-history.json"
    history = read_json(history_file, {})
    for r in rows:
        if r["PRODCD"] not in PRODUCTS:
            continue
        history.setdefault(r["PRODCD"], {})[ymd(r["DATE"])] = r["PRICE"]
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def collect_news(keyword):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(keyword, safe='')}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        xml = http(url)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"뉴스 RSS 응답 오류({keyword}): HTTP {e.code}")
    items = []
    for block in xml.split("<item>")[1:]:
        source = tag(block, "source")
        title = tag(block, "title")
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)]
        items.append(
            {
                "title": title,
                "source": source,
                "url": tag(block, "link"),
                "publishedAt": iso_z(parsedate_to_datetime(tag(block, "pubDate"))),
            }
        )
    return items


def build_news(feeds, today):
    base = datetime.strptime(today, "%Y-%m-%d")
    days = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(WINDOW_DAYS - 1, -1, -1)]
    daily, items = {}, {}
    for k in KEYWORDS:
        dates = [kst_date(datetime.fromisoformat(n["publishedAt"].replace("Z", "+00:00"))) for n in feeds[k]]
        daily[k] = [dates.count(d) for d in days]
        items[k] = feeds[k][:NEWS_PER_KEYWORD]
    return {"keywords": KEYWORDS, "dates": days, "daily": daily, "items": items}


def build_prices(history):
    dates = sorted({d for h in history.values() for d in h})[-WINDOW_DAYS:]
    series = {code: [history.get(code, {}).get(d) for d in dates] for code in PRODUCTS}
    return {"products": PRODUCTS, "dates": dates, "series": series}


def make_briefing(key, prices, news):
    price_lines = []
    for code, name in PRODUCTS.items():
        s = prices["series"][code]
        price_lines.append(f"- {name}: 현재 {s[-1]}원/L, 7일 전 대비 {s[-1] - s[0]:.2f}원")
    news_lines = []
    for k in KEYWORDS:
        total = sum(news["daily"][k])
        titles = " / ".join(n["title"] for n in news["items"][k][:3])
        news_lines.append(f"- {k}: 7일간 기사 {total}건. 최신 헤드라인: {titles}")
    prompt = "\n".join(
        [
            "아래는 난방 에너지 가격과 관련 뉴스 집계입니다. 난방 연료를 쓰는 일반 가정 독자를 위해 오늘의 브리핑을 한국어로 3~4문장 써 주세요.",
            "규칙: 아래 데이터에 있는 사실만 쓰고, 가격 전망·투자 조언·과장 표현은 쓰지 않습니다. 마크다운 없이 줄글로만 씁니다.",
            "",
            f"기준일: {prices['dates'][-1]}",
            "[가격]",
            *price_lines,
            "[뉴스]",
            *news_lines,
        ]
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    try:
        res = http(url, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini 응답 오류: HTTP {e.code}")
    parts = (json.loads(res).get("candidates") or [{}])[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini가 빈 응답을 돌려줬습니다.")
    return {"text": text, "model": GEMINI_MODEL, "generatedAt": iso_z(datetime.now(timezone.utc))}


def main():
    env = read_env(ENV_PATH)
    key = env.get("opinet_api_key")
    if not key:
        raise RuntimeError(".env에서 opinet_api_key를 찾지 못했습니다.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    history = collect_prices(key)
    feeds = {k: collect_news(k) for k in KEYWORDS}

    now = datetime.now(timezone.utc)
    data = {
        "generatedAt": iso_z(now),
        "prices": build_prices(history),
        "news": build_news(feeds, kst_date(now)),
        "briefing": None,
    }
    if env.get("gemini_api_key"):
        try:
            data["briefing"] = make_briefing(env["gemini_api_key"], data["prices"], data["news"])
        except Exception as e:
            print(f"브리핑 생성 실패(가격·뉴스는 정상 저장): {e}", file=sys.stderr)
    else:
        print(".env에 gemini_api_key가 없어 브리핑을 건너뜁니다.", file=sys.stderr)

    out = "window.DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    (DATA_DIR / "dashboard-data.js").write_text(out, encoding="utf-8")
    print(f"저장 완료: 가격 {len(data['prices']['dates'])}일, 뉴스 키워드 {len(KEYWORDS)}개")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
