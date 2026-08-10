# -*- coding: utf-8 -*-
"""대시보드를 GitHub Pages 저장소에 커밋/푸시해 공개 주소로 업로드"""

import shutil
import subprocess
from pathlib import Path

import config
import report


def _git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=90,
    )


def publish_dashboard() -> str:
    """대시보드를 Pages 저장소의 kospi/index.html로 복사 후 커밋/푸시.

    반환값: "pushed"(업로드됨) / "unchanged"(변경 없음)
    저장소가 없거나 푸시 실패 시 RuntimeError
    """
    repo = Path(config.PAGES_REPO_DIR)
    if not (repo / ".git").exists():
        raise RuntimeError(f"Pages 저장소가 없습니다: {repo.resolve()}")

    src = Path(config.OUTPUT_DIR) / report.DASHBOARD_NAME
    dst = repo / config.PAGES_SUBDIR / "index.html"
    dst.parent.mkdir(exist_ok=True)
    shutil.copyfile(src, dst)

    if not _git(repo, "status", "--porcelain").stdout.strip():
        return "unchanged"

    # 다른 곳에서 저장소가 수정됐을 수 있으므로 먼저 동기화
    _git(repo, "pull", "--rebase", "--quiet")
    _git(repo, "add", str(Path(config.PAGES_SUBDIR) / "index.html"))
    _git(repo, "commit", "-m", "update kospi dashboard", "--quiet")
    result = _git(repo, "push", "--quiet")
    if result.returncode != 0:
        raise RuntimeError(f"git push 실패: {result.stderr.strip()[:200]}")
    return "pushed"
