import base64
import math
import os
from io import BytesIO
from typing import Dict, List, Optional

import requests
from PIL import Image, ImageEnhance
from datetime import datetime

from .vendor.pak import unpack_one_to_memory
from .logging_utils import get_logger
from .vendor import m32lib

logger = get_logger(__name__)

# Cache for portraits and other assets loaded from PAKs
ALL_PORTRAITS: dict[str, Image.Image] = {}
SPRITESHEET_CONCHARS: Optional[Image.Image] = None
FLAG_IMG_RED: Optional[Image.Image] = None
FLAG_IMG_BLUE: Optional[Image.Image] = None

# Horizontal crop configuration (left pixels cropped off, and right margin kept)
# To widen the visible area by 32px on each side, reduce left crop by 32 and reduce right margin by 32.
# Original: left=128, right_margin=108 → Wider: left=96, right_margin=76
CROP_LEFT = 96
CROP_RIGHT_MARGIN = 76

COLOR_ARRAY = [
    "#ffffff", "#FFFFFF", "#FF0000", "#00FF00", "#ffff00", "#0000ff", "#ff00ff",
    "#00ffff", "#000000", "#7f7f7f", "#ffffff", "#7f0000", "#007f00", "#ffffff",
    "#7f7f00", "#00007f", "#564d28", "#4c5e36", "#376f65", "#005572", "#54647e",
    "#54647e", "#66097b", "#705e61", "#980053", "#960018", "#702d07", "#54492a",
    "#61a997", "#cb8f39", "#cf8316", "#ff8020",
]


def gen_scoreboard_init(sof_dir: str) -> dict[str, Image.Image]:
    global ALL_PORTRAITS, SPRITESHEET_CONCHARS, FLAG_IMG_RED, FLAG_IMG_BLUE
    ALL_PORTRAITS = load_all_portraits(sof_dir)
    # Load additional resources from PAKs
    SPRITESHEET_CONCHARS = load_conchars_from_paks(sof_dir)
    FLAG_IMG_RED, FLAG_IMG_BLUE = load_flags_from_paks(sof_dir)
    logger.info(
        "Initialization complete: %d portraits, conchars=%s, flags(red=%s, blue=%s)",
        len(ALL_PORTRAITS),
        bool(SPRITESHEET_CONCHARS),
        bool(FLAG_IMG_RED),
        bool(FLAG_IMG_BLUE),
    )
    return ALL_PORTRAITS


def _decode_player_name(value: Optional[str]) -> str:
    if not value:
        return "Unknown"
    # If bytes were passed in, decode directly
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("latin-1")
        except Exception:
            return "Unknown"

    # Only decode once, and only if input is canonical base64 as produced by our exporter.
    s: str = value
    try:
        # Quick shape checks first
        b64chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        if not s or len(s) % 4 != 0 or any(ch not in b64chars for ch in s):
            return s
        decoded_bytes = base64.b64decode(s, validate=True)
        # Strict round-trip to avoid accidental re-decoding of plain names
        re_encoded = base64.b64encode(decoded_bytes).decode("ascii").rstrip("=")
        normalized_orig = s.strip().rstrip("=")
        if re_encoded == normalized_orig:
            return decoded_bytes.decode("latin-1", errors="replace")
        return s
    except Exception:
        return s


