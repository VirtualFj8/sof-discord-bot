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


def load_trigger_data(filepath: str) -> Dict[str, Any]:
    """Parse an ext_trigger wakeup file (e.g. ``ext_trigger/discord.cfg``).

    Written by ``ext_trigger_fire`` (see ``ext_trigger.func``, canonical
    source in sof-profiles): ``~name`` -> ``name``, ``~slot`` -> ``slot``,
    ``~arg1`` -> ``mode``, ``~arg2`` -> ``msg``, plus the monotonic ``seq``.
    Returns an empty dict when the file is absent (servers still running the
    pre-migration .func that only writes ``info_server/server.cfg``).
    """
    trigger_data: Dict[str, Any] = {}
    if not os.path.isfile(filepath):
        return trigger_data
    cvar_pattern = re.compile(r'set "([^"]+)" "([^"]*)"')
    try:
        with open(filepath, "r", encoding="latin-1") as file_obj:
            for line in file_obj:
                match = cvar_pattern.match(line)
                if not match:
                    continue
                key, value = match.groups()
                if key == "_ext_trigger_name":
                    trigger_data["name"] = value
                elif key == "_ext_trigger_seq":
                    try:
                        trigger_data["seq"] = int(value)
                    except ValueError:
                        trigger_data["seq"] = value
                elif key == "_ext_trigger_slot":
                    try:
                        trigger_data["slot"] = int(value)
                    except ValueError:
                        trigger_data["slot"] = value
                elif key == "_ext_trigger_arg1":
                    trigger_data["mode"] = value
                elif key == "_ext_trigger_arg2":
                    trigger_data["msg"] = value
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing trigger file %s: %s", filepath, exc)
    return trigger_data


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
    trigger_cfg_path = os.path.join(sofplus_data_path, "ext_trigger/discord.cfg")
    # Prefer a snapshot directory if present; fall back to live info_client
    snap_path = os.path.join(sofplus_data_path, "info_client_snap")
    if os.path.isdir(snap_path):
        player_data_path = snap_path
    else:
        player_data_path = os.path.join(sofplus_data_path, "info_client")

    server_data = load_server_data(server_cfg_path)
    if not server_data:
        logger.error("Could not load server data for port %s. Aborting.", port)
        return None
    # Event metadata: prefer the ext_trigger wakeup file, which info_client
    # fires *after* the snapshot above was written. Fall back to the legacy
    # ~discord_* keys in server.cfg for pre-migration servers.
    trigger_data = load_trigger_data(trigger_cfg_path)
    if trigger_data.get("name"):
        if "mode" in trigger_data:
            server_data["mode"] = trigger_data["mode"]
        if "slot" in trigger_data:
            server_data["slot"] = trigger_data["slot"]
        if "msg" in trigger_data:
            server_data["msg"] = trigger_data["msg"]
        server_data["trigger_seq"] = trigger_data.get("seq")
        server_data["trigger_name"] = trigger_data.get("name")
        logger.info(
            "Using ext_trigger event %s seq=%s for port %s",
            trigger_data.get("name"), trigger_data.get("seq"), port,
        )
    loaded_players = load_player_data_from_files(player_data_path)
    data = {"server": server_data, "players": loaded_players}

    if server_data.get("~end_reason") == "flaglimit":
        # Correct data.players[i].flags_captured for the winning team
        winner = server_data.get("~winner")
        capping_slot = server_data.get("~capping_slot","-1")
        
        # logger.info("Capping slot: %s", capping_slot)
        if isinstance(capping_slot, int) and 0 <= capping_slot < len(loaded_players):
            for idx, player in enumerate(loaded_players):
                if player is None:
                    continue
                team = player.get("team")
                # Map team number to color: 0 -> "blue", 1 -> "red"
                team_color = "blue" if team == 1 else "red" if team == 2 else None
                if team_color == winner and idx == capping_slot:
                    player["flags_captured"] = player.get("flags_captured", 0) + 1
            if winner == "blue":
                server_data["num_flags_blue"] = server_data.get("num_flags_blue", 0) + 1
            elif winner == "red":
                server_data["num_flags_red"] = server_data.get("num_flags_red", 0) + 1
    

    logger.info("Read data successfully for port %s, the match ended with %s", port, server_data.get("~end_reason"))
    return data
