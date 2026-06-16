from backend.db import _now, get_db, row_to_dict


def list_prompts() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts ORDER BY id"
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_prompt(prompt_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        return row_to_dict(row)


def get_active_prompt() -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        if row:
            return row_to_dict(row)
        row = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts ORDER BY id LIMIT 1"
        ).fetchone()
        return row_to_dict(row)


def create_prompt(name: str, body: str, set_active: bool = False) -> dict:
    now = _now()
    with get_db() as conn:
        if set_active:
            conn.execute("UPDATE system_prompts SET is_active = 0")
        cur = conn.execute(
            "INSERT INTO system_prompts (name, body, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (name, body, 1 if set_active else 0, now, now),
        )
        prompt_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        return row_to_dict(row)


def update_prompt(prompt_id: int, name: str | None = None, body: str | None = None, set_active: bool | None = None) -> dict | None:
    existing = get_prompt(prompt_id)
    if not existing:
        return None

    now = _now()
    new_name = name if name is not None else existing["name"]
    new_body = body if body is not None else existing["body"]

    with get_db() as conn:
        if set_active:
            conn.execute("UPDATE system_prompts SET is_active = 0")
            conn.execute(
                "UPDATE system_prompts SET name = ?, body = ?, is_active = 1, updated_at = ? WHERE id = ?",
                (new_name, new_body, now, prompt_id),
            )
        else:
            active = existing["is_active"] if set_active is None else (1 if set_active else 0)
            conn.execute(
                "UPDATE system_prompts SET name = ?, body = ?, is_active = ?, updated_at = ? WHERE id = ?",
                (new_name, new_body, active, now, prompt_id),
            )
        row = conn.execute(
            "SELECT id, name, body, is_active, created_at, updated_at FROM system_prompts WHERE id = ?",
            (prompt_id,),
        ).fetchone()
        return row_to_dict(row)


def delete_prompt(prompt_id: int) -> bool:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM system_prompts WHERE id = ?", (prompt_id,)).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM system_prompts WHERE id = ?", (prompt_id,))
        remaining = conn.execute("SELECT COUNT(*) as c FROM system_prompts").fetchone()["c"]
        if remaining == 0:
            from backend.db import DEFAULT_PROMPT

            now = _now()
            conn.execute(
                "INSERT INTO system_prompts (name, body, is_active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                ("Default Security Audit", DEFAULT_PROMPT, now, now),
            )
        else:
            active = conn.execute("SELECT COUNT(*) as c FROM system_prompts WHERE is_active = 1").fetchone()["c"]
            if active == 0:
                conn.execute(
                    "UPDATE system_prompts SET is_active = 1 WHERE id = (SELECT MIN(id) FROM system_prompts)"
                )
        return True
