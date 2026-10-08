"""钉钉机器人渠道：加签 + markdown 消息 + @人。

加签算法（钉钉官方）：
  timestamp = 毫秒时间戳
  sign = urlencode(base64(hmac_sha256(secret, f"{timestamp}\\n{secret}")))
"""
import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx


def _signed_url(webhook: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"),
                      string_to_sign.encode("utf-8"),
                      digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def send_markdown(webhook: str, secret: str, title: str, text: str,
                  at_mobiles: list[str] | None = None,
                  at_user_ids: list[str] | None = None,
                  is_at_all: bool = False,
                  timeout: float = 5.0) -> tuple[bool, str]:
    """发送 markdown 消息。返回 (是否成功, 响应/错误信息)。"""
    url = _signed_url(webhook, secret) if secret else webhook
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": text},
        "at": {
            "atMobiles": at_mobiles or [],
            "atUserIds": at_user_ids or [],
            "isAtAll": is_at_all,
        },
    }
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        body = resp.json()
        # 钉钉 errcode=0 表示成功
        if body.get("errcode") == 0:
            return True, resp.text
        return False, resp.text
    except Exception as e:
        return False, str(e)
