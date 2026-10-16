const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const DATA_DIR = path.join(ROOT, 'data');
const ENV_PATH = [path.join(ROOT, '.env'), path.join(ROOT, '..', '.env')].find((p) => fs.existsSync(p));

const PRODUCTS = {
  C004: '실내등유',
  D047: '자동차경유',
  B027: '보통휘발유',
  B034: '고급휘발유',
  K015: '자동차부탄',
};
const KEYWORDS = ['보일러', '난방비', '등유', '가스요금', '에어컨'];
const NEWS_PER_KEYWORD = 8;
const WINDOW_DAYS = 7;
const GEMINI_MODEL = 'gemini-flash-latest'; // 모델이 종료돼도 깨지지 않도록 "최신 flash" 별칭 사용

function readEnv(file) {
  const env = {};
  if (!file) return env;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$/);
    if (m) env[m[1].toLowerCase()] = m[2].trim().replace(/^["']|["']$/g, '').trim();
  }
  return env;
}

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function ymd(d) {
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
}

function kstDate(iso) {
  return new Date(new Date(iso).getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

function decode(s) {
  return s
    .replace(/^<!\[CDATA\[|\]\]>$/g, '')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .trim();
}

function tag(block, name) {
  const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : '';
}

async function collectPrices(key) {
  const url = `http://www.opinet.co.kr/api/avgRecentPrice.do?code=${encodeURIComponent(key)}&out=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`오피넷 응답 오류: HTTP ${res.status}`);
  const json = await res.json();
  const rows = json.RESULT.OIL;
  const historyFile = path.join(DATA_DIR, 'prices-history.json');
  const history = readJson(historyFile, {});
  for (const r of rows) {
    if (!PRODUCTS[r.PRODCD]) continue;
    history[r.PRODCD] = history[r.PRODCD] || {};
    history[r.PRODCD][ymd(r.DATE)] = r.PRICE;
  }
  fs.writeFileSync(historyFile, JSON.stringify(history, null, 2));
  return history;
}

async function collectNews(keyword) {
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(keyword)}&hl=ko&gl=KR&ceid=KR:ko`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`뉴스 RSS 응답 오류(${keyword}): HTTP ${res.status}`);
  const xml = await res.text();
  return xml
    .split('<item>')
    .slice(1)
    .map((block) => {
      const source = tag(block, 'source');
      let title = tag(block, 'title');
      if (source && title.endsWith(` - ${source}`)) title = title.slice(0, -(source.length + 3));
      return {
        title,
        source,
        url: tag(block, 'link'),
        publishedAt: new Date(tag(block, 'pubDate')).toISOString(),
      };
    });
}

function buildNews(feeds, today) {
  const days = [];
  for (let i = WINDOW_DAYS - 1; i >= 0; i--) {
    days.push(new Date(new Date(`${today}T00:00:00Z`).getTime() - i * 86400000).toISOString().slice(0, 10));
  }
  const daily = {};
  const items = {};
  for (const k of KEYWORDS) {
    daily[k] = days.map((d) => feeds[k].filter((n) => kstDate(n.publishedAt) === d).length);
    items[k] = feeds[k].slice(0, NEWS_PER_KEYWORD);
  }
  return { keywords: KEYWORDS, dates: days, daily, items };
}

function buildPrices(history) {
  const dates = [...new Set(Object.values(history).flatMap((h) => Object.keys(h)))].sort().slice(-WINDOW_DAYS);
  const series = {};
  for (const code of Object.keys(PRODUCTS)) {
    series[code] = dates.map((d) => history[code]?.[d] ?? null);
  }
  return { products: PRODUCTS, dates, series };
}

async function makeBriefing(key, prices, news) {
  const last = (a) => a[a.length - 1];
  const priceLines = Object.entries(PRODUCTS).map(([code, name]) => {
    const s = prices.series[code];
    return `- ${name}: 현재 ${last(s)}원/L, 7일 전 대비 ${(last(s) - s[0]).toFixed(2)}원`;
  });
  const newsLines = KEYWORDS.map((k) => {
    const total = news.daily[k].reduce((a, b) => a + b, 0);
    const titles = news.items[k].slice(0, 3).map((n) => n.title).join(' / ');
    return `- ${k}: 7일간 기사 ${total}건. 최신 헤드라인: ${titles}`;
  });
  const prompt = [
    '아래는 난방 에너지 가격과 관련 뉴스 집계입니다. 난방 연료를 쓰는 일반 가정 독자를 위해 오늘의 브리핑을 한국어로 3~4문장 써 주세요.',
    '규칙: 아래 데이터에 있는 사실만 쓰고, 가격 전망·투자 조언·과장 표현은 쓰지 않습니다. 마크다운 없이 줄글로만 씁니다.',
    '',
    `기준일: ${last(prices.dates)}`,
    '[가격]',
    ...priceLines,
    '[뉴스]',
    ...newsLines,
  ].join('\n');

  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
    body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
  });
  if (!res.ok) throw new Error(`Gemini 응답 오류: HTTP ${res.status}`);
  const json = await res.json();
  const text = json.candidates?.[0]?.content?.parts?.map((p) => p.text).join('').trim();
  if (!text) throw new Error('Gemini가 빈 응답을 돌려줬습니다.');
  return { text, model: GEMINI_MODEL, generatedAt: new Date().toISOString() };
}

async function main() {
  const env = readEnv(ENV_PATH);
  const key = env.opinet_api_key;
  if (!key) throw new Error('.env에서 opinet_api_key를 찾지 못했습니다.');
  fs.mkdirSync(DATA_DIR, { recursive: true });

  const history = await collectPrices(key);
  const feeds = {};
  for (const k of KEYWORDS) feeds[k] = await collectNews(k);

  const today = kstDate(new Date().toISOString());
  const data = {
    generatedAt: new Date().toISOString(),
    prices: buildPrices(history),
    news: buildNews(feeds, today),
    briefing: null,
  };
  if (env.gemini_api_key) {
    try {
      data.briefing = await makeBriefing(env.gemini_api_key, data.prices, data.news);
    } catch (e) {
      console.warn(`브리핑 생성 실패(가격·뉴스는 정상 저장): ${e.message}`);
    }
  } else {
    console.warn('.env에 gemini_api_key가 없어 브리핑을 건너뜁니다.');
  }
  fs.writeFileSync(path.join(DATA_DIR, 'dashboard-data.js'), `window.DASHBOARD_DATA = ${JSON.stringify(data, null, 2)};\n`);
  console.log(`저장 완료: 가격 ${data.prices.dates.length}일, 뉴스 키워드 ${KEYWORDS.length}개`);
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
