#\!/bin/bash
set -e

# 가상 디스플레이 시작
Xvfb :99 -screen 0 1280x720x24 &
sleep 1

# 윈도우 매니저 시작
openbox &
sleep 0.5

# Firefox 브라우저 시작
firefox about:blank &

sleep 2

# VNC 서버 시작 (포트 5900)
x11vnc -display :99 -forever -nopw -quiet -nodpms -bg

# noVNC 웹 뷰어 시작 (포트 6080)
/usr/share/novnc/utils/launch.sh --vnc localhost:5900 --listen 6080 &

# 컨테이너 유지
tail -f /dev/null
