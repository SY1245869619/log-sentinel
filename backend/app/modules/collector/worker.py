"""采集 worker：每个日志源一个线程。

- 断点：per-file offset 存 Redis hash（ls:off:{source_id}），处理落库后提交（§4.5）
- 轮转：inode 变化 → 记录 rotated_file 并从 0 读新文件；copytruncate（size<offset）→ offset 归 0（§4.4）
- 多行合并：行首匹配 multiline_pattern 为新条目，否则并入上一条；空闲一周期后强制 flush（§4.3）
- 新文件策略：首次发现从文件末尾开始（不补采历史）
- 远程模式：SSH 断线指数退避重连（上限 5 分钟），状态上报 RECONNECTING
"""
import logging
import re
import threading
import time
from datetime import datetime

from ...database import SessionLocal, redis_client
from ...models import CollectorState, Host, LogSource, Project
from ..notify import engine
from ..system import sse
from .reader import READ_CHUNK_BYTES, BaseReader, build_reader

logger = logging.getLogger("logsentinel.collector")


def _to_str(v) -> str | None:
    """Redis hget 默认返回 bytes，统一解码为 str；None 原样返回。"""
    if v is None:
        return None
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


class CollectorWorker:
    def __init__(self, source_id: int):
        self.source_id = source_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._reader: BaseReader | None = None
        self._retry = 0
        # {project} 通配模式下的项目缓存：目录名 -> Project
        self._projects: dict[str, Project] = {}

    # ---------------- 生命周期 ----------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name=f"collector-{self.source_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ---------------- Redis 断点 ----------------

    def _off_key(self) -> str:
        return f"ls:off:{self.source_id}"

    def _inode_key(self) -> str:
        return f"ls:inode:{self.source_id}"

    # ---------------- 主循环 ----------------

    def _run(self) -> None:
        logger.info("采集线程启动: source=%d", self.source_id)
        while not self._stop.is_set():
            db = SessionLocal()
            try:
                source = db.query(LogSource).filter(LogSource.id == self.source_id).first()
                if not source or not source.enabled:
                    self._report(db, "STOPPED")
                    return
                project = db.query(Project).filter(Project.id == source.project_id).first()
                host = db.query(Host).filter(Host.id == source.host_id).first()
                if not project or not host:
                    self._report(db, "ERROR", "关联项目或主机不存在")
                    self._wait(source.interval_seconds if source else 5)
                    continue

                if not self._reader:
                    self._reader = build_reader(host)

                self._collect_once(db, source, project, host)
                self._retry = 0
                self._report(db, "RUNNING")
                self._wait(source.interval_seconds)
            except Exception as e:  # noqa: BLE001 - 采集异常转入重连
                self._retry += 1
                logger.warning("采集异常(source=%d, 第%d次): %s", self.source_id, self._retry, e)
                try:
                    self._report(db, "RECONNECTING", str(e)[:1000])
                except Exception:  # noqa: BLE001
                    pass
                if self._reader:
                    self._reader.close()
                    self._reader = None
                # 指数退避，上限 300 秒
                self._wait(min(2 ** self._retry, 300))
            finally:
                db.close()
        logger.info("采集线程停止: source=%d", self.source_id)

    def _wait(self, seconds: float) -> None:
        self._stop.wait(max(1, seconds))

    # ---------------- 单次采集 ----------------

    def _collect_once(self, db, source: LogSource, project: Project, host: Host) -> None:
        pattern = source.path_pattern
        wildcard_project = "{project}" in pattern
        glob_pattern = pattern.replace("{project}", "*") if wildcard_project else pattern

        files = self._reader.list_files(glob_pattern, source.exclude_pattern)
        if not files:
            return
        for path in files:
            if self._stop.is_set():
                return
            # {project} 模式：按目录名解析归属项目（不存在则自动创建）
            file_project = project
            if wildcard_project:
                proj_name = self._derive_project_name(pattern, path)
                if proj_name:
                    file_project = self._resolve_project(db, proj_name, fallback=project)
            try:
                self._collect_file(db, source, file_project, host, path)
            except FileNotFoundError:
                continue  # 文件被轮转/清理，跳过
            except Exception as e:  # noqa: BLE001
                logger.warning("采集文件失败 %s: %s", path, e)

    @staticmethod
    def _derive_project_name(pattern: str, path: str) -> str | None:
        """从路径提取 {project} 占位符对应的目录名。

        例：pattern=/opt/fscr/app/logs/{project}/*.log，
        path=/opt/fscr/app/logs/fscr-base/error.log → fscr-base
        """
        prefix = pattern.split("{project}")[0]
        if not path.startswith(prefix):
            return None
        rest = path[len(prefix):]
        return rest.split("/")[0] if rest else None

    def _resolve_project(self, db, name: str, fallback: Project) -> Project:
        """按目录名获取项目，不存在则自动创建（项目自动发现）。"""
        if name in self._projects:
            return self._projects[name]
        project = db.query(Project).filter(
            (Project.name == name) | (Project.code == name)).first()
        if not project:
            try:
                project = Project(name=name, code=name, status=1,
                                  description="采集自动发现创建")
                db.add(project)
                db.commit()
                db.refresh(project)
                logger.info("项目自动发现: %s（来源日志目录）", name)
                sse.publish({"type": "project_auto", "name": name})
            except Exception:  # noqa: BLE001 - 并发创建冲突等
                db.rollback()
                project = db.query(Project).filter(Project.code == name).first() or fallback
        self._projects[name] = project
        return project

    def _collect_file(self, db, source, project, host, path: str) -> None:
        st = self._reader.stat(path)

        # 【关键修复】Redis hget 默认返回 bytes，必须解码后再和 str 比较，
        # 否则 bytes != str 永远为 True，会被误判为"日志轮转"，
        # 导致 offset 被清空、每次只写文件末尾、永远读不到新日志。
        stored_inode = _to_str(redis_client.hget(self._inode_key(), path))
        offset_raw = _to_str(redis_client.hget(self._off_key(), path))

        # inode 可用（非空）时才做 rename+create 轮转判断；
        # SFTP 不返回 inode 的服务器退化到下方 size < offset 检测
        if st.inode and stored_inode and stored_inode != st.inode:
            # rename+create 轮转/应用重建文件：新文件从 0 完整读取（不漏采）
            logger.info("[采集] 检测到文件轮转 source=%d %s: inode %s -> %s，offset 归 0",
                        self.source_id, path, stored_inode, st.inode)
            self._report(db, "RUNNING", current_file=path,
                         rotated_file=f"inode {stored_inode} -> {st.inode}")
            redis_client.hset(self._inode_key(), path, st.inode)
            redis_client.hset(self._off_key(), path, 0)
            offset_raw = "0"
        elif st.inode:
            redis_client.hset(self._inode_key(), path, st.inode)

        if offset_raw is None:
            # 新文件：从末尾开始（不补采历史）
            logger.info("[采集] 首次发现文件 source=%d %s，从末尾 %d 开始",
                        self.source_id, path, st.size)
            redis_client.hset(self._off_key(), path, st.size)
            return

        offset = int(offset_raw)
        if st.size < offset:
            # copytruncate 截断（§4.4）
            logger.info("[采集] 检测到文件截断 source=%d %s: size %d < offset %d，offset 归 0",
                        self.source_id, path, st.size, offset)
            offset = 0
        if st.size == offset:
            return  # 无新数据

        data = self._reader.read(path, offset, READ_CHUNK_BYTES)
        if not data:
            return

        entries, consumed = self._split_entries(data, source)
        for text, start_off in entries:
            engine.process_entry(db, source, project, host,
                                 path, st.inode, offset + start_off,
                                 text, datetime.now())
        # §4.5 处理落库后才提交 offset
        redis_client.hset(self._off_key(), path, offset + consumed)
        logger.info("[采集] source=%d file=%s offset %d -> %d，本次 %d 条",
                    self.source_id, path, offset, offset + consumed, len(entries))
        self._report(db, "RUNNING", current_file=path,
                     read_offset=offset + consumed, inode=st.inode)

    def _split_entries(self, data: bytes, source: LogSource) -> tuple[list[tuple[str, int]], int]:
        """按 \n 切行 + 多行合并。返回 ([(条目文本, 条目起始相对偏移)], 已消费字节数)。

        未结尾的不完整行保留到下周期（不消费）。
        """
        encoding = "gbk" if source.encoding.upper() == "GBK" else "utf-8"
        last_nl = data.rfind(b"\n")
        if last_nl < 0:
            return [], 0  # 无完整行
        body = data[: last_nl + 1]
        consumed = len(body)

        new_line_re = re.compile(source.multiline_pattern)
        entries: list[tuple[str, int]] = []
        buf: list[str] = []
        buf_start = 0
        pos = 0
        matched_any = False

        def flush() -> None:
            if buf:
                entries.append(("\n".join(buf), buf_start))

        for raw_line in body.split(b"\n")[:-1]:
            line = raw_line.decode(encoding, errors="replace").rstrip("\r")
            if new_line_re.match(line):
                matched_any = True
                flush()
                buf = [line]
                buf_start = pos
            else:
                if not buf:
                    buf_start = pos
                if len(buf) < 200:  # 合并上限（§4.3）
                    buf.append(line)
            pos += len(raw_line) + 1
        if not matched_any:
            # 多行起始正则一行都不匹配：所有行会合并成一条（超过 200 行的部分被丢弃），
            # 极易导致漏报，必须显式告警提示修正配置
            logger.warning("[采集] 多行起始正则不匹配任何行 source=%d pattern=%r，"
                           "请用日志源弹窗中的「生成正则」重新生成",
                           self.source_id, source.multiline_pattern)
        flush()  # 本周期结束时 flush（堆栈通常在单次写入中完整到达）
        return entries, consumed

    # ---------------- 状态上报 ----------------

    def _report(self, db, status: str, error: str | None = None,
                current_file: str | None = None, rotated_file: str | None = None,
                read_offset: int | None = None, inode: str | None = None) -> None:
        try:
            state = db.query(CollectorState).filter(
                CollectorState.log_source_id == self.source_id).first()
            if not state:
                state = CollectorState(log_source_id=self.source_id, host_id=0)
                db.add(state)
            state.status = status
            state.last_heartbeat = datetime.now()
            state.error_msg = error
            state.retry_count = self._retry
            if status == "RECONNECTING":
                state.last_retry_at = datetime.now()
            if current_file:
                state.current_file = current_file
            if rotated_file:
                state.rotated_file = rotated_file
            if read_offset is not None:
                state.read_offset = read_offset
                state.last_read_position = read_offset
            if inode is not None:
                state.inode = str(inode)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        if status in ("ERROR", "RECONNECTING"):
            sse.publish({"type": "collector", "status": status,
                         "source_id": self.source_id, "error": error})