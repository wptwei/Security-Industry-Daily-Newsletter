"""推送：企业微信 / 钉钉 / 飞书群机器人 + SMTP 邮件。未配置的渠道自动跳过。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Dict

import requests

from app.utils.logging import get_logger

logger = get_logger("pusher")

WECOM_LIMIT = 4096      # 企业微信 markdown 字节上限
DINGTALK_LIMIT = 20000  # 钉钉 markdown 字符上限
FEISHU_LIMIT = 30000    # 飞书 text 字符上限


def _truncate(text: str, limit: int, by_bytes: bool = False) -> str:
    if by_bytes:
        data = text.encode("utf-8")
        if len(data) <= limit:
            return text
        cut = data[: limit - 3].decode("utf-8", errors="ignore")
        return cut + "..."
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class Pusher:
    def __init__(self, config) -> None:
        self.config = config

    def push(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None) -> Dict[str, str]:
        results = {
            "wecom": self._push_wecom(markdown_text),
            "dingtalk": self._push_dingtalk(markdown_text),
            "feishu": self._push_feishu(markdown_text),
            "email": self._send_email(markdown_text, html_text, date_str, pdf_path),
        }
        for k, v in results.items():
            logger.info("推送 %s：%s", k, v)
        return results

    def _post_json(self, url: str, payload: dict, timeout: int = 15) -> bool:
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.error("推送失败 %s：%s", url[:60], exc)
            return False

    def _push_wecom(self, text: str) -> str:
        url = self.config.wecom_webhook
        if not url:
            return "跳过（未配置）"
        ok = self._post_json(
            url,
            {"msgtype": "markdown", "markdown": {"content": _truncate(text, WECOM_LIMIT, by_bytes=True)}},
        )
        return "成功" if ok else "失败"

    def _push_dingtalk(self, text: str) -> str:
        url = self.config.dingtalk_webhook
        if not url:
            return "跳过（未配置）"
        if self.config.dingtalk_secret:
            timestamp = str(round(time.time() * 1000))
            string_to_sign = f"{timestamp}\n{self.config.dingtalk_secret}"
            sign = urllib.parse.quote_plus(
                base64.b64encode(
                    hmac.new(
                        self.config.dingtalk_secret.encode(),
                        string_to_sign.encode(),
                        hashlib.sha256,
                    ).digest()
                )
            )
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}timestamp={timestamp}&sign={sign}"
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "全球安防态势日报", "text": _truncate(text, DINGTALK_LIMIT)},
        }
        ok = self._post_json(url, payload)
        return "成功" if ok else "失败"

    def _push_feishu(self, text: str) -> str:
        url = self.config.feishu_webhook
        if not url:
            return "跳过（未配置）"
        ok = self._post_json(url, {"msg_type": "text", "content": {"text": _truncate(text, FEISHU_LIMIT)}})
        return "成功" if ok else "失败"

    def _send_email(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None) -> str:
        cfg = self.config
        if not (cfg.smtp_host and cfg.email_to):
            return "跳过（未配置）"
        try:
            import smtplib
            from email.mime.application import MIMEApplication
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(html_text, "html", "utf-8"))
            alt.attach(MIMEText(markdown_text, "plain", "utf-8"))

            msg = MIMEMultipart("mixed")
            msg["Subject"] = f"全球安防态势日报 · {date_str}"
            msg["From"] = cfg.smtp_from or cfg.smtp_user
            msg["To"] = ", ".join(cfg.email_to)
            msg.attach(alt)

            if pdf_path is not None and pdf_path.exists():
                pdf_bytes = pdf_path.read_bytes()
                filename = f"daily_brief_{date_str}.pdf"
                part = MIMEApplication(pdf_bytes, _subtype="pdf", Name=filename)
                part.add_header("Content-Disposition", "attachment", filename=filename)
                msg.attach(part)

            if cfg.smtp_port == 465:
                server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20)
                server.starttls()
            if cfg.smtp_user:
                server.login(cfg.smtp_user, cfg.smtp_pass)
            server.sendmail(msg["From"], cfg.email_to, msg.as_string())
            server.quit()
            return "成功"
        except Exception as exc:
            logger.error("邮件发送失败：%s", exc)
            return "失败"
