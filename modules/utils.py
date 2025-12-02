# modules/utils.py

import time

def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}")

def is_command(text):
    return text.startswith("/")