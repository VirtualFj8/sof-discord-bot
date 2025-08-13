# sof-discord-bot

## About
A production-ready Discord webhook bot for Soldier of Fortune (SoF1) servers. When a player triggers an in-game command, the bot:
- Exports live server and player info via a SoFPlus script (`info_client.func`)
- Detects the update, renders a scoreboard image with portraits and stats
- Optionally posts a rich embed with the image to a Discord channel via webhook

This repository includes minimal vendored utilities to read SoF PAK assets for portraits.

## Features
- File watcher monitors `user-<port>/sofplus/data/info_server/server.cfg`
- Robust scoreboard image rendering with fallbacks for map backgrounds
- Portraits decoded from game PAKs (`pak0.pak`, `pak2.pak`)
- Discord webhook integration with environment-based configuration
- Configurable logging and clean CLI entry point
- Linux and Windows setup scripts

## Repository layout
- `info_client.func`: SoFPlus script that exports server and client info when players issue `.wantplay`, `.match1`, `.match2`
- `src/sof_discord_bot/`
  - `cli.py`: Console entry point (`sof-discord-bot`)
  - `watcher.py`: Watches for server update triggers and orchestrates processing
  - `exporter.py`: Parses exported config files into structured data
  - `scoreboard.py`: Loads portraits from PAKs and renders the scoreboard image
  - `discorder.py`: Builds and sends Discord webhook payloads
  - `vendor/`: Thin wrappers around `pak.py` and `m32lib.py`
  - `assets/`: Place `conchars.png`, `blueflag.png`, `redflag.png`, and optionally map screenshots
- `pak.py`, `m32lib.py`: Vendored support libraries (kept at repo root, imported by package)
- `setup_env.sh`, `setup_env.bat`: Convenience scripts to create a venv and install deps
- `pyproject.toml`: Build and install configuration
- `requirements.txt`: Pinned runtime deps for non-build installs

## Prerequisites
- Python 3.9+
- Pillow, requests, watchdog, python-dotenv
- SoF server directory structure, e.g. `.../base` and user folders like `../user-28910/`

## Installation
You can either run from source with a virtual environment or install as a package.

### Option A: Run from source
1. Clone this repository into the folder where `sof.exe` resides (so parent path points to SoF root):
   - Example tree: `./sof.exe`, `./base/`, `./user-28910/`, `./sof-discord-bot/`
2. Create a venv and install dependencies:
   - Linux/macOS (setup only): `./setup_env.sh`
   - Linux/macOS (setup + activate current shell): `source setup_env.sh`
   - Windows: `setup_env.bat`
   - Manual activation after setup (Linux/macOS): `source sof-discord-venv/bin/activate`
3. Copy `info_client.func` to each server's addons folder:
   - `user-<PORT>/sofplus/addons/info_client.func`
   - For many servers, you may place it in `base/sofplus/addons/` instead
4. Place required assets into `src/sof_discord_bot/assets/`:
   - `conchars.png` (console charset spritesheet)
   - `blueflag.png`, `redflag.png`
   - Optional map backgrounds: `assets/sof_inter_ss/<map>.png` or `assets/MAPS_SCREENSHOTS/<map_path>.png`
5. Configure environment variables (optional but recommended):
   - Create a `.env` file at repo root with:
     - `DISCORD_WEBHOOK_URL=...`
     - `SOF_BOT_LOG=INFO` (or `DEBUG`)

Run the watcher from repo root:

```bash
source sof-discord-venv/bin/activate  # Linux/macOS

# Method 1 (recommended): install package and run console script
pip install -e .
sof-discord-bot

# Method 2: run as module with src-layout
PYTHONPATH=src python3 -m sof_discord_bot.cli

# Method 3: use helper launcher (adds src to sys.path)
python3 run.py
```

### Option B: Install as a package
1. From repo root:
   ```bash
   pip install -e .
   # or a regular build/install
   # pip install .
   ```
2. Set env variables as above (or use `.env`).
3. Execute:
   ```bash
   sof-discord-bot
   ```

## How it works
1. In-game commands call functions defined in `info_client.func`:
   - `.wantplay`, `.match1`, `.match2`
   - These write server info to `user-<PORT>/sofplus/data/info_server/server.cfg` and client info to `.../info_client/player_<SLOT>.cfg`
