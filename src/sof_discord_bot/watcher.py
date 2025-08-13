import os
import re
import time
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .scoreboard import gen_scoreboard_init, generate_screenshot_for_port, postprocess_upload_match_image
from .exporter import read_data_from_sof_server
from .discorder import generate_payload, send_to_discord, upload_image_to_discord
from .logging_utils import get_logger

logger = get_logger(__name__)


class ServerCfgEventHandler(FileSystemEventHandler):
    PORT_REGEX = re.compile(r"user-(\d+)")

    def __init__(self, cooldown: int = 10) -> None:
        self.cooldown = cooldown
        self.last_triggered_time: dict[str, float] = {}

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        src_path = event.src_path
        if src_path.endswith(os.path.join("info_server", "server.cfg")):
            port_match = self.PORT_REGEX.search(src_path)
            if not port_match:
                logger.warning("Could not extract port from path: %s", src_path)
                return
            port = port_match.group(1)
            current_time = time.time()
            last_time = self.last_triggered_time.get(port, 0)
            if current_time - last_time < self.cooldown:
                return
            self.last_triggered_time[port] = current_time
            logger.info("Detected modification for trigger file: %s", src_path)
            time.sleep(1)
            sofplus_data_path = f"../user-{port}/sofplus/data"
            if not os.path.exists(sofplus_data_path):
                logger.error("Directory does not exist: %s", sofplus_data_path)
                return
            exported_data = read_data_from_sof_server(port, sofplus_data_path)
            if exported_data is None:
                return
            image_path = generate_screenshot_for_port(port, sofplus_data_path, exported_data)
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
                    total_players += 1
                    # Names are base64-encoded in files
                    name_val = p.get("name", "")
                    try:
                        import base64
                        decoded = base64.b64decode(name_val).decode("latin-1") if name_val else "Unknown"
                    except Exception:
                        decoded = "Unknown"
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
                            caller_name = "Unknown"
                caller_name = caller_name or "Unknown"

                mode = server.get("mode") or ""
                custom_text = server.get("msg") or None

                # Determine needed players for match request modes
                needed_players: Optional[int] = None
                if mode in {".match1", ".want1"}:
                    needed_players = 1
                elif mode in {".match2", ".want2"}:
                    needed_players = 2

                # Default description if not provided via custom_text
                if mode in {".wantmatch", ".match1", ".match2", ".want1", ".want2"}:
                    custom_msg = custom_text or "Players on the server want a match. Who's in?"
                elif mode == ".wantplay":
                    custom_msg = custom_text or "Competitive match is wanted"
                else:
                    custom_msg = custom_text or "Live scoreboard"

                payload = generate_payload(
                    caller_name=caller_name,
                    red_team=red_team_names,
                    blue_team=blue_team_names,
                    custom_msg=custom_msg,
                    total_players=total_players,
                    image_url=None,
                    mode=mode,
                    needed_players=needed_players,
                )
                mode = server.get("mode") or ""
                if mode == ".upload_match" and image_path:
                    # Post-process image per upload-match rules (overlay + crop)
                    processed_path = postprocess_upload_match_image(image_path, exported_data)
                    final_path = processed_path or image_path
                    # Upload as file to webhook so it lives in Discord
                    upload_image_to_discord(final_path, {})
                else:
                    send_to_discord(payload)
            except Exception:
                logger.exception("Failed to prepare or send Discord notification")


def run_watcher(cooldown: int = 10) -> None:
    sof_dir = os.path.dirname(os.getcwd())
    gen_scoreboard_init(sof_dir)
    logger.info("Starting file monitor on: %s", sof_dir)
    event_handler = ServerCfgEventHandler(cooldown=cooldown)
    observer = Observer()
    observer.schedule(event_handler, sof_dir, recursive=True)
    observer.start()
    logger.info("Monitor started. Waiting for 'server.cfg' modifications...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Monitor stopped by user.")
        observer.stop()
    observer.join()
