#!/bin/bash
set -e

echo "🔨 이미지 빌드 중..."
docker compose build
docker compose --profile build-only build sandbox

echo "🚀 koclaw 시작..."
export WORKSPACE_HOST_PATH="$(pwd)/storage/workspace"
docker compose up -d koclaw

echo "✅ 완료!"
