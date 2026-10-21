import logging
import html
import io
import smtplib
import threading
from collections import Counter
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Dict, List
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests

from server.user_runtime import sanitize_execution_results

try:
    from main import _log_ctx
except ImportError:
    _log_ctx = threading.local()

logger = logging.getLogger(__name__)


class MessagePusher:
    STATUS_EMOJIS = {"success": "✅", "fail": "❌", "pending": "⏳", "skip": "⏭️", "unknown": "❓"}
    SUPPORTED_TYPES = {"Server", "SMTP", "PushPlus", "ClawBot"}
    SMTP_HOST = "smtp.qq.com"
    SMTP_PORT = 465

    def __init__(self, push_config: list | None):
        self.push_config = push_config or []

    def push(self, results: List[Dict[str, Any]]) -> list:
        if any(isinstance(cfg, dict) and cfg.get("fallbackEnabled") for cfg in self.push_config):
            return self._push_fallback(results)
        delivery_states = []
        skip_count = sum(1 for result in results if result.get("status") == "skip")
        if results and skip_count == len(results):
            logger.info("所有任务均被跳过，不发送推送消息")
            return delivery_states

        success_count = sum(result.get("status") == "success" for result in results)
        title = f"{'🎉' if success_count == len(results) else '📋'} 工学云报告({success_count}/{len(results)})"
        if len(results) == 1 and results[0].get("task_type") == "异常恢复通知":
            title = "✅ 工学云考勤异常已恢复"

        for service_config in self.push_config:
            if not isinstance(service_config, dict):
                continue
            service_type = str(service_config.get("type") or "").strip()
            if service_type not in self.SUPPORTED_TYPES:
                continue
            if not service_config.get("enabled", False):
                continue
            try:
                if service_type == "Server":
                    self._server_push(service_config, title, self._generate_markdown_message(results))
                    delivery_states.append({"type": "Server", "status": "sent"})
                elif service_type in {"PushPlus", "ClawBot"}:
                    from server.pushplus_delivery import send_message
                    content = self._generate_html_message(results).replace("</body></html>", "")
                    for result in self._verification_results(results):
                        details = result["details"]
                        direct_url = self._safe_alipay_url(details.get("registerUrl"))
                        browser_url = self._alipay_browser_url(direct_url)
                        content += '<h3>签到需要授权</h3><p>微信可能拦截支付宝跳转，请复制链接到浏览器或支付宝打开。</p>'
                        if service_config.get("uploadQr") and service_config.get("secretKey"):
                            try:
                                from server.pushplus_delivery import upload_qr
                                image_url = upload_qr(service_config, self._qr_png(direct_url))
                                content += '<img width="320" src="' + html.escape(image_url, quote=True) + '" alt="授权二维码" />'
                            except Exception as exc:
                                logger.warning("PushPlus 二维码上传失败: %s", type(exc).__name__)
                                content += '<p>二维码上传失败，请使用以下链接或查看邮件二维码。</p>'
                        else:
                            content += '<p>未启用官方图片上传，二维码请查看邮件或管理页面。</p>'
                        content += '<p><a href="' + html.escape(browser_url, quote=True) + '">打开支付宝授权</a></p><p>复制链接：</p><code>' + html.escape(direct_url) + '</code><p>授权链接请勿转发。完成授权不代表签到成功，请回查考勤结果。</p>'
                    state = send_message(service_config, title, content + "</body></html>")
                    delivery_states.append({"type": service_type, "status": state})
                elif service_type == "SMTP":
                    verification_results = self._verification_results(results)
                    for result in verification_results:
                        state = self._smtp_verification_push(service_config, result)
                        delivery_states.append({"type": "SMTP", "status": state})
                    normal_results = [result for result in results if result not in verification_results]
                    if normal_results:
                        normal_config = dict(service_config)
                        if len(normal_results) == 1:
                            notice = normal_results[0]
                            incident = (notice.get("details") or {}).get("通知事件")
                            if incident:
                                normal_config.update(incident_id=incident,
                                    incident_phase="recovery" if notice.get("task_type") == "异常恢复通知" else "alert")
                        state = self._smtp_push(
                            normal_config,
                            title,
                            self._generate_html_message(normal_results),
                        )
                        delivery_states.append({"type": "SMTP", "status": state})
            except Exception as exc:
                logger.error("%s 消息推送失败: %s", service_type, type(exc).__name__)
                state = "uncertain" if service_type in {"PushPlus", "ClawBot"} and isinstance(exc, (requests.Timeout, requests.ConnectionError)) else "enqueue_failed"
                delivery_states.append({"type": service_type, "status": state})
        return delivery_states

    def _push_fallback(self, results):
        states = []
        for kind in ("ClawBot", "PushPlus", "SMTP"):
            config = next((cfg for cfg in self.push_config if isinstance(cfg, dict)
                           and cfg.get("type") == kind and cfg.get("enabled")), None)
            if config is None:
                continue
            # One attempt per channel; unknown online delivery falls forward, never replayed.
            config = {**config, "fallbackEnabled": False, "confirmDelivery": True}
            attempt = MessagePusher([config]).push(results)
            states.extend(attempt)
            if kind != "SMTP" and any(item.get("status") == "provider_sent" for item in attempt):
                break
        return states

    @staticmethod
    def _safe_alipay_url(value: Any) -> str:
        url = str(value or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "alipays" or not parsed.netloc:
            return ""
        return url

    @classmethod
    def _verification_results(cls, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        matched = []
        for result in results:
            if not isinstance(result, dict):
                continue
            details = result.get("details")
            if not isinstance(details, dict):
                continue
            if details.get("verification_type") not in {"account", "face"}:
                continue
            if not cls._safe_alipay_url(details.get("registerUrl")):
                continue
            matched.append(result)
        return matched

    @classmethod
    def _alipay_browser_url(cls, direct_url: str) -> str:
        url = cls._safe_alipay_url(direct_url)
        if not url:
            raise ValueError("支付宝授权链接无效")
        return urlunsplit(("https", "ds.alipay.com", "/", urlencode({"scheme": url}), ""))

    @staticmethod
    def _qr_png(content: str) -> bytes:
        # 本地生成二维码，不把授权链接发送给第三方二维码服务。
        import qrcode

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=4,
        )
        qr.add_data(content)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def _smtp_verification_push(
        self,
        config: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        config = dict(config)
        session_id = (result.get("details") or {}).get("verification_session_id")
        if session_id:
            config["verification_session_id"] = session_id
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "").strip()
        to = str(config.get("to") or "").strip()
        from_name = str(config.get("from") or "工学云签到通知").strip()
        if not username or not password or not to:
            raise ValueError("SMTP 配置缺少 username/password/to")

        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        direct_url = self._safe_alipay_url(details.get("registerUrl"))
        if not direct_url:
            raise ValueError("支付宝授权链接无效")
        browser_url = self._alipay_browser_url(direct_url)
        verification_type = str(details.get("verification_type") or "account")
        type_text = "支付宝人脸识别" if verification_type == "face" else "支付宝安全验证"
        target_type = {"START": "上班", "END": "下班"}.get(
            str(details.get("target_type") or "").upper(),
            str(details.get("target_type") or "签到"),
        )
        title = f"⚠️ 工学云{target_type}签到需要{type_text}"
        safe_message = html.escape(str(result.get("message") or "签到需要授权"))
        safe_direct_url = html.escape(direct_url, quote=True)
        safe_browser_url = html.escape(browser_url, quote=True)
        content = f"""
        <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
        <style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7;color:#1f2328;padding:20px}}.card{{max-width:620px;border:1px solid #d0d7de;border-radius:10px;padding:20px}}.button{{display:inline-block;background:#1677ff;color:#fff!important;text-decoration:none;padding:10px 18px;border-radius:6px}}code{{display:block;word-break:break-all;background:#f6f8fa;padding:10px;border-radius:6px}}</style>
        </head><body><div class="card">
        <h2>工学云签到需要授权</h2><p>{safe_message}</p>
        <p><strong>签到类型：</strong>{html.escape(target_type)}</p>
        <p>请使用手机扫描二维码，或点击下面的链接打开支付宝完成验证。</p>
        <p><img src="cid:gxy-verification-qr" alt="支付宝授权二维码" width="360" height="360"></p>
        <p><a class="button" href="{safe_browser_url}">打开支付宝授权</a></p>
        <p><strong>复制链接：</strong></p><code>{safe_direct_url}</code>
        <p>完成验证后，返回工学云管理页面确认本次考勤结果。授权链接只发送到当前配置的收件邮箱，请勿转发。</p>
        </div></body></html>
        """

        msg = MIMEMultipart("related")
        msg["From"] = formataddr((Header(from_name, "utf-8").encode(), username))
        msg["To"] = to
        msg["Subject"] = Header(title, "utf-8").encode()
        msg.attach(MIMEText(content, "html", "utf-8"))
        qr_image = MIMEImage(self._qr_png(direct_url), _subtype="png")
        qr_image.add_header("Content-ID", "<gxy-verification-qr>")
        qr_image.add_header("Content-Disposition", "inline", filename="gongxueyun-authorization.png")
        msg.attach(qr_image)

        return self._deliver_smtp(config, msg)

    @staticmethod
    def _deliver_smtp(config, msg):
        from server.mail_delivery import enqueue_and_send
        status = enqueue_and_send(config, msg)
        logger.info("SMTP 邮件状态: %s", status)
        return status

    def _server_push(self, config: Dict[str, Any], title: str, content: str) -> None:
        send_key = str(config.get("sendKey") or "").strip()
        if not send_key:
            raise ValueError("Server 酱 sendKey 不能为空")
        url = f"https://sctapi.ftqq.com/{send_key}.send"
        rsp = requests.post(url, data={"title": title, "desp": content}, timeout=15).json()
        if rsp.get("code") != 0:
            raise RuntimeError(rsp.get("message") or "Server 酱推送失败")
        logger.info("Server 酱推送成功")

    def _smtp_push(self, config: Dict[str, Any], title: str, content: str) -> None:
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "").strip()
        to = str(config.get("to") or "").strip()
        from_name = str(config.get("from") or "工学云签到通知").strip()
        if not username or not password or not to:
            raise ValueError("SMTP 配置缺少 username/password/to")

        msg = MIMEMultipart()
        msg["From"] = formataddr((Header(from_name, "utf-8").encode(), username))
        msg["To"] = to
        msg["Subject"] = Header(title, "utf-8").encode()
        msg.attach(MIMEText(content, "html", "utf-8"))

        return self._deliver_smtp(config, msg)

    @classmethod
    def _generate_markdown_message(cls, results: List[Dict[str, Any]]) -> str:
        results = sanitize_execution_results(results)
        status_counts = Counter(result.get("status", "unknown") for result in results)
        total_tasks = len(results)
        parts = [
            "# 工学云任务执行报告\n\n",
            "## 执行统计\n\n",
            f"- 总任务数：{total_tasks}\n",
            f"- 成功：{status_counts['success']}\n",
            f"- 失败：{status_counts['fail']}\n",
            f"- 跳过：{status_counts['skip']}\n\n",
            "## 详细任务报告\n\n",
        ]
        for result in results:
            task_type = result.get("task_type", "未知任务")
            status = result.get("status", "unknown")
            status_emoji = cls.STATUS_EMOJIS.get(status, cls.STATUS_EMOJIS["unknown"])
            parts.extend(
                [
                    f"### {status_emoji} {task_type}\n\n",
                    f"**状态：** {status}\n\n",
                    f"**结果：** {result.get('message', '无消息')}\n\n",
                ]
            )
            details = result.get("details")
            if isinstance(details, dict) and details:
                parts.append("**详细信息：**\n\n")
                for key, value in details.items():
                    parts.append(f"- **{key}**：{value}\n")
                parts.append("\n")
            report_content = result.get("report_content")
            if isinstance(report_content, str) and report_content.strip():
                parts.extend(["**报告：**\n\n", f"```\n{report_content}\n```\n\n"])
            parts.append("---\n\n")
        return "".join(parts)

    @classmethod
    def _generate_html_message(cls, results: List[Dict[str, Any]]) -> str:
        results = sanitize_execution_results(results)
        status_counts = Counter(result.get("status", "unknown") for result in results)
        total_tasks = len(results)
        html = [
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            "<title>工学云任务执行报告</title>",
            '<style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6;padding:20px;color:#1f2328;}h1{margin-bottom:16px;}h2{margin-top:24px;}pre{white-space:pre-wrap;background:#f6f8fa;padding:12px;border-radius:6px;}.card{border:1px solid #d0d7de;border-radius:8px;padding:16px;margin-bottom:16px;}.muted{color:#57606a;}</style>',
            "</head><body>",
            "<h1>工学云任务执行报告</h1>",
            f'<p class="muted">总任务数：{total_tasks} / 成功：{status_counts["success"]} / 失败：{status_counts["fail"]} / 跳过：{status_counts["skip"]}</p>',
            "<h2>详细任务报告</h2>",
        ]
        for result in results:
            task_type = result.get("task_type", "未知任务")
            status = result.get("status", "unknown")
            html.append('<div class="card">')
            html.append(f'<h3>{cls.STATUS_EMOJIS.get(status, cls.STATUS_EMOJIS["unknown"])} {task_type}</h3>')
            html.append(f'<p><strong>状态：</strong>{status}</p>')
            html.append(f'<p><strong>结果：</strong>{result.get("message", "无消息")}</p>')
            details = result.get("details")
            if isinstance(details, dict) and details:
                html.append("<ul>")
                for key, value in details.items():
                    html.append(f"<li><strong>{key}：</strong>{value}</li>")
                html.append("</ul>")
            report_content = result.get("report_content")
            if isinstance(report_content, str) and report_content.strip():
                html.append(f"<pre>{report_content}</pre>")
            html.append("</div>")
        html.append("</body></html>")
        return "".join(html)


def send_test_smtp_message(config: Dict[str, Any]) -> str:
    import uuid
    smtp_config = dict(config or {})
    smtp_config["delivery_nonce"] = uuid.uuid4().hex
    username = str(smtp_config.get("username") or "").strip()
    smtp_config["to"] = username
    title = "工学云 SMTP 测试邮件"
    content = "<p>这是一封 SMTP 测试邮件，说明当前 QQ 邮箱 SMTP 配置可用。</p>"
    status = MessagePusher([])._smtp_push(smtp_config, title, content)
    if status != "sent":
        raise RuntimeError(f"SMTP 测试未确认发送，队列状态：{status}")
    return username
