import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
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

# --- KONFİGÜRASYON ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1358830140343193821 
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- SİSTEM KURULUMU ---
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default(); intents.message_content = True; intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# Çevrimiçi kullanıcıları ve bekleyen komutları tutar
# Yapı: { "roblox_id": { "job": "...", "last_seen": 12345, "hwid": "...", "command": None, "reason": "" } }
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

def save_db():
    try:
        with open(DB_FILE, "w") as f:
            json.dump(database, f)
    except:
        pass

load_db()

def parse_duration(s):
    s = s.lower()
    try: 
        if "d" in s: return int(s.replace("d",""))*24
        elif "h" in s: return int(s.replace("h",""))
        else: return int(s)
    except: return None

# --- DM GÖNDERME ---
async def send_dm_code(user_id, code):
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="🔐 Login Verification", color=0xF1C40F)
            embed.description = f"Code: `{code}`"
            await user.send(embed=embed)
            return True
    except: return False

# --- FLASK YOLLARI (API) ---

@app.route('/', methods=['GET'])
def home(): return "Anarchy System Online"

# 1. GİRİŞ VE DOĞRULAMA
@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key"); hwid = data.get("hwid")
        username = data.get("username")
        display_name = data.get("display_name")
        
        if hwid in database["blacklisted_hwids"]: return jsonify({"valid": False, "msg": "HWID BANNED"})
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        
        # İsmi ve Roblox ID'yi kaydet (Banlarken lazım olacak)
        if username:
            info["last_roblox_name"] = f"{display_name} (@{username})"
        
        # Roblox ID'yi database'e eklemeye çalış (Ban eşleştirmesi için)
        # Not: Roblox scriptinden verify sırasında ID göndermek iyi olur ama şimdilik isimden idare ediyoruz.

        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Key Expired"})

        if info["hwid"] == hwid: 
            # 24 Saat OTP Kontrolü
            last_check = info.get("last_otp_verify", 0)
            if time.time() - last_check > 86400:
                if "otp" not in info:
                    info["otp"] = str(random.randint(100000, 999999))
                    info["temp_hwid"] = hwid
                    save_db()
                asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
                return jsonify({"valid": False, "msg": "OTP_SENT"})
            else:
                rem = int(info["expires"] - time.time())
                return jsonify({"valid": True, "msg": "Welcome Back", "left": f"{rem//86400}d"})
            
        elif info["hwid"] is None:
            if "otp" not in info:
                info["otp"] = str(random.randint(100000, 999999))
                info["temp_hwid"] = hwid
                save_db()
            asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
            return jsonify({"valid": False, "msg": "OTP_SENT"})
            
        else: return jsonify({"valid": False, "msg": "HWID Mismatch"})

    except: return jsonify({"valid": False, "msg": "Server Error"})

# 2. OTP KONTROL
@app.route('/check_otp', methods=['POST'])
def check_otp():
    try:
        data = request.json
        key = data.get("key"); code = data.get("code")
        
        if key not in database["keys"]: return jsonify({"valid": False})
        info = database["keys"][key]
        
        if info.get("otp") == code:
            info["hwid"] = info["temp_hwid"]
            info["last_otp_verify"] = time.time()
            if "otp" in info: del info["otp"]
            if "temp_hwid" in info: del info["temp_hwid"]
            save_db()
            rem = int(info["expires"] - time.time())
            return jsonify({"valid": True, "left": f"{rem//86400}d"})
        else:
            return jsonify({"valid": False, "msg": "Wrong Code"})
    except: return jsonify({"valid": False})

# 3. NETWORK (Admin Paneli ve Kullanıcı Listesi İçin)
@app.route('/network', methods=['POST'])
def network():
    try:
        data = request.json
        user_id = str(data.get("userId")) # Roblox ID
        job_id = data.get("jobId")
        hwid = data.get("hwid")

        # Ban Kontrolü (HWID veya ID yasaklı mı?)
        if hwid in database["blacklisted_hwids"] or user_id in database["blacklisted_ids"]:
            return jsonify({"command": "ban", "reason": "You are permanently banned."})

        # Kullanıcıyı Online Listesine Ekle/Güncelle
        current_time = time.time()
        
        # Eğer bu kullanıcıya özel bir komut (Kick/Ban) varsa onu al
        command_to_send = None
        reason_to_send = ""
        
        if user_id in online_users:
            if online_users[user_id].get("command"):
                command_to_send = online_users[user_id]["command"]
                reason_to_send = online_users[user_id].get("reason", "")
                # Komutu gönderdikten sonra sıfırla
                online_users[user_id]["command"] = None 

        online_users[user_id] = {
            "id": user_id,
            "job": job_id,
            "hwid": hwid,
            "last_seen": current_time,
            "command": command_to_send # Varsa komutu tekrar yerine koyuyoruz ki kaybolmasın (eğer yukarıda sıfırlamazsak)
        }
        
        # Eski kullanıcıları listeden temizle (60 saniye inaktifse)
        active_users_list = []
        for uid, udata in list(online_users.items()):
            if current_time - udata["last_seen"] < 60:
                active_users_list.append({"id": uid, "job": udata["job"]})
            else:
                del online_users[uid]

        response = {
            "users": active_users_list
        }
        
        if command_to_send:
            response["command"] = command_to_send
            response["reason"] = reason_to_send

        return jsonify(response)
    except Exception as e:
        print(f"Network Error: {e}")
        return jsonify({"error": "server error"})

