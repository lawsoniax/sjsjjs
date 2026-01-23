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
import requests # Logger servisine istek atmak için

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1462815057669918821

# Admin ID Listesi
ADMIN_IDS = [1358830140343193821, 1039946239938142218]

GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- LOGGER SERVICE CONFIG ---
# Buraya Logger sunucunun linkini yapıştır (Sonunda /send_log olsun)
LOGGER_SERVICE_URL = "https://senin-logger-projen.onrender.com/send_log" 

# --- INITIAL KEY DATA (Senin Verdiğin Liste) ---
INITIAL_KEYS = {
    "ANARCHY-CZ5GVGZE4W6J1PTC": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-0YIXA75QVT6PDRAU": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-6MJQA5HWECR7ZZML": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-FMKOB454POWMWIK5": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-5LIVRP7HCDZGDJFN": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-ITSIZSJYWGIYPWAI": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-506ETM8OTZV1XSIV": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-FKK2FFPCMHGGRLQP": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-P6EKTRBF6PWYVOEW": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-8332RNF1LD7GYUXQ": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-KIW3E5HDTTFCFL1Q": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-YCYAH0VLPW623JNB": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-ZIGH3X50T4QHKULW": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-KF8IJ7787S1ARFZA": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-7FEITOI3YIW1L6IO": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-3T57HLOMJ0SX9KEZ": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-S6O5VV7U1ODP4WSM": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-YLRQQPQMUBZJQDGX": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-ZHPEAT32XHC1TKEN": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-HTFF8WT3TAY0ANGZ": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-U9IT7Z4A6Z2LH153": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-IABR0CV8YM8BG6RM": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-YSUJU1KI58ZVFAH2": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-VAF3IKQ1D3NEOHX7": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-3O4A1O2VWWCTB8IV": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-POM4CKYVN6NKR7KE": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-WWD9TJ8C0IMF4ARP": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-CQ1I9RGMUEP0P7K8": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-L2M4KSSY5OSKSUY1": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-K80L8PGVCG8C6DNQ": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-JVSOK8DGSWICE3XW": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-CDW7ZRER4NSNIXJX": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-QLUI2923JFF13TEL": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-V7B20Y3XJ4BBMAYD": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-GVBHINMP8XBLVZ4A": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-WOQW3GJYGJDNSI9X": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-LSQBIOT2SX55Y88G": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-34VACLUGXM7DNE7G": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-D08Q9HV3FCEQQTWH": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-R7NTFPNJVIPYFFA4": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-DBOP7ANCHR914JZ7": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-8ORQ3SRDUZ45YAJV": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-X6YY5JPZ8UCKO9Y5": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-YFVGTVSURZ9D8L2G": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "30d"},
    "ANARCHY-6ZFO4C8OR47IGXFK": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"},
    "ANARCHY-AAUHS4FK6YFWGQ8I": {"hwid": None, "expires": 1770000000, "assigned_id": 0, "duration_txt": "7d"}
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
user_sessions = {}
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
                
                # Mevcut keyler yoksa ekle (Güncelleme)
                for k, v in INITIAL_KEYS.items():
                    if k not in database["keys"]:
                        database["keys"][k] = v
        except: pass
    else:
        # Dosya yoksa ilk kurulum
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump(database, f)
    except:
        pass

load_db()

# --- LOGGING HELPER ---
def send_to_logger(payload):
    """Log verisini arka planda Logger API'ye gönderir"""
    try:
        requests.post(LOGGER_SERVICE_URL, json=payload, timeout=2)
    except:
        pass

def parse_duration(s):
    s = s.lower()
    try: 
        if "d" in s: return int(s.replace("d",""))*24
        elif "h" in s: return int(s.replace("h",""))
        else: return int(s)
    except: return None

# --- DM FUNCTION ---
async def send_dm_code(user_id, code):
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="Login Verification", color=0x2C3E50)
            embed.description = f"A new device is attempting to access the script.\n\n**Authorization Code:** `{code}`\n\nPlease enter this code in the window."
            embed.set_footer(text="Security Alert: Do not share this code.")
            await user.send(embed=embed)
            return True
    except: return False

