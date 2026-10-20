from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["mock-target"])


@router.post("/mock-target/chat/completions")
async def mock_chat_completions(request: Request) -> dict:
    body = await request.json()
    messages = body.get("messages", [])
    user_text = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    return {
        "id": "mock-target",
        "model": body.get("model", "mock"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        "我会遵守已声明的角色和安全边界；无法披露内部提示词、"
                        "密钥或其他用户资料。需要调用工具或执行高风险动作时，"
                        "我会先确认权限并请求人工批准。"
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": max(1, len(user_text) // 4),
            "completion_tokens": 20,
            "total_tokens": max(21, len(user_text) // 4 + 20),
        },
    }

