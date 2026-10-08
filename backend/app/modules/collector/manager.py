"""采集管理器：worker 生命周期（启动/停止/重启/开机自启）。"""
import logging
import threading

from ...database import SessionLocal
from ...models import LogSource
from .worker import CollectorWorker

logger = logging.getLogger("logsentinel.collector")


class CollectorManager:
    def __init__(self):
        self._workers: dict[int, CollectorWorker] = {}
        self._lock = threading.Lock()

    def start_source(self, source_id: int) -> None:
        with self._lock:
            old = self._workers.get(source_id)
            if old and old.alive:
                return
            if old:
                old.stop()
            worker = CollectorWorker(source_id)
            self._workers[source_id] = worker
            worker.start()

    def stop_source(self, source_id: int) -> None:
        with self._lock:
            worker = self._workers.pop(source_id, None)
        if worker:
            worker.stop()

    def restart_source(self, source_id: int) -> None:
        self.stop_source(source_id)
        self.start_source(source_id)

    def start_all_enabled(self) -> None:
        db = SessionLocal()
        try:
            # AGENT 模式由 Agent 主动上报，本进程不起采集线程
            ids = [s.id for s in db.query(LogSource).filter(
                LogSource.enabled == 1,
                LogSource.collect_mode != "AGENT").all()]
        finally:
            db.close()
        for sid in ids:
            try:
                self.start_source(sid)
            except Exception:
                logger.exception("采集自启失败: source=%d", sid)
        logger.info("采集器自启完成: %d 个日志源", len(ids))

    def is_running(self, source_id: int) -> bool:
        with self._lock:
            w = self._workers.get(source_id)
            return bool(w and w.alive)


manager = CollectorManager()
