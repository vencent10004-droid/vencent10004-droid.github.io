# -*- coding: utf-8 -*-
"""뉴스 제목 감성 분석: 호재/악재 키워드 기반 점수 산출"""

import config


def is_relevant(stock_name: str, title: str, universe: set[str] | None = None) -> bool:
    """뉴스 제목이 실제로 이 종목에 관한 기사인지 판별.

    제목에 종목명(또는 config.STOCK_ALIASES의 별칭)이 포함돼야 관련 기사로 본다.
    이때 더 긴 다른 종목명의 일부로만 등장하는 경우는 제외한다.
    (예: 'SK'는 'SK하이닉스' 기사에 매칭되지 않고,
         '현대차'는 '현대백화점' 기사에 매칭되지 않는다)
    """
    terms = [stock_name] + config.STOCK_ALIASES.get(stock_name, [])
    for term in terms:
        masked = title
        if universe:
            # 이 종목명을 부분 문자열로 포함하는 더 긴 종목명을 먼저 지운다
            for other in universe:
                if other != term and term in other and other in masked:
                    masked = masked.replace(other, "")
        if term in masked:
            return True
    return False


def detect_material(title: str) -> list[tuple[str, str, bool]]:
    """뉴스 제목에서 투자유치성 재료/경계 재료 카테고리를 감지.

    반환: [(카테고리명, 매칭된 용어, 경계재료 여부), ...] - 카테고리당 최대 1건
    """
    found = []
    for category, terms in config.MATERIAL_CATEGORIES.items():
        for term in terms:
            if term in title:
                found.append((category, term, False))
                break
    for category, terms in config.WARNING_MATERIALS.items():
        for term in terms:
            if term in title:
                found.append((category, term, True))
                break
    return found


def score_title(title: str) -> tuple[int, list[str]]:
    """뉴스 제목 하나의 감성 점수와 매칭된 키워드 목록 반환"""
    score = 0
    matched = []
    # 긴 키워드부터 매칭해 중복 카운트 방지 (예: '적자전환'이 '적자'보다 우선)
    all_keywords = {**config.POSITIVE_KEYWORDS, **config.NEGATIVE_KEYWORDS}
    remaining = title
    for keyword in sorted(all_keywords, key=len, reverse=True):
        if keyword in remaining:
            score += all_keywords[keyword]
            matched.append(keyword)
            remaining = remaining.replace(keyword, "")
    return score, matched


def analyze_stock(stock: dict, articles: list[dict],
                  universe: set[str] | None = None,
                  disclosures: list[dict] | None = None) -> dict:
    """종목 하나에 대해 뉴스+공시 점수를 집계하고 최종 점수를 계산

    - universe가 주어지면 제목에 종목명이 실제로 들어간 기사만 점수에 반영
    - 공시(disclosures)는 정형화된 제목이라 관련성 검사 없이 반영
    - 같은 키워드는 종목당 최대 KEYWORD_CAP회까지만 점수에 반영해
      동일 이벤트의 반복 보도로 점수가 부풀려지는 것을 방지한다.
    """
    if universe is not None:
        articles = [a for a in articles
                    if is_relevant(stock["name"], a["title"], universe)]
    if disclosures:
        articles = articles + [{**d, "disclosure": True} for d in disclosures]
    all_keywords = {**config.POSITIVE_KEYWORDS, **config.NEGATIVE_KEYWORDS}
    news_score = 0
    keyword_counts: dict[str, int] = {}
    # 같은 키워드 조합(=같은 내용의 기사)은 대표 기사 1건만 남기고 건수만 센다
    hit_groups: dict[tuple, dict] = {}
    positive_hits = []   # {title, keywords, count}
    negative_hits = []
    # 투자유치성 재료: 카테고리당 대표 기사 1건 + 가점
    material_seen: dict[str, dict] = {}
    material_hits = []   # {category, term, title, url, datetime, count}

    for article in articles:
        for category, term, warn in detect_material(article["title"]):
            if category in material_seen:
                material_seen[category]["count"] += 1
                continue
            mh = {"category": category, "term": term, "warn": warn,
                  "title": article["title"], "url": article.get("url", ""),
                  "datetime": article["datetime"],
                  "disclosure": article.get("disclosure", False), "count": 1}
            material_seen[category] = mh
            material_hits.append(mh)
        s, matched = score_title(article["title"])
        for keyword in matched:
            count = keyword_counts.get(keyword, 0)
            if count < config.KEYWORD_CAP:
                news_score += all_keywords[keyword]
            keyword_counts[keyword] = count + 1
        if s == 0:
            continue
        sig = (s > 0, tuple(sorted(matched)))
        if sig in hit_groups:
            hit_groups[sig]["count"] += 1
            continue
        hit = {"title": article["title"], "keywords": matched,
               "url": article.get("url", ""),
               "disclosure": article.get("disclosure", False), "count": 1}
        hit_groups[sig] = hit
        if s > 0:
            positive_hits.append(hit)
        else:
            negative_hits.append(hit)

    # 재료 카테고리당 가점, 경계 재료는 감점 (하루 1회씩)
    for mh in material_hits:
        news_score += (config.WARNING_PENALTY if mh["warn"]
                       else config.MATERIAL_BONUS)

    final_score = (
        news_score * config.NEWS_WEIGHT
        + stock["change_rate"] * config.MOMENTUM_WEIGHT
    )

    return {
        **stock,
        "news_count": len(articles),
        "news_score": news_score,
        "final_score": round(final_score, 2),
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
        "material_hits": material_hits,
    }


def pick_candidates(results: list[dict], count: int = config.PICK_COUNT) -> list[dict]:
    """상승 후보 선정: 뉴스 점수가 양수인 종목을 최종 점수 순으로 정렬"""
    candidates = [r for r in results if r["news_score"] > 0]
    candidates.sort(key=lambda r: (r["final_score"], r["news_score"]), reverse=True)
    return candidates[:count]
