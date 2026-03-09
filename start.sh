#!/bin/bash
set -e

# storage 디렉토리가 없으면 생성 (DB 마운트 전 권한 확보)
mkdir -p storage/workspace

echo "🔨 이미지 빌드 중..."
docker compose build
docker compose --profile build-only build sandbox

echo "🚀 koclaw 시작..."
export WORKSPACE_HOST_PATH="$(pwd)/storage/workspace"
docker compose up -d koclaw

echo "✅ 완료!"
