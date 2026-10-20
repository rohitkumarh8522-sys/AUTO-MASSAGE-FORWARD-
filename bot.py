import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid

# Logging Setup
logging.basicConfig(level=logging.INFO)

# ==================== ENVIRONMENT VARIABLES ==================== #
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
ADMIN_ID = os.getenv("ADMIN_ID")

if API_ID:
    API_ID = int(API_ID)
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)
else:
    ADMIN_ID = 0
# =============================================================== #

# Flask Web Server (Render 24/7 Keeping Alive)
app = Flask(__name__)

@app.route('/')
def home():
    return "⚡ Broadcaster Bot Server Active 24/7"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

flask_thread = Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# Main Telegram Bot Client
bot = Client(
    "auto_broadcast_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_sessions = {}
temp_login = {}

broadcast_config = {
    "message": None,
    "interval": 60,
    "is_running": False
}

broadcast_task = None

def main_keyboard():
    status_icon = "🟢 RUNNING" if broadcast_config["is_running"] else "🔴 STOPPED"
    msg_icon = "✅ READY" if broadcast_config["message"] else "❌ NOT SET"
    active_count = len(user_sessions)
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ START BROADCAST", callback_data="start_all"),
            InlineKeyboardButton("⏹️ STOP BROADCAST", callback_data="stop_all")
        ],
        [
            InlineKeyboardButton("➕ ADD SESSION", callback_data="login_session"),
            InlineKeyboardButton("🧹 LOGOUT ALL", callback_data="logout_session")
        ],
        [
            InlineKeyboardButton("📝 EDIT MESSAGE", callback_data="set_msg"),
            InlineKeyboardButton("🗑️ CLEAR MSG", callback_data="del_msg")
        ],
        [
            InlineKeyboardButton(f"⏱️ INTERVAL: {broadcast_config['interval']}s", callback_data="set_time")
        ],
        [
            InlineKeyboardButton(f"📊 STATUS: {status_icon}", callback_data="status_info")
        ],
        [
            InlineKeyboardButton(f"📱 SESSIONS ACTIVE: {active_count} | MSG: {msg_icon}", callback_data="status_info2")
        ]
    ])

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    logging.info(f"Received /start from User ID: {user_id}")
    
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await message.reply_text(
            f"🚫 **ACCESS DENIED**\n\n"
            f"👤 **Your User ID:** `{user_id}`\n"
            f"⚠️ You are not authorized to use this control panel.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    text = (
        "✨ **MULTI-ACCOUNT AUTO BROADCASTER** ✨\n"
        "──────────────────────────────\n"
        "Welcome to your Premium Control Dashboard.\n"
        "Manage sessions, configure intervals, and broadcast seamlessly.\n\n"
        f"👑 **Admin ID:** `{user_id}`\n"
        "──────────────────────────────"
    )

    await message.reply_text(text, reply_markup=main_keyboard())

@bot.on_callback_query()
async def callback_handler(client, query):
    user_id = query.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await query.answer("❌ Unauthorized Access!", show_alert=True)
        return

    data = query.data

    if data == "start_all":
        if not broadcast_config["message"]:
            await query.answer("❌ Broadcast Message set nahi hai!", show_alert=True)
            return
        if not user_sessions:
            await query.answer("❌ Koi bhi Active Session logged in nahi hai!", show_alert=True)
            return
        if broadcast_config["is_running"]:
            await query.answer("⚠️ Broadcast pehle se chal raha hai!", show_alert=True)
            return
        
        broadcast_config["is_running"] = True
        global broadcast_task
        broadcast_task = asyncio.create_task(run_broadcast())
        await query.message.edit_text("🚀 **Broadcasting Started Successfully!**", reply_markup=main_keyboard())

    elif data == "stop_all":
        if not broadcast_config["is_running"]:
            await query.answer("⚠️ Broadcast pehle se stopped hai!", show_alert=True)
            return
        
        broadcast_config["is_running"] = False
        if broadcast_task:
            broadcast_task.cancel()
        await query.message.edit_text("🛑 **Broadcasting Stopped!**", reply_markup=main_keyboard())

    elif data == "set_msg":
        await query.message.reply_text(
            "📝 **Broadcast Message Update**\n\n"
            "Kripya apna naya Broadcast Message reply mein bhejen:",
            reply_markup=ForceReply(True)
        )
        await query.answer()

    elif data == "del_msg":
        broadcast_config["message"] = None
        await query.answer("🗑️ Message cleared!", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=main_keyboard())

    elif data == "set_time":
        await query.message.reply_text(
            "⏱️ **Interval Setting**\n\n"
            "Har message ke beech ka gap (Seconds me) reply karein (e.g., 60, 120, 300):",
            reply_markup=ForceReply(True)
        )
        await query.answer()

    elif data == "login_session":
        await query.message.reply_text(
            "📱 **Add New Telegram Account**\n\n"
            "Country Code ke saath Phone Number bhejen (e.g., `+919876543210`):",
            reply_markup=ForceReply(True)
        )
        await query.answer()

    elif data == "logout_session":
        if not user_sessions:
            await query.answer("❌ Koi active sessions nahi hain!", show_alert=True)
            return
        for phone, app_client in list(user_sessions.items()):
            try:
                await app_client.stop()
            except:
                pass
        user_sessions.clear()
        await query.answer("🚪 Saare sessions logout kar diye gaye hain!", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=main_keyboard())

