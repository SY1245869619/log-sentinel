"""SSH 连接（Paramiko）。支持密码/私钥直连，以及经跳板机（堡垒机/jumpserver）中转。

跳板机原理（与 ssh -J 等价）：
1. 先 SSH 登录跳板机
2. 在跳板机连接上开 direct-tcpip 通道指向目标机
3. 把该通道当作 socket 再发起对目标机的 SSH 认证

jumpserver 说明：需 jumpserver 账号对目标资产有授权且支持直连（koko 组件），
使用 jumpserver 的地址/端口/账号作为"跳板机"配置，目标机填真实服务器。
"""
import io

import paramiko


def _load_private_key(key_text: str, password: str | None = None):
    """依次尝试常见私钥类型。"""
    last_err: Exception | None = None
    for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
        try:
            return key_cls.from_private_key(io.StringIO(key_text), password=password)
        except Exception as e:  # noqa: BLE001 - 尝试下一种类型
            last_err = e
    raise ValueError(f"私钥解析失败: {last_err}")


def _auth_kwargs(auth_type: str, password: str | None, private_key: str | None) -> dict:
    if auth_type == "KEY":
        if not private_key:
            raise ValueError("未配置私钥")
        return {"pkey": _load_private_key(private_key, password)}
    if not password:
        raise ValueError("未配置密码")
    return {"password": password}


def connect_ssh(ip: str, port: int, username: str, auth_type: str,
                password: str | None = None, private_key: str | None = None,
                timeout: float = 8.0, bastion: dict | None = None) -> paramiko.SSHClient:
    """建立 SSH 连接（调用方用 close_ssh 关闭）。

    bastion 可选：{"ip", "port", "username", "auth_type", "password", "private_key"}
    """
    jump = None
    sock = None
    if bastion and bastion.get("ip"):
        jump = paramiko.SSHClient()
        jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jump.connect(
            hostname=bastion["ip"], port=int(bastion.get("port") or 22),
            username=bastion.get("username") or "",
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
            **_auth_kwargs(bastion.get("auth_type", "PASSWORD"),
                           bastion.get("password"), bastion.get("private_key")))
        sock = jump.get_transport().open_channel(
            "direct-tcpip", (ip, int(port)), ("127.0.0.1", 0))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip, port=int(port), username=username,
            timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
            sock=sock,
            **_auth_kwargs(auth_type, password, private_key))
    except Exception:
        if sock:
            sock.close()
        if jump:
            jump.close()
        raise
    # 把跳板机连接挂在客户端上，close_ssh 时一并关闭
    client._bastion_client = jump  # type: ignore[attr-defined]
    return client


def close_ssh(client: paramiko.SSHClient) -> None:
    """关闭连接（含跳板机）。"""
    try:
        client.close()
    finally:
        jump = getattr(client, "_bastion_client", None)
        if jump:
            try:
                jump.close()
            except Exception:  # noqa: BLE001
                pass


def test_ssh_connection(ip: str, port: int, username: str, auth_type: str,
                        password: str | None = None,
                        private_key: str | None = None,
                        bastion: dict | None = None) -> tuple[bool, str]:
    """测试 SSH 连接并执行 echo ok。返回 (是否成功, 信息)。"""
    try:
        client = connect_ssh(ip, port, username, auth_type, password, private_key,
                             bastion=bastion)
        try:
            _, stdout, _ = client.exec_command("echo ok", timeout=5)
            result = stdout.read().decode("utf-8", errors="replace").strip()
            via = f"（经跳板机 {bastion['ip']}）" if bastion and bastion.get("ip") else ""
            return (True, f"连接成功{via}，远程返回: {result}")
        finally:
            close_ssh(client)
    except Exception as e:  # noqa: BLE001 - 统一返回错误信息
        return False, str(e)
