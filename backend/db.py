import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.config import settings

DB_PATH = os.path.join(settings.data_dir, "koda.db")

DEFAULT_PROMPT = """You are an expert code security and quality auditor analyzing a GitHub repository.

Your job is to find bugs, security vulnerabilities, and code quality issues as specified in this prompt.

## Methodology
- Use the provided tools to explore the codebase iteratively. NEVER guess file contents.
- Start with the repository structure summary, then prioritize high-risk areas:
  authentication/authorization, input validation, SQL/database queries, file I/O, API endpoints,
  cryptography, dependency configs, environment variables, and error handling.
- Read files in focused chunks. Use search_files to locate patterns like secrets, eval, exec, SQL strings.
- Report each issue via report_finding with accurate file paths and line numbers when possible.
- When you have covered the important areas, call finish_scan with an executive summary.

## What to look for
### Bugs
- Null/undefined dereferences, off-by-one errors, race conditions
- Missing error handling, swallowed exceptions, resource leaks
- Logic errors in conditionals and loops

### Security (OWASP-style)
- Injection (SQL, command, XSS, template)
- Hardcoded secrets, API keys, passwords in source
- Weak authentication/authorization, missing access controls
- SSRF, path traversal, insecure deserialization
- Insecure crypto, weak randomness
- Misconfigured CORS, headers, cookies

### Code quality
- Dead code, duplicated logic
- Dangerous dependency versions (if visible in lockfiles)
- Missing input validation at trust boundaries

## Severity levels
- critical: exploitable vulnerability or data loss risk
- high: serious bug or security flaw requiring prompt fix
- medium: notable issue with moderate impact
- low: minor issue or best-practice deviation
- info: observation, not necessarily a defect
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    os.makedirs(settings.data_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS system_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                body TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS github_tokens (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                encrypted_token TEXT NOT NULL,
                username TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repos (
                id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                full_name TEXT NOT NULL,
                clone_url TEXT NOT NULL,
                local_path TEXT NOT NULL,
                is_private INTEGER NOT NULL DEFAULT 0,
                cloned_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                repo_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_id INTEGER,
                status TEXT NOT NULL,
                summary TEXT,
                activity_log TEXT NOT NULL DEFAULT '[]',
                findings TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (repo_id) REFERENCES repos(id),
                FOREIGN KEY (prompt_id) REFERENCES system_prompts(id)
            );
            """
        )
        row = conn.execute("SELECT COUNT(*) as c FROM system_prompts").fetchone()
        if row["c"] == 0:
            now = _now()
            conn.execute(
                "INSERT INTO system_prompts (name, body, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                ("Default Security Audit", DEFAULT_PROMPT, now, now),
            )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
