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

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1358830140343193821 
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- SYSTEM SETUP ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

user_sessions = {}

# Database Structure
database = {
    "keys": {}, 
    "users": {}, 
    "history": [], 
    "blacklisted_hwids": [], 
    "blacklisted_ids": [] 
}

# --- DATABASE OPERATIONS ---
def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                if "history" not in data: data["history"] = []
                if "blacklisted_hwids" not in data: data["blacklisted_hwids"] = []
                if "blacklisted_ids" not in data: data["blacklisted_ids"] = []
                if "keys" not in data: data["keys"] = {}
                if "users" not in data: data["users"] = {}
                database = data
                print("[SYSTEM] Database loaded successfully.")
        except Exception as e: 
            print(f"[ERROR] Database load failed: {e}")

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

def parse_duration(duration_str: str):
    duration_str = duration_str.lower()
    try:
        if duration_str.endswith("d"):
            return int(duration_str.replace("d", "")) * 24
        elif duration_str.endswith("h"):
            return int(duration_str.replace("h", ""))
        else:
            return int(duration_str)
    except:
        return None

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"System Online: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Sync Error: {e}")

@bot.event
async def on_member_remove(member):
    # Admin is immune
    if member.id == ADMIN_ID: return

    deleted_key = None
    hwid_to_ban = None
    
    # 1. Check if user has a key
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            if info.get("hwid"):
                hwid_to_ban = info["hwid"]
            
            # Delete key
            del database["keys"][key]
            deleted_key = key
            break      
    
    # 2. PUNISHMENT IF KEY EXISTS
    if deleted_key:
        # A) Blacklist HWID (Prevents alt accounts on same PC)
        if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
            database["blacklisted_hwids"].append(hwid_to_ban)
            print(f"[SECURITY] Member {member.name} left with Active Key. HWID Blacklisted.")
        
        save_db()
        print(f"[SECURITY] License revoked for {member.name}.")

        # B) Ban from Discord (Prevents re-joining)
        try:
            await member.ban(reason="Anarchy Security: Left server while holding a license (Potential Seller).")
            print(f"[SECURITY] BANNED {member.name} from Discord Server.")
        except Exception as e:
            print(f"[ERROR] Could not ban {member.name}: {e}")

async def log_to_discord(data, user_id, status, discord_identity):
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    status_color = 0x2ECC71 if status == "Online" else 0xE74C3C
    
    embed = discord.Embed(title=f"System Monitor: {status}", color=status_color)
    
    profile_url = f"https://www.roblox.com/users/{user_id}/profile"
    
    r_display = data.get('display_name', 'Unknown')
    r_user = data.get('username', 'Unknown')
    game = data.get('game', 'Unknown')
    server_plrs = data.get('server_players', '?/?')
    job = data.get('job_id', 'Unknown')
    executor = data.get('executor', 'Unknown')
    
    embed.add_field(
        name="User Identification", 
        value=f"**Discord:** {discord_identity}\n**Roblox:** [{r_display}]({profile_url}) (@{r_user})\n**ID:** `{user_id}`", 
        inline=False
    )
    
    embed.add_field(
        name="Session Information", 
        value=f"**Game:** {game}\n**Server:** {server_plrs} Players\n**Job ID:** `{job}`", 
        inline=False
    )

    embed.add_field(
        name="Technical Specs", 
        value=f"**Executor:** {executor}\n**Ping:** {data.get('ping', 0)}ms | **FPS:** {data.get('fps', 0)}", 
        inline=False
    )

    thumb_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png"
    embed.set_thumbnail(url=thumb_url)
    
    time_str = datetime.datetime.now().strftime('%H:%M:%S')
    footer_text = f"Anarchy Security • {time_str}"
    if status == "Offline":
        footer_text = f"Connection Terminated • {time_str}"
        
    embed.set_footer(text=footer_text)

    msg_id = user_sessions.get(user_id, {}).get('msg_id')
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except: pass 

    msg = await channel.send(embed=embed)
    if user_id not in user_sessions: user_sessions[user_id] = {}
    user_sessions[user_id]['msg_id'] = msg.id

