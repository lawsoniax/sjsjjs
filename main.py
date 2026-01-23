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
DB_FILE = "anarchy_keys.json"

# LOGGER ADRESİ (Kendi Logger URL'nizi buraya yazın)
LOGGER_SERVICE_URL = "https://SENIN-LOGGER-SITEN.onrender.com" 

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
        }, timeout=1) 
    except: pass

def check_security(hwid):
    try:
        r = requests.post(f"{LOGGER_SERVICE_URL}/check_status", json={"hwid": hwid}, timeout=2)
        return r.json() 
    except: return {"allowed": True} 

def punish_user(hwid):
    try: requests.post(f"{LOGGER_SERVICE_URL}/add_strike", json={"hwid": hwid}, timeout=1)
    except: pass

def clear_punish(hwid):
    try: requests.post(f"{LOGGER_SERVICE_URL}/clear_strike", json={"hwid": hwid}, timeout=1)
    except: pass

def get_ip():
    if request.headers.getlist("X-Forwarded-For"): return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

# --- LUA ENDPOINTS ---
@app.route('/update_roblox', methods=['POST'])
def update_roblox():
    try:
        data = request.json
        key = data.get("key")
        roblox_user = data.get("roblox_user")
        if key in database["keys"] and roblox_user:
            database["keys"][key]["roblox_nick"] = roblox_user; save_db()
            return jsonify({"success": True})
        return jsonify({"success": False})
    except: return jsonify({"success": False})

@app.route('/get_users', methods=['GET'])
def get_users():
    try:
        user_list = []
        for k, v in database["keys"].items():
            r_nick = v.get("roblox_nick", "N/A")
            d_name = v.get("registered_name", "Unknown")
            user_list.append({"roblox": r_nick, "discord": d_name, "status": "Online"})
        return jsonify(user_list)
    except: return jsonify([])

# ==========================================
#        C++ LOADER (GÜNCELLENDİ)
# ==========================================

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        ip = get_ip()

        # 1. GÜVENLİK KONTROLÜ (CEZALI MI?)
        sec_check = check_security(hwid)
        if not sec_check["allowed"]: return jsonify({"success": False, "msg": sec_check["msg"]})

        if hwid in database["blacklisted_hwids"]: return jsonify({"success": False, "msg": "BANNED DEVICE"})

        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member_named(discord_name) if guild else None
        
        if not member:
            punish_user(hwid) # HATA -> CEZA EKLE
            return jsonify({"success": False, "msg": "User Not Found"})

        # --- ZATEN KAYITLI MI? ---
        existing_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == member.id and time.time() < v.get("expires", 0):
                existing_key = k
                break
        
        if existing_key:
            # YENİ EKLEME: Zaten kayıtlıysa da CEZA PUANI EKLE!
            # İlk basışta uyarır, ikinci basışta 60sn ceza verir.
            punish_user(hwid) 
            return jsonify({"success": False, "msg": "Already Registered!"})

        # --- YENİ KAYIT ---
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid, "roblox_nick": "N/A", 
            "expires": time.time() + (7 * 86400), "assigned_id": member.id,
            "registered_name": discord_name, "pc_user": pc_user
        }
        save_db()
        
        clear_punish(hwid) # Başarılıysa sicili temizle
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

        # 1. GÜVENLİK KONTROLÜ
        sec_check = check_security(hwid)
        if not sec_check["allowed"]: return jsonify({"valid": False, "msg": sec_check["msg"]})

        # Yanlış Key
        if key not in database["keys"]:
            punish_user(hwid) # HATA -> CEZA EKLE
            log_to_service("Unknown", key, hwid, ip, "Invalid Key Attempt")
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        # Yanlış Bilgisayar (HWID)
        if info.get("native_hwid") and info.get("native_hwid") != hwid:
            punish_user(hwid) # HATA -> CEZA EKLE
            return jsonify({"valid": False, "msg": "Wrong HWID"})
        
        if not info.get("native_hwid"): 
            info["native_hwid"] = hwid; save_db()

        if roblox: info["roblox_nick"] = roblox; save_db()

        clear_punish(hwid) # Başarılı giriş -> Sicili temizle
        log_to_service(info.get("registered_name"), key, hwid, ip, "Login Success")
        return jsonify({"valid": True, "msg": "Success"})

    except: return jsonify({"valid": False, "msg": "Error"})

# --- DISCORD ---
@app.route('/callback')
def discord_callback(): return "Login Endpoint Active"

@bot.tree.command(name="listkeys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("No permission", ephemeral=True); return
    lines = [f"{'KEY':<20} | {'DISCORD':<15} | {'ROBLOX':<15}", "-" * 60]
    for k, v in database["keys"].items():
        lines.append(f"{k} | {v.get('registered_name','?'):<15} | {v.get('roblox_nick','N/A'):<15}")
    f = discord.File(io.StringIO("\n".join(lines)), filename="db.txt")
    await interaction.response.send_message("DB:", file=f, ephemeral=True)

@bot.tree.command(name="reset_hwid")
async def reset_hwid(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("No permission", ephemeral=True); return
    if key in database["keys"]:
        database["keys"][key]["native_hwid"] = None; save_db()
        await interaction.response.send_message(f"Reset: {key}", ephemeral=True)
    else: await interaction.response.send_message("Not found", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
