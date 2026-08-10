# -*- coding: utf-8 -*-
"""코스피 상위 100개 종목 뉴스 실시간 모니터링

5분(config.POLL_INTERVAL_SECONDS)마다 전체 종목의 새 뉴스를 확인해
- 호재/악재 뉴스를 콘솔에 즉시 알림
- output/YYYY-MM-DD_realtime_report.md 실시간 순위 리포트 갱신
- state/ 폴더에 당일 수집 상태 저장 (재시작해도 이어서 집계)

실행:  python realtime.py          (RUN_UNTIL 시각까지 계속 실행, Ctrl+C로 종료)
       python realtime.py --once   (한 번만 스윕하고 종료 - 테스트용)
"""

import json
import socket
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import analyzer
import config
import crawler
import heatmap
import publish
import report
import sector

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except AttributeError:
    pass


def state_path(today: date) -> Path:
    return Path(config.STATE_DIR) / f"{today.isoformat()}.json"


def load_state(today: date) -> dict:
    path = state_path(today)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("date") == today.isoformat():
            state.setdefault("disclosures", {})
            return state
    return {"date": today.isoformat(), "articles": {}, "disclosures": {}}


def save_state(state: dict):
    path = state_path(date.fromisoformat(state["date"]))
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def sweep(stocks: list[dict], state: dict, first: bool) -> list[tuple]:
    """전 종목 뉴스를 한 바퀴 확인하고 새로 발견한 알림 대상 뉴스 반환"""
    today = date.fromisoformat(state["date"])
    universe = {s["name"] for s in stocks}
    alerts = []
    alert_sigs = {}  # 같은 내용(종목+키워드 조합)은 대표 1건만 알림
    for stock in stocks:
        code = stock["code"]
        # 처음 보는 종목(예: 새로 추가된 코스닥)은 전체 페이지 수집
        pages = (config.NEWS_PAGES_PER_STOCK
                 if first or code not in state["articles"] else 1)
        try:
            articles = crawler.get_stock_news(code, today, pages=pages)
        except Exception as e:
            print(f"  [경고] {stock['name']} 뉴스 수집 실패: {e}")
            continue
        known = {a["title"]: a for a in state["articles"].get(code, [])}
        for a in articles:
            if a["title"] in known:
                # 링크 없이 저장된 기존 기사에 링크 보충
                if not known[a["title"]].get("url") and a.get("url"):
                    known[a["title"]]["url"] = a["url"]
                continue
            state["articles"].setdefault(code, []).append(a)
            # 제목에 종목명이 실제로 들어간 기사만 알림 대상
            if not analyzer.is_relevant(stock["name"], a["title"], universe):
                continue
            score, keywords = analyzer.score_title(a["title"])
            cats = [c for c, _t, _w in analyzer.detect_material(a["title"])]
            # 투자유치성 재료 뉴스는 점수와 무관하게 항상 알림
            if cats or abs(score) >= config.ALERT_THRESHOLD:
                sig = (code, score > 0, tuple(sorted(keywords + cats)))
                if sig in alert_sigs:
                    alert_sigs[sig]["count"] += 1
                    continue
                alert = {"name": stock["name"], "score": score,
                         "keywords": keywords, "cats": cats,
                         "article": a, "count": 1}
                alert_sigs[sig] = alert
                alerts.append(alert)

        # 당일 공시 수집 - 재료/점수 감지 시 알림
        if config.FETCH_DISCLOSURES:
            try:
                notices = crawler.get_stock_disclosures(code, today)
            except Exception:
                notices = []
            known_n = {d["title"] for d in state["disclosures"].get(code, [])}
            for d in notices:
                if d["title"] in known_n:
                    continue
                state["disclosures"].setdefault(code, []).append(d)
                score, keywords = analyzer.score_title(d["title"])
                cats = [c for c, _t, _w in analyzer.detect_material(d["title"])]
                if cats or abs(score) >= config.ALERT_THRESHOLD:
                    alerts.append({"name": stock["name"], "score": score,
                                   "keywords": keywords, "cats": cats,
                                   "article": d, "disclosure": True,
                                   "count": 1})
        time.sleep(config.REQUEST_DELAY)
    return alerts


def print_alerts(alerts: list[dict]):
    for al in alerts:
        if al["score"] > 0:
            icon = "🔺호재"
        elif al["score"] < 0:
            icon = "🔻악재"
        else:
            icon = "▪재료"
        tag = f"💰재료[{'/'.join(al['cats'])}] " if al.get("cats") else ""
        if al.get("disclosure"):
            tag = "📋공시 " + tag
        extra = (f" (같은 내용 외 {al['count'] - 1}건)"
                 if al["count"] > 1 else "")
        print(f"  {tag}{icon}[{al['score']:+d}] {al['name']} | "
              f"{al['article']['title']}{extra} "
              f"({al['article']['datetime']}) [{', '.join(al['keywords'])}]")


