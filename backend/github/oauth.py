import secrets
from urllib.parse import urlencode

import httpx

from backend.config import settings
from backend.github.repos import clear_github_token, get_github_token, get_github_username, store_github_token

# In-memory OAuth state store (single-user local app)
_oauth_states: dict[str, bool] = {}


def is_github_configured() -> bool:
    return bool(settings.github_client_id and settings.github_client_secret)


def get_github_status() -> dict:
    token = get_github_token()
    return {
        "configured": is_github_configured(),
        "connected": token is not None,
        "username": get_github_username(),
    }


def get_login_url() -> str:
    if not is_github_configured():
        raise ValueError("GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in .env")
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = True
    params = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": f"{settings.backend_url}/api/github/callback",
            "scope": "repo read:user",
            "state": state,
        }
    )
    return f"https://github.com/login/oauth/authorize?{params}"


async def handle_callback(code: str, state: str) -> str:
    if state not in _oauth_states:
        raise ValueError("Invalid OAuth state")
    del _oauth_states[state]

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(token_data.get("error_description", "Failed to get access token"))

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        user_resp.raise_for_status()
        username = user_resp.json().get("login")

    store_github_token(access_token, username)
    return username or "user"


async def list_user_repos(page: int = 1, per_page: int = 30, search: str = "") -> list[dict]:
    token = get_github_token()
    if not token:
        raise ValueError("Not connected to GitHub")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            params={"page": page, "per_page": per_page, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
        )
        resp.raise_for_status()
        repos = resp.json()

    results = []
    search_lower = search.lower()
    for r in repos:
        full_name = r.get("full_name", "")
        if search and search_lower not in full_name.lower() and search_lower not in (r.get("description") or "").lower():
            continue
        results.append(
            {
                "id": r["id"],
                "full_name": full_name,
                "owner": r["owner"]["login"],
                "name": r["name"],
                "private": r["private"],
                "description": r.get("description"),
                "html_url": r.get("html_url"),
            }
        )
    return results


def disconnect_github():
    clear_github_token()
