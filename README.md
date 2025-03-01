# Paim0n Genshin Impact AI Chatbot

After downloading the program and data files, follow the commands below to initialize a virtual environment, then run the main program. 
If hosting from VS Code, run commands through WSL. 

Successfully run the following commands once to initialize the chatbot fully:
```bash
python3 -m venv .venv
source .venv/bin/activate # Linux 
pip install -r requirements.txt
python main.py
```

Subsequent chatbot runs can be executed by the following: 
```bash
source .venv/bin/activate # Linux
python main.py # https://localhost:5000
```
