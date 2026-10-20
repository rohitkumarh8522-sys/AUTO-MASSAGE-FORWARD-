import os
import asyncio
import logging
from threading import Thread
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
user_states = {}        
user_panel_msg = {}     

broadcast_config = {
    "message": None,
    "interval": 60,
    "is_running": False,
    "sent_count": 0,
    "dm_message": None
}

broadcast_task = None

def main_keyboard():
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
            InlineKeyboardButton("🤖 DM Msg", callback_data="dm_menu"),
            InlineKeyboardButton("⏱️ Set Time", callback_data="set_time")
        ]
    ])

def dm_keyboard():
    dm_preview = "✅ Set" if broadcast_config.get("dm_message") else "❌ Not Set"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"Status: {dm_preview}", callback_data="noop")
        ],
        [
            InlineKeyboardButton("➕ Set DM", callback_data="set_dm_msg"),
            InlineKeyboardButton("🗑️ Del DM", callback_data="del_dm_msg")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="back_home")
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
    sent_total = broadcast_config.get("sent_count", 0)
    active_acc = len(user_sessions)
    
    return (
        "⚡ **Broadcaster Panel** ⚡\n"
        "━━━━━━━━━━━━━━━\n"
        f"📊 **Status:** {status}\n"
        f"📨 **Sent Messages:** `{sent_total}`\n"
        f"📱 **Active Accounts:** `{active_acc}`\n"
        f"💬 **Message:** {msg_preview}\n"
        f"⏱️ **Interval:** `{broadcast_config['interval']}s`\n"
        "━━━━━━━━━━━━━━━"
    )

# Incoming DM Auto-Reply Handler
async def handle_incoming_dm(client, message):
    if broadcast_config.get("dm_message"):
        if message.chat.type.name == "PRIVATE":
            try:
                await message.reply_text(broadcast_config["dm_message"])
            except Exception as e:
                logging.error(f"Failed to send Auto DM reply: {e}")

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    logging.info(f"Received /start from User ID: {user_id}")
    
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await message.reply_text(f"⛔ **Access Denied**\nYour ID: `{user_id}`")
        return

    sent = await message.reply_text(get_dashboard_text(), reply_markup=main_keyboard())
    user_panel_msg[user_id] = sent.id

