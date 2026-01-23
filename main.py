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

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1462815057669918821

# Admin ID Listesi
ADMIN_IDS = [1358830140343193821, 1039946239938142218]

GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- SYSTEM SETUP ---
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default(); intents.message_content = True; intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# --- RATE LIMITER SETUP (YENİ EKLENDİ) ---
# Sunucunu spam'den korumak için gerekli ayar.
# Hafızada tutar (RAM kullanır), veritabanı gerektirmez.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "60 per hour"], # Varsayılan genel limitler
    storage_uri="memory://"
)

# Online User Tracking System
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
        if "d" in s:
            return int(s.replace("d",""))*24
        elif "h" in s:
            return int(s.replace("h",""))
        else:
            return int(s)
    except: return None

# --- DM FUNCTION ---
async def send_dm_code(user_id, code):
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="Login Verification", color=0x2C3E50)
            embed.description = f"A new device is attempting to access the script.\n\n**Authorization Code:** `{code}`\n\nPlease enter this code in the Roblox execution window."
            embed.set_footer(text="Security Alert: Do not share this code.")
            await user.send(embed=embed)
            return True
    except Exception as e:
        print(f"DM Failed: {e}")
        return False

# --- DISCORD KICK FUNCTION ---
async def kick_discord_user(user_id, reason):
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                try: await member.send(f"**Notice of Termination**\nYou have been banned from Anarchy.\nReason: {reason}")
                except: pass
                await member.kick(reason=reason)
    except Exception as e:
        print(f"Kick Error: {e}")

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"System Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

@bot.event
async def on_member_remove(member):
    # Adminlerden biri çıkarsa işlem yapma
    if member.id in ADMIN_IDS: return

    deleted = False
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            # Kullanıcı çıkarsa HWID'sini blacklist'e al (Güvenlik önlemi)
            if info.get("hwid") and info["hwid"] not in database["blacklisted_hwids"]:
                database["blacklisted_hwids"].append(info["hwid"])
            del database["keys"][key]
            deleted = True
            break        
    if deleted: save_db()

async def log_discord(data, uid, status, d_id):
    await bot.wait_until_ready(); c = bot.get_channel(CHANNEL_ID)
    if not c: return
    
    hwid = data.get('hwid')
    rbx_name = f"{data.get('display_name')} (@{data.get('username')})"
    
    if hwid:
        for k, v in database["keys"].items():
            if v.get("hwid") == hwid:
                v["last_roblox_name"] = rbx_name
                save_db()
                break

    embed = discord.Embed(title=f"Session Monitor: {status}", color=0x3498DB if status=="Online" else 0xE74C3C)
    embed.add_field(name="User Identity", value=f"**Discord:** {d_id}\n**Roblox:** {rbx_name}")
    embed.add_field(name="Session Data", value=f"Game ID: {data.get('game')}\nPerformance: {data.get('fps')} FPS")
    embed.set_footer(text=f"System Time: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    mid = user_sessions.get(uid, {}).get('msg_id')
    if mid: 
        try: msg = await c.fetch_message(mid); await msg.edit(embed=embed); return
        except: pass
    m = await c.send(embed=embed)
    if uid not in user_sessions: user_sessions[uid]={}
    user_sessions[uid]['msg_id'] = m.id

# --- FLASK ENDPOINTS ---
@app.route('/', methods=['GET'])
def home(): return "System Operational"

@app.route('/verify', methods=['POST'])
@limiter.limit("10 per minute") # [RATE LIMIT] Dakikada max 10 deneme
def verify():
    try:
        data = request.json
        key = data.get("key"); hwid = data.get("hwid")
        username = data.get("username")
        display_name = data.get("display_name")
        
        if hwid in database["blacklisted_hwids"]: return jsonify({"valid": False, "msg": "Access Denied: HWID Banned"})
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]
        
        if username and display_name:
            info["last_roblox_name"] = f"{display_name} (@{username})"
            save_db()

        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "License Expired"})

        g = bot.get_guild(GUILD_ID)
        if g and not g.get_member(info["assigned_id"]):
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Discord Membership Required"})

        if info["hwid"] == hwid: 
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
                return jsonify({"valid": True, "msg": "Authenticated", "left": f"{rem//86400}d"})
            
        elif info["hwid"] is None:
            if "otp" not in info:
                info["otp"] = str(random.randint(100000, 999999))
                info["temp_hwid"] = hwid
                save_db()
            
            asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
            return jsonify({"valid": False, "msg": "OTP_SENT"})
            
        else: return jsonify({"valid": False, "msg": "HWID Mismatch"})

    except: return jsonify({"valid": False, "msg": "Internal Server Error"})

