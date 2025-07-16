# sof-discord-bot
## About
Includes pak.py from pypak project (d3), m32lib.py from pym32lib project (d3)  
## Instructions
Ensure your user folder has the port in its name, like user-28910.  
Clone this repo into the folder where sof.exe resides.  It will use ".." (parent) to access the sof directories.    
Place info_client.func into user-{YOURPORT}/sofplus/addons/ directory.  (If you have host many servers, many user-{PORTS}, you might consider placing it into base/sofplus/addons/ directory instead, for all servers to load the same file.  
The sof_exporter.py is the main program entry, that loops to listen for file modified changes on a specific file within user-{PORT}/sofplus/data/info_server/server.cfg. When this file is modified, it indicates that a player has requested to export data.  
It's necessary to setup a python venv folder with the dependencies.  
The provided setup_env.sh or setup_env.bat(for windows) helps with this.  
**use screen or dtach or nohup to launch the program.**

## Developers
We use : `pip freeze > requirements.txt` to generate the python dependencies automatically. (requirements.txt)  