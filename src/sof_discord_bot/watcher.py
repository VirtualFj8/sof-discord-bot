import os
from typing import Optional

from .scoreboard import gen_scoreboard_init, generate_screenshot_for_port, postprocess_upload_match_image
from .exporter import read_data_from_sof_server
from .discorder import generate_payload, send_to_discord, upload_image_to_discord
from .logging_utils import get_logger
from .trigger_client import DEFAULT_HOST, DEFAULT_PORT, subscribe_forever

logger = get_logger(__name__)


class DiscordTriggerHandler:
    """Handles discord trigger events from the sof-export-fire socket bus.

    File watching, cooldown, settle, and trigger_seq dedup all live in the
    separately-installed export-fire server; this class is pure Discord
    domain logic per event dict.
    """

    def handle_trigger(self, event: dict) -> None:
        port = event.get("port", "?")
        logger.info(
            "Received trigger %s seq=%s for port %s",
            event.get("name"), event.get("seq"), port,
        )
        sofplus_data_path = event.get("data_dir") or ("../user-%s/sofplus/data" % port)
        if not os.path.exists(sofplus_data_path):
            logger.error("Directory does not exist: %s", sofplus_data_path)
            return
        exported_data = read_data_from_sof_server(port, sofplus_data_path)
        if exported_data is None:
            return
        # Skip if there are zero active (non-spectator) players
        players = exported_data.get("players", [])
        active_count = 0
        for p in players:
            if not p:
                continue
            try:
                if int(p.get("spectator", 0) or 0) != 0:
                    continue
            except Exception:
                pass
            active_count += 1
        if active_count == 0:
            logger.info("No active players; skipping screenshot and Discord notification.")
            return
            
        # Build and send Discord notification (optional, requires DISCORD_WEBHOOK_URL)
        try:
            server = exported_data.get("server", {})
            players = exported_data.get("players", [])
            red_team_names: list[str] = []
            blue_team_names: list[str] = []
            total_players = 0
            for p in players:
                if not p:
                    continue
                try:
                    if int(p.get("spectator", 0) or 0) != 0:
                        continue
                except Exception:
                    pass
                total_players += 1
                # Names are base64-encoded in files
                name_val = p.get("name", "")
                try:
                    import base64
                    decoded = base64.b64decode(name_val).decode("latin-1") if name_val else ""
                except Exception:
                    decoded = ""
                team_val = p.get("team")
                if team_val == 1:
                    blue_team_names.append(decoded)
                elif team_val == 2:
                    red_team_names.append(decoded)

            caller_slot = server.get("slot")
            caller_name = None
            if isinstance(caller_slot, int) and 0 <= caller_slot < len(players):
                slot_player = players[caller_slot]
                if slot_player:
                    try:
                        import base64
                        caller_name = base64.b64decode(slot_player.get("name", "")).decode("latin-1")
                    except Exception:
                        caller_name = ""
            caller_name = caller_name or ""

            mode = server.get("mode") or ""
            custom_text = server.get("msg") or None

            # Determine needed players for match request modes
            needed_players: Optional[int] = None
            if mode in {".match1", ".want1"}:
                needed_players = 1
            elif mode in {".match2", ".want2"}:
                needed_players = 2

            # Default description if not provided via custom_text
            if mode in {".wantmatch", ".match1", ".match2", ".want1", ".want2", ".wantplay"}:
                custom_msg = custom_text or "Players on the server want a match. Who's in?"

                
            mode = server.get("mode") or ""
            if mode == ".upload_match":
                image_path = generate_screenshot_for_port(port, sofplus_data_path, exported_data)
                if image_path:
                    # Post-process image per upload-match rules (overlay + crop)
                    processed_path = postprocess_upload_match_image(image_path, exported_data)
                    final_path = processed_path or image_path
                    # Upload as file to webhook so it lives in Discord
                    upload_image_to_discord(final_path, {})
            else:
                payload = generate_payload(
                    caller_name=caller_name,
                    red_team=red_team_names,
                    blue_team=blue_team_names,
                    custom_msg=custom_msg,
                    total_players=total_players,
                    image_url=None,
                    mode=mode,
                    needed_players=needed_players,
                    map_name=server.get("map_current"),
                    hostname=server.get("hostname"),
                )
                send_to_discord(payload)
        except Exception:
            logger.exception("Failed to prepare or send Discord notification")


def _export_fire_port() -> int:
    try:
        return int(os.environ.get("SOF_EXPORT_FIRE_PORT", str(DEFAULT_PORT)))
    except (TypeError, ValueError):
        logger.warning("Bad SOF_EXPORT_FIRE_PORT %r; using default %d",
                       os.environ.get("SOF_EXPORT_FIRE_PORT"), DEFAULT_PORT)
        return DEFAULT_PORT


def run_watcher() -> None:
    sof_dir = os.path.dirname(os.getcwd())
    gen_scoreboard_init(sof_dir)
    host = os.environ.get("SOF_EXPORT_FIRE_HOST", DEFAULT_HOST)
    port = _export_fire_port()
    handler = DiscordTriggerHandler()
    logger.info("Subscribing to discord triggers on %s:%d ...", host, port)
    subscribe_forever(host, port, ["discord"], handler.handle_trigger)
