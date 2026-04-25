import json
import time
import os

WAL_PATH = os.environ.get("WAL_PATH", "/tmp/minikv.log")


def wal_append(key: str, value: str, clock: dict) -> None:
    entry = json.dumps({"ts": time.time(), "key": key, "value": value, "clock": clock})
    with open(WAL_PATH, "a") as f:
        f.write(entry + "\n")


def wal_read_all() -> list[dict]:
    if not os.path.exists(WAL_PATH):
        return []
    with open(WAL_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]