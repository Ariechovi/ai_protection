from app.services.redaction import redact_messages, redact_text


def test_redacts_common_credentials():
    text = (
        "sk-1234567890abcdef "
        "Authorization: Bearer abc.def.ghi "
        "password=hunter2 "
        "api_key=my-secret"
    )
    result = redact_text(text)
    assert "sk-1234567890abcdef" not in result
    assert "hunter2" not in result
    assert "my-secret" not in result
    assert "[REDACTED_API_KEY]" in result
    assert "[REDACTED_TOKEN]" in result
    assert "[REDACTED_SECRET]" in result


def test_redacts_message_contents_only():
    messages = [
        {"role": "user", "content": "token sk-1234567890abcdef"},
        {"role": "assistant", "content": "safe"},
    ]
    result = redact_messages(messages)
    assert result[0]["content"] != messages[0]["content"]
    assert result[1]["content"] == "safe"

