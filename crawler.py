# -*- coding: utf-8 -*-
"""네이버 금융 크롤러: 코스피 시총 상위 종목 목록 + 종목별 뉴스"""

import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

import config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}

session = requests.Session()
session.headers.update(HEADERS)


def _get(url: str, params: dict | None = None) -> BeautifulSoup:
    """GET 요청 후 BeautifulSoup 반환 (네이버 금융은 euc-kr 인코딩)"""
    for attempt in range(3):
        try:
            resp = session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            resp.encoding = "euc-kr"
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))


def _parse_number(text: str) -> float:
    """'1,234' / '+1.23%' 같은 문자열을 숫자로 변환"""
    cleaned = re.sub(r"[^0-9.\-+]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def get_top_stocks(n: int = config.TOP_N_STOCKS, sosok: int = 0) -> list[dict]:
    """시가총액 상위 n개 종목 (sosok: 0=코스피, 1=코스닥)"""
    stocks = []
    page = 1
    while len(stocks) < n:
        soup = _get(
            "https://finance.naver.com/sise/sise_market_sum.naver",
            params={"sosok": sosok, "page": page},
        )
        rows = soup.select("table.type_2 tbody tr")
        found = False
        for row in rows:
            link = row.select_one("a.tltle")
            if not link:
                continue
            found = True
            cols = row.select("td")
            code_match = re.search(r"code=(\d{6})", link.get("href", ""))
            if not code_match:
                continue
            stocks.append({
                "code": code_match.group(1),
                "name": link.get_text(strip=True),
                "price": _parse_number(cols[2].get_text()),
                "change_rate": _parse_number(cols[4].get_text()),  # 등락률 %
                "market_cap": _parse_number(cols[6].get_text()),   # 억원
            })
            if len(stocks) >= n:
                break
        if not found:  # 더 이상 페이지 없음
            break
        page += 1
        time.sleep(config.REQUEST_DELAY)
    return stocks


def get_stock_disclosures(code: str, target_date: date | None = None,
                          pages: int = 1) -> list[dict]:
    """종목별 공시 중 target_date(기본: 오늘) 날짜의 공시 제목 수집

    네이버 공시 페이지(table.type6)는 날짜만 있고 시각은 없다.
    """
    if target_date is None:
        target_date = date.today()
    date_prefix = target_date.strftime("%Y.%m.%d")

    items = []
    for page in range(1, pages + 1):
        soup = _get(
            "https://finance.naver.com/item/news_notice.naver",
            params={"code": code, "page": page},
        )
        rows = soup.select("table.type6 tr")
        todays = 0
        for row in rows:
            title_el = row.select_one("td.title a")
            date_el = row.select_one("td.date")
            if not title_el or not date_el:
                continue
            d = date_el.get_text(strip=True)
            if not d.startswith(date_prefix):
                continue
            todays += 1
            href = title_el.get("href", "")
            if href.startswith("/"):
                href = "https://finance.naver.com" + href
            items.append({
                "title": title_el.get_text(strip=True),
                "datetime": d,
                "url": href,
            })
        if todays == 0:  # 이 페이지에 당일 공시 없음 → 이후 페이지는 과거
            break
        time.sleep(config.REQUEST_DELAY)

    seen = set()
    unique = []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            unique.append(it)
    return unique


def get_all_stocks() -> list[dict]:
    """분석 대상 전체: 코스피 상위 + 코스닥 상위 종목"""
    stocks = get_top_stocks(config.TOP_N_STOCKS, sosok=0)
    for s in stocks:
        s["market"] = "KOSPI"
    if config.KOSDAQ_TOP_N > 0:
        kosdaq = get_top_stocks(config.KOSDAQ_TOP_N, sosok=1)
        for s in kosdaq:
            s["market"] = "KOSDAQ"
        stocks += kosdaq
    return stocks


def get_stock_news(code: str, target_date: date | None = None,
                   pages: int | None = None) -> list[dict]:
    """종목별 뉴스 중 target_date(기본: 오늘) 날짜의 기사 제목 수집"""
    if target_date is None:
        target_date = date.today()
    if pages is None:
        pages = config.NEWS_PAGES_PER_STOCK
    date_prefix = target_date.strftime("%Y.%m.%d")

    articles = []
    for page in range(1, pages + 1):
        soup = _get(
            "https://finance.naver.com/item/news_news.naver",
            params={"code": code, "page": page},
        )
        rows = soup.select("table.type5 tr")
        stop = False
        for row in rows:
            title_el = row.select_one("td.title a")
            date_el = row.select_one("td.date")
            if not title_el or not date_el:
                continue
            article_date = date_el.get_text(strip=True)
            if article_date.startswith(date_prefix):
                href = title_el.get("href", "")
                if href.startswith("/"):
                    href = "https://finance.naver.com" + href
                articles.append({
                    "title": title_el.get_text(strip=True),
                    "datetime": article_date,
                    "url": href,
                })
            elif article_date < date_prefix:
                # 날짜 내림차순이므로 과거 기사가 나오면 중단
                stop = True
                break
        if stop:
            break
        time.sleep(config.REQUEST_DELAY)

    # 중복 제목 제거 (연관기사 묶음 등)
    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    return unique
