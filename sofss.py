import base64
import requests
from PIL import Image
import os
import re
from io import BytesIO
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# This script has been updated to use the 'watchdog' library to monitor for file creation.
# It actively watches for new 'server.cfg' files in user-specific directories.
# When a 'server.cfg' is created, it triggers the generation of a screenshot,
# using the corresponding player data and saving the output to a designated image folder.

# --- [Original Drawing and Data Loading Functions - No Changes] ---

# The color array for parsing in-string color codes.
COLOR_ARRAY = [
    "#ffffff", "#FFFFFF", "#FF0000", "#00FF00", "#ffff00", "#0000ff", "#ff00ff",
    "#00ffff", "#000000", "#7f7f7f", "#ffffff", "#7f0000", "#007f00", "#ffffff",
    "#7f7f00", "#00007f", "#564d28", "#4c5e36", "#376f65", "#005572", "#54647e",
    "#54647e", "#66097b", "#705e61", "#980053", "#960018", "#702d07", "#54492a",
    "#61a997", "#cb8f39", "#cf8316", "#ff8020"
]

def load_server_data(filepath):
    """Loads server data from a specified .cfg file."""
    server_data = {}
    expanded_path = os.path.expanduser(filepath)
    if not os.path.isfile(expanded_path):
        print(f"Warning: Server config file not found: {expanded_path}")
        return server_data
    cvar_pattern = re.compile(r'set "([^"]+)" "([^"]*)"')
    try:
        with open(expanded_path, 'r', encoding='latin-1') as f:
            for line in f:
                match = cvar_pattern.match(line)
                if match:
                    key, value = match.groups()
                    if key.startswith('_sp_sv_info_'):
                        clean_key = key.replace('_sp_sv_info_', '')
                        if clean_key.startswith('num_'):
                            try:
                                server_data[clean_key] = int(value)
                            except ValueError:
                                server_data[clean_key] = value
                        else:
                            server_data[clean_key] = value
    except Exception as e:
        print(f"Error processing server config file {expanded_path}: {e}")
    return server_data

def load_player_data_from_files(directory_path):
    """Loads player data from .cfg files in a specified directory."""
    players = []
    expanded_path = os.path.expanduser(directory_path)
    if not os.path.isdir(expanded_path):
        print(f"Warning: Player data directory not found: {expanded_path}")
        return players
    cvar_pattern = re.compile(r'set "_sp_sv_info_client_([^"]+)" "([^"]*)"')
    for filename in os.listdir(expanded_path):
        if filename.endswith(".cfg"):
            player_data = {}
            filepath = os.path.join(expanded_path, filename)
            try:
                with open(filepath, 'r', encoding='latin-1') as f:
                    for line in f:
                        match = cvar_pattern.match(line)
                        if match:
                            key, value = match.groups()
                            if key in ['score', 'ping', 'team', 'deaths', 'frags', 'suicides', 'teamkills', 'spectator', 'flags_captured', 'flags_recovered','frames_total']:
                                try:
                                    player_data[key] = int(value)
                                except ValueError:
                                    player_data[key] = 0
                            else:
                                player_data[key] = value
                if 'name' in player_data:
                    player_data['name'] = base64.b64encode(player_data['name'].encode('latin-1')).decode('ascii')
                if player_data:
                    players.append(player_data)
            except Exception as e:
                print(f"Error processing file {filename}: {e}")
    return players

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

import base64
import math

