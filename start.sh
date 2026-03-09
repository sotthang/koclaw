#!/bin/bash
set -e

# storage 디렉토리가 없으면 생성 (DB 마운트 전 권한 확보)
mkdir -p storage/workspace

# 컨테이너를 현재 사용자 UID/GID로 실행 (볼륨 권한 문제 방지)
export CURRENT_UID=$(id -u)
export CURRENT_GID=$(id -g)
# Docker socket GID 동적 감지 (sandbox 컨테이너 실행 권한)
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 999)

echo "🔨 이미지 빌드 중..."
docker compose build
docker compose --profile build-only build sandbox

echo "🚀 koclaw 시작..."
export WORKSPACE_HOST_PATH="$(pwd)/storage/workspace"
docker compose up -d koclaw

echo "✅ 완료!"
