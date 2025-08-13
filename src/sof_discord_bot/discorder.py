from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

import requests
from dotenv import load_dotenv

from .logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class Player:
    name: str
    team: str


def _ordinal_day(now: datetime) -> str:
    day = now.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return f"{day}{suffix}"


def format_request_datetime(now: datetime | None = None) -> str:
    now = now or datetime.now()
    weekday = now.strftime("%A")
    month = now.strftime("%B")
    time_12h = now.strftime("%I:%M%p").lstrip("0")
    time_24h = now.strftime("%H:%M")
    return f"**{weekday}, {_ordinal_day(now)} {month} {time_12h} ({time_24h})**"


def generate_payload(
    caller_name: str,
    red_team: Iterable[str],
    blue_team: Iterable[str],
    custom_msg: str | None = None,
    total_players: int | None = None,
    image_url: str | None = None,
) -> dict:
    fields: List[dict] = [
        {"name": "Red team", "value": ", ".join(list(red_team)) or "None", "inline": True},
        {"name": "Blue team", "value": ", ".join(list(blue_team)) or "None", "inline": False},
    ]
    if total_players is not None:
        fields.append({"name": "Total players", "value": str(total_players), "inline": True})

    embed: dict = {
        "title": "SoF Live Scoreboard",
        "description": custom_msg or "Now in-game",
        "url": "https://www.sof1.org/",
        "color": 3447003,
        "thumbnail": {"url": "https://www.sof1.org/gallery/image/7656/medium"},
        "author": {
            "name": caller_name,
            "url": "https://www.sof1.org/",
            "icon_url": "https://www.sof1.org/gallery/image/7656/medium",
        },
        "fields": fields,
        "footer": {"text": "Sent from SoF Server", "icon_url": "https://www.sof1.org/gallery/image/7656/medium"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if image_url:
        embed["image"] = {"url": image_url}

    return {
        "username": "🔴 [LIVE] SoF Gamers",
        "avatar_url": "https://www.sof1.org/gallery/image/7656/medium",
        "content": "\n\u200b\n 🕹️ **SCOREBOARD** 🕹️\n\u200b\n ",
        "embeds": [embed],
    }


def send_to_discord(payload: dict) -> None:
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL is not set. Skipping Discord send.")
        return
    try:
        response = requests.post(webhook_url, json=payload, timeout=8)
        if response.status_code not in (200, 204):
            logger.error("Error sending message to Discord: %s - %s", response.status_code, response.text)
        else:
            logger.info("Message sent to Discord.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send message to Discord: %s", exc)
