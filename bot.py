import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.handlers import MessageHandler
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

# Flask Web Server
app = Flask(__name__)

@app.route('/')
def home():
    return "⚡ Broadcaster Bot Active"

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
    "is_running": False,
    "sent_count": 0,
    "dm_message": None,
    "dm_enabled": False
}

broadcast_task = None

def main_keyboard():
    dm_status = "On 🟢" if broadcast_config.get("dm_enabled") else "Off 🔴"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Start", callback_data="start_all"),
            InlineKeyboardButton("⏹️ Stop", callback_data="stop_all")
        ],
        [
            InlineKeyboardButton("🔑 Login", callback_data="login_session"),
            InlineKeyboardButton("🚪 Logout", callback_data="logout_menu")
        ],
        [
            InlineKeyboardButton("📝 Set Msg", callback_data="set_msg"),
            InlineKeyboardButton("🗑️ Del Msg", callback_data="del_msg")
        ],
        [
            InlineKeyboardButton("🤖 DM Msg", callback_data="set_dm_msg"),
            InlineKeyboardButton(f"⚙️ DM: {dm_status}", callback_data="toggle_dm")
        ],
        [
            InlineKeyboardButton("⏱️ Set Time", callback_data="set_time")
        ]
    ])

def logout_keyboard():
    keyboard = []
    for phone in user_sessions.keys():
        keyboard.append([InlineKeyboardButton(f"❌ Logout: {phone}", callback_data=f"logout_acc_{phone}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_home")])
    return InlineKeyboardMarkup(keyboard)

def get_dashboard_text():
    status = "On 🟢" if broadcast_config["is_running"] else "Off 🔴"
    msg_preview = "Set ✅" if broadcast_config["message"] else "Not Set ❌"
    dm_stat = "On 🟢" if broadcast_config.get("dm_enabled") else "Off 🔴"
    dm_msg_preview = "Set ✅" if broadcast_config.get("dm_message") else "Not Set ❌"
    sent_total = broadcast_config.get("sent_count", 0)
    active_acc = len(user_sessions)
    
    return (
        "⚡ **Broadcaster Panel** ⚡\n"
        "━━━━━━━━━━━━━━━\n"
        f"📊 **Status:** {status}\n"
        f"📨 **Sent Messages:** `{sent_total}`\n"
        f"📱 **Active Accounts:** `{active_acc}`\n"
        f"💬 **Broadcast Msg:** {msg_preview}\n"
        f"🤖 **Auto DM:** {dm_stat} | **DM Msg:** {dm_msg_preview}\n"
        f"⏱️ **Interval:** `{broadcast_config['interval']}s`\n"
        "━━━━━━━━━━━━━━━"
    )

# Incoming DM Auto-Reply Handler function
async def handle_incoming_dm(client, message):
    if broadcast_config.get("dm_enabled") and broadcast_config.get("dm_message"):
        if message.chat.type.name == "PRIVATE":
            try:
                await message.reply_text(broadcast_config["dm_message"])
            except Exception as e:
                logging.error(f"Failed to send Auto DM reply: {e}")

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    logging.info(f"Received /start from User ID: {user_id}")
    
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await message.reply_text(f"⛔ **Access Denied**\nYour ID: `{user_id}`")
        return

    await message.reply_text(get_dashboard_text(), reply_markup=main_keyboard())

