import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import asyncio
import logging
import time
import json
import secrets
import string
import requests
import io

# --- AYARLAR ---
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1460981897730592798 
DB_FILE = "anarchy_keys.json" # Sadece keyleri tutar

# BURAYA LOGGER.PY'Yİ YÜKLEDİĞİN SİTENİN ADRESİNİ YAZ!
# Eğer aynı sunucudaysa http://127.0.0.1:5000 olabilir ama Render'da ayrı servislerse tam link lazım.
LOGGER_SERVICE_URL = "https://asdasdj.onrender.com" 

# --- DISCORD OAUTH ---
CLIENT_ID = "1464002253244600511" 
CLIENT_SECRET = "6djxraALuFvcg6ZLT_aDpHs94Y4PcUzj"
REDIRECT_URI = "https://sjsjjs.onrender.com/callback"

ADMIN_IDS = [1358830140343193821, 1039946239938142218]
INITIAL_KEYS = {} 
pending_logins = {}

logging.basicConfig(level=logging.ERROR)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True 

bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(get_remote_address, app=app, default_limits=["50000 per day"], storage_uri="memory://")

database = {"keys": {}, "blacklisted_hwids": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: database = json.load(f)
        except: pass
    else:
        database["keys"] = INITIAL_KEYS; save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

# --- YARDIMCI: LOGGER İLE İLETİŞİM ---
def log_to_service(user, key, hwid, ip, status):
    try:
        requests.post(f"{LOGGER_SERVICE_URL}/send_log", json={
            "username": user, "key": key, "hwid": hwid, "ip": ip, "status": status
        }, timeout=1) # Hızlı olsun diye timeout kısa
    except: pass

def check_security(hwid):
    try:
        r = requests.post(f"{LOGGER_SERVICE_URL}/check_status", json={"hwid": hwid}, timeout=2)
        return r.json() # {"allowed": True/False, "msg": "..."}
    except: return {"allowed": True} # Logger çökerse sistemi durdurma

def punish_user(hwid):
    try: requests.post(f"{LOGGER_SERVICE_URL}/add_strike", json={"hwid": hwid}, timeout=1)
    except: pass

def clear_punish(hwid):
    try: requests.post(f"{LOGGER_SERVICE_URL}/clear_strike", json={"hwid": hwid}, timeout=1)
    except: pass

def get_ip():
    if request.headers.getlist("X-Forwarded-For"): return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

# --- ENDPOINTS ---

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        ip = get_ip()

        # 1. Logger'a sor: Bu adam banlı mı?
        sec_check = check_security(hwid)
        if not sec_check["allowed"]:
            return jsonify({"success": False, "msg": sec_check["msg"]})

        if hwid in database["blacklisted_hwids"]:
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member_named(discord_name) if guild else None
        
        if not member:
            punish_user(hwid) # Hata -> Ceza Puanı
            return jsonify({"success": False, "msg": "User Not Found"})

        # Zaten key var mı?
        existing_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == member.id and time.time() < v.get("expires", 0):
                existing_key = k
                break
        
        if existing_key:
            return jsonify({"success": False, "msg": "Already Registered!"})

        # Yeni Key
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid, "roblox_nick": "N/A", 
            "expires": time.time() + (7 * 86400), "assigned_id": member.id,
            "registered_name": discord_name, "pc_user": pc_user
        }
        save_db()
        
        clear_punish(hwid) # Başarılı -> Temizle
        asyncio.run_coroutine_threadsafe(member.send(f"Anarchy License: `{new_key}`"), bot.loop)
        log_to_service(discord_name, new_key, hwid, ip, "New Register")
        
        return jsonify({"success": True, "msg": "Sent to DM"})
    except: return jsonify({"success": False, "msg": "Error"})

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        roblox = data.get("roblox_user")
        ip = get_ip()

        # 1. Logger'a sor
        sec_check = check_security(hwid)
        if not sec_check["allowed"]: return jsonify({"valid": False, "msg": sec_check["msg"]})

        if key not in database["keys"]:
            punish_user(hwid) # Hata -> Ceza Puanı
            log_to_service("Unknown", key, hwid, ip, "Invalid Key Attempt")
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        if info.get("native_hwid") and info.get("native_hwid") != hwid:
            return jsonify({"valid": False, "msg": "Wrong HWID"})
        
        if not info.get("native_hwid"): 
            info["native_hwid"] = hwid; save_db()

        if roblox: info["roblox_nick"] = roblox; save_db()

        clear_punish(hwid) # Başarılı -> Temizle
        log_to_service(info.get("registered_name"), key, hwid, ip, "Login Success")
        return jsonify({"valid": True, "msg": "Success"})

    except: return jsonify({"valid": False, "msg": "Error"})

# ... (Discord OAuth ve Bot Komutları aynı kalacak, sadece DB referanslarına dikkat et) ...
# Callback ve diğer kısımları yer tasarrufu için tekrar yazmıyorum, önceki kodla aynı kalabilir.
# Sadece `database["keys"]` kullanıldığından emin ol.

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
