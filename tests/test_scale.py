"""
test_scale.py — 1,000 concurrent SET+GET pairs to MiniKV coordinator.
Run: python tests/test_scale.py
"""
import asyncio
import time
import httpx

BASE = "http://localhost:8000"
TOTAL = 1000
CONCURRENCY = 50   # sweet spot for local Docker


async def set_get(client: httpx.AsyncClient, i: int) -> tuple[bool, bool]:
    key = f"bench:key:{i}"
    value = f"value_{i}"
    set_ok = get_ok = False
    try:
        r = await client.post(f"{BASE}/set", json={"key": key, "value": value}, timeout=15)
        set_ok = r.status_code == 200
    except Exception:
        pass
    try:
        r = await client.get(f"{BASE}/get/{key}", timeout=15)
        if r.status_code == 200:
            get_ok = r.json()["value"] == value
    except Exception:
        pass
    return set_ok, get_ok


async def main():
    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded(client, i):
        async with sem:
            return await set_get(client, i)

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    async with httpx.AsyncClient(limits=limits) as client:
        start = time.perf_counter()
        results = await asyncio.gather(*[bounded(client, i) for i in range(TOTAL)])
        elapsed = time.perf_counter() - start

    set_ok = sum(r[0] for r in results)
    get_ok = sum(r[1] for r in results)
    ops = (set_ok + get_ok) / elapsed

    print(f"\n{'='*50}")
    print(f"  Requests : {TOTAL} SET + {TOTAL} GET")
    print(f"  SET OK   : {set_ok}/{TOTAL}")
    print(f"  GET OK   : {get_ok}/{TOTAL}")
    print(f"  Elapsed  : {elapsed:.2f}s")
    print(f"  Ops/sec  : {ops:,.0f}  (local Docker limit)")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    asyncio.run(main())