@bot.on_callback_query()
async def callback_handler(client, query):
    user_id = query.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await query.answer("❌ Unauthorized!", show_alert=True)
        return

    data = query.data
    user_panel_msg[user_id] = query.message.id

    if data == "noop":
        await query.answer()
        return

    if data == "start_all":
        if not broadcast_config["message"]:
            await query.answer("❌ Pehle message set karein!", show_alert=True)
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
        user_states[user_id] = "waiting_broadcast_msg"
        await query.message.edit_text("📝 **Naya Broadcast Message yahan type karein:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

    elif data == "dm_menu":
        await query.message.edit_text("🤖 **Auto DM Menu:**", reply_markup=dm_keyboard())

    elif data == "set_dm_msg":
        user_states[user_id] = "waiting_dm_msg"
        await query.message.edit_text("🤖 **Naya Auto DM Message yahan type karein:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="dm_menu")]]))

    elif data == "del_dm_msg":
        broadcast_config["dm_message"] = None
        await query.answer("🗑️ Auto DM message deleted!", show_alert=True)
        await query.message.edit_text("🤖 **Auto DM Menu:**", reply_markup=dm_keyboard())

    elif data == "del_msg":
        broadcast_config["message"] = None
        await query.answer("🗑️ Broadcast message cleared!", show_alert=True)
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

    elif data == "set_time":
        user_states[user_id] = "waiting_interval"
        await query.message.edit_text("⏱️ **Interval seconds mein type karein (jaise 60):**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

    elif data == "login_session":
        user_states[user_id] = "waiting_phone"
        await query.message.edit_text("📱 **Phone number type karein (+91...):**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

    elif data == "logout_menu":
        if not user_sessions:
            await query.answer("❌ Koi active session nahi hai!", show_alert=True)
            return
        await query.message.edit_text("🚪 **Select account to logout:**", reply_markup=logout_keyboard())

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
        user_states.pop(user_id, None)
        await query.message.edit_text(get_dashboard_text(), reply_markup=main_keyboard())

@bot.on_message(filters.text & ~filters.command("start"))
async def handle_text_inputs(client, message):
    user_id = message.from_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        return

    state = user_states.get(user_id)
    if not state:
        return

    try:
        await message.delete()
    except:
        pass

    text = message.text.strip()
    panel_id = user_panel_msg.get(user_id)

    async def update_panel(new_text, markup):
        if panel_id:
            try:
                await client.edit_message_text(message.chat.id, panel_id, new_text, reply_markup=markup)
                return
            except:
                pass
        sent = await client.send_message(message.chat.id, new_text, reply_markup=markup)
        user_panel_msg[user_id] = sent.id

    if state == "waiting_broadcast_msg":
        broadcast_config["message"] = message.text
        user_states.pop(user_id, None)
        await update_panel(get_dashboard_text(), main_keyboard())

    elif state == "waiting_dm_msg":
        broadcast_config["dm_message"] = message.text
        user_states.pop(user_id, None)
        await update_panel("🤖 **Auto DM Menu:**", dm_keyboard())

    elif state == "waiting_interval":
        if text.isdigit():
            broadcast_config["interval"] = int(text)
            user_states.pop(user_id, None)
            await update_panel(get_dashboard_text(), main_keyboard())
        else:
            await update_panel("❌ Kripya sirf valid number bhejen (jaise 60):", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

    elif state == "waiting_phone":
        phone = text.replace(" ", "")
        temp_login["phone"] = phone
        
        # Fixed stable session parameters to prevent phone logout conflicts
        user_client = Client(
            f"session_{phone.replace('+', '')}",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
            device_model="PC 64bit",
            system_version="Windows 11",
            app_version="4.8.1",
            lang_code="en"
        )
        await user_client.connect()
        try:
            code_hash = await user_client.send_code(phone)
            temp_login["client"] = user_client
            temp_login["phone_code_hash"] = code_hash.phone_code_hash
            user_states[user_id] = "waiting_otp"
            await update_panel("📩 **OTP bhej diya gaya hai!**\nTelegram OTP yahan type karein (jaise `1 2 3 4 5`):", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))
        except Exception as e:
            user_states.pop(user_id, None)
            await update_panel(f"❌ Error: `{str(e)}`", main_keyboard())

    elif state == "waiting_otp":
        otp = text.replace(" ", "")
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")
        
        if not user_client or not phone:
            user_states.pop(user_id, None)
            await update_panel(get_dashboard_text(), main_keyboard())
            return

        try:
            await user_client.sign_in(phone, temp_login["phone_code_hash"], otp)
            user_client.add_handler(MessageHandler(handle_incoming_dm, filters.private & ~filters.me))
            user_sessions[phone] = user_client
            temp_login.clear()
            user_states.pop(user_id, None)
            await update_panel(get_dashboard_text(), main_keyboard())

        except SessionPasswordNeeded:
            user_states[user_id] = "waiting_2fa"
            await update_panel("🔐 **2-Step Verification Password type karein:**", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

        except PhoneCodeInvalid:
            await update_panel("❌ **Galat OTP!** Sahi OTP dobara type karein:", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

        except Exception as e:
            user_states.pop(user_id, None)
            await update_panel(f"❌ Error: `{str(e)}`", main_keyboard())

    elif state == "waiting_2fa":
        password = message.text.strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")

        if not user_client or not phone:
            user_states.pop(user_id, None)
            await update_panel(get_dashboard_text(), main_keyboard())
            return

        try:
            await user_client.check_password(password)
            user_client.add_handler(MessageHandler(handle_incoming_dm, filters.private & ~filters.me))
            user_sessions[phone] = user_client
            temp_login.clear()
            user_states.pop(user_id, None)
            await update_panel(get_dashboard_text(), main_keyboard())

        except PasswordHashInvalid:
            await update_panel("❌ **Galat Password!** Sahi password dobara type karein:", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="back_home")]]))

        except Exception as e:
            user_states.pop(user_id, None)
            await update_panel(f"❌ Error: `{str(e)}`", main_keyboard())

async def run_broadcast():
    while broadcast_config["is_running"]:
        msg = broadcast_config["message"]
        if not msg:
            broadcast_config["is_running"] = False
            break
        
        for phone, u_client in list(user_sessions.items()):
            if not broadcast_config["is_running"]:
                break
            try:
                async for dialog in u_client.get_dialogs():
                    if not broadcast_config["is_running"]:
                        break
                    chat_type = str(dialog.chat.type).lower()
                    if "group" in chat_type or "supergroup" in chat_type:
                        try:
                            await u_client.send_message(dialog.chat.id, msg)
                            broadcast_config["sent_count"] = broadcast_config.get("sent_count", 0) + 1
                            await asyncio.sleep(2)
                        except Exception as e:
                            logging.error(f"Failed in {dialog.chat.id}: {e}")
            except Exception as e:
                logging.error(f"Session error for {phone}: {e}")
        
        # Fixed Continuous Interval Loop (Rechecks every second so stop works instantly)
        interval = broadcast_config.get("interval", 60)
        for _ in range(interval):
            if not broadcast_config["is_running"]:
                break
            await asyncio.sleep(1)

if __name__ == "__main__":
    logging.info("Starting Bot...")
    bot.run()