@bot.on_message(filters.reply)
async def handle_replies(client, message):
    user_id = message.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        return

    if not message.reply_to_message or not message.reply_to_message.text:
        return

    reply_text = message.reply_to_message.text.lower()

    # 1. Message Setting
    if "broadcast message" in reply_text:
        broadcast_config["message"] = message.text
        await message.reply_text("✅ **Broadcast Message Updated!**", reply_markup=main_keyboard())

    # 2. Interval Setting
    elif "interval setting" in reply_text or "seconds" in reply_text:
        if message.text.isdigit():
            broadcast_config["interval"] = int(message.text)
            await message.reply_text(f"⏱️ **Interval set to {message.text} Seconds!**", reply_markup=main_keyboard())

    # 3. Phone Number Input
    elif "phone number" in reply_text:
        phone = message.text.strip().replace(" ", "")
        temp_login["phone"] = phone
        user_client = Client(f"session_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await user_client.connect()
        try:
            code_hash = await user_client.send_code(phone)
            temp_login["client"] = user_client
            temp_login["phone_code_hash"] = code_hash.phone_code_hash
            await message.reply_text(
                "📩 **OTP Sent!**\n\n"
                "Telegram par aaya hua Login OTP bhejen.\n"
                "*(Tip: OTP ke beech me spaces dein, e.g., `1 2 3 4 5`)*",
                reply_markup=ForceReply(True)
            )
        except Exception as e:
            await message.reply_text(f"❌ **Login Error:** `{str(e)}`")

    # 4. OTP Input
    elif "otp" in reply_text:
        otp = message.text.replace(" ", "").strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")
        
        if not user_client or not phone:
            await message.reply_text("❌ Login process reset ho gaya hai. Dobara try karein.")
            return

        try:
            await user_client.sign_in(phone, temp_login["phone_code_hash"], otp)
            user_sessions[phone] = user_client
            temp_login.clear()
            await message.reply_text(f"🎉 **Account {phone} Successfully Logged In!**", reply_markup=main_keyboard())

        except SessionPasswordNeeded:
            # 2-Step Verification Password Required
            await message.reply_text(
                "🔐 **2-Step Verification Enabled!**\n\n"
                "Is account par Password laga hua hai. Kripya apna **2FA Password** reply karein:",
                reply_markup=ForceReply(True)
            )

        except PhoneCodeInvalid:
            await message.reply_text("❌ **Invalid OTP!** Kripya sahi OTP bhejen.")

        except Exception as e:
            await message.reply_text(f"❌ **OTP Sign-in Error:** `{str(e)}`")

    # 5. 2FA Password Input
    elif "2-step verification" in reply_text or "password" in reply_text:
        password = message.text.strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")

        if not user_client or not phone:
            await message.reply_text("❌ Login session timeout ho gaya. Dobara Login button dabayein.")
            return

        try:
            await user_client.check_password(password)
            user_sessions[phone] = user_client
            temp_login.clear()
            await message.reply_text(f"🎉 **Account {phone} Successfully Logged In with 2FA!**", reply_markup=main_keyboard())

        except PasswordHashInvalid:
            await message.reply_text("❌ **Incorrect Password!** Sahi password dobara reply karein:", reply_markup=ForceReply(True))

        except Exception as e:
            await message.reply_text(f"❌ **Password Error:** `{str(e)}`")

async def run_broadcast():
    while broadcast_config["is_running"]:
        msg = broadcast_config["message"]
        if not msg:
            break
        for phone, u_client in list(user_sessions.items()):
            try:
                async for dialog in u_client.get_dialogs():
                    if dialog.chat.type.name in ["GROUP", "SUPERGROUP"]:
                        try:
                            await u_client.send_message(dialog.chat.id, msg)
                            await asyncio.sleep(2)
                        except Exception as e:
                            logging.error(f"Failed in {dialog.chat.id}: {e}")
            except Exception as e:
                logging.error(f"Session error for {phone}: {e}")
        await asyncio.sleep(broadcast_config["interval"])

if __name__ == "__main__":
    logging.info("Starting Premium Telegram Bot...")
    bot.run()
