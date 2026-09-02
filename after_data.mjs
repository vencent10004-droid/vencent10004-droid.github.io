// 코스피 상위 400 + 코스닥 상위 200 종목의 정규장/애프터마켓 시세를 네이버에서 받아 JSON으로 저장.
// 사용법: node after_data.mjs [출력경로=after_data.json]
// 종목 유니버스는 .universe_cache.json 에 6시간 캐시된다 (시세는 매 실행마다 갱신).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outPath = process.argv[2] || path.join(here, 'after_data.json');
const cachePath = path.join(here, '.universe_cache.json');
const KOSPI_TOP = 400;
const KOSDAQ_TOP = 200;
const UNIVERSE_TTL_MS = 6 * 3600 * 1000;
const HEADERS = {
  'user-agent': 'Mozilla/5.0',
  referer: 'https://m.stock.naver.com/',
  accept: 'application/json,text/plain,*/*',
};
const FUND_PREFIXES = ['KODEX', 'TIGER', 'ACE', 'SOL', 'RISE', 'PLUS', 'HANARO', 'KOSEF', 'ARIRANG', 'TIMEFOLIO', 'KBSTAR'];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const isFund = name => FUND_PREFIXES.some(p => name.startsWith(p)) || name.includes('ETN');

function num(v) {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const n = Number(String(v).replace(/,/g, '').replace(/%/g, '').trim());
  return Number.isFinite(n) ? n : null;
}

function koreanMoney(v) {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return v;
  const text = String(v).replace(/,/g, '').replace(/\s/g, '');
  const units = { '조': 1e12, '억': 1e8, '만': 1e4 };
  let total = 0, current = '';
  for (const ch of text) {
    if (/[\d.]/.test(ch)) current += ch;
    else if (units[ch]) { if (current) { total += Number(current) * units[ch]; current = ''; } }
  }
  if (current) total += Number(current);
  return total || num(text);
}

async function fetchJson(url) {
  const r = await fetch(url, { headers: HEADERS });
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
  return r.json();
}

async function fetchTopStocks(market, topN) {
  const out = [];
  for (let page = 1; out.length < topN && page <= 30; page++) {
    const j = await fetchJson(`https://m.stock.naver.com/api/stocks/marketValue/${market}?page=${page}&pageSize=100`);
    const stocks = j.stocks || [];
    if (!stocks.length) break;
    for (const s of stocks) {
      if (s.stockEndType !== 'stock') continue;
      if (isFund(s.stockName)) continue;
      out.push({ ticker: String(s.itemCode).padStart(6, '0'), name: s.stockName, market });
      if (out.length >= topN) break;
    }
    await sleep(120);
  }
  if (out.length < topN) console.warn(`[WARN] ${market}: requested ${topN}, got ${out.length}`);
  out.forEach((s, i) => (s.market_rank = i + 1));
  return out;
}

async function getUniverse() {
  try {
    const cached = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
    if (Date.now() - cached.ts < UNIVERSE_TTL_MS && cached.stocks?.length) {
      console.log(`Universe cache hit: ${cached.stocks.length} stocks`);
      return cached.stocks;
    }
  } catch {}
  const [kospi, kosdaq] = [await fetchTopStocks('KOSPI', KOSPI_TOP), await fetchTopStocks('KOSDAQ', KOSDAQ_TOP)];
  const stocks = [...kospi, ...kosdaq];
  fs.writeFileSync(cachePath, JSON.stringify({ ts: Date.now(), stocks }), 'utf8');
  return stocks;
}

async function fetchQuotes(tickers) {
  const map = new Map();
  for (let i = 0; i < tickers.length; i += 50) {
    const chunk = tickers.slice(i, i + 50);
    try {
      const j = await fetchJson(`https://polling.finance.naver.com/api/realtime/domestic/stock/${chunk.join(',')}`);
      for (const it of j.datas || []) {
        const over = it.overMarketPriceInfo || {};
        // 애프터장 체결이 실제로 있는 종목만 인정 (체결 없는 종목은 overPrice에 잔존값이 내려와 가짜 격차가 생김)
        const vol = num(over.accumulatedTradingVolumeRaw ?? over.accumulatedTradingVolume ?? over.tradeVolume);
        const traded = vol != null && vol > 0;
        map.set(String(it.itemCode).padStart(6, '0'), {
          regular_close: num(it.closePrice),
          regular_return: num(it.fluctuationsRatio),
          after_price: traded ? num(over.overPrice) : null,
          after_return: traded ? num(over.fluctuationsRatio) : null,
          after_volume: traded ? vol : null,
          after_value: traded ? koreanMoney(over.accumulatedTradingValueRaw ?? over.accumulatedTradingValue ?? over.tradePrice) : null,
          market_status: it.marketStatus || '',
          after_status: over.overMarketStatus || '',
        });
      }
    } catch (e) {
      console.warn(`[WARN] quote chunk ${Math.floor(i / 50) + 1} failed: ${e.message}`);
    }
    await sleep(150);
  }
  return map;
}

// 정규장 중에는 애프터 시세가 실시간가와 같아 격차가 0이므로 수집하지 않는다.
// (직전 거래일 저녁에 수집한 스냅샷을 다음 장 마감까지 유지 → 당일 종가 vs 당일 애프터 비교 보존)
{
  const kst = new Date(Date.now() + 9 * 3600 * 1000);
  const hhmm = kst.getUTCHours() * 100 + kst.getUTCMinutes();
  if (hhmm >= 840 && hhmm < 1532) {
    console.log(`Regular session (KST ${hhmm}) — skip, keeping last after-market snapshot.`);
    process.exit(0);
  }
}

const universe = await getUniverse();
const quotes = await fetchQuotes(universe.map(s => s.ticker));
console.log(`Quotes fetched: ${quotes.size}/${universe.length}`);

const rows = [];
for (const s of universe) {
  const q = quotes.get(s.ticker);
  if (!q || q.regular_close == null) continue;
  const gap = q.regular_return != null && q.after_return != null ? q.after_return - q.regular_return : null;
  const vs = q.after_price != null && q.regular_close ? (q.after_price / q.regular_close - 1) * 100 : null;
  rows.push({
    market_rank: s.market_rank,
    ticker: s.ticker,
    market: s.market,
    name: s.name,
    regular_close: q.regular_close,
    after_price: q.after_price,
    regular_return: q.regular_return,
    after_return: q.after_return,
    return_gap: gap == null ? null : Math.round(gap * 100) / 100,
    after_vs_regular: vs == null ? null : Math.round(vs * 10000) / 10000,
    after_volume: q.after_volume,
    after_value: q.after_value,
  });
}
rows.sort((a, b) => (b.return_gap ?? -1e9) - (a.return_gap ?? -1e9));
rows.forEach((r, i) => (r.rank = i + 1));

const kstNow = new Date(Date.now() + 9 * 3600 * 1000);
const pad = n => String(n).padStart(2, '0');
const meta = {
  generated: `${kstNow.getUTCFullYear()}-${pad(kstNow.getUTCMonth() + 1)}-${pad(kstNow.getUTCDate())} ${pad(kstNow.getUTCHours())}:${pad(kstNow.getUTCMinutes())}`,
  kospi_top: KOSPI_TOP,
  kosdaq_top: KOSDAQ_TOP,
  kospi_count: rows.filter(r => r.market === 'KOSPI').length,
  kosdaq_count: rows.filter(r => r.market === 'KOSDAQ').length,
};

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, JSON.stringify({ meta, rows }), 'utf8');
console.log(`Saved ${outPath}: ${rows.length} stocks, generated ${meta.generated} KST`);
