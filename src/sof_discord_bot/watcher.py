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

    def __init__(self) -> None:
        # Last seq seen per port, to spot restarts/replays/out-of-order delivery
        # in the logs (e.g. seq=1 arriving after seq=2 means the game server
        # restarted and its monotonic counter reset).
        self._last_seq: dict[str, int] = {}

    def handle_trigger(self, event: dict) -> None:
        port = event.get("port", "?")
        port_key = str(port)
        name = event.get("name")
        seq = event.get("seq")
        logger.info(
            "Received trigger %s seq=%s for port %s",
            name, seq, port,
        )
        # Warn on duplicate / out-of-order / reset seq so logs explain gaps.
        try:
            seq_int = int(seq) if seq is not None else None
        except (TypeError, ValueError):
            seq_int = None
        if seq_int is not None:
            last = self._last_seq.get(port_key)
            if last is not None and seq_int <= last:
                logger.warning(
                    "Non-monotonic seq for port %s: got seq=%s after last seq=%s "
                    "(server restart? replayed/coalesced event? possible duplicate upload)",
                    port, seq_int, last,
                )
            self._last_seq[port_key] = seq_int
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
            custom_msg = custom_text
            if mode in {".wantmatch", ".match1", ".match2", ".want1", ".want2", ".wantplay"}:
                custom_msg = custom_text or "Players on the server want a match. Who's in?"


            mode = server.get("mode") or ""
            if mode == ".upload_match":
                image_path = generate_screenshot_for_port(port, sofplus_data_path, exported_data)
                if not image_path:
                    logger.error(
                        "port=%s seq=%s screenshot generation FAILED; Discord upload skipped",
                        port, seq,
                    )
                else:
                    # Post-process image per upload-match rules (overlay + crop)
                    processed_path = postprocess_upload_match_image(image_path, exported_data)
                    if processed_path:
                        logger.info(
                            "port=%s seq=%s postprocess OK: %s -> %s",
                            port, seq, image_path, processed_path,
                        )
                    else:
                        logger.warning(
                            "port=%s seq=%s postprocess FAILED, falling back to raw %s",
                            port, seq, image_path,
                        )
                    final_path = processed_path or image_path
                    try:
                        fsize = os.path.getsize(final_path)
                    except OSError as exc:
                        logger.error(
                            "port=%s seq=%s upload SKIPPED: cannot stat %s: %s",
                            port, seq, final_path, exc,
                        )
                        return
                    # Upload as file to webhook so it lives in Discord.
                    # upload_image_to_discord now uses ?wait=true and returns
                    # per-webhook {ok, status, message_id, ...}; only ok=True
                    # (2xx + message id) counts as VERIFIED.
                    results = upload_image_to_discord(final_path, {})
                    total = len(results)
                    ok_keys = [k for k, r in results.items() if r.get("ok")]
                    ok = len(ok_keys)
                    ids = {k: (r.get("message_id"), r.get("channel_id")) for k, r in results.items()}
                    if total == 0:
                        logger.error(
                            "port=%s seq=%s upload SKIPPED: no webhooks configured (file=%s %db)",
                            port, seq, final_path, fsize,
                        )
                    elif ok == total:
                        logger.info(
                            "port=%s seq=%s upload VERIFIED %d/%d (file=%s %db ids=%s)",
                            port, seq, ok, total, final_path, fsize, ids,
                        )
                    elif ok == 0:
                        logger.error(
                            "port=%s seq=%s upload FAILED 0/%d (file=%s %db details=%s)",
                            port, seq, total, final_path, fsize, results,
                        )
                    else:
                        logger.warning(
                            "port=%s seq=%s upload PARTIAL %d/%d (file=%s %db ids=%s details=%s)",
                            port, seq, ok, total, final_path, fsize, ids, results,
                        )
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
                results = send_to_discord(payload)
                total = len(results)
                ok = sum(1 for r in results.values() if r.get("ok"))
                if total == 0:
                    logger.error("port=%s seq=%s send SKIPPED: no webhooks configured", port, seq)
                elif ok == total:
                    logger.info("port=%s seq=%s send VERIFIED %d/%d", port, seq, ok, total)
                elif ok == 0:
                    logger.error("port=%s seq=%s send FAILED 0/%d details=%s", port, seq, total, results)
                else:
                    logger.warning("port=%s seq=%s send PARTIAL %d/%d details=%s", port, seq, ok, total, results)
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
