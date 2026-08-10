# -*- coding: utf-8 -*-
"""분석 결과를 마크다운 리포트 + CSV로 저장 (일괄/실시간 공용)"""

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import config


def build_report(target_date: date, picks: list[dict], results: list[dict],
                 realtime: bool = False) -> str:
    title = ("실시간 코스피·코스닥 상승 후보" if realtime
             else "코스피·코스닥 상승 후보 리포트")
    lines = [
        f"# {title} ({target_date.isoformat()})",
        "",
        f"- 분석 대상: 코스피·코스닥 시가총액 상위 {len(results)}개 종목",
        f"- {target_date.isoformat()} 당일 게재된 뉴스만 집계 "
        f"(총 {sum(r['news_count'] for r in results)}건, 제목에 종목명이 포함된 기사만 반영)",
        f"- 갱신 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> ⚠️ 본 리포트는 뉴스 키워드 기반 자동 분석 결과이며, 투자 판단의 근거가 아닙니다.",
        "> 실제 투자 결정과 그 결과에 대한 책임은 투자자 본인에게 있습니다.",
        "",
        "## 다음 거래일 상승 후보 종목",
        "",
        "| 순위 | 종목명 | 코드 | 현재가 | 등락률 | 뉴스점수 | 최종점수 |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(picks, 1):
        lines.append(
            f"| {i} | {p['name']} | {p['code']} | {p['price']:,.0f} "
            f"| {p['change_rate']:+.2f}% | {p['news_score']} | {p['final_score']} |"
        )

    # 투자유치성 재료 뉴스 (전체 종목 대상)
    mats = []
    for r in results:
        for mh in r.get("material_hits", []):
            mats.append((r["name"], mh))
    mats.sort(key=lambda x: x[1]["datetime"], reverse=True)
    lines += ["", "## 💰 투자유치성 재료 뉴스 (당일)", ""]
    if mats:
        for name, mh in mats:
            title_md = (f"[{mh['title']}]({_canonical_url(mh['url'])})"
                        if mh.get("url") else mh["title"])
            m_extra = (f" (같은 내용 외 {mh['count'] - 1}건)"
                       if mh["count"] > 1 else "")
            lines.append(f"- `{mh['category']}` **{name}** — {title_md}{m_extra}")
    else:
        lines.append("- 오늘 감지된 재료 뉴스 없음")

    lines += ["", "## 종목별 근거 뉴스 (같은 내용 기사는 대표 1건만 표시)", ""]
    for p in picks:
        lines.append(f"### {p['name']} ({p['code']}) — 뉴스점수 {p['news_score']}")
        for icon, hits in (("🔺", p["positive_hits"]), ("🔻", p["negative_hits"])):
            for hit in hits:
                extra = (f" (같은 내용 외 {hit['count'] - 1}건)"
                         if hit["count"] > 1 else "")
                title_md = (f"[{hit['title']}]({_canonical_url(hit['url'])})"
                            if hit.get("url") else hit["title"])
                lines.append(f"- {icon} {title_md}{extra}  "
                             f"`[{', '.join(hit['keywords'])}]`")
        lines.append("")
    return "\n".join(lines)


def save_outputs(target_date: date, picks: list[dict], results: list[dict],
                 realtime: bool = False) -> tuple[Path, Path]:
    """리포트(.md)와 전체 결과(.csv) 저장 후 경로 반환"""
    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(exist_ok=True)
    suffix = "_realtime" if realtime else ""
    date_str = target_date.isoformat()

    df = pd.DataFrame([
        {k: r.get(k, "") for k in
         ("code", "name", "market", "price", "change_rate", "market_cap",
          "news_count", "news_score", "final_score")}
        for r in results
    ]).sort_values("final_score", ascending=False)
    csv_path = out_dir / f"{date_str}{suffix}_analysis.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    report_path = out_dir / f"{date_str}{suffix}_report.md"
    report_path.write_text(
        build_report(target_date, picks, results, realtime), encoding="utf-8")
    return report_path, csv_path


# ---------------------------------------------------------------
# 실시간 HTML 대시보드

DASHBOARD_NAME = "realtime_dashboard.html"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>코스피 실시간 뉴스 모니터</title>
<style>
  body {{ font-family: 'Malgun Gothic', sans-serif; background: #f4f6f9;
         margin: 0; padding: 24px; color: #222; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .meta {{ color: #667; font-size: 13px; margin-bottom: 16px; }}
  .warn {{ background: #fff3cd; border: 1px solid #ffe08a; border-radius: 6px;
           padding: 10px 14px; font-size: 13px; margin-bottom: 20px; }}
  .ai {{ background: #eef4ff; border: 1px solid #c9dcf8; border-radius: 6px;
         padding: 10px 14px; font-size: 13px; margin-bottom: 20px; }}
  .ai .prob {{ font-size: 16px; }}
  h2 {{ font-size: 17px; margin: 28px 0 10px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); font-size: 14px; }}
  th, td {{ padding: 8px 12px; border-bottom: 1px solid #e8ecf1; text-align: right; }}
  th {{ background: #2c3e50; color: #fff; font-weight: 600; }}
  td.name, th.name {{ text-align: left; }}
  tr:hover td {{ background: #f0f6ff; }}
  .up {{ color: #d32f2f; font-weight: 600; }}
  .down {{ color: #1565c0; font-weight: 600; }}
  .alert {{ background: #fff; border-left: 4px solid #d32f2f; margin: 6px 0;
            padding: 8px 12px; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }}
  .alert.neg {{ border-left-color: #1565c0; }}
  .kw {{ color: #888; font-size: 12px; }}
  .time {{ color: #999; font-size: 12px; margin-right: 8px; }}
  .table-wrap {{ overflow-x: auto; }}
  a {{ color: #1565c0; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  tr.mrow {{ cursor: pointer; }}
  .arr {{ color: #aab; font-size: 11px; }}
  tr.drow {{ display: none; background: #f8fafc; }}
  tr.drow td {{ text-align: left; white-space: normal; }}
  .dbox {{ padding: 4px 6px; }}
  .dline {{ padding: 3px 0; font-size: 13px; }}
  .naver {{ display: inline-block; margin-bottom: 6px; font-size: 13px; font-weight: 600; }}
  .badge {{ display: inline-block; background: #fff3d6; color: #7a5200;
            border: 1px solid #f0d9a0; border-radius: 4px; padding: 1px 7px;
            font-size: 11px; font-weight: 600; margin-right: 6px; }}
  .badge.warn {{ background: #fde8e8; color: #a02020; border-color: #f0b8b8; }}
  .src {{ display: inline-block; background: #e6f2ea; color: #1e6b3a;
          border: 1px solid #bfdcc9; border-radius: 4px; padding: 1px 6px;
          font-size: 11px; font-weight: 600; margin-right: 6px; }}
  .alert.mat {{ border-left-color: #f9a825; }}
  .mkt {{ display: inline-block; background: #e8eef7; color: #456;
          border-radius: 3px; padding: 0 4px; font-size: 10px;
          font-weight: 700; vertical-align: middle; }}
  .tmap {{ width: 100%; height: auto; background: #fff; border-radius: 8px;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 12px;
           display: block; }}
  .tmap a {{ cursor: pointer; }}
  .tmap a:hover rect {{ stroke: #2c3e50; stroke-width: 2; }}
  .tmap text {{ pointer-events: none; font-family: 'Malgun Gothic', sans-serif; }}
  .tmwrap {{ position: relative; }}
  .fsbtn {{ position: absolute; top: 8px; right: 8px; z-index: 2;
            background: rgba(44,62,80,.85); color: #fff; border: none;
            border-radius: 6px; padding: 6px 12px; font-size: 12px;
            font-family: inherit; cursor: pointer; }}
  #fsWrap {{ position: fixed; inset: 0; background: #f4f6f9; z-index: 50;
             display: none; flex-direction: column; }}
  #fsBar {{ display: flex; justify-content: space-between; align-items: center;
            padding: 10px 14px; background: #2c3e50; color: #fff; }}
  #fsBar b {{ font-size: 15px; }}
  #fsBar .hint {{ font-size: 11px; opacity: .75; margin-left: 10px; }}
  #fsBar button {{ background: #fff; color: #2c3e50; border: none;
                   border-radius: 6px; padding: 7px 16px; font-size: 13px;
                   font-weight: 700; font-family: inherit; cursor: pointer; }}
  #fsBody {{ flex: 1; overflow: auto; -webkit-overflow-scrolling: touch; }}
  #fsBody svg {{ width: 95vw; height: auto; display: block; margin: 8px auto; }}
  @media (max-width: 600px) {{
    #fsBody svg {{ width: 250vw; margin: 4px; }}
  }}
  h3 {{ font-size: 14px; margin: 14px 0 6px; color: #345; }}
  .session {{ display: inline-block; background: #e8f0e9; color: #1e6b3a;
              border: 1px solid #c4dcc9; border-radius: 12px; padding: 2px 12px;
              font-size: 12px; font-weight: 600; vertical-align: middle; }}
  .tabs {{ margin: 20px 0 0; display: flex; }}
  .tab {{ background: #dde5ee; border: none; border-radius: 6px 6px 0 0;
          padding: 8px 22px; font-size: 14px; font-weight: 600; color: #345;
          cursor: pointer; margin-right: 4px; font-family: inherit; flex: 0 1 auto; }}
  .tab.on {{ background: #2c3e50; color: #fff; }}
  @media (max-width: 600px) {{
    .tabs {{ position: sticky; top: 0; z-index: 5; background: #f4f6f9;
             padding-top: 4px; }}
    .tab {{ flex: 1; padding: 9px 4px; font-size: 13px; text-align: center; }}
  }}
  @media (max-width: 600px) {{
    body {{ padding: 12px; }}
    h1 {{ font-size: 18px; }}
    th, td {{ padding: 6px 8px; font-size: 13px; white-space: nowrap; }}
    .alert {{ font-size: 13px; }}
  }}
</style>
</head>
<body>
<h1>📈 코스피·코스닥 실시간 뉴스 모니터 <span style="font-size:14px;color:#888">시가총액 상위 {stock_count}종목</span></h1>
<div class="meta">마지막 갱신: {updated} · 당일 게재 뉴스만 집계 (누적 {news_total}건, 제목에 종목명 포함 기사만 반영) · 60초마다 자동 새로고침 (뉴스 펼침 중엔 일시정지) · <b>종목명 클릭 → 네이버 종목 페이지</b> · 행 클릭 → 근거 뉴스 펼침</div>
<div class="warn">⚠️ 뉴스 키워드 기반 자동 분석 결과이며 투자 판단의 근거가 아닙니다. 투자 결정과 결과의 책임은 본인에게 있습니다.</div>
{ai_card}

<div class="tabs">
<button class="tab on" data-m="all" onclick="showPane('all')">전체</button>
<button class="tab" data-m="KOSPI" onclick="showPane('KOSPI')">코스피</button>
<button class="tab" data-m="KOSDAQ" onclick="showPane('KOSDAQ')">코스닥</button>
</div>
<div id="pane-all" class="pane">
{heatmap_all}
<h2>🏆 다음 거래일 상승 후보 (전체 통합)</h2>
{table_all}
</div>
<div id="pane-KOSPI" class="pane" style="display:none">
{heatmap_kospi}
<h2>🏆 다음 거래일 상승 후보 (코스피)</h2>
{table_kospi}
</div>
<div id="pane-KOSDAQ" class="pane" style="display:none">
{heatmap_kosdaq}
<h2>🏆 다음 거래일 상승 후보 (코스닥)</h2>
{table_kosdaq}
</div>

<h2>💰 투자유치성 재료 뉴스 (당일, 최신순)</h2>
<div class="meta" style="margin-top:-4px">AI빅테크 · 정부지원 · JV · M&amp;A·지분투자 · 국부펀드 · 대규모 수주 · 바이오 기술수출 · 주주환원 · 국책사업 · 지배구조 · 지수편입 · 디지털자산 · 기술독점 — 13개 재료 카테고리 + <span class="badge warn">경계 재료 ⚠️</span> (보호예수 해제·블록딜·CB발행 등 물량 부담)</div>
{material_items}

<h2>🔔 실시간 뉴스 알림 (최신순)</h2>
{alert_items}

<div id="fsWrap">
<div id="fsBar"><span><b id="fsTitle"></b><span class="hint">드래그로 이동 · 핀치로 확대 · 타일 터치 시 종목 페이지</span></span>
<button onclick="fsClose()">✕ 닫기</button></div>
<div id="fsBody"></div>
</div>
<script>
function tg(id) {{
  var e = document.getElementById(id);
  var open = e.style.display === 'table-row';
  e.style.display = open ? 'none' : 'table-row';
  e.dataset.open = open ? '0' : '1';
}}
function showPane(m) {{
  document.querySelectorAll('.pane').forEach(function (p) {{
    p.style.display = (p.id === 'pane-' + m) ? '' : 'none';
  }});
  document.querySelectorAll('.tab').forEach(function (b) {{
    b.className = (b.dataset.m === m) ? 'tab on' : 'tab';
  }});
  document.querySelectorAll('div[data-market]').forEach(function (el) {{
    el.style.display = (m === 'all' || el.dataset.market === m) ? '' : 'none';
  }});
  try {{ localStorage.setItem('marketTab', m); }} catch (e) {{}}
}}
function fsOpen(btn) {{
  var svg = btn.closest('.tmwrap').querySelector('svg.tmap');
  var body = document.getElementById('fsBody');
  body.innerHTML = '';
  body.appendChild(svg.cloneNode(true));
  document.getElementById('fsTitle').textContent = btn.dataset.title || '';
  document.getElementById('fsWrap').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}}
function fsClose() {{
  document.getElementById('fsWrap').style.display = 'none';
  document.body.style.overflow = '';
}}
(function () {{
  var m = 'all';
  try {{ m = localStorage.getItem('marketTab') || 'all'; }} catch (e) {{}}
  if (m !== 'all') showPane(m);
}})();
setInterval(function () {{
  var fsOpen_ = document.getElementById('fsWrap').style.display === 'flex';
  if (!fsOpen_ && !document.querySelector("tr.drow[data-open='1']")) {{
    location.reload();
  }}
}}, 60000);
</script>
</body>
</html>
"""


_predict = None  # 첫 사용 때 로드 (False = 사용 불가)


def _build_ai_card(results: list[dict]) -> str:
    """딥러닝 히트맵 CNN의 다음 거래일 전망 카드 (모델 없으면 빈 문자열)"""
    global _predict
    if _predict is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent / "dl"))
            from predict import predict_next_day
            _predict = predict_next_day
        except Exception:
            _predict = False
    if not _predict:
        return ""
    try:
        pred = _predict({r["code"]: r["change_rate"] for r in results})
    except Exception:
        return ""
    if not pred:
        return ""
    prob = pred["prob_up"]
    cls = "up" if prob >= 0.5 else "down"
    return (
        f"<div class='ai'>🤖 <b>AI 내일 전망 (히트맵 CNN 실험)</b> — "
        f"다음 거래일 코스피 <span class='prob {cls}'>상승 확률 {prob:.0%}</span> "
        f"<span class='kw'>· 현재 등락률 {pred['coverage']}종목 히트맵 기준 · "
        f"딥러닝 미니 프로젝트 데모이며 예측 성능은 검증되지 않았습니다 (AUC≈0.5)</span></div>"
    )


def _canonical_url(url: str) -> str:
    """네이버 구형 링크를 모바일에서도 열리는 표준 형식으로 변환.

    - news_read.naver → n.news.naver.com/mnews/article/{언론사}/{기사ID}
    - news_notice_read.naver → m.stock.naver.com/domestic/stock/{code}/notice/{no}
    (구형 형식은 네이버가 폐기해 빈 페이지만 반환됨)
    """
    from urllib.parse import parse_qs, urlparse
    q = parse_qs(urlparse(url).query)
    if "news_read.naver" in url:
        aid = q.get("article_id", [""])[0]
        oid = q.get("office_id", [""])[0]
        if aid and oid:
            return f"https://n.news.naver.com/mnews/article/{oid}/{aid}"
    elif "news_notice_read.naver" in url:
        no = q.get("no", [""])[0]
        code = q.get("code", [""])[0]
        if no and code:
            return f"https://m.stock.naver.com/domestic/stock/{code}/notice/{no}"
    return url


def _link(title: str, url: str) -> str:
    if url:
        return (f"<a href='{_canonical_url(url)}' target='_blank' "
                f"rel='noopener'>{title}</a>")
    return title


def _ranking_table(picks: list[dict], prefix: str) -> str:
    """상승 후보 순위 테이블 HTML (prefix: 펼침 행 id 충돌 방지용)"""
    rows = []
    for i, p in enumerate(picks, 1):
        cr = p["change_rate"]
        cls = "up" if cr > 0 else ("down" if cr < 0 else "")
        naver_url = f"https://finance.naver.com/item/main.naver?code={p['code']}"
        mat_mark = " 💰" if p.get("material_hits") else ""
        if p.get("market") == "KOSDAQ":
            mat_mark += " <span class='mkt'>KQ</span>"
        rid = f"d{prefix}{i}"
        # 종목명 클릭 → 네이버 개별종목 페이지 / 행의 나머지 클릭 → 근거 뉴스 펼침
        rows.append(
            f"<tr class='mrow' onclick=\"tg('{rid}')\"><td>{i}</td>"
            f"<td class='name'><a href='{naver_url}' target='_blank' "
            f"rel='noopener' onclick='event.stopPropagation()'>{p['name']}</a>"
            f"{mat_mark} <span class='arr'>▾</span></td>"
            f"<td>{p['code']}</td><td>{p['price']:,.0f}</td>"
            f"<td class='{cls}'>{cr:+.2f}%</td>"
            f"<td>{p['news_score']}</td><td><b>{p['final_score']}</b></td></tr>"
        )
        # 펼쳐지는 종목 상세 행: 근거 뉴스 + 네이버 금융 링크
        detail = [f"<a class='naver' href='{naver_url}' target='_blank' "
                  f"rel='noopener'>📊 네이버 금융에서 {p['name']} 상세보기 ↗</a>"]
        for mh in p.get("material_hits", []):
            m_extra = (f" <span class='kw'>(같은 내용 외 {mh['count'] - 1}건)</span>"
                       if mh["count"] > 1 else "")
            b_cls = "badge warn" if mh.get("warn") else "badge"
            src = "<span class='src'>공시</span>" if mh.get("disclosure") else ""
            detail.append(
                f"<div class='dline'><span class='{b_cls}'>{mh['category']}</span>"
                f"{src}{_link(mh['title'], mh.get('url', ''))}{m_extra}</div>"
            )
        for icon, hits in (("🔺", p["positive_hits"]), ("🔻", p["negative_hits"])):
            for hit in hits:
                extra = (f" <span class='kw'>(같은 내용 외 {hit['count'] - 1}건)</span>"
                         if hit["count"] > 1 else "")
                detail.append(
                    f"<div class='dline'>{icon} "
                    f"{_link(hit['title'], hit.get('url', ''))}{extra} "
                    f"<span class='kw'>[{', '.join(hit['keywords'])}]</span></div>"
                )
        if len(detail) == 1:
            detail.append("<div class='dline kw'>표시할 근거 뉴스가 없습니다</div>")
        rows.append(
            f"<tr id='{rid}' class='drow'><td colspan='7'>"
            f"<div class='dbox'>{''.join(detail)}</div></td></tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='7' style='text-align:center;color:#888'>"
                    "아직 호재 점수가 양수인 종목이 없습니다</td></tr>")
    return (
        "<div class='table-wrap'>\n<table>\n"
        "<tr><th>순위</th><th class='name'>종목명</th><th>코드</th><th>현재가</th>"
        "<th>등락률</th><th>뉴스점수</th><th>최종점수</th></tr>\n"
        + "\n".join(rows) + "\n</table>\n</div>"
    )


def _squarify(values: list[float], x: float, y: float,
              w: float, h: float) -> list[tuple]:
    """시총 비례 트리맵 배치 (squarified). values는 내림차순 정렬 상태여야 함."""
    rects = []
    total = sum(values)
    if total <= 0 or not values:
        return rects
    scale = w * h / total
    areas = [v * scale for v in values]
    i = 0
    while i < len(areas):
        side = min(w, h)

        def worst(row):
            s = sum(row)
            return max(side * side * max(row) / (s * s),
                       s * s / (side * side * min(row)))

        row = [areas[i]]
        i += 1
        while i < len(areas) and worst(row + [areas[i]]) <= worst(row):
            row.append(areas[i])
            i += 1
        s = sum(row)
        if w >= h:  # 세로 열로 배치
            rw = s / h
            ry = y
            for a in row:
                rh = a / rw
                rects.append((x, ry, rw, rh))
                ry += rh
            x += rw
            w -= rw
        else:       # 가로 행으로 배치
            rh = s / w
            rx = x
            for a in row:
                rw2 = a / rh
                rects.append((rx, y, rw2, rh))
                rx += rw2
            y += rh
            h -= rh
    return rects


def _rate_color(v: float) -> str:
    t = max(-1.0, min(1.0, v / 5))
    return (f"rgba(211,47,47,{0.10 + 0.85 * t:.2f})" if t >= 0
            else f"rgba(21,101,192,{0.10 - 0.85 * t:.2f})")


def _heatmap_grid(cells: list[dict], height: int = 620,
                  prefix: str = "t") -> str:
    """업종별 그룹 + 시총 비례 크기의 트리맵 히트맵 (SVG).

    cells: [{code, name, rate, cap, sector}]
    모든 타일에 이름을 넣되 clipPath로 타일 밖은 잘라
    전체화면 확대 시 작은 종목도 읽을 수 있게 한다.
    """
    W = 1000
    cells = [c for c in cells if c.get("cap", 0) > 0]
    if not cells:
        return "<div class='kw'>시세 데이터가 없습니다</div>"

    # 업종별 그룹 (시총 합 내림차순)
    groups: dict[str, list[dict]] = {}
    for c in cells:
        groups.setdefault(c.get("sector") or "기타", []).append(c)
    sectors = sorted(groups.items(),
                     key=lambda kv: -sum(c["cap"] for c in kv[1]))
    sec_rects = _squarify([sum(c["cap"] for c in g) for _, g in sectors],
                          0, 0, W, height)

    parts = [f"<svg viewBox='0 0 {W} {height}' class='tmap' "
             f"xmlns='http://www.w3.org/2000/svg'>"]
    for (sec_name, g), (sx, sy, sw, sh) in zip(sectors, sec_rects):
        g.sort(key=lambda c: -c["cap"])
        # 업종 라벨 밴드 (영역이 충분할 때만)
        label_h = 15 if sh > 42 and sw > 60 else 0
        if label_h:
            parts.append(
                f"<text x='{sx + 4:.0f}' y='{sy + 11:.0f}' font-size='10' "
                f"fill='#556' font-weight='700'>"
                f"{sec_name[:int(sw / 11)]}</text>")
        inner = _squarify([c["cap"] for c in g],
                          sx, sy + label_h, sw, sh - label_h)
        for c, (x, y, w, h) in zip(g, inner):
            v = c["rate"]
            url = f"https://finance.naver.com/item/main.naver?code={c['code']}"
            cid = f"{prefix}{c['code']}"
            parts.append(
                f"<clipPath id='{cid}'><rect x='{x:.1f}' y='{y:.1f}' "
                f"width='{w:.1f}' height='{h:.1f}'/></clipPath>"
                f"<a href='{url}' target='_blank' rel='noopener'>"
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{w:.1f}' height='{h:.1f}' "
                f"fill='{_rate_color(v)}' stroke='#fff' stroke-width='1'>"
                f"</rect>"
                f"<title>{c['name']} ({sec_name}) {v:+.2f}%</title>")
            # 모든 타일에 이름 표기 (타일 크기에 맞춰 글자 크기 조정,
            # 넘치는 부분은 clipPath로 잘림 → 확대하면 읽을 수 있음)
            if w > 8 and h > 8:
                fs = max(4.5, min(17, w / (len(c["name"]) * 1.05 + 0.5),
                                  h / 2.6))
                cx, cy = x + w / 2, y + h / 2
                parts.append(
                    f"<g clip-path='url(#{cid})'>"
                    f"<text x='{cx:.1f}' y='{cy - 0.5:.1f}' "
                    f"font-size='{fs:.1f}' text-anchor='middle' "
                    f"fill='#10243a' font-weight='600'>{c['name']}</text>"
                    f"<text x='{cx:.1f}' y='{cy + fs:.1f}' "
                    f"font-size='{fs * 0.85:.1f}' text-anchor='middle' "
                    f"fill='#10243a' opacity='.8'>{v:+.1f}%</text></g>")
            parts.append("</a>")
        # 업종 경계선
        parts.append(
            f"<rect x='{sx:.1f}' y='{sy:.1f}' width='{sw:.1f}' "
            f"height='{sh:.1f}' fill='none' stroke='#f4f6f9' "
            f"stroke-width='2.5'></rect>")
    parts.append("</svg>")
    return "".join(parts)


def _heatmap_sections(heatmap: dict | None) -> dict:
    """탭별 히트맵 HTML 조각 생성. heatmap: {label, kospi: cells, kosdaq: cells}"""
    if not heatmap:
        return {"heatmap_all": "", "heatmap_kospi": "", "heatmap_kosdaq": ""}
    label = f"<span class='session'>{heatmap['label']}</span>"

    def wrap(svg: str, name: str) -> str:
        return (f"<div class='tmwrap'><button class='fsbtn' "
                f"data-title='{name} 히트맵' onclick='fsOpen(this)'>"
                f"🔍 크게 보기</button>{svg}</div>")

    kospi = wrap(_heatmap_grid(heatmap["kospi"], height=620, prefix="k"),
                 "코스피")
    kosdaq = wrap(_heatmap_grid(heatmap["kosdaq"], height=420, prefix="q"),
                  "코스닥")
    title = f"<h2>🗺️ 실시간 히트맵 {label}</h2>"
    return {
        "heatmap_all": (
            f"{title}<h3>코스피 상위 {len(heatmap['kospi'])}</h3>{kospi}"
            f"<h3>코스닥 상위 {len(heatmap['kosdaq'])}</h3>{kosdaq}"),
        "heatmap_kospi": f"{title}{kospi}",
        "heatmap_kosdaq": f"{title}{kosdaq}",
    }


def build_dashboard(picks: list[dict], results: list[dict],
                    alerts: list[dict], heatmap: dict | None = None) -> str:
    """실시간 HTML 대시보드 생성. alerts: [{datetime, name, title, score, keywords}]"""
    import analyzer  # 시장별 후보 산출용 (지연 임포트로 순환 참조 방지)

    kospi = [r for r in results if r.get("market") != "KOSDAQ"]
    kosdaq = [r for r in results if r.get("market") == "KOSDAQ"]
    table_all = _ranking_table(picks, "a")
    table_kospi = _ranking_table(analyzer.pick_candidates(kospi), "k")
    table_kosdaq = _ranking_table(analyzer.pick_candidates(kosdaq), "q")

    items = []
    for a in alerts[:60]:
        cls = "alert" if a["score"] >= 0 else "alert neg"
        icon = "🔺" if a["score"] > 0 else ("🔻" if a["score"] < 0 else "▪")
        extra = (f" <span class='kw'>(같은 내용 외 {a['count'] - 1}건)</span>"
                 if a.get("count", 1) > 1 else "")
        src = "<span class='src'>공시</span>" if a.get("disclosure") else ""
        items.append(
            f"<div class='{cls}' data-market='{a.get('market', '')}'>"
            f"<span class='time'>{a['datetime']}</span>"
            f"{icon} {src}<b>{a['name']}</b> [{a['score']:+d}] "
            f"{_link(a['title'], a.get('url', ''))}{extra} "
            f"<span class='kw'>[{', '.join(a['keywords'])}]</span></div>"
        )
    if not items:
        items.append("<div style='color:#888'>아직 알림 대상 뉴스가 없습니다</div>")

    # 투자유치성 재료 뉴스: 전체 종목에서 수집해 최신순으로
    mats = []
    for r in results:
        for mh in r.get("material_hits", []):
            mats.append((r["name"], r.get("market", ""), mh))
    mats.sort(key=lambda x: x[2]["datetime"], reverse=True)
    mat_items = []
    for name, market, mh in mats[:60]:
        m_extra = (f" <span class='kw'>(같은 내용 외 {mh['count'] - 1}건)</span>"
                   if mh["count"] > 1 else "")
        b_cls = "badge warn" if mh.get("warn") else "badge"
        box_cls = "alert neg mat" if mh.get("warn") else "alert mat"
        src = "<span class='src'>공시</span>" if mh.get("disclosure") else ""
        mat_items.append(
            f"<div class='{box_cls}' data-market='{market}'>"
            f"<span class='time'>{mh['datetime']}</span>"
            f"<span class='{b_cls}'>{mh['category']}</span>{src}<b>{name}</b> "
            f"{_link(mh['title'], mh.get('url', ''))}{m_extra}</div>"
        )
    if not mat_items:
        mat_items.append(
            "<div style='color:#888'>오늘 감지된 투자유치성 재료 뉴스가 없습니다</div>")

    return _HTML_TEMPLATE.format(
        stock_count=len(results),
        updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        news_total=sum(r["news_count"] for r in results),
        ai_card=_build_ai_card(results),
        table_all=table_all,
        table_kospi=table_kospi,
        table_kosdaq=table_kosdaq,
        material_items="\n".join(mat_items),
        alert_items="\n".join(items),
        **_heatmap_sections(heatmap),
    )


def save_dashboard(picks: list[dict], results: list[dict],
                   alerts: list[dict], heatmap: dict | None = None) -> Path:
    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(exist_ok=True)
    path = out_dir / DASHBOARD_NAME
    path.write_text(
        build_dashboard(picks, results, alerts, heatmap), encoding="utf-8")
    return path


def save_placeholder_dashboard() -> Path:
    """첫 수집이 끝나기 전 브라우저에 보여줄 준비 화면"""
    out_dir = Path(config.OUTPUT_DIR)
    out_dir.mkdir(exist_ok=True)
    path = out_dir / DASHBOARD_NAME
    path.write_text(
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        "<meta http-equiv='refresh' content='15'>"
        "<title>코스피 실시간 뉴스 모니터</title></head>"
        "<body style=\"font-family:'Malgun Gothic',sans-serif;padding:40px\">"
        "<h2>📡 첫 뉴스 수집 중입니다...</h2>"
        "<p>약 1~2분 후 이 화면이 자동으로 대시보드로 바뀝니다.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    return path
