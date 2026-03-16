#!/bin/bash
set -e

# storage 디렉토리가 없으면 생성
mkdir -p storage/workspace

# ── Windows Agent 자동 시작 ──────────────────────────────
# WINDOWS_AGENT_URL이 .env에 설정된 경우 Windows Agent를 항상 재시작
WINDOWS_AGENT_URL=""
if [ -f .env ]; then
    WINDOWS_AGENT_URL=$(grep "^WINDOWS_AGENT_URL=" .env | cut -d'=' -f2 | tr -d '\r' | tr -d '"')
fi

if [ -n "$WINDOWS_AGENT_URL" ]; then
    echo "🖥️  Windows Agent 재시작 중..."
    if ! command -v powershell.exe &>/dev/null; then
        echo "⚠️  powershell.exe를 찾을 수 없습니다 (WSL interop 비활성화 또는 비Windows 환경)."
        echo "   다음 경로를 PATH에 추가한 뒤 재시도하세요:"
        echo "   export PATH=\"\$PATH:/mnt/c/Windows/System32/WindowsPowerShell/v1.0\""
        echo "   또는 Windows에서 직접 start.ps1을 실행해 Windows Agent를 재시작하세요."
    else
        WINDOWS_HOME=$(powershell.exe -NoProfile -Command '$env:USERPROFILE' 2>/dev/null | tr -d '\r\n')
        START_PS1="${WINDOWS_HOME}\\koclaw-agent\\start.ps1"
        # 7777 포트 사용 중인 프로세스만 종료
        powershell.exe -NoProfile -Command "
            \$conn = Get-NetTCPConnection -LocalPort 7777 -ErrorAction SilentlyContinue | Select-Object -First 1
            if (\$conn) { Stop-Process -Id \$conn.OwningProcess -Force -ErrorAction SilentlyContinue }
        " 2>/dev/null || true
        sleep 1
        # 새로 시작 (백그라운드, 숨김 창)
        powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File "$START_PS1" >/dev/null 2>&1 &
        echo "✅ Windows Agent 시작됨"
    fi
fi
# ────────────────────────────────────────────────────────

# 컨테이너를 현재 사용자 UID/GID로 실행 (볼륨 권한 문제 방지)
export CURRENT_UID=$(id -u)
export CURRENT_GID=$(id -g)
# Docker socket GID 동적 감지 (computer_use 컨테이너 실행 권한)
# macOS Docker Desktop: 컨테이너 내부에서 socket이 항상 root:root(GID 0)으로 보임
# Linux: 호스트 GID와 컨테이너 내부 GID가 일치하므로 host에서 감지
if [[ "$(uname)" == "Darwin" ]]; then
    export DOCKER_GID=0
else
    export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 999)
fi

echo "🔨 이미지 빌드 중..."
docker compose build
docker compose --profile build-only build computer-use

echo "🚀 koclaw 시작..."
docker compose up -d koclaw

echo "✅ 완료!"
