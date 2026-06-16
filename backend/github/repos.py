import base64
import os
import re
import uuid

import git

from backend.config import settings
from backend.db import _now, get_db, row_to_dict


GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:#.*)?(?:\?.*)?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    url = url.strip()
    m = GITHUB_URL_RE.match(url)
    if not m:
        raise ValueError("Invalid GitHub repository URL. Expected: https://github.com/owner/repo")
    owner, name = m.group(1), m.group(2)
    if name.endswith(".git"):
        name = name[:-4]
    return owner, name


def _get_fernet():
    from cryptography.fernet import Fernet

    key = settings.fernet_key
    if not key:
        raise ValueError(
            "FERNET_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" '
            "and add it to .env before using GitHub authentication."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def store_github_token(token: str, username: str | None = None):
    f = _get_fernet()
    encrypted = f.encrypt(token.encode()).decode()
    now = _now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO github_tokens (id, encrypted_token, username, updated_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET encrypted_token = excluded.encrypted_token,
                username = excluded.username, updated_at = excluded.updated_at
            """,
            (encrypted, username, now),
        )


def get_github_token() -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT encrypted_token FROM github_tokens WHERE id = 1").fetchone()
        if not row:
            return None
    try:
        f = _get_fernet()
        return f.decrypt(row["encrypted_token"].encode()).decode()
    except ValueError:
        raise
    except Exception:
        return None


def get_github_username() -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT username FROM github_tokens WHERE id = 1").fetchone()
        return row["username"] if row else None


def clear_github_token():
    with get_db() as conn:
        conn.execute("DELETE FROM github_tokens WHERE id = 1")


def _clone_repository(owner: str, name: str, local_path: str, token: str | None) -> None:
    clone_url = f"https://github.com/{owner}/{name}.git"
    if not token:
        git.Repo.clone_from(clone_url, local_path, depth=1)
        return

    auth_header = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraHeader"
    env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {auth_header}"
    git.Repo.clone_from(clone_url, local_path, depth=1, env=env)


def clone_repo(owner: str, name: str, token: str | None = None, is_private: bool = False) -> dict:
    os.makedirs(settings.repos_dir, exist_ok=True)
    repo_id = str(uuid.uuid4())
    local_path = os.path.join(settings.repos_dir, repo_id)
    full_name = f"{owner}/{name}"
    clone_url = f"https://github.com/{owner}/{name}.git"

    _clone_repository(owner, name, local_path, token)

    now = _now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO repos (id, owner, name, full_name, clone_url, local_path, is_private, cloned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (repo_id, owner, name, full_name, clone_url, local_path, 1 if is_private else 0, now),
        )

    return get_repo(repo_id)


def clone_from_url(url: str) -> dict:
    owner, name = parse_github_url(url)
    return clone_repo(owner, name)


def get_repo(repo_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM repos WHERE id = ?", (repo_id,)).fetchone()
        return row_to_dict(row)


def list_repos() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT id, owner, name, full_name, is_private, cloned_at FROM repos ORDER BY cloned_at DESC").fetchall()
        return [row_to_dict(r) for r in rows]
