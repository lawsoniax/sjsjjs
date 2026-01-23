import os
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import asyncio
import logging
import time
import json
import secrets
import string
import requests

# --- AYARLAR ---
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1460981897730592798 # Senin Sunucu ID'n
DB_FILE = "anarchy_db.json"
LOGGER_SERVICE_URL = "https://senin-logger-projen.onrender.com/send_log" # Logger linkin

# --- ESKİ KEYLER (LEGACY SUPPORT) ---
# Verdiğin listeyi buraya işledim. Bunlar yeni sistemden etkilenmez, çalışmaya devam eder.
INITIAL_KEYS = {
    "ANARCHY-CZ5GVGZE4W6J1PTC": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-0YIXA75QVT6PDRAU": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-6MJQA5HWECR7ZZML": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "Messy (@yoshordybad)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-FMKOB454POWMWIK5": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-5LIVRP7HCDZGDJFN": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-ITSIZSJYWGIYPWAI": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "tink (@tinksouffle)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-506ETM8OTZV1XSIV": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-FKK2FFPCMHGGRLQP": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-P6EKTRBF6PWYVOEW": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-8332RNF1LD7GYUXQ": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-KIW3E5HDTTFCFL1Q": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-YCYAH0VLPW623JNB": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "Rkelley (@Rkelley390)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-ZIGH3X50T4QHKULW": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-KF8IJ7787S1ARFZA": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "ieatbreadforaliving (@ieatbreadforaliving)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-7FEITOI3YIW1L6IO": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "meds (@91med)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-3T57HLOMJ0SX9KEZ": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "OY_Zeus (@BloxPatcher)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-S6O5VV7U1ODP4WSM": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "jpinnedui_123 (@asdfasdasdasgwas)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-YLRQQPQMUBZJQDGX": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "Meko (@Alecdoom)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-ZHPEAT32XHC1TKEN": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-HTFF8WT3TAY0ANGZ": {"expires": 1770000000, "registered_name": "Unknown", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-U9IT7Z4A6Z2LH153": {"expires": 1770000000, "registered_name": "Unknown", "last_roblox_name": "urlastgoodbye (@KingSammelot_Vortrox)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-IABR0CV8YM8BG6RM": {"expires": 1770000000, "registered_name": "frank12_1k", "last_roblox_name": "H4ke_10 (@H4ke_10)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-YSUJU1KI58ZVFAH2": {"expires": 1770000000, "registered_name": "4utummchill", "last_roblox_name": "vexmivhael (@wolf_haoo)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-VAF3IKQ1D3NEOHX7": {"expires": 1770000000, "registered_name": "axeorzz", "last_roblox_name": "LarrysLot (@LarrysLot)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-3O4A1O2VWWCTB8IV": {"expires": 1770000000, "registered_name": "hatniac", "last_roblox_name": "Nettspend_Yams (@Nettspend_Yams)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-POM4CKYVN6NKR7KE": {"expires": 1770000000, "registered_name": "oxycodoneprime", "last_roblox_name": "Youranoob5252 (@youranoob5252)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-WWD9TJ8C0IMF4ARP": {"expires": 1770000000, "registered_name": "zoqf_teo", "last_roblox_name": "Bron (@super21isasam)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-CQ1I9RGMUEP0P7K8": {"expires": 1770000000, "registered_name": "ktih", "last_roblox_name": "3yrsd (@3yrsd)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-L2M4KSSY5OSKSUY1": {"expires": 1770000000, "registered_name": "graui6749", "last_roblox_name": "05s (@ZEZUS7779ZZZ777)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-K80L8PGVCG8C6DNQ": {"expires": 1770000000, "registered_name": "dape23_", "last_roblox_name": "Scp087DashB (@Scp087DashB)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-JVSOK8DGSWICE3XW": {"expires": 1770000000, "registered_name": "elffup", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-CDW7ZRER4NSNIXJX": {"expires": 1770000000, "registered_name": "programlover", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-QLUI2923JFF13TEL": {"expires": 1770000000, "registered_name": "mikaillwayskind2", "last_roblox_name": "Gubby (@Siempum)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-V7B20Y3XJ4BBMAYD": {"expires": 1770000000, "registered_name": "lolity0926", "last_roblox_name": "enbracex122 (@enbracex122)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-GVBHINMP8XBLVZ4A": {"expires": 1770000000, "registered_name": "mkjay33", "last_roblox_name": "Kaz (@Gerald1021)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-WOQW3GJYGJDNSI9X": {"expires": 1770000000, "registered_name": "ciglipuff", "last_roblox_name": "puff (@OguzAMAA)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-LSQBIOT2SX55Y88G": {"expires": 1770000000, "registered_name": "batu01987", "last_roblox_name": "jokerpapa18 (@jokerpapa18)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-34VACLUGXM7DNE7G": {"expires": 1770000000, "registered_name": ".jssee", "last_roblox_name": "EcoStudies (@ColdForceBlatan_t)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-D08Q9HV3FCEQQTWH": {"expires": 1770000000, "registered_name": "21n10", "last_roblox_name": "yone12218 (@yone12218)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-R7NTFPNJVIPYFFA4": {"expires": 1770000000, "registered_name": "fleshmnevochko0178", "last_roblox_name": "Fallisae (@Fallisaeed)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-DBOP7ANCHR914JZ7": {"expires": 1770000000, "registered_name": "3sabwavee", "last_roblox_name": "Oak (@YokaiIzsus)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-8ORQ3SRDUZ45YAJV": {"expires": 1770000000, "registered_name": "ateniy", "last_roblox_name": "Barnn (@domozkokushibo)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-X6YY5JPZ8UCKO9Y5": {"expires": 1770000000, "registered_name": ".archyx", "last_roblox_name": "Archyx (@FredBear_599)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-YFVGTVSURZ9D8L2G": {"expires": 1770000000, "registered_name": "2oaw", "duration_txt": "30d", "native_hwid": None},
    "ANARCHY-6ZFO4C8OR47IGXFK": {"expires": 1770000000, "registered_name": "itsnotlukke", "last_roblox_name": "CosmicKernel (@itsnotlukke_5)", "duration_txt": "7d", "native_hwid": None},
    "ANARCHY-AAUHS4FK6YFWGQ8I": {"expires": 1770000000, "registered_name": "lokwn.", "duration_txt": "7d", "native_hwid": None}
}

# --- SYSTEM SETUP ---
log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # BU KESİNLİKLE GEREKLİ
bot = commands.Bot(command_prefix="!", intents=intents)
app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["3000 per day", "1000 per hour"], 
    storage_uri="memory://"
)

database = {"keys": {}, "users": {}, "blacklisted_hwids": []}

def load_db():
    global database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f: 
                data = json.load(f)
                for k in ["keys", "users", "blacklisted_hwids"]:
                    if k not in data: data[k] = [] if "list" in k else {}
                database = data
                
                # Eski Keyleri Yükle (Eğer yoksa)
                for k, v in INITIAL_KEYS.items():
                    if k not in database["keys"]:
                        database["keys"][k] = v
        except: pass
    else:
        # İlk kurulumda eski keyleri yükle
        database["keys"] = INITIAL_KEYS
        save_db()

def save_db():
    try:
        with open(DB_FILE, "w") as f: json.dump(database, f)
    except: pass

load_db()

def send_to_logger(payload):
    try: requests.post(LOGGER_SERVICE_URL, json=payload, timeout=2)
    except: pass

# --- YENİ KAYIT SİSTEMİ (PC APP İÇİN) ---
@app.route('/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    try:
        data = request.json
        discord_name = data.get("username") # Kullanıcının girdiği nick
        hwid = data.get("hwid")
        
        if request.headers.getlist("X-Forwarded-For"): ip = request.headers.getlist("X-Forwarded-For")[0]
        else: ip = request.remote_addr

        log_payload = {"status": "Register Attempt", "username": discord_name, "hwid": hwid, "ip": ip}

        # 1. HWID Blacklist Kontrol
        if hwid in database["blacklisted_hwids"]:
            return jsonify({"success": False, "msg": "BANNED DEVICE"})

        # 2. 1 HWID = 1 Key Kuralı
        # Tüm keyleri tara, bu HWID'ye kilitli başka key var mı?
        for k, v in database["keys"].items():
            if v.get("native_hwid") == hwid:
                # Eğer süre bitmişse izin ver, değilse engelle
                if time.time() < v.get("expires", 0):
                    return jsonify({"success": False, "msg": "This PC already has an active key!"})

        # 3. Discord İsmi Kontrolü (Daha önce alınmış mı?)
        for k, v in database["keys"].items():
            if v.get("registered_name") and v.get("registered_name").lower() == discord_name.lower():
                 if time.time() < v.get("expires", 0):
                    return jsonify({"success": False, "msg": "This Discord user already has a key!"})

        # 4. Discord Sunucusunda Ara
        guild = bot.get_guild(GUILD_ID)
        if not guild: return jsonify({"success": False, "msg": "Server Error (Guild not loaded)"})
        
        member = guild.get_member_named(discord_name)
        if not member:
            return jsonify({"success": False, "msg": "User not found in Discord Server!"})

        # 5. Key Oluştur
        raw = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
        new_key = f"ANARCHY-{raw}"
        
        # 6. Kaydet ve HWID KİLİTLE
        database["keys"][new_key] = {
            "native_hwid": hwid,      # Loader için kilit
            "roblox_hwid": None,      # Roblox için kilit (ilk girişte)
            "expires": time.time() + (7 * 86400), # 7 Günlük
            "created_at": time.time(),
            "duration_txt": "7d (Auto-Gen)",
            "assigned_id": member.id,
            "registered_name": discord_name
        }
        save_db()

        # 7. DM Gönder
        asyncio.run_coroutine_threadsafe(send_dm_key(member, new_key), bot.loop)
        
        # Logla
        log_payload["status"] = "Registered & Key Sent"
        log_payload["key"] = new_key
        threading.Thread(target=send_to_logger, args=(log_payload,)).start()

        return jsonify({"success": True, "msg": "Key sent to DM!"})

    except Exception as e:
        print(f"Register Error: {e}")
        return jsonify({"success": False, "msg": "Server Error"})

async def send_dm_key(member, key):
    try:
        embed = discord.Embed(title="🔐 Anarchy License", description="Here is your key for the loader.", color=0x00FF00)
        embed.add_field(name="License Key", value=f"```{key}```", inline=False)
        embed.add_field(name="Warning", value="This key is now locked to your PC.", inline=False)
        await member.send(embed=embed)
    except: pass

# --- LOGIN KONTROL (VERIFY) ---
@app.route('/verify', methods=['POST'])
@limiter.limit("60 per minute")
def verify():
    try:
        data = request.json
        key = data.get("key")
        sent_hwid = data.get("hwid")
        is_loader = data.get("is_loader", False)
        
        username = data.get("username")
        display_name = data.get("display_name")
        
        if request.headers.getlist("X-Forwarded-For"): ip = request.headers.getlist("X-Forwarded-For")[0]
        else: ip = request.remote_addr

        log_payload = {"key": key, "hwid": sent_hwid, "username": username, "ip": ip, "status": "Processing..."}

        # 1. Blacklist
        if sent_hwid in database["blacklisted_hwids"]:
            log_payload["status"] = "BANNED HWID"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "HWID Banned"})
        
        # 2. Key Var mı?
        if key not in database["keys"]:
            log_payload["status"] = "Invalid Key"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Invalid Key"})
        
        info = database["keys"][key]
        
        # İsim Güncelleme
        if username and display_name:
            if is_loader: info["pc_user"] = f"{display_name}"
            else: info["last_roblox_name"] = f"{display_name} (@{username})"
            save_db()

        # 3. Süre Bitti mi?
        if time.time() > info["expires"]:
            # Eski key silinmesin, sadece expired densin (istiyorsan silme kodunu açabilirsin)
            log_payload["status"] = "Expired"
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": False, "msg": "Expired"})

        valid_access = False
        
        if is_loader:
            # --- C++ LOADER KONTROL ---
            saved_native = info.get("native_hwid")
            
            if saved_native is None:
                # Eski Keyler için İlk PC Girişi -> Kilitle
                info["native_hwid"] = sent_hwid
                save_db()
                valid_access = True
                log_payload["status"] = "Locked to PC (Legacy)"
            elif saved_native == sent_hwid:
                valid_access = True
                log_payload["status"] = "Success (PC)"
            else:
                log_payload["status"] = "HWID Mismatch (PC)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "Wrong PC"})
                
        else:
            # --- ROBLOX SCRIPT KONTROL ---
            saved_roblox = info.get("roblox_hwid")
            
            if saved_roblox is None:
                info["roblox_hwid"] = sent_hwid
                save_db()
                valid_access = True
                log_payload["status"] = "Locked to Roblox"
            elif saved_roblox == sent_hwid:
                valid_access = True
                log_payload["status"] = "Success (Roblox)"
            else:
                log_payload["status"] = "HWID Mismatch (Roblox)"
                threading.Thread(target=send_to_logger, args=(log_payload,)).start()
                return jsonify({"valid": False, "msg": "Wrong Exploit"})

        if valid_access:
            rem = int(info["expires"] - time.time())
            days = rem // 86400
            threading.Thread(target=send_to_logger, args=(log_payload,)).start()
            return jsonify({"valid": True, "msg": "Authenticated", "left": f"{days}d"})

    except Exception as e:
        return jsonify({"valid": False, "msg": "Server Error"})

@app.route('/network', methods=['POST'])
def network():
    # Eski network fonksiyonunu buraya yapıştırabilirsin (Online user listesi için)
    return jsonify({"users": []})

def run_flask(): app.run(host='0.0.0.0', port=8080)
if __name__ == '__main__':
    t = threading.Thread(target=run_flask); t.start()
    if TOKEN: bot.run(TOKEN)
