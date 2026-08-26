from __future__ import annotations

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.responses import JSONResponse

from .config import AgentRuntimeConfig


def build_agent_card(config: AgentRuntimeConfig) -> AgentCard:
    skills = [
        AgentSkill(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            tags=skill.tags,
            examples=skill.examples,
            inputModes=config.input_modes,
            outputModes=config.output_modes,
        )
        for skill in config.skills
    ]
    return AgentCard(
        name=config.name,
        description=config.description,
        url=config.public_url,
        version="1.0.0",
        defaultInputModes=config.input_modes,
        defaultOutputModes=config.output_modes,
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
        ),
        skills=skills,
    )


def create_a2a_app(
    config: AgentRuntimeConfig,
    executor,
    *,
    lifespan=None,
):
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=build_agent_card(config),
        http_handler=handler,
    )
    app = server.build(lifespan=lifespan)

    async def readiness(_request):
        return JSONResponse(executor.agent.readiness())

    app.add_route("/health/ready", readiness, methods=["GET"])
    return app
