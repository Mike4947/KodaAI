import httpx

from backend.config import settings


async def check_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            return {"reachable": True, "message": "Ollama is running"}
    except httpx.ConnectError:
        return {"reachable": False, "message": "Cannot connect to Ollama. Is it running?"}
    except Exception as e:
        return {"reachable": False, "message": str(e)}


async def list_gemma_models() -> list[dict]:
    health = await check_health()
    if not health["reachable"]:
        return []

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{settings.ollama_base_url}/api/tags")
        resp.raise_for_status()
        data = resp.json()

    models = []
    for m in data.get("models", []):
        name = m.get("name", "")
        base = name.split(":")[0].lower()
        if "gemma4" in base or base == "koda-gemma4":
            models.append(
                {
                    "name": name,
                    "size": m.get("size"),
                    "modified_at": m.get("modified_at"),
                }
            )
    return models
