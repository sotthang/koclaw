#!/bin/bash
set -e

# storage 디렉토리가 없으면 생성
mkdir -p storage/workspace

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
