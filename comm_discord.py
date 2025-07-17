
import requests
from fakedata import player_data_array
from datetime import datetime

webhook_url = "https://canary.discord.com/api/webhooks/1389994799255523459/eQfZ5L2LA2XMezOL92KjKnMTL-6FKB5pVv9ZYKVqpRuAGT3B4CbLgPGYEL80DYLkc5j6"

def get_formatted_datetime():
    now = datetime.now()

    day = now.day
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]

    day_str = f"{day}{suffix}"
    weekday = now.strftime("%A")
    month = now.strftime("%B")    

    time_12h = now.strftime("%I:%M%p").lstrip("0")  
    time_24h = now.strftime("%H:%M")                

    return f"**{weekday}, {day_str} {month} {time_12h} ({time_24h})**"

header = get_formatted_datetime()

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
    # player_names = ", ".join([player.name for player in player_data]) <- ALL NAMES TOGETHER
    player_names = "\n- " + "\n- ".join([player.name for player in player_data]) # NAMES 1 EACH LINE
    caller_name = player_data[slot_caller].name

    ### Getting modes
    if mode == ".wantplay":
        send_to_discord(
            f"# Match Request for [_{header}_]\n"
            f"```diff\n+ Players: ```"
            f"```diff{player_names} ```"
            f"```diff\n+ Competitive match is wanted by {caller_name}```"
        )
    """ elif mode == ".match1":
        send_to_discord(
            f"Match is on the way! {player_names} need 1 player or an odd-sized group (3, 5, etc.). "
            f"{caller_name} is calling! Come if you're free and want to play!"
        )
    elif mode == ".match2":
        send_to_discord(
            f"Match is on the way! {player_names} need 2 players or an even-sized group (4, 6, etc.). "
            f"{caller_name} is calling! Come if you're free and want to play!"
        ) """
    
# Clase Player para crear objetos a partir de los dicts
class Player:
    def __init__(self, data):
        self.name = data.get("name", "Unknown")
        self.score = data.get("score", 0)
        self.ping = data.get("ping", 0)
        self.team = data.get("team", "")
        self.deaths = data.get("deaths", 0)
        self.frags = data.get("frags", 0)
        self.suicides = data.get("suicides", 0)
        self.teamkills = data.get("teamkills", 0)
        self.spectator = data.get("spectator", 0)
        self.flags_captured = data.get("flags_captured", 0)
        self.flags_recovered = data.get("flags_recovered", 0)
        self.frames_total = data.get("frames_total", 0)

# TEST desde fakedata
if __name__ == "__main__":
    # Convertimos la data de dicts a objetos Player
    player_list = [Player(data) for data in player_data_array]

    # Elegimos quién es el "slot_caller" (ej: el primero)
    slot_caller = 0

    print("Testing .wantplay")
    comm_discord(".wantplay", player_list, slot_caller)

    print("\nTesting .match1")
    comm_discord(".match1", player_list, slot_caller)

    print("\nTesting .match2")
    comm_discord(".match2", player_list, slot_caller)