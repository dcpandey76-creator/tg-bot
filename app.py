import threading
import asyncio
import sqlite3
from flask import Flask
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded

# ==================== 1. FLASK WEB SERVER (Render 24/7 Alive) ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Telegram Multi-Account Userbot is Live and Running!"

def run_flask():
    web_app.run(host="0.0.0.0", port=10000)

# ==================== 2. CONFIGURATIONS & DATABASE ====================
API_ID = 39247243  
API_HASH = "bee07e137cee5341cb61b73a4c3f9137"  
BOT_TOKEN = "8905516793:AAFZ9OD8KhsmGur87euDtESNRfOuIHMx8jo"  

DB_FILE = "accounts.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_string TEXT UNIQUE)''')
    conn.commit()
    conn.close()

init_db()

def add_session_to_db(session_str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO sessions (session_string) VALUES (?)", (session_str,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  
    finally:
        conn.close()

def get_all_sessions():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT session_string FROM sessions")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

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
    help_text = (
        "🤖 **Userbot Control Panel**\n\n"
        "Commands:\n"
        "1. `/login` - Phone number aur OTP se naya account add karein\n"
        "2. `/add <session_string>` - Direct session string se add karein\n"
        "3. `/list` - Saved accounts dekhein\n"
        "4. `/join <t.me/link> <delay_secs>` - Sabhi accounts se channel join karein\n"
    )
    await message.reply_text(help_text)

@bot.on_message(filters.command("login"))
async def login_command(client, message):
    USER_STATES[message.chat.id] = "WAITING_PHONE"
    await message.reply_text("📱 Kripya apne Telegram account ka phone number country code ke sath bhejein\n(Example: `+919876543210`):")

@bot.on_message(filters.command("add"))
async def add_session(client, message):
    try:
        args = message.text.split(" ", 1)
        if len(args) < 2:
            await message.reply_text("❌ Kripya session string bhi likhein.\nUsage: `/add <session_string>`")
            return
        
        session_str = args[1].strip()
        success = add_session_to_db(session_str)
        total_accounts = len(get_all_sessions())
        
        if success:
            await message.reply_text(f"✅ Account successfully database mein save ho gaya!\nTotal saved accounts: {total_accounts}")
        else:
            await message.reply_text(f"⚠️ Yeh session pehle se added hai!\nTotal saved accounts: {total_accounts}")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

@bot.on_message(filters.command("list"))
async def list_accounts(client, message):
    sessions = get_all_sessions()
    await message.reply_text(f"📊 Total Permanently Saved Accounts: **{len(sessions)}**")

@bot.on_message(filters.text & ~filters.command(["start", "login", "add", "list", "join"]))
async def handle_login_steps(client, message):
    chat_id = message.chat.id
    state = USER_STATES.get(chat_id)
    
    if not state:
        return  
    
    if state == "WAITING_PHONE":
        phone = message.text.strip()
        try:
            status_msg = await message.reply_text("⏳ Telegram par OTP code bheja ja raha hai...")
            u_client = Client(f"temp_login_{chat_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await u_client.connect()
            sent_code = await u_client.send_code(phone)
            
            LOGIN_DATA[chat_id] = {
                "client": u_client,
                "phone": phone,
                "hash": sent_code.phone_code_hash
            }
            USER_STATES[chat_id] = "WAITING_OTP"
            await status_msg.edit_text("✅ OTP bhej diya gaya hai!\nKripya apne Telegram app par aaya hua **OTP code** yahan bhejein:")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ Phone Error: {e}\nDobara koshish karne ke liye `/login` likhein.")

    elif state == "WAITING_OTP":
        otp = message.text.strip().replace(" ", "")
        data = LOGIN_DATA.get(chat_id)
        if not data:
            await message.reply_text("❌ Session expired. Dobara `/login` likhein.")
            USER_STATES.pop(chat_id, None)
            return
        
        try:
            u_client = data["client"]
            phone = data["phone"]
            ph_hash = data["hash"]
            
            try:
                await u_client.sign_in(phone, ph_hash, otp)
            except SessionPasswordNeeded:
                USER_STATES[chat_id] = "WAITING_2FA"
                await message.reply_text("🔒 Aapke account par 2FA Password laga hai. Apna **2FA Password** yahan bhejein:")
                return
            
            session_string = await u_client.export_session_string()
            await u_client.disconnect()
            add_session_to_db(session_string)
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            
            await message.reply_text(f"🎉 Account successfully login ho gaya!\nTotal saved accounts: {len(get_all_sessions())}")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ OTP Error: {e}\nDobara koshish ke liye `/login` use karein.")

    elif state == "WAITING_2FA":
        password = message.text.strip()
        data = LOGIN_DATA.get(chat_id)
        if not data:
            await message.reply_text("❌ Session expired. Dobara `/login` likhein.")
            USER_STATES.pop(chat_id, None)
            return
        
        try:
            u_client = data["client"]
            await u_client.check_password(password)
            session_string = await u_client.export_session_string()
            await u_client.disconnect()
            add_session_to_db(session_string)
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            
            await message.reply_text(f"🎉 2FA verified! Account successfully saved.\nTotal saved accounts: {len(get_all_sessions())}")
        except Exception as e:
            USER_STATES.pop(chat_id, None)
            LOGIN_DATA.pop(chat_id, None)
            await message.reply_text(f"❌ Password Error: {e}\nDobara koshish ke liye `/login` use karein.")

@bot.on_message(filters.command("join"))
async def join_channels(client, message):
    sessions = get_all_sessions()
    if not sessions:
        await message.reply_text("❌ Pehle koi account add karein (`/login` command se).")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ Sahi format use karein:\n`/join <t.me/channel_link> <delay_seconds>`")
        return
    
    chat_input = clean_chat_input(args[1])
    delay = int(args[2])
    status_msg = await message.reply_text(f"🚀 `{chat_input}` par real requests bheji ja rahi hain...")
    
    success_count = 0
    for idx, session in enumerate(sessions, start=1):
        try:
            async with Client(f"real_user_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session) as user_client:
                await user_client.join_chat(chat_input)
                success_count += 1
                await status_msg.edit_text(f"⚡ Account {idx} ne successfully join kar liya!\nWaiting for {delay} seconds...")
            await asyncio.sleep(delay)
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Account {idx} error: {e}")
            await asyncio.sleep(delay)

    await message.reply_text(f"✨ Task Complete! Total successful joins: {success_count}/{len(sessions)}")

# ==================== 4. SAFE RUNNER (Python 3.14 Fix) ====================
if __name__ == "__main__":
    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("Flask web server running on port 10000...")

    print("Telegram Control Bot starting...")
    # Safe manual loop initialization for Python 3.14
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot.start())
    
    import idle
    # Keep bot running safely
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(bot.stop())
