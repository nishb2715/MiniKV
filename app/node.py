"""
Storage node: thin HTTP wrapper around Redis + hinted handoff store.
Env: REDIS_HOST, REDIS_PORT, NODE_ID
"""
import json
import os
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI()

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
_redis: aioredis.Redis | None = None

# In-memory hint store: {target_node: [{payload, key}]}
_hints: dict[str, list] = {}


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    return _redis


class SetPayload(BaseModel):
    key: str
    value: str
    vector_clock: dict
    ts: float


@app.post("/internal/set")
async def internal_set(payload: SetPayload):
    r = await get_redis()
    await r.set(
        payload.key,
        json.dumps({"value": payload.value, "vector_clock": payload.vector_clock, "ts": payload.ts}),
    )
    return {"status": "ok"}


@app.get("/internal/get/{key}")
async def internal_get(key: str):
    r = await get_redis()
    raw = await r.get(key)
    if raw is None:
        raise HTTPException(status_code=404, detail="Key not found")
    data = json.loads(raw)
    return {"key": key, "value": data["value"], "vector_clock": data["vector_clock"], "ts": data["ts"]}


# ── Hinted handoff ────────────────────────────────────────────────────────────
@app.post("/internal/hint")
async def store_hint(payload: SetPayload, target_node: str = Query(...)):
    _hints.setdefault(target_node, []).append({"target_node": target_node, "payload": payload.model_dump()})
    return {"status": "hint stored", "target": target_node}


@app.get("/internal/hints/pending")
async def pending_hints():
    all_hints = []
    for hints in _hints.values():
        all_hints.extend(hints)
    return {"hints": all_hints}


@app.delete("/internal/hints/delete")
async def delete_hint(key: str = Query(...), target: str = Query(...)):
    if target in _hints:
        _hints[target] = [h for h in _hints[target] if h["payload"]["key"] != key]
    return {"status": "deleted"}


@app.get("/health")
async def health():
    return {"status": "ok"}