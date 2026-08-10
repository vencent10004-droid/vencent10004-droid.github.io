# -*- coding: utf-8 -*-
"""종목별 업종명 조회 (네이버 모바일 API, 파일 캐시)

업종은 바뀌지 않으므로 sector_cache.json에 저장해 두고 새 종목만 조회한다.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

_CACHE_PATH = Path(__file__).resolve().parent / "sector_cache.json"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


def _industry_code(code: str) -> tuple[str, str | None]:
    try:
        r = requests.get(
            f"https://m.stock.naver.com/api/stock/{code}/integration",
            headers=_HEADERS, timeout=8)
        r.raise_for_status()
        ind = r.json().get("industryCode")
        return code, (str(ind) if ind else None)
    except requests.RequestException:
        return code, None


def _industry_name(no: str) -> tuple[str, str | None]:
    try:
        r = requests.get(
            f"https://m.stock.naver.com/api/stocks/industry/{no}"
            f"?page=1&pageSize=1",
            headers=_HEADERS, timeout=8)
        r.raise_for_status()
        return no, (r.json().get("groupInfo") or {}).get("name")
    except requests.RequestException:
        return no, None


def get_sectors(codes: list[str]) -> dict[str, str]:
    """{종목코드: 업종명}. 캐시에 없는 종목만 API 조회."""
    cache: dict[str, str] = {}
    if _CACHE_PATH.exists():
        try:
            cache = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}

    missing = [c for c in codes if c not in cache]
    if missing:
        with ThreadPoolExecutor(max_workers=10) as pool:
            code_to_ind = dict(pool.map(_industry_code, missing))
            unique_inds = {i for i in code_to_ind.values() if i}
            ind_names = dict(pool.map(_industry_name, unique_inds))
        for code, ind in code_to_ind.items():
            name = ind_names.get(ind) if ind else None
            if name:
                cache[code] = name
        _CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    return {c: cache.get(c, "기타") for c in codes}
