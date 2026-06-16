import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from backend.config import settings
from backend.db import _now, get_db
from backend.ollama.client import OllamaClient, parse_tool_calls
from backend.scanner.indexer import index_repo
from backend.scanner.tools import TOOL_DEFINITIONS, ToolExecutor

# In-memory scan state for SSE and cancellation
_active_scans: dict[str, dict] = {}
_cancel_flags: dict[str, bool] = {}


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _trim_messages(messages: list[dict], max_tokens: int = 16000) -> list[dict]:
    """Keep system + initial user, trim oldest tool results from the middle."""
    if len(messages) <= 3:
        return messages

    system = messages[0]
    initial = messages[1]
    rest = messages[2:]

    total = _estimate_tokens(json.dumps(messages))
    while total > max_tokens and len(rest) > 2:
        rest.pop(0)
        trimmed = [system, initial] + rest
        total = _estimate_tokens(json.dumps(trimmed))

    return [system, initial] + rest


def create_scan(repo_id: str, model: str, prompt_body: str, prompt_id: int | None) -> dict:
    scan_id = str(uuid.uuid4())
    now = _now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO scans (id, repo_id, model, prompt_id, status, activity_log, findings, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', '[]', '[]', ?, ?)
            """,
            (scan_id, repo_id, model, prompt_id, now, now),
        )

    _active_scans[scan_id] = {
        "events": [],
        "status": "pending",
        "findings": [],
        "summary": None,
        "activity": [],
    }
    _cancel_flags[scan_id] = False

    asyncio.create_task(_run_scan(scan_id, repo_id, model, prompt_body))
    return {"id": scan_id, "status": "pending"}


def cancel_scan(scan_id: str) -> bool:
    if scan_id in _cancel_flags:
        _cancel_flags[scan_id] = True
        return True
    return False


def get_scan_events(scan_id: str) -> dict | None:
    return _active_scans.get(scan_id)


def _emit(scan_id: str, event_type: str, data: dict):
    event = {"type": event_type, "data": data, "ts": datetime.now(timezone.utc).isoformat()}
    if scan_id in _active_scans:
        _active_scans[scan_id]["events"].append(event)
        if event_type == "finding":
            _active_scans[scan_id]["findings"].append(data)
        elif event_type == "activity":
            _active_scans[scan_id]["activity"].append(data)
        elif event_type == "status":
            _active_scans[scan_id]["status"] = data.get("status", "")


def _update_scan_db(scan_id: str, status: str, findings: list, summary: str | None, activity: list):
    now = _now()
    with get_db() as conn:
        conn.execute(
            "UPDATE scans SET status = ?, findings = ?, summary = ?, activity_log = ?, updated_at = ? WHERE id = ?",
            (status, json.dumps(findings), summary, json.dumps(activity), now, scan_id),
        )


async def _run_scan(scan_id: str, repo_id: str, model: str, prompt_body: str):
    from backend.github.repos import get_repo

    repo = get_repo(repo_id)
    if not repo:
        _emit(scan_id, "status", {"status": "error", "message": "Repository not found"})
        _update_scan_db(scan_id, "error", [], None, [])
        return

    repo_root = repo["local_path"]
    _emit(scan_id, "status", {"status": "indexing"})
    _update_scan_db(scan_id, "indexing", [], None, [])

    try:
        index = index_repo(repo_root)
    except Exception as e:
        _emit(scan_id, "status", {"status": "error", "message": f"Indexing failed: {e}"})
        _update_scan_db(scan_id, "error", [], None, [])
        return

    findings: list[dict] = []
    activity: list[dict] = []

    def on_finding(f: dict):
        _emit(scan_id, "finding", f)

    executor = ToolExecutor(repo_root, findings, on_finding=on_finding)
    client = OllamaClient(model)

    system_msg = prompt_body
    user_msg = (
        f"You are analyzing repository: {repo['full_name']}\n\n"
        f"## Repository structure\n{index.tree_summary()}\n\n"
        "Begin your analysis. Use tools to explore the codebase and report findings."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    _emit(scan_id, "status", {"status": "running"})
    _update_scan_db(scan_id, "running", findings, None, activity)

    for turn in range(settings.max_agent_turns):
        if _cancel_flags.get(scan_id):
            _emit(scan_id, "status", {"status": "cancelled"})
            _update_scan_db(scan_id, "cancelled", findings, "Scan cancelled by user.", activity)
            return

        messages = _trim_messages(messages)

        try:
            response = await client.chat(messages, tools=TOOL_DEFINITIONS)
        except Exception as e:
            _emit(scan_id, "status", {"status": "error", "message": f"Ollama error: {e}"})
            _update_scan_db(scan_id, "error", findings, None, activity)
            return

        msg = response.get("message", {})
        content = msg.get("content", "")
        tool_calls = parse_tool_calls(msg)

        messages.append(msg)

        act_entry = {"turn": turn + 1, "action": "model_response", "content": (content or "")[:500]}
        if tool_calls:
            act_entry["tool_calls"] = [tc["name"] for tc in tool_calls]
        activity.append(act_entry)
        _emit(scan_id, "activity", act_entry)

        if not tool_calls:
            # Nudge model to use tools or finish
            if turn < settings.max_agent_turns - 1:
                messages.append({
                    "role": "user",
                    "content": "Continue analysis using tools (list_directory, read_file, search_files) or call finish_scan when done.",
                })
                continue
            break

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]
            result = executor.execute(name, args)

            act = {"turn": turn + 1, "action": name, "args": args, "result_preview": result[:300]}
            activity.append(act)
            _emit(scan_id, "activity", act)

            messages.append({
                "role": "tool",
                "content": result,
            })

            if executor.finished:
                summary = executor.summary or "Scan completed."
                _emit(scan_id, "status", {"status": "completed", "summary": summary})
                _update_scan_db(scan_id, "completed", findings, summary, activity)
                return

    summary = executor.summary or f"Scan completed after {settings.max_agent_turns} turns. {len(findings)} findings recorded."
    _emit(scan_id, "status", {"status": "completed", "summary": summary})
    _update_scan_db(scan_id, "completed", findings, summary, activity)


def get_scan_from_db(scan_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["findings"] = json.loads(d["findings"])
        d["activity_log"] = json.loads(d["activity_log"])
        return d


def findings_to_markdown(scan: dict) -> str:
    lines = [
        f"# Code Analysis Report",
        f"",
        f"**Repository scan ID:** {scan['id']}",
        f"**Status:** {scan['status']}",
        f"**Model:** {scan['model']}",
        f"",
    ]
    if scan.get("summary"):
        lines.extend(["## Executive Summary", "", scan["summary"], ""])

    findings = scan.get("findings", [])
    if isinstance(findings, str):
        findings = json.loads(findings)

    lines.append(f"## Findings ({len(findings)})")
    lines.append("")

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.get("severity", "info"), 5))

    for i, f in enumerate(sorted_findings, 1):
        loc = ""
        if f.get("file"):
            loc = f["file"]
            if f.get("line"):
                loc += f":{f['line']}"
        lines.append(f"### {i}. [{f.get('severity', 'info').upper()}] {f.get('title', 'Untitled')}")
        if loc:
            lines.append(f"**Location:** `{loc}`")
        lines.append("")
        lines.append(f.get("description", ""))
        lines.append("")

    return "\n".join(lines)
