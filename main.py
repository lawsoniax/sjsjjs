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
DB_FILE = "anarchy_db.json"
LOG_WEBHOOK = "https://discord.com/api/webhooks/1464013246414717192/mXK-_-Yft9JqDS-pqUWSbOa1Uv5wzHtmN0jOC5__aU4_cewwXikQZ1ofDVmc141cpkaj"

# --- DISCORD OAUTH ---
CLIENT_ID = "1464002253244600511" 
CLIENT_SECRET = "6djxraALuFvcg6ZLT_aDpHs94Y4PcUzj"
REDIRECT_URI = "https://sjsjjs.onrender.com/callback"

ADMIN_IDS = [1358830140343193821, 1039946239938142218]
INITIAL_KEYS = {} 
pending_logins = {}

# --- SISTEM ---
logging.basicConfig(level=logging.INFO) # Logları görelim
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
intents.presences = True 

bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# Flask limitini geniş tutuyoruz, kendi mantığımızı kullanacağız
limiter = Limiter(get_remote_address, app=app, default_limits=["50000 per day"], storage_uri="memory://")

# TEK VERİTABANI (Security + Keys)
database = {"keys": {}, "users": {}, "blacklisted_hwids": [], "security": {}}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                # Eksik anahtarları tamamla
                for k in ["keys", "users", "blacklisted_hwids", "security"]:
                    if k not in data: 
                        data[k] = {} if k != "blacklisted_hwids" else []
                database = data
        except: pass
    else:
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

# ==========================================
#        GÜVENLİK SİSTEMİ (ÇEKİRDEK)
# ==========================================

def calculate_penalty(streak):
    # 1. Hata: Uyarı (Ceza Yok)
    if streak <= 1: return 0        
    # 2. Hata: 60 Saniye (Direkt Ceza)
    if streak == 2: return 60       
    # 3. Hata: 5 Dakika
    if streak == 3: return 300      
    # 4. Hata: 1 Saat
    if streak >= 4: return 3600     
    return 0

def check_security(hwid):
    """Kullanıcının banlı olup olmadığını kontrol eder."""
    current_time = time.time()
    
    if hwid not in database["security"]:
        return True, "OK"
    
    sec = database["security"][hwid]
    
    # Eğer ceza süresi bitmemişse
    if current_time < sec.get("ban_until", 0):
        remaining = int(sec["ban_until"] - current_time)
        return False, f"SECURITY LOCK: Wait {remaining}s"
    
    return True, "OK"

def add_strike(hwid):
    """Kullanıcıya ceza puanı ekler ve gerekirse banlar."""
    current_time = time.time()
    
    if hwid not in database["security"]:
        database["security"][hwid] = {"fails": 0, "ban_until": 0}
    
    sec = database["security"][hwid]
    sec["fails"] += 1
    
    streak = sec["fails"]
    penalty = calculate_penalty(streak)
    
    msg = ""
    if penalty > 0:
        sec["ban_until"] = current_time + penalty
        msg = f"SECURITY LOCK: Wait {penalty}s"
    else:
        msg = "Warning: Do not spam!" # UI'da göstermeyebiliriz ama loga düşer
        
    save_db()
    print(f"[SECURITY] HWID: {hwid} | Strike: {streak} | Penalty: {penalty}s")
    
    return penalty > 0, msg # (Cezalı mı?, Mesaj)

def clear_strike(hwid):
    """Başarılı işlemde sicili temizler."""
    if hwid in database["security"]:
        database["security"][hwid] = {"fails": 0, "ban_until": 0}
        save_db()

# --- DISCORD LOG ---
def send_discord_log(title, discord_user, pc_user, key, hwid, ip, status, color=3066993):
    try:
        embed = {
            "title": f"🛡️ {title}", "color": color,
            "fields": [
                {"name": "User", "value": f"{discord_user}", "inline": True},
                {"name": "PC", "value": f"{pc_user}", "inline": True},
                {"name": "HWID", "value": f"`{hwid}`", "inline": False},
                {"name": "Status", "value": f"**{status}**", "inline": True},
                {"name": "Key", "value": f"`{key}`", "inline": False}
            ],
            "footer": {"text": "Anarchy Auth System"}
        }
        requests.post(LOG_WEBHOOK, json={"username": "Anarchy Logger", "embeds": [embed]})
    except: pass

def get_real_ip():
    if request.headers.getlist("X-Forwarded-For"): return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

