import asyncio
import threading
import time
import requests
import os
import sqlite3
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.raw.functions.phone import JoinGroupCall, LeaveGroupCall
from pyrogram.raw.types import InputPeerChannel

# ==================== 1. FLASK WEB SERVER & SELF-PING ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Telegram Multi-Account Userbot is Live and Running!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

def self_ping():
    render_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:10000")
    while True:
        try:
            time.sleep(240)
            requests.get(render_url)
        except Exception:
            pass

# ==================== 2. CONFIGURATIONS & STORAGE ====================
API_ID = 39247243  
API_HASH = "bee07e137cee5341cb61b73a4c3f9137"  
BOT_TOKEN = "8905516793:AAFZ9OD8KhsmGur87euDtESNRfOuIHMx8jo"  

# 👑 Teri Original Telegram User ID (Always Owner)
OWNER_ID = 5406594181  

DB_FILE = "accounts.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_string TEXT UNIQUE)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

# --- ADMIN MANAGEMENT ---
def is_owner_or_admin(user_id):
    if user_id == OWNER_ID:
        return True
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        return True

    env_admins = os.getenv("ADMIN_IDS", "")
    if env_admins:
        for aid in env_admins.split(","):
            if aid.strip() and int(aid.strip()) == user_id:
                return True

    return False