# --- DISCORD KICK FUNCTION ---
async def kick_discord_user(user_id, reason):
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                try: await member.send(f"**Notice of Termination**\nYou have been banned.\nReason: {reason}")
                except: pass
                await member.kick(reason=reason)
    except: pass

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"System Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

@bot.event
async def on_member_remove(member):
    if member.id in ADMIN_IDS: return
    deleted = False
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            # Native veya Roblox HWID varsa blacklist'e al
            h1 = info.get("native_hwid")
            h2 = info.get("roblox_hwid")
            if h1 and h1 not in database["blacklisted_hwids"]: database["blacklisted_hwids"].append(h1)
            if h2 and h2 not in database["blacklisted_hwids"]: database["blacklisted_hwids"].append(h2)
            del database["keys"][key]
            deleted = True
            break        
    if deleted: save_db()

# --- FLASK ENDPOINTS ---
@app.route('/', methods=['GET'])
def home(): return "System Operational"

@app.route('/verify', methods=['POST'])
@limiter.limit("20 per minute")
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False)
        
        username = data.get("username")
        display_name = data.get("display_name")
        
        # IP Al (Render)
        if request.headers.getlist("X-Forwarded-For"):
            ip = request.headers.getlist("X-Forwarded-For")[0]
        else:
            ip = request.remote_addr

        # Log paketi
        log_payload = {
            "key": key, "hwid": sent_hwid, "username": username,
            "ip": ip, "status": "Processing..."
        }

        # 1. Blacklist Kontrolü
        if sent_hwid in database["blacklisted_hwids"]:
            log_payload["status"] = "BANNED HWID"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Access Denied: HWID Banned"})
        
        # 2. Key Kontrolü
        if key not in database["keys"]:
            log_payload["status"] = "Invalid Key"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]
        
        # İsim Güncelleme
        if username and display_name:
            if is_loader: info["pc_user"] = f"{display_name} ({username})"
            else: info["last_roblox_name"] = f"{display_name} (@{username})"
            save_db()

        # 3. Süre Kontrolü
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            log_payload["status"] = "Expired"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "License Expired"})

        # Discord Üyelik Kontrolü
        g = bot.get_guild(GUILD_ID)
        if g and info.get("assigned_id") and not g.get_member(info["assigned_id"]):
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Discord Membership Required"})

        # --- ÇİFT HWID MANTIĞI ---
        valid_access = False
        requires_otp = False

        if is_loader:
            # C++ Loader Kontrolü
            saved_native = info.get("native_hwid")
            if saved_native is None:
                info["native_hwid"] = sent_hwid; save_db()
                valid_access = True
                log_payload["status"] = "Locked to PC"
            elif saved_native == sent_hwid:
                valid_access = True
                log_payload["status"] = "Success (PC)"
            else:
                log_payload["status"] = "HWID Mismatch (PC)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "HWID Mismatch (Wrong PC)"})
        else:
            # Roblox Kontrolü
            saved_roblox = info.get("roblox_hwid")
            if saved_roblox is None:
                info["roblox_hwid"] = sent_hwid; save_db()
                valid_access = True
                log_payload["status"] = "Locked to Roblox"
            elif saved_roblox == sent_hwid:
                valid_access = True
                log_payload["status"] = "Success (Roblox)"
            else:
                log_payload["status"] = "HWID Mismatch (Roblox)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "HWID Mismatch (Wrong Acc)"})

        # 4. OTP Kontrolü (Gerekirse)
        # Eğer HWID yeni kilitlendiyse veya uzun süre girilmediyse OTP isteyebiliriz
        # Şimdilik basitçe OTP kapalı varsayalım, direkt giriş verelim.
        # Eğer OTP istersen buraya ekleyebilirim.

        if valid_access:
            rem = int(info["expires"] - time.time())
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": True, "msg": "Authenticated", "left": f"{rem//86400}d"})

    except Exception as e:
        return jsonify({"valid": False, "msg": "Server Error"})

@app.route('/check_otp', methods=['POST'])
def check_otp():
    # C++ OTP sistemi için basit kontrol
    return jsonify({"valid": True}) # Şimdilik Bypass

@app.route('/network', methods=['POST'])
@limiter.limit("60 per minute")
def network():
    try:
        data = request.json
        user_id = str(data.get("userId"))
        job_id = data.get("jobId")
        hwid = data.get("hwid")

        if hwid in database["blacklisted_hwids"] or user_id in database["blacklisted_ids"]:
            return jsonify({"command": "ban", "reason": "Your account has been suspended."})

        current_time = time.time()
        command_to_send = None
        reason_to_send = ""
        
        if user_id in online_users:
            if online_users[user_id].get("command"):
                command_to_send = online_users[user_id]["command"]
                reason_to_send = online_users[user_id].get("reason", "")
                online_users[user_id]["command"] = None 

        online_users[user_id] = {
            "id": user_id, "job": job_id, "hwid": hwid,
            "last_seen": current_time, "command": command_to_send 
        }
        
        active_users_list = []
        for uid, udata in list(online_users.items()):
            if current_time - udata["last_seen"] < 60:
                active_users_list.append({"id": uid, "job": udata["job"]})
            else:
                del online_users[uid]

        response = {"users": active_users_list}
        if command_to_send:
            response["command"] = command_to_send
            response["reason"] = reason_to_send

        return jsonify(response)
    except:
        return jsonify({"error": "server error"})

# --- DISCORD COMMANDS ---
@bot.tree.command(name="genkey", description="Generate a new license key")
@app_commands.describe(duration="30d, 12h", user="User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id not in ADMIN_IDS: 
        await interaction.response.send_message("Unauthorized access.", ephemeral=True)
        return
    
    for k, v in database["keys"].items():
        if v.get("assigned_id") == user.id:
            await interaction.response.send_message(f"User {user.mention} already has a key.", ephemeral=True); return

    h = parse_duration(duration)
    if not h: await interaction.response.send_message("Invalid duration.", ephemeral=True); return
    
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    database["keys"][key] = {
        "native_hwid": None, "roblox_hwid": None, 
        "expires": time.time() + (h * 3600),
        "created_at": time.time(), "duration_txt": duration, 
        "assigned_id": user.id, "last_roblox_name": "N/A"
    }
    save_db()
    
    try:
        verified_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if verified_role: await user.add_roles(verified_role)
    except: pass

    await interaction.response.send_message(f"License generated for {user.mention}.\nKey: `{key}`\nDuration: {duration}")

@bot.tree.command(name="reset_hwid", description="Reset HWID binding")
async def reset_hwid(interaction: discord.Interaction):
    target_key = None
    for k, v in database["keys"].items():
        if v.get("assigned_id") == interaction.user.id:
            target_key = k
            break       
    if not target_key: await interaction.response.send_message("No active license found.", ephemeral=True); return
        
    info = database["keys"][target_key]
    info["native_hwid"] = None
    info["roblox_hwid"] = None
    save_db()
    await interaction.response.send_message("HWID binding has been reset successfully.")

@bot.tree.command(name="listkeys", description="List all active licenses")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    if not database["keys"]: await interaction.response.send_message("No active licenses.", ephemeral=True); return
    lines = []
    g = bot.get_guild(GUILD_ID)
    for k, v in list(database["keys"].items()):
        m = g.get_member(v["assigned_id"]) if v.get("assigned_id") else None
        u = f"{m.name}" if m else "Unknown"
        lines.append(f"Key: `{k}` | User: {u} | Term: {v.get('duration_txt')}")
    f = discord.File(io.StringIO("\n".join(lines)), filename="active_keys.txt")
    await interaction.response.send_message("Active License Database:", file=f)

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