# --- FLASK ROUTES ---

@app.route('/', methods=['GET'])
def home(): return "Anarchy C&C Server Online."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing Parameters"})
        
        # HWID CHECK
        if hwid in database["blacklisted_hwids"]:
             return jsonify({"valid": False, "msg": "ACCESS DENIED - HARDWARE BANNED"})

        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]

        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "License Expired"})

        # Check Discord Membership
        if info.get("assigned_id"):
            g = bot.get_guild(GUILD_ID)
            if g:
                if not g.get_member(info["assigned_id"]):
                    del database["keys"][key]; save_db()
                    return jsonify({"valid": False, "msg": "Verification Failed: User not in Discord"})

        remaining = int(info["expires"] - time.time())
        d = remaining // 86400
        h = (remaining % 86400) // 3600
        left_str = f"{d}d {h}h"

        # HWID LOCKING SYSTEM (Key Satışını Önler)
        if info["hwid"] is None:
            # İlk giriş: Keyi bu bilgisayara kilitle
            info["hwid"] = hwid
            save_db()
            return jsonify({"valid": True, "msg": "Activation Successful (HWID Locked)", "left": left_str})
        elif info["hwid"] == hwid: 
            # Doğru bilgisayar
            return jsonify({"valid": True, "msg": "Login Successful", "left": left_str})
        else: 
            # Yanlış bilgisayar (Key çalınmış veya satılmış olabilir)
            return jsonify({"valid": False, "msg": "HWID Mismatch: Key is locked to another PC."})

    except Exception as e:
        return jsonify({"valid": False, "msg": "Server Error"})

@app.route('/network', methods=['POST'])
def network():
    try:
        data = request.json
        uid = str(data.get("userId"))
        job = str(data.get("jobId"))
        now = time.time()
        
        if uid in database["blacklisted_ids"]: return jsonify({"users": []})

        database["users"][uid] = {"job": job, "seen": now}
        
        toremove = [k for k,v in database["users"].items() if now - v["seen"] > 130]
        for k in toremove: del database["users"][k]
        
        users = [{"id": k, "job": v["job"]} for k,v in database["users"].items()]
        return jsonify({"users": users})
    except: return jsonify({"users": []})

@app.route('/ban', methods=['POST'])
def global_ban():
    data = request.json
    target_id = str(data.get("target_id"))
    
    if target_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(target_id)
        save_db()
    
    print(f"[ADMIN] Global Ban Executed: {target_id}")
    return jsonify({"success": True, "msg": "Target Banned"})

@app.route('/update', methods=['POST'])
def update_log():
    data = request.json
    user_id = str(data.get("user_id"))
    hwid = data.get("hwid")

    # KICK CHECK
    if user_id in database["blacklisted_ids"] or (hwid and hwid in database["blacklisted_hwids"]):
        return jsonify({"command": "KICK"}), 200

    # Discord Identity Logic
    discord_id_str = "Unlinked / Unknown"
    found_discord_id = None
    
    if hwid:
        for key, info in database["keys"].items():
            if info.get("hwid") == hwid:
                found_discord_id = info.get("assigned_id")
                break
    
    if found_discord_id:
        d_user = bot.get_user(found_discord_id)
        if d_user:
            discord_id_str = f"{d_user.name} (`{d_user.id}`)"
        else:
            discord_id_str = f"Unknown User (`{found_discord_id}`)"

    asyncio.run_coroutine_threadsafe(log_to_discord(data, user_id, "Online", discord_id_str), bot.loop)
    return jsonify({"command": "NONE"}), 200

# --- DISCORD COMMANDS ---

