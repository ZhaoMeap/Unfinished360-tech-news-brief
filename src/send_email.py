"""Explicit opt-in SMTP transport. Never print credentials or server responses."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses

REQUIRED = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_FROM", "MAIL_TO")


def send_email(subject: str, body: str) -> bool:
    missing = [name for name in REQUIRED if not os.getenv(name, "").strip()]
    if missing:
        print("寄信設定不足，報告已保留；缺少：" + ", ".join(missing))
        return False
    try:
        port = int(os.environ["SMTP_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError("port")
        sender = os.environ["MAIL_FROM"].strip()
        recipients = os.environ["MAIL_TO"].strip()
        if any("\n" in value or "\r" in value for value in (subject, sender, recipients)):
            raise ValueError("headers")
        addresses = [addr for _, addr in getaddresses([recipients])]
        if not addresses or any("@" not in addr for addr in addresses) or "@" not in sender:
            raise ValueError("addresses")
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipients
        message.set_content(body)
        context = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        options = {"timeout": 20}
        if port == 465:
            options["context"] = context
        with transport(os.environ["SMTP_HOST"], port, **options) as smtp:
            if port != 465:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            smtp.send_message(message, to_addrs=addresses)
        print("報告已透過 SMTP 寄出。")
        return True
    except (ValueError, OSError, smtplib.SMTPException) as exc:
        print(f"寄信失敗（{type(exc).__name__}）；請檢查 SMTP 設定，報告已保留。")
        return False
