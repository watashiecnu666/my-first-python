import json
import os

DATA_FILE='todo_list.json'

def load_tasks():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE,'r',cenicoding='utf-8')as f:
            return json.load(f)
        return []

def save_tasks(tasks):
    with open(DATA_FILE,'w',encoding='utf-8')as f:
        json.dump(tasks,f,ensure_ascii=False,indent=4)
    
