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

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1358830140343193821 
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- SYSTEM SETUP ---
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default(); intents.message_content = True; intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# [YENİ] Online Kullanıcıları Takip Eden Sistem
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

# --- DM GÖNDERME FONKSİYONU ---
async def send_dm_code(user_id, code):
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="🔐 Login Verification", color=0xF1C40F)
            embed.description = f"A new device is trying to access your script.\n\n**Code:** `{code}`\n\nEnter this code inside the **Roblox Script** window."
            embed.set_footer(text="Do not share this code.")
            await user.send(embed=embed)
            return True
    except Exception as e:
        print(f"DM Failed: {e}")
        return False

# [YENİ] Discord'dan Atma Fonksiyonu
async def kick_discord_user(user_id, reason):
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                try: await member.send(f"🚫 **You have been banned from Anarchy.**\nReason: {reason}")
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
    if member.id == ADMIN_ID: return
    deleted = False
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
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
    
    # Update Name via Loop as well
    if hwid:
        for k, v in database["keys"].items():
            if v.get("hwid") == hwid:
                v["last_roblox_name"] = rbx_name
                save_db()
                break

    embed = discord.Embed(title=f"Monitor: {status}", color=0x2ECC71 if status=="Online" else 0xE74C3C)
    embed.add_field(name="User", value=f"**DS:** {d_id}\n**RBX:** {rbx_name}")
    embed.add_field(name="Data", value=f"Game: {data.get('game')}\nFPS: {data.get('fps')}")
    embed.set_footer(text=f"Anarchy • {datetime.datetime.now().strftime('%H:%M')}")
    
    mid = user_sessions.get(uid, {}).get('msg_id')
    if mid: 
        try: msg = await c.fetch_message(mid); await msg.edit(embed=embed); return
        except: pass
    m = await c.send(embed=embed)
    if uid not in user_sessions: user_sessions[uid]={}
    user_sessions[uid]['msg_id'] = m.id

# --- FLASK ENDPOINTS ---
@app.route('/', methods=['GET'])
def home(): return "Anarchy C&C"

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key"); hwid = data.get("hwid")
        
        # İSİM GÜNCELLEME
        username = data.get("username")
        display_name = data.get("display_name")
        
        if hwid in database["blacklisted_hwids"]: return jsonify({"valid": False, "msg": "HWID BANNED"})
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        
        # Veritabanına ismi kaydet
        if username and display_name:
            info["last_roblox_name"] = f"{display_name} (@{username})"
            save_db()

        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Key Expired"})

        g = bot.get_guild(GUILD_ID)
        if g and not g.get_member(info["assigned_id"]):
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "User left Discord"})

        # --- LOGIN LOGIC ---
        if info["hwid"] == hwid: 
            # 24 SAAT KURALI
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
            
            # OTP sırasında da ismi güncelle
            username = data.get("username")
            display_name = data.get("display_name")
            if username and display_name:
                info["last_roblox_name"] = f"{display_name} (@{username})"
            
            save_db()
            rem = int(info["expires"] - time.time())
            return jsonify({"valid": True, "left": f"{rem//86400}d"})
        else:
            return jsonify({"valid": False, "msg": "Wrong Code"})
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
    d = request.json
    if d.get("target_id") not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(d.get("target_id")); save_db()
    return jsonify({"success": True})

# [YENİ] ROBLOX SCRIPTINDEN GELEN ISTEKLER ICIN (ADMIN PANEL + ONLINE LISTESI)
@app.route('/network', methods=['POST'])
def network():
    try:
        data = request.json
        user_id = str(data.get("userId"))
        job_id = data.get("jobId")
        hwid = data.get("hwid")

        # Ban Kontrolü
        if hwid in database["blacklisted_hwids"] or user_id in database["blacklisted_ids"]:
            return jsonify({"command": "ban", "reason": "You are permanently banned."})

        # Kullanıcıyı Online Listesine Kaydet
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
        
        # İnaktifleri temizle
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

# [YENİ] ADMIN PANELINDEN GELEN KICK ISTEGI
@app.route('/admin/kick', methods=['POST'])
def admin_kick():
    data = request.json
    target_id = str(data.get("targetId"))
    if target_id in online_users:
        online_users[target_id]["command"] = "kick"
        online_users[target_id]["reason"] = "You have been kicked by an admin."
        return jsonify({"success": True})
    return jsonify({"success": False})

