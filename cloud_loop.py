# -*- coding: utf-8 -*-
"""GitHub Actions 장시간 실시간 루프

5분마다 스윕(cloud_run.main)을 돌리고 결과 dashboard.html을
data 브랜치에 강제 푸시한다 (단일 커밋 유지 - 저장소 비대화 방지).
공개 페이지(kospi/index.html)는 정적 셸이며, 이 데이터를 60초마다
raw.githubusercontent.com 에서 받아와 화면만 갱신한다.

- 오전 잡: ~13:58 종료 / 오후 잡: ~19:58 종료 (Actions 6시간 한도 대응)
- 당일 수집 상태(state/)와 업종 캐시도 data 브랜치로 잡 사이에 인계
"""

import shutil
import subprocess
import sys
import time
from datetime import datetime
from datetime import time as dtime
from pathlib import Path

import cloud_run
import config
import report

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except AttributeError:
    pass

DATAREPO = Path("datarepo")


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(DATAREPO), *args],
                          capture_output=True, text=True, timeout=120)


def restore_state():
    """이전 잡이 data 브랜치에 남긴 당일 상태·업종 캐시 복원"""
    src = DATAREPO / "state"
    if src.exists():
        dst = Path(config.STATE_DIR)
        dst.mkdir(exist_ok=True)
        for f in src.glob("*.json"):
            if not (dst / f.name).exists():
                shutil.copyfile(f, dst / f.name)
    cache = DATAREPO / "sector_cache.json"
    if cache.exists() and not Path("sector_cache.json").exists():
        shutil.copyfile(cache, "sector_cache.json")


def push_data():
    """대시보드 + 당일 상태를 data 브랜치 단일 커밋으로 강제 푸시"""
    shutil.copyfile(Path(config.OUTPUT_DIR) / report.DASHBOARD_NAME,
                    DATAREPO / "dashboard.html")
    (DATAREPO / "state").mkdir(exist_ok=True)
    today = datetime.now().date().isoformat()
    state_file = Path(config.STATE_DIR) / f"{today}.json"
    if state_file.exists():
        shutil.copyfile(state_file, DATAREPO / "state" / state_file.name)
    if Path("sector_cache.json").exists():
        shutil.copyfile("sector_cache.json", DATAREPO / "sector_cache.json")

    _git("add", "-A")
    if _git("rev-parse", "--verify", "HEAD").returncode == 0:
        _git("commit", "--amend", "-m", "data")
    else:
        _git("commit", "-m", "data")
    p = _git("push", "--force", "origin", "data")
    print("[cloud] data 푸시:",
          "OK" if p.returncode == 0 else p.stderr.strip()[:200])


def _end_time() -> dtime:
    now = datetime.now().time()
    if now < dtime(13, 58):
        return dtime(13, 58)
    if now < dtime(19, 58):
        return dtime(19, 58)
    return now  # 장외 시간에 시작되면 1회만 실행


def main():
    restore_state()
    end = _end_time()
    start = time.time()
    print(f"[cloud] 실시간 루프 시작 (뉴스 5분·시세 60초 주기, "
          f"{end.strftime('%H:%M')} 종료 예정)")

    def time_up() -> bool:
        return (datetime.now().time() >= end
                or time.time() - start > 5 * 3600 + 40 * 60)

    ctx = None
    while True:
        t0 = time.time()
        # 풀 스윕 (뉴스·공시 수집 + 분석 + 렌더)
        try:
            ctx = cloud_run.run_sweep()
            cloud_run.render(ctx)
            push_data()
        except Exception as e:
            print(f"[cloud] 스윕 오류: {e}")
        if time_up():
            break
        # 다음 풀 스윕까지 60초마다 시세만 갱신 (실시간 히트맵)
        while time.time() - t0 < 295 and not time_up():
            time.sleep(max(15, 60 - ((time.time() - t0) % 60)))
            if ctx is None:
                continue
            try:
                cloud_run.render(ctx)
                push_data()
            except Exception as e:
                print(f"[cloud] 시세 갱신 오류: {e}")
        if time_up():
            break
    print("[cloud] 루프 종료")


if __name__ == "__main__":
    main()
