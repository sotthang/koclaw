MAX_EXTERNAL_CONTENT_LENGTH = 15000


def _sanitize_label(label: str) -> str:
    """label의 대괄호를 제거하여 경계 문자열 위조를 방지한다."""
    return label.replace("[", "").replace("]", "")


def wrap_external_content(
    label: str,
    content: str,
    max_length: int = MAX_EXTERNAL_CONTENT_LENGTH,
) -> str:
    """외부 소스에서 가져온 콘텐츠를 명확한 경계로 래핑합니다.

    LLM이 외부 데이터 내의 지시사항을 따르지 않도록 컨텍스트를 명시합니다.
    """
    safe_label = _sanitize_label(label)

    if len(content) > max_length:
        truncated_chars = len(content) - max_length
        content = content[:max_length] + f"\n... ({truncated_chars}자 잘림)"

    return f"[외부 데이터 시작: {safe_label}]\n{content}\n[외부 데이터 끝: {safe_label}]"
