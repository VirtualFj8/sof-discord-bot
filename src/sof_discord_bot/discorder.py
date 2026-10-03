from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

import requests
from dotenv import load_dotenv

from .logging_utils import get_logger

logger = get_logger(__name__)

_WEBHOOK_ENV_KEYS = ("DISCORD_WEBHOOK_URL", "DISCORD_WEBHOOK_URL_2")


def _webhook_urls() -> list[tuple[str, str]]:
    load_dotenv()
    return [(key, url) for key in _WEBHOOK_ENV_KEYS if (url := os.getenv(key))]


def _mask_webhook(url: str) -> str:
    """Return a log-safe webhook identifier (id + last 4 of token, never the secret)."""
    try:
        # https://discord.com/api/webhooks/<id>/<token>[?wait=true]
        base = url.split("?", 1)[0].rstrip("/")
        parts = base.split("/")
        if len(parts) >= 2:
            wid, token = parts[-2], parts[-1]
            return f"id={wid} token=...{token[-4:]}" if len(token) >= 4 else f"id={wid} token=...?"
        return "..." + base[-12:]
    except Exception:
        return "(unparseable)"


def _with_wait(url: str) -> str:
    """Append ?wait=true so Discord returns the created message JSON (verifiable id).

    Without it Discord replies 204 with an empty body, which proves the POST was
    accepted but gives no message/channel id to correlate in logs.
    """
    if "wait=" in url:
        return url
    return url + ("&wait=true" if "?" in url else "?wait=true")


def _parse_message_response(response) -> tuple[str | None, str | None]:
    """Extract (message_id, channel_id) from a Discord ?wait=true response, else (None, None)."""
    try:
        body = response.json()
        if isinstance(body, dict):
            mid = body.get("id")
            cid = body.get("channel_id")
            return (str(mid) if mid else None, str(cid) if cid else None)
    except Exception:
        pass
    return None, None


def _truncate(text: str | None, limit: int = 500) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + f"...[truncated {len(text)-limit} chars]"


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




def send_to_discord(payload: dict) -> dict[str, dict]:
    """POST a JSON payload to all configured webhooks with ?wait=true.

    Returns per-webhook results: {env_key: {"ok": bool, "status": int|None,
    "message_id": str|None, "channel_id": str|None, "error": str|None}}.
    Success is only logged when Discord returns 2xx AND (with wait=true) a
    message id — otherwise it is an ERROR so journald no longer shows a false
    'Message sent'.
    """
    webhooks = _webhook_urls()
    results: dict[str, dict] = {}
    if not webhooks:
        logger.error("No Discord webhook URLs configured. Skipping Discord send.")
        return results
    for env_key, webhook_url in webhooks:
        target = _with_wait(webhook_url)
        who = f"{env_key}({_mask_webhook(webhook_url)})"
        try:
            response = requests.post(target, json=payload, timeout=8)
            status = response.status_code
            if status not in (200, 204):
                err = _truncate(response.text)
                # Surface rate-limit waits explicitly (Discord 429 {"retry_after": X}).
                try:
                    retry_after = response.json().get("retry_after") if status == 429 else None
                except Exception:
                    retry_after = None
                extra = f" retry_after={retry_after}s" if retry_after is not None else ""
                logger.error(
                    "Discord send FAILED (%s): status=%s%s body=%s",
                    who, status, extra, err,
                )
                results[env_key] = {"ok": False, "status": status, "message_id": None, "channel_id": None, "error": err}
                continue
            message_id, channel_id = _parse_message_response(response)
            if status == 204 or message_id is None:
                # Accepted but unverified (no ?wait support / empty body). Treat as
                # suspicious, not success, so callers investigate instead of assuming.
                logger.warning(
                    "Discord send UNVERIFIED (%s): status=%s accepted but no message id returned (no ?wait JSON).",
                    who, status,
                )
                results[env_key] = {"ok": False, "status": status, "message_id": None, "channel_id": channel_id, "error": "no-message-id"}
            else:
                logger.info(
                    "Discord send VERIFIED (%s): status=%s message_id=%s channel_id=%s",
                    who, status, message_id, channel_id,
                )
                results[env_key] = {"ok": True, "status": status, "message_id": message_id, "channel_id": channel_id, "error": None}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Discord send EXCEPTION (%s): %s", who, exc)
            results[env_key] = {"ok": False, "status": None, "message_id": None, "channel_id": None, "error": str(exc)}
    return results


def upload_image_to_discord(file_path: str, payload: Optional[dict] = None) -> dict[str, dict]:
    """Upload an image file to all Discord webhooks as multipart form data.

    Uses ?wait=true so success returns a message JSON with id/channel_id.
    Returns per-webhook results: {env_key: {"ok": bool, "status": int|None,
    "message_id": str|None, "channel_id": str|None, "bytes": int, "error": str|None}}.
    Only 2xx WITH a message id counts as ok=True; 204/empty body is UNVERIFIED
    (ok=False) so the watcher logs FAILED/PARTIAL instead of a false 'uploaded'.
    """
    webhooks = _webhook_urls()
    results: dict[str, dict] = {}
    if not webhooks:
        logger.error("No Discord webhook URLs configured. Skipping Discord upload.")
        return results
    data = payload or {}
    basename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as fp:
            file_bytes = fp.read()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to read image for Discord upload: %s", exc)
        for env_key, _ in webhooks:
            results[env_key] = {"ok": False, "status": None, "message_id": None, "channel_id": None, "bytes": 0, "error": f"read-failed: {exc}"}
        return results
    nbytes = len(file_bytes)
    for env_key, webhook_url in webhooks:
        target = _with_wait(webhook_url)
        who = f"{env_key}({_mask_webhook(webhook_url)})"
        try:
            files = {"file": (basename, file_bytes, "image/png")}
            response = requests.post(
                target,
                data={"payload_json": json_dumps(data)},
                files=files,
                timeout=20,
            )
            status = response.status_code
            if status not in (200, 204):
                err = _truncate(response.text)
                try:
                    retry_after = response.json().get("retry_after") if status == 429 else None
                except Exception:
                    retry_after = None
                extra = f" retry_after={retry_after}s" if retry_after is not None else ""
                logger.error(
                    "Discord upload FAILED (%s): status=%s%s bytes=%d file=%s body=%s",
                    who, status, extra, nbytes, basename, err,
                )
                results[env_key] = {"ok": False, "status": status, "message_id": None, "channel_id": None, "bytes": nbytes, "error": err}
                continue
            message_id, channel_id = _parse_message_response(response)
            if status == 204 or message_id is None:
                logger.warning(
                    "Discord upload UNVERIFIED (%s): status=%s accepted but no message id returned bytes=%d file=%s.",
                    who, status, nbytes, basename,
                )
                results[env_key] = {"ok": False, "status": status, "message_id": None, "channel_id": channel_id, "bytes": nbytes, "error": "no-message-id"}
            else:
                logger.info(
                    "Discord upload VERIFIED (%s): status=%s bytes=%d file=%s message_id=%s channel_id=%s",
                    who, status, nbytes, basename, message_id, channel_id,
                )
                results[env_key] = {"ok": True, "status": status, "message_id": message_id, "channel_id": channel_id, "bytes": nbytes, "error": None}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Discord upload EXCEPTION (%s): bytes=%d file=%s: %s", who, nbytes, basename, exc)
            results[env_key] = {"ok": False, "status": None, "message_id": None, "channel_id": None, "bytes": nbytes, "error": str(exc)}
    return results


def json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, separators=(",", ":"))