@bot.tree.command(name="genkey", description="Generate License")
@app_commands.describe(duration="Time (30d, 12h)", user="Target User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied.", ephemeral=True); return

    for info in database["keys"].values():
        if info.get("assigned_id") == user.id:
            await interaction.response.send_message(f"User {user.mention} already has a license.", ephemeral=True); return

    hours = parse_duration(duration)
    if not hours: await interaction.response.send_message("Invalid duration.", ephemeral=True); return

    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    database["keys"][key] = {
        "hwid": None, 
        "expires": time.time() + (hours * 3600),
        "created_at": time.time(),
        "duration_txt": duration,
        "assigned_id": user.id 
    }
    database["history"].append(user.id)
    save_db()
    
    try:
        v_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        m_role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if v_role: await user.add_roles(v_role)
        if m_role and m_role in user.roles: await user.remove_roles(m_role)
    except: pass

    await interaction.response.send_message(f"**License Generated**\nUser: {user.mention}\nKey: `{key}`\nDuration: {duration}")

@bot.tree.command(name="delkey", description="Manually revoke a license key")
@app_commands.describe(key="License Key to delete")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied.", ephemeral=True)
        return

    if key in database["keys"]:
        # Key sahibinin ID'sini al (varsa)
        user_id = database["keys"][key].get("assigned_id")
        
        # Key'i sil
        del database["keys"][key]
        save_db()
        
        msg = f"Key `{key}` has been successfully revoked."
        
        # Eğer kullanıcı sunucudaysa rolünü almayı dene (Opsiyonel)
        if user_id:
            try:
                member = interaction.guild.get_member(user_id)
                v_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
                if member and v_role:
                    await member.remove_roles(v_role)
                    msg += " (Role removed from user)"
            except: pass

        await interaction.response.send_message(msg)
    else:
        await interaction.response.send_message(f"Key `{key}` not found in database.", ephemeral=True)

@bot.tree.command(name="ban_roblox_user", description="Ban a Roblox ID Globally")
async def ban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id != ADMIN_ID: return
    if roblox_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(roblox_id)
        save_db()
        await interaction.response.send_message(f"Roblox ID `{roblox_id}` has been globally banned.")
    else:
        await interaction.response.send_message("ID already banned.")

@bot.tree.command(name="reset_user", description="Reset user history (Allow new key)")
async def reset_user(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != ADMIN_ID: return
    if user.id in database["history"]:
        database["history"].remove(user.id)
        save_db()
        await interaction.response.send_message(f"User {user.mention} reset.")
    else:
        await interaction.response.send_message("User history not found.", ephemeral=True)

@bot.tree.command(name="banhwid", description="Blacklist HWID")
async def banhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID: return
    if hwid not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` banned.")
    else: await interaction.response.send_message("HWID already banned.")

@bot.tree.command(name="unbanhwid", description="Unban HWID")
async def unbanhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID: return
    if hwid in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].remove(hwid)
        save_db()
        await interaction.response.send_message(f"HWID unbanned.")
    else: await interaction.response.send_message("HWID not found.")

@bot.tree.command(name="listkeys", description="View active licenses")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]: await interaction.response.send_message("No keys.", ephemeral=True); return
    
    lines = []
    now = time.time()
    guild = bot.get_guild(GUILD_ID)

    for key, info in list(database["keys"].items()):
        if now > info["expires"]: continue
        rem = int(info["expires"] - now)
        d = rem // 86400
        h = (rem % 86400) // 3600
        
        u_str = "Unknown"
        if info.get("assigned_id") and guild:
            m = guild.get_member(info["assigned_id"])
            u_str = f"{m.name}" if m else f"Left ({info['assigned_id']})"
        
        lines.append(f"`{key}` | User: {u_str} | Time: {d}d {h}h | HWID: {info['hwid'] or 'Pending'}")

    full = "\n".join(lines)
    if len(full) > 1900:
        f = discord.File(io.StringIO(full), filename="keys.txt")
        await interaction.response.send_message("List attached.", file=f)
    else: await interaction.response.send_message(f"**Active Licenses:**\n{full}")

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
