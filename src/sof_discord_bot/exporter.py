import base64
import os
import re
from typing import Any, Dict, List, Optional

from .logging_utils import get_logger

logger = get_logger(__name__)


def load_server_data(filepath: str) -> Dict[str, Any]:
    server_data: Dict[str, Any] = {}
    if not os.path.isfile(filepath):
        logger.warning("Server config file not found: %s", filepath)
        return server_data
    cvar_pattern = re.compile(r'set "([^"]+)" "([^"]*)"')
    try:
        with open(filepath, "r", encoding="latin-1") as file_obj:
            for line in file_obj:
                match = cvar_pattern.match(line)
                if not match:
                    continue
                key, value = match.groups()
                if key == "ctf_loops":
                    try:
                        server_data[key] = int(value)
                    except ValueError:
                        server_data[key] = value
                elif key == "~capping_slot":
                    try:
                        server_data[key] = int(value)
                    except ValueError:
                        server_data[key] = value
                elif key.startswith("~discord_"):
                    clean_key = key.replace("~discord_", "")
                    if clean_key == "slot":
                        try:
                            server_data[clean_key] = int(value)
                        except ValueError:
                            server_data[clean_key] = value
                    else:
                        server_data[clean_key] = value
                elif key.startswith("_sp_sv_info_"):
                    clean_key = key.replace("_sp_sv_info_", "")
                    if clean_key.startswith("num_"):
                        try:
                            server_data[clean_key] = int(value)
                        except ValueError:
                            server_data[clean_key] = value
                    else:
                        server_data[clean_key] = value
                else:
                    server_data[key] = value
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing server config file %s: %s", filepath, exc)
    return server_data


def load_player_data_from_files(directory_path: str) -> List[Optional[dict]]:
    players: List[Optional[dict]] = [None] * 16
    if not os.path.isdir(directory_path):
        logger.warning("Player data directory not found: %s", directory_path)
        return players

    cvar_pattern = re.compile(r'set "_sp_sv_info_client_([^"]+)" "([^"]*)"')
    file_pattern = re.compile(r"player_(\d+)\.cfg")

    for filename in os.listdir(directory_path):
        file_match = file_pattern.match(filename)
        if not file_match:
            continue
        try:
            slot = int(file_match.group(1))
            if not 0 <= slot < 16:
                logger.warning("Skipping file %s with out-of-range slot number: %s", filename, slot)
                continue
            player_data: dict = {}
            filepath = os.path.join(directory_path, filename)
            with open(filepath, "r", encoding="latin-1") as file_obj:
                for line in file_obj:
                    match = cvar_pattern.match(line)
                    if not match:
                        continue
                    key, value = match.groups()
                    if key in [
                        "score",
                        "ping",
                        "team",
                        "deaths",
                        "frags",
                        "suicides",
                        "teamkills",
                        "spectator",
                        "flags_captured",
                        "flags_recovered",
                        "frames_total",
                        "ppm_now",
                        "fps",
                    ]:
                        try:
                            player_data[key] = int(value)
                        except ValueError:
                            player_data[key] = 0
                    else:
                        player_data[key] = value
            if "name" in player_data:
                player_data["name"] = base64.b64encode(player_data["name"].encode("latin-1")).decode("ascii")
            if player_data:
                players[slot] = player_data
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error processing file %s: %s", filename, exc)
    return players


def read_data_from_sof_server(port: str, sofplus_data_path: str) -> Optional[dict]:
    server_cfg_path = os.path.join(sofplus_data_path, "info_server/server.cfg")
    player_data_path = os.path.join(sofplus_data_path, "info_client")

    server_data = load_server_data(server_cfg_path)
    if not server_data:
        logger.error("Could not load server data for port %s. Aborting.", port)
        return None
    loaded_players = load_player_data_from_files(player_data_path)
    data = {"server": server_data, "players": loaded_players}

    if server_data.get("~end_reason") == "flaglimit":
        # Correct data.players[i].flags_captured for the winning team
        winner = server_data.get("~winner")
        capping_slot = server_data.get("~capping_slot","-1")
        
        if isinstance(capping_slot, int) and 0 <= capping_slot < len(loaded_players):
            for idx, player in enumerate(loaded_players):
                if player is None:
                    continue
                team = player.get("team")
                # Map team number to color: 0 -> "blue", 1 -> "red"
                team_color = "blue" if team == 0 else "red" if team == 1 else None
                if team_color == winner and idx == capping_slot:
                    player["flags_captured"] = player.get("flags_captured", 0) + 1
            if winner == "blue":
                server_data["num_flags_blue"] = server_data.get("num_flags_blue", 0) + 1
            elif winner == "red":
                server_data["num_flags_red"] = server_data.get("num_flags_red", 0) + 1
    

    logger.info("Read data successfully for port %s, the match ended with %s", port, server_data.get("~end_reason"))
    return data