def add_admin_to_db(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()

def get_all_admins():
    admins_set = {OWNER_ID}
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins")
        rows = cursor.fetchall()
        conn.close()
        for row in rows:
            admins_set.add(row[0])
            
    env_admins = os.getenv("ADMIN_IDS", "")
    if env_admins:
        for aid in env_admins.split(","):
            if aid.strip():
                admins_set.add(int(aid.strip()))
                
    return list(admins_set)

# --- ACCOUNT MANAGEMENT ---
def add_session_to_db(session_str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO sessions (session_string) VALUES (?)", (session_str,))
        conn.commit()
        return True
    except Exception:
        return False  
    finally:
        conn.close()

def get_all_sessions():
    sessions_set = set()
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT session_string FROM sessions")
        rows = cursor.fetchall()
        conn.close()
        for row in rows:
            sessions_set.add(row[0].strip())
            
    env_sessions = os.getenv("SESSION_STRINGS", "")
    if env_sessions:
        for s in env_sessions.split(","):
            if s.strip():
                sessions_set.add(s.strip())
                
    return list(sessions_set)

# Main Control Bot
bot = Client(
    "main_control_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

USER_STATES = {}
LOGIN_DATA = {}

def clean_chat_input(raw_input):
    raw_input = raw_input.strip()
    if "t.me/" in raw_input:
        raw_input = raw_input.split("t.me/")[-1].split("/")[0]
    if raw_input.startswith("@"):
        raw_input = raw_input[1:]
    return raw_input

# ==================== 3. BOT COMMANDS ====================

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        await message.reply_text("⛔ Aap is bot ko use karne ke liye authorized nahi hain!")
        return

    help_text = (
        "🤖 **Userbot Control Panel (Fully Bot-Managed)**\n\n"
        "Commands:\n"
        "1. `/login` - Phone & OTP se account add karein\n"
        "2. `/add <session>` - Direct session add karein\n"
        "3. `/list` - Saved accounts dekhein\n"
        "4. `/join <link> <delay>` - Channel join karein\n"
        "5. `/joinc <link>` - Voice Chat (VC) join karein\n"
        "6. `/leavec <link>` - Voice Chat (VC) leave karein\n"
        "7. `/addadmin <user_id>` - Direct admin banayein (**Owner Only**)\n"
        "8. `/admins` - Sabhi admins ki list dekhein\n"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.command("addadmin"))
async def add_admin_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("⛔ Yeh command sirf Bot ke Owner ke liye hai!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Sahi format use karein:\n`/addadmin <user_id>`")
        return
    
    try:
        new_id = int(args[1])
        success = add_admin_to_db(new_id)
        if success:
            await message.reply_text(f"✅ User `{new_id}` ko successfully database mein Admin bana diya gaya hai!")
        else:
            await message.reply_text("⚠️ Yeh user pehle se admin hai ya koi error aaya.")
    except ValueError:
        await message.reply_text("❌ User ID ek number honi chahiye!")

@bot.on_message(filters.command("admins"))
async def list_admins_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    admins = get_all_admins()
    await message.reply_text(f"👑 **Owner ID:** `{OWNER_ID}`\n👥 **Active Admins:** `{admins}`")

@bot.on_message(filters.command("login"))
async def login_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    USER_STATES[message.chat.id] = "WAITING_PHONE"
    await message.reply_text("📱 Apne Telegram account ka phone number bhejein (Example: `+919876543210`):")

@bot.on_message(filters.command("add"))
async def add_session(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    try:
        args = message.text.split(" ", 1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: `/add <session_string>`")
            return
        session_str = args[1].strip()
        add_session_to_db(session_str)
        await message.reply_text(f"✅ Account successfully database mein save ho gaya!\n📊 Total Active Accounts: {len(get_all_sessions())}")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@bot.on_message(filters.command("list"))
async def list_accounts(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    sessions = get_all_sessions()
    await message.reply_text(f"📊 Total Saved Accounts: **{len(sessions)}**")

@bot.on_message(filters.text & ~filters.command(["start", "login", "add", "list", "join", "joinc", "leavec", "addadmin", "admins"]))
async def handle_login_steps(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    chat_id = message.chat.id
    state = USER_STATES.get(chat_id)
    if not state:
        return  
    
    if state == "WAITING_PHONE":
        phone = message.text.strip()
        try:
            status_msg = await message.reply_text("⏳ OTP bheja ja raha hai...")
            u_client = Client(f"temp_login_{chat_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await u_client.connect()
            sent_code = await u_client.send_code(phone)
            LOGIN_DATA[chat_id] = {"client": u_client, "phone": phone, "hash": sent_code.phone_code_hash}
            USER_STATES[chat_id] = "WAITING_OTP"
            await status_msg.edit_text("✅ OTP bhej diya gaya hai! OTP yahan bhejein:")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ Error: {e}")

    elif state == "WAITING_OTP":
        otp = message.text.strip().replace(" ", "")
        data = LOGIN_DATA.get(chat_id)
        if not data:
            USER_STATES.pop(chat_id, None)
            return
        try:
            u_client = data["client"]
            try:
                await u_client.sign_in(data["phone"], data["hash"], otp)
            except SessionPasswordNeeded:
                USER_STATES[chat_id] = "WAITING_2FA"
                await message.reply_text("🔒 2FA Password required. Password bhejein:")
                return
            session_string = await u_client.export_session_string()
            await u_client.disconnect()
            add_session_to_db(session_string)
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"🎉 Login Success & Account Saved in DB!\n📊 Total Accounts: {len(get_all_sessions())}")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ OTP Error: {e}")

    elif state == "WAITING_2FA":
        try:
            u_client = LOGIN_DATA[chat_id]["client"]
            await u_client.check_password(message.text.strip())
            session_string = await u_client.export_session_string()
            await u_client.disconnect()
            add_session_to_db(session_string)
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"🎉 2FA Success & Account Saved in DB!\n📊 Total Accounts: {len(get_all_sessions())}")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ Password Error: {e}")

@bot.on_message(filters.command("join"))
async def join_channels(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    sessions = get_all_sessions()
    if not sessions:
        await message.reply_text("❌ Pehle accounts add karein.")
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ Format: `/join <link> <delay_seconds>`")
        return
    raw_link, delay = args[1].strip(), int(args[2])
    status_msg = await message.reply_text(f"🚀 `{len(sessions)}` accounts se join shuru...")
    
    success, fail = 0, 0
    for idx, session in enumerate(sessions, start=1):
        try:
            uc = Client(f"j_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
            await uc.connect()
            if "+" in raw_link or "joinchat" in raw_link:
                await uc.join_chat(raw_link)
            else:
                await uc.join_chat(clean_chat_input(raw_link))
            success += 1
            await status_msg.edit_text(f"✅ Account {idx} joined! Waiting {delay}s...")
            await uc.disconnect()
            await asyncio.sleep(delay)
        except Exception as e:
            fail += 1
            await message.reply_text(f"⚠️ Account {idx} Error: `{e}`")
            await asyncio.sleep(delay)
    await message.reply_text(f"✨ Complete! Success: {success}, Failed: {fail}")

@bot.on_message(filters.command("joinc"))
async def join_vc_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    sessions = get_all_sessions()
    if not sessions:
        await message.reply_text("❌ Pehle accounts add karein.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ Format: `/joinc <channel_username_or_link>`")
        return
    
    raw_link = args[1].strip()
    status_msg = await message.reply_text(f"🎙️ `{len(sessions)}` accounts se Voice Chat join ki ja rahi hai...")
    
    success, fail = 0, 0
    for idx, session in enumerate(sessions, start=1):
        try:
            uc = Client(f"vc_j_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
            await uc.connect()
            
            if "+" in raw_link or "joinchat" in raw_link:
                chat = await uc.join_chat(raw_link)
                peer = await uc.resolve_peer(chat.id)
            else:
                username = clean_chat_input(raw_link)
                chat = await uc.get_chat(username)
                peer = await uc.resolve_peer(chat.id)
            
            await uc.invoke(JoinGroupCall(
                peer=InputPeerChannel(channel_id=peer.channel_id, access_hash=peer.access_hash),
                muted=True,
                video_stopped=True,
                invite_hash=""
            ))
            success += 1
            await status_msg.edit_text(f"🎙️ Account {idx} VC joined successfully!")
            await uc.disconnect()
            await asyncio.sleep(2)
        except Exception as e:
            fail += 1
            await message.reply_text(f"⚠️ Account {idx} VC Error: `{e}`")
            try:
                await uc.disconnect()
            except:
                pass
            await asyncio.sleep(2)
            
    await message.reply_text(f"✨ VC Join Complete!\n✅ Success: {success}\n❌ Failed: {fail}")

@bot.on_message(filters.command("leavec"))
async def leave_vc_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return
    sessions = get_all_sessions()
    if not sessions:
        await message.reply_text("❌ Pehle accounts add karein.")
        return
    args = message.text.split()
    if
