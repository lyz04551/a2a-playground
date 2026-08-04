"""Validated commands accepted by the unified run runtime."""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class RunCommand(BaseModel):
    conversation_id: str | None = None
    mode: Literal["direct", "auto"]
    target_agent_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def validate_target_for_mode(self) -> Self:
        if self.mode == "direct":
            if not self.target_agent_id or not self.target_agent_id.strip():
                raise ValueError(
                    "target_agent_id is required for direct mode"
                )
            self.target_agent_id = self.target_agent_id.strip()
        else:
            # Auto routing is exclusively owned by the Host. Silently discard
            # stale UI state instead of allowing it to influence routing.
            self.target_agent_id = None
        return self