def draw_players(data, canvas_image, mullins_img, spritesheet):
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
        canvas_image.paste(mullins_img, (160, y_base), mullins_img)
        draw_string_at(canvas_image, spritesheet, player['name'], 192, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 192, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get('score', 0)), 256, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 192, y_base + 16, "#b5b2b5")
        
        # Calculate and draw player time
        frames_total = player.get('frames_total', 0)
        time = math.floor(math.floor(int(frames_total)/10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time}", 192, y_base + 24, "#b5b2b5")

    for i, player in enumerate(red_players):
        y_base = 120 + (32 * i)
        canvas_image.paste(mullins_img, (340, y_base), mullins_img)
        draw_string_at(canvas_image, spritesheet, player['name'], 372, y_base)
        draw_string_at(canvas_image, spritesheet, "Score:  ", 372, y_base + 8, "#b5b2b5")
        draw_string_at(canvas_image, spritesheet, str(player.get('score', 0)), 436, y_base + 8, "#ffffff")
        draw_string_at(canvas_image, spritesheet, f"Ping:   {player.get('ping', 'N/A')}", 372, y_base + 16, "#b5b2b5")

        # Calculate and draw player time
        frames_total = player.get('frames_total', 0)
        time = math.floor(math.floor(int(frames_total)/10) / 60)
        draw_string_at(canvas_image, spritesheet, f"Time:   {time}", 372, y_base + 24, "#b5b2b5")

    draw_string_at(canvas_image, spritesheet, "Score: ", 192, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(blue_score), 248, 68, "#ffffff")
    draw_string_at(canvas_image, spritesheet, "Score: ", 372, 68, "#b5b2b5")
    draw_string_at(canvas_image, spritesheet, str(red_score), 428, 68, "#ffffff")

def draw_screenshot_hud(spritesheet, data, canvas_image):
    """Draws the main HUD elements on the screenshot."""
    try:
        blueflag_img = Image.open('blueflag.png').convert("RGBA")
        redflag_img = Image.open('redflag.png').convert("RGBA")
        mullins_img = Image.open('mullins.png').convert("RGBA")
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
    draw_players(data, canvas_image, mullins_img, spritesheet)


# --- [NEW and REFACTORED Logic] ---

def generate_screenshot_for_port(port):
    """
    Main logic to generate a screenshot for a specific server port.
    This function is triggered when a new server.cfg is detected.
    """
    print(f"\n--- Triggered screenshot generation for port {port} ---")
    
    # Define paths based on the detected port
    base_path = f'~/server/user-{port}/sofplus/data'
    server_cfg_path = os.path.join(base_path, 'info_server/server.cfg')
    player_data_path = os.path.join(base_path, 'info_client')
    output_dir = os.path.join(base_path, 'info_image')
    output_path = os.path.join(output_dir, 'ss.png')

    # Ensure the output directory exists, creating it if necessary
    os.makedirs(os.path.expanduser(output_dir), exist_ok=True)
    
    # Load server and player data
    server_data = load_server_data(server_cfg_path)
    if not server_data:
        print(f"Could not load server data for port {port}. Aborting.")
        return
        
    loaded_players = load_player_data_from_files(player_data_path)

    # Construct the main data object
    data = {"server": server_data, "players": loaded_players}

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
    
    print(f"--- Finished process for port {port} ---")


class ServerCfgEventHandler(FileSystemEventHandler):
    """
    Handles filesystem events, looking for the creation of 'server.cfg'.
    Introduces a cooldown to prevent rapid, repeated triggers.
    """
    PORT_REGEX = re.compile(r'user-(\d+)')

    def __init__(self, cooldown=10):
        """
        Initializes the event handler.
        :param cooldown: The minimum time in seconds between triggers for the same port.
        """
        self.cooldown = cooldown
        self.last_triggered_time = {}

    def on_modified(self, event):
        """
        Called when a file or directory is modified.
        """
        if event.is_directory:
            return

        src_path = event.src_path
        if src_path.endswith(os.path.join('info_server', 'server.cfg')):
            port_match = self.PORT_REGEX.search(src_path)
            if port_match:
                port = port_match.group(1)
                current_time = time.time()

                # Check if the port is currently in its cooldown period.
                last_time = self.last_triggered_time.get(port, 0)
                if current_time - last_time < self.cooldown:
                    return  # Still in cooldown, so we ignore this event and do nothing.

                # If not in cooldown, update the last triggered time and proceed.
                self.last_triggered_time[port] = current_time
                print(f"Detected valid modification for trigger file: {src_path}")
                
                # Give the system a moment to ensure all client files are also written.
                time.sleep(1) 
                generate_screenshot_for_port(port)
            else:
                print(f"Could not extract port from path: {src_path}")


def main():
    """
    Sets up and starts the watchdog file monitor.
    """
    path = os.path.expanduser('~/server')
    if not os.path.isdir(path):
        print(f"Error: Monitored directory '{path}' does not exist.")
        print("Please create it and the user subdirectories before running.")
        return

    print(f"Starting file monitor on directory: {path}")
    # Initialize the event handler with a 10-second cooldown.
    event_handler = ServerCfgEventHandler(cooldown=10)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    
    observer.start()
    print("Monitor started. Waiting for 'server.cfg' to be modified...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Monitor stopped by user.")
        observer.stop()
    
    observer.join()


if __name__ == "__main__":
    main()