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

# --- SYSTEM CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1358830140343193821 
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

# --- INITIALIZATION ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

user_sessions = {}

# Database Schema
database = {
    "keys": {}, 
    "users": {}, 
    "history": [], 
    "blacklisted_hwids": [], 
    "blacklisted_ids": [] 
}

# --- DATABASE MANAGEMENT ---
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
                print("Database loaded successfully.")
        except Exception as e: 
            print(f"Database load error: {e}")

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

def parse_duration(duration_str: str):
    duration_str = duration_str.lower()
    try:
        if duration_str.endswith("d"):
            days = int(duration_str.replace("d", ""))
            return days * 24
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
    if member.id == ADMIN_ID: return

    deleted_key = None
    hwid_to_ban = None
    
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            if info.get("hwid"):
                hwid_to_ban = info["hwid"]
            
            del database["keys"][key]
            deleted_key = key
            break      
    
    if deleted_key:
        if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
            database["blacklisted_hwids"].append(hwid_to_ban)
            print(f"[AUTO-SECURITY] User {member.name} left. HWID Blacklisted.")
        
        save_db()
        print(f"[AUTO-SECURITY] Key revoked for {member.name}.")

async def ban_discord_user(user_id, reason="Security Violation"):
    if user_id == ADMIN_ID: return

    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                await member.ban(reason=reason)
            else:
                await guild.ban(discord.Object(id=user_id), reason=reason)
    except Exception as e:
        print(f"Ban Execution Error: {e}")

async def log_to_discord(data, user_id, status, discord_info):
    await bot.wait_until_ready()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel: return

    status_color = 0x2ECC71 if status == "Online" else 0xE74C3C
    
    embed = discord.Embed(title=f"System Monitor: {status}", color=status_color)
    
    profile_url = f"https://www.roblox.com/users/{user_id}/profile"
    
    # Data Extraction
    roblox_display = data.get('display_name', 'Unknown')
    roblox_username = data.get('username', 'Unknown')
    game = data.get('game', 'Unknown')
    server_plrs = data.get('server_players', '?/?')
    job = data.get('job_id', 'Unknown')
    executor = data.get('executor', 'Unknown')
    
    # 1. Identity Section (Discord & Roblox)
    embed.add_field(
        name="User Identification", 
        value=f"**Discord:** {discord_info}\n**Roblox:** [{roblox_display}]({profile_url}) (@{roblox_username})\n**ID:** `{user_id}`", 
        inline=False
    )
    
    # 2. Session Data
    embed.add_field(
        name="Session Details", 
        value=f"**Game:** {game}\n**Server:** {server_plrs} Players\n**Job ID:** `{job}`", 
        inline=False
    )

    # 3. Technical Data
    embed.add_field(
        name="Technical Specs", 
        value=f"**Executor:** {executor}\n**Ping:** {data.get('ping', 0)}ms | **FPS:** {data.get('fps', 0)}", 
        inline=False
    )

    thumb_url = f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=420&height=420&format=png"
    embed.set_thumbnail(url=thumb_url)
    
    time_str = datetime.datetime.now().strftime('%H:%M:%S')
    footer_text = f"Anarchy Security Systems • {time_str}"
    if status == "Offline":
        footer_text = f"Connection Terminated at {time_str}"
        
    embed.set_footer(text=footer_text)

    # Update or Send New
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

# --- FLASK ENDPOINTS ---

@app.route('/', methods=['GET'])
def home(): return "Anarchy C&C Server Running."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing Parameters"})
        
        if hwid in database["blacklisted_hwids"]:
             return jsonify({"valid": False, "msg": "ACCESS DENIED - HARDWARE BANNED"})

        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid License"})
        
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
                    return jsonify({"valid": False, "msg": "Verification Failed: Discord Account Not Found"})

        remaining = int(info["expires"] - time.time())
        d = remaining // 86400
        h = (remaining % 86400) // 3600
        left_str = f"{d}d {h}h"

        if info["hwid"] is None:
            info["hwid"] = hwid; save_db()
            return jsonify({"valid": True, "msg": "Activation Successful", "left": left_str})
        elif info["hwid"] == hwid: 
            return jsonify({"valid": True, "msg": "Login Successful", "left": left_str})
        else: return jsonify({"valid": False, "msg": "HWID Mismatch"})

    except Exception as e:
        print(e)
        return jsonify({"valid": False, "msg": "Server Error"})

