# -*- coding: utf-8 -*-
import os

# -----------------------------------------------------------------------------
# Configuration File (Telegram Bot ke liye Updated)
# -----------------------------------------------------------------------------
# Hum sabhi secret keys ko code se nikaal kar Environment Variables
# (jaise Heroku Config Vars) se padhenge.
# -----------------------------------------------------------------------------

# --- NAYA (Surakshit Tareeka) ---

# Telegram Bot Token (Heroku Config Vars se aayega)
# Heroku dashboard -> Settings -> Config Vars mein isko set karein
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Bot Owner ID (Heroku Config Vars se aayega)
# Yeh aapka numeric Telegram User ID hai. Bot sirf aapko respond karega.
# Aap @userinfobot se apna ID le sakte hain.
# Yeh set karna ZAROORI hai.
BOT_OWNER_ID_STR = os.environ.get('BOT_OWNER_ID')

# --- Check aur Type Conversion ---
if not TELEGRAM_BOT_TOKEN:
    print("CRITICAL ERROR: 'TELEGRAM_BOT_TOKEN' environment variable set nahi hai.")
    # Agar token nahi hai toh bot run nahi ho sakta
    raise ValueError("CRITICAL ERROR: 'TELEGRAM_BOT_TOKEN' environment variable set nahi hai.")

BOT_OWNER_ID = None
if not BOT_OWNER_ID_STR:
    print("CRITICAL ERROR: 'BOT_OWNER_ID' environment variable set nahi hai.")
    # Agar owner ID nahi hai toh bot run nahi ho sakta
    raise ValueError("CRITICAL ERROR: 'BOT_OWNER_ID' environment variable set nahi hai.")
else:
    try:
        BOT_OWNER_ID = int(BOT_OWNER_ID_STR)
    except ValueError:
        print(f"CRITICAL ERROR: 'BOT_OWNER_ID' ({BOT_OWNER_ID_STR}) ek valid number nahi hai.")
        raise ValueError(f"CRITICAL ERROR: 'BOT_OWNER_ID' ({BOT_OWNER_ID_STR}) ek valid number nahi hai.")

# Testbook Auth Token aur Gemini Key ko config.json mein move kar diya gaya hai,
# taaki unhe bot commands se update kiya ja sake.
# Unhe yahaan define karne ki zaroorat nahi hai.

print("Config loaded successfully.")
print(f"Bot Owner ID set to: {BOT_OWNER_ID}")