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

TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1358830140343193821 
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478
DB_FILE = "anarchy_db.json"

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

database = {"keys": {}, "users": {}, "history": [], "blacklisted_hwids": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                if "history" not in data: data["history"] = []
                if "blacklisted_hwids" not in data: data["blacklisted_hwids"] = []
                database = data
        except: database = {"keys": {}, "users": {}, "history": [], "blacklisted_hwids": []}

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
    deleted_key = None
    hwid_to_ban = None
    
    if member.id == ADMIN_ID:
        print(f"Administrator left. Actions bypassed.")
        return

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
            print(f"[System] User {member.name} left. HWID {hwid_to_ban} blacklisted.")
        
        save_db()
        print(f"[System] User {member.name} left. Key {deleted_key} revoked.")

async def ban_discord_user(user_id, reason):
    if user_id == ADMIN_ID:
        print(f"[System] Administrator detected. Ban prevented.")
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                await member.ban(reason=reason)
                print(f"[System] Banned user {member.name} (ID: {user_id}).")
            else:
                await guild.ban(discord.Object(id=user_id), reason=reason)
                print(f"[System] ID Banned: {user_id}.")
    except Exception as e:
        print(f"Ban Error: {e}")

@bot.tree.command(name="genkey", description="Generate a license key for a user")
@app_commands.describe(duration="Duration (e.g., 30d, 12h)", user="Target User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied: Insufficient permissions.", ephemeral=True)
        return

    if user.id in database["history"]:
         await interaction.response.send_message(f"Action Denied: User {user.mention} has already generated a key.", ephemeral=True)
         return

    for info in database["keys"].values():
        if info.get("assigned_id") == user.id:
            await interaction.response.send_message(f"Action Denied: User {user.mention} already has an active key.", ephemeral=True)
            return

    hours = parse_duration(duration)
    if hours is None:
        await interaction.response.send_message("Format Error: Use format like '30d' or '24h'.", ephemeral=True)
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
        verified_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)

        if verified_role:
            await user.add_roles(verified_role)
        
        if member_role and member_role in user.roles:
            await user.remove_roles(member_role)
    except Exception as e:
        print(f"Role Update Error: {e}")

    await interaction.response.send_message(f"**License Generated Successfully**\n\n**User:** {user.mention}\n**Key:** `{key}`\n**Duration:** {duration}")

@bot.tree.command(name="banhwid", description="Manually blacklist a Hardware ID")
async def banhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied.", ephemeral=True)
        return
        
    if hwid not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` has been permanently blacklisted.")
    else:
        await interaction.response.send_message(f"HWID `{hwid}` is already on the blacklist.")

@bot.tree.command(name="unbanhwid", description="Remove a Hardware ID from blacklist")
async def unbanhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Access Denied.", ephemeral=True)
        return

    if hwid in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].remove(hwid)
        save_db()
        await interaction.response.send_message(f"HWID `{hwid}` has been removed from the blacklist.")
    else:
        await interaction.response.send_message(f"HWID `{hwid}` was not found in the blacklist.", ephemeral=True)

@bot.tree.command(name="listbanned", description="Display all blacklisted HWIDs")
async def listbanned(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    
    if not database["blacklisted_hwids"]:
        await interaction.response.send_message("Blacklist is empty.")
        return

    banned_list = "\n".join([f"`{h}`" for h in database["blacklisted_hwids"]])
    await interaction.response.send_message(f"**Blacklisted HWIDs:**\n{banned_list}")

@bot.tree.command(name="resetuser", description="Reset user history to allow new key generation")
async def resetuser(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != ADMIN_ID: return
    if user.id in database["history"]:
        database["history"].remove(user.id)
        save_db()
        await interaction.response.send_message(f"User {user.mention} history has been reset.")
    else:
        await interaction.response.send_message("User not found in history.", ephemeral=True)

@bot.tree.command(name="delkey", description="Revoke an existing key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID: return
    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await interaction.response.send_message(f"Key `{key}` has been revoked.")
    else:
        await interaction.response.send_message("Key not found.", ephemeral=True)

@bot.tree.command(name="listkeys", description="List all active keys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]:
        await interaction.response.send_message("No active keys found.", ephemeral=True)
        return
    
    active_keys = []
    now = time.time()
    guild = bot.get_guild(GUILD_ID)

    for key, info in list(database["keys"].items()):
        if now > info["expires"]: continue
        remaining = int(info["expires"] - now)
        days = remaining // 86400
        hours = (remaining % 86400) // 3600
        minutes = (remaining % 3600) // 60
        
        user_display = "Unknown"
        if info.get("assigned_id") and guild:
            m = guild.get_member(info["assigned_id"])
            user_display = f"{m.name} ({m.id})" if m else f"User Left ({info['assigned_id']})"
        
        hwid_disp = info["hwid"] if info["hwid"] else "Not Linked"
        active_keys.append(f"**Key:** `{key}`\n**User:** {user_display}\n**Time Remaining:** {days}d {hours}h {minutes}m\n**HWID:** `{hwid_disp}`\n----------------")

    full_text = "\n".join(active_keys)
    if len(full_text) > 1900:
        file = discord.File(io.StringIO(full_text), filename="keys.txt")
        await interaction.response.send_message("Output too long. Sending as file.", file=file)
    else:
        await interaction.response.send_message(f"**Active License Keys:**\n\n{full_text}")

@app.route('/', methods=['GET'])
def home(): return "Anarchy System Online."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing Data"})
        
        if hwid in database.get("blacklisted_hwids", []):
             if key in database["keys"]:
                 discord_user_id = database["keys"][key].get("assigned_id")
                 
                 if discord_user_id:
                     if discord_user_id == ADMIN_ID:
                         print(f"[System] Admin bypass active on blacklisted HWID.")
                     else:
                         bot.loop.create_task(ban_discord_user(discord_user_id, reason="Security: Blacklisted HWID Detected"))
                 
                 del database["keys"][key]
                 save_db()
                 print(f"[System] Security Violation: Key {key} revoked.")
             
             return jsonify({"valid": False, "msg": "ACCESS DENIED - HARDWARE BANNED"})

        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "License Expired"})

        if info.get("assigned_id"):
            g = bot.get_guild(GUILD_ID)
            if g:
                if not g.get_member(info["assigned_id"]):
                    del database["keys"][key]; save_db()
                    return jsonify({"valid": False, "msg": "Authentication Failed: User not in Discord"})
            else: return jsonify({"valid": False, "msg": "Server Error"})

        # Calculate time left
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
        return jsonify({"valid": False, "msg": "Internal Server Error"})

@app.route('/network', methods=['POST'])
def network():
    try:
        data = request.json
        uid = str(data.get("userId"))
        job = str(data.get("jobId"))
        now = time.time()
        
        database["users"][uid] = {"job": job, "seen": now}
        
        toremove = [k for k,v in database["users"].items() if now - v["seen"] > 60]
        for k in toremove: del database["users"][k]
        
        users = [{"id": k, "job": v["job"]} for k,v in database["users"].items()]
        return jsonify({"users": users})
    except:
        return jsonify({"users": []})

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
