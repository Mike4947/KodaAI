import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.config import settings
from backend.db import _now, get_db
from backend.ollama.client import OllamaClient, parse_tool_calls
from backend.scanner.indexer import index_repo
from backend.scanner.tools import TOOL_DEFINITIONS, ToolExecutor

_active_scans: dict[str, dict] = {}
_cancel_flags: dict[str, bool] = {}
MAX_LOG_FIELD = 12000


def _clip(text: str, limit: int = MAX_LOG_FIELD) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} more characters truncated)"


def _log_activity(
    scan_id: str,
    activity: list[dict],
    findings: list[dict],
    status: str,
    entry: dict,
    *,
    persist: bool = True,
):
    activity.append(entry)
    _emit(scan_id, "activity", entry)
    if persist:
        _update_scan_db(scan_id, status, findings, None, activity)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _trim_messages(messages: list[dict], max_tokens: int = 16000) -> list[dict]:
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


def create_scan_record(repo_id: str, model: str, prompt_id: int | None) -> str:
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
    return scan_id


def cancel_scan(scan_id: str) -> bool:
    if scan_id in _cancel_flags:
        _cancel_flags[scan_id] = True
        return True
    scan = get_scan_from_db(scan_id)
    if scan and scan["status"] in ("pending", "indexing", "running"):
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


async def run_scan(scan_id: str, repo_id: str, model: str, prompt_body: str):
    from backend.github.repos import get_repo

    if scan_id not in _active_scans:
        _active_scans[scan_id] = {
            "events": [],
            "status": "pending",
            "findings": [],
            "summary": None,
            "activity": [],
        }
        _cancel_flags[scan_id] = False

    repo = get_repo(repo_id)
    if not repo:
        _emit(scan_id, "status", {"status": "error", "message": "Repository not found"})
        _update_scan_db(scan_id, "error", [], None, [])
        return

    repo_root = repo["local_path"]
    findings: list[dict] = []
    activity: list[dict] = []

    _emit(scan_id, "status", {"status": "indexing"})
    _update_scan_db(scan_id, "indexing", findings, None, activity)

    _log_activity(
        scan_id,
        activity,
        findings,
        "indexing",
        {
            "kind": "phase",
            "turn": 0,
            "action": "indexing",
            "message": f"Indexing repository {repo['full_name']}...",
        },
    )

    try:
        index = index_repo(repo_root)
    except Exception as e:
        _emit(scan_id, "status", {"status": "error", "message": f"Indexing failed: {e}"})
        _update_scan_db(scan_id, "error", findings, None, activity)
        return

    _log_activity(
        scan_id,
        activity,
        findings,
        "indexing",
        {
            "kind": "phase",
            "turn": 0,
            "action": "indexed",
            "message": f"Indexed {index.total_files} files ({index.total_lines} lines). Stacks: {', '.join(index.stacks) or 'unknown'}.",
        },
    )

    def on_finding(f: dict):
        _emit(scan_id, "finding", f)

    executor = ToolExecutor(repo_root, findings, on_finding=on_finding)
    client = OllamaClient(model)

    user_msg = (
        f"You are analyzing repository: {repo['full_name']}\n\n"
        f"## Repository structure\n{index.tree_summary()}\n\n"
        "Begin your analysis. Use tools to explore the codebase and report findings."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt_body},
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

        _log_activity(
            scan_id,
            activity,
            findings,
            "running",
            {
                "kind": "phase",
                "turn": turn + 1,
                "action": "model_request",
                "message": f"Turn {turn + 1}: Sending context to {model} and waiting for response...",
            },
        )

        try:
            response = await client.chat(messages, tools=TOOL_DEFINITIONS)
        except Exception as e:
            _emit(scan_id, "status", {"status": "error", "message": f"Ollama error: {e}"})
            _log_activity(
                scan_id,
                activity,
                findings,
                "error",
                {
                    "kind": "error",
                    "turn": turn + 1,
                    "action": "ollama_error",
                    "message": str(e),
                },
            )
            _update_scan_db(scan_id, "error", findings, None, activity)
            return

        msg = response.get("message", {})
        content = msg.get("content", "") or ""
        thinking = msg.get("thinking", "") or ""
        tool_calls = parse_tool_calls(msg)

        messages.append(msg)

        model_entry: dict[str, Any] = {
            "kind": "model",
            "turn": turn + 1,
            "action": "model_response",
            "content": _clip(content),
        }
        if thinking:
            model_entry["thinking"] = _clip(thinking)
        if tool_calls:
            model_entry["tool_calls"] = [
                {"name": tc["name"], "arguments": tc["arguments"]} for tc in tool_calls
            ]
        _log_activity(scan_id, activity, findings, "running", model_entry)

        if not tool_calls:
            if content:
                _log_activity(
                    scan_id,
                    activity,
                    findings,
                    "running",
                    {
                        "kind": "note",
                        "turn": turn + 1,
                        "action": "model_message",
                        "message": "Model responded without tool calls.",
                        "content": _clip(content),
                    },
                )
            if turn < settings.max_agent_turns - 1:
                nudge = "Continue analysis using tools (list_directory, read_file, search_files) or call finish_scan when done."
                messages.append({"role": "user", "content": nudge})
                _log_activity(
                    scan_id,
                    activity,
                    findings,
                    "running",
                    {
                        "kind": "system",
                        "turn": turn + 1,
                        "action": "nudge",
                        "message": nudge,
                    },
                )
                continue
            break

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]

            _log_activity(
                scan_id,
                activity,
                findings,
                "running",
                {
                    "kind": "tool_call",
                    "turn": turn + 1,
                    "action": name,
                    "args": args,
                },
            )

            result = executor.execute(name, args)

            _log_activity(
                scan_id,
                activity,
                findings,
                "running",
                {
                    "kind": "tool_result",
                    "turn": turn + 1,
                    "action": name,
                    "args": args,
                    "result": _clip(result),
                },
            )

            messages.append({"role": "tool", "content": result, "tool_name": name})

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


