# -*- coding: utf-8 -*-
"""코스피 시총 상위 100개 종목 뉴스 일괄 분석 → 상승 후보 리포트 생성 (1회 실행)

실행: python main.py [YYYY-MM-DD]
      날짜 생략 시 오늘 날짜 뉴스를 분석
실시간 모니터링은 realtime.py (또는 start.bat) 사용
"""

import sys
import time
from datetime import date

import analyzer
import config
import crawler
import report

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    if len(sys.argv) > 1:
        target_date = date.fromisoformat(sys.argv[1])
    else:
        target_date = date.today()

    print(f"[1/4] 코스피 상위 {config.TOP_N_STOCKS} + 코스닥 상위 "
          f"{config.KOSDAQ_TOP_N}개 종목 수집 중...")
    stocks = crawler.get_all_stocks()
    print(f"      {len(stocks)}개 종목 수집 완료")

    print(f"[2/4] 종목별 뉴스 크롤링 및 분석 중 ({target_date.isoformat()})...")
    universe = {s["name"] for s in stocks}
    results = []
    start = time.time()
    for i, stock in enumerate(stocks, 1):
        try:
            articles = crawler.get_stock_news(stock["code"], target_date)
        except Exception as e:
            print(f"      [경고] {stock['name']} 뉴스 수집 실패: {e}")
            articles = []
        disclosures = []
        if config.FETCH_DISCLOSURES:
            try:
                disclosures = crawler.get_stock_disclosures(
                    stock["code"], target_date)
            except Exception:
                pass
        results.append(
            analyzer.analyze_stock(stock, articles, universe, disclosures))
        if i % 20 == 0:
            print(f"      {i}/{len(stocks)} 완료 ({time.time() - start:.0f}초 경과)")
        time.sleep(config.REQUEST_DELAY)

    print("[3/4] 상승 후보 선정 중...")
    picks = analyzer.pick_candidates(results)

    print("[4/4] 리포트 저장 중...")
    report_path, csv_path = report.save_outputs(target_date, picks, results)

    print(f"\n완료! 결과 파일:\n  - {report_path}\n  - {csv_path}\n")
    print("=== 상승 후보 종목 ===")
    for i, p in enumerate(picks, 1):
        print(f"{i:2d}. {p['name']}({p['code']}) "
              f"뉴스점수 {p['news_score']:+d} / 최종점수 {p['final_score']:+.2f}")
    if not picks:
        print("(오늘은 호재 뉴스 점수가 양수인 종목이 없습니다)")


if __name__ == "__main__":
    main()