# [YENİ] ADMIN PANELINDEN GELEN BAN & WIPE ISTEGI
@app.route('/admin/ban', methods=['POST'])
def admin_ban():
    data = request.json
    target_id = str(data.get("targetId"))
    reason = data.get("reason", "Admin Ban")

    # Roblox ID Banla
    if target_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(target_id)

    hwid_to_ban = None
    if target_id in online_users:
        hwid_to_ban = online_users[target_id].get("hwid")
        online_users[target_id]["command"] = "ban"
        online_users[target_id]["reason"] = reason

    if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid_to_ban)

    # Key Silme ve Discord Kick
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

# --- COMMANDS ---

@bot.tree.command(name="genkey", description="Create License assigned to a user")
@app_commands.describe(duration="30d, 12h", user="Buyer")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID: await interaction.response.send_message("No.", ephemeral=True); return
    
    for k, v in database["keys"].items():
        if v.get("assigned_id") == user.id:
            await interaction.response.send_message(f"User {user.mention} already has a key.", ephemeral=True); return

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

    await interaction.response.send_message(f"**License Generated**\nUser: {user.mention}\nKey: `{key}`\nDuration: {duration}\n\n*Daily Code will be sent via DM.*")

@bot.tree.command(name="reset_hwid", description="Reset HWID (Once per 3 days)")
async def reset_hwid(interaction: discord.Interaction):
    target_key = None
    for k, v in database["keys"].items():
        if v.get("assigned_id") == interaction.user.id:
            target_key = k
            break    
    if not target_key: await interaction.response.send_message("No key.", ephemeral=True); return
        
    info = database["keys"][target_key]
    last_r = info.get("last_reset", 0)
    if time.time() - last_r < 259200 and interaction.user.id != ADMIN_ID:
        remaining = int(259200 - (time.time() - last_r))
        h = remaining // 3600
        await interaction.response.send_message(f"Cooldown! Wait {h} hours.", ephemeral=True); return

    info["hwid"] = None
    info["last_reset"] = time.time()
    save_db()
    await interaction.response.send_message(f"✅ HWID Reset! New code will be sent on login.")

@bot.tree.command(name="listhwids", description="Admin: List Banned HWIDs")
async def listhwids(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    hwids = database.get("blacklisted_hwids", [])
    if not hwids: await interaction.response.send_message("No banned HWIDs.", ephemeral=True); return
    lines = [f"🚫 **Banned HWIDs ({len(hwids)}):**"]
    for hwid in hwids: lines.append(f"`{hwid}`")
    msg = "\n".join(lines)
    if len(msg) > 1900:
        f = discord.File(io.StringIO(msg), filename="banned_hwids.txt")
        await interaction.response.send_message("List attached:", file=f)
    else: await interaction.response.send_message(msg)

@bot.tree.command(name="delkey", description="Admin: Delete Key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID: return
    if key in database["keys"]: del database["keys"][key]; save_db(); await interaction.response.send_message("Deleted.")
    else: await interaction.response.send_message("Not found.")

@bot.tree.command(name="ban_roblox_user", description="Global Ban Roblox ID")
async def ban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id != ADMIN_ID: return
    if roblox_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(roblox_id)
        save_db()
        await interaction.response.send_message(f"Roblox ID `{roblox_id}` banned.")
    else: await interaction.response.send_message("Already banned.")

@bot.tree.command(name="listkeys", description="Admin: List Active Keys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]: await interaction.response.send_message("No active keys.", ephemeral=True); return
    lines = []
    g = bot.get_guild(GUILD_ID)
    for k, v in list(database["keys"].items()):
        m = g.get_member(v["assigned_id"]) if v.get("assigned_id") else None
        u = f"{m.name}" if m else "Unknown"
        rbx = v.get("last_roblox_name", "N/A")
        lines.append(f"`{k}`\nDs: {u} | Rbx: {rbx} | Time: {v.get('duration_txt')}\n")
    f = discord.File(io.StringIO("\n".join(lines)), filename="keys.txt")
    await interaction.response.send_message("Active Licenses:", file=f)

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