ONGOING_STATUSES = ("pending", "indexing", "running")
TERMINAL_STATUSES = ("completed", "error", "cancelled")


def list_scans(
    page: int = 1,
    per_page: int = 10,
    status_filter: str = "ongoing",
) -> dict:
    page = max(1, page)
    per_page = max(1, min(per_page, 50))
    offset = (page - 1) * per_page

    conditions = []
    params: list = []

    if status_filter == "ongoing":
        placeholders = ",".join("?" * len(ONGOING_STATUSES))
        conditions.append(f"s.status IN ({placeholders})")
        params.extend(ONGOING_STATUSES)
    elif status_filter != "all":
        conditions.append("s.status = ?")
        params.append(status_filter)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) as c FROM scans s {where}",
            params,
        ).fetchone()["c"]

        rows = conn.execute(
            f"""
            SELECT
                s.id, s.repo_id, s.model, s.status, s.summary,
                s.findings, s.created_at, s.updated_at, s.prompt_id,
                r.full_name as repo_full_name,
                r.owner as repo_owner,
                r.name as repo_name,
                p.name as prompt_name
            FROM scans s
            LEFT JOIN repos r ON s.repo_id = r.id
            LEFT JOIN system_prompts p ON s.prompt_id = p.id
            {where}
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, per_page, offset],
        ).fetchall()

    scans = []
    for row in rows:
        d = dict(row)
        findings = json.loads(d.pop("findings", "[]"))
        d["findings_count"] = len(findings)

        live = get_scan_events(d["id"])
        if live and live.get("status"):
            d["status"] = live["status"]
            d["findings_count"] = max(d["findings_count"], len(live.get("findings", [])))

        scans.append(d)

    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "scans": scans,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "ongoing_count": _count_ongoing(),
    }


def _count_ongoing() -> int:
    placeholders = ",".join("?" * len(ONGOING_STATUSES))
    with get_db() as conn:
        return conn.execute(
            f"SELECT COUNT(*) as c FROM scans WHERE status IN ({placeholders})",
            ONGOING_STATUSES,
        ).fetchone()["c"]


def findings_to_markdown(scan: dict) -> str:
    lines = [
        "# Code Analysis Report",
        "",
        f"**Repository scan ID:** {scan['id']}",
        f"**Status:** {scan['status']}",
        f"**Model:** {scan['model']}",
        "",
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
