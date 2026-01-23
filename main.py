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
import sys
import io

# --- AYARLAR ---
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1460981897730592798 
DB_FILE = "anarchy_db.json"

# --- LOGGER BAĞLANTISI ---
# Buraya diğer Render hesabındaki Logger uygulamasının adresini yaz.
# Sonunda /send_log olması ŞART.
LOGGER_SERVICE_URL = "https://asdasdj.onrender.com" 

# --- YETKİLİ ID'LER ---
ADMIN_IDS = [1358830140343193821, 1039946239938142218]

# --- ESKİ KEYLER ---
INITIAL_KEYS = {} 

# --- SİSTEM KURULUMU ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True 

bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["3000 per day", "1000 per hour"], 
    storage_uri="memory://"
)

database = {"keys": {}, "users": {}, "blacklisted_hwids": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                for k in ["keys", "users", "blacklisted_hwids"]:
                    if k not in data: data[k] = [] if "list" in k else {}
                database = data
        except: pass
    else:
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try: with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

# --- UZAK LOGGER FONKSİYONU ---
# Bu fonksiyon veriyi senin logger.py dosyana gönderir
def send_log_remote(status, user, key, hwid, ip):
    try:
        payload = {
            "status": status,
            "username": user,
            "key": key,
            "hwid": hwid,
            "ip": ip
        }
        # Arka planda isteği at, cevabı bekleme (Hız kaybetmemek için)
        requests.post(LOGGER_SERVICE_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Logger Error: {e}")

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

# --- REGISTER ---
@app.route('/register', methods=['POST'])
@limiter.limit("10 per minute")
def register():
    try:
        if not bot.is_ready(): return jsonify({"success": False, "msg": "Bot Loading..."})

        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        
        if request.headers.getlist("X-Forwarded-For"): ip = request.headers.getlist("X-Forwarded-For")[0]
        else: ip = request.remote_addr

        if not discord_name: return jsonify({"success": False, "msg": "Enter Username"})

        if hwid in database["blacklisted_hwids"]:
            # Yasaklı giriş logu gönder
            threading.Thread(target=send_log_remote, args=("BANNED DEVICE", discord_name, "N/A", hwid, ip)).start()
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        # HWID Kontrol
        for k, v in database["keys"].items():
            if v.get("native_hwid") == hwid and time.time() < v.get("expires", 0):
                return jsonify({"success": False, "msg": "PC Already Registered!"})

        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Server Error"})
        
        member = guild.get_member_named(discord_name)
        if not member:
            return jsonify({"success": False, "msg": "User Not Found in Discord!"})

        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid,
            "roblox_hwid": None,
            "expires": time.time() + (7 * 86400),
            "created_at": time.time(),
            "duration_txt": "7d Trial",
            "assigned_id": member.id,
            "registered_name": discord_name
        }
        save_db()

        asyncio.run_coroutine_threadsafe(send_dm_key(member, new_key), bot.loop)
        
        # --- BAŞARILI KAYIT LOGU (Uzak Sunucuya) ---
        threading.Thread(target=send_log_remote, args=("New Registration", discord_name, new_key, hwid, ip)).start()

        return jsonify({"success": True, "msg": "Key sent to DM!"})

    except Exception as e:
        return jsonify({"success": False, "msg": f"Err: {str(e)[:20]}"})

async def send_dm_key(member, key):
    try:
        embed = discord.Embed(title="🔐 Anarchy License", description=f"Key: ```{key}```", color=0x00FF00)
        await member.send(embed=embed)
    except: pass

# --- VERIFY (GİRİŞ) ---
@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False)
        
        pc_user = data.get("username", "Unknown PC User") 
        
        if request.headers.getlist("X-Forwarded-For"): ip = request.headers.getlist("X-Forwarded-For")[0]
        else: ip = request.remote_addr

        if key not in database["keys"]: 
            # Geçersiz Key Logu
            threading.Thread(target=send_log_remote, args=("Invalid Key Attempt", pc_user, key, sent_hwid, ip)).start()
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        registered_user = info.get("registered_name", "Unknown")
        log_user_display = f"{pc_user} ({registered_user})"

        if time.time() > info["expires"]: 
            threading.Thread(target=send_log_remote, args=("Expired License", log_user_display, key, sent_hwid, ip)).start()
            return jsonify({"valid": False, "msg": "Expired"})

        valid = False
        status_log = "Success"

        if is_loader:
            if info.get("native_hwid") == sent_hwid: 
                valid = True
                status_log = "Login Success (PC)"
            elif info.get("native_hwid") is None: 
                info["native_hwid"] = sent_hwid
                save_db()
                valid = True
                status_log = "Locked to PC"
            else:
                threading.Thread(target=send_log_remote, args=("HWID Mismatch (PC)", log_user_display, key, sent_hwid, ip)).start()
                return jsonify({"valid": False, "msg": "Wrong PC"})
        else:
            if info.get("roblox_hwid") == sent_hwid: 
                valid = True
                status_log = "Login Success (Roblox)"
            elif info.get("roblox_hwid") is None: 
                info["roblox_hwid"] = sent_hwid
                save_db()
                valid = True
                status_log = "Locked to Roblox"
            else:
                return jsonify({"valid": False, "msg": "Wrong Roblox Acc"})
        
        if valid:
            rem = int(info["expires"] - time.time())
            
            # --- BAŞARILI GİRİŞ LOGU (Uzak Sunucuya) ---
            threading.Thread(target=send_log_remote, args=(status_log, log_user_display, key, sent_hwid, ip)).start()
            
            return jsonify({"valid": True, "msg": "Success", "left": f"{rem//86400}d"})
            
    except Exception as e: 
        return jsonify({"valid": False, "msg": "Error"})

# --- DISCORD KOMUTLARI ---
@bot.tree.command(name="listkeys", description="List all keys (Admin Only)")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True); return

    if not database["keys"]: 
        await interaction.response.send_message("No keys.", ephemeral=True); return
        
    lines = []
    for k, v in list(database["keys"].items()):
        u = v.get("registered_name", "Unknown")
        pc = "Linked" if v.get("native_hwid") else "Free"
        lines.append(f"{k} | {u} | {pc}")
    
    file_data = "\n".join(lines)
    f = discord.File(io.StringIO(file_data), filename="keys.txt")
    await interaction.response.send_message("Database:", file=f, ephemeral=True)

@bot.tree.command(name="reset_user", description="Reset HWID (Admin Only)")
async def reset_user(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True); return

    if key in database["keys"]:
        database["keys"][key]["native_hwid"] = None
        database["keys"][key]["roblox_hwid"] = None
        save_db()
        await interaction.response.send_message(f"✅ Reset: `{key}`", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Key not found.", ephemeral=True)

@app.route('/network', methods=['POST'])
def network(): return jsonify({"users": []})

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
