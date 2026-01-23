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
LOGGER_SERVICE_URL = "https://senin-logger-projen.onrender.com/send_log" 

# --- YETKİLİ ID'LER (SADECE BU KİŞİLER KOMUT KULLANABİLİR) ---
ADMIN_IDS = [1358830140343193821, 1039946239938142218]

# --- ESKİ KEYLER ---
INITIAL_KEYS = {
    # Buraya uzun key listeni yapıştırabilirsin, database'den de okur.
}

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

def send_to_logger(payload):
    try: requests.post(LOGGER_SERVICE_URL, json=payload, timeout=2)
    except: pass

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Sync Error: {e}")

# --- WEBHOOK / API ENDPOINTS ---

@app.route('/', methods=['GET'])
def home(): return "System Online"

@app.route('/register', methods=['POST'])
@limiter.limit("10 per minute")
def register():
    try:
        if not bot.is_ready():
            return jsonify({"success": False, "msg": "Bot Loading..."})

        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        
        if not discord_name or len(discord_name) < 2:
             return jsonify({"success": False, "msg": "Invalid Name"})

        if hwid in database["blacklisted_hwids"]:
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        # HWID Kontrol (1 PC = 1 Key)
        for k, v in database["keys"].items():
            if v.get("native_hwid") == hwid:
                if time.time() < v.get("expires", 0):
                    return jsonify({"success": False, "msg": "PC Already Registered!"})

        # İsim Kontrolü (Başkasının ismini alamasın)
        for k, v in database["keys"].items():
            if v.get("registered_name") and v.get("registered_name").lower() == discord_name.lower():
                 if time.time() < v.get("expires", 0):
                    return jsonify({"success": False, "msg": "Discord User Already Registered!"})

        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Bot Error: Guild Not Found"})
        
        member = guild.get_member_named(discord_name)
        if not member:
            return jsonify({"success": False, "msg": "User not found in Discord!"})

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
        
        # Loglama
        log_payload = {"status": "New Register", "username": discord_name, "hwid": hwid, "key": new_key}
        threading.Thread(target=send_to_logger, args=(log_payload,)).start()

        return jsonify({"success": True, "msg": "Key sent to DM!"})

    except Exception as e:
        print(f"Register Error: {e}")
        return jsonify({"success": False, "msg": "Server Error"})

async def send_dm_key(member, key):
    try:
        embed = discord.Embed(title="🔐 Anarchy License", description="Here is your key.", color=0x00FF00)
        embed.add_field(name="Key", value=f"```{key}```")
        await member.send(embed=embed)
    except: pass

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False)
        
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        valid = False
        if is_loader:
            if info.get("native_hwid") == sent_hwid: valid = True
            elif info.get("native_hwid") is None: info["native_hwid"] = sent_hwid; save_db(); valid = True
            else: return jsonify({"valid": False, "msg": "Wrong PC"})
        else:
            if info.get("roblox_hwid") == sent_hwid: valid = True
            elif info.get("roblox_hwid") is None: info["roblox_hwid"] = sent_hwid; save_db(); valid = True
            else: return jsonify({"valid": False, "msg": "Wrong Roblox Acc"})
        
        if valid:
            rem = int(info["expires"] - time.time())
            return jsonify({"valid": True, "msg": "Success", "left": f"{rem//86400}d"})
            
    except: return jsonify({"valid": False, "msg": "Error"})

# --- DISCORD KOMUTLARI (ADMIN KORUMALI) ---

@bot.tree.command(name="listkeys", description="List all active licenses (Admin Only)")
async def listkeys(interaction: discord.Interaction):
    # 1. ID KONTROLÜ (Sadece ADMIN_IDS listesindekiler kullanabilir)
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("⛔ You are not authorized to use this command.", ephemeral=True)
        return

    if not database["keys"]: 
        await interaction.response.send_message("No active licenses.", ephemeral=True)
        return
        
    lines = []
    for k, v in list(database["keys"].items()):
        u = v.get("registered_name", "Unknown")
        hwid_stat = "Linked" if v.get("native_hwid") else "Free"
        lines.append(f"Key: {k} | User: {u} | PC: {hwid_stat}")
    
    file_data = "\n".join(lines)
    f = discord.File(io.StringIO(file_data), filename="keys.txt")
    await interaction.response.send_message("Active Database:", file=f, ephemeral=True)

@bot.tree.command(name="reset_user", description="Reset HWID for a specific key (Admin Only)")
async def reset_user(interaction: discord.Interaction, key: str):
    # Bu da sadece size özel
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("⛔ Unauthorized.", ephemeral=True); return

    if key in database["keys"]:
        database["keys"][key]["native_hwid"] = None
        database["keys"][key]["roblox_hwid"] = None
        save_db()
        await interaction.response.send_message(f"✅ HWID reset for key: `{key}`", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Key not found.", ephemeral=True)

@app.route('/network', methods=['POST'])
def network(): return jsonify({"users": []})

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: 
        bot.run(TOKEN)
    else:
        print("ERROR: DISCORD_TOKEN not found!")
