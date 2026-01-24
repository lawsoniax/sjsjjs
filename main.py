import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
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
import requests
import firebase_admin
from firebase_admin import credentials, firestore

TOKEN = os.getenv("DISCORD_TOKEN")
firebase_config = os.getenv("FIREBASE_CREDENTIALS")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") 

CHANNEL_ID = 1462815057669918821
ADMIN_IDS = [1358830140343193821, 1039946239938142218, 561405817744654366, 503944284563701765]
GUILD_ID = 1460981897730592798 
VERIFIED_ROLE_ID = 1462941857922416661
MEMBER_ROLE_ID = 1461016842582757478

if not firebase_config:
    print("Error: FIREBASE_CREDENTIALS not found in environment variables.")
else:
    try:
        cred = credentials.Certificate(json.loads(firebase_config))
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase Connected Successfully.")
    except Exception as e:
        print(f"Firebase Connection Error: {e}")

log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default(); intents.message_content = True; intents.members = True 
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "60 per hour"],
    storage_uri="memory://"
)

online_users = {}
user_sessions = {}
log_cooldowns = {}
webhook_spam_map = {} 

def parse_duration(s):
    s = s.lower()
    try: 
        if "d" in s: return int(s.replace("d",""))*24
        elif "h" in s: return int(s.replace("h",""))
        else: return int(s)
    except: return None

async def send_dm_code(user_id, code):
    if user_id == 0: return False 
    try:
        user = await bot.fetch_user(user_id)
        if user:
            embed = discord.Embed(title="Login Verification", color=0x2C3E50)
            embed.description = f"A new device is attempting to access the script.\n\n**Authorization Code:** `{code}`\n\nPlease enter this code in the Roblox execution window."
            embed.set_footer(text="Security Alert: Do not share this code.")
            await user.send(embed=embed)
            return True
    except Exception as e:
        print(f"DM Failed: {e}")
        return False

async def kick_discord_user(user_id, reason):
    if user_id == 0: return 
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(user_id)
            if member:
                try: await member.send(f"**Notice of Termination**\nYou have been banned from Anarchy.\nReason: {reason}")
                except: pass
                await member.kick(reason=reason)
    except Exception as e:
        print(f"Kick Error: {e}")

def get_key_data(key):
    doc = db.collection('keys').document(key).get()
    if doc.exists:
        return doc.to_dict()
    return None

def update_key_data(key, data):
    db.collection('keys').document(key).update(data)

def delete_key_data(key):
    db.collection('keys').document(key).delete()

def is_hwid_banned(hwid):
    if not hwid: return False
    docs = db.collection('blacklist_hwids').where('hwid', '==', hwid).stream()
    return any(docs)

def ban_hwid_db(hwid):
    if not hwid: return
    db.collection('blacklist_hwids').document(hwid).set({'hwid': hwid, 'banned_at': time.time()})

def unban_hwid_db(hwid):
    db.collection('blacklist_hwids').document(hwid).delete()

def is_roblox_banned(rid):
    doc = db.collection('blacklist_roblox').document(str(rid)).get()
    return doc.exists

def ban_roblox_db(rid):
    db.collection('blacklist_roblox').document(str(rid)).set({'id': str(rid), 'banned_at': time.time()})

def unban_roblox_db(rid):
    db.collection('blacklist_roblox').document(str(rid)).delete()

@bot.event
async def on_ready():
    print(f"System Online: {bot.user}")
    try: await bot.tree.sync()
    except: pass

@bot.event
async def on_member_remove(member):
    if member.id in ADMIN_IDS: return

    keys_ref = db.collection('keys')
    query = keys_ref.where('assigned_id', '==', member.id).stream()

    found_key = False
    for doc in query:
        key_data = doc.to_dict()
        key_id = doc.id
        
        if key_data.get('hwid'):
            ban_hwid_db(key_data['hwid'])
        
        delete_key_data(key_id)
        found_key = True

