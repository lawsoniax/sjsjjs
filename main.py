import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import asyncio
import datetime
import logging
import time
import json
import secrets
import string
import io
import random
import requests 

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1462815057669918821
ADMIN_IDS = [1358830140343193821, 1039946239938142218]
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"
LOGGER_SERVICE_URL = "https://senin-logger-projen.onrender.com/send_log" 

# --- INITIAL KEY DATA ---
INITIAL_KEYS = {
    # Keylerin aynı kalabilir, buraya kopyalamana gerek yok, db dosyasına kaydediliyor zaten
}

# --- SYSTEM SETUP ---
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default(); intents.message_content = True; intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per day", "200 per hour"], 
    storage_uri="memory://"
)

online_users = {}
database = {"keys": {}, "users": {}, "history": [], "blacklisted_hwids": [], "blacklisted_ids": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                for k in ["keys", "users", "history", "blacklisted_hwids", "blacklisted_ids"]:
                    if k not in data: data[k] = [] if "list" in k else {}
                database = data
        except: pass
    else:
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump(database, f)
    except: pass

load_db()

def send_to_logger(payload):
    try: requests.post(LOGGER_SERVICE_URL, json=payload, timeout=2)
    except: pass

def parse_duration(s):
    s = s.lower()
    try: 
        if "d" in s: return int(s.replace("d",""))*24
        elif "h" in s: return int(s.replace("h",""))
        else: return int(s)
    except: return None

# --- FLASK ENDPOINTS (ÖNEMLİ KISIM) ---
@app.route('/', methods=['GET'])
def home(): return "System Operational"

@app.route('/verify', methods=['POST'])
@limiter.limit("60 per minute")
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False) # C++ true gönderiyor, Roblox false
        
        username = data.get("username")
        display_name = data.get("display_name")
        
        if request.headers.getlist("X-Forwarded-For"):
            ip = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip = request.remote_addr

        log_payload = {
            "key": key, "hwid": sent_hwid, "username": username,
            "ip": ip, "status": "Processing..."
        }

        # 1. Blacklist
        if sent_hwid in database["blacklisted_hwids"]:
            log_payload["status"] = "BANNED HWID"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Access Denied: HWID Banned"})
        
        # 2. Key Var mı?
        if key not in database["keys"]:
            log_payload["status"] = "Invalid Key"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]
        
        # İsim Kaydı
        if username and display_name:
            if is_loader: info["pc_user"] = f"{display_name}"
            else: info["last_roblox_name"] = f"{display_name} (@{username})"
            save_db()

        # 3. Süre Bitti mi?
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            log_payload["status"] = "Expired"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "License Expired"})

        # --- HWID KONTROLÜ (DUAL SYSTEM) ---
        valid_access = False
        
        if is_loader:
            # --- C++ LOADER (Bilgisayar HWID) ---
            saved_native = info.get("native_hwid")
            
            if saved_native is None:
                # İlk giriş: HWID kilitle
                info["native_hwid"] = sent_hwid
                save_db()
                valid_access = True
                log_payload["status"] = "Locked to PC"
            elif saved_native == sent_hwid:
                # Eşleşme başarılı
                valid_access = True
                log_payload["status"] = "Success (PC)"
            else:
                # Hata: Başka PC
                log_payload["status"] = "HWID Mismatch (PC)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "HWID Mismatch (Wrong PC)"})
                
        else:
            # --- ROBLOX SCRIPT (Exploit HWID) ---
            saved_roblox = info.get("roblox_hwid")
            
            if saved_roblox is None:
                info["roblox_hwid"] = sent_hwid
                save_db()
                valid_access = True
                log_payload["status"] = "Locked to Roblox"
            elif saved_roblox == sent_hwid:
                valid_access = True
                log_payload["status"] = "Success (Roblox)"
            else:
                log_payload["status"] = "HWID Mismatch (Roblox)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "HWID Mismatch (Wrong Exploit)"})

        if valid_access:
            rem = int(info["expires"] - time.time())
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            
            # Kalan süreyi güzel formatla
            days = rem // 86400
            hours = (rem % 86400) // 3600
            time_left_str = f"{days}d {hours}h"
            
            return jsonify({"valid": True, "msg": "Authenticated", "left": time_left_str})

    except Exception as e:
        print(e)
        return jsonify({"valid": False, "msg": "Server Error"})

# (Geri kalan Discord komutları aynı kalabilir)
# ...

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
