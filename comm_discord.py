
import requests
import time
import re
import os

def comm_discord(player_data):
    for player in player_data:
        print(f'player data is {player["name"]}')
    
    MAIN_PATH = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(MAIN_PATH, "user-server", "sof.log")
    webhook_url = "your-url-here"

    def send_to_discord(message):
        payload = {"content": message}
        response = requests.post(webhook_url, json=payload)
        if response.status_code not in [200, 204]:  
            print(f"Error sending message to Discord: {response.status_code}")
            print(f"Response content: {response.text}") 
        else:
            print("Message sent to Discord.")

    def tail_log(file):
        with open(file, "r") as f:
            f.seek(0, 2)  
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                yield line.strip()

    def process_command(line):
        player_names = ", ".join([player["name"] for player in player_data])
        if re.search(r"\.wantplay", line):
            send_to_discord(f"Players: {player_names} are in server to frag some asses! If you're online and want some fun, double click your SoF icon! GoGoGo!")
        elif re.search(r"\.match1", line):
            send_to_discord(f"Match is on the way! {player_names} need 1 player or an odd-sized group (3, 5, etc.). Come if you're free and want to play!")
        elif re.search(r"\.match2", line):
            send_to_discord(f"Match is on the way! {player_names} need 2 players or an even-sized group (4, 6, etc.). Come if you're free and want to play!")

    for line in tail_log(log_file):
        if re.search(r"\.wantplay|\.match1|\.match2", line):
            process_command(line)