async def log_discord(data, uid, status, d_id):
    await bot.wait_until_ready(); c = bot.get_channel(CHANNEL_ID)
    if not c: return
    
    hwid = data.get('hwid')
    rbx_name = f"{data.get('display_name')} (@{data.get('username')})"
    
    if hwid:
        docs = db.collection('keys').where('hwid', '==', hwid).stream()
        for doc in docs:
            update_key_data(doc.id, {"last_roblox_name": rbx_name})

    embed = discord.Embed(title=f"Session Monitor: {status}", color=0x3498DB if status=="Online" else 0xE74C3C)
    embed.add_field(name="User Identity", value=f"**Discord:** {d_id}\n**Roblox:** {rbx_name}")
    embed.add_field(name="Session Data", value=f"Game ID: {data.get('game')}\nPerformance: {data.get('fps')} FPS")
    embed.set_footer(text=f"System Time: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    mid = user_sessions.get(uid, {}).get('msg_id')
    if mid: 
        try: msg = await c.fetch_message(mid); await msg.edit(embed=embed); return
        except: pass
    m = await c.send(embed=embed)
    if uid not in user_sessions: user_sessions[uid]={}
    user_sessions[uid]['msg_id'] = m.id

@app.route('/', methods=['GET'])
def home(): return "Anarchy Firebase System Operational"

@app.route('/webhook_proxy', methods=['POST'])
def webhook_proxy():
    try:
        user_key = request.headers.get('User-Agent')
        data = request.json

        if not user_key or user_key == "Roblox/Linux": 
            return jsonify({"error": "Auth Required"}), 403

        doc_ref = db.collection('keys').document(user_key)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({"error": "Invalid License Key"}), 403

        current_time = time.time()
        if user_key in webhook_spam_map:
            last_request_time = webhook_spam_map[user_key]
            if current_time - last_request_time < 2.0:
                print(f"[SPAM DETECTED] Key: {user_key} is spamming webhooks. BANNING.")
                
                key_data = doc.to_dict()
                if key_data.get('hwid'):
                    ban_hwid_db(key_data['hwid'])
                
                doc_ref.delete()
                
                del webhook_spam_map[user_key]
                return jsonify({"error": "Spam Detected - License Revoked"}), 429

        webhook_spam_map[user_key] = current_time

        if not WEBHOOK_URL:
            return jsonify({"error": "Server Config Error"}), 500

        discord_headers = {"Content-Type": "application/json"}
        response = requests.post(WEBHOOK_URL, json=data, headers=discord_headers)
        
        return jsonify({"status": "sent", "code": response.status_code})

    except Exception as e:
        print(f"Proxy Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_webhook', methods=['GET'])
def get_webhook_url():
    return jsonify({"url": ""})

@app.route('/verify', methods=['POST'])
@limiter.limit("10 per minute")
def verify():
    try:
        data = request.json
        key = data.get("key"); hwid = data.get("hwid")
        username = data.get("username")
        display_name = data.get("display_name")
        
        if is_hwid_banned(hwid): return jsonify({"valid": False, "msg": "Access Denied: HWID Banned"})
        
        info = get_key_data(key)
        if not info: return jsonify({"valid": False, "msg": "Invalid License Key"})
        
        if username and display_name:
            update_key_data(key, {"last_roblox_name": f"{display_name} (@{username})"})

        if time.time() > info["expires"]:
            delete_key_data(key)
            return jsonify({"valid": False, "msg": "License Expired"})

        if info["assigned_id"] != 0:
            g = bot.get_guild(GUILD_ID)
            if g and not g.get_member(info["assigned_id"]):
                if info.get("hwid"): ban_hwid_db(info["hwid"])
                delete_key_data(key)
                return jsonify({"valid": False, "msg": "Discord Membership Required - License Revoked"})

        if info["hwid"] == hwid: 
            last_check = info.get("last_otp_verify", 0)
            if time.time() - last_check > 86400 and info["assigned_id"] != 0: 
                if "otp" not in info:
                    otp_code = str(random.randint(100000, 999999))
                    update_key_data(key, {"otp": otp_code, "temp_hwid": hwid})
                
                asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
                return jsonify({"valid": False, "msg": "OTP_SENT"})
            else:
                rem = int(info["expires"] - time.time())
                return jsonify({"valid": True, "msg": "Authenticated", "left": f"{rem//86400}d"})
            
        elif info["hwid"] is None:
            if info["assigned_id"] == 0:
                update_key_data(key, {"hwid": hwid})
                return jsonify({"valid": True, "msg": "Authenticated", "left": "7d"})
            else:
                if "otp" not in info:
                    otp_code = str(random.randint(100000, 999999))
                    update_key_data(key, {"otp": otp_code, "temp_hwid": hwid})
                
                asyncio.run_coroutine_threadsafe(send_dm_code(info["assigned_id"], info["otp"]), bot.loop)
                return jsonify({"valid": False, "msg": "OTP_SENT"})
            
        else: return jsonify({"valid": False, "msg": "HWID Mismatch"})

    except Exception as e:
        print(f"Verify Error: {e}")
        return jsonify({"valid": False, "msg": "Internal Server Error"})

@app.route('/check_otp', methods=['POST'])
@limiter.limit("10 per minute")
def check_otp():
    try:
        data = request.json
        key = data.get("key"); code = data.get("code")
        
        info = get_key_data(key)
        if not info: return jsonify({"valid": False})
        
        if info.get("otp") == code:
            updates = {
                "hwid": info["temp_hwid"],
                "last_otp_verify": time.time(),
                "otp": firestore.DELETE_FIELD,
                "temp_hwid": firestore.DELETE_FIELD
            }
            
            username = data.get("username")
            display_name = data.get("display_name")
            if username and display_name:
                updates["last_roblox_name"] = f"{display_name} (@{username})"
            
            update_key_data(key, updates)
            rem = int(info["expires"] - time.time())
            return jsonify({"valid": True, "left": f"{rem//86400}d"})
        else:
            return jsonify({"valid": False, "msg": "Invalid Code"})
    except: return jsonify({"valid": False})

@app.route('/update', methods=['POST'])
@limiter.limit("5 per minute")
def update_log():
    data = request.json
    uid = str(data.get("user_id"))
    hwid = data.get("hwid")
    
    if uid in log_cooldowns:
        if time.time() - log_cooldowns[uid] < 30:
            return jsonify({"command": "NONE"})
    
    log_cooldowns[uid] = time.time()

    if not hwid: return jsonify({"command": "NONE"})

    docs = db.collection('keys').where('hwid', '==', hwid).stream()
    is_valid_customer = False
    d_str = "Unknown"
    
    for doc in docs:
        is_valid_customer = True
        v = doc.to_dict()
        if v.get("assigned_id") != 0:
            u = bot.get_user(v.get("assigned_id"))
            if u: d_str = f"{u.id} ({u.name})"
        else:
            d_str = v.get("notes", "Imported User")
        break
    
    if not is_valid_customer:
        return jsonify({"command": "NONE"})
    
    if is_roblox_banned(uid) or is_hwid_banned(hwid):
        return jsonify({"command": "KICK"})
                
    asyncio.run_coroutine_threadsafe(log_discord(data, uid, "Online", d_str), bot.loop)
    return jsonify({"command": "NONE"})

@app.route('/ban', methods=['POST'])
def ban():
    d = request.json
    target_id = str(d.get("target_id"))
    ban_roblox_db(target_id)
    return jsonify({"success": True})

@app.route('/network', methods=['POST'])
@limiter.limit("60 per minute")
def network():
    try:
        data = request.json
        user_id = str(data.get("userId"))
        job_id = data.get("jobId")
        hwid = data.get("hwid")

        if is_hwid_banned(hwid) or is_roblox_banned(user_id):
            return jsonify({"command": "ban", "reason": "Your account has been permanently suspended."})

        current_time = time.time()
        command_to_send = None
        reason_to_send = ""
        
        if user_id in online_users:
            if online_users[user_id].get("command"):
                command_to_send = online_users[user_id]["command"]
                reason_to_send = online_users[user_id].get("reason", "")
                online_users[user_id]["command"] = None 

        online_users[user_id] = {
            "id": user_id,
            "job": job_id,
            "hwid": hwid,
            "last_seen": current_time,
            "command": command_to_send 
        }
        
        active_users_list = []
        for uid, udata in list(online_users.items()):
            if current_time - udata["last_seen"] < 60:
                active_users_list.append({"id": uid, "job": udata["job"]})
            else:
                del online_users[uid]

        response = {"users": active_users_list}
        
        if command_to_send:
            response["command"] = command_to_send
            response["reason"] = reason_to_send

        return jsonify(response)
    except:
        return jsonify({"error": "server error"})

@app.route('/admin/kick', methods=['POST'])
def admin_kick():
    data = request.json
    target_id = str(data.get("targetId"))
    if target_id in online_users:
        online_users[target_id]["command"] = "kick"
        online_users[target_id]["reason"] = "You have been disconnected by an administrator."
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/admin/ban', methods=['POST'])
def admin_ban():
    data = request.json
    target_id = str(data.get("targetId"))
    reason = data.get("reason", "Administrator Ban")

    ban_roblox_db(target_id)

    hwid_to_ban = None
    if target_id in online_users:
        hwid_to_ban = online_users[target_id].get("hwid")
        online_users[target_id]["command"] = "ban"
        online_users[target_id]["reason"] = reason

    if hwid_to_ban:
        ban_hwid_db(hwid_to_ban)

    key_to_delete = None
    discord_id_to_kick = None

    if hwid_to_ban:
        docs = db.collection('keys').where('hwid', '==', hwid_to_ban).stream()
        for doc in docs:
            key_to_delete = doc.id
            discord_id_to_kick = doc.to_dict().get("assigned_id")
            break
    
    if key_to_delete:
        delete_key_data(key_to_delete)

    if discord_id_to_kick:
        asyncio.run_coroutine_threadsafe(kick_discord_user(discord_id_to_kick, reason), bot.loop)

    return jsonify({"success": True})

@bot.tree.command(name="getkey", description="Retrieve your active license key")
async def getkey(interaction: discord.Interaction):
    TARGET_GUILD_ID = 1460981897730592798
    if interaction.guild_id != TARGET_GUILD_ID:
        await interaction.response.send_message("This command can only be used in the official server.", ephemeral=True)
        return

    BLACKLISTED_ROLE_ID = 1464562474249617480
    if any(role.id == BLACKLISTED_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("Access denied: You are restricted from using this command.", ephemeral=True)
        return

    docs = db.collection('keys').where('assigned_id', '==', interaction.user.id).stream()
    active_key = None
    
    for doc in docs:
        active_key = doc.id
        break
    
    if active_key:
        await interaction.response.send_message(f"Your active license key is:\n`{active_key}`\n\n*Keep this key safe and do not share it.*", ephemeral=True)
    else:
        await interaction.response.send_message("You do not have an active license key.", ephemeral=True)

@bot.tree.command(name="genkey", description="Generate a new license key")
@app_commands.describe(duration="30d, 12h", user="User")
async def genkey(interaction: discord.Interaction, duration: str, user: discord.Member):
    if interaction.user.id not in ADMIN_IDS: 
        await interaction.response.send_message("Unauthorized access.", ephemeral=True)
        return
    
    docs = db.collection('keys').where('assigned_id', '==', user.id).stream()
    if any(docs):
        await interaction.response.send_message(f"User {user.mention} already possesses an active license.", ephemeral=True); return

    h = parse_duration(duration)
    if not h: await interaction.response.send_message("Invalid duration format.", ephemeral=True); return
    
    raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    key = f"ANARCHY-{raw}"
    
    key_data = {
        "hwid": None, "expires": time.time() + (h * 3600),
        "created_at": time.time(), "duration_txt": duration, 
        "assigned_id": user.id, "last_reset": 0, "last_roblox_name": "N/A",
        "last_otp_verify": 0
    }
    
    db.collection('keys').document(key).set(key_data)
    
    try:
        verified_role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        member_role = interaction.guild.get_role(MEMBER_ROLE_ID)
        if verified_role: await user.add_roles(verified_role)
        if member_role: await user.remove_roles(member_role) 
    except: pass

    await interaction.response.send_message(f"License generated for {user.mention}.\nKey: `{key}`\nDuration: {duration}")

@bot.tree.command(name="ban", description="Ban a user from Discord, Revoke Key and Ban HWID")
@app_commands.describe(user="The Discord user to ban", reason="Reason for the ban")
async def ban_command(interaction: discord.Interaction, user: discord.Member, reason: str = "Violating Rules"):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("Unauthorized access.", ephemeral=True)
        return

    actions_taken = []
    
    docs = db.collection('keys').where('assigned_id', '==', user.id).stream()
    
    for doc in docs:
        info = doc.to_dict()
        key_id = doc.id
        
        if info.get("hwid"):
            ban_hwid_db(info["hwid"])
            actions_taken.append("HWID Blacklisted")
        
        delete_key_data(key_id)
        actions_taken.append("License Key Revoked")
    
    try:
        try: await user.send(f"You have been banned from Anarchy.\nReason: {reason}")
        except: pass
        await user.ban(reason=reason)
        actions_taken.append("Banned from Discord Server")
    except Exception as e:
        actions_taken.append(f"Failed to ban from Discord: {e}")

    if not actions_taken:
        actions_taken.append("User had no key/HWID, but tried to ban from Discord.")
    
    embed = discord.Embed(title="User Termination Protocol", color=0xFF0000)
    embed.add_field(name="Target", value=f"{user.mention} ({user.id})", inline=False)
    embed.add_field(name="Actions Taken", value="\n".join([f"• {x}" for x in actions_taken]), inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reset_hwid", description="Reset HWID binding")
async def reset_hwid(interaction: discord.Interaction):
    docs = db.collection('keys').where('assigned_id', '==', interaction.user.id).stream()
    target_key = None
    info = None
    
    for doc in docs:
        target_key = doc.id
        info = doc.to_dict()
        break
        
    if not target_key: await interaction.response.send_message("No active license found.", ephemeral=True); return
        
    last_r = info.get("last_reset", 0)
    
    if time.time() - last_r < 259200 and interaction.user.id not in ADMIN_IDS:
        remaining = int(259200 - (time.time() - last_r))
        h = remaining // 3600
        await interaction.response.send_message(f"Cooldown active. Please wait {h} hours.", ephemeral=True); return

    update_key_data(target_key, {"hwid": None, "last_reset": time.time()})
    await interaction.response.send_message("HWID binding has been reset successfully.")

@bot.tree.command(name="listhwids", description="List banned HWIDs")
async def listhwids(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    docs = db.collection('blacklist_hwids').stream()
    hwids = [doc.id for doc in docs]
    
    if not hwids: await interaction.response.send_message("No banned HWIDs found.", ephemeral=True); return
    lines = [f"**Banned HWID List ({len(hwids)}):**"]
    for hwid in hwids: lines.append(f"`{hwid}`")
    msg = "\n".join(lines)
    if len(msg) > 1900:
        f = discord.File(io.StringIO(msg), filename="banned_hwids.txt")
        await interaction.response.send_message("List is too long, see attachment:", file=f)
    else: await interaction.response.send_message(msg)

@bot.tree.command(name="delkey", description="Revoke a license key")
async def delkey(interaction: discord.Interaction, key: str):
    if interaction.user.id not in ADMIN_IDS: return
    
    doc = db.collection('keys').document(key).get()
    if doc.exists:
        delete_key_data(key)
        await interaction.response.send_message("License revoked.")
    else: 
        await interaction.response.send_message("Key not found.")

@bot.tree.command(name="ban_roblox_user", description="Ban a Roblox User ID")
async def ban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id not in ADMIN_IDS: return
    ban_roblox_db(roblox_id)
    await interaction.response.send_message(f"Roblox ID `{roblox_id}` has been banned.")

@bot.tree.command(name="listkeys", description="List all active licenses")
async def listkeys(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    docs = db.collection('keys').stream()
    
    lines = []
    g = bot.get_guild(GUILD_ID)
    
    count = 0
    for doc in docs:
        count += 1
        k = doc.id
        v = doc.to_dict()
        
        if v.get("assigned_id") == 0:
            u = v.get("notes", "Unknown Imported User")
        else:
            m = g.get_member(v["assigned_id"]) if v.get("assigned_id") else None
            u = f"{v.get('assigned_id')} ({m.name})" if m else f"ID:{v.get('assigned_id')}"
        
        rbx = v.get("last_roblox_name", "N/A")
        lines.append(f"Key: `{k}` | User: {u} | Roblox: {rbx} | Term: {v.get('duration_txt')}")
    
    if count == 0: await interaction.response.send_message("No active licenses.", ephemeral=True); return

    f = discord.File(io.StringIO("\n".join(lines)), filename="active_keys.txt")
    await interaction.response.send_message(f"Active License Database ({count}):", file=f)

@bot.tree.command(name="unban_hwid", description="Unban a specific HWID")
async def unban_hwid(interaction: discord.Interaction, hwid: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("Unauthorized access.", ephemeral=True); return
    
    if is_hwid_banned(hwid):
        unban_hwid_db(hwid)
        await interaction.response.send_message(f"HWID `{hwid}` has been unbanned.", ephemeral=True)
    else:
        await interaction.response.send_message("HWID not found in blacklist.", ephemeral=True)

@bot.tree.command(name="unban_roblox_user", description="Unban a Roblox User ID")
async def unban_roblox_user(interaction: discord.Interaction, roblox_id: str):
    if interaction.user.id not in ADMIN_IDS: await interaction.response.send_message("Unauthorized access.", ephemeral=True); return
    
    if is_roblox_banned(roblox_id):
        unban_roblox_db(roblox_id)
        await interaction.response.send_message(f"Roblox ID `{roblox_id}` has been unbanned.", ephemeral=True)
    else:
        await interaction.response.send_message("ID not found in blacklist.", ephemeral=True)

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