@app.route('/check_otp', methods=['POST'])
@limiter.limit("10 per minute") # [RATE LIMIT] OTP deneme sınırı
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
            
            username = data.get("username")
            display_name = data.get("display_name")
            if username and display_name:
                info["last_roblox_name"] = f"{display_name} (@{username})"
            
            save_db()
            rem = int(info["expires"] - time.time())
            return jsonify({"valid": True, "left": f"{rem//86400}d"})
        else:
            return jsonify({"valid": False, "msg": "Invalid Code"})
    except: return jsonify({"valid": False})

@app.route('/update', methods=['POST'])
def update_log():
    data = request.json
    uid = str(data.get("user_id")); hwid = data.get("hwid")
    if uid in database["blacklisted_ids"] or (hwid and hwid in database["blacklisted_hwids"]):
        return jsonify({"command": "KICK"})
    
    d_str = "Unknown"
    if hwid:
        for k, v in database["keys"].items():
            if v.get("hwid") == hwid:
                u = bot.get_user(v.get("assigned_id"))
                if u: d_str = f"{u.name} ({u.id})"
                break
                
    asyncio.run_coroutine_threadsafe(log_discord(data, uid, "Online", d_str), bot.loop)
    return jsonify({"command": "NONE"})

@app.route('/ban', methods=['POST'])
def ban():
    # Bu route roblox scripti içinden ID banlamak için
    d = request.json
    if d.get("target_id") not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(d.get("target_id")); save_db()
    return jsonify({"success": True})

# --- ROBLOX API ROUTES ---
@app.route('/network', methods=['POST'])
@limiter.limit("60 per minute")
def network():
    try:
        data = request.json
        user_id = str(data.get("userId"))
        job_id = data.get("jobId")
        hwid = data.get("hwid")

        if hwid in database["blacklisted_hwids"] or user_id in database["blacklisted_ids"]:
            return jsonify({"command": "ban", "reason": "Your account has been permanently suspended."})

        current_time = time.time()
        command_to_send = None
        reason_to_send = ""
        
        if user_id in online_users:
            if online_users[user_id].get("command"):
                command_to_send = online_users[user_id]["command"]
                reason_to_send = online_users[user_id].get("reason", "")
                online_users[user_id]["command"] = None 

        online_users[user_id] = {
            "id": user_id,
            "job": job_id,
            "hwid": hwid,
            "last_seen": current_time,
            "command": command_to_send 
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

@app.route('/admin/kick', methods=['POST'])
def admin_kick():
    data = request.json
    target_id = str(data.get("targetId"))
    if target_id in online_users:
        online_users[target_id]["command"] = "kick"
        online_users[target_id]["reason"] = "You have been disconnected by an administrator."
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/admin/ban', methods=['POST'])
def admin_ban():
    data = request.json
    target_id = str(data.get("targetId"))
    reason = data.get("reason", "Administrator Ban")

    if target_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(target_id)

    hwid_to_ban = None
    if target_id in online_users:
        hwid_to_ban = online_users[target_id].get("hwid")
        online_users[target_id]["command"] = "ban"
        online_users[target_id]["reason"] = reason

    if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid_to_ban)

    key_to_delete = None
    discord_id_to_kick = None

    if hwid_to_ban:
        for k, v in list(database["keys"].items()):
            if v.get("hwid") == hwid_to_ban:
                key_to_delete = k
                discord_id_to_kick = v.get("assigned_id")
                break
    
    if key_to_delete:
        del database["keys"][key_to_delete]

    save_db()

    if discord_id_to_kick:
        asyncio.run_coroutine_threadsafe(kick_discord_user(discord_id_to_kick, reason), bot.loop)

    return jsonify({"success": True})

# --- DISCORD COMMANDS ---

