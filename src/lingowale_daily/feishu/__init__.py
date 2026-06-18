"""飞书客户端：app bot 发卡片 + webhook 告警。"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from base64 import b64encode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from lingowale_daily.config import Settings

log = logging.getLogger(__name__)
_TIMEOUT = 15.0


class FeishuClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._token_expires: float = 0

    # ── token 管理 ──

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        self._token = self._fetch_token()
        self._token_expires = time.time() + 7000  # 实际 7200s，提前 200s 刷新
        return self._token

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), reraise=True)
    def _fetch_token(self) -> str:
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": self._settings.feishu_app_id,
                "app_secret": self._settings.feishu_app_secret,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        return data["tenant_access_token"]

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._ensure_token()}"}

    # ── 发送卡片 ──

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5), reraise=True)
    def send_template_card(
        self, chat_id: str, template_id: str, template_variable: dict
    ) -> None:
        """通过模板 ID + 变量发送卡片消息。"""
        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": _build_template_content(template_id, template_variable),
        }
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers=self._auth_headers(),
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送卡片失败: {data}")
        log.info("卡片已发送 chat_id=%s template=%s", chat_id, template_id)

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5), reraise=True)
    def send_raw_card(self, chat_id: str, card: dict) -> None:
        """发送动态构建的 card JSON（兜底）。"""
        import json

        payload = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        }
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers=self._auth_headers(),
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"发送 raw card 失败: {data}")

    # ── 告警（独立 webhook，不依赖 app token）──

    def alert(self, text: str) -> None:
        """通过自定义机器人 webhook 推告警，确保 app 挂了也能发。"""
        try:
            payload = self._build_webhook_payload(msg_type="text", content={"text": text})
            resp = httpx.post(
                self._settings.feishu_alert_webhook,
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            log.info("告警已发送: %s", text[:50])
        except Exception:
            log.error("告警发送也失败了！text=%s", text, exc_info=True)

    def send_card_webhook(self, card: dict) -> None:
        """通过 webhook 发送卡片消息。"""
        payload = self._build_webhook_payload(msg_type="interactive", card=card)
        resp = httpx.post(
            self._settings.feishu_alert_webhook,
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0 and data.get("StatusCode") != 0:
            # webhook 返回格式可能是 {"StatusCode":0} 或 {"code":0}
            if data.get("code") and data.get("code") != 0:
                raise RuntimeError(f"webhook 发卡片失败: {data}")
        log.info("卡片已通过 webhook 发送")

    def _build_webhook_payload(self, *, msg_type: str, **kwargs) -> dict:
        payload: dict = {"msg_type": msg_type}
        if msg_type == "text":
            payload["content"] = kwargs.get("content", {})
        elif msg_type == "interactive":
            payload["card"] = kwargs.get("card", {})

        secret = self._settings.feishu_alert_secret
        if secret:
            timestamp = str(int(time.time()))
            sign = _gen_sign(timestamp, secret)
            payload["timestamp"] = timestamp
            payload["sign"] = sign
        return payload


def _build_template_content(template_id: str, variables: dict) -> str:
    """构建模板卡片的 content JSON 字符串。"""
    import json

    return json.dumps(
        {
            "type": "template",
            "data": {"template_id": template_id, "template_variable": variables},
        },
        ensure_ascii=False,
    )


def _gen_sign(timestamp: str, secret: str) -> str:
    """飞书 webhook 签名。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.HMAC(
        string_to_sign.encode("utf-8"), msg=b"", digestmod=hashlib.sha256
    ).digest()
    return b64encode(hmac_code).decode("utf-8")
