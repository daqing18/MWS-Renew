#!/usr/bin/env python3
"""Send renewal notifications through notify-gateway or Telegram.

The preferred path is notify-gateway. To keep the upgraded repository
compatible with the legacy MWS-Renew secrets, TG_BOT_TOKEN and TG_CHAT_ID are
used as a fallback when NOTIFY_URL is not configured.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

NOTIFY_URL = (os.environ.get("NOTIFY_URL") or "").strip()
NOTIFY_TOKEN = (os.environ.get("NOTIFY_TOKEN") or "").strip()
TG_BOT_TOKEN = (os.environ.get("TG_BOT_TOKEN") or "").strip()
TG_CHAT_ID = (os.environ.get("TG_CHAT_ID") or "").strip()

# Cloudflare returns error 1010 for urllib's default user agent.
NOTIFY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _notify_gateway(title, content, level, details, source):
    payload = {
        "source": source,
        "title": title,
        "content": content,
        "level": level,
        "channel": ["email", "telegram"],
        "data": details or {"total": 0, "success": 0, "failed": 0, "details": []},
    }
    req = urllib.request.Request(
        NOTIFY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer {}".format(NOTIFY_TOKEN),
            "Content-Type": "application/json",
            "User-Agent": NOTIFY_UA,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _notify_telegram(title, content, level):
    if not (TG_BOT_TOKEN and TG_CHAT_ID):
        print("[i] ??????????")
        return {"messageId": "not-configured"}

    prefix = {"success": "?", "partial": "??", "failed": "?"}.get(level, "??")
    text = "{}\n{}\n\n{}".format(prefix, title, content)
    payload = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text[:4000],
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot{}/sendMessage".format(TG_BOT_TOKEN),
        data=payload,
        headers={"User-Agent": NOTIFY_UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    print("[?] Telegram ?????")
    return result


def notify(title, content, level="success", details=None, source="puratya-renew"):
    if NOTIFY_URL:
        return _notify_gateway(title, content, level, details, source)
    return _notify_telegram(title, content, level)


if __name__ == "__main__":
    print(
        json.dumps(
            notify(
                "MWS ????",
                "??????",
                level="partial",
                details={
                    "total": 5,
                    "success": 3,
                    "failed": 2,
                    "details": [
                        {"id": "bot_001", "name": "Bot A", "status": "success"},
                        {"id": "bot_002", "name": "Bot B", "status": "failed", "error": "HTTP 403"},
                        {"id": "site_001", "name": "Site C", "status": "partial", "message": "1/2 ????"},
                    ],
                },
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
