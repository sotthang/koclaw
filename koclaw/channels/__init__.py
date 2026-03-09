from typing import Any


def match_registry(registry: dict[str, Any], session_id: str) -> Any | None:
    """session_id에 대해 가장 긴 prefix를 가진 항목을 반환합니다."""
    for prefix in sorted(registry.keys(), key=len, reverse=True):
        if session_id.startswith(prefix):
            return registry[prefix]
    return None


def parse_parent_session_id(session_id: str) -> str | None:
    """스레드 session_id에서 부모 채널 session_id를 반환한다.

    slack:C123:thread_ts       → slack:C123
    discord:thread:P123:T456   → discord:P123
    그 외                       → None
    """
    parts = session_id.split(":")
    if parts[0] == "slack" and len(parts) == 3 and parts[1] != "dm":
        return f"slack:{parts[1]}"
    if parts[0] == "discord" and len(parts) == 4 and parts[1] == "thread":
        return f"discord:{parts[2]}"
    return None
