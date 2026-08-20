from __future__ import annotations

from fastapi import APIRouter

from backend.events.feed import build_event_feed
from backend.models import ApiResponse, Conversation


def _page(data: dict) -> tuple[int, int] | None:
    if "page" not in data and "page_size" not in data and "pageSize" not in data:
        return None
    page = max(1, int(data.get("page", 1)))
    size = min(100, max(1, int(data.get("page_size", data.get("pageSize", 20)))))
    return page, size


def _paged(items, page: int, size: int, total: int) -> dict:
    return {"items": items, "page": page, "page_size": size, "total": total, "has_more": page * size < total}


def create_router(repository) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/conversation/create")
    async def create_conversation(data: dict):
        conversation = Conversation(
            agent_id=data.get("agentId", ""),
            title=data.get("title", "New Chat"),
            type=data.get("type", "single"),
        )
        return ApiResponse(
            result=repository.create_conversation(conversation.model_dump())
        )

    @router.post("/conversation/list")
    async def list_conversations(data: dict):
        agent_id = data.get("agentId", "")
        conversation_type = data.get("type", "")
        pagination = _page(data)
        limit, offset = (pagination[1], (pagination[0] - 1) * pagination[1]) if pagination else (None, 0)
        conversations = (
            repository.list_conversations_by_agent(agent_id, limit=limit, offset=offset)
            if agent_id else repository.list_conversations(limit=limit, offset=offset)
        )
        if conversation_type:
            conversations = [
                item for item in conversations
                if item.get("type", "single") == conversation_type
            ]
        conversations.sort(
            key=lambda item: item.get("updated_at", ""), reverse=True
        )
        if pagination:
            total = repository.count_conversations(agent_id or None)
            return ApiResponse(result=_paged(conversations, *pagination, total))
        return ApiResponse(result=conversations)

    @router.post("/conversation/get")
    async def get_conversation(data: dict):
        conversation_id = data.get("conversationId", "")
        conversation = repository.get_conversation(conversation_id)
        if not conversation:
            return ApiResponse(
                success=False, error="Conversation not found"
            )
        messages = repository.list_messages(conversation_id)
        messages.sort(key=lambda item: item.get("created_at", ""))
        return ApiResponse(result={**conversation, "messages": messages})

    @router.post("/conversation/update")
    async def update_conversation(data: dict):
        updates = {}
        if data.get("title"):
            updates["title"] = data["title"]
        updated = repository.update_conversation(
            data.get("conversationId", ""), updates
        )
        if not updated:
            return ApiResponse(
                success=False, error="Conversation not found"
            )
        return ApiResponse(result=updated)

    @router.post("/conversation/delete")
    async def delete_conversation(data: dict):
        if not repository.delete_conversation(
            data.get("conversationId", "")
        ):
            return ApiResponse(
                success=False, error="Conversation not found"
            )
        return ApiResponse()

    @router.post("/message/list")
    async def list_messages(data: dict):
        return ApiResponse(result=repository.list_messages(
            data.get("conversationId", "")
        ))

    @router.post("/events/list")
    async def list_events(data: dict | None = None):
        data = data or {}
        pagination = _page(data)
        limit, offset = (pagination[1], (pagination[0] - 1) * pagination[1]) if pagination else (None, 0)
        items = build_event_feed(
            repository.list_events(limit=limit, offset=offset),
            repository.list_conversations(),
            repository.list_agents(),
        )
        return ApiResponse(result=_paged(items, *pagination, repository.count_events()) if pagination else items)

    @router.post("/events/query")
    async def query_events(data: dict):
        return ApiResponse(result=build_event_feed(
            repository.get_events_for_conversation(
                data.get("conversationId", "")
            ),
            repository.list_conversations(),
            repository.list_agents(),
        ))

    return router
