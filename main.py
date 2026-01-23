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
logging.basicConfig(level=logging.ERROR)
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
    default_limits=["10000 per day", "2000 per hour"], 
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
    try:
        with open(DB_FILE, "w") as f:
            json.dump(database, f)
    except: pass

load_db()

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"success": False, "valid": False, "msg": "Slow Down! (Spam)"}), 429

# --- DISCORD OAUTH (OTOMATİK KAPATMA EKLENDİ) ---
@app.route('/callback')
def discord_callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not state: return "Error: Missing Parameters"

    data = {
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
    }
    try:
        r = requests.post('https://discord.com/api/oauth2/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        r.raise_for_status()
        access_token = r.json().get('access_token')
        
        user_req = requests.get('https://discord.com/api/users/@me', headers={'Authorization': f'Bearer {access_token}'})
        user_req.raise_for_status()
        user_data = user_req.json()
        
        discord_id = int(user_data['id'])
        username = user_data['username']

        found_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == discord_id and time.time() < v.get("expires", 0):
                found_key = k
                break
        
        # --- HTML ŞABLONU (OTOMATİK KAPATMA İÇİN) ---
        html_template = """
        <html>
        <head>
            <title>Anarchy Auth</title>
            <style>
                body { background-color: #09090b; color: white; font-family: 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; flex-direction: column; }
                h1 { font-size: 24px; margin-bottom: 10px; }
                p { color: #a1a1aa; }
            </style>
            <script>
                window.onload = function() {
                    // Tarayıcıya pencereyi kapatmasını söyle
                    setTimeout(function() { window.close(); }, 1000);
                }
            </script>
        </head>
        <body>
            <h1>LOGIN SUCCESSFUL</h1>
            <p>You can close this tab and return to the application.</p>
        </body>
        </html>
        """

        if found_key:
            pending_logins[state] = {"status": "Success", "key": found_key, "user": username}
            return html_template # Başarılıysa otomatik kapatma sayfasını döndür
        else:
            pending_logins[state] = {"status": "Failed", "msg": "No License"}
            return """
            <html><body style='background:#09090b;color:#ef4444;font-family:sans-serif;text-align:center;padding-top:100px;'>
            <h1>NO ACTIVE LICENSE</h1><p>Please use the Register button in the app.</p>
            </body></html>
            """
            
    except Exception as e: return str(e)

@app.route('/auth/poll', methods=['POST'])
def poll_auth():
    state = request.json.get("state")
    if state in pending_logins: return jsonify(pending_logins.pop(state))
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
                {"name": "Status", "value": f"**{status}**", "inline": True}
            ],
            "footer": {"text": "Anarchy Auth"}
        }
        requests.post(LOG_WEBHOOK, json={"username": "Logger", "embeds": [embed]})
    except: pass

def get_real_ip():
    if request.headers.getlist("X-Forwarded-For"): return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

@bot.event
async def on_ready():
    print(f"Bot Active: {bot.user}")
    try: await bot.tree.sync()
    except: pass

@app.route('/register', methods=['POST'])
@limiter.limit("10 per minute")
def register():
    try:
        if not bot.is_ready(): return jsonify({"success": False, "msg": "System Loading..."})
        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        
        if hwid in database["blacklisted_hwids"]:
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Server Error"})
        member = guild.get_member_named(discord_name)
        if not member: return jsonify({"success": False, "msg": "User Not Found"})

        # --- ZATEN KAYITLI MI KONTROLÜ ---
        existing_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == member.id and time.time() < v.get("expires", 0):
                existing_key = k
                break
        
        if existing_key:
            # DM GÖNDERME KODU KALDIRILDI. Sadece hata mesajı dönüyor.
            return jsonify({"success": False, "msg": "Already Registered!"})

        # --- YENİ KAYIT ---
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid, 
            "roblox_nick": "N/A", 
            "expires": time.time() + (7 * 86400),
            "assigned_id": member.id,
            "registered_name": discord_name,
            "pc_user": pc_user
        }
        save_db()
        
        # Sadece yeni kayıtta DM at
        asyncio.run_coroutine_threadsafe(send_dm_key(member, new_key), bot.loop)
        threading.Thread(target=send_discord_log, args=("New Register", discord_name, pc_user, new_key, hwid, get_real_ip(), "N/A", "N/A", "Success")).start()
        
        return jsonify({"success": True, "msg": "Sent to DM"})
    except: return jsonify({"success": False, "msg": "Server Error"})

async def send_dm_key(member, key):
    try: await member.send(f"Anarchy License: `{key}`\nLocked to your HWID.")
    except: pass

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        roblox_user = data.get("roblox_user", None) 

        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        valid = False
        if info.get("native_hwid") == sent_hwid: valid = True
        elif info.get("native_hwid") is None: 
            info["native_hwid"] = sent_hwid; save_db(); valid = True
        else: return jsonify({"valid": False, "msg": "Wrong HWID"})
        
        if valid:
            if roblox_user: info["roblox_nick"] = roblox_user; save_db()
            return jsonify({"valid": True, "msg": "Success"})
    except: return jsonify({"valid": False, "msg": "Error"})

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