class _DashboardHandler(SimpleHTTPRequestHandler):
    """output 폴더를 서빙하되 루트(/)는 대시보드로 연결, 접속 로그는 숨김"""

    def do_GET(self):
        if self.path in ("", "/"):
            self.path = "/" + report.DASHBOARD_NAME
        return super().do_GET()

    def log_message(self, *args):
        pass


def get_lan_ip() -> str:
    """같은 네트워크의 다른 기기(휴대폰)에서 접속할 수 있는 PC의 IP 주소"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 실제 전송 없음 - 라우팅 IP 확인용
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def start_web_server() -> ThreadingHTTPServer:
    out_dir = Path(config.OUTPUT_DIR).resolve()
    out_dir.mkdir(exist_ok=True)
    handler = partial(_DashboardHandler, directory=str(out_dir))
    server = ThreadingHTTPServer(("0.0.0.0", config.WEB_PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def collect_alerts(stocks: list[dict], state: dict) -> list[dict]:
    """당일 누적 기사 중 알림 기준 이상 뉴스를 최신순으로 반환 (대시보드용)"""
    names = {s["code"]: s["name"] for s in stocks}
    markets = {s["code"]: s.get("market", "") for s in stocks}
    universe = {s["name"] for s in stocks}
    alerts = []
    for code, articles in state["articles"].items():
        name = names.get(code, code)
        for a in articles:
            if not analyzer.is_relevant(name, a["title"], universe):
                continue
            score, keywords = analyzer.score_title(a["title"])
            if abs(score) >= config.ALERT_THRESHOLD:
                alerts.append({
                    "datetime": a["datetime"],
                    "name": name,
                    "market": markets.get(code, ""),
                    "title": a["title"],
                    "url": a.get("url", ""),
                    "score": score,
                    "keywords": keywords,
                })
    # 공시도 알림 대상에 포함 (관련성 검사 불필요 - 정형화된 제목)
    for code, notices in state.get("disclosures", {}).items():
        name = names.get(code, code)
        for d in notices:
            score, keywords = analyzer.score_title(d["title"])
            cats = analyzer.detect_material(d["title"])
            if not cats and abs(score) < config.ALERT_THRESHOLD:
                continue
            alerts.append({
                "datetime": d["datetime"],
                "name": name,
                "market": markets.get(code, ""),
                "title": d["title"],
                "url": d.get("url", ""),
                "score": score,
                "keywords": keywords,
                "disclosure": True,
            })
    alerts.sort(key=lambda a: a["datetime"], reverse=True)

    # 같은 내용(종목+키워드 조합)은 최신 기사 1건만 남기고 건수를 센다
    deduped = []
    seen = {}
    for a in alerts:
        if a.get("disclosure"):
            sig = (a["name"], "공시", a["title"])  # 공시는 제목 단위로 구분
        else:
            sig = (a["name"], a["score"] > 0, tuple(sorted(a["keywords"])))
        if sig in seen:
            seen[sig]["count"] += 1
        else:
            a["count"] = 1
            seen[sig] = a
            deduped.append(a)
    return deduped


_dl_dashboard = None  # 첫 사용 때 로드 (False = 사용 불가)


def update_heatmap_dashboard(stocks: list[dict]):
    """딥러닝 히트맵 대시보드를 장중 등락률로 갱신 (torch 없으면 조용히 생략)"""
    global _dl_dashboard
    if _dl_dashboard is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent / "dl"))
            import dashboard as mod
            _dl_dashboard = mod
        except Exception as e:
            print(f"  [안내] 히트맵 CNN 대시보드 비활성 ({e})")
            _dl_dashboard = False
    if _dl_dashboard:
        try:
            _dl_dashboard.save_live(
                {s["code"]: s["change_rate"] for s in stocks})
        except Exception as e:
            print(f"  [경고] 히트맵 대시보드 갱신 실패: {e}")


def should_stop() -> bool:
    if not config.RUN_UNTIL:
        return False
    limit = datetime.strptime(config.RUN_UNTIL, "%H:%M").time()
    return datetime.now().time() >= limit


def main():
    once = "--once" in sys.argv
    print(f"실시간 모니터링 시작 (주기 {config.POLL_INTERVAL_SECONDS}초, "
          f"종료 시각 {config.RUN_UNTIL or '없음'}) - Ctrl+C로 종료\n")

    state = load_state(date.today())
    first = not state["articles"]  # 당일 상태가 없으면 첫 스윕

    # 대시보드 준비 화면 생성 후 웹서버 시작 (수집 완료 시 자동 전환)
    report.save_placeholder_dashboard()
    try:
        start_web_server()
    except OSError as e:
        print(f"[경고] 웹서버 시작 실패 (포트 {config.WEB_PORT} 사용 중?): {e}")
        print("       이미 실행 중인 모니터가 있다면 그쪽 대시보드를 사용하세요.")
        return
    local_url = f"http://localhost:{config.WEB_PORT}/"
    mobile_url = f"http://{get_lan_ip()}:{config.WEB_PORT}/"
    print(f"대시보드 주소 (이 PC)          : {local_url}")
    print(f"대시보드 주소 (같은 와이파이)  : {mobile_url}")
    if config.PUBLISH_ENABLED:
        print(f"대시보드 주소 (인터넷 공개)    : {config.PUBLIC_URL}")
        print(f"  → 모바일 데이터로도 접속 가능, 약 {config.PUBLISH_INTERVAL_SECONDS // 60}분 간격 갱신")
    print()
    if not once:
        webbrowser.open(local_url)

    last_publish = 0.0  # 첫 스윕 직후 바로 업로드되도록 0에서 시작
    try:
        while True:
            today = date.today()
            if state["date"] != today.isoformat():  # 자정 넘김 → 새 날짜로 초기화
                state = load_state(today)
                first = True

            sweep_start = time.time()
            stocks = crawler.get_all_stocks()  # 코스피+코스닥 목록·현재가·등락률 갱신
            alerts = sweep(stocks, state, first)
            first = False
            save_state(state)

            universe = {s["name"] for s in stocks}
            results = [
                analyzer.analyze_stock(
                    s, state["articles"].get(s["code"], []), universe,
                    state["disclosures"].get(s["code"], []))
                for s in stocks
            ]
            picks = analyzer.pick_candidates(results)
            report_path, _ = report.save_outputs(today, picks, results, realtime=True)

            # 세션 인지 실시간 히트맵 (코스피 상위 100 + 코스닥 상위 50)
            # 프리/애프터마켓 중에는 NXT 시간외 시세를 반영한다
            kospi_top = [s for s in stocks if s.get("market") == "KOSPI"][:100]
            kosdaq_top = [s for s in stocks if s.get("market") == "KOSDAQ"][:50]
            try:
                heat_label, heat_rates = heatmap.get_heatmap_rates(
                    kospi_top + kosdaq_top)
                sectors = sector.get_sectors(
                    [s["code"] for s in kospi_top + kosdaq_top])

                def _cells(lst):
                    return [{"code": s["code"], "name": s["name"],
                             "rate": heat_rates[s["code"]],
                             "cap": s.get("market_cap", 0),
                             "sector": sectors.get(s["code"], "기타")}
                            for s in lst]

                heat = {"label": heat_label,
                        "kospi": _cells(kospi_top),
                        "kosdaq": _cells(kosdaq_top)}
            except Exception as e:
                print(f"  [경고] 히트맵 시세 조회 실패: {e}")
                heat = None
            report.save_dashboard(picks, results,
                                  collect_alerts(stocks, state), heat)
            update_heatmap_dashboard(stocks)  # 딥러닝 히트맵도 장중 값으로 갱신

            # 공개 주소(GitHub Pages)에 주기적으로 업로드
            if (config.PUBLISH_ENABLED
                    and time.time() - last_publish >= config.PUBLISH_INTERVAL_SECONDS):
                try:
                    outcome = publish.publish_dashboard()
                    last_publish = time.time()
                    if outcome == "pushed":
                        print(f"  🌐 공개 주소 갱신 완료: {config.PUBLIC_URL}")
                except RuntimeError as e:
                    print(f"  [경고] 공개 주소 업로드 실패: {e}")

            now = datetime.now().strftime("%H:%M:%S")
            total = sum(len(v) for v in state["articles"].values())
            print(f"[{now}] 스윕 완료 ({time.time() - sweep_start:.0f}초) | "
                  f"새 알림 {len(alerts)}건 | 누적 뉴스 {total}건 | "
                  f"리포트: {report_path}")
            print_alerts(alerts)
            if picks:
                top = ", ".join(
                    f"{p['name']}({p['final_score']:+.1f})" for p in picks[:5])
                print(f"  현재 상위: {top}\n")

            if once:
                break
            if should_stop():
                print(f"\n{config.RUN_UNTIL} 도달 - 모니터링을 종료합니다.")
                break
            elapsed = time.time() - sweep_start
            time.sleep(max(30, config.POLL_INTERVAL_SECONDS - elapsed))
    except KeyboardInterrupt:
        save_state(state)
        print("\n사용자 중단 - 상태 저장 후 종료합니다.")


if __name__ == "__main__":
    main()
