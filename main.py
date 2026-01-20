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
                # Ensure schema integrity
                for k in ["keys", "users", "history", "blacklisted_hwids", "blacklisted_ids"]:
                    if k not in data: data[k] = [] if "list" in k else {}
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
            print(f"[SECURITY] Member {member.name} left. HWID Blacklisted.")
        
        save_db()
        print(f"[SECURITY] License revoked for {member.name}.")

        try:
            await member.ban(reason="Anarchy Security: Left server while holding a license.")
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
        
        # 1. HWID Blacklist Check
        if hwid in database["blacklisted_hwids"]:
             return jsonify({"valid": False, "msg": "ACCESS DENIED - HARDWARE BANNED"})

        # 2. Key Check
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]

        # 3. Expiry Check
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "License Expired"})

        # 4. Claim Check (New System)
        if info.get("assigned_id") is None:
            return jsonify({"valid": False, "msg": "UNCLAIMED KEY\nGo to Discord and type:\n/redeem " + key})

        # 5. Discord Membership Check
        g = bot.get_guild(GUILD_ID)
        if g and not g.get_member(info["assigned_id"]):
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Verification Failed: User not in Discord"})

        remaining = int(info["expires"] - time.time())
        d = remaining // 86400
        h = (remaining % 86400) // 3600
        left_str = f"{d}d {h}h"

        # 6. AUTO-LOGIN & OTP SYSTEM
        if info["hwid"] == hwid: 
            # KNOWN DEVICE -> AUTO LOGIN
            return jsonify({"valid": True, "msg": "Welcome Back", "left": left_str})
            
        elif info["hwid"] is None:
            # NEW DEVICE -> REQUIRE OTP
            if "otp" not in info:
                info["otp"] = str(random.randint(10000, 99999))
                info["temp_hwid"] = hwid
                save_db()
            
            return jsonify({
                "valid": False, 
                "msg": "OTP_REQUIRED", 
                "code": info["otp"]
            })
            
        else: 
            return jsonify({"valid": False, "msg": "HWID Mismatch: Key locked to another device."})

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

@bot.tree.command(name="genkey", description="Create Unclaimed License")
@app_commands.describe(duration="30d, 12h", user="Optional: Pre-assign")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member = None):
    if interaction.user.id != ADMIN_ID: await interaction.response.send_message("Access Denied.", ephemeral=True); return
    
    h = parse_duration(duration)
    if not h: await interaction.response.send_message("Invalid Format.", ephemeral=True); return
    
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    assigned = user.id if user else None
    
    database["keys"][key] = {
        "hwid": None, 
        "expires": time.time() + (h * 3600),
        "created_at": time.time(),
        "duration_txt": duration,
        "assigned_id": assigned
    }
    save_db()
    
    msg = f"**License Generated**\nKey: `{key}`\nDuration: {duration}"
    if assigned: msg += f"\nAssigned to: {user.mention}"
    else: msg += "\n**Status:** Unclaimed (User must type `/redeem {key}`)"
    
    await interaction.response.send_message(msg)

@bot.tree.command(name="redeem", description="Claim a license key to your account")
async def redeem(interaction: discord.Interaction, key: str):
    if key not in database["keys"]:
        await interaction.response.send_message("Invalid Key.", ephemeral=True); return
    
    info = database["keys"][key]
    
    if info.get("assigned_id") is not None:
        await interaction.response.send_message("This key is already claimed.", ephemeral=True); return

    # 1 User = 1 Key Rule
    for k, v in database["keys"].items():
        if v.get("assigned_id") == interaction.user.id:
            await interaction.response.send_message("You already have an active license.", ephemeral=True); return
        
    info["assigned_id"] = interaction.user.id
    save_db()
    
    try:
        r = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if r: await interaction.user.add_roles(r)
    except: pass
    
    await interaction.response.send_message(f"✅ **Success!** Key `{key}` is now linked to your account.\nYou can now login in the script.", ephemeral=True)

@bot.tree.command(name="activate", description="Verify Login OTP")
async def activate(interaction: discord.Interaction, code: str):
    for key, info in database["keys"].items():
        if info.get("otp") == code:
            if info.get("assigned_id") == interaction.user.id:
                info["hwid"] = info["temp_hwid"]
                del info["otp"]
                del info["temp_hwid"]
                save_db()
                await interaction.response.send_message("✅ **Device Verified!** You can login now.", ephemeral=True)
                return
            else:
                await interaction.response.send_message("❌ Access Denied. You do not own this key.", ephemeral=True); return
    await interaction.response.send_message("❌ Invalid Code.", ephemeral=True)

@bot.tree.command(name="delkey", description="Admin: Revoke Key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID: return
    if key in database["keys"]:
        user_id = database["keys"][key].get("assigned_id")
        del database["keys"][key]
        save_db()
        msg = f"Key `{key}` revoked."
        if user_id:
            try:
                m = interaction.guild.get_member(user_id)
                r = interaction.guild.get_role(VERIFIED_ROLE_ID)
                if m and r: await m.remove_roles(r); msg += " (Role removed)"
            except: pass
        await interaction.response.send_message(msg)
    else: await interaction.response.send_message("Not found.")

@bot.tree.command(name="reset_hwid", description="Admin: Reset HWID")
async def reset_hwid(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != ADMIN_ID: return
    for k, v in database["keys"].items():
        if v.get("assigned_id") == user.id:
            v["hwid"] = None; save_db()
            await interaction.response.send_message(f"Reset HWID for {user.mention}. They must verify again.")
            return
    await interaction.response.send_message("User has no key.")

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
        u = "Unclaimed"
        if v.get("assigned_id"):
            m = g.get_member(v["assigned_id"])
            u = f"{m.name} ({m.id})" if m else f"Left ({v['assigned_id']})"
        
        lines.append(f"`{k}` | {u} | {v.get('duration_txt')}")

    f = discord.File(io.StringIO("\n".join(lines)), filename="keys.txt")
    await interaction.response.send_message("Active License List:", file=f)

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
