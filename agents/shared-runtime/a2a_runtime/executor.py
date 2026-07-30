from __future__ import annotations

import json

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import InternalError, Part, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from .streaming import RuntimeEventType


class RuntimeAgentExecutor(AgentExecutor):
    def __init__(self, agent):
        self.agent = agent

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        query = context.get_user_input()
        task = context.current_task
        if task is None:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        try:
            async for item in self.agent.stream(query, task.context_id):
                if item.require_user_input:
                    if item.artifact_name:
                        await self._add_artifact(updater, item)
                    message = new_agent_text_message(
                        item.content, task.context_id, task.id
                    )
                    message.metadata = {
                        "event_type": item.type.value,
                        "data": item.data,
                    }
                    await updater.update_status(
                        TaskState.input_required, message, final=True
                    )
                    return
                if item.is_task_complete:
                    if item.type is RuntimeEventType.ERROR:
                        message = new_agent_text_message(
                            item.content, task.context_id, task.id
                        )
                        await updater.update_status(
                            TaskState.failed, message, final=True
                        )
                        return
                    await self._add_artifact(updater, item)
                    await updater.complete()
                    return
                message = new_agent_text_message(
                    item.content, task.context_id, task.id
                )
                message.metadata = {
                    "event_type": item.type.value,
                    "data": item.data,
                }
                await updater.update_status(TaskState.working, message)
        except Exception as exc:
            raise ServerError(error=InternalError()) from exc

    @staticmethod
    async def _add_artifact(updater: TaskUpdater, item) -> None:
        text = json.dumps(
            item.data or {"text": item.content},
            ensure_ascii=False,
        )
        await updater.add_artifact(
            [Part(root=TextPart(text=text))],
            name=item.artifact_name or "result",
        )

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        task = context.current_task
        if task is None:
            return
        await TaskUpdater(
            event_queue, task.id, task.context_id
        ).cancel()
