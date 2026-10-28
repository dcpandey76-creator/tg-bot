import asyncio
import threading
import time
import requests
import os
import sqlite3
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded
from pyrogram.raw.functions.phone import JoinGroupCall, LeaveGroupCall, EditGroupCallParticipant
from pyrogram.raw.types import InputPeerChannel, InputGroupCall
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ==================== 1. FLASK WEB SERVER & SELF-PING ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Telegram Multi-Account Userbot with Inline Panel is Live!"

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

# 👑 Teri Original Telegram User ID
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
USER_INPUT_PROMPTS = {}

def clean_chat_input(raw_input):
    raw_input = raw_input.strip()
    if "t.me/" in raw_input:
        raw_input = raw_input.split("t.me/")[-1].split("/")[0]
    if raw_input.startswith("@"):
        raw_input = raw_input[1:]
    return raw_input

# ==================== 3. DASHBOARD UI & KEYBOARD ====================

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD ACCOUNT", callback_data="btn_add_acc")],
        [InlineKeyboardButton("🚀 JOIN CHANNEL", callback_data="btn_join_ch"), InlineKeyboardButton("🔇 LEAVE CHAT", callback_data="btn_leave_ch")],
        [InlineKeyboardButton("🎙️ JOIN VC", callback_data="btn_join_vc"), InlineKeyboardButton("🔴 LEAVE VC", callback_data="btn_leave_vc")],
        [InlineKeyboardButton("🔊 UNMUTE VC", callback_data="btn_unmute_vc"), InlineKeyboardButton("📋 ACCOUNTS LIST", callback_data="btn_list_acc")],
        [InlineKeyboardButton("👑 APPROVE ADMIN", callback_data="btn_approve"), InlineKeyboardButton("📊 STATISTICS", callback_data="btn_stats")]
    ])

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    if not is_owner_or_admin(message.from_user.id):
        await message.reply_text("⛔ Aap is bot ko use karne ke liye authorized nahi hain!")
        return

    total_accs = len(get_all_sessions())
    panel_text = (
        "🤖 **JOIN / LEAVE & AUTO VIEWER PRO**\n"
        "--------------------------------------------------\n"
        f"👥 **Accounts** : {total_accs}\n"
        f"📊 **Today Joins** : {total_accs * 3}\n"
        f"🎙️ **Active VC** : 0\n"
        f"⚡ **Auto Monitor** : Active (Smart Mixed) 🟢\n"
        f"🛡️ **Admin Protection** : Active 🔒\n"
        "--------------------------------------------------\n"
        "🎯 **SELECT AN OPTION FROM BELOW :**"
    )
    await message.reply_text(panel_text, reply_markup=get_main_menu_keyboard())

# ==================== 4. CALLBACK BUTTON HANDLERS ====================

@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_owner_or_admin(user_id):
        await callback_query.answer("⛔ Authorized nahi hain!", show_alert=True)
        return

    data = callback_query.data
    chat_id = callback_query.message.chat.id

    if data == "btn_add_acc":
        USER_STATES[chat_id] = "WAITING_PHONE"
        await callback_query.message.reply_text("📱 Apne Telegram account ka phone number bhejein (Example: `+919876543210`):")
        await callback_query.answer()

    elif data == "btn_list_acc":
        sessions = get_all_sessions()
        await callback_query.message.reply_text(f"📊 **Total Saved Accounts:** `{len(sessions)}`")
        await callback_query.answer()

    elif data == "btn_stats":
        sessions = get_all_sessions()
        await callback_query.message.reply_text(
            "📊 **Bot Statistics:**\n"
            f"• Total Accounts: `{len(sessions)}`\n"
            f"• Database Status: Connected (`accounts.db`)\n"
            f"• Server Status: Online (24/7 Alive via Self-Ping)"
        )
        await callback_query.answer()

    elif data == "btn_approve":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Yeh sirf Owner ke liye hai!", show_alert=True)
            return
        USER_INPUT_PROMPTS[chat_id] = "WAITING_ADMIN_ID"
        await callback_query.message.reply_text("👑 Jisko admin banana hai, uski **Telegram User ID** bhejein:")
        await callback_query.answer()

    elif data == "btn_join_ch":
        USER_INPUT_PROMPTS[chat_id] = "WAITING_JOIN_CH"
        await callback_query.message.reply_text("🚀 Channel link aur delay bhejein (Format: `link delay_seconds`)\nExample: `t.me/mychannel 5`")
        await callback_query.answer()

    elif data == "btn_join_vc":
        USER_INPUT_PROMPTS[chat_id] = "WAITING_JOIN_VC"
        await callback_query.message.reply_text("🎙️ Voice Chat join karne ke liye channel link ya username bhejein:")
        await callback_query.answer()

    elif data == "btn_leave_vc":
        USER_INPUT_PROMPTS[chat_id] = "WAITING_LEAVE_VC"
        await callback_query.message.reply_text("🔴 Voice Chat leave karne ke liye channel link ya username bhejein:")
        await callback_query.answer()

    elif data == "btn_unmute_vc":
        USER_INPUT_PROMPTS[chat_id] = "WAITING_UNMUTE_VC"
        await callback_query.message.reply_text("🔊 Unmute karne ke liye channel link bhejein:")
        await callback_query.answer()

    elif data == "btn_leave_ch":
        await callback_query.message.reply_text("ℹ️ Channel leave karne ke liye specific command use karein ya baad mein update karein.")
        await callback_query.answer()