def _has_effective_inline_color(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    # Color control chars only take effect on subsequent printable chars.
    # Ignore any trailing control chars at the end of the string.
    control_chars = ''.join(chr(i) for i in range(32))
    trimmed = value.rstrip(control_chars)
    return any(ord(ch) < 32 for ch in trimmed)


def load_all_portraits(sof_dir: str) -> dict[str, Image.Image]:
    portrait_images: dict[str, Image.Image] = {}
    base_path_in_pak = "ghoul/pmodels/portraits"
    portrait_sources: dict[str, list[str]] = {
        "pak0.pak": [
            "amu.m32","assassin.m32","bear.m32","bonesnapper.m32","breaker.m32","butcher.m32",
            "captain.m32","cleaner.m32","cleaver.m32","crackshot.m32","crusher.m32","deadeye.m32",
            "defender.m32","dekker.m32","dragon.m32","enforcer.m32","fireball.m32","fist.m32","fixer.m32",
            "freeze.m32","ghost.m32","gimp.m32","grinder.m32","guard.m32","hawk.m32","iceman.m32",
            "icepick.m32","lieutenant.m32","mohawk.m32","mullins.m32","muscle.m32","ninja.m32",
            "ponytail.m32","princess.m32","rebel.m32","ripper.m32","sabre.m32","sam.m32","shadow.m32",
            "silencer.m32","skorpio.m32","slaughter.m32","slick.m32","stiletto.m32","strongarm.m32",
            "suit.m32","tank.m32","taylor.m32","wall.m32","whisper.m32",
        ],
        "pak2.pak": ["assault.m32","brick.m32","cobra.m32","commando.m32","jersey.m32","widowmaker.m32"],
    }

    for pak_dir, filenames in portrait_sources.items():
        for filename in filenames:
            try:
                m32_path_in_archive = os.path.join(base_path_in_pak, filename)
                pak_archive = os.path.join(sof_dir, "base", pak_dir)
                m32_data = unpack_one_to_memory(pak_archive, m32_path_in_archive)
                mipheader = m32lib.MipHeader(filename, m32_data)
                width_px = int(mipheader.width.read()[0])
                height_px = int(mipheader.height.read()[0])
                image = Image.frombytes("RGBA", (width_px, height_px), mipheader.imgdata())
                portrait_name = os.path.splitext(filename)[0]
                portrait_images[portrait_name] = image
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load portrait %s from %s: %s", filename, pak_dir, exc)
    return portrait_images


def unpack_from_paks(sof_dir: str, relative_path: str) -> Optional[bytes]:
    """Try to unpack a file from common PAK archives under <sof_dir>/base/.

    Returns file bytes or None if not found.
    """
    for pak_name in ("pak0.pak", "pak1.pak", "pak2.pak"):
        pak_archive = os.path.join(sof_dir, "base", pak_name)
        try:
            file_bytes = unpack_one_to_memory(pak_archive, relative_path)
            if file_bytes:
                return file_bytes
        except Exception:
            continue
    return None


def load_conchars_from_paks(sof_dir: str) -> Optional[Image.Image]:
    """Load pics/console/conchars.png from game PAKs as a spritesheet image."""
    rel = os.path.join("pics", "console", "conchars.m32")
    data = unpack_from_paks(sof_dir, rel)
    if not data:
        return None
    try:
        mh = m32lib.MipHeader("conchars.m32", data)
        w = int(mh.width.read()[0])
        h = int(mh.height.read()[0])
        img = Image.frombytes("RGBA", (w, h), mh.imgdata())
        return img
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load conchars from PAKs: %s", exc)
        return None


def load_flags_from_paks(sof_dir: str) -> tuple[Optional[Image.Image], Optional[Image.Image]]:
    """Load red/blue flag HUD icons from M32 resources in PAKs."""
    red_rel = os.path.join("pics", "interface2", "ctfr_hudflag.m32")
    blue_rel = os.path.join("pics", "interface2", "ctfb_hudflag.m32")
    red_img = None
    blue_img = None
    red_data = unpack_from_paks(sof_dir, red_rel)
    blue_data = unpack_from_paks(sof_dir, blue_rel)
    try:
        if red_data:
            mh = m32lib.MipHeader("ctfr_hudflag.m32", red_data)
            w = int(mh.width.read()[0])
            h = int(mh.height.read()[0])
            red_img = Image.frombytes("RGBA", (w, h), mh.imgdata())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load red flag from PAKs: %s", exc)
    try:
        if blue_data:
            mh = m32lib.MipHeader("ctfb_hudflag.m32", blue_data)
            w = int(mh.width.read()[0])
            h = int(mh.height.read()[0])
            blue_img = Image.frombytes("RGBA", (w, h), mh.imgdata())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load blue flag from PAKs: %s", exc)
    return red_img, blue_img


def draw_string_at(canvas_image: Image.Image, spritesheet: Image.Image, string: str, xpos: int, ypos: int, color_override: Optional[str] = None) -> None:
    x_offset = 0
    current_color = "#00ff00"
    current_color_code: Optional[int] = None
    # Accept bytes/bytearray directly to avoid rendering the Python repr (e.g. "b'...'"),
    # which would expose escape sequences as visible characters. Otherwise encode the
    # provided string to latin-1 bytes so we map exactly to the 0-255 spritesheet indices.
    if isinstance(string, (bytes, bytearray)):
        byte_seq = bytes(string)
    else:
        try:
            byte_seq = str(string).encode("latin-1", errors="replace")
        except Exception:
            byte_seq = bytes((ord(ch) % 256 for ch in str(string)))

    for char_code in byte_seq:
        # char_code is an int 0..255
        if char_code < 32:
            # Log color-code application for debugging problematic names
            try:
                if not color_override and char_code < len(COLOR_ARRAY):
                    logger.debug("draw_string_at: applying color code %d -> %s for string=%r", char_code, COLOR_ARRAY[char_code], string)
                    current_color = COLOR_ARRAY[char_code]
                    current_color_code = char_code
                else:
                    logger.debug("draw_string_at: encountered control byte %d but color override present or out of range for string=%r", char_code, string)
            except Exception:
                pass
            continue
        final_color = color_override if color_override else current_color
        x_clip = (char_code % 16) * 8
        y_clip = (char_code // 16) * 8
        if x_clip + 8 <= spritesheet.width and y_clip + 8 <= spritesheet.height:
            char_sprite = spritesheet.crop((x_clip, y_clip, x_clip + 8, y_clip + 8))
            ox = xpos + x_offset
            oy = ypos
            # New rule: do not alter background unless the active inline color code is between 8 and 30 inclusive
            if not color_override and current_color_code is not None and 8 <= current_color_code <= 30:
                try:
                    region = canvas_image.crop((ox, oy, ox + 8, oy + 8))
                    # Apply a constant white overlay (single shade) under the glyph
                    white_overlay = Image.new("RGBA", (8, 8), (255, 255, 255, 44))
                    region = Image.alpha_composite(region.convert("RGBA"), white_overlay)
                    canvas_image.paste(region, (ox, oy))
                except Exception:
                    pass
            # Draw the glyph
            color_image = Image.new("RGBA", (8, 8), final_color)
            canvas_image.paste(color_image, (ox, oy), mask=char_sprite)
        x_offset += 8


def _measure_visible_chars_and_luminance(string: str, color_override: Optional[str] = None) -> tuple[int, float]:
    # No longer used; kept for potential future tuning. Return zeros.
    return 0, 0.0


def draw_players(data: dict, canvas_image: Image.Image, spritesheet: Image.Image, y_offset: int = 0) -> None:
    blue_players: list[dict] = []
    red_players: list[dict] = []
    blue_score = 0
    red_score = 0
    for player_data in list(data.get("players", [])):
        if player_data is None:
            continue
        # Skip spectators
        try:
            if int(player_data.get("spectator", 0) or 0) != 0:
                continue
        except Exception:
            pass
        if isinstance(player_data.get("name"), str) and "_decoded_name" not in player_data:
            # Decode from exporter-provided base64 but do not mutate original field
            original = player_data.get("name")
            decoded_name = _decode_player_name(original)
            player_data["_decoded_name"] = decoded_name
            # Log suspicious names that contain non-ASCII or control bytes for debugging
            try:
                name_check = decoded_name
                if any(ord(ch) < 32 or ord(ch) > 127 for ch in name_check):
                    logger.debug(
                        "Suspicious player name decoded in draw_players: original=%r decoded=%r bytes=%s",
                        original,
                        name_check,
                        list(name_check.encode("latin-1", errors="replace")),
                    )
            except Exception:
                pass
        if player_data.get("team") == 1:
            blue_players.append(player_data)
            blue_score += int(player_data.get("score", 0))
        elif player_data.get("team") == 2:
            red_players.append(player_data)
            red_score += int(player_data.get("score", 0))
    blue_players.sort(key=lambda p: int(p.get("score", 0)), reverse=True)
    red_players.sort(key=lambda p: int(p.get("score", 0)), reverse=True)

    for i, player in enumerate(blue_players):
        y_base = 120 + (32 * i) + y_offset
        skin = ALL_PORTRAITS.get(player.get("skin", "mullins"))
        if skin is None:
            skin = ALL_PORTRAITS.get("mullins")
        if skin is not None:
            canvas_image.paste(skin, (160, y_base), skin)
        name_to_draw = player.get("_decoded_name") or _decode_player_name(player.get("name", ""))
        draw_string_at(canvas_image, spritesheet, name_to_draw, 192, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 192, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get("score", 0)), 256, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 192, y_base + 16, "#b5b2b5")
        frames_total = player.get("frames_total", 0)
        time_min = math.floor(math.floor(int(frames_total) / 10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time_min}", 192, y_base + 24, "#b5b2b5")

    for i, player in enumerate(red_players):
        y_base = 120 + (32 * i) + y_offset
        skin = ALL_PORTRAITS.get(player.get("skin", "mullins"))
        if skin is None:
            skin = ALL_PORTRAITS.get("mullins")
        if skin is not None:
            # Place red team portraits at the right column (aligned with text at x=372)
            canvas_image.paste(skin, (340, y_base), skin)
        name_to_draw = player.get("_decoded_name") or _decode_player_name(player.get("name", ""))
        draw_string_at(canvas_image, spritesheet, name_to_draw, 372, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 372, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get("score", 0)), 436, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 372, y_base + 16, "#b5b2b5")
        frames_total = player.get("frames_total", 0)
        time_min = math.floor(math.floor(int(frames_total) / 10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time_min}", 372, y_base + 24, "#b5b2b5")

    draw_string_at(canvas_image, spritesheet, "Score: ", 192, 68 + y_offset, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_score), 248, 68 + y_offset, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Score: ", 372, 68 + y_offset, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_score), 428, 68 + y_offset, "#ffffff")


def draw_screenshot_hud(spritesheet: Image.Image, data: dict, canvas_image: Image.Image, y_offset: int = 0) -> None:
    # Prefer flags loaded from PAKs; no-op if not available
    if FLAG_IMG_BLUE and FLAG_IMG_RED:
        canvas_image.paste(FLAG_IMG_BLUE, (160, 55 + y_offset), FLAG_IMG_BLUE)
        canvas_image.paste(FLAG_IMG_RED, (340, 55 + y_offset), FLAG_IMG_RED)
    else:
        # Fallback to asset images if provided
        try:
            asset_dir = os.path.join(os.path.dirname(__file__), "assets")
            blueflag_img = Image.open(os.path.join(asset_dir, "blueflag.png")).convert("RGBA")
            redflag_img = Image.open(os.path.join(asset_dir, "redflag.png")).convert("RGBA")
            canvas_image.paste(blueflag_img, (160, 55 + y_offset), blueflag_img)
            canvas_image.paste(redflag_img, (340, 55 + y_offset), redflag_img)
        except FileNotFoundError:
            # If neither PAK nor assets provide flags, continue without them
            logger.info("Flag HUD images not available; continuing without them")

    server_info = data.get("server", {})
    blue_caps = server_info.get("num_flags_blue", 0)
    red_caps = server_info.get("num_flags_red", 0)
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 192, 78 + y_offset, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_caps), 312, 78 + y_offset, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 372, 78 + y_offset, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_caps), 492, 78 + y_offset, "#ffffff")
    draw_players(data, canvas_image, spritesheet, y_offset)


