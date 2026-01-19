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

TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821

ADMIN_ID = 1358830140343193821

GUILD_ID = 1460981897730592798

DB_FILE = "anarchy_db.json"

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

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
    print(f"Bot Logged in as: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@bot.tree.command(name="genkey", description="Generate a key assigned to a user")
@app_commands.describe(duration="Time (e.g. 30d, 12h)", user="Select the user to assign the key")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
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
    save_db()
    
    await interaction.response.send_message(f"✅ Key generated for {user.mention}!\n🔑 **Key:** `{key}`\n⏳ **Duration:** {duration}\n⚠️ *You must remain in the Discord server to use this key.*")

@bot.tree.command(name="delkey", description="Delete an existing key")
@app_commands.describe(key="The key to delete")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return

    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await interaction.response.send_message(f"Key `{key}` has been deleted.")
    else:
        await interaction.response.send_message("Key not found.", ephemeral=True)

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
            
        assigned_id = key_data.get("assigned_id")
        if assigned_id:
            guild = bot.get_guild(GUILD_ID)
            if guild:
                member = guild.get_member(assigned_id)
                if not member:
                    return jsonify({"valid": False, "msg": "You must be in the Discord Server!"})
            else:
                return jsonify({"valid": False, "msg": "Server Auth Error"})

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


