import asyncio
import logging
import os
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# ==================== CONFIGURATION ==================== #
BOT_TOKEN = "8948185417:AAELFyo_-xV_34NpLFoMYOOLS1ilYb0Bmyo"  # अपना Bot Token डालें
API_ID = 30694477                   # अपनी API ID डालें
API_HASH = "13ab444dda105878ce293b7da83b3c5a"    # अपना API Hash डालें
ADMIN_ID = 8741889602                 # अपनी Telegram User ID डालें
# ======================================================= #

logging.basicConfig(level=logging.INFO)

# Flask Web Server (Render के लिए)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# Telegram Bot Setup
user_sessions = {}
temp_login = {}

broadcast_config = {
    "message": None,
    "interval": 60,
    "is_running": False
}

broadcast_task = None
bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def main_keyboard():
    status = "🟢 Running" if broadcast_config["is_running"] else "🔴 Stopped"
    msg_status = "✅ Set" if broadcast_config["message"] else "❌ Not Set"
    
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛑 Stop All", callback_data="stop_all"),
            InlineKeyboardButton("▶️ Start All", callback_data="start_all")
        ],
        [
            InlineKeyboardButton("🔑 Login Session", callback_data="login_session"),
            InlineKeyboardButton("🚪 Logout Session", callback_data="logout_session")
        ],
        [
            InlineKeyboardButton("📝 Set Message", callback_data="set_msg"),
            InlineKeyboardButton("🗑️ Delete Message", callback_data="del_msg")
        ],
        [
            InlineKeyboardButton(f"⏱️ Set Interval ({broadcast_config['interval']}s)", callback_data="set_time")
        ],
        [
            InlineKeyboardButton(f"Status: {status} | Msg: {msg_status}", callback_data="status_info")
        ]
    ])

@bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def start_command(client, message):
    await message.reply_text(
        "👋 **Multi-Account Auto Broadcaster Bot में आपका स्वागत है!**\n\n"
        "नीचे दिए गए बटन्स का इस्तेमाल करके कंट्रोल करें:",
        reply_markup=main_keyboard()
    )

@bot.on_callback_query(filters.user(ADMIN_ID))
async def callback_handler(client, query):
    data = query.data

    if data == "start_all":
        if not broadcast_config["message"]:
            await query.answer("❌ पहले Broadcast Message सेट करें!", show_alert=True)
            return
        if not user_sessions:
            await query.answer("❌ कोई Active Login Session नहीं है!", show_alert=True)
            return
        if broadcast_config["is_running"]:
            await query.answer("⚠️ ब्रॉडकास्ट पहले से चल रहा है!", show_alert=True)
            return
        
        broadcast_config["is_running"] = True
        global broadcast_task
        broadcast_task = asyncio.create_task(run_broadcast())
        await query.message.edit_text("🟢 **ब्रॉडकास्ट स्टार्ट हो गया है!**", reply_markup=main_keyboard())

    elif data == "stop_all":
        if not broadcast_config["is_running"]:
            await query.answer("⚠️ ब्रॉडकास्ट पहले से रुका हुआ है!", show_alert=True)
            return
        
        broadcast_config["is_running"] = False
        if broadcast_task:
            broadcast_task.cancel()
        await query.message.edit_text("🔴 **ब्रॉडकास्ट स्टॉप कर दिया गया है!**", reply_markup=main_keyboard())

    elif data == "set_msg":
        await query.message.reply_text("📝 Broadcast Message भेजें:", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "del_msg":
        broadcast_config["message"] = None
        await query.answer("🗑️ Message डिलीट हो गया!", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=main_keyboard())

    elif data == "set_time":
        await query.message.reply_text("⏱️ Interval Time (Seconds में) भेजें (जैसे 60, 300):", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "login_session":
        await query.message.reply_text("📱 Country Code के साथ Phone Number भेजें (जैसे +919876543210):", reply_markup=ForceReply(True))
        await query.answer()

    elif data == "logout_session":
        if not user_sessions:
            await query.answer("❌ कोई session नहीं है!", show_alert=True)
            return
        for phone, app_client in list(user_sessions.items()):
            try:
                await app_client.stop()
            except:
                pass
        user_sessions.clear()
        await query.answer("🚪 सारे sessions logout हो गए!", show_alert=True)
        await query.message.edit_reply_markup(reply_markup=main_keyboard())

@bot.on_message(filters.user(ADMIN_ID) & filters.reply)
async def handle_replies(client, message):
    reply_text = message.reply_to_message.text

    if "broadcast message" in reply_text.lower():
        broadcast_config["message"] = message.text
        await message.reply_text("✅ **Broadcast Message सेट हो गया!**", reply_markup=main_keyboard())

    elif "interval time" in reply_text.lower():
        if message.text.isdigit():
            broadcast_config["interval"] = int(message.text)
            await message.reply_text(f"✅ **Interval {message.text} Seconds सेट हो गया!**", reply_markup=main_keyboard())

    elif "phone number" in reply_text.lower():
        phone = message.text.strip()
        temp_login["phone"] = phone
        user_client = Client(f"session_{phone}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await user_client.connect()
        try:
            code_hash = await user_client.send_code(phone)
            temp_login["client"] = user_client
            temp_login["phone_code_hash"] = code_hash.phone_code_hash
            await message.reply_text("📩 OTP भेज दिया गया है! OTP को स्पेस देकर भेजें (उदा: 1 2 3 4 5):", reply_markup=ForceReply(True))
        except Exception as e:
            await message.reply_text(f"❌ Error: {str(e)}")

    elif "otp" in reply_text.lower():
        otp = message.text.replace(" ", "").strip()
        user_client = temp_login.get("client")
        phone = temp_login.get("phone")
        try:
            await user_client.sign_in(phone, temp_login["phone_code_hash"], otp)
            user_sessions[phone] = user_client
            await message.reply_text(f"🎉 **{phone} सफलतापूर्वक Login हो गया!**", reply_markup=main_keyboard())
        except Exception as e:
            await message.reply_text(f"❌ OTP Error: {str(e)}")

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
                logging.error(f"Session error {phone}: {e}")
        await asyncio.sleep(broadcast_config["interval"])

async def main():
    # Flask Web Server ko background thread me chalana
    import threading
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Bot start karna
    await bot.start()
    logging.info("Bot started successfully!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