def generate_screenshot_for_port(port: str, sofplus_data_path: str, data: dict) -> str | None:
    if "server" not in data:
        logger.error("server_data is missing in data")
        return None

    # Early exit if no active (non-spectator) players
    try:
        players_list = list(data.get("players", []))
        has_active = any(p and int(p.get("spectator", 0) or 0) == 0 for p in players_list)
        if not has_active:
            logger.info("No active players; not generating screenshot.")
            return None
    except Exception:
        pass

    server_data = data["server"]
    logger.info("Triggered screenshot generation for port %s", port)

    output_dir = os.path.join(sofplus_data_path, "info_image")
    output_path = os.path.join(output_dir, "ss.png")
    os.makedirs(output_dir, exist_ok=True)

    # Use conchars from PAKs if available; fallback to bundled asset
    spritesheet: Optional[Image.Image] = SPRITESHEET_CONCHARS
    if spritesheet is None:
        try:
            spritesheet = Image.open(os.path.join(os.path.dirname(__file__), "assets", "conchars.png")).convert("RGBA")
        except FileNotFoundError:
            logger.error("Could not load 'conchars' spritesheet from PAKs or assets.")
            return None

    map_full_name = server_data.get("map_current", "dm/dmjpnctf1").lower()
    map_substr = "".join(map_full_name.split("/"))

    canvas_image: Optional[Image.Image] = None
    local_bg_path = os.path.join(os.path.dirname(__file__), "assets", "sof_inter_ss", f"{map_substr}.png")
    web_bg_url = f"http://mods.sof1.org/wp-content/uploads/2011/05/{map_substr}.png"
    maps_screenshots_path = os.path.join(os.path.dirname(__file__), "assets", "MAPS_SCREENSHOTS", f"{map_full_name}.png")

    try:
        canvas_image = Image.open(local_bg_path).convert("RGBA")
        logger.info("Loaded local background: %s", local_bg_path)
    except FileNotFoundError:
        logger.info("Local background not found: %s. Trying web fallback.", local_bg_path)
        try:
            response = requests.get(web_bg_url, timeout=5)
            response.raise_for_status()
            canvas_image = Image.open(BytesIO(response.content)).convert("RGBA")
            logger.info("Loaded web background from %s", web_bg_url)
        except Exception:
            logger.info("Web background failed. Trying %s.", maps_screenshots_path)
            try:
                img = Image.open(maps_screenshots_path).convert("RGBA")
                canvas_image = img.resize((640, 480))
                logger.info("Loaded and resized local background from %s", maps_screenshots_path)
            except FileNotFoundError:
                logger.warning("No background found for map %s", map_full_name)

    # Prepare a smoky black base (background fill outside map area)
    # Slightly brighter base background to improve readability of dark names
    base_bg = Image.new("RGBA", (640, 480), (16, 16, 16, 220))

    # Compute target cropped region geometry to fit the background within
    players_list = list(data.get("players", []))
    # Only count non-spectators when sizing the cropped region
    active_players: list[dict] = []
    for p in players_list:
        if not p:
            continue
        try:
            if int(p.get("spectator", 0) or 0) != 0:
                continue
        except Exception:
            pass
        active_players.append(p)
    blue_count = sum(1 for p in active_players if p.get("team") == 1)
    red_count = sum(1 for p in active_players if p.get("team") == 2)
    total_players = len(active_players)
    max_col_players = max(blue_count, red_count)
    #32 px margin below
    overlay_base_y = max_col_players * 32 + 150
    # Include bottom padding (+8) consistent with postprocess
    intended_bottom = overlay_base_y + 16 + (total_players * 8) + 8
    target_left, target_top = CROP_LEFT, 32
    target_right = 640 - CROP_RIGHT_MARGIN
    target_bottom = min(480, max(target_top + 1, intended_bottom))
    region_w = max(1, target_right - target_left)
    region_h = max(1, target_bottom - target_top)

    # Resize map background to fit inside the target region, preserving aspect ratio
    if canvas_image is not None:
        try:
            scale = min(region_w / canvas_image.width, region_h / canvas_image.height)
            scaled_w = max(1, int(canvas_image.width * scale))
            scaled_h = max(1, int(canvas_image.height * scale))
            try:
                resample = Image.LANCZOS  # Pillow>=3.4
            except Exception:
                resample = Image.BICUBIC
            map_scaled = canvas_image.resize((scaled_w, scaled_h), resample=resample)
            # Darken only the map image
            # Subtle brightness lift: reduce darkening to make white/black names readable
            overlay = Image.new("RGBA", map_scaled.size, (0, 0, 0, 96))
            map_dark = Image.alpha_composite(map_scaled.convert("RGBA"), overlay)
            # Center within target region
            paste_x = target_left + (region_w - scaled_w) // 2
            paste_y = target_top + (region_h - scaled_h) // 2
            base_bg.paste(map_dark, (paste_x, paste_y), map_dark)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to scale/paste background: %s", exc)

    # Draw HUD/text/portraits directly on the base background so local contrast adjustments affect visible pixels
    # Shift entire HUD down by 8 px to guarantee 8 px spacing from top info rows
    draw_screenshot_hud(spritesheet, data, base_bg, y_offset=8)
    final_composite = base_bg

    try:
        final_path = os.path.expanduser(output_path)
        final_composite.save(final_path)
        logger.info("Successfully created screenshot: %s", final_path)
        return final_path
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error saving the final image: %s", exc)
        return None


def _load_conchars_local_fallback() -> Optional[Image.Image]:
    try:
        return Image.open(os.path.join(os.path.dirname(__file__), "assets", "conchars.png")).convert("RGBA")
    except FileNotFoundError:
        logger.error("Could not load 'conchars' spritesheet from PAKs or assets.")
        return None


def _collect_players_by_team(data: dict) -> tuple[list[tuple[int, dict]], list[tuple[int, dict]]]:
    blue_players: list[tuple[int, dict]] = []
    red_players: list[tuple[int, dict]] = []
    for slot, player_data in enumerate(list(data.get("players", []))):
        if player_data is None:
            continue
        # Skip spectators
        try:
            if int(player_data.get("spectator", 0) or 0) != 0:
                continue
        except Exception:
            pass
        # Decode from exporter-provided base64 but do not mutate original field
        if isinstance(player_data.get("name"), str) and "_decoded_name" not in player_data:
            original = player_data.get("name")
            decoded_name = _decode_player_name(original)
            player_data["_decoded_name"] = decoded_name
            try:
                name_check = decoded_name
                if any(ord(ch) < 32 or ord(ch) > 127 for ch in name_check):
                    logger.debug(
                        "Suspicious player name in slot %s: original=%r decoded=%r bytes=%s",
                        slot,
                        original,
                        name_check,
                        list(name_check.encode("latin-1", errors="replace")),
                    )
            except Exception:
                pass
        team_val = player_data.get("team")
        if team_val == 1:
            blue_players.append((slot, player_data))
        elif team_val == 2:
            red_players.append((slot, player_data))
    return blue_players, red_players


def postprocess_upload_match_image(image_path: str, data: dict) -> Optional[str]:
    """Overlay upload-match text using conchars and crop per specification.

    - Crop: left=128, right=width-108, top=32, bottom=max(red,blue)*32 + 150 + 16 + total_players*8
    - Overlay header and one row per player using conchars.m32 at y = max(red,blue)*32 + 150
    Returns the new file path (PNG) or None on failure.
    """
    try:
        base_img = Image.open(image_path).convert("RGBA")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to open image for postprocess: %s", exc)
        return None

    spritesheet: Optional[Image.Image] = SPRITESHEET_CONCHARS or _load_conchars_local_fallback()
    if spritesheet is None:
        return None

    blue_players, red_players = _collect_players_by_team(data)
    total_players = len(blue_players) + len(red_players)
    max_col_players = max(len(blue_players), len(red_players))

    # Compute baseline Y for overlay and bottom crop per request
    overlay_base_y = max_col_players * 32 + 150
    # Add 8px padding below the last stats row and shift scoreboard down by 8px
    crop_bottom = overlay_base_y + 32 + (total_players * 8) + 8
    # Ensure we have enough canvas height BEFORE drawing rows, or drawing would be clipped
    if crop_bottom > base_img.height:
        try:
            # Slightly brighter extension area to match main base background
            extended = Image.new("RGBA", (base_img.width, crop_bottom), (16, 16, 16, 220))
            extended.paste(base_img, (0, 0))
            base_img = extended
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extend canvas prior to drawing: %s", exc)

    # Draw top info rows (all left-aligned):
    # Row 1 at y=32 (lands at 0..8 after crop): Time
    # Row 2 at y=40 (lands at 8..16 after crop): Hostname (with inline color codes)
    # Row 3 at y=48 (lands at 16..24 after crop): Map name
    server_info = data.get("server", {})
    map_display = str(server_info.get("map_current", "unknown")) or "unknown"
    hostname = str(server_info.get("hostname", "unknown host")) or "unknown host"
    utc_now = datetime.utcnow().strftime("%d/%m/%y %H:%M utc")
    width, height = base_img.size
    crop_left = CROP_LEFT
    crop_right = max(crop_left + 1, width - CROP_RIGHT_MARGIN)
    # Row 1: time left (shifted down by 8px to provide top padding after crop)
    draw_string_at(base_img, spritesheet, utc_now, crop_left, 40, "#ffffff")
    # Row 2: hostname left with inline colors (no override)
    draw_string_at(base_img, spritesheet, hostname, crop_left, 48)
    # Row 3: map name left
    draw_string_at(base_img, spritesheet, map_display, crop_left, 56, "#ffffff")

    # Draw header and rows
    header1 = " # CC FPS Ping Score PPM FRG DIE SK FLG REC Name"
    header2 = "-- -- --- ---- ----- --- --- --- -- --- --- ---------------"
    # Place within the area that will remain after left crop (x=128)
    overlay_x = CROP_LEFT
    draw_string_at(base_img, spritesheet, header1, overlay_x, overlay_base_y + 8, "#ffffff")
    draw_string_at(base_img, spritesheet, header2, overlay_x, overlay_base_y + 16, "#b5b2b5")

    # Build a flat ordered list of players sorted solely by slot id
    ordered_players = sorted(blue_players + red_players, key=lambda t: t[0])
    for row_index, (slot, p) in enumerate(ordered_players):
        # Safe getters
        ping = int(p.get("ping", 0) or 0)
        score = int(p.get("score", 0) or 0)
        frags = int(p.get("frags", 0) or 0)
        deaths = int(p.get("deaths", 0) or 0)
        suicides = int(p.get("suicides", 0) or 0)
        flags_captured = int(p.get("flags_captured", 0) or 0)
        flags_recovered = int(p.get("flags_recovered", 0) or 0)
        frames_total = int(p.get("frames_total", 0) or 0)
        # PPM from server if present; otherwise fallback to computed
        try:
            # .players uses ppm_best instead of ppm_now
            ppm = int(p.get("ppm_best", 0) or 0)
        except Exception:
            ppm = 0
        if ppm == 0:
            try:
                time_minutes = math.floor(math.floor(frames_total / 10) / 60)
                ppm = int(score / time_minutes) if time_minutes > 0 else 0
            except Exception:
                ppm = 0
        cc = p.get("country", "??")
        fps = p.get("fps", "-")
        # Always use single-pass decoded name prepared earlier; fallback to decoding once here
        name = p.get("_decoded_name") or _decode_player_name(p.get("name", "")) or "unknown"
        team_val = p.get("team", 0)

        # Draw slot id in team color, rest of columns white, then name with in-string color codes
        row_y = overlay_base_y + 24 + (row_index * 8)
        # Slot column width is 2 chars; right-align to match header dashes
        slot_text = f"{slot:>2}"
        slot_color = "#0000ff" if team_val == 1 else ("#ff0000" if team_val == 2 else "#ffffff")
        draw_string_at(base_img, spritesheet, slot_text, overlay_x, row_y, slot_color)

        # Right-align each numeric/stat field to the width implied by header hyphens
        # CC:2 FPS:3 Ping:4 Score:5 PPM:3 FRG:3 DIE:3 SK:2 FLG:3 REC:3
        columns_text = (
            f" {cc:>2}"
            f" {str(fps):>3}"
            f" {ping:>4}"
            f" {score:>5}"
            f" {ppm:>3}"
            f" {frags:>3}"
            f" {deaths:>3}"
            f" {suicides:>2}"
            f" {flags_captured:>3}"
            f" {flags_recovered:>3} "
        )
        x_after_slot = overlay_x + (len(slot_text) * 8)
        draw_string_at(base_img, spritesheet, columns_text, x_after_slot, row_y, "#ffffff")

        x_before_name = x_after_slot + (len(columns_text) * 8)
        # Use white when no inline color codes are present; otherwise respect in-name colors
        try:
            has_inline_color = _has_effective_inline_color(name)
        except Exception:
            has_inline_color = False
        if has_inline_color:
            draw_string_at(base_img, spritesheet, name, x_before_name, row_y)
        else:
            draw_string_at(base_img, spritesheet, name, x_before_name, row_y, "#ffffff")

    # Perform crop
    width, height = base_img.size
    left = CROP_LEFT
    top = 32
    right = max(left + 1, width - CROP_RIGHT_MARGIN)
    # Ensure we do not cut off the statistics table; extend canvas if needed
    if crop_bottom > height:
        try:
            extended = Image.new("RGBA", (width, crop_bottom), (16, 16, 16, 220))
            extended.paste(base_img, (0, 0))
            base_img = extended
            height = base_img.height
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to extend canvas for stats: %s", exc)
    bottom = max(top + 1, crop_bottom)
    try:
        cropped = base_img.crop((left, top, right, bottom))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to crop upload-match image: %s", exc)
        return None

    # Save alongside original
    new_path = os.path.join(os.path.dirname(image_path), "ss_upload.png")
    try:
        cropped.save(new_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to save cropped upload-match image: %s", exc)
        return None
    return new_path
