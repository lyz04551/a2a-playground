from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
import uuid


class AgentRegister(BaseModel):
    agentAddress: str


class AgentCard(BaseModel):
    name: str = "Unknown"
    description: str = ""
    url: str = ""
    provider: Optional[dict] = None
    version: str = "1.0"
    capabilities: Optional[dict] = None
    defaultInputModes: list[str] = ["text"]
    defaultOutputModes: list[str] = ["text"]
    skills: list[dict] = []


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    url: str
    description: str = ""
    provider: Optional[dict] = None
    capabilities: Optional[dict] = None
    inputModes: list[str] = ["text"]
    outputModes: list[str] = ["text"]
    skills: list[dict] = []
    version: str = ""
    protocolVersion: str = ""
    preferredTransport: str = ""
    documentationUrl: str = ""
    createdAt: str = Field(default_factory=lambda: datetime.now().isoformat())


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    agent_id: str
    title: str = "New Chat"
    type: str = "single"  # "single" or "multi"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0


class Message(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    conversation_id: str
    role: str  # "user" or "agent"
    content: str
    parts: list[Any] = []
    task_id: Optional[str] = None
    metadata: Optional[dict] = None  # For routing agent name, tool calls, etc.
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class TaskEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    conversation_id: str
    task_id: str
    event_type: str  # "tool_call", "tool_result", "routing", "status_update", "artifact_update", "error"
    state: str = ""
    content: str = ""
    metadata: Optional[dict] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class SendMessageRequest(BaseModel):
    conversation_id: str
    content: str


class FetchCardResponse(BaseModel):
    success: bool
    card: Optional[AgentCard] = None
    error: str = ""


class ApiResponse(BaseModel):
    success: bool = True
    message: str = ""
    result: Any = None
    error: str = ""
