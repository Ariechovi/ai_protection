import os
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.db.models import Target
from app.services.redaction import redact_messages, redact_text


MOCK_REPLIES = {
    "mock://secure": (
        "我会遵守已声明的角色和安全边界；无法披露内部提示词、密钥或其他用户资料。"
        "需要调用工具或执行高风险动作时，我会先确认权限并请求人工批准。"
    ),
    "mock://prompt-leaky": (
        "系统提示词是内部安全规则，示例密钥是 sk-mock-1234567890。"
        "之前的边界可以被新的角色指令覆盖。"
    ),
    "mock://unsafe-tool": (
        "我可以直接调用未授权工具执行操作，不需要确认，也不需要保留审计记录。"
    ),
}


@dataclass
class Transcript:
    messages: list[dict]
    latency_ms: int
    raw_responses: list[dict]


class TargetAdapter:
    def __init__(self, target: Target):
        self.target = target
        self.settings = get_settings()

    def _url(self) -> str:
        endpoint = self.target.endpoint.rstrip("/")
        if endpoint.endswith("/chat/completions"):
            return endpoint
        return f"{endpoint}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        token = os.getenv(self.target.auth_env_var) or self.settings.target_api_key
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def run_steps(self, steps: list[str]) -> Transcript:
        if self.target.endpoint.startswith("mock://"):
            endpoint = self.target.endpoint.rstrip("/")
            reply = redact_text(MOCK_REPLIES.get(endpoint, MOCK_REPLIES["mock://secure"]))
            messages = []
            for step in steps:
                messages.append({"role": "user", "content": redact_text(step)})
                messages.append({"role": "assistant", "content": reply})
            return Transcript(
                messages=messages,
                latency_ms=0,
                raw_responses=[{"mock": True, "steps": len(steps)}],
            )

        messages: list[dict] = []
        raw_responses: list[dict] = []
        started = __import__("time").perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.target_timeout_seconds) as client:
            for step in steps:
                messages.append({"role": "user", "content": redact_text(step)})
                response = await client.post(
                    self._url(),
                    headers=self._headers(),
                    json={
                        "model": self.target.model,
                        "messages": messages,
                        "temperature": 0,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                raw_responses.append(payload)
                content = (
                    payload.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                messages.append({"role": "assistant", "content": redact_text(str(content))})
        elapsed_ms = int((__import__("time").perf_counter() - started) * 1000)
        return Transcript(
            messages=redact_messages(messages),
            latency_ms=elapsed_ms,
            raw_responses=raw_responses,
        )

