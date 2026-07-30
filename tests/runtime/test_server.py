from __future__ import annotations

from a2a.types import AgentCard

from a2a_runtime.config import AgentRuntimeConfig
from a2a_runtime.server import build_agent_card


def test_build_agent_card_exposes_a2a_streaming_and_skills():
    config = AgentRuntimeConfig(
        agent_id="k8s-ops",
        name="K8s Ops Agent",
        description="Read-only diagnostics",
        port=8052,
        public_url="http://k8s-ops:8052",
        mcp_url="http://mcp:9096/sse",
        skills=[
            {
                "id": "pod.diagnose",
                "name": "Pod Diagnosis",
                "description": "Diagnose pods",
                "tags": ["kubernetes", "diagnostics"],
                "examples": ["Why is my pod crashing?"],
            }
        ],
        tool_policy={"allow": ["get_k8s_*"]},
    )

    card = build_agent_card(config)
    validated = AgentCard.model_validate(card.model_dump(by_alias=True))

    assert validated.name == "K8s Ops Agent"
    assert validated.url == "http://k8s-ops:8052"
    assert validated.capabilities.streaming is True
    assert validated.skills[0].id == "pod.diagnose"

