"""pytest 公共夹具：用 fakeredis 替换引擎中的 Redis 客户端。"""
import fakeredis
import pytest

from app.modules.notify import engine


@pytest.fixture()
def fake_redis(monkeypatch):
    client = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(engine, "redis_client", client)
    return client


@pytest.fixture()
def make_rule():
    """快速构造告警规则对象（不落库）。"""
    from app.models import AlertRule

    def _make(**kwargs):
        defaults = dict(
            id=1, name="测试规则", severity="MAJOR", match_type="KEYWORD",
            alert_enabled=1, silence_seconds=300, recover_notify=0,
            recover_window_seconds=300, aggregate_notify=0,
            aggregate_window_seconds=60, enabled=1,
        )
        defaults.update(kwargs)
        return AlertRule(**defaults)

    return _make
