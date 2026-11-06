import re


_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "[REDACTED_API_KEY]"),
    (
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
        r"\1[REDACTED_TOKEN]",
    ),
    (
        re.compile(
            r"(?i)((?:password|passwd|secret|api[_-]?key)\s*[:=]\s*)[^\s,;]+"
        ),
        r"\1[REDACTED_SECRET]",
    ),
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*)[^\s,;]+"),
        r"\1[REDACTED_AUTH]",
    ),
]


def redact_text(value: str) -> str:
    """Mask common credentials before persistence or model prompts."""
    if not isinstance(value, str):
        return value
    result = value
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_messages(messages: list[dict]) -> list[dict]:
    redacted = []
    for message in messages:
        item = dict(message)
        if isinstance(item.get("content"), str):
            item["content"] = redact_text(item["content"])
        redacted.append(item)
    return redacted

