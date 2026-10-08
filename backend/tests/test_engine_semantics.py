"""告警引擎语义测试（需求 §4 强制实现标准）。"""
from datetime import datetime

from app.modules.notify import engine


class TestFingerprint:
    """§4.1 告警指纹。"""

    def test_same_input_same_fingerprint(self):
        fp1 = engine._fingerprint(1, 2, "/a.log", "100", 1024, "内容")
        fp2 = engine._fingerprint(1, 2, "/a.log", "100", 1024, "内容")
        assert fp1 == fp2

    def test_different_offset_different_fingerprint(self):
        fp1 = engine._fingerprint(1, 2, "/a.log", "100", 1024, "内容")
        fp2 = engine._fingerprint(1, 2, "/a.log", "100", 2048, "内容")
        assert fp1 != fp2

    def test_redis_dedup(self, fake_redis):
        assert fake_redis.set("ls:fp:abc", 1, nx=True, ex=86400)
        assert not fake_redis.set("ls:fp:abc", 1, nx=True, ex=86400)


class TestSlidingWindow:
    """§4.6 N 秒内 M 次（滑动窗口，触发后清空重计）。"""

    def test_trigger_at_threshold(self, fake_redis, make_rule):
        rule = make_rule(window_seconds=60, threshold_count=3)
        assert engine._eval_window(rule, 1) is False  # 1次
        assert engine._eval_window(rule, 1) is False  # 2次
        assert engine._eval_window(rule, 1) is True   # 3次触发

    def test_counter_cleared_after_trigger(self, fake_redis, make_rule):
        rule = make_rule(window_seconds=60, threshold_count=2)
        engine._eval_window(rule, 1)
        assert engine._eval_window(rule, 1) is True
        # 触发后清空，重新计数
        assert engine._eval_window(rule, 1) is False


class TestConsecutive:
    """§4.7 连续 N 次（未命中行清零）。"""

    def test_trigger_at_n(self, fake_redis, make_rule):
        rule = make_rule(consecutive_count=3)
        assert engine._eval_consecutive(rule, 1) is False
        assert engine._eval_consecutive(rule, 1) is False
        assert engine._eval_consecutive(rule, 1) is True

    def test_reset_on_miss(self, fake_redis, make_rule):
        rule = make_rule(consecutive_count=3)
        engine._eval_consecutive(rule, 1)
        engine._eval_consecutive(rule, 1)
        engine.reset_consecutive(rule.id, 1)  # 中间出现未命中行
        assert engine._eval_consecutive(rule, 1) is False  # 重新计数


class TestSilence:
    """§4.11 静默期（rule_id, host_id, 匹配键 三元组）。"""

    def test_silence_blocks(self, fake_redis, make_rule):
        rule = make_rule(silence_seconds=300)
        assert engine._check_silence(rule, 1, "500") is False
        engine._mark_silence(rule, 1, "500")
        assert engine._check_silence(rule, 1, "500") is True

    def test_different_key_not_silenced(self, fake_redis, make_rule):
        rule = make_rule(silence_seconds=300)
        engine._mark_silence(rule, 1, "500")
        assert engine._check_silence(rule, 1, "404") is False   # 不同匹配键
        assert engine._check_silence(rule, 2, "500") is False   # 不同主机

    def test_zero_silence_never_blocks(self, fake_redis, make_rule):
        rule = make_rule(silence_seconds=0)
        engine._mark_silence(rule, 1, "500")
        assert engine._check_silence(rule, 1, "500") is False


class TestMaintenanceWindow:
    """§4.10 维护窗口（支持跨天）。"""

    def test_same_day_window(self, make_rule):
        rule = make_rule(maintenance_start="09:00", maintenance_end="12:00")
        at = lambda h: datetime(2026, 9, 28, h, 0)
        assert engine._in_maintenance(rule, at(10)) is True
        assert engine._in_maintenance(rule, at(13)) is False

    def test_cross_day_window(self, make_rule):
        rule = make_rule(maintenance_start="22:00", maintenance_end="06:00")
        at = lambda h: datetime(2026, 9, 28, h, 0)
        assert engine._in_maintenance(rule, at(23)) is True
        assert engine._in_maintenance(rule, at(5)) is True
        assert engine._in_maintenance(rule, at(12)) is False

    def test_no_window(self, make_rule):
        rule = make_rule(maintenance_start=None, maintenance_end=None)
        assert engine._in_maintenance(rule, datetime(2026, 9, 28, 3, 0)) is False
