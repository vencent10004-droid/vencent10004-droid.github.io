# -*- coding: utf-8 -*-
"""GitHub Actions용 스윕/렌더 모듈

- run_sweep(): 뉴스·공시 수집 + 분석 (약 3분, 5분 주기용)
- render(ctx): 실시간 시세 조회 + 대시보드 생성 (약 15초, 60초 주기용)
- main(): 1회 실행 (스윕 + 렌더)
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


def run_sweep() -> dict:
    """뉴스·공시 수집과 분석 - 5분 주기 풀 스윕"""
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

    total = sum(len(v) for v in state["articles"].values())
    print(f"[cloud] 스윕 완료 | 누적 뉴스 {total}건 | 후보 {len(picks)}종목")
    return {"stocks": stocks, "state": state,
            "results": results, "picks": picks}


def _build_heat(stocks: list[dict]) -> dict | None:
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

        return {"label": label, "kospi": cells(kospi_top),
                "kosdaq": cells(kosdaq_top)}
    except Exception as e:
        print(f"[cloud] 히트맵 시세 조회 실패: {e}")
        return None


def render(ctx: dict):
    """실시간 시세로 히트맵을 갱신해 대시보드 재생성 - 60초 주기"""
    heat = _build_heat(ctx["stocks"])
    dashboard = report.save_dashboard(
        ctx["picks"], ctx["results"],
        realtime.collect_alerts(ctx["stocks"], ctx["state"]), heat)
    Path("kospi").mkdir(exist_ok=True)
    shutil.copyfile(dashboard, Path("kospi") / "index.html")


def main():
    ctx = run_sweep()
    render(ctx)


if __name__ == "__main__":
    main()
