from __future__ import annotations

from a2a.types import AgentCard

from a2a_runtime.server import build_agent_card

from .test_agent_configs import load_configs


def test_all_agent_cards_are_valid_a2a_cards(monkeypatch):
    cards = [
        build_agent_card(config) for config in load_configs(monkeypatch)
    ]

    for card in cards:
        AgentCard.model_validate(card.model_dump(by_alias=True))
        assert card.capabilities.streaming is True
        assert card.skills

    assert {card.name for card in cards} == {
        "K8s Ops Agent",
        "K8s Resource Orchestrator Agent",
        "K8s Security Agent",
    }
