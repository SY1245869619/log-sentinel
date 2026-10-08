"""文件读取抽象：本机直连 / 远程 SFTP（Paramiko）。

远程 glob 通过 bash 展开（支持 ** 递归，需远端 bash）；
offset 按字节读取，GBK/UTF-8 按 \n 字节切分后解码均安全（0x0A 不会出现在多字节字符内）。
"""
import fnmatch
import glob
import logging
import os
from dataclasses import dataclass

from ...common.security import aes_decrypt
from ...models import Host
from ..hosts.ssh import connect_ssh

logger = logging.getLogger("logsentinel.collector")

READ_CHUNK_BYTES = 1024 * 1024  # 每周期每文件最多读 1MB，防积压时内存暴涨


@dataclass
class FileStat:
    path: str
    inode: str
    size: int


class BaseReader:
    def list_files(self, pattern: str, exclude: str | None) -> list[str]:
        raise NotImplementedError

    def stat(self, path: str) -> FileStat:
        raise NotImplementedError

    def read(self, path: str, offset: int, max_bytes: int) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass


class LocalReader(BaseReader):
    def list_files(self, pattern: str, exclude: str | None) -> list[str]:
        files = [f for f in glob.glob(pattern, recursive=True) if os.path.isfile(f)]
        if exclude:
            files = [f for f in files if not fnmatch.fnmatch(os.path.basename(f), exclude)
                     and not fnmatch.fnmatch(f, exclude)]
        return sorted(files)

    def stat(self, path: str) -> FileStat:
        st = os.stat(path)
        # Windows 等平台 st_ino 可能为 0（视为不可用，由 worker 退化到 size 检测）
        inode = st.st_ino or ""
        return FileStat(path=path, inode=str(inode), size=st.st_size)

    def read(self, path: str, offset: int, max_bytes: int) -> bytes:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read(max_bytes)


class RemoteReader(BaseReader):
    """远程 SFTP 读取：连接按需建立，异常时重连（指数退避，上限 5 分钟）。"""

    def __init__(self, host: Host):
        self.host = host
        self._client = None
        self._sftp = None

    def _ensure_conn(self) -> None:
        if self._client and self._sftp:
            transport = self._client.get_transport()
            if transport and transport.is_active():
                return
        self.close()
        h = self.host
        bastion = None
        if h.bastion_ip:
            bastion = {
                "ip": h.bastion_ip, "port": h.bastion_port or 22,
                "username": h.bastion_username or "",
                "auth_type": h.bastion_auth_type or "PASSWORD",
                "password": aes_decrypt(h.bastion_password_enc),
                "private_key": aes_decrypt(h.bastion_key_enc),
            }
        self._client = connect_ssh(
            ip=h.ip, port=h.ssh_port, username=h.username or "",
            auth_type=h.auth_type,
            password=aes_decrypt(h.password_enc),
            private_key=aes_decrypt(h.private_key_enc),
            timeout=10.0, bastion=bastion)
        self._sftp = self._client.open_sftp()

    def list_files(self, pattern: str, exclude: str | None) -> list[str]:
        self._ensure_conn()
        # bash 展开 glob（-O globstar 支持 **；-O nullglob 无匹配时置空）
        cmd = f"bash -O globstar -O nullglob -c 'for f in {pattern}; do [ -f \"$f\" ] && echo \"$f\"; done'"
        _, stdout, _ = self._client.exec_command(cmd, timeout=15)
        files = [line.strip() for line in stdout.read().decode("utf-8", "replace").splitlines()
                 if line.strip()]
        if exclude:
            files = [f for f in files if not fnmatch.fnmatch(os.path.basename(f), exclude)
                     and not fnmatch.fnmatch(f, exclude)]
        return sorted(files)

    def stat(self, path: str) -> FileStat:
        self._ensure_conn()
        st = self._sftp.stat(path)
        # 部分 SFTP 服务端不返回 st_ino：inode 置空（不可用）。
        # 注意不能用 mtime 冒充 inode——mtime 随每次写入变化，
        # 会导致误判轮转、反复重读全文件（曾造成告警洪水）。
        # 无 inode 时由 worker 退化到 size 回退检测（copytruncate 分支）。
        inode = getattr(st, "st_ino", None)
        return FileStat(path=path, inode=str(inode) if inode is not None else "",
                        size=st.st_size)

    def read(self, path: str, offset: int, max_bytes: int) -> bytes:
        self._ensure_conn()
        with self._sftp.open(path, "rb") as f:
            f.seek(offset)
            return f.read(max_bytes)

    def close(self) -> None:
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:  # noqa: BLE001
            pass
        if self._client:
            from ..hosts.ssh import close_ssh
            close_ssh(self._client)  # 含跳板机
        self._sftp = None
        self._client = None


def build_reader(host: Host) -> BaseReader:
    return LocalReader() if host.host_type == "LOCAL" else RemoteReader(host)
