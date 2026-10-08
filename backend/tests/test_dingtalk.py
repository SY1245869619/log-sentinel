"""钉钉加签测试。"""
import urllib.parse

from app.notify_engine.dingtalk import _signed_url


def test_signed_url_contains_timestamp_and_sign():
    webhook = "https://oapi.dingtalk.com/robot/send?access_token=abc"
    url = _signed_url(webhook, "SEC123")
    assert "timestamp=" in url
    assert "sign=" in url
    # 两次调用时间戳不同或相同都行，但签名必须是合法 URL 编码
    query = urllib.parse.urlparse(url).query
    params = urllib.parse.parse_qs(query)
    assert params["access_token"] == ["abc"]
    assert params["timestamp"][0].isdigit()
    assert len(params["sign"][0]) > 0


def test_sign_is_deterministic_for_same_input(monkeypatch):
    import time
    monkeypatch.setattr(time, "time", lambda: 1727520000)
    webhook = "https://oapi.dingtalk.com/robot/send?access_token=abc"
    url1 = _signed_url(webhook, "SEC123")
    url2 = _signed_url(webhook, "SEC123")
    assert url1 == url2
    # 不同 secret 签名不同
    assert _signed_url(webhook, "SEC999") != url1
