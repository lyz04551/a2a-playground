"""Build an evidence ledger from actual MCP calls, independent of model prose."""

from __future__ import annotations

import json
from typing import Any


def _kind(tool: str, arguments: dict[str, Any]) -> str:
    if arguments.get("kind"):
        return str(arguments["kind"])
    suffix = tool.rsplit("_", 1)[-1]
    if suffix.endswith("s"):
        suffix = suffix[:-1]
    return suffix.capitalize() if suffix and suffix != tool else ""


def _resource_id(kind: str, name: str, namespace: str = "") -> str:
    if not kind or not name:
        return ""
    return f"{kind}/{namespace}/{name}" if namespace else f"{kind}/{name}"


def _result_state(value: str) -> str:
    if value.lstrip().startswith(("工具执行失败：", "Error:", "MCP dependency unavailable:")):
        return "error"
    if value.lstrip().startswith("工具调用预算已达到"):
        return "skipped"
    return "empty" if not value or value.strip() in {"null", '""'} else "returned"


def _listed_resources(kind: str, namespace: str, value: str) -> list[str] | None:
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        return None
    targets: list[str] = []
    for item in parsed:
        if isinstance(item, dict):
            name = item.get("name") or (item.get("metadata") or {}).get("name")
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            item_namespace = item.get("namespace") or metadata.get("namespace") or namespace
            item_kind = str(item.get("kind") or kind)
        elif isinstance(item, str):
            name, item_namespace, item_kind = item, namespace, kind
        else:
            return None
        target = _resource_id(item_kind, str(name or ""), str(item_namespace or ""))
        if not target:
            return None
        targets.append(target)
    return targets


def build_evidence_ledger(calls: dict[str, dict], results: dict[str, str]) -> tuple[list[dict], dict]:
    """Return tool evidence and conservative coverage using only observed calls.

    List responses enumerate expected objects; a successful named read verifies an
    object. A list of names alone never counts as inspecting each object.
    """
    evidence: list[dict] = []
    expected: list[str] = []
    inspected: list[str] = []
    enumeration_seen = False
    enumeration_valid = True
    for call_id, result_value in results.items():
        call = calls.get(call_id) or {}
        tool = str(call.get("tool") or "")
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        result = str(result_value)
        state = _result_state(result)
        kind = _kind(tool, arguments)
        namespace = str(arguments.get("namespace") or "")
        name = str(arguments.get("name") or "")
        if state in {"returned", "empty"}:
            try:
                payload = json.loads(result)
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                kind = str(payload.get("kind") or kind)
                namespace = str(metadata.get("namespace") or payload.get("namespace") or namespace)
                name = str(metadata.get("name") or payload.get("name") or name)
        target = _resource_id(kind, name, namespace)
        resource_ids = [target] if target else []
        if tool.startswith("list_") and kind:
            enumeration_seen = True
            listed = _listed_resources(kind, namespace, result) if state in {"returned", "empty"} else None
            if listed is None:
                enumeration_valid = False
            else:
                resource_ids = listed
                expected.extend(listed)
        elif target:
            expected.append(target)
            if state in {"returned", "empty"} and tool.startswith(("get_", "describe_")):
                inspected.append(target)
        evidence.append({
            "call_id": call_id,
            "tool": tool,
            "resource_ids": resource_ids,
            "arguments": arguments,
            "called_at": call.get("called_at", ""),
            "result_state": state,
            "result": result,
        })
    coverage = {
        "scope": "observed MCP resources",
        "expected_targets": list(dict.fromkeys(expected)),
        "inspected_targets": list(dict.fromkeys(inspected)),
        "enumeration_complete": enumeration_seen and enumeration_valid,
        "evidence_call_ids": [item["call_id"] for item in evidence],
    }
    return evidence, coverage


def build_assessment(evidence: list[dict], coverage: dict) -> dict:
    """Classify runtime observations without promoting model prose to fact."""
    facts = [
        {
            "tool": item["tool"],
            "resource_ids": item["resource_ids"],
            "evidence_call_ids": [item["call_id"]],
            "result_state": item["result_state"],
        }
        for item in evidence
        if item["result_state"] in {"returned", "empty"}
    ]
    unknowns = [
        {"resource_id": target, "reason": "not inspected"}
        for target in coverage["expected_targets"]
        if target not in coverage["inspected_targets"]
    ]
    unknowns.extend(
        {"resource_id": target, "reason": item["result_state"]}
        for item in evidence if item["result_state"] in {"error", "skipped"}
        for target in item["resource_ids"] if target not in coverage["expected_targets"]
    )
    return {"facts": facts, "inferences": [], "unknowns": unknowns}
