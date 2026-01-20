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
    try: with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass
load_db()

def parse_duration(s):
    s = s.lower()
    try: return int(s.replace("d",""))*24 if "d" in s else int(s.replace("h","")) if "h" in s else int(s)
    except: return None

async def send_dm_code(user_id, code):
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="🔐 Security Check", color=0xF1C40F)
            embed.description = f"Daily security verification required.\n\n**Code:** `{code}`\n\nEnter this code in the script."
            embed.set_footer(text="Valid for 24 hours.")
            await user.send(embed=embed)
            return True
    except Exception as e:
        print(f"DM Failed: {e}")
        return False

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
        
        if hwid in database["blacklisted_hwids"]: return jsonify({"valid": False, "msg": "HWID BANNED"})
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Key Expired"})

        g = bot.get_guild(GUILD_ID)
        if g and not g.get_member(info["assigned_id"]):
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "User left Discord"})

        # --- GÜNLÜK KONTROL SİSTEMİ ---
        
        # 1. HWID Eşleşiyor mu?
        if info["hwid"] == hwid: 
            # 2. Son doğrulama üzerinden 24 saat (86400 sn) geçti mi?
            last_check = info.get("last_otp_verify", 0)
            if time.time() - last_check > 86400:
                # SÜRE DOLMUŞ -> YENİ KOD İSTE
                if "otp" not in info:
                    info["otp"] = str(random.randint(100000, 999999))
                    info["temp_hwid"] = hwid # Mevcut HWID'yi tekrar teyit et
                    save_db()
                
                asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
                return jsonify({"valid": False, "msg": "OTP_SENT"}) # Script'e kod sor emri
            else:
                # SÜRE DOLMAMIŞ -> GİRİŞ BAŞARILI
                rem = int(info["expires"] - time.time())
                return jsonify({"valid": True, "msg": "Welcome Back", "left": f"{rem//86400}d"})
            
        elif info["hwid"] is None:
            # YENİ CİHAZ -> KOD İSTE
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
            info["last_otp_verify"] = time.time() # DOĞRULAMA ZAMANINI KAYDET
            del info["otp"]; del info["temp_hwid"]
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