@app.route('/network', methods=['POST'])
def network():
    try:
        data = request.json
        uid = str(data.get("userId"))
        job = str(data.get("jobId"))
        now = time.time()
        
        if uid in database["blacklisted_ids"]:
            return jsonify({"users": []})

        database["users"][uid] = {"job": job, "seen": now}
        
        toremove = [k for k,v in database["users"].items() if now - v["seen"] > 130]
        for k in toremove: del database["users"][k]
        
        users = [{"id": k, "job": v["job"]} for k,v in database["users"].items()]
        return jsonify({"users": users})
    except:
        return jsonify({"users": []})

@app.route('/ban', methods=['POST'])
def global_ban():
    data = request.json
    target_id = str(data.get("target_id"))
    reason = data.get("reason", "Global Ban Executed")
    
    if target_id not in database["blacklisted_ids"]:
        database["blacklisted_ids"].append(target_id)
        save_db()
    
    # Try to find associated Discord user to ban them
    discord_target = None
    # We scan keys to find who owns this HWID/Roblox ID if possible
    # (Simplified logic: ban request usually comes with Roblox ID)
    
    print(f"[ADMIN] Global Ban issued for Roblox ID: {target_id}")
    return jsonify({"success": True, "msg": "Target Banned"})

@app.route('/update', methods=['POST'])
def update_log():
    data = request.json
    user_id = str(data.get("user_id"))
    hwid = data.get("hwid")

    # KICK CHECK
    if user_id in database["blacklisted_ids"] or (hwid and hwid in database["blacklisted_hwids"]):
        return jsonify({"command": "KICK"}), 200

    # DISCORD USERNAME FINDER
    discord_identity = "Unlinked / Unknown"
    
    # HWID üzerinden Key'i ve Discord ID'yi bul
    found_discord_id = None
    if hwid:
        for key, info in database["keys"].items():
            if info.get("hwid") == hwid:
                found_discord_id = info.get("assigned_id")
                break
    
    if found_discord_id:
        # Bot cache'inden kullanıcıyı bul
        d_user = bot.get_user(found_discord_id)
        if d_user:
            discord_identity = f"{d_user.name} (`{d_user.id}`)"
        else:
            discord_identity = f"Unknown ID (`{found_discord_id}`)"

    asyncio.run_coroutine_threadsafe(log_to_discord(data, user_id, "Online", discord_identity), bot.loop)
    return jsonify({"command": "NONE"}), 200

# --- SLASH COMMANDS ---

@bot.tree.command(name="genkey", description="Create a new license")
@app_commands.describe(duration="Time (e.g. 30d, 12h)", user="Discord User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied.", ephemeral=True)
        return

    for info in database["keys"].values():
        if info.get("assigned_id") == user.id:
            await interaction.response.send_message(f"User {user.mention} already holds an active license.", ephemeral=True)
            return

    hours = parse_duration(duration)
    if not hours:
        await interaction.response.send_message("Invalid duration format.", ephemeral=True)
        return

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

@bot.tree.command(name="banhwid", description="Blacklist HWID")
async def banhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID: return
    if hwid not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` added to blacklist.")
    else:
        await interaction.response.send_message("HWID is already blacklisted.")

@bot.tree.command(name="unbanhwid", description="Remove HWID from blacklist")
async def unbanhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID: return
    if hwid in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].remove(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` removed from blacklist.")
    else:
        await interaction.response.send_message("HWID not found.")

@bot.tree.command(name="listkeys", description="View active licenses")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]:
        await interaction.response.send_message("No active licenses found.", ephemeral=True)
        return
    
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
            u_str = f"{m.name} ({m.id})" if m else f"Left ({info['assigned_id']})"
        
        lines.append(f"`{key}`\nUser: {u_str}\nTime: {d}d {h}h\nHWID: {info['hwid'] or 'Pending'}\n")

    full = "\n".join(lines)
    if len(full) > 1900:
        f = discord.File(io.StringIO(full), filename="keys.txt")
        await interaction.response.send_message("List attached.", file=f)
    else:
        await interaction.response.send_message(f"**Active Licenses:**\n\n{full}")

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
