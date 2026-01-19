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

# --- SETTINGS ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821

# !!! DUZENLEME GEREKLI ALANLAR !!!
ADMIN_ID = 1358830140343193821
GUILD_ID = 1460981897730592798
ROLE_ID = 1462941857922416661 

DB_FILE = "anarchy_db.json"
# ----------------

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# Data Structure
# "history": Daha once key almis kisilerin ID'lerini tutar (Kalıcı Liste)
database = {"keys": {}, "users": {}, "history": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                # Eski veritabaninda history yoksa hata vermesin diye kontrol
                if "history" not in data: data["history"] = []
                database = data
        except: database = {"keys": {}, "users": {}, "history": []}

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

# --- TIME PARSER ---
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
    print(f"Bot Logged in as: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.event
async def on_member_remove(member):
    deleted_key = None
    # Kullanici sunucudan cikarsa keyini sil ama history'den silme!
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            del database["keys"][key]
            deleted_key = key
            break
            
    if deleted_key:
        save_db()
        print(f"[AUTO-DELETE] User {member.name} left. Key {deleted_key} deleted.")

# --- SLASH COMMANDS ---

@bot.tree.command(name="genkey", description="Generate a key assigned to a user")
@app_commands.describe(duration="Time (e.g. 30d, 12h)", user="Select the user to assign the key")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return

    # 1. KONTROL: Kullanici daha once key almis mi?
    # Eger kullanici ID'si gecmiste varsa, yeni key vermeyi reddet.
    if user.id in database["history"]:
         await interaction.response.send_message(f"🚫 **Action Denied:** User {user.mention} has already received a key before!\n⚠️ *One key per user policy is active.*", ephemeral=True)
         return

    # 2. KONTROL: Mevcut aktif bir keyi var mi?
    for info in database["keys"].values():
        if info.get("assigned_id") == user.id:
            await interaction.response.send_message(f"🚫 **Action Denied:** User {user.mention} already has an active key!", ephemeral=True)
            return

    hours = parse_duration(duration)
    if hours is None:
        await interaction.response.send_message("Invalid format! Use: 30d, 24h, or 12", ephemeral=True)
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
    
    # Kullaniciyi gecmise ekle (Kara Liste mantigi)
    database["history"].append(user.id)
    save_db()
    
    # Rol Verme
    role_status = ""
    try:
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            await user.add_roles(role)
            role_status = "\n✅ **Role:** 'Verified User' added!"
        else:
            role_status = "\n⚠️ **Role Error:** Role ID not found."
    except Exception as e:
        role_status = f"\n⚠️ **Role Error:** Check bot hierarchy ({e})"

    await interaction.response.send_message(f"✅ Key generated for {user.mention}!\n🔑 **Key:** `{key}`\n⏳ **Duration:** {duration}\n⚠️ *If you leave the server, this key will be deleted permanently and you won't get a new one.*{role_status}")

# --- RESET KOMUTU (Gerekirse birine tekrar hak tanimak icin) ---
@bot.tree.command(name="resetuser", description="Allow a user to get a key again (Remove from history)")
@app_commands.describe(user="User to reset")
async def resetuser(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Permission Denied.", ephemeral=True)
        return

    if user.id in database["history"]:
        database["history"].remove(user.id)
        save_db()
        await interaction.response.send_message(f"✅ User {user.mention} has been reset. They can receive a new key now.")
    else:
        await interaction.response.send_message(f"User {user.mention} is not in the history list.", ephemeral=True)

@bot.tree.command(name="delkey", description="Delete an existing key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID: return
    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await interaction.response.send_message(f"Key `{key}` deleted.")
    else:
        await interaction.response.send_message("Key not found.", ephemeral=True)

@bot.tree.command(name="listkeys", description="Show all active keys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]:
        await interaction.response.send_message("❌ No active keys.", ephemeral=True)
        return

    active_keys = []
    now = time.time()
    guild = bot.get_guild(GUILD_ID)

    for key, info in list(database["keys"].items()):
        if now > info["expires"]: continue
        remaining = int(info["expires"] - now)
        days = remaining // 86400
        hours = (remaining % 86400) // 3600
        
        user_display = "Unknown"
        if info.get("assigned_id") and guild:
            m = guild.get_member(info["assigned_id"])
            user_display = f"{m.name} ({m.id})" if m else f"Left ({info['assigned_id']})"

        active_keys.append(f"🔑 `{key}` | 👤 {user_display} | ⏳ {days}d {hours}h")

    full_text = "\n".join(active_keys)
    if len(full_text) > 1900:
        file = discord.File(io.StringIO(full_text), filename="keys.txt")
        await interaction.response.send_message("📂 List too long:", file=file)
    else:
        await interaction.response.send_message(f"**Active Keys:**\n{full_text}")

# --- ROBLOX API ---
@app.route('/', methods=['GET'])
def home(): return "Anarchy System Online."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing Data"})
        if key not in database["keys"]: return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        if time.time() > info["expires"]:
            del database["keys"][key]; save_db()
            return jsonify({"valid": False, "msg": "Key Expired"})

        if info.get("assigned_id"):
            g = bot.get_guild(GUILD_ID)
            if g:
                if not g.get_member(info["assigned_id"]):
                    del database["keys"][key]; save_db()
                    return jsonify({"valid": False, "msg": "Left Discord - Key Deleted"})
            else: return jsonify({"valid": False, "msg": "Server Auth Error"})

        if info["hwid"] is None:
            info["hwid"] = hwid; save_db()
            return jsonify({"valid": True, "msg": "Activated"})
        elif info["hwid"] == hwid: return jsonify({"valid": True, "msg": "Login Success"})
        else: return jsonify({"valid": False, "msg": "HWID Mismatch"})
    except: return jsonify({"valid": False, "msg": "Error"})

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