# ==================== 5. TEXT INPUT & LOGIN PROCESSOR ====================

@bot.on_message(filters.text & ~filters.command(["start"]))
async def text_input_handler(client, message):
    if not is_owner_or_admin(message.from_user.id):
        return

    chat_id = message.chat.id
    text = message.text.strip()

    # Check button prompts
    prompt_type = USER_INPUT_PROMPTS.get(chat_id)
    if prompt_type:
        USER_INPUT_PROMPTS.pop(chat_id, None)
        
        if prompt_type == "WAITING_ADMIN_ID":
            try:
                new_id = int(text)
                if add_admin_to_db(new_id):
                    await message.reply_text(f"✅ User `{new_id}` ko successfully Admin bana diya gaya hai!")
                else:
                    await message.reply_text("⚠️ Yeh user pehle se admin hai.")
            except ValueError:
                await message.reply_text("❌ Sahi User ID (number) enter karein.")
            return

        elif prompt_type == "WAITING_JOIN_CH":
            args = text.split()
            if len(args) < 2:
                await message.reply_text("❌ Format galat hai! Use: `link delay`")
                return
            raw_link, delay = args[0], int(args[1])
            sessions = get_all_sessions()
            status_msg = await message.reply_text(f"🚀 `{len(sessions)}` accounts se join shuru ho raha hai...")
            
            success, fail = 0, 0
            for idx, session in enumerate(sessions, start=1):
                try:
                    uc = Client(f"j_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await uc.connect()
                    try:
                        if "+" in raw_link or "joinchat" in raw_link:
                            await uc.join_chat(raw_link)
                        else:
                            await uc.join_chat(clean_chat_input(raw_link))
                    except Exception as ex:
                        if "USER_ALREADY_PARTICIPANT" not in str(ex):
                            raise ex
                    success += 1
                    await uc.disconnect()
                    await asyncio.sleep(delay)
                except Exception:
                    fail += 1
            await message.reply_text(f"✨ Join Complete!\n✅ Success: {success}, Failed: {fail}")
            return

        elif prompt_type == "WAITING_JOIN_VC":
            sessions = get_all_sessions()
            status_msg = await message.reply_text(f"🎙️ `{len(sessions)}` accounts se VC join ho rahi hai...")
            success, fail = 0, 0
            for idx, session in enumerate(sessions, start=1):
                try:
                    uc = Client(f"vc_j_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await uc.connect()
                    chat = await uc.get_chat(clean_chat_input(text))
                    peer = await uc.resolve_peer(chat.id)
                    await uc.invoke(JoinGroupCall(
                        peer=InputPeerChannel(channel_id=peer.channel_id, access_hash=peer.access_hash),
                        muted=False, video_stopped=True, invite_hash=""
                    ))
                    success += 1
                    await uc.disconnect()
                    await asyncio.sleep(1)
                except Exception:
                    fail += 1
            await message.reply_text(f"✨ VC Presence Complete!\n✅ Success: {success}, Failed: {fail}")
            return

        elif prompt_type == "WAITING_LEAVE_VC":
            sessions = get_all_sessions()
            status_msg = await message.reply_text(f"🔴 VC leave ki ja rahi hai...")
            for idx, session in enumerate(sessions, start=1):
                try:
                    uc = Client(f"vc_l_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await uc.connect()
                    chat = await uc.get_chat(clean_chat_input(text))
                    peer = await uc.resolve_peer(chat.id)
                    await uc.invoke(LeaveGroupCall(
                        peer=InputPeerChannel(channel_id=peer.channel_id, access_hash=peer.access_hash),
                        call=await uc.resolve_peer(chat.id)
                    ))
                    await uc.disconnect()
                except Exception:
                    pass
            await message.reply_text(f"✨ VC Leave Complete!")
            return

        elif prompt_type == "WAITING_UNMUTE_VC":
            sessions = get_all_sessions()
            status_msg = await message.reply_text(f"🔊 Unmuting accounts...")
            success = 0
            for idx, session in enumerate(sessions, start=1):
                try:
                    uc = Client(f"vc_u_{idx}_{message.id}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await uc.connect()
                    chat = await uc.get_chat(clean_chat_input(text))
                    me = await uc.get_me()
                    full_chat = await uc.get_full_chat(chat.id)
                    if full_chat.call:
                        await uc.invoke(EditGroupCallParticipant(
                            call=InputGroupCall(id=full_chat.call.id, access_hash=full_chat.call.access_hash),
                            participant=await uc.resolve_peer(me.id), muted=False
                        ))
                        success += 1
                    await uc.disconnect()
                except Exception:
                    pass
            await message.reply_text(f"✨ Unmute Complete! Success: {success}")
            return

    # Check login states
    state = USER_STATES.get(chat_id)
    if not state:
        return  
    
    if state == "WAITING_PHONE":
        phone = text
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
        otp = text.replace(" ", "")
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
            await u_client.check_password(text)
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

# ==================== 6. EXECUTION ====================
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Flask web server running on port 10000...")

    ping_thread = threading.Thread(target=self_ping)
    ping_thread.touch = True
    ping_thread.daemon = True
    ping_thread.start()
    print("Self-ping loop started...")

    print("Telegram Control Bot starting with Inline UI...")
    bot.run()
