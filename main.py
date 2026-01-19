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

# --- AYARLAR ---
TOKEN = os.getenv("DISCORD_TOKEN") 
CHANNEL_ID = 1462815057669918821

# !!! SENIN ID'N (DOKUNULMAZ ID) !!!
ADMIN_ID = 1358830140343193821 

# !!! SUNUCU ID'SI !!!
GUILD_ID = 1460981897730592798 

# !!! VERIFIED USER ROL ID'SI !!!
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

# Veritabani Yapisı
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

# --- CIKANI KARA LISTEYE AL ---
@bot.event
async def on_member_remove(member):
    deleted_key = None
    hwid_to_ban = None
    
    # ADMIN KORUMASI: Sen cikarsan banlamaz
    if member.id == ADMIN_ID:
        print(f"Admin left the server. Bans ignored.")
        return

    # Giden kisinin keyini bul
    for key, info in list(database["keys"].items()):
        if info.get("assigned_id") == member.id:
            if info.get("hwid"):
                hwid_to_ban = info["hwid"]
            
            del database["keys"][key]
            deleted_key = key
            break     
    
    # Key silindi, simdi HWID'yi banlayalim
    if deleted_key:
        if hwid_to_ban and hwid_to_ban not in database["blacklisted_hwids"]:
            database["blacklisted_hwids"].append(hwid_to_ban)
            print(f"[AUTO-BAN] User {member.name} left. HWID {hwid_to_ban} added to blacklist.")
        
        save_db()
        print(f"[AUTO-DELETE] User {member.name} left. Key {deleted_key} deleted.")

# --- YARDIMCI FONKSIYON: DISCORD BANLAMA ---
async def ban_discord_user(user_id, reason):
    # ADMIN KORUMASI: Seni asla banlamaz
    if user_id == ADMIN_ID:
        print(f"[SHIELD] Admin ID detected. Ban prevented.")
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                await member.ban(reason=reason)
                print(f"[JUSTICE] Banned user {member.name} (ID: {user_id}) from Discord.")
            else:
                await guild.ban(discord.Object(id=user_id), reason=reason)
                print(f"[JUSTICE] Hack-Banned user ID {user_id}.")
    except Exception as e:
        print(f"Error banning user: {e}")

# --- SLASH COMMANDS ---

@bot.tree.command(name="genkey", description="Generate a key assigned to a user")
@app_commands.describe(duration="Time (e.g. 30d, 12h)", user="Select the user to assign the key")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Permission Denied.", ephemeral=True)
        return

    if user.id in database["history"]:
         await interaction.response.send_message(f"🚫 **Denied:** User {user.mention} has already used a key before!", ephemeral=True)
         return

    for info in database["keys"].values():
        if info.get("assigned_id") == user.id:
            await interaction.response.send_message(f"🚫 **Denied:** User {user.mention} already has an active key!", ephemeral=True)
            return

    hours = parse_duration(duration)
    if hours is None:
        await interaction.response.send_message("Invalid format! Use: 30d, 24h", ephemeral=True)
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
    
    role_status = ""
    try:
        role = interaction.guild.get_role(ROLE_ID)
        if role:
            await user.add_roles(role)
            role_status = " | Role Added ✅"
    except: role_status = " | Role Error ⚠️"

    await interaction.response.send_message(f"✅ Key generated for {user.mention}!\n🔑 `{key}`\n⏳ {duration}{role_status}")

@bot.tree.command(name="banhwid", description="Ban a specific HWID manually")
async def banhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Permission Denied.", ephemeral=True)
        return
        
    if hwid not in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].append(hwid)
        save_db()
        await interaction.response.send_message(f"🚫 HWID `{hwid}` has been **BANNED** permanently.")
    else:
        await interaction.response.send_message(f"HWID `{hwid}` is already banned.")

@bot.tree.command(name="unbanhwid", description="Unban a specific HWID")
async def unbanhwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("Permission Denied.", ephemeral=True)
        return

    if hwid in database["blacklisted_hwids"]:
        database["blacklisted_hwids"].remove(hwid)
        save_db()
        await interaction.response.send_message(f"✅ HWID `{hwid}` has been **UNBANNED**.")
    else:
        await interaction.response.send_message(f"❌ HWID `{hwid}` is not in the ban list.", ephemeral=True)

@bot.tree.command(name="listbanned", description="Show all banned HWIDs")
async def listbanned(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    
    if not database["blacklisted_hwids"]:
        await interaction.response.send_message("✅ No banned HWIDs.")
        return

    banned_list = "\n".join([f"`{h}`" for h in database["blacklisted_hwids"]])
    await interaction.response.send_message(f"🚫 **Banned HWIDs:**\n{banned_list}")

@bot.tree.command(name="resetuser", description="Reset history for a user")
async def resetuser(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != ADMIN_ID: return
    if user.id in database["history"]:
        database["history"].remove(user.id)
        save_db()
        await interaction.response.send_message(f"✅ User {user.mention} reset.")
    else:
        await interaction.response.send_message("User not in history.", ephemeral=True)

@bot.tree.command(name="delkey", description="Delete key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id != ADMIN_ID: return
    if key in database["keys"]:
        del database["keys"][key]
        save_db()
        await interaction.response.send_message(f"Deleted `{key}`")
    else:
        await interaction.response.send_message("Not found.", ephemeral=True)

@bot.tree.command(name="listkeys", description="List active keys")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id != ADMIN_ID: return
    if not database["keys"]:
        await interaction.response.send_message("No active keys.", ephemeral=True)
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
            user_display = f"{m.name} ({m.id})" if m else f"Left ({info['assigned_id']})"
        
        hwid_disp = info["hwid"] if info["hwid"] else "None"
        active_keys.append(f"🔑 `{key}`\n👤 {user_display}\n⏳ {days}d {hours}h {minutes}m\n💻 HWID: `{hwid_disp}`\n----------------")

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
        
        # 1. HWID BAN VE OTOMATIK KEY SILME (BURASI GÜNCELLENDI)
        if hwid in database.get("blacklisted_hwids", []):
             
             # Eger bu key veritabaninda varsa:
             if key in database["keys"]:
                 discord_user_id = database["keys"][key].get("assigned_id")
                 
                 # --- DOKUNULMAZ ID KONTROLU ---
                 if discord_user_id:
                     if discord_user_id == ADMIN_ID:
                         # Admin ise BANLAMA
                         print(f"[SHIELD] Admin tried to login with Banned HWID. Ban skipped.")
                     else:
                         # Admin degilse SUNUCUDAN BANLA
                         bot.loop.create_task(ban_discord_user(discord_user_id, reason="HWID Blacklisted Detection"))
                 
                 # --- KEY YAKMA İŞLEMİ (Herkes için geçerli) ---
                 # Keyi veritabanindan kalici olarak sil.
                 # Boylece o key bir daha asla kullanilamaz.
                 del database["keys"][key]
                 save_db()
                 print(f"[SECURITY] Banned HWID detected. Key {key} has been BURNED (Deleted).")
             
             return jsonify({"valid": False, "msg": "HWID BANNED - KEY DELETED"})

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
    except Exception as e:
        print(e)
        return jsonify({"valid": False, "msg": "Server Error"})

def run_flask(): app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.start()
    if TOKEN: bot.run(TOKEN)
