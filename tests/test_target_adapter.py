import asyncio

from app.db.models import Target
from app.services.target_adapter import TargetAdapter


def make_target(endpoint: str) -> Target:
    return Target(
        id="target-1",
        name="mock target",
        endpoint=endpoint,
        model="mock-model",
        auth_env_var="TARGET_API_KEY",
        authorized=True,
        allowed_categories=["prompt_boundary"],
    )


def run_mock(endpoint: str):
    return asyncio.run(TargetAdapter(make_target(endpoint)).run_steps(["检查边界"]))


def test_secure_mock_returns_safe_response():
    transcript = run_mock("mock://secure")
    assert "无法披露" in transcript.messages[-1]["content"]
    assert transcript.latency_ms == 0


def test_prompt_leaky_mock_is_redacted_before_storage():
    transcript = run_mock("mock://prompt-leaky")
    text = transcript.messages[-1]["content"]
    assert "sk-mock-1234567890" not in text
    assert "[REDACTED_API_KEY]" in text


def test_unsafe_tool_mock_is_explicitly_unsafe():
    transcript = run_mock("mock://unsafe-tool")
    assert "未授权工具" in transcript.messages[-1]["content"]

