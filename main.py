import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify, redirect
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
LOG_WEBHOOK = "https://discord.com/api/webhooks/1464013246414717192/mXK-_-Yft9JqDS-pqUWSbOa1Uv5wzHtmN0jOC5__aU4_cewwXikQZ1ofDVmc141cpkaj"

# --- DISCORD OAUTH AYARLARI ---
CLIENT_ID = "1464002253244600511" 
CLIENT_SECRET = "6djxraALuFvcg6ZLT_aDpHs94Y4PcUzj"
REDIRECT_URI = "https://sjsjjs.onrender.com/callback"

ADMIN_IDS = [1358830140343193821, 1039946239938142218]
INITIAL_KEYS = {} 

pending_logins = {}

# --- SISTEM ---
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

# --- DISCORD OAUTH CALLBACK ---
@app.route('/callback')
def discord_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code or not state: return "Error: Missing Parameters"

    data = {
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        r = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
        r.raise_for_status()
        access_token = r.json().get('access_token')
        
        user_req = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'})
        user_req.raise_for_status()
        user_data = user_req.json()
        
        discord_id = int(user_data['id'])
        username = user_data['username']

        # Lisans Kontrolu
        found_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == discord_id:
                # Süresi dolmamışsa
                if time.time() < v.get("expires", 0):
                    found_key = k
                    break
        
        if found_key:
            pending_logins[state] = {"status": "Success", "key": found_key, "user": username}
            return f"<body style='background:#09090b;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;'><h1>Login Successful</h1><p>Welcome, {username}. You can close this window.</p></body>"
        else:
            pending_logins[state] = {"status": "Failed", "msg": "No Active License"}
            return f"<body style='background:#09090b;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;'><h1>Access Denied</h1><p>No active license found for {username}. Please register via App.</p></body>"

    except Exception as e:
        return f"Auth Error: {str(e)}"

@app.route('/auth/poll', methods=['POST'])
def poll_auth():
    data = request.json
    state = data.get("state")
    if state in pending_logins:
        result = pending_logins.pop(state)
        return jsonify(result)
    return jsonify({"status": "Waiting"})

# --- LOG ---
def send_discord_log(title, discord_user, pc_user, key, hwid, ip, mac, ram, status, color=3066993):
    try:
        embed = {
            "title": title, "color": color,
            "fields": [
                {"name": "Windows User", "value": f"`{pc_user}`", "inline": True},
                {"name": "Discord User", "value": f"`{discord_user}`", "inline": True},
                {"name": "Key", "value": f"`{key}`", "inline": False},
                {"name": "HWID", "value": f"`{hwid}`", "inline": False},
                {"name": "MAC", "value": f"`{mac}`", "inline": True},
                {"name": "RAM", "value": f"`{ram}`", "inline": True},
                {"name": "IP", "value": f"`{ip}`", "inline": False},
                {"name": "Status", "value": f"**{status}**", "inline": True}
            ],
            "footer": {"text": "Anarchy Security System"}
        }
        requests.post(LOG_WEBHOOK, json={"username": "Anarchy Logger", "embeds": [embed]})
    except: pass

def get_real_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

@app.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    try:
        if not bot.is_ready(): return jsonify({"success": False, "msg": "System Loading..."})
        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        mac = data.get("mac", "N/A")
        ram = data.get("ram", "N/A")
        ip = get_real_ip()

        if not discord_name: return jsonify({"success": False, "msg": "Invalid Name"})
        
        # 1. HWID Ban Kontrolü
        if hwid in database["blacklisted_hwids"]:
            send_discord_log("Blocked", discord_name, pc_user, "N/A", hwid, ip, mac, ram, "BANNED", 15158332)
            return jsonify({"success": False, "msg": "BANNED HWID"})

        # 2. Discord Üye Kontrolü
        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Server Error"})
        member = guild.get_member_named(discord_name)
        if not member: return jsonify({"success": False, "msg": "User Not Found in Server"})

        # 3. ZATEN KEY VAR MI KONTROLÜ (YENİ EKLENDİ)
        existing_key = None
        for k, v in database["keys"].items():
            # ID eşleşiyorsa ve süresi bitmemişse
            if v.get("assigned_id") == member.id:
                if time.time() < v.get("expires", 0):
                    existing_key = k
                    break
        
        if existing_key:
            # Key zaten var, yeniden oluşturma, eskisini at
            asyncio.run_coroutine_threadsafe(send_dm_key(member, existing_key), bot.loop)
            return jsonify({"success": True, "msg": "You already have a key. Check DM."})

        # 4. Yeni Key Oluşturma
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid, # Kayıt olurkenki HWID'ye kilitlenir
            "roblox_nick": "N/A", # Roblox ismi başta yok
            "expires": time.time() + (7 * 86400),
            "created_at": time.time(),
            "duration_txt": "7d Trial",
            "assigned_id": member.id,
            "registered_name": discord_name,
            "pc_user": pc_user
        }
        save_db()
        
        asyncio.run_coroutine_threadsafe(send_dm_key(member, new_key), bot.loop)
        threading.Thread(target=send_discord_log, args=("New Register", discord_name, pc_user, new_key, hwid, ip, mac, ram, "Success")).start()
        
        return jsonify({"success": True, "msg": "Sent to DM"})
    except Exception as e:
        print(e)
        return jsonify({"success": False, "msg": "Error"})