# ==========================================
#        ENDPOINTS (LUA & C++)
# ==========================================

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        discord_name = data.get("username", "").strip()
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        ip = get_real_ip()

        # 1. GÜVENLİK KONTROLÜ (Girişte)
        is_safe, sec_msg = check_security(hwid)
        if not is_safe:
            return jsonify({"success": False, "msg": sec_msg})

        # 2. BAN KONTROLÜ
        if hwid in database["blacklisted_hwids"]:
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member_named(discord_name) if guild else None
        
        if not member:
            is_banned, ban_msg = add_strike(hwid) # HATA -> CEZA EKLE
            if is_banned: return jsonify({"success": False, "msg": ban_msg})
            return jsonify({"success": False, "msg": "User Not Found"})

        # 3. ZATEN KEY VAR MI?
        existing_key = None
        for k, v in database["keys"].items():
            if v.get("assigned_id") == member.id and time.time() < v.get("expires", 0):
                existing_key = k
                break
        
        if existing_key:
            # KRİTİK NOKTA: Zaten kayıtlıysa da CEZA EKLE!
            is_banned, ban_msg = add_strike(hwid)
            
            # Eğer bu tıklamada ceza sınırını geçtiyse, "Already Registered" yerine direkt BAN mesajını göster
            if is_banned:
                return jsonify({"success": False, "msg": ban_msg})
            else:
                return jsonify({"success": False, "msg": "Already Registered!"})

        # 4. YENİ KAYIT
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        database["keys"][new_key] = {
            "native_hwid": hwid, "roblox_nick": "N/A", 
            "expires": time.time() + (7 * 86400), "assigned_id": member.id,
            "registered_name": discord_name, "pc_user": pc_user
        }
        save_db()
        
        clear_strike(hwid) # Başarılı -> Sicili temizle
        asyncio.run_coroutine_threadsafe(member.send(f"Anarchy License: `{new_key}`"), bot.loop)
        
        send_discord_log("New Register", discord_name, pc_user, new_key, hwid, ip, "Success")
        return jsonify({"success": True, "msg": "Sent to DM"})

    except Exception as e:
        print(e)
        return jsonify({"success": False, "msg": "Server Error"})

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        pc_user = data.get("pc_user", "Unknown")
        roblox = data.get("roblox_user")
        ip = get_real_ip()

        # 1. GÜVENLİK KONTROLÜ
        is_safe, sec_msg = check_security(hwid)
        if not is_safe: return jsonify({"valid": False, "msg": sec_msg})

        if key not in database["keys"]:
            is_banned, ban_msg = add_strike(hwid)
            if is_banned: return jsonify({"valid": False, "msg": ban_msg})
            
            send_discord_log("Failed Login", "Unknown", pc_user, key, hwid, ip, "Invalid Key", 15158332)
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]: return jsonify({"valid": False, "msg": "Expired"})

        if info.get("native_hwid") and info.get("native_hwid") != hwid:
            is_banned, ban_msg = add_strike(hwid)
            if is_banned: return jsonify({"valid": False, "msg": ban_msg})
            return jsonify({"valid": False, "msg": "Wrong HWID"})
        
        if not info.get("native_hwid"): 
            info["native_hwid"] = hwid; save_db()

        if roblox: info["roblox_nick"] = roblox; save_db()

        clear_strike(hwid) # Başarılı -> Temizle
        send_discord_log("Login Success", info.get("registered_name"), pc_user, key, hwid, ip, "Authorized")
        return jsonify({"valid": True, "msg": "Success"})

    except: return jsonify({"valid": False, "msg": "Error"})

# --- LUA ÖZEL ---
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
            user_list.append({
                "roblox": v.get("roblox_nick", "N/A"),
                "discord": v.get("registered_name", "Unknown"),
                "status": "Online"
            })
        return jsonify(user_list)
    except: return jsonify([])

# --- DISCORD ---
@app.route('/callback')
def discord_callback(): 
    # Otomatik Kapatma Sayfası
    return """
    <script>setTimeout(function(){window.close()},1000);</script>
    <body style="background:#111;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;">
    <h1>Login Successful. You can close this.</h1>
    </body>
    """

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

# --- CEZA SIFIRLAMA KOMUTU (ADMİNLER İÇİN) ---
@bot.tree.command(name="unban_hwid")
async def unban_hwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("No permission", ephemeral=True); return
    if hwid in database["security"]:
        database["security"][hwid] = {"fails": 0, "ban_until": 0}
        save_db()
        await interaction.response.send_message(f"Unbanned HWID: {hwid}", ephemeral=True)
    else: await interaction.response.send_message("HWID not found in security DB", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
