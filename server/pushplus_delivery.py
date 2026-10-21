"""HTTPS-only provider calls, no automatic replay of uncertain submissions."""
from urllib.parse import urlsplit

import requests
import time


class PushPlusError(RuntimeError):
    pass


def send_message(config, title, content):
    token = str(config.get("token") or "").strip()
    if not token:
        raise PushPlusError("PushPlus Token 未配置")
    response = requests.post("https://www.pushplus.plus/send", json={
        "token": token, "title": title, "content": content,
        "template": "html", "channel": "clawbot" if config.get("type") == "ClawBot" else "wechat",
    }, timeout=(5, 20), allow_redirects=False)
    response.raise_for_status()
    result = response.json()
    if response.status_code != 200 or result.get("code") != 200:
        raise PushPlusError("PushPlus 未受理消息，请检查额度和配置")
    if config.get("confirmDelivery"):
        return confirm_delivery(config, result.get("data"))
    return "accepted"  # Provider acceptance is NOT proof of WeChat delivery.


def confirm_delivery(config, short_code):
    """Bounded read-only check. Unknown or delayed result must allow fallback."""
    if not isinstance(short_code, str) or not short_code or not config.get("secretKey"):
        return "accepted"
    try:
        response = requests.post("https://www.pushplus.plus/api/common/openApi/getAccessKey",
            json={"token": config["token"], "secretKey": config["secretKey"]},
            timeout=(3, 5), allow_redirects=False)
        response.raise_for_status()
        auth = response.json()
        key = (auth.get("data") or {}).get("accessKey") if auth.get("code") == 200 else None
        if not key:
            return "accepted"
        for attempt in range(3):
            if attempt:
                time.sleep(1)
            response = requests.get("https://www.pushplus.plus/api/open/message/sendMessageResult",
                params={"shortCode": short_code}, headers={"access-key": key},
                timeout=(3, 5), allow_redirects=False)
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 200:
                return "accepted"
            status = (result.get("data") or {}).get("status")
            if status == 2:
                return "provider_sent"  # Provider says sent; not a read receipt.
            if status == 3:
                return "failed"
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("PushPlus 投递回查不可用: %s", type(exc).__name__)
    return "accepted"


def upload_qr(config, png):
    """Explicit opt-in only: authorization QR becomes provider-hosted content."""
    def api(path, **kwargs):
        response = requests.request(url="https://www.pushplus.plus" + path,
                                    timeout=(5, 20), allow_redirects=False, **kwargs)
        response.raise_for_status()
        data = response.json()
        if response.status_code != 200 or data.get("code") != 200:
            raise PushPlusError("PushPlus 图片服务不可用")
        return data.get("data") or {}

    auth = api("/api/common/openApi/getAccessKey", method="POST",
               json={"token": config["token"], "secretKey": config["secretKey"]})
    key = auth.get("accessKey")
    if not key:
        raise PushPlusError("PushPlus 图片凭据无效")
    ticket = api("/api/open/userImage/uploadToken", method="GET", headers={"access-key": key})
    target = str(ticket.get("uploadUrl") or "")
    parsed = urlsplit(target)
    if parsed.scheme != "https" or parsed.hostname not in {"upload.qiniup.com", "upload-z1.qiniup.com", "upload-z2.qiniup.com", "upload-na0.qiniup.com", "upload-as0.qiniup.com"} or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise PushPlusError("图片上传地址不在允许范围")
    if not ticket.get("uploadToken"):
        raise PushPlusError("图片上传凭据缺失")
    response = requests.post(target, data={"token": ticket["uploadToken"]},
                             files={"file": ("verification.png", png, "image/png")},
                             timeout=(5, 20), allow_redirects=False)
    response.raise_for_status()
    data = response.json()
    url = str(data.get("url") or "")
    parsed = urlsplit(url)
    if data.get("errno") != 0 or parsed.scheme != "https" or parsed.hostname != "pic.pushplus.plus" or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise PushPlusError("图片服务返回无效地址")
    return url
