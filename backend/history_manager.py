import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def add_download(entry):
    history = load_history()
    history.append(entry)
    save_history(history)

def update_download(url, new_data):
    history = load_history()
    
    for item in history:
        if item["url"] == url:
            item.update(new_data)
    
    save_history(history)