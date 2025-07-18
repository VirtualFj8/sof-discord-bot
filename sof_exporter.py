import base64

import os
import re

import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# KaS discord signal
#from comm_discord import comm_discord
# d3 scoreboard image gen
from gen_scoreboard import gen_scoreboard_init, generate_screenshot_for_port

# This script has been updated to use the 'watchdog' library to monitor for file creation.
# It actively watches for new 'server.cfg' files in user-specific directories.
# When a 'server.cfg' is created, it triggers the generation of a screenshot,
# using the corresponding player data and saving the output to a designated image folder.

def load_server_data(filepath):
    """Loads server data from a specified .cfg file."""
    server_data = {}
    
    if not os.path.isfile(filepath):
        print(f"Warning: Server config file not found: {filepath}")
        return server_data
    cvar_pattern = re.compile(r'set "([^"]+)" "([^"]*)"')
    try:
        with open(filepath, 'r', encoding='latin-1') as f:
            for line in f:
                match = cvar_pattern.match(line)
                if match:
                    key, value = match.groups()
                    if key.startswith('~discord_'):
                        clean_key = key.replace('~discord_', '')
                        #handle numbers separately.
                        if clean_key == "slot":
                            try:
                                server_data[clean_key] = int(value)
                            except ValueError:
                                server_data[clean_key] = value
                        else:
                            server_data[clean_key] = value
                    elif key.startswith('_sp_sv_info_'):
                        clean_key = key.replace('_sp_sv_info_', '')
                        #handle numbers separately.
                        if clean_key.startswith('num_'):
                            try:
                                server_data[clean_key] = int(value)
                            except ValueError:
                                server_data[clean_key] = value
                        else:
                            server_data[clean_key] = value
    except Exception as e:
        print(f"Error processing server config file {filepath}: {e}")
    return server_data

def load_player_data_from_files(directory_path):
    """
    Loads player data from .cfg files into a list, using the slot number
    from the filename as the index.
    """
    # Initialize a list of size 16 with None to represent slots 0-15.
    # This is created from scratch on each function call.
    players = [None] * 16
    

    if not os.path.isdir(directory_path):
        print(f"Warning: Player data directory not found: {directory_path}")
        return players

    cvar_pattern = re.compile(r'set "_sp_sv_info_client_([^"]+)" "([^"]*)"')
    file_pattern = re.compile(r'player_(\d+)\.cfg')

    for filename in os.listdir(directory_path):
        file_match = file_pattern.match(filename)
        if file_match:
            try:
                slot = int(file_match.group(1))

                # Ensure the slot is within the valid range (0-15) before assigning.
                if 0 <= slot < 16:
                    player_data = {}
                    filepath = os.path.join(directory_path, filename)

                    with open(filepath, 'r', encoding='latin-1') as f:
                        for line in f:
                            match = cvar_pattern.match(line)
                            if match:
                                key, value = match.groups()
                                if key in ['score', 'ping', 'team', 'deaths', 'frags', 'suicides', 'teamkills', 'spectator', 'flags_captured', 'flags_recovered', 'frames_total']:
                                    try:
                                        player_data[key] = int(value)
                                    except ValueError:
                                        player_data[key] = 0
                                else:
                                    player_data[key] = value

                    if 'name' in player_data:
                        player_data['name'] = base64.b64encode(player_data['name'].encode('latin-1')).decode('ascii')
                    
                    if player_data:
                        # Use the extracted slot as a direct index into the list.
                        players[slot] = player_data
                else:
                    print(f"Warning: Skipping file {filename} with out-of-range slot number: {slot}")

            except Exception as e:
                print(f"Error processing file {filename}: {e}")

    return players


def read_data_from_sof_server(port, sofplus_data_path):
    # Define paths based on the detected port
    
    server_cfg_path = os.path.join(sofplus_data_path, 'info_server/server.cfg')
    player_data_path = os.path.join(sofplus_data_path, 'info_client')

    # Load server and player data
    server_data = load_server_data(server_cfg_path)
    if not server_data:
        print(f"Could not load server data for port {port}. Aborting.")
        return None
        
    loaded_players = load_player_data_from_files(player_data_path)

    # Construct the main data object
    data = {"server": server_data, "players": loaded_players}

    print(f"---Read data successfully for port {port} ---")
    return data


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
                sofplus_data_path = f'../user-{port}/sofplus/data'
                if not os.path.exists(sofplus_data_path):
                    # This should exist.
                    print(f"Directory: `{sofplus_data_path}` Does Not Exist.")
                    return
                exported_data = read_data_from_sof_server(port, sofplus_data_path)
                if exported_data is not None:
                    #d3 image gen.
                    generate_screenshot_for_port(port, sofplus_data_path, exported_data)
                    #kasey discord signal.
                    #comm_discord(port, sofplus_data_path, exported_data["players"])
            else:
                print(f"Could not extract port from path: {src_path}")


def main():
    sof_dir = os.path.dirname(os.getcwd())

    """
    Init
    """
    gen_scoreboard_init(sof_dir)
    
    """
    Sets up and starts the watchdog file monitor.
    """
    
    print(f"Starting file monitor on this directory: {sof_dir}")
    # Initialize the event handler with a 10-second cooldown.
    event_handler = ServerCfgEventHandler(cooldown=10)
    observer = Observer()
    observer.schedule(event_handler, sof_dir, recursive=True)
    
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