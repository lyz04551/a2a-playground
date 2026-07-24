"""K8s Orchestrator AgentExecutor — A2A AgentExecutor wrapping the LangGraph agent."""

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    InvalidParamsError,
    Message,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from agent import get_agent

logger = logging.getLogger(__name__)


class K8sOrchestratorAgentExecutor(AgentExecutor):
    """A2A AgentExecutor for the K8s Orchestrator LangGraph agent."""

    def __init__(self):
        self.agent = get_agent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute the K8s orchestration agent and stream results via A2A."""
        logger.info("Executing K8s orchestrator agent")

        error = self._validate_request(context)
        if error:
            raise ServerError(error=InvalidParamsError())

        query = context.get_user_input()
        task = context.current_task

        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]

                if not is_task_complete and not require_user_input:
                    # Streaming intermediate progress
                    msg = new_agent_text_message(
                        item["content"],
                        task.context_id,
                        task.id,
                    )
                    msg.metadata = {"event_type": item.get("type", "text")}
                    await updater.update_status(
                        TaskState.working,
                        msg,
                    )
                elif require_user_input:
                    # Agent needs more input from the user
                    msg = new_agent_text_message(
                        item["content"],
                        task.context_id,
                        task.id,
                    )
                    msg.metadata = {"event_type": item.get("type", "text")}
                    await updater.update_status(
                        TaskState.input_required,
                        msg,
                        final=True,
                    )
                    break
                else:
                    # Task complete — add artifact and mark done
                    await updater.add_artifact(
                        [Part(root=TextPart(text=item["content"]))],
                        name="k8s_orchestration_result",
                    )
                    await updater.complete()
                    break

        except Exception as e:
            logger.exception("Error during K8s orchestrator agent execution")
            raise ServerError(error=InternalError()) from e

    def _validate_request(self, context: RequestContext) -> bool:
        """Validate the incoming request. Returns False if valid."""
        return False

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Cancel the agent execution (not supported)."""
        raise ServerError(error=UnsupportedOperationError())
