"""邮件渠道：SMTP SSL 发送（QQ 邮箱等）。

配置字段：host / port / user / password(授权码) / to(收件人列表)
"""
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr


def send_email(host: str, port: int, user: str, password: str,
               to_list: list[str], subject: str, content: str,
               timeout: float = 10.0) -> tuple[bool, str]:
    """发送纯文本邮件。返回 (是否成功, 响应/错误信息)。"""
    if not to_list:
        return False, "收件人列表为空"
    msg = MIMEText(content, "plain", "utf-8")
    msg["From"] = formataddr((str(Header("LogSentinel 日志监控告警系统", "utf-8")), user))
    msg["To"] = ",".join(to_list)
    msg["Subject"] = Header(subject, "utf-8")
    try:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as smtp:
            smtp.login(user, password)
            smtp.sendmail(user, to_list, msg.as_string())
        return True, f"已发送至 {len(to_list)} 个收件人"
    except Exception as e:
        return False, str(e)
