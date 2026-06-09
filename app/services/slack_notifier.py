from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from app.core import config


logger = logging.getLogger(__name__)


def _now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")


def _field(label: str, value: str) -> dict[str, Any]:
    clean_value = (value or "미지정").strip() or "미지정"
    return {"type": "mrkdwn", "text": f"*{label}*\n{clean_value}"}


def build_slack_payload(
    *,
    title: str,
    severity: str,
    priority: str,
    status: str,
    reporter: str,
    notion_url: str,
    registered_at: str | None = None,
) -> dict[str, Any]:
    registered_at = registered_at or _now_kst()
    clean_title = (title or "제목 없음").strip()
    clean_notion_url = (notion_url or "").strip()

    payload: dict[str, Any] = {
        "text": f"신규 결함 등록: {clean_title}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🐞 신규 결함 등록", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    _field("제목", clean_title),
                    _field("심각도", severity),
                    _field("우선순위", priority),
                    _field("상태", status),
                    _field("등록자", reporter),
                    _field("등록일시", registered_at),
                ],
            },
            {"type": "divider"},
        ],
    }
    if config.SLACK_CHANNEL_NAME:
        payload["channel"] = f"#{config.SLACK_CHANNEL_NAME.lstrip('#')}"
    if clean_notion_url:
        payload["blocks"].append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "결함 보기", "emoji": True},
                        "url": clean_notion_url,
                    }
                ],
            }
        )
    return payload


def send_slack_notification(
    *,
    title: str,
    severity: str,
    priority: str,
    status: str,
    reporter: str,
    notion_url: str,
) -> bool:
    if not config.SLACK_NOTIFY_ENABLED:
        logger.info("[SLACK] Notification skipped: disabled")
        return False
    webhook_url = config.SLACK_WEBHOOK_URL
    if not webhook_url:
        logger.warning("[SLACK] Notification skipped: SLACK_WEBHOOK_URL is not set")
        return False

    logger.info("[SLACK] Notification started")
    payload = build_slack_payload(
        title=title,
        severity=severity,
        priority=priority,
        status=status,
        reporter=reporter,
        notion_url=notion_url,
    )
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("[WARN] [SLACK] Notification failed: %s", exc)
        return False

    logger.info("[SLACK] Notification sent")
    return True