@bot.tree.command(name="genkey", description="Generate a new license key")
@app_commands.describe(duration="30d, 12h", user="User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id not in ADMIN_IDS: 
        await interaction.response.send_message("Unauthorized access.", ephemeral=True)
        return
    
    for k, v in database["keys"].items():
        if v.get("assigned_id") == user.id:
            await interaction.response.send_message(f"User {user.mention} already possesses an active license.", ephemeral=True); return

    h = parse_duration(duration)
    if not h: await interaction.response.send_message("Invalid duration format.", ephemeral=True); return
    
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
        verified_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

        if verified_role: 
            await user.add_roles(verified_role)
        
        if member_role:
            await user.remove_roles(member_role) 
    except: pass

    await interaction.response.send_message(f"License generated for {user.mention}.\nKey: `{key}`\nDuration: {duration}")

@bot.tree.command(name="ban", description="Ban a user from Discord, Revoke Key and Ban HWID")
@app_commands.describe(user="The Discord user to ban", reason="Reason for the ban")
async def ban_command(interaction: discord.Interaction, user: discord.Member, reason: str = "Violating Rules"):
    # Yetki Kontrolü
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("Unauthorized access.", ephemeral=True)
        return

    # İşlem Raporu
    actions_taken = []
    
    # 1. Veritabanından Key ve HWID Kontrolü
    deleted_key = False
    banned_hwid = False
    target_key = None

    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == user.id:
            target_key = key
            
            # HWID varsa banla
            if info.get("hwid") and info["hwid"] not in database["blacklisted_hwids"]:
                database["blacklisted_hwids"].append(info["hwid"])
                banned_hwid = True
                actions_taken.append("HWID Blacklisted")
            
            # Key'i sil
            del database["keys"][key]
            deleted_key = True
            actions_taken.append("License Key Revoked")
            break
    
    if deleted_key or banned_hwid:
        save_db()

    # 2. Discord Sunucusundan Banla
    try:
        # Kullanıcıya DM atmayı dene
        try:
            await user.send(f"You have been banned from Anarchy.\nReason: {reason}")
        except: pass
        
        await user.ban(reason=reason)
        actions_taken.append("Banned from Discord Server")
    except Exception as e:
        actions_taken.append(f"Failed to ban from Discord: {e}")

    # 3. Sonuç Mesajı
    if not actions_taken:
        actions_taken.append("User had no key/HWID, but tried to ban from Discord.")
    
    embed = discord.Embed(title="User Termination Protocol", color=0xFF0000)
    embed.add_field(name="Target", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="Actions Taken", value="\n".join([f"• {x}" for x in actions_taken]), inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reset_hwid", description="Reset HWID binding")
async def reset_hwid(interaction: discord.Interaction):
    target_key = None
    for k, v in database["keys"].items():
        if v.get("assigned_id") == interaction.user.id:
            target_key = k
            break      
    if not target_key: await interaction.response.send_message("No active license found.", ephemeral=True); return
        
    info = database["keys"][target_key]
    last_r = info.get("last_reset", 0)
    
    if time.time() - last_r < 259200 and interaction.user.id not in ADMIN_IDS:
        remaining = int(259200 - (time.time() - last_r))
        h = remaining // 3600
        await interaction.response.send_message(f"Cooldown active. Please wait {h} hours.", ephemeral=True); return

    info["hwid"] = None
    info["last_reset"] = time.time()
    save_db()
    await interaction.response.send_message("HWID binding has been reset successfully.")

@bot.tree.command(name="listhwids", description="List banned HWIDs")
async def listhwids(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    hwids = database.get("blacklisted_hwids", [])
    if not hwids: await interaction.response.send_message("No banned HWIDs found.", ephemeral=True); return
    lines = [f"**Banned HWID List ({len(hwids)}):**"]
    for hwid in hwids: lines.append(f"`{hwid}`")
    msg = "\n".join(lines)
    if len(msg) > 1900:
        f = discord.File(io.StringIO(msg), filename="banned_hwids.txt")
        await interaction.response.send_message("List is too long, see attachment:", file=f)
    else: await interaction.response.send_message(msg)

@bot.tree.command(name="delkey", description="Revoke a license key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS: return
    if key in database["keys"]: del database["keys"][key]; save_db(); await interaction.response.send_message("License revoked.")
    else: await interaction.response.send_message("Key not found.")

@bot.tree.command(name="ban_roblox_user", description="Ban a Roblox User ID")
async def ban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id not in ADMIN_IDS: return
    if roblox_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(roblox_id)
        save_db()
        await interaction.response.send_message(f"Roblox ID `{roblox_id}` has been banned.")
    else: await interaction.response.send_message("This ID is already banned.")

@bot.tree.command(name="listkeys", description="List all active licenses")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    if not database["keys"]: await interaction.response.send_message("No active licenses.", ephemeral=True); return
    lines = []
    g = bot.get_guild(GUILD_ID)
    for k, v in list(database["keys"].items()):
        m = g.get_member(v["assigned_id"]) if v.get("assigned_id") else None
        u = f"{m.name}" if m else "Unknown"
        rbx = v.get("last_roblox_name", "N/A")
        lines.append(f"Key: `{k}` | User: {u} | Roblox: {rbx} | Term: {v.get('duration_txt')}")
    f = discord.File(io.StringIO("\n".join(lines)), filename="active_keys.txt")
    await interaction.response.send_message("Active License Database:", file=f)

@bot.tree.command(name="unban_hwid", description="Unban a specific HWID")
async def unban_hwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("Unauthorized access.", ephemeral=True); return
    
    if hwid in database.get("blacklisted_hwids", []):
        database["blacklisted_hwids"].remove(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` has been unbanned.", ephemeral=True)
    else:
        await interaction.response.send_message("HWID not found in blacklist.", ephemeral=True)

@bot.tree.command(name="unban_roblox_user", description="Unban a Roblox User ID")
async def unban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("Unauthorized access.", ephemeral=True); return
    
    if roblox_id in database.get("blacklisted_ids", []):
        database["blacklisted_ids"].remove(roblox_id)
        save_db()
        await interaction.response.send_message(f"Roblox ID `{roblox_id}` has been unbanned.", ephemeral=True)
    else:
        await interaction.response.send_message("ID not found in blacklist.", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
