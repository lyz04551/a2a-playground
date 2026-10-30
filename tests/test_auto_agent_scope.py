from backend.registry.service import AgentRegistry


class Repository:
    def list_agents(self):
        return [
            {"id": "k8s-ops", "skills": [{"id": "diagnose", "tags": ["kubernetes"]}]},
            {"id": "external", "skills": [{"id": "diagnose", "tags": ["kubernetes"]}]},
        ]

    def get_agent(self, agent_id):
        return next((agent for agent in self.list_agents() if agent["id"] == agent_id), None)


def test_auto_scope_excludes_external_agent_from_listing_and_fallback():
    registry = AgentRegistry(Repository(), allowed_ids={"k8s-ops"})
    assert [agent["id"] for agent in registry.list()] == ["k8s-ops"]
    assert registry.get("external") is None
    assert [agent["id"] for agent in registry.rank_candidates(
        skill="diagnose", tags={"kubernetes"}, risk="read"
    )] == ["k8s-ops"]


def test_direct_registry_still_exposes_external_agent():
    registry = AgentRegistry(Repository())
    assert registry.get("external")["id"] == "external"
