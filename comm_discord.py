
import requests
import os

webhook_url = "your-url-here"

def send_to_discord(message):
    payload = {"content": message}
    response = requests.post(webhook_url, json=payload)
    if response.status_code not in [200, 204]:  
        print(f"Error sending message to Discord: {response.status_code}")
        print(f"Response content: {response.text}") 
    else:
        print("Message sent to Discord.")


def comm_discord(mode, player_data, slot_caller):

    ### Debugging data ( - Not really needed for this purpose - )
    for player in player_data:
        print(f'player data is {player.name}')

    ### Getting names
    player_names = ", ".join([player.name for player in player_data])
    caller_name = player_data[slot_caller].name

    ### Getting modes
    if mode == ".wantplay":
        send_to_discord(
            f"Players: {player_names} are in server to frag some asses! "
            f"{caller_name} says: If you're online and want some fun, double click your SoF icon! GoGoGo!"
        )
    elif mode == ".match1":
        send_to_discord(
            f"Match is on the way! {player_names} need 1 player or an odd-sized group (3, 5, etc.). "
            f"{caller_name} is calling! Come if you're free and want to play!"
        )
    elif mode == ".match2":
        send_to_discord(
            f"Match is on the way! {player_names} need 2 players or an even-sized group (4, 6, etc.). "
            f"{caller_name} is calling! Come if you're free and want to play!"
        )
      