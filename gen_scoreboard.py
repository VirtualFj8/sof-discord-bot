import os
import base64
import math
import sys
import requests

from PIL import Image
from io import BytesIO

#d3 sof libs
from pak import unpack_one_to_memory
import m32lib

def gen_scoreboard_init(sof_dir):
    """
    Prepare some resource files from sof .pak by loading all portraits.
    """

    # Load all portraits and store them in a variable
    # This variable can then be passed to other functions or stored globally
    all_portraits = load_all_portraits(sof_dir)
    
    print(f"\n--- Initialization complete: {len(all_portraits)} portraits loaded successfully. ---")
    
    # You can now use the 'all_portraits' dictionary. For example:
    # mullins_img = all_portraits.get("mullins")
    # if mullins_img:
    #     mullins_img.show() # Displays the image

    return all_portraits

def load_all_portraits(sof_dir):
    """
    Loads all M32 portraits from the SoF PAK files into memory.

    This function iterates through predefined lists of portrait files,
    unpacks them from their respective PAK archives, and converts them
    into PIL Image objects.

    Args:
        sof_dir (str): The path to the main Soldier of Fortune directory
                       (containing 'base', 'pak2', etc.).

    Returns:
        dict: A dictionary where keys are portrait names (e.g., 'mullins')
              and values are the corresponding PIL Image objects.
    """
    portrait_images = {}
    
    # NOTE: Your original code uses "portaits". 
    # If the correct path is "portraits", you must change it here.
    base_path_in_pak = "ghoul/pmodels/portraits"

    # Define which portraits are in which PAK directory.
    portrait_sources = {
        "pak0.pak": [
            "amu.m32","assassin.m32","bear.m32","bonesnapper.m32","breaker.m32","butcher.m32",
            "captain.m32","cleaner.m32","cleaver.m32","crackshot.m32","crusher.m32","deadeye.m32",
            "defender.m32","dekker.m32","dragon.m32","enforcer.m32","fireball.m32","fist.m32","fixer.m32",
            "freeze.m32","ghost.m32","gimp.m32","grinder.m32","guard.m32","hawk.m32","iceman.m32",
            "icepick.m32","lieutenant.m32","mohawk.m32","mullins.m32","muscle.m32","ninja.m32",
            "ponytail.m32","princess.m32","rebel.m32","ripper.m32","sabre.m32","sam.m32","shadow.m32",
            "silencer.m32","skorpio.m32","slaughter.m32","slick.m32","stiletto.m32","strongarm.m32",
            "suit.m32","tank.m32","taylor.m32","wall.m32","whisper.m32"
        ],
        "pak2.pak": [
            "assault.m32","brick.m32","cobra.m32","commando.m32","jersey.m32","widowmaker.m32"
        ]
    }

    # Loop through each source (pak_dir) and its list of filenames
    for pak_dir, filenames in portrait_sources.items():
        for filename in filenames:
            try:
                # Construct the full path for the unpacker function
                m32_path_in_archive = os.path.join(base_path_in_pak, filename)
                pak_archive = os.path.join(sof_dir, "base",  pak_dir)

                # 1. Unpack the file data from the PAK archive
                m32_data = unpack_one_to_memory(pak_archive, m32_path_in_archive)

                # 2. Process the M32 header to get dimensions
                mipheader = m32lib.MipHeader(filename, m32_data)
                w = int(mipheader.width.read()[0])
                h = int(mipheader.height.read()[0])
                
                # 3. Create a PIL Image object from the raw pixel data
                image = Image.frombytes("RGBA", (w, h), mipheader.imgdata())

                # 4. Store the image in our dictionary, using the filename without extension as the key
                portrait_name = os.path.splitext(filename)[0]
                portrait_images[portrait_name] = image

            except Exception as e:
                print(f"Failed to load portrait '{filename}' from '{pak_dir}'. Error: {e}")
    
    return portrait_images

def draw_string_at(canvas_image, spritesheet, string, xpos, ypos, color_override=None):
    """Draws a string on the canvas using character sprites from a spritesheet."""
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