# 4. ADMIN: KICK KOMUTU
@app.route('/admin/kick', methods=['POST'])
def admin_kick():
    data = request.json
    target_id = str(data.get("targetId"))
    
    if target_id in online_users:
        online_users[target_id]["command"] = "kick"
        return jsonify({"success": True, "msg": "Kick command queued"})
    return jsonify({"success": False, "msg": "User not online"})

# 5. ADMIN: BAN & WIPE KOMUTU
@app.route('/admin/ban', methods=['POST'])
def admin_ban():
    data = request.json
    target_id = str(data.get("targetId"))
    reason = data.get("reason", "Anarchy Ban")
    action = data.get("action") # full_wipe

    # 1. Roblox ID'yi Banla
    if target_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(target_id)

    # 2. Online ise HWID'yi bul ve banla + Kick komutu gönder
    hwid_to_ban = None
    if target_id in online_users:
        hwid_to_ban = online_users[target_id].get("hwid")
        online_users[target_id]["command"] = "ban"
        online_users[target_id]["reason"] = reason

    if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid_to_ban)

    # 3. Key Silme ve Discord'dan Atma
    key_to_delete = None
    discord_id_to_kick = None

    # HWID üzerinden Key bulmaya çalış
    if hwid_to_ban:
        for k, v in list(database["keys"].items()):
            if v.get("hwid") == hwid_to_ban:
                key_to_delete = k
                discord_id_to_kick = v.get("assigned_id")
                break
    
    # Key sil
    if key_to_delete:
        del database["keys"][key_to_delete]

    save_db()

    # Discord'dan Atma İşlemi (Async)
    if discord_id_to_kick:
        asyncio.run_coroutine_threadsafe(kick_discord_user(discord_id_to_kick, reason), bot.loop)

    return jsonify({"success": True, "msg": "User Wiped & Banned"})

# --- DISCORD HELPER ---
async def kick_discord_user(user_id, reason):
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                try: await member.send(f"🚫 **You have been banned from Anarchy.**\nReason: {reason}")
                except: pass
                await member.kick(reason=reason)
                print(f"Kicked Discord User: {user_id}")
            else:
                # Kullanıcı sunucuda yoksa fetch ile bulup banlamayı deneyebiliriz (opsiyonel)
                pass
    except Exception as e:
        print(f"Discord Kick Error: {e}")

# --- DISCORD KOMUTLARI ---
@bot.tree.command(name="genkey", description="Create License")
@app_commands.describe(duration="30d, 12h", user="Buyer")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID: await interaction.response.send_message("No permission.", ephemeral=True); return
    
    h = parse_duration(duration)
    if not h: await interaction.response.send_message("Bad format.", ephemeral=True); return
    
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    database["keys"][key] = {
        "hwid": None, "expires": time.time() + (h * 3600),
        "created_at": time.time(), "duration_txt": duration, 
        "assigned_id": user.id, "last_reset": 0, "last_roblox_name": "N/A",
        "last_otp_verify": 0
    }
    save_db()
    
    try:
        r = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if r: await user.add_roles(r)
    except: pass

    await interaction.response.send_message(f"✅ Key Generated for {user.mention}\n`{key}`")

@bot.tree.command(name="reset_hwid", description="Reset HWID")
async def reset_hwid(interaction: discord.Interaction):
    target_key = None
    for k, v in database["keys"].items():
        if v.get("assigned_id") == interaction.user.id:
            target_key = k; break
    
    if not target_key: await interaction.response.send_message("You don't have a key.", ephemeral=True); return
    
    info = database["keys"][target_key]
    last_r = info.get("last_reset", 0)
    
    if time.time() - last_r < 259200 and interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Cooldown active (3 days).", ephemeral=True); return

    info["hwid"] = None
    info["last_reset"] = time.time()
    save_db()
    await interaction.response.send_message("HWID Reset Successful.")

@bot.event
async def on_ready():
    print(f"Discord Bot Connected: {bot.user}")
    try: await bot.tree.sync()
    except: pass

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
