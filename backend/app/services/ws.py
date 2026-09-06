import json
from datetime import datetime

from fastapi import WebSocket

from app.config import LOGS_DIR


class LogStore:
    """日志内存缓冲 + JSONL 落盘，支持 WS 断线重连后回放。"""

    def __init__(self):
        self._buffer: dict[int, list[dict]] = {}

    def append(self, run_id: int, event: dict) -> None:
        self._buffer.setdefault(run_id, []).append(event)
        with open(LOGS_DIR / f"{run_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def history(self, run_id: int) -> list[dict]:
        if run_id in self._buffer:
            return self._buffer[run_id]
        path = LOGS_DIR / f"{run_id}.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def cleanup(self, run_id: int) -> None:
        self._buffer.pop(run_id, None)


log_store = LogStore()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}

    async def connect(self, run_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: int, ws: WebSocket) -> None:
        conns = self._connections.get(run_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self._connections.pop(run_id, None)

    async def broadcast(self, run_id: int, event: dict) -> None:
        event["ts"] = datetime.utcnow().isoformat()
        log_store.append(run_id, event)
        dead = []
        for ws in self._connections.get(run_id, []):
            try:
                await ws.send_text(json.dumps(event, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(run_id, ws)


manager = ConnectionManager()


def make_log_event(node_id: str, node_name: str, level: str, message: str) -> dict:
    return {"type": "log", "node_id": node_id, "node_name": node_name, "level": level, "message": message}
