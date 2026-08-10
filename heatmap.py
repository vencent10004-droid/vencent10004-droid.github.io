# -*- coding: utf-8 -*-
"""세션 인지 실시간 히트맵 데이터 수집

네이버 모바일 API(m.stock.naver.com)로 현재 세션을 판별하고,
프리마켓/애프터마켓(NXT) 중에는 시간외 시세를, 정규장에는 정규장 등락률을 반환한다.
- 프리마켓(NXT): 08:00~08:50
- 정규장(KRX):   09:00~15:30
- 애프터마켓(NXT): 15:30~20:00
"""

from concurrent.futures import ThreadPoolExecutor

import requests

_API = "https://m.stock.naver.com/api/stock/{code}/basic"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


def _basic(code: str) -> dict:
    r = requests.get(_API.format(code=code), headers=_HEADERS, timeout=8)
    r.raise_for_status()
    return r.json()


def _parse_ratio(text, direction: str = "") -> float | None:
    """'1.95' + 방향(RISING/FALLING) → 부호 있는 등락률"""
    if text in (None, ""):
        return None
    try:
        v = float(str(text).replace(",", "").replace("%", ""))
    except ValueError:
        return None
    if direction in ("FALLING", "LOWER_LIMIT") and v > 0:
        v = -v
    return v


def get_session() -> tuple[str, str]:
    """현재 세션 판별 → (키, 표시 라벨)"""
    try:
        d = _basic("005930")
    except requests.RequestException:
        return "unknown", "정규장 기준 (실시간 조회 불가)"
    if d.get("marketStatus") == "OPEN":
        return "regular", "정규장 실시간"
    over = d.get("overMarketPriceInfo") or {}
    if over.get("overMarketStatus") == "OPEN":
        if over.get("tradingSessionType") == "PRE_MARKET":
            return "pre", "프리마켓(NXT) 실시간"
        return "after", "애프터마켓(NXT) 실시간"
    return "closed", "장 마감 (정규장 종가 기준)"


def _over_rate(code: str) -> tuple[str, float | None]:
    """시간외(NXT) 등락률. 시간외 시세가 없으면 정규장 등락률로 폴백."""
    try:
        d = _basic(code)
    except requests.RequestException:
        return code, None
    over = d.get("overMarketPriceInfo") or {}
    if over.get("overMarketStatus") == "OPEN":
        v = _parse_ratio(
            over.get("fluctuationsRatio"),
            (over.get("compareToPreviousPrice") or {}).get("name", ""),
        )
        if v is not None:
            return code, v
    return code, _parse_ratio(
        d.get("fluctuationsRatio"),
        (d.get("compareToPreviousPrice") or {}).get("name", ""),
    )


def get_heatmap_rates(stocks: list[dict]) -> tuple[str, dict[str, float]]:
    """히트맵용 세션 인지 등락률.

    반환: (세션 라벨, {종목코드: 등락률})
    프리/애프터마켓 중에는 NXT 시세를 병렬 조회하고,
    정규장/마감 시에는 이미 수집된 등락률(change_rate)을 그대로 쓴다.
    """
    session, label = get_session()
    rates: dict[str, float] = {}
    if session in ("pre", "after"):
        with ThreadPoolExecutor(max_workers=10) as pool:
            for code, v in pool.map(_over_rate, [s["code"] for s in stocks]):
                if v is not None:
                    rates[code] = v
    for s in stocks:  # 조회 실패/미대상 종목은 정규장 등락률로 폴백
        rates.setdefault(s["code"], s["change_rate"])
    return label, rates
