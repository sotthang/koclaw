FROM docker:cli AS docker-cli

FROM python:3.12-slim

WORKDIR /app

# Docker CLI 복사 (sandbox 컨테이너 생성용, socket mount 방식)
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 의존성 먼저 복사 (캐시 활용)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-editable --extra browse --extra file --extra korean --extra discord

# 소스 복사
COPY koclaw/ ./koclaw/
COPY main.py ./

CMD ["uv", "run", "python", "main.py"]
