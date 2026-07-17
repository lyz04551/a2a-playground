import json
import os
from datetime import datetime
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AGENTS_FILE = os.path.join(DATA_DIR, "agents.json")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_json(path: str) -> list:
    _ensure_data_dir()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _write_json(path: str, data: list):
    _ensure_data_dir()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# --- Agents ---

def list_agents() -> list[dict]:
    return _read_json(AGENTS_FILE)


def get_agent(agent_id: str) -> Optional[dict]:
    agents = list_agents()
    for a in agents:
        if a["id"] == agent_id:
            return a
    return None


def add_agent(agent: dict) -> dict:
    agents = list_agents()
    # check duplicate by url
    for a in agents:
        if a["url"] == agent["url"]:
            return a
    agents.append(agent)
    _write_json(AGENTS_FILE, agents)
    return agent


def delete_agent(agent_id: str) -> bool:
    agents = list_agents()
    new_agents = [a for a in agents if a["id"] != agent_id]
    if len(new_agents) == len(agents):
        return False
    _write_json(AGENTS_FILE, new_agents)
    return True


# --- Conversations ---

def list_conversations() -> list[dict]:
    return _read_json(CONVERSATIONS_FILE)


def list_conversations_by_agent(agent_id: str) -> list[dict]:
    convs = list_conversations()
    return [c for c in convs if c["agent_id"] == agent_id]


def get_conversation(conversation_id: str) -> Optional[dict]:
    convs = list_conversations()
    for c in convs:
        if c["id"] == conversation_id:
            return c
    return None


def create_conversation(conversation: dict) -> dict:
    convs = list_conversations()
    convs.append(conversation)
    _write_json(CONVERSATIONS_FILE, convs)
    return conversation


def update_conversation(conversation_id: str, updates: dict) -> Optional[dict]:
    convs = list_conversations()
    for i, c in enumerate(convs):
        if c["id"] == conversation_id:
            convs[i].update(updates)
            convs[i]["updated_at"] = datetime.now().isoformat()
            _write_json(CONVERSATIONS_FILE, convs)
            return convs[i]
    return None


def delete_conversation(conversation_id: str) -> bool:
    convs = list_conversations()
    new_convs = [c for c in convs if c["id"] != conversation_id]
    if len(new_convs) == len(convs):
        return False
    _write_json(CONVERSATIONS_FILE, new_convs)
    # also delete associated messages and events
    msgs = list_messages()
    msgs = [m for m in msgs if m["conversation_id"] != conversation_id]
    _write_json(MESSAGES_FILE, msgs)
    evts = list_events()
    evts = [e for e in evts if e["conversation_id"] != conversation_id]
    _write_json(EVENTS_FILE, evts)
    return True


# --- Messages ---

def list_messages(conversation_id: Optional[str] = None) -> list[dict]:
    all_msgs = _read_json(MESSAGES_FILE)
    if conversation_id:
        return [m for m in all_msgs if m["conversation_id"] == conversation_id]
    return all_msgs


def add_message(message: dict) -> dict:
    msgs = list_messages()
    msgs.append(message)
    _write_json(MESSAGES_FILE, msgs)
    # update conversation message count and last time
    update_conversation(message["conversation_id"], {
        "message_count": len([m for m in msgs if m["conversation_id"] == message["conversation_id"]]),
    })
    return message


def get_message(message_id: str) -> Optional[dict]:
    msgs = list_messages()
    for m in msgs:
        if m["id"] == message_id:
            return m
    return None


# --- Events ---

def list_events(conversation_id: Optional[str] = None) -> list[dict]:
    all_events = _read_json(EVENTS_FILE)
    if conversation_id:
        return [e for e in all_events if e["conversation_id"] == conversation_id]
    return sorted(all_events, key=lambda x: x.get("timestamp", ""))


def add_event(event: dict) -> dict:
    events = list_events()
    events.append(event)
    _write_json(EVENTS_FILE, events)
    return event


def get_events_for_conversation(conversation_id: str) -> list[dict]:
    return list_events(conversation_id)
