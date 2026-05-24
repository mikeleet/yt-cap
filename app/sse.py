import asyncio
import json
import queue
from typing import AsyncGenerator


class SSEManager:
    def __init__(self):
        self._channels: dict[str, list[queue.Queue]] = {}

    def subscribe(self, channel_id: str) -> queue.Queue:
        if channel_id not in self._channels:
            self._channels[channel_id] = []
        q: queue.Queue = queue.Queue()
        self._channels[channel_id].append(q)
        return q

    def unsubscribe(self, channel_id: str, q: queue.Queue):
        if channel_id in self._channels:
            try:
                self._channels[channel_id].remove(q)
            except ValueError:
                pass

    def send(self, channel_id: str, event: str, data: dict):
        if channel_id not in self._channels:
            return
        message = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        dead = []
        for q in self._channels[channel_id]:
            try:
                q.put_nowait(message)
            except queue.Full:
                dead.append(q)
        for q in dead:
            try:
                self._channels[channel_id].remove(q)
            except ValueError:
                pass


sse_manager = SSEManager()


async def sse_stream(channel_id: str) -> AsyncGenerator[str, None]:
    q = sse_manager.subscribe(channel_id)
    loop = asyncio.get_event_loop()
    try:
        q.put_nowait(f"event: connected\ndata: {json.dumps({'channel_id': channel_id})}\n\n")
        while True:
            try:
                message = await loop.run_in_executor(None, lambda: q.get(timeout=30))
                yield message
            except queue.Empty:
                yield f"event: ping\ndata: {json.dumps({'ts': None})}\n\n"
    finally:
        sse_manager.unsubscribe(channel_id, q)
