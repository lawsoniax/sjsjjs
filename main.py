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

# --- AYARLAR ---
# Token'i kodun icine YAZMIYORUZ. Render ayarlarindan cekecek.
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821
ADMIN_ID = 1234567890 # BURAYA KENDI DISCORD ID'NI SAYI OLARAK YAZ (Tirnak isareti olmadan)
DB_FILE = "anarchy_db.json"
# ----------------

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

# Veri Yapısı: { "keys": {}, "users": {} }
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

# --- DISCORD BOT KOMUTLARI ---
@bot.event
async def on_ready():
    print(f"Bot Hazır: {bot.user}")

@bot.command()
async def genkey(ctx, hours: int = 24):
    # Yetki Kontrolü
    if ctx.author.id != ADMIN_ID:
        await ctx.send("❌ Yetkin yok!")
        return

    # Rastgele Key Üret
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    # Veritabanına Ekle
    database["keys"][key] = {
        "hwid": None, 
        "expires": time.time() + (hours * 3600),
        "created_at": time.time()
    }
    save_db()
    
    # DM Gönder
    try:
        await ctx.author.send(f"🔑 **Key Oluşturuldu!**\n`{key}`\n⏳ Süre: {hours} Saat")
        await ctx.send(f"✅ Key DM olarak gönderildi.")
    except:
        await ctx.send(f"❌ DM Kapalı! Key: `{key}`")

@bot.command()
async def delkey(ctx, key: str):
    if ctx.author.id != ADMIN_ID: return
    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await ctx.send("🗑️ Key silindi.")
    else:
        await ctx.send("❌ Key bulunamadı.")

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
        
        if not key or not hwid: return jsonify({"valid": False, "msg": "Eksik veri!"})
        
        if key not in database["keys"]:
            return jsonify({"valid": False, "msg": "Geçersiz Key!"})
            
        key_data = database["keys"][key]
        
        if time.time() > key_data["expires"]:
            del database["keys"][key]
            save_db()
            return jsonify({"valid": False, "msg": "Key süresi dolmuş!"})
            
        if key_data["hwid"] is None:
            key_data["hwid"] = hwid
            save_db()
            return jsonify({"valid": True, "msg": "Key aktif edildi!"})
        elif key_data["hwid"] == hwid:
            return jsonify({"valid": True, "msg": "Giriş başarılı."})
        else:
            return jsonify({"valid": False, "msg": "HWID Uyuşmazlığı!"})
            
    except Exception as e:
        return jsonify({"valid": False, "msg": "Sunucu hatası."})

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