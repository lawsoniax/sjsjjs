import os
import discord
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

DB_FILE = "anarchy_db.json"
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
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

@bot.event
async def on_ready():
    print(f"Bot Ready: {bot.user}")

@bot.command()
async def genkey(ctx, hours: int = 24):
    if ctx.author.id != ADMIN_ID:
        await ctx.send("You do not have permission.")
        return

    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    database["keys"][key] = {
        "hwid": None, 
        "expires": time.time() + (hours * 3600),
        "created_at": time.time()
    }
    save_db()
    
    try:
        await ctx.author.send(f"**Key Generated:**\n`{key}`\nDuration: {hours} Hours")
        await ctx.send("Key sent to DM.")
    except:
        await ctx.send(f"DM Closed. Key: `{key}`")

@bot.command()
async def delkey(ctx, key: str):
    if ctx.author.id != ADMIN_ID: return
    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await ctx.send("Key deleted.")
    else:
        await ctx.send("Key not found.")

@app.route('/', methods=['GET'])
def home():
    return "Anarchy System Online."

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.json
        key = data.get("key")
        hwid = data.get("hwid")
        
        if not key or not hwid: return jsonify({"valid": False, "msg": "Missing data."})
        
        if key not in database["keys"]:
            return jsonify({"valid": False, "msg": "Invalid Key."})
            
        key_data = database["keys"][key]
        
        if time.time() > key_data["expires"]:
            del database["keys"][key]
            save_db()
            return jsonify({"valid": False, "msg": "Key expired."})
            
        if key_data["hwid"] is None:
            key_data["hwid"] = hwid
            save_db()
            return jsonify({"valid": True, "msg": "Key activated."})
        elif key_data["hwid"] == hwid:
            return jsonify({"valid": True, "msg": "Login successful."})
        else:
            return jsonify({"valid": False, "msg": "HWID Mismatch."})
            
    except Exception as e:
        return jsonify({"valid": False, "msg": "Server error."})

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
