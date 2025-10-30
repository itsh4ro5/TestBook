# -*- coding: utf-8 -*-
import os
import logging
from dotenv import load_dotenv # --- NAYA IMPORT (THEEK KIYA GAYA) ---

# --- NAYA: Load .env file ---
# Yeh line project directory mein .env file ko automatically dhoond kar load karegi
load_dotenv() 
# --- END NAYA ---

logger = logging.getLogger(__name__) # Logger instance banayein

# -----------------------------------------------------------------------------
# Configuration File (Telegram Bot ke liye Updated)
# -----------------------------------------------------------------------------
# Hum sabhi secret keys ko code se nikaal kar Environment Variables
# (jaise Heroku Config Vars ya .env file) se padhenge.
# -----------------------------------------------------------------------------

# --- NAYA (Surakshit Tareeka) ---

# Telegram Bot Token (Environment Variable ya .env file se aayega)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Bot Owner ID (Environment Variable ya .env file se aayega)
# Yeh aapka numeric Telegram User ID hai. Bot sirf aapko respond karega.
# Aap @userinfobot se apna ID le sakte hain.
# Yeh set karna ZAROORI hai.
BOT_OWNER_ID_STR = os.environ.get('BOT_OWNER_ID')

# --- Check aur Type Conversion ---
if not TELEGRAM_BOT_TOKEN:
    # Error log karein taaki console mein dikhe
    logger.critical("CRITICAL ERROR: 'TELEGRAM_BOT_TOKEN' environment variable set nahi hai. Kripya .env file check karein ya environment variable set karein.")
    # Agar token nahi hai toh bot run nahi ho sakta
    raise ValueError("CRITICAL ERROR: 'TELEGRAM_BOT_TOKEN' environment variable set nahi hai.")

BOT_OWNER_ID = None
if not BOT_OWNER_ID_STR:
    logger.critical("CRITICAL ERROR: 'BOT_OWNER_ID' environment variable set nahi hai. Kripya .env file check karein ya environment variable set karein.")
    # Agar owner ID nahi hai toh bot run nahi ho sakta
    raise ValueError("CRITICAL ERROR: 'BOT_OWNER_ID' environment variable set nahi hai.")
else:
    try:
        BOT_OWNER_ID = int(BOT_OWNER_ID_STR)
    except ValueError:
        logger.critical(f"CRITICAL ERROR: 'BOT_OWNER_ID' ({BOT_OWNER_ID_STR}) ek valid number nahi hai.")
        raise ValueError(f"CRITICAL ERROR: 'BOT_OWNER_ID' ({BOT_OWNER_ID_STR}) ek valid number nahi hai.")

# Testbook Auth Token aur Gemini Key ko config.json mein move kar diya gaya hai,
# taaki unhe bot commands se update kiya ja sake.
# Unhe yahaan define karne ki zaroorat nahi hai.

logger.info("Config (.env aur environment variables se) successfully loaded.")
logger.info(f"Bot Owner ID set to: {BOT_OWNER_ID}")
# Token ko log nahi karna chahiye suraksha ke liye
# logger.info(f"Telegram Token Loaded: {'Yes' if TELEGRAM_BOT_TOKEN else 'No'}")

