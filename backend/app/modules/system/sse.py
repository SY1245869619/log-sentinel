"""SSE 实时推送：进程内发布/订阅（采集与告警事件）。"""
import json
import queue
import threading

_clients: list[queue.Queue] = []
_lock = threading.Lock()


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=1000)
    with _lock:
        _clients.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _clients:
            _clients.remove(q)


def publish(event: dict) -> None:
    data = json.dumps(event, ensure_ascii=False, default=str)
    with _lock:
        clients = list(_clients)
    for q in clients:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass  # 慢客户端丢弃，不阻塞生产者


def format_sse(data: str) -> str:
    return f"data: {data}\n\n"
