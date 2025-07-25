
import requests
from fakedata import player_data_array
from datetime import datetime, timezone

webhook_url = "your-url-here"

def get_date():
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

def generate_payload(caller_name, red_team, blue_team, custom_msg=None, total_players=None):

    fields = [
        {
            "name": "Red team",
            "value": ", ".join(red_team) or "None",
            "inline": True
        },
        {
            "name": "Blue team",
            "value": ", ".join(blue_team) or "None",
            "inline": False
        }
    ] 
    if total_players is not None:
        fields.append({
            "name": "Total players",
            "value": str(total_players),
            "inline": True
        })
        
    return {
        "username": "🔴 [LIVE] SoF Gamers",
        "avatar_url": "https://www.sof1.org/gallery/image/7656/medium",
        "content": "\n\u200b\n 🕹️ **SCOREBOARD** 🕹️\n\u200b\n ",
        "embeds": [
            {
                "title": "SoF Live Scoreboard",
                "description": "Now in-game",
                "url": "https://www.sof1.org/gallery/image/846/medium",
                "color": 3447003,
                "image": {
                    "url": "https://www.sof1.org/gallery/image/846/medium"
                },
                "thumbnail": {
                    "url": "https://www.sof1.org/gallery/image/846/medium"
                },
                "author": {
                    "name": caller_name,
                    "url": "https://www.sof1.org/",
                    "icon_url": "https://www.sof1.org/gallery/image/7656/medium"
                },
                "fields": fields, 
                "footer": {
                    "text": "Sent from SoF Server A", # f"Sent from {server_name}"
                    "icon_url": "https://example.com/footer_icon.png"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }

def send_to_discord(payload): #payload
    #payload = {"content": payload} TRUE ONE
    response = requests.post(webhook_url, json=payload)
    if response.status_code not in [200, 204]:  
        print(f"Error sending message to Discord: {response.status_code}")
        print(f"Response content: {response.text}") 
    else:
        print("Message sent to Discord.")


def comm_discord(mode, player_data, slot_caller):

    request_date = get_date()

    ### Debugging data ( - Not really needed for this purpose - )
    for player in player_data:
        print(f'player data is {player.name}')

    ### Getting players, teams, etc.
    # player_names = ", ".join([player.name for player in player_data]) <- NAMES: ALL TOGETHER
    total_players = len(player_data)
    player_names = "\n- " + "\n- ".join([player.name for player in player_data]) # <- NAMES: 1 EACH LINE
    red_team = [player.name for player in player_data if player.team.lower() == "red"]
    blue_team = [player.name for player in player_data if player.team.lower() == "blue"]
    caller_name = player_data[slot_caller].name 

    ### Getting modes
    if mode == ".wantplay":
        message = (
            f"# Match Request for [_{request_date}_]\n"
            f"```diff\n+ Players: ```"
            f"```diff{player_names} ```"
            f"```diff\n+ Competitive match is wanted by {caller_name}```"
        )
    elif mode == ".match1":
        message = (
            f"# Match Request for [_{request_date}_]\n"
            f"```diff\n+ Players: ```"
            f"```diff{player_names} ```"
            f"```diff\n+ Match is on the way! We need 1 player or an odd-sized group (3, 5, etc.). ```"
        )
    elif mode == ".match2":
        message = (
            f"# Match Request for [_{request_date}_]\n"
            f"```diff\n+ Players: ```"
            f"```diff{player_names} ```"
            f"```diff\n+ Match is on the way! We need 2 players or an even-sized group (4, 6, etc.). ```"
        )
    
    payload = generate_payload(caller_name, red_team, blue_team, message, total_players)
    send_to_discord(payload)
    
class Player:
    def __init__(self, data):
        self.name = data.get("name", "Unknown")
        self.score = data.get("score", 0)
        self.ping = data.get("ping", 0)
        self.team = data.get("team", "")
        self.deaths = data.get("deaths", 0)
        self.frags = data.get("frags", 0)
        self.suicidekills = data.get("suicidekills", 0)
        self.teamkills = data.get("teamkills", 0)
        self.spectator = data.get("spectator", 0)
        self.flags_captured = data.get("flags_captured", 0)
        self.flags_recovered = data.get("flags_recovered", 0)
        self.frames_total = data.get("frames_total", 0)

if __name__ == "__main__":
    player_data = [Player(data) for data in player_data_array]

    slot_caller = 0

    mode = input("Type a cmd to test it (.wantplay, .match1, .match2): ").strip()
    if mode in [".wantplay", ".match1", ".match2"]:
        comm_discord(mode, player_data, slot_caller)
    else:
        print("Unknown cmd.")