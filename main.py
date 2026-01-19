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

# --- SETTINGS ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821

# !!! IMPORTANT: PUT YOUR DISCORD ID HERE !!!
ADMIN_ID = 1358830140343193821 

DB_FILE = "anarchy_db.json"
# ----------------

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Setup Bot with Slash Command Support
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# Data Structure
database = {"keys": {}, "users": {}}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: database = json.load(f)
        except: database = {"keys": {}, "users": {}}

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

# --- TIME PARSER HELPER ---
def parse_duration(duration_str: str):
    """Converts 1d -> 24, 1h -> 1, 30 -> 30"""
    duration_str = duration_str.lower()
    try:
        if duration_str.endswith("d"):
            days = int(duration_str.replace("d", ""))
            return days * 24
        elif duration_str.endswith("h"):
            return int(duration_str.replace("h", ""))
        else:
            return int(duration_str) # Default to hours if no letter
    except:
        return None

# --- BOT EVENTS ---
@bot.event
async def on_ready():
    print(f"Bot Logged in as: {bot.user}")
    try:
        # Sync Slash Commands with Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# --- SLASH COMMANDS ---

@bot.tree.command(name="genkey", description="Generate a license key (e.g. 1d, 12h, 30)")
@app_commands.describe(duration="Duration: use 'd' for days, 'h' for hours (Example: 7d)")
async def genkey(interaction: discord.Interaction, duration: str):
    # 1. Permission Check
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return

    # 2. Parse Duration (14d -> Hours)
    hours = parse_duration(duration)
    if hours is None:
        await interaction.response.send_message("Invalid format! Use: 1d, 24h, or 12", ephemeral=True)
        return

    # 3. Generate Key
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    # 4. Save to Database
    database["keys"][key] = {
        "hwid": None, 
        "expires": time.time() + (hours * 3600),
        "created_at": time.time(),
        "duration_txt": duration # Store original text for display
    }
    save_db()
    
    # 5. Send Response (Public Message)
    await interaction.response.send_message(f"**Key Generated:**\n`{key}`\nDuration: {duration} ({hours} Hours)")

@bot.tree.command(name="delkey", description="Delete an existing key")
@app_commands.describe(key="The key to delete")
async def delkey(interaction: discord.Interaction, key: str):
    # Permission Check
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return

    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await interaction.response.send_message(f"Key `{key}` has been deleted.")
    else:
        await interaction.response.send_message("Key not found in database.", ephemeral=True)

# --- ROBLOX API ---
@app.route('/', methods=['GET'])
def home():
    return "Anarchy System Online."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing Data"})
        
        if key not in database["keys"]:
            return jsonify({"valid": False, "msg": "Invalid Key"})
            
        key_data = database["keys"][key]
        
        if time.time() > key_data["expires"]:
            del database["keys"][key]
            save_db()
            return jsonify({"valid": False, "msg": "Key Expired"})
            
        if key_data["hwid"] is None:
            key_data["hwid"] = hwid
            save_db()
            return jsonify({"valid": True, "msg": "Key Activated"})
        elif key_data["hwid"] == hwid:
            return jsonify({"valid": True, "msg": "Login Successful"})
        else:
            return jsonify({"valid": False, "msg": "HWID Mismatch"})
            
    except Exception as e:
        return jsonify({"valid": False, "msg": "Server Error"})

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

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN:
        try: bot.run(TOKEN)
        except: pass
