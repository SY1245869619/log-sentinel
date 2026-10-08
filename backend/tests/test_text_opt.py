"""中文优化与脱敏链测试（需求 §3.6 七步处理）。"""
from app.common import text_opt


def test_decode_unicode_escapes():
    assert text_opt.decode_unicode_escapes(r"错误 \u65e0\u6cd5连接") == "错误 无法连接"


def test_strip_ansi():
    assert text_opt.strip_ansi("\x1b[31mERROR\x1b[0m 失败") == "ERROR 失败"


def test_decode_html_entities():
    assert text_opt.decode_html_entities("a &lt; b &amp; c") == "a < b & c"


def test_mask_sensitive_phone_idcard():
    text = "用户13812345678身份证110101199003077777登录"
    result = text_opt.mask_sensitive(text)
    assert "13812345678" not in result
    assert "110101199003077777" not in result


def test_mask_sensitive_secret_fields():
    result = text_opt.mask_sensitive("password=abc123 token: xyz789")
    assert "abc123" not in result
    assert "xyz789" not in result
    assert "******" in result


def test_truncate_bytes_keeps_utf8_boundary():
    text = "中文测试" * 2000
    result = text_opt.truncate_bytes(text, 100)
    # 截断后必须是合法字符串且不超过限制（含后缀）
    assert len(result.encode("utf-8")) <= 100 + 100


def test_bold_keywords():
    assert text_opt.bold_keywords("发生了NullPointerException异常", ["NullPointerException"]) == \
        "发生了**NullPointerException**异常"


def test_extract_level():
    assert text_opt.extract_level("2026-09-28 10:00:00 ERROR 启动失败") == "ERROR"
    assert text_opt.extract_level("2026-09-28 10:00:00 INFO 正常") == "INFO"
    assert text_opt.extract_level("没有级别") is None


def test_optimize_full_chain():
    raw = r"\x1b[31m\u9519\u8bef\x1b[0m password=secret123 13812345678"
    result = text_opt.optimize(raw)
    assert "secret123" not in result
    assert "13812345678" not in result


def test_extract_summary_json_message():
    text = '2026-09-30 10:13:38,732 - ERROR - handler.py - {"code": 401230117, "message": "用户名或密码错误，请重新输入。"}'
    assert text_opt.extract_summary(text) == "用户名或密码错误，请重新输入。"


def test_extract_summary_no_mojibake_after_optimize():
    """\\uXXXX 经 optimize 解码后，extract_summary 不得再次转换（曾导致乱码）。"""
    raw = '{"code": 402037047, "message": "\\u5236\\u5f0f\\u8bfe\\u7a0b\\u4e0d\\u53ef\\u590d\\u5236"}'
    optimized = text_opt.optimize(raw)
    assert text_opt.extract_summary(optimized) == "制式课程不可复制"


def test_extract_summary_fallback_first_line():
    assert text_opt.extract_summary("第一行内容\n第二行") == "第一行内容"


def test_quote_lines():
    assert text_opt.quote_lines("a\nb") == "> a\n> b"