def draw_players(data, canvas_image, spritesheet):
    """Processes and draws player data onto the screenshot."""
    blue_players, red_players = [], []
    blue_score, red_score = 0, 0
    for player_data in list(data['players']):
        try:
            player_data['name'] = base64.b64decode(player_data['name']).decode('latin-1')
        except (base64.binascii.Error, UnicodeDecodeError) as e:
            player_data['name'] = "decode_error"
        if player_data.get('team') == 1:
            blue_players.append(player_data)
            blue_score += int(player_data.get('score', 0))
        elif player_data.get('team') == 2:
            red_players.append(player_data)
            red_score += int(player_data.get('score', 0))
    blue_players.sort(key=lambda p: int(p.get('score', 0)), reverse=True)
    red_players.sort(key=lambda p: int(p.get('score', 0)), reverse=True)
    for i, player in enumerate(blue_players):
        y_base = 120 + (32 * i)
        try:
            skin = all_portraits[p.get('skin', 'mullins')]
            canvas_image.paste(skin, (160, y_base), skin)
            draw_string_at(canvas_image, spritesheet, player['name'], 192, y_base)
            draw_string_at(canvas_image, spritesheet, "Score:  ", 192, y_base + 8, "#b5b2b5")
            draw_string_at(canvas_image, spritesheet, str(player.get('score', 0)), 256, y_base + 8, "#ffffff")
            draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 192, y_base + 16, "#b5b2b5")
            
            # Calculate and draw player time
            frames_total = player.get('frames_total', 0)
            time = math.floor(math.floor(int(frames_total)/10) / 60)
            draw_string_at(canvas_image, spritesheet, f"Time:   {time}", 192, y_base + 24, "#b5b2b5")
        except KeyError:
            print("fatal error, can't find the portraits.")
            sys.exit(1)
        
        

    for i, player in enumerate(red_players):
        y_base = 120 + (32 * i)
        try:
            skin = all_portraits[p.get('skin', 'mullins')]
            canvas_image.paste(skin, (340, y_base), skin)
            draw_string_at(canvas_image, spritesheet, player['name'], 372, y_base)
            draw_string_at(canvas_image, spritesheet, "Score:  ", 372, y_base + 8, "#b5b2b5")
            draw_string_at(canvas_image, spritesheet, str(player.get('score', 0)), 436, y_base + 8, "#ffffff")
            draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 372, y_base + 16, "#b5b2b5")

            # Calculate and draw player time
            frames_total = player.get('frames_total', 0)
            time = math.floor(math.floor(int(frames_total)/10) / 60)
            draw_string_at(canvas_image, spritesheet, f"Time:   {time}", 372, y_base + 24, "#b5b2b5")
        except KeyError:
            print("fatal error, can't find the portraits.")
            sys.exit(1)

    draw_string_at(canvas_image, spritesheet, "Score: ", 192, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_score), 248, 68, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Score: ", 372, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_score), 428, 68, "#ffffff")

def draw_screenshot_hud(spritesheet, data, canvas_image):
    """Draws the main HUD elements on the screenshot."""
    try:
        blueflag_img = Image.open('blueflag.png').convert("RGBA")
        redflag_img = Image.open('redflag.png').convert("RGBA")
        
    except FileNotFoundError as e:
        print(f"FATAL: Asset file not found: {e}. Make sure blueflag.png, redflag.png, and mullins.png are in the script's directory.")
        return


    canvas_image.paste(blueflag_img, (160, 55), blueflag_img)
    canvas_image.paste(redflag_img, (340, 55), redflag_img)
    server_info = data.get("server", {})
    blue_caps = server_info.get("num_flags_blue", 0)
    red_caps = server_info.get("num_flags_red", 0)
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 192, 78, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_caps), 312, 78, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Flag Captures: ", 372, 78, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_caps), 492, 78, "#ffffff")
    draw_players(data, canvas_image, spritesheet)

def generate_screenshot_for_port(port, sofplus_data_path, data):
    """
    Main logic to generate a screenshot for a specific server port.
    This function is triggered when a new server.cfg is detected.
    """
    if "server" not in data:
        print("server_data not existing in data...")
        return

    server_data = data["server"]
    print(f"\n--- Triggered screenshot generation for port {port} ---")
    
    output_dir = os.path.join(sofplus_data_path, 'info_image')
    output_path = os.path.join(output_dir, 'ss.png')

    # Ensure the output directory exists, creating it if necessary
    os.makedirs(output_dir, exist_ok=True)
    
    # Load base assets (spritesheet)
    try:
        spritesheet = Image.open('conchars.png').convert("RGBA")
    except FileNotFoundError:
        print("FATAL: Could not load 'conchars.png'. Make sure it's in the script's directory.")
        return

    # Determine map and load background image
    map_full_name = server_data.get("map_current", "dm/dmjpnctf1").lower()
    map_substr = ''.join(map_full_name.split('/'))
    
    canvas_image = None
    local_bg_path = f"sof_inter_ss/{map_substr}.png"
    web_bg_url = f"http://mods.sof1.org/wp-content/uploads/2011/05/{map_substr}.png"
    maps_screenshots_path = f"MAPS_SCREENSHOTS/{map_full_name}.png"

    # Try loading background from various sources
    try:
        canvas_image = Image.open(local_bg_path).convert("RGBA")
        print(f"Loaded local background: {local_bg_path}")
    except FileNotFoundError:
        print(f"Local background '{local_bg_path}' not found. Trying web fallback.")
        try:
            response = requests.get(web_bg_url)
            response.raise_for_status()
            canvas_image = Image.open(BytesIO(response.content)).convert("RGBA")
            print(f"Loaded web background from {web_bg_url}")
        except requests.exceptions.RequestException:
            print(f"Web background failed. Trying '{maps_screenshots_path}'.")
            try:
                img = Image.open(maps_screenshots_path).convert("RGBA")
                canvas_image = img.resize((640, 480)) # Resize as requested
                print(f"Loaded and resized local background from {maps_screenshots_path}")
            except FileNotFoundError:
                print(f"'{maps_screenshots_path}' not found.")

    if not canvas_image:
            print("All background sources failed. Creating a black 640x480 canvas.")
            canvas_image = Image.new("RGBA", (640, 480), "black")
    else:
        # Create a semi-transparent overlay to darken the background
        overlay = Image.new('RGBA', canvas_image.size, (0, 0, 0, 128)) # Black with 50% opacity
        canvas_image = Image.alpha_composite(canvas_image.convert('RGBA'), overlay)

    # Draw the screenshot content
    draw_screenshot_hud(spritesheet, data, canvas_image)

    # Save the final image to the port-specific directory
    try:
        final_path = os.path.expanduser(output_path)
        canvas_image.save(final_path)
        print(f"Successfully created screenshot: {final_path}")
    except Exception as e:
        print(f"Error saving the final image: {e}")