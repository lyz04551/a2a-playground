"""K8s Orchestrator A2A Agent — A2A Starlette server with AgentCard."""

import asyncio
from contextlib import asynccontextmanager
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from agent import K8sOrchestratorAgent, init_agent, shutdown_agent
from agent_executor import K8sOrchestratorAgentExecutor

import httpx
import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import (
    BasePushNotificationSender,
    InMemoryPushNotificationConfigStore,
    InMemoryTaskStore,
)
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

HOST = "0.0.0.0"
PORT = 8051
AGENT_URL = f"http://{HOST}:{PORT}"
AGENT_NAME = "K8s Orchestrator Agent"
AGENT_DESCRIPTION = (
    "Kubernetes orchestration agent that manages K8s resources via MCP tools. "
    "Supports generating, analyzing, applying, and retrieving K8s resource configurations "
    "(Deployment, Service, ConfigMap, etc.) through a LangGraph-powered ReAct agent."
)


def build_agent_card() -> AgentCard:
    """Build the AgentCard for A2A discovery."""
    skill = AgentSkill(
        id="k8s_orchestration",
        name="Kubernetes Resource Orchestration",
        description=(
            "Generate, analyze, apply, and retrieve Kubernetes resource configurations "
            "(Deployment, Service, ConfigMap, Namespace, Pod, etc.) via MCP tools"
        ),
        inputModes=["text/plain"],
        outputModes=["text/plain"],
        tags=["kubernetes", "k8s", "orchestration", "deployment", "infrastructure", "mcp"],
        examples=[
            "Create a deployment for an nginx web server",
            "List all pods in the default namespace",
            "Analyze the current state of the cluster",
            "Generate a ConfigMap for application configuration",
            "Apply a YAML deployment configuration",
        ],
    )

    return AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=AGENT_URL,
        version="1.0.0",
        defaultInputModes=K8sOrchestratorAgent.SUPPORTED_CONTENT_TYPES,
        defaultOutputModes=K8sOrchestratorAgent.SUPPORTED_CONTENT_TYPES,
        capabilities=AgentCapabilities(streaming=True, pushNotifications=False),
        skills=[skill],
    )


@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for startup/shutdown."""
    await init_agent()
    yield
    await shutdown_agent()


def create_app():
    """Create and configure the A2A Starlette application."""
    agent_card = build_agent_card()

    httpx_client = httpx.AsyncClient()
    push_config_store = InMemoryPushNotificationConfigStore()
    push_sender = BasePushNotificationSender(
        httpx_client=httpx_client,
        config_store=push_config_store,
    )

    request_handler = DefaultRequestHandler(
        agent_executor=K8sOrchestratorAgentExecutor(),
        task_store=InMemoryTaskStore(),
        push_config_store=push_config_store,
        push_sender=push_sender,
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build(
        lifespan=lifespan,
    )
    return app


app = create_app()


if __name__ == "__main__":
    logger.info("Starting K8s Orchestrator Agent on %s:%s", HOST, PORT)
    uvicorn.run("main:app", host=HOST, port=PORT, log_level="info", reload=True)
