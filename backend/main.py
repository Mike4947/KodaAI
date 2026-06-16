import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.config import settings
from backend.db import init_db
from backend.github.oauth import (
    disconnect_github,
    get_github_status,
    get_login_url,
    handle_callback,
    list_user_repos,
)
from backend.github.repos import clone_from_url, clone_repo, get_github_token, get_repo, list_repos
from backend.ollama.models import check_health, list_gemma_models
from backend.prompts.store import (
    create_prompt,
    delete_prompt,
    get_active_prompt,
    get_prompt,
    list_prompts,
    update_prompt,
)
from backend.scanner.agent import (
    cancel_scan,
    create_scan_record,
    findings_to_markdown,
    get_scan_events,
    get_scan_from_db,
    list_scans,
    run_scan,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="KodaAI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request models ---

class CloneUrlRequest(BaseModel):
    url: str


class CloneRepoRequest(BaseModel):
    owner: str
    name: str
    private: bool = False


class PromptCreate(BaseModel):
    name: str
    body: str
    set_active: bool = False


class PromptUpdate(BaseModel):
    name: str | None = None
    body: str | None = None
    set_active: bool | None = None


class ScanRequest(BaseModel):
    repo_id: str
    model: str
    prompt_id: int | None = None


# --- Ollama ---

@app.get("/api/ollama/health")
async def ollama_health():
    return await check_health()


@app.get("/api/ollama/models")
async def ollama_models():
    health = await check_health()
    models = await list_gemma_models()
    return {"health": health, "models": models}


# --- GitHub OAuth ---

@app.get("/api/github/status")
async def github_status():
    return get_github_status()


@app.get("/api/github/login")
async def github_login():
    try:
        url = get_login_url()
        return {"url": url}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/github/callback")
async def github_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"{settings.frontend_url}?github_error={error}")
    try:
        username = await handle_callback(code, state)
        return RedirectResponse(f"{settings.frontend_url}?github_connected={username}")
    except Exception as e:
        return RedirectResponse(f"{settings.frontend_url}?github_error={str(e)}")


@app.get("/api/github/repos")
async def github_repos(page: int = 1, per_page: int = 30, search: str = ""):
    try:
        repos = await list_user_repos(page, per_page, search)
        return {"repos": repos}
    except ValueError as e:
        raise HTTPException(401, str(e))


@app.post("/api/github/disconnect")
async def github_disconnect():
    disconnect_github()
    return {"ok": True}


# --- Repos ---

@app.post("/api/repos/clone")
async def repos_clone_url(req: CloneUrlRequest):
    try:
        repo = clone_from_url(req.url)
        return repo
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Clone failed: {e}")


@app.post("/api/repos/clone-selected")
async def repos_clone_selected(req: CloneRepoRequest):
    token = get_github_token() if req.private else None
    if req.private and not token:
        raise HTTPException(401, "GitHub authentication required for private repos")
    try:
        repo = clone_repo(req.owner, req.name, token=token, is_private=req.private)
        return repo
    except Exception as e:
        raise HTTPException(500, f"Clone failed: {e}")


@app.get("/api/repos")
async def repos_list():
    return {"repos": list_repos()}


@app.get("/api/repos/{repo_id}")
async def repos_get(repo_id: str):
    repo = get_repo(repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")
    return repo


# --- Prompts ---

@app.get("/api/prompts")
async def prompts_list():
    return {"prompts": list_prompts(), "active": get_active_prompt()}


@app.get("/api/prompts/{prompt_id}")
async def prompts_get(prompt_id: int):
    p = get_prompt(prompt_id)
    if not p:
        raise HTTPException(404, "Prompt not found")
    return p


@app.post("/api/prompts")
async def prompts_create(req: PromptCreate):
    return create_prompt(req.name, req.body, req.set_active)


@app.put("/api/prompts/{prompt_id}")
async def prompts_update(prompt_id: int, req: PromptUpdate):
    p = update_prompt(prompt_id, req.name, req.body, req.set_active)
    if not p:
        raise HTTPException(404, "Prompt not found")
    return p


@app.delete("/api/prompts/{prompt_id}")
async def prompts_delete(prompt_id: int):
    if not delete_prompt(prompt_id):
        raise HTTPException(404, "Prompt not found")
    return {"ok": True}


# --- Scans ---

@app.get("/api/scans")
async def scans_list(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    status: str = Query("ongoing", description="ongoing, all, or a specific status"),
):
    return list_scans(page=page, per_page=per_page, status_filter=status)


@app.post("/api/scan")
async def scan_start(req: ScanRequest, background_tasks: BackgroundTasks):
    repo = get_repo(req.repo_id)
    if not repo:
        raise HTTPException(404, "Repository not found")

    if req.prompt_id:
        prompt = get_prompt(req.prompt_id)
    else:
        prompt = get_active_prompt()

    if not prompt:
        raise HTTPException(400, "No system prompt available")

    scan_id = create_scan_record(req.repo_id, req.model, prompt["id"])
    background_tasks.add_task(run_scan, scan_id, req.repo_id, req.model, prompt["body"])
    return {"id": scan_id, "status": "pending"}


@app.post("/api/scan/{scan_id}/cancel")
async def scan_cancel(scan_id: str):
    if cancel_scan(scan_id):
        return {"ok": True}
    raise HTTPException(404, "Scan not found")


@app.get("/api/scan/{scan_id}")
async def scan_get(scan_id: str):
    scan = get_scan_from_db(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return scan


@app.get("/api/scan/{scan_id}/report")
async def scan_report(scan_id: str, format: str = Query("json")):
    scan = get_scan_from_db(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    if format == "markdown":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(findings_to_markdown(scan), media_type="text/markdown")
    return scan


@app.get("/api/scan/{scan_id}/stream")
async def scan_stream(scan_id: str):
    scan = get_scan_from_db(scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")

    async def event_generator():
        db_scan = get_scan_from_db(scan_id)
        if db_scan:
            yield f"data: {json.dumps({'type': 'snapshot', 'data': {'status': db_scan['status'], 'summary': db_scan.get('summary'), 'activity_log': db_scan['activity_log'], 'findings': db_scan['findings']}})}\n\n"

        state = get_scan_events(scan_id)
        sent = len(state.get("events", [])) if state else 0

        while True:
            state = get_scan_events(scan_id)
            if state:
                events = state.get("events", [])
                while sent < len(events):
                    yield f"data: {json.dumps(events[sent])}\n\n"
                    sent += 1
                status = state.get("status", "")
                if status in ("completed", "error", "cancelled"):
                    yield f"data: {json.dumps({'type': 'done', 'data': {'status': status}})}\n\n"
                    break
            else:
                db_scan = get_scan_from_db(scan_id)
                if db_scan and db_scan["status"] in ("completed", "error", "cancelled"):
                    yield f"data: {json.dumps({'type': 'done', 'data': {'status': db_scan['status']}})}\n\n"
                    break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
