"""推送：企业微信 / 钉钉 / 飞书群机器人 + SMTP 邮件。未配置的渠道自动跳过。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime
from typing import Dict

import requests

from app.utils.logging import get_logger

logger = get_logger("pusher")


def _subject(date_str: str) -> str:
    """邮件主题：Global Security Newsletter - 日期 星期几。"""
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return f"Global Security Newsletter - {date_str} {weekdays[d.weekday()]}"

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

    def push(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None, poster_png=None) -> Dict[str, str]:
        results = {
            "wecom": self._push_wecom(markdown_text),
            "dingtalk": self._push_dingtalk(markdown_text),
            "feishu": self._push_feishu(markdown_text),
            "email": self._send_email(markdown_text, html_text, date_str, pdf_path, poster_png),
        }
        for k, v in results.items():
            logger.info("推送 %s：%s", k, v)
        return results

    def _post_json(self, url: str, payload: dict, timeout: int = 15) -> bool:
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            # Robot webhooks can report a delivery error with HTTP 200.
            result = resp.json()
            if not isinstance(result, dict):
                logger.error("推送失败：响应格式异常")
                return False
            code = result.get("errcode", result.get("code"))
            if code not in (0, "0"):
                logger.error("推送失败：接口返回业务错误")
                return False
            return True
        except Exception as exc:
            # URLs and request exceptions can contain the webhook token.
            logger.error("推送失败：%s", type(exc).__name__)
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

    def _build_message(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None, poster_png=None):
        """构建 MIME 邮件消息（不发送），供 SMTP 发送与 .eml 草稿文件共用。"""
        from email.mime.application import MIMEApplication
        from email.mime.image import MIMEImage
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        cfg = self.config
        # HTML 正文：优先内嵌海报长图（Outlook/QQ 像素一致），否则用表格版正文
        body = html_text
        inline_image = None
        if poster_png:
            body = (
                '<html><body style="margin:0;padding:0;background:#eef1f6;'
                "font-family:-apple-system,'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif;\">"
                f'<div style="padding:16px 20px;color:#6b7280;font-size:13px;text-align:center;">'
                f'🔍 安防行业日报 · {date_str} · 详情见 PDF 附件</div>'
                '<img src="cid:poster" style="width:100%;max-width:780px;display:block;margin:0 auto;border:0;">'
                '</body></html>'
            )
            inline_image = MIMEImage(poster_png, _subtype="png", Name="poster.png")
            inline_image.add_header("Content-ID", "<poster>")
            inline_image.add_header("Content-Disposition", "inline", filename="poster.png")

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "html", "utf-8"))
        alt.attach(MIMEText(markdown_text, "plain", "utf-8"))

        # 有内嵌图片时包一层 related，让 <img src="cid:poster"> 生效
        if inline_image is not None:
            related = MIMEMultipart("related")
            related.attach(alt)
            related.attach(inline_image)
        else:
            related = alt

        msg = MIMEMultipart("mixed")
        msg["Subject"] = _subject(date_str)
        msg["From"] = cfg.smtp_from or cfg.smtp_user
        msg["To"] = ", ".join(cfg.email_to) if cfg.email_to else ""
        if cfg.email_cc:
            msg["Cc"] = cfg.email_cc
        msg.attach(related)

        if pdf_path is not None and pdf_path.exists():
            pdf_bytes = pdf_path.read_bytes()
            filename = f"security_daily_report_{date_str}.pdf"
            part = MIMEApplication(pdf_bytes, _subtype="pdf", Name=filename)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        return msg

    def _all_recipients(self) -> list:
        """所有收件人（To + Cc 的邮箱地址），用于 SMTP 信封。"""
        import re
        to = list(self.config.email_to)
        cc = self.config.email_cc or ""
        cc_addrs = re.findall(r"<([^>]+)>", cc) or [a.strip() for a in cc.split(",") if a.strip()]
        return to + [a for a in cc_addrs if a not in to]

    def _send_email(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None, poster_png=None) -> str:
        cfg = self.config
        if not (cfg.smtp_host and cfg.email_to):
            return "跳过（未配置）"
        try:
            import smtplib
            msg = self._build_message(markdown_text, html_text, date_str, pdf_path, poster_png)

            connection = (
                smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20)
                if cfg.smtp_port == 465
                else smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20)
            )
            with connection as server:
                if cfg.smtp_port != 465:
                    server.ehlo()
                    if server.has_extn("starttls"):
                        server.starttls()
                        server.ehlo()
                    elif cfg.smtp_user:
                        raise smtplib.SMTPNotSupportedError("服务器不支持 STARTTLS，已拒绝明文认证")
                if cfg.smtp_user:
                    server.login(cfg.smtp_user, cfg.smtp_pass)
                server.sendmail(msg["From"], self._all_recipients(), msg.as_string())
            return "成功"
        except Exception as exc:
            logger.error("邮件发送失败：%s", exc)
            return "失败"

    def save_eml(self, markdown_text: str, html_text: str, date_str: str, pdf_path=None, poster_png=None, output_dir=None) -> str:
        """把邮件存为 .eml 草稿文件，用户双击可在 Outlook 里打开后手动发送。返回文件路径，失败返回空串。"""
        try:
            from pathlib import Path
            msg = self._build_message(markdown_text, html_text, date_str, pdf_path, poster_png)
            out_dir = Path(output_dir) if output_dir else Path(self.config.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            eml_path = out_dir / f"security_daily_report_{date_str}.eml"
            eml_path.write_bytes(msg.as_bytes())
            logger.info("邮件草稿 .eml 已写入 %s", eml_path)
            return str(eml_path)
        except Exception as exc:
            logger.error("生成 .eml 草稿失败：%s", exc)
            return ""

    def save_outlook_draft(self, html_text: str, date_str: str, pdf_path=None, poster_png=None) -> str:
        """通过 Outlook COM 生成「可编辑」草稿到 Outlook 草稿箱，用户可改收件人后手动发送。"""
        try:
            import win32com.client  # pyright: ignore[reportMissingImports]
        except Exception as exc:
            logger.warning("未安装 pywin32，跳过写入 Outlook 草稿箱：%s", exc)
            return "跳过（未安装 pywin32）"

        cfg = self.config
        if not cfg.email_to:
            return "跳过（无收件人）"

        png_file = None
        try:
            from pathlib import Path
            outlook = win32com.client.Dispatch("Outlook.Application")
            mail = outlook.CreateItem(0)  # 0 = olMailItem
            mail.To = "; ".join(cfg.email_to)
            if cfg.email_cc:
                mail.CC = cfg.email_cc.replace(",", "; ")
            mail.Subject = _subject(date_str)

            if poster_png:
                # 海报长图作为内嵌图片（cid:poster）——Outlook COM 需要绝对路径
                png_file = Path(self.config.output_dir).resolve() / f"_draft_poster_{date_str}.png"
                png_file.write_bytes(poster_png)
                att = mail.Attachments.Add(str(png_file))
                # PR_ATTACH_CONTENT_ID = 0x3712001E，设为 "poster" 让 cid:poster 引用生效
                att.PropertyAccessor.SetProperty(
                    "http://schemas.microsoft.com/mapi/proptag/0x3712001E", "poster"
                )
                mail.HTMLBody = (
                    '<html><body style="margin:0;padding:0;">'
                    '<img src="cid:poster" style="width:100%;max-width:780px;display:block;">'
                    '</body></html>'
                )
            else:
                mail.HTMLBody = html_text

            if pdf_path is not None and pdf_path.exists():
                mail.Attachments.Add(str(Path(pdf_path).resolve()))

            mail.Save()  # 保存到 Outlook 草稿箱
            logger.info("已写入 Outlook 草稿箱（%d 个收件人）", len(cfg.email_to))
            return "成功"
        except Exception as exc:
            logger.error("写入 Outlook 草稿箱失败：%s", exc)
            return "失败"
        finally:
            if png_file is not None:
                try:
                    png_file.unlink(missing_ok=True)
                except OSError:
                    pass
