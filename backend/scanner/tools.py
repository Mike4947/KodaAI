import json
import os
import re
from typing import Any

from backend.config import settings

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a path relative to repo root. Use '.' for root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read contents of a file. Optionally specify line range. Max 300 lines per call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path"},
                    "start_line": {"type": "integer", "description": "Start line (1-based)"},
                    "end_line": {"type": "integer", "description": "End line (1-based, inclusive)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for a regex pattern across repository text files. Returns up to 30 matches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search"},
                    "path_prefix": {"type": "string", "description": "Optional path prefix to limit search"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_finding",
            "description": "Report a bug, security issue, or code quality finding.",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                },
                "required": ["severity", "title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_scan",
            "description": "Complete the scan with an executive summary of overall code health.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Executive summary of findings and recommendations"},
                },
                "required": ["summary"],
            },
        },
    },
]


class ToolExecutor:
    def __init__(self, repo_root: str, findings: list[dict], on_finding=None):
        self.repo_root = os.path.abspath(repo_root)
        self.findings = findings
        self.on_finding = on_finding
        self.finished = False
        self.summary: str | None = None

    def _resolve_path(self, rel_path: str) -> str:
        rel_path = rel_path.strip().lstrip("/").replace("\\", "/")
        if rel_path in (".", ""):
            rel_path = ""
        full = os.path.abspath(os.path.join(self.repo_root, rel_path))
        if not full.startswith(self.repo_root):
            raise ValueError("Path traversal denied")
        return full

    def list_directory(self, path: str = ".") -> str:
        target = self._resolve_path(path)
        if not os.path.isdir(target):
            return f"Error: '{path}' is not a directory"

        entries = []
        try:
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                kind = "dir" if os.path.isdir(full) else "file"
                entries.append(f"{kind}: {name}")
        except OSError as e:
            return f"Error listing directory: {e}"

        if not entries:
            return "(empty directory)"
        return "\n".join(entries[:100])

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        target = self._resolve_path(path)
        if not os.path.isfile(target):
            return f"Error: '{path}' is not a file"

        try:
            size = os.path.getsize(target)
            if size > settings.max_file_size_bytes:
                return f"Error: file too large ({size} bytes, max {settings.max_file_size_bytes})"

            with open(target, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except OSError as e:
            return f"Error reading file: {e}"

        total = len(lines)
        start = max(1, start_line or 1)
        end = min(total, end_line or total)
        if end - start + 1 > settings.max_file_read_lines:
            end = start + settings.max_file_read_lines - 1

        selected = lines[start - 1 : end]
        numbered = [f"{i + start:4d}| {line.rstrip()}" for i, line in enumerate(selected)]
        header = f"File: {path} (lines {start}-{end} of {total})\n"
        return header + "\n".join(numbered)

    def search_files(self, pattern: str, path_prefix: str = "") -> str:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Invalid regex: {e}"

        prefix = path_prefix.strip().lstrip("/").replace("\\", "/") if path_prefix else ""
        matches = []
        max_matches = 30
        files_scanned = 0
        lines_scanned = 0

        for dirpath, _, filenames in os.walk(self.repo_root):
            rel_dir = os.path.relpath(dirpath, self.repo_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            for filename in filenames:
                if files_scanned >= settings.max_search_files:
                    matches.append(
                        f"(search stopped: scanned {settings.max_search_files} files — narrow path_prefix)"
                    )
                    return "\n".join(matches)

                rel_path = f"{rel_dir}/{filename}" if rel_dir else filename
                if prefix and not rel_path.startswith(prefix):
                    continue

                full = os.path.join(dirpath, filename)
                try:
                    if os.path.getsize(full) > settings.max_file_size_bytes:
                        continue
                    files_scanned += 1
                    with open(full, encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            lines_scanned += 1
                            if lines_scanned > settings.max_search_lines:
                                matches.append(
                                    f"(search stopped: scanned {settings.max_search_lines} lines — narrow path_prefix or pattern)"
                                )
                                return "\n".join(matches)
                            if regex.search(line):
                                matches.append(f"{rel_path}:{i}: {line.strip()[:120]}")
                                if len(matches) >= max_matches:
                                    return "\n".join(matches)
                except OSError:
                    continue

        return "\n".join(matches) if matches else "No matches found"

    def report_finding(self, severity: str, title: str, description: str, file: str = "", line: int | None = None) -> str:
        finding = {
            "severity": severity,
            "title": title,
            "description": description,
            "file": file,
            "line": line,
        }
        self.findings.append(finding)
        if self.on_finding:
            self.on_finding(finding)
        return f"Finding recorded: [{severity}] {title}"

    def finish_scan(self, summary: str) -> str:
        self.finished = True
        self.summary = summary
        return "Scan marked complete."

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        if name == "list_directory":
            return self.list_directory(arguments.get("path", "."))
        if name == "read_file":
            return self.read_file(
                arguments.get("path", ""),
                arguments.get("start_line"),
                arguments.get("end_line"),
            )
        if name == "search_files":
            return self.search_files(arguments.get("pattern", ""), arguments.get("path_prefix", ""))
        if name == "report_finding":
            return self.report_finding(
                arguments.get("severity", "info"),
                arguments.get("title", "Untitled"),
                arguments.get("description", ""),
                arguments.get("file", ""),
                arguments.get("line"),
            )
        if name == "finish_scan":
            return self.finish_scan(arguments.get("summary", ""))
        return f"Unknown tool: {name}"
