from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TargetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    endpoint: str = Field(description="OpenAI-compatible chat completions endpoint")
    model: str = Field(min_length=1, max_length=100)
    auth_env_var: str = "TARGET_API_KEY"
    authorized: bool = False
    allowed_categories: list[str] = Field(
        default_factory=lambda: ["prompt_boundary", "data_protection", "tool_boundary"]
    )


class TargetRead(TargetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str


class TestCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    severity: str
    description: str
    steps: list[str]
    expected_behavior: str
    source_ref: str | None = None


class RunCreate(BaseModel):
    target_id: str
    categories: list[str] | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    target_id: str
    status: str
    summary: dict[str, Any] | None = None


class ResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    case_id: str
    verdict: str
    severity: str
    confidence: float
    reason: str
    evidence: dict[str, Any] | None = None
    latency_ms: int

