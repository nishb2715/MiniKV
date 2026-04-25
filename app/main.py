import asyncio
import os
import time
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.hash_ring import HashRing
from app.vector_clock import VectorClock
from app.wal import wal_append, wal_read_all

N, W, R = 5, 3, 3
VIRTUAL_NODES = 150
COORDINATOR_ID = "coordinator"

REDIS_NODES: dict[str, str] = {
    f"node{i}": f"http://node{i}:800{i}" for i in range(1, N + 1)
}

ring = HashRing(virtual_nodes=VIRTUAL_NODES)


async def write_to_node(client, node, payload):
    try:
        r = await client.post(f"{REDIS_NODES[node]}/internal/set", json=payload, timeout=1.5)
        return r.status_code == 200
    except:
        return False


async def read_from_node(client, node, key):
    try:
        r = await client.get(f"{REDIS_NODES[node]}/internal/get/{key}", timeout=1.5)
        return r.json() if r.status_code == 200 else None
    except:
        return None


async def write_hint_to_proxy(client, proxy, target, payload):
    try:
        r = await client.post(
            f"{REDIS_NODES[proxy]}/internal/hint",
            json=payload,
            params={"target_node": target},
            timeout=1.5,
        )
        return r.status_code == 200
    except:
        return False


async def handback_worker():
    async with httpx.AsyncClient() as client:
        while True:
            await asyncio.sleep(2)
            for proxy_node, proxy_url in REDIS_NODES.items():
                try:
                    r = await client.get(f"{proxy_url}/internal/hints/pending", timeout=1.0)
                    if r.status_code != 200:
                        continue
                    for hint in r.json().get("hints", []):
                        target, payload = hint["target_node"], hint["payload"]
                        try:
                            ok = await client.post(
                                f"{REDIS_NODES[target]}/internal/set", json=payload, timeout=1.0
                            )
                            if ok.status_code == 200:
                                await client.delete(
                                    f"{proxy_url}/internal/hints/delete",
                                    params={"key": payload["key"], "target": target},
                                )
                        except:
                            continue
                except:
                    continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    for node in REDIS_NODES:
        ring.add_node(node)
    asyncio.create_task(handback_worker())
    yield


app = FastAPI(title="MiniKV Coordinator", lifespan=lifespan)


class SetRequest(BaseModel):
    key: str
    value: str


class KVResponse(BaseModel):
    key: str
    value: str
    vector_clock: dict
    node_responses: int


@app.post("/set", response_model=KVResponse)
async def set_key(req: SetRequest):
    target_nodes = ring.get_nodes(req.key, N)
    all_nodes = list(REDIS_NODES.keys())

    async with httpx.AsyncClient() as client:
        read_tasks = [read_from_node(client, n, req.key) for n in target_nodes]
        read_results = await asyncio.gather(*read_tasks)

    # FIX: reassign on each merge — VectorClock methods return new instances
    latest_vc = VectorClock()
    for resp in read_results:
        if resp:
            latest_vc = latest_vc.merge(VectorClock.from_dict(resp["vector_clock"]))
    latest_vc = latest_vc.increment(COORDINATOR_ID)
    new_clock = latest_vc.to_dict()

    payload = {"key": req.key, "value": req.value, "vector_clock": new_clock, "ts": time.time()}
    wal_append(req.key, req.value, new_clock)

    async with httpx.AsyncClient() as client:
        write_tasks = [write_to_node(client, n, payload) for n in target_nodes]
        results = list(await asyncio.gather(*write_tasks))

    acks = sum(results)

    async with httpx.AsyncClient() as client:
        potential_proxies = [n for n in all_nodes if n not in target_nodes]
        for i, success in enumerate(results):
            if not success and potential_proxies:
                proxy = potential_proxies.pop(0)
                hint_ok = await write_hint_to_proxy(client, proxy, target_nodes[i], payload)
                if hint_ok:
                    acks += 1

    if acks < W:
        raise HTTPException(status_code=503, detail=f"Write quorum failed: {acks}/{W}")

    return KVResponse(key=req.key, value=req.value, vector_clock=new_clock, node_responses=acks)


@app.get("/get/{key}", response_model=KVResponse)
async def get_key(key: str):
    target_nodes = ring.get_nodes(key, N)

    async with httpx.AsyncClient() as client:
        tasks = [read_from_node(client, n, key) for n in target_nodes]
        results = await asyncio.gather(*tasks)

    responses = [r for r in results if r is not None]
    if len(responses) < R:
        raise HTTPException(status_code=503, detail=f"Read quorum failed: {len(responses)}/{R}")

    best = responses[0]
    best_vc = VectorClock.from_dict(best["vector_clock"])
    for resp in responses[1:]:
        candidate_vc = VectorClock.from_dict(resp["vector_clock"])
        if candidate_vc.is_newer_than(best_vc):
            best = resp
            best_vc = candidate_vc

    return KVResponse(
        key=key,
        value=best["value"],
        vector_clock=best["vector_clock"],
        node_responses=len(responses),
    )


@app.get("/wal")
async def get_wal():
    return {"entries": wal_read_all()}


@app.get("/ring/node/{key}")
async def ring_lookup(key: str):
    return {"key": key, "nodes": ring.get_nodes(key, N)}


@app.get("/health")
async def health():
    return {"status": "ok", "nodes": list(REDIS_NODES.keys())}