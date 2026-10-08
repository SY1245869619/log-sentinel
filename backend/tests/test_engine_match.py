"""规则匹配测试（§3.5 四种匹配类型 + 白名单排除）。"""
from app.models import ErrorCode, Keyword
from app.modules.notify.engine import RuleCtx, match_rule


def kw(pattern, op="CONTAINS"):
    return Keyword(id=1, name="k", pattern=pattern, match_op=op, enabled=1)


def ctx(match_type, keywords=None, error_codes=None, match_content=None, rule_id=1):
    from app.models import AlertRule
    rule = AlertRule(id=rule_id, name="r", severity="MAJOR", match_type=match_type,
                     match_content=match_content, alert_enabled=1, enabled=1)
    return RuleCtx(rule=rule, keywords=keywords or [], error_codes=error_codes or [])


def test_keyword_contains():
    c = ctx("KEYWORD", keywords=[kw("NullPointerException")])
    matched, key, _ = match_rule(c, "java.lang.NullPointerException at line 1")
    assert matched and key == "NullPointerException"
    assert not match_rule(c, "一切正常")[0]


def test_keyword_not_contains_whitelist():
    # NOT_CONTAINS 关键字在文本中出现 → 整体不命中（白名单语义）
    c = ctx("KEYWORD", keywords=[kw("ERROR"), kw("HealthCheck", "NOT_CONTAINS")])
    assert not match_rule(c, "ERROR HealthCheck ok")[0]
    assert match_rule(c, "ERROR 数据库连接失败")[0]


def test_keyword_equals_and_regex():
    c = ctx("KEYWORD", keywords=[kw("FATAL", "EQUALS")])
    assert match_rule(c, "FATAL")[0]
    assert not match_rule(c, "FATAL error")[0]
    c2 = ctx("KEYWORD", keywords=[kw(r"timeout \d+ms", "REGEX")])
    assert match_rule(c2, "请求 timeout 3000ms 超时")[0]


def test_regex_rule():
    c = ctx("REGEX", match_content=r"OutOfMemoryError|StackOverflowError")
    assert match_rule(c, "java.lang.OutOfMemoryError: Java heap space")[0]
    assert not match_rule(c, "普通日志")[0]


def test_error_code_extraction():
    # §4.2 提取正则：500 命中，5000 不误中
    ec = ErrorCode(id=1, code="500", extract_regex=r"(?<!\d)500(?!\d)", enabled=1)
    c = ctx("ERROR_CODE", error_codes=[ec])
    matched, key, _ = match_rule(c, "HTTP request failed with status 500")
    assert matched and key == "500"
    assert not match_rule(c, "listening on port 5000")[0]


def test_error_code_business_code():
    ec = ErrorCode(id=1, code="ERR_TIMEOUT", extract_regex=r"ERR_[A-Z_]+", enabled=1)
    c = ctx("ERROR_CODE", error_codes=[ec])
    assert match_rule(c, "调用支付接口返回 ERR_TIMEOUT")[0]


def test_error_code_prefixed_whole_match():
    """提取正则为 "code":\\s*123 时，整体匹配串带前缀也必须命中（真实日志场景）。"""
    ec = ErrorCode(id=1, code="401230117", extract_regex=r'"code":\s*401230117', enabled=1)
    c = ctx("ERROR_CODE", error_codes=[ec])
    log = '2026-09-29 10:43:10,231 - ERROR - handler.py - {"code": 401230117, "message": "测试"}'
    matched, key, _ = match_rule(c, log)
    assert matched and key == "401230117"
    # 其他 code 不误中
    assert not match_rule(c, '{"code": 402037047, "message": "x"}')[0]


def test_error_code_with_capture_group():
    """带捕获分组的提取正则。"""
    ec = ErrorCode(id=1, code="402037047", extract_regex=r'"code":\s*(\d+)', enabled=1)
    c = ctx("ERROR_CODE", error_codes=[ec])
    assert match_rule(c, '{"code": 402037047, "message": "制式课程不可复制"}')[0]
    assert not match_rule(c, '{"code": 0, "message": "成功"}')[0]


def test_log_level():
    c = ctx("LOG_LEVEL", match_content="ERROR")
    assert match_rule(c, "2026-09-28 ERROR 服务异常")[0]
    assert not match_rule(c, "2026-09-28 INFO 正常")[0]
    # 词边界：TERROR 不应命中 ERROR
    assert not match_rule(c, "TERROR 字样")[0]