async def send_dm_key(member, key):
    try: await member.send(f"Anarchy License Key: `{key}`\nThis key is locked to your HWID.")
    except: pass

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        mac = data.get("mac", "N/A")
        ram = data.get("ram", "N/A")
        
        # C++ Loader buraya Roblox ismini gönderemez (genelde),
        # ama eğer bir gün gönderirse diye buraya ekliyoruz.
        # Asıl Roblox ismi güncellemesi Lua script üzerinden yapılmalı.
        roblox_user = data.get("roblox_user", None) 
        
        ip = get_real_ip()

        if key not in database["keys"]: 
            threading.Thread(target=send_discord_log, args=("Failed Login", "Unknown", pc_user, key, sent_hwid, ip, mac, ram, "Invalid Key", 15158332)).start()
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        valid = False
        # HWID Kontrolü
        if info.get("native_hwid") == sent_hwid: 
            valid = True
        elif info.get("native_hwid") is None: 
            # İlk girişse kilitle
            info["native_hwid"] = sent_hwid
            save_db()
            valid = True
        else: 
            return jsonify({"valid": False, "msg": "Wrong PC (HWID Mismatch)"})
        
        if valid:
            # Eğer istekte Roblox ismi varsa veritabanını güncelle
            if roblox_user:
                info["roblox_nick"] = roblox_user
                save_db()

            threading.Thread(target=send_discord_log, args=("Login Success", info.get("registered_name"), pc_user, key, sent_hwid, ip, mac, ram, "Authorized")).start()
            return jsonify({"valid": True, "msg": "Success"})
    except: return jsonify({"valid": False, "msg": "Error"})

# --- YENİ: Lua Script İçin Roblox İsim Güncelleme ---
@app.route('/update_roblox', methods=['POST'])
def update_roblox():
    try:
        data = request.json
        key = data.get("key")
        roblox_user = data.get("roblox_user")
        
        if key in database["keys"] and roblox_user:
            database["keys"][key]["roblox_nick"] = roblox_user
            save_db()
            return jsonify({"success": True})
        return jsonify({"success": False})
    except: return jsonify({"success": False})

@bot.tree.command(name="listkeys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: 
        await interaction.response.send_message("No permission", ephemeral=True)
        return
    
    # Roblox isimlerini de gösteren format
    lines = []
    lines.append(f"{'KEY':<25} | {'DISCORD':<20} | {'ROBLOX':<20}")
    lines.append("-" * 75)
    
    for k, v in database["keys"].items():
        discord_name = v.get('registered_name', 'Unknown')
        roblox_name = v.get('roblox_nick', 'N/A')
        lines.append(f"{k} | {discord_name:<20} | {roblox_name:<20}")
    
    file_content = "\n".join(lines)
    f = discord.File(io.StringIO(file_content), filename="database.txt")
    await interaction.response.send_message("Database Report:", file=f, ephemeral=True)

@bot.tree.command(name="reset_hwid")
async def reset_hwid(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS: 
        await interaction.response.send_message("No permission", ephemeral=True)
        return
        
    if key in database["keys"]:
        database["keys"][key]["native_hwid"] = None
        save_db()
        await interaction.response.send_message(f"HWID Reset for key: {key}", ephemeral=True)
    else: 
        await interaction.response.send_message("Key not found", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
