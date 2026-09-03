@echo off
chcp 65001 >nul
cd /d "%~dp0"
title KOSPI Realtime News Monitor
echo ============================================
echo  KOSPI 실시간 뉴스 모니터 시작
echo  브라우저에 대시보드가 자동으로 열립니다.
echo  휴대폰 접속 주소는 아래에 표시됩니다.
echo  종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ============================================
python -u realtime.py
pause
