# 에이전트 타임아웃 (초)
AGENT_TIMEOUT_DEFAULT = 120  # 일반 쿼리: 2분
AGENT_TIMEOUT_COMPUTER_USE = 600  # computer_use 세션: 10분

# 대화 요약 임계값
SUMMARIZE_THRESHOLD = 20
KEEP_RECENT_MESSAGES = 4

# 파일 크기 제한
MAX_FILE_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 다운로드: 50MB
MAX_FILE_WRITE_BYTES = 1024 * 1024  # 파일 tool 쓰기: 1MB
MAX_FILE_COUNT = 100  # 세션당 최대 파일 수

# 웹 검색 재시도 (지수 백오프)
SEARCH_MAX_RETRIES = 3
SEARCH_RETRY_DELAY = 2.0  # 기준 초 — 실제 대기: delay * 2^attempt
