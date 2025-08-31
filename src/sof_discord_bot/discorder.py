from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

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


def _strip_color_codes(value: str | None) -> str:
    """Remove in-game color control codes (bytes 1..31) from strings.
    Leaves regular printable characters intact. If value is None, returns empty string.
    """
    if not value:
        return ""
    try:
        return "".join(ch for ch in value if not (1 <= ord(ch) <= 31))
    except Exception:
        return value


def generate_payload(
    caller_name: str,
    red_team: Iterable[str],
    blue_team: Iterable[str],
    custom_msg: str | None = None,
    total_players: int | None = None,
    image_url: str | None = None,
    mode: str | None = None,
    needed_players: int | None = None,
    map_name: str | None = None,
    hostname: str | None = None,
    uploader: str | None = None,
) -> dict:
    # Always build match request style embeds (live scoreboard removed)
    fields: List[dict] = []

    # Sanitize names and hostname to remove color control codes for clean embeds
    caller_name_clean = _strip_color_codes(caller_name)
    red_team_clean = [ _strip_color_codes(n) for n in list(red_team) ]
    blue_team_clean = [ _strip_color_codes(n) for n in list(blue_team) ]
    hostname_clean = _strip_color_codes(hostname)

    title = "Match request"
    if needed_players:
        title = f"Match request: Need +{needed_players}"

    # Build an encouraging description
    parts: List[str] = []
    if custom_msg:
        parts.append(f"> {custom_msg}")
    if total_players is not None:
        if total_players <= 1:
            parts.append("There is a player on the server who wants a match.")
        else:
            parts.append("Some players on the server want a match.")
    else:
        parts.append("Players want a match.")
    parts.append("Interested? Jump in now!")
    description = "\n".join(parts)

    # Highlight needed players if applicable
    if needed_players is not None:
        fields.append({
            "name": "Needed",
            "value": f"+{needed_players} player(s)",
            "inline": True,
        })
    if total_players is not None:
        fields.append({
            "name": "Players online",
            "value": str(total_players),
            "inline": True,
        })

    # Context: map and server (inline)
    if map_name:
        fields.append({"name": "Map", "value": map_name, "inline": True})
    if hostname_clean:
        fields.append({"name": "Server", "value": hostname_clean, "inline": True})

    # Teams as bulleted lists
    red_list = "\n".join([f"• {n}" for n in red_team_clean]) or "None"
    blue_list = "\n".join([f"• {n}" for n in blue_team_clean]) or "None"
    fields.append({"name": "Red team", "value": red_list, "inline": True})
    fields.append({"name": "Blue team", "value": blue_list, "inline": True})

    # Color scheme tuned for urgency
    color = 0x2ECC71  # green
    if mode in {".match1", ".want1", ".wantplay"}:
        color = 0xF1C40F  # amber
    if mode in {".match2", ".want2"}:
        color = 0xE74C3C  # red

    embed: dict = {
        "title": title,
        "description": description,
        "url": "https://www.sof1.org/",
        "color": color,
        "thumbnail": {"url": "https://www.sof1.org/gallery/image/7656/medium"},
        "author": {
            "name": caller_name_clean + " is requesting a match!",
            "url": "https://www.sof1.org/",
            "icon_url": "https://www.sof1.org/gallery/image/7656/medium",
        },
        "fields": fields,
        "footer": {"text": "React if you're in. Sent from SoF Server", "icon_url": "https://www.sof1.org/gallery/image/7656/medium"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if image_url:
        embed["image"] = {"url": image_url}

    # Top-level `content` will appear above the embed; show uploader there if provided
    top_content = "\n\u200b\n 📣 **MATCH REQUEST** \n\u200b\n "
    if uploader:
        top_content = f"**Uploaded by:** {uploader}\n\n" + top_content

    # Add a visible placeholder field below the teams/image
    embed.setdefault("fields", []).append({"name": "Placeholder", "value": "(placeholder)", "inline": False})

    return {
        "username": "📣 Match Request",
        "avatar_url": "https://www.sof1.org/gallery/image/7656/medium",
        "content": top_content,
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


def upload_image_to_discord(file_path: str, payload: Optional[dict] = None) -> Optional[dict]:
    """Upload an image file to the Discord webhook as multipart form data.

    Returns the response JSON (if any) or None on failure. Many webhooks return an empty
    body on success (204), so callers should not rely on a JSON body being present.
    """
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL is not set. Skipping Discord upload.")
        return None
    try:
        data = payload or {}
        with open(file_path, "rb") as fp:
            files = {"file": (os.path.basename(file_path), fp, "image/png")}
            response = requests.post(webhook_url, data={"payload_json": json_dumps(data)}, files=files, timeout=20)
        if response.status_code not in (200, 204):
            logger.error("Error uploading image to Discord: %s - %s", response.status_code, response.text)
            return None
        try:
            return response.json()
        except Exception:
            return None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to upload image to Discord: %s", exc)
        return None


def json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, separators=(",", ":"))
