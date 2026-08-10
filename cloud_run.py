# -*- coding: utf-8 -*-
"""GitHub Actions용 1회 스윕 실행

클라우드에서 10분마다 실행되어 수집→분석→대시보드 생성 후
kospi/index.html 로 복사한다 (커밋/푸시는 워크플로가 담당).
당일 수집 상태(state/)는 Actions 캐시로 이어진다.
"""

import shutil
import sys
from datetime import date
from pathlib import Path

import analyzer
import config
import crawler
import heatmap as hm
import realtime
import report
import sector

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except AttributeError:
    pass


def main():
    today = date.today()
    state = realtime.load_state(today)
    first = not state["articles"]

    print(f"[cloud] {today.isoformat()} 스윕 시작 (첫 수집: {first})")
    stocks = crawler.get_all_stocks()
    alerts = realtime.sweep(stocks, state, first)
    realtime.save_state(state)
    realtime.print_alerts(alerts)

    universe = {s["name"] for s in stocks}
    results = [
        analyzer.analyze_stock(
            s, state["articles"].get(s["code"], []), universe,
            state["disclosures"].get(s["code"], []))
        for s in stocks
    ]
    picks = analyzer.pick_candidates(results)

    kospi_top = [s for s in stocks if s.get("market") == "KOSPI"][:100]
    kosdaq_top = [s for s in stocks if s.get("market") == "KOSDAQ"][:50]
    try:
        label, rates = hm.get_heatmap_rates(kospi_top + kosdaq_top)
        sectors = sector.get_sectors(
            [s["code"] for s in kospi_top + kosdaq_top])

        def cells(lst):
            return [{"code": s["code"], "name": s["name"],
                     "rate": rates[s["code"]],
                     "cap": s.get("market_cap", 0),
                     "sector": sectors.get(s["code"], "기타")} for s in lst]

        heat = {"label": label, "kospi": cells(kospi_top),
                "kosdaq": cells(kosdaq_top)}
    except Exception as e:
        print(f"[cloud] 히트맵 조회 실패: {e}")
        heat = None

    dashboard = report.save_dashboard(
        picks, results, realtime.collect_alerts(stocks, state), heat)
    Path("kospi").mkdir(exist_ok=True)
    shutil.copyfile(dashboard, Path("kospi") / "index.html")

    total = sum(len(v) for v in state["articles"].values())
    print(f"[cloud] 완료 | 누적 뉴스 {total}건 | 후보 {len(picks)}종목")


if __name__ == "__main__":
    main()
