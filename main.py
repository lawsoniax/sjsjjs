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
import datetime

# --- YAPILANDIRMA ---
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1460981897730592798 
DB_FILE = "anarchy_db.json"

# Webhook Adresi
LOG_WEBHOOK = "https://discord.com/api/webhooks/1464013246414717192/mXK-_-Yft9JqDS-pqUWSbOa1Uv5wzHtmN0jOC5__aU4_cewwXikQZ1ofDVmc141cpkaj"

# Yetkili Yönetici ID Listesi
ADMIN_IDS = [1358830140343193821, 1039946239938142218]

# Eski Lisans Anahtarlari
INITIAL_KEYS = {} 

# --- SISTEM BASLATMA ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True 

bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["5000 per day", "1000 per hour"], 
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
                    if k not in data: 
                        data[k] = [] if "list" in k else {}
                database = data
        except: 
            pass
    else:
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump(database, f)
    except:
        pass

load_db()

# --- LOGLAMA SISTEMI ---
def send_discord_log(title, discord_user, pc_user, key, hwid, ip, mac, ram, status, color=3066993):
    try:
        embed = {
            "title": title,
            "color": color,
            "fields": [
                {"name": "Windows User", "value": f"`{pc_user}`", "inline": True},
                {"name": "Discord User", "value": f"`{discord_user}`", "inline": True},
                {"name": "License Key", "value": f"`{key}`", "inline": False},
                {"name": "HWID", "value": f"`{hwid}`", "inline": False},
                {"name": "MAC Address", "value": f"`{mac}`", "inline": True},
                {"name": "RAM", "value": f"`{ram}`", "inline": True},
                {"name": "IP Address", "value": f"`{ip}`", "inline": False},
                {"name": "Status", "value": f"**{status}**", "inline": True},
                {"name": "Time", "value": f"<t:{int(time.time())}:R>", "inline": True}
            ],
            "footer": {"text": "Anarchy Security System"}
        }
        
        requests.post(LOG_WEBHOOK, json={"username": "Anarchy Logger", "embeds": [embed]})
    except Exception as e:
        print(f"Log Error: {e}")

# --- IP COZUMLEME ---
def get_real_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    try: 
        await bot.tree.sync()
    except: 
        pass

# --- KAYIT ISLEMI (REGISTER) ---
@app.route('/register', methods=['POST'])
@limiter.limit("10 per minute")
def register():
    try:
        if not bot.is_ready(): return jsonify({"success": False, "msg": "System Loading..."})

        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        
        # Donanim Bilgileri
        pc_user = data.get("pc_user", "Unknown")
        mac = data.get("mac", "N/A")
        ram = data.get("ram", "N/A")
        
        ip = get_real_ip()

        if not discord_name: return jsonify({"success": False, "msg": "Enter Username"})

        if hwid in database["blacklisted_hwids"]:
            send_discord_log("Register Blocked", discord_name, pc_user, "N/A", hwid, ip, mac, ram, "BANNED DEVICE", 15158332)
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        for k, v in database["keys"].items():
            if v.get("native_hwid") == hwid and time.time() < v.get("expires", 0):
                return jsonify({"success": False, "msg": "PC Already Registered"})

        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Server Error"})
        
        member = guild.get_member_named(discord_name)
        if not member:
            return jsonify({"success": False, "msg": "User Not Found in Discord"})

        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid,
            "roblox_hwid": None,
            "expires": time.time() + (7 * 86400),
            "created_at": time.time(),
            "duration_txt": "7d Trial",
            "assigned_id": member.id,
            "registered_name": discord_name,
            "pc_user": pc_user
        }
        save_db()

        asyncio.run_coroutine_threadsafe(send_dm_key(member, new_key), bot.loop)
        
        threading.Thread(target=send_discord_log, args=("New Registration", discord_name, pc_user, new_key, hwid, ip, mac, ram, "Key Sent to DM")).start()

        return jsonify({"success": True, "msg": "Key sent to DM"})

    except Exception as e:
        return jsonify({"success": False, "msg": "System Error"})

async def send_dm_key(member, key):
    try:
        embed = discord.Embed(title="Anarchy License", description=f"Key: ```{key}```", color=0x00FF00)
        await member.send(embed=embed)
    except: pass

# --- DOGRULAMA ISLEMI (VERIFY) ---
@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False)
        
        pc_user = data.get("pc_user", "Unknown PC") 
        mac = data.get("mac", "N/A")
        ram = data.get("ram", "N/A")
        
        ip = get_real_ip()

        if key not in database["keys"]: 
            threading.Thread(target=send_discord_log, args=("Login Failed", "Unknown", pc_user, key, sent_hwid, ip, mac, ram, "Invalid Key", 15158332)).start()
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        discord_user = info.get("registered_name", "Unknown")

        if time.time() > info["expires"]: 
            threading.Thread(target=send_discord_log, args=("Login Failed", discord_user, pc_user, key, sent_hwid, ip, mac, ram, "Expired License", 15158332)).start()
            return jsonify({"valid": False, "msg": "Expired"})

        valid = False
        status_msg = "Success"

        if is_loader:
            if info.get("native_hwid") == sent_hwid: 
                valid = True
                status_msg = "Login Success (PC)"
            elif info.get("native_hwid") is None: 
                info["native_hwid"] = sent_hwid
                save_db()
                valid = True
                status_msg = "Locked to PC"
            else:
                threading.Thread(target=send_discord_log, args=("Security Alert", discord_user, pc_user, key, sent_hwid, ip, mac, ram, "HWID Mismatch", 10038562)).start()
                return jsonify({"valid": False, "msg": "Wrong PC"})
        else:
            if info.get("roblox_hwid") == sent_hwid: 
                valid = True
                status_msg = "Login Success (Roblox)"
            elif info.get("roblox_hwid") is None: 
                info["roblox_hwid"] = sent_hwid
                save_db()
                valid = True
                status_msg = "Locked to Roblox"
            else:
                return jsonify({"valid": False, "msg": "Wrong Roblox Account"})
        
        if valid:
            rem = int(info["expires"] - time.time())
            threading.Thread(target=send_discord_log, args=("Login Approved", discord_user, pc_user, key, sent_hwid, ip, mac, ram, status_msg)).start()
            return jsonify({"valid": True, "msg": "Success", "left": f"{rem//86400}d"})
            
    except Exception as e: 
        return jsonify({"valid": False, "msg": "Error"})

# --- DISCORD KOMUTLARI ---
@bot.tree.command(name="listkeys", description="Admin: List all keys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("Unauthorized.", ephemeral=True); return

    if not database["keys"]: 
        await interaction.response.send_message("Database empty.", ephemeral=True); return
        
    lines = []
    for k, v in list(database["keys"].items()):
        u = v.get("registered_name", "Unknown")
        pc = v.get("pc_user", "N/A")
        lines.append(f"{k} | Discord: {u} | PC: {pc}")
    
    file_data = "\n".join(lines)
    f = discord.File(io.StringIO(file_data), filename="keys.txt")
    await interaction.response.send_message("Database Export:", file=f, ephemeral=True)

@bot.tree.command(name="reset_user", description="Admin: Reset HWID")
async def reset_user(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("Unauthorized.", ephemeral=True); return

    if key in database["keys"]:
        database["keys"][key]["native_hwid"] = None
        database["keys"][key]["roblox_hwid"] = None
        save_db()
        await interaction.response.send_message(f"Reset Complete: `{key}`", ephemeral=True)
    else:
        await interaction.response.send_message("Key not found.", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