@bot.on_callback_query()
async def callback_handler(client, query):
    user_id = query.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await query.answer("❌ Unauthorized!", show_alert=True)
        return

    data = query.data

    if data == "start_all":
        if not broadcast_config["message"]:
            await query.answer("❌ Pehle broadcast message set karein!", show_alert=True)
            return
        if not user_sessions:
            await query.answer("❌ Koi session login nahi hai!", show_alert=True)
            return
        if broadcast_config["is_running"]:
            await query.answer("⚠️ Broadcast pehle se chal raha hai!", show_alert=True)
            return
        
        broadcast_config["is_running"] = True
        global broadcast_task
        broadcast_task = asyncio.create_task(run_broadcast())
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "stop_all":
        if not broadcast_config["is_running"]:
            await query.answer("⚠️ Broadcast pehle se stopped hai!", show_alert=True)
            return
        
        broadcast_config["is_running"] = False
        if broadcast_task:
            broadcast_task.cancel()
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "set_msg":
        await query.message.reply_text("📝 **Send Broadcast Message:**", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "set_dm_msg":
        await query.message.reply_text("🤖 **Send Auto DM Reply Message:**", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "toggle_dm":
        current_state = broadcast_config.get("dm_enabled", False)
        broadcast_config["dm_enabled"] = not current_state
        state_text = "enabled" if broadcast_config["dm_enabled"] else "disabled"
        await query.answer(f"🤖 Auto DM is now {state_text}!", show_alert=True)
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "del_msg":
        broadcast_config["message"] = None
        await query.answer("🗑️ Broadcast message cleared!", show_alert=True)
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "set_time":
        await query.message.reply_text("⏱️ **Send Interval in Seconds (e.g. 60):**", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "login_session":
        await query.message.reply_text("📱 **Send Phone Number (+91...):**", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "logout_menu":
        if not user_sessions:
            await query.answer("❌ Koi active session nahi hai!", show_alert=True)
            return
        await query.message.edit_text("🚪 **Select account to logout:**", reply_markup=logout_keyboard())
        await query.answer()

    elif data.startswith("logout_acc_"):
        phone = data.replace("logout_acc_", "")
        if phone in user_sessions:
            try:
                await user_sessions[phone].stop()
            except:
                pass
            user_sessions.pop(phone, None)
            await query.answer(f"🚪 {phone} logged out successfully!", show_alert=True)
        
        if user_sessions:
            await query.message.edit_text("🚪 **Select account to logout:**", reply_markup=logout_keyboard())
        else:
            await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "back_home":
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

@bot.on_message(filters.reply)
async def handle_replies(client, message):
    user_id = message.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        return

    if not message.reply_to_message or not message.reply_to_message.text:
        return

    reply_text = message.reply_to_message.text.lower()

    if "send broadcast message" in reply_text:
        broadcast_config["message"] = message.text
        await message.reply_text("✅ **Broadcast Message Saved!**", reply_markup=main_keyboard())

    elif "send auto dm reply message" in reply_text:
        broadcast_config["dm_message"] = message.text
        broadcast_config["dm_enabled"] = True
        await message.reply_text("✅ **Auto DM Message Saved & Enabled!**", reply_markup=main_keyboard())

    elif "send interval in seconds" in reply_text:
        if message.text.isdigit():
            broadcast_config["interval"] = int(message.text)
            await message.reply_text(f"⏱️ **Interval Set: {message.text}s**", reply_markup=main_keyboard())

    elif "send phone number" in reply_text:
        phone = message.text.strip().replace(" ", "")
        temp_login["phone"] = phone
        
        user_client = Client(
            f"session_{phone}",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
            device_model="Desktop Client",
            system_version="Windows 11",
            app_version="4.8.1",
            lang_code="en"
        )
        await user_client.connect()
        try:
            code_hash = await user_client.send_code(phone)
            temp_login["client"] = user_client
            temp_login["phone_code_hash"] = code_hash.phone_code_hash
            await message.reply_text("📩 **Send Login OTP:**\n*(Tip: Use spaces e.g. `1 2 3 4 5`)*", reply_markup=ForceReply(True))
        except Exception as e:
            await message.reply_text(f"❌ Error: `{str(e)}`")

    elif "send login otp" in reply_text:
        otp = message.text.replace(" ", "").strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")
        
        if not user_client or not phone:
            await message.reply_text("❌ Session reset. Try again.")
            return

        try:
            await user_client.sign_in(phone, temp_login["phone_code_hash"], otp)
            # Register incoming DM handler for this user client
            user_client.add_handler(MessageHandler(handle_incoming_dm, filters.private & ~filters.me))
            user_sessions[phone] = user_client
            temp_login.clear()
            await message.reply_text(f"🎉 **{phone} Logged In Successfully!**", reply_markup=main_keyboard())

        except SessionPasswordNeeded:
            await message.reply_text("🔐 **Send 2-Step Verification Password:**", reply_markup=ForceReply(True))

        except PhoneCodeInvalid:
            await message.reply_text("❌ Invalid OTP! Try again.")

        except Exception as e:
            await message.reply_text(f"❌ OTP Error: `{str(e)}`")

    elif "send 2-step verification password" in reply_text:
        password = message.text.strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")

        if not user_client or not phone:
            await message.reply_text("❌ Session timeout. Retry again.")
            return

        try:
            await user_client.check_password(password)
            # Register incoming DM handler for this user client
            user_client.add_handler(MessageHandler(handle_incoming_dm, filters.private & ~filters.me))
            user_sessions[phone] = user_client
            temp_login.clear()
            await message.reply_text(f"🎉 **{phone} Logged In with 2FA!**", reply_markup=main_keyboard())

        except PasswordHashInvalid:
            await message.reply_text("❌ Incorrect Password! Try again:", reply_markup=ForceReply(True))

        except Exception as e:
            await message.reply_text(f"❌ Password Error: `{str(e)}`")

async def run_broadcast():
    while broadcast_config["is_running"]:
        msg = broadcast_config["message"]
        if not msg:
            break
        for phone, u_client in list(user_sessions.items()):
            try:
                async for dialog in u_client.get_dialogs():
                    if not broadcast_config["is_running"]:
                        break
                    if dialog.chat.type.name in ["GROUP", "SUPERGROUP"]:
                        try:
                            await u_client.send_message(dialog.chat.id, msg)
                            broadcast_config["sent_count"] = broadcast_config.get("sent_count", 0) + 1
                            await asyncio.sleep(2)
                        except Exception as e:
                            logging.error(f"Failed in {dialog.chat.id}: {e}")
            except Exception as e:
                logging.error(f"Session error for {phone}: {e}")
        await asyncio.sleep(broadcast_config["interval"])

if __name__ == "__main__":
    logging.info("Starting Bot...")
    bot.run()