2. The watcher listens for modifications to `server.cfg`, parses the data, then renders `info_image/ss.png` under the same `sofplus/data` path.
3. If `DISCORD_WEBHOOK_URL` is set, you can extend `watcher.py` to call `discorder.generate_payload()` and `discorder.send_to_discord()` with the latest data and an image URL or attachment workflow.

## Discord webhook integration
- Set `DISCORD_WEBHOOK_URL` in `.env` or environment.
- Build a payload with `discorder.generate_payload()`.
- Send with `discorder.send_to_discord()`.
- For image delivery, you can:
  - Host `ss.png` via a web server and pass a full URL in the `image_url` parameter.
  - Or extend the code to upload the image as a multipart attachment to a bot (requires a bot token and Discord API changes not included by default).

## Assets and backgrounds
- Portraits are loaded from `pak0.pak` and `pak2.pak` under `<SoF root>/base/`.
- Map backgrounds are tried in this order:
  - Local: `assets/sof_inter_ss/<map>.png` where `<map>` is `dmjpnctf1` for `dm/dmjpnctf1`
  - Remote: `http://mods.sof1.org/wp-content/uploads/2011/05/<map>.png`
  - Local fallback: `assets/MAPS_SCREENSHOTS/dm/dmjpnctf1.png` resized to 640x480
- If none found, a solid black canvas is used.

## Configuration
- `SOF_BOT_LOG`: Set log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
- `DISCORD_WEBHOOK_URL`: Webhook endpoint to post messages (optional).

## Development
- Code lives under `src/sof_discord_bot` with type hints and modular structure.
- Logging is centralized in `logging_utils.py`.
- To run lint/type checks (optional suggestions):
  - `pip install ruff mypy`
  - `ruff check src`
  - `mypy src`

## SoFPlus script (`info_client.func`)
- Place into `user-<PORT>/sofplus/addons/` or `base/sofplus/addons/`.
- Exports per-player files as `info_client/player_<slot>.cfg` and server info to `info_server/server.cfg`.
- Provides commands for players:
  - `.wantplay`
  - `.match1`
  - `.match2`

## Run as a systemd service (Linux)
Below is a minimal service template. Adjust paths and user/group.

1) Create a dedicated user (optional but recommended):
```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin sofbot || true
```

2) Place the repo and create a venv as that user, then install the package into the venv:
```bash
sudo mkdir -p /opt/sof-discord-bot
sudo chown -R sofbot:sofbot /opt/sof-discord-bot
sudo -u sofbot git clone <this-repo> /opt/sof-discord-bot
cd /opt/sof-discord-bot
sudo -u sofbot -H bash -lc 'cd /opt/sof-discord-bot && ./setup_env.sh'
sudo -u sofbot -H bash -lc 'source /opt/sof-discord-bot/sof-discord-venv/bin/activate && pip install -e .'
```

3) Configure environment:
```bash
sudo cp systemd/sof-discord-bot.env.example /etc/default/sof-discord-bot
sudo nano /etc/default/sof-discord-bot  # set DISCORD_WEBHOOK_URL, SOF_BOT_LOG
```

4) Install the service unit (uses the console script installed above):
```bash
sudo cp systemd/sof-discord-bot.service /etc/systemd/system/sof-discord-bot.service
sudo nano /etc/systemd/system/sof-discord-bot.service  # adjust WorkingDirectory and venv path if needed
sudo systemctl daemon-reload
sudo systemctl enable sof-discord-bot
sudo systemctl start sof-discord-bot
```

Alternative service (without installing the package):
- Set `Environment=PYTHONPATH=/opt/sof-discord-bot/src` and use `ExecStart=/opt/sof-discord-bot/sof-discord-venv/bin/python -m sof_discord_bot.cli` in the unit file.

5) Manage the service:
```bash
sudo systemctl status sof-discord-bot
sudo systemctl restart sof-discord-bot
sudo systemctl stop sof-discord-bot
journalctl -u sof-discord-bot -f
```

## License
MIT for this repository. Game assets remain the property of their respective owners.
