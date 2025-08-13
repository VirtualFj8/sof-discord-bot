import base64
import math
import os
from io import BytesIO
from typing import Dict, List, Optional

import requests
from PIL import Image

from .vendor.pak import unpack_one_to_memory
from .logging_utils import get_logger
from .vendor import m32lib

logger = get_logger(__name__)

# Cache for portraits and other assets loaded from PAKs
ALL_PORTRAITS: dict[str, Image.Image] = {}
SPRITESHEET_CONCHARS: Optional[Image.Image] = None
FLAG_IMG_RED: Optional[Image.Image] = None
FLAG_IMG_BLUE: Optional[Image.Image] = None

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
    rel = os.path.join("pics", "console", "conchars.png")
    data = unpack_from_paks(sof_dir, rel)
    if not data:
        return None
    try:
        return Image.open(BytesIO(data)).convert("RGBA")
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
    for char in str(string):
        char_code = ord(char)
        if char_code < 32:
            if not color_override and char_code < len(COLOR_ARRAY):
                current_color = COLOR_ARRAY[char_code]
            continue
        final_color = color_override if color_override else current_color
        x_clip = (char_code % 16) * 8
        y_clip = (char_code // 16) * 8
        if x_clip + 8 <= spritesheet.width and y_clip + 8 <= spritesheet.height:
            char_sprite = spritesheet.crop((x_clip, y_clip, x_clip + 8, y_clip + 8))
            color_image = Image.new("RGBA", (8, 8), final_color)
            canvas_image.paste(color_image, (xpos + x_offset, ypos), mask=char_sprite)
        x_offset += 8


def draw_players(data: dict, canvas_image: Image.Image, spritesheet: Image.Image) -> None:
    blue_players: list[dict] = []
    red_players: list[dict] = []
    blue_score = 0
    red_score = 0
    for player_data in list(data.get("players", [])):
        if player_data is None:
            continue
        try:
            player_data["name"] = base64.b64decode(player_data["name"]).decode("latin-1")
        except Exception:  # noqa: BLE001
            player_data["name"] = "decode_error"
        if player_data.get("team") == 1:
            blue_players.append(player_data)
            blue_score += int(player_data.get("score", 0))
        elif player_data.get("team") == 2:
            red_players.append(player_data)
            red_score += int(player_data.get("score", 0))
    blue_players.sort(key=lambda p: int(p.get("score", 0)), reverse=True)
    red_players.sort(key=lambda p: int(p.get("score", 0)), reverse=True)

    for i, player in enumerate(blue_players):
        y_base = 120 + (32 * i)
        skin = ALL_PORTRAITS.get(player.get("skin", "mullins"))
        if skin is not None:
            canvas_image.paste(skin, (160, y_base), skin)
        draw_string_at(canvas_image, spritesheet, player["name"], 192, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 192, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get("score", 0)), 256, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 192, y_base + 16, "#b5b2b5")
        frames_total = player.get("frames_total", 0)
        time_min = math.floor(math.floor(int(frames_total) / 10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time_min}", 192, y_base + 24, "#b5b2b5")

    for i, player in enumerate(red_players):
        y_base = 120 + (32 * i)
        skin = ALL_PORTRAITS.get(player.get("skin", "mullins"))
        if skin is not None:
            canvas_image.paste(skin, (160, y_base), skin)
        draw_string_at(canvas_image, spritesheet, player["name"], 372, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 372, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get("score", 0)), 436, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 372, y_base + 16, "#b5b2b5")
        frames_total = player.get("frames_total", 0)
        time_min = math.floor(math.floor(int(frames_total) / 10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time_min}", 372, y_base + 24, "#b5b2b5")

    draw_string_at(canvas_image, spritesheet, "Score: ", 192, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_score), 248, 68, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Score: ", 372, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_score), 428, 68, "#ffffff")


def draw_screenshot_hud(spritesheet: Image.Image, data: dict, canvas_image: Image.Image) -> None:
    # Prefer flags loaded from PAKs; no-op if not available
    if FLAG_IMG_BLUE and FLAG_IMG_RED:
        canvas_image.paste(FLAG_IMG_BLUE, (160, 55), FLAG_IMG_BLUE)
        canvas_image.paste(FLAG_IMG_RED, (340, 55), FLAG_IMG_RED)
    else:
        # Fallback to asset images if provided
        try:
            asset_dir = os.path.join(os.path.dirname(__file__), "assets")
            blueflag_img = Image.open(os.path.join(asset_dir, "blueflag.png")).convert("RGBA")
            redflag_img = Image.open(os.path.join(asset_dir, "redflag.png")).convert("RGBA")
            canvas_image.paste(blueflag_img, (160, 55), blueflag_img)
            canvas_image.paste(redflag_img, (340, 55), redflag_img)
        except FileNotFoundError:
            # If neither PAK nor assets provide flags, continue without them
            logger.info("Flag HUD images not available; continuing without them")

    server_info = data.get("server", {})
    blue_caps = server_info.get("num_flags_blue", 0)
    red_caps = server_info.get("num_flags_red", 0)
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 192, 78, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_caps), 312, 78, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 372, 78, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_caps), 492, 78, "#ffffff")
    draw_players(data, canvas_image, spritesheet)


def generate_screenshot_for_port(port: str, sofplus_data_path: str, data: dict) -> str | None:
    if "server" not in data:
        logger.error("server_data is missing in data")
        return None

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

    if not canvas_image:
        logger.info("All background sources failed. Creating a black 640x480 canvas.")
        canvas_image = Image.new("RGBA", (640, 480), "black")
    else:
        overlay = Image.new("RGBA", canvas_image.size, (0, 0, 0, 128))
        canvas_image = Image.alpha_composite(canvas_image.convert("RGBA"), overlay)

    draw_screenshot_hud(spritesheet, data, canvas_image)

    try:
        final_path = os.path.expanduser(output_path)
        canvas_image.save(final_path)
        logger.info("Successfully created screenshot: %s", final_path)
        return final_path
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error saving the final image: %s", exc)
        return None
