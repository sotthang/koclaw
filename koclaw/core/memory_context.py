from dataclasses import dataclass


@dataclass
class MemoryContext:
    user_scope: str | None = None
    channel_scope: str | None = None
    thread_scope: str | None = None

    def applicable_scopes(self) -> list[tuple[str, str]]:
        result = []
        if self.user_scope:
            result.append(("user", self.user_scope))
        if self.channel_scope:
            result.append(("channel", self.channel_scope))
        if self.thread_scope:
            result.append(("thread", self.thread_scope))
        return result


def parse_memory_context(
    session_id: str,
    user_id: str | None = None,
    parent_channel_id: str | None = None,
) -> MemoryContext:
    """session_id + user_id로부터 적용 가능한 메모리 스코프를 결정합니다.

    Slack:
      slack:D{id}        → DM → user scope
      slack:C{id}        → channel scope
      slack:C{id}:{ts}   → channel scope + thread scope

    Discord:
      discord:dm:{uid}       → DM → user scope
      discord:thread:{id}    → thread scope (+ channel scope if parent_channel_id 제공)
      discord:{id}           → channel scope
    """
    if session_id.startswith("slack:"):
        rest = session_id[len("slack:"):]
        parts = rest.split(":")
        channel = parts[0]
        if channel.startswith("D") or channel.startswith("G"):
            return MemoryContext(user_scope=user_id)
        if len(parts) >= 2:
            return MemoryContext(
                channel_scope=f"slack:{channel}",
                thread_scope=session_id,
            )
        return MemoryContext(channel_scope=session_id)

    if session_id.startswith("discord:"):
        rest = session_id[len("discord:"):]
        if rest.startswith("dm:"):
            return MemoryContext(user_scope=user_id)
        if rest.startswith("thread:"):
            channel_scope = f"discord:{parent_channel_id}" if parent_channel_id else None
            return MemoryContext(channel_scope=channel_scope, thread_scope=session_id)
        return MemoryContext(channel_scope=session_id)

    return MemoryContext()
