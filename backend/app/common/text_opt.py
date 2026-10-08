"""日志内容中文优化与脱敏链（按需求 §3.6 顺序执行，单步失败不影响整体）：

1. 解码 \\uXXXX  2. 清理 ANSI  3. 解码 HTML 实体  4. 乱码修复
5. 关键字加粗  6. 超长截断  7. 脱敏（仅作用于优化后内容）
"""
import html
import logging
import re

logger = logging.getLogger("logsentinel")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
IDCARD_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
SECRET_RE = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|apikey|api_key|access_key)(\s*[:=]\s*)(\S+)")
LEVEL_RE = re.compile(r"\b(FATAL|ERROR|WARN|WARNING|INFO|DEBUG|TRACE)\b")


def _safe(fn, text: str) -> str:
    try:
        return fn(text)
    except Exception:  # noqa: BLE001 - 单步失败跳过
        logger.debug("文本优化单步失败，已跳过", exc_info=True)
        return text


def decode_unicode_escapes(text: str) -> str:
    return UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def decode_html_entities(text: str) -> str:
    return html.unescape(text)


def fix_mojibake(text: str) -> str:
    """修复典型 UTF-8 被按 latin-1 误读的乱码（含 'Ã'/'å' 特征时尝试还原）。"""
    if ("Ã" in text or "å" in text) and not re.search(r"[一-鿿]", text):
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    return text


def bold_keywords(text: str, keywords: list[str]) -> str:
    for kw in keywords:
        if kw:
            text = text.replace(kw, f"**{kw}**")
    return text


def mask_sensitive(text: str) -> str:
    text = PHONE_RE.sub("1**********", text)
    text = IDCARD_RE.sub("******************", text)
    text = SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}******", text)
    return text


def truncate_bytes(text: str, max_bytes: int, suffix: str = "") -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = encoded[:max_bytes]
    # 回退到完整 UTF-8 字符边界
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="ignore") + suffix


def optimize(raw: str, keywords: list[str] | None = None, max_bytes: int = 4000) -> str:
    """完整优化链：用于消息内容与 optimized_content 落库。"""
    text = raw or ""
    text = _safe(decode_unicode_escapes, text)
    text = _safe(strip_ansi, text)
    text = _safe(decode_html_entities, text)
    text = _safe(fix_mojibake, text)
    if keywords:
        text = _safe(lambda t: bold_keywords(t, keywords), text)
    text = _safe(lambda t: truncate_bytes(
        t, max_bytes, "\n...(内容过长已截断，请登录 LogSentinel 查看详情)"), text)
    text = _safe(mask_sensitive, text)
    return text


def extract_level(text: str) -> str | None:
    """从日志内容前 300 字符提取日志级别。"""
    m = LEVEL_RE.search(text[:300])
    return m.group(1) if m else None


JSON_MSG_RE = re.compile(r'\{[^{}]*"message"\s*:\s*"((?:[^"\\]|\\.)*)"[^{}]*\}')


def extract_summary(text: str, max_len: int = 100) -> str:
    """提取异常摘要：优先解析 {"code":N,"message":"..."} 的 message，
    否则取首行前 max_len 字符。
    注意：调用处传入的文本已完成 \\uXXXX 解码，此处不得再做 unicode_escape 转换。"""
    m = JSON_MSG_RE.search(text or "")
    if m:
        return m.group(1)[:max_len]
    first = (text or "").strip().split("\n", 1)[0]
    return first[:max_len]


def clip_lines(text: str, max_lines: int = 10, max_bytes: int = 800) -> str:
    """截取日志片段（钉钉消息用）：前 N 行且不超过字节上限。"""
    lines = (text or "").split("\n")
    clipped = "\n".join(lines[:max_lines])
    clipped = truncate_bytes(clipped, max_bytes)
    if len(lines) > max_lines:
        clipped += f"\n... 共 {len(lines)} 行，完整内容请登录系统查看"
    return clipped


def quote_lines(text: str) -> str:
    """每行加 markdown 引用前缀（钉钉不支持代码块，用引用块展示日志）。"""
    return "\n".join("> " + line if line.strip() else ">" for line in (text or "").split("\n"))
