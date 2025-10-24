# -*- coding: utf-8 -*-
import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    ConversationHandler, MessageHandler, Filters
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import io
import asyncio  # Live progress bar ke liye
import time

from extractor import TestbookExtractor
from html_generator import generate_html
from config import TELEGRAM_BOT_TOKEN, BOT_OWNER_ID

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration Files ---
ADMIN_FILE = 'admins.json'
CONFIG_FILE = 'config.json'

# --- State Definitions for Bulk Download ---
ASK_EXTRACTOR_NAME, ASK_DESTINATION = range(2)

# --- Config & Admin Helper Functions ---

def load_admins():
    """Admins file se admin IDs load karta hai."""
    if not os.path.exists(ADMIN_FILE):
        save_admins([])
        return []
    try:
        with open(ADMIN_FILE, 'r') as f:
            return json.load(f).get('admin_ids', [])
    except json.JSONDecodeError:
        return []

def save_admins(admin_list):
    """Admin IDs ko file mein save karta hai."""
    with open(ADMIN_FILE, 'w') as f:
        json.dump({'admin_ids': admin_list}, f, indent=4)

def load_config():
    """Config file (token/channel) load karta hai."""
    if not os.path.exists(CONFIG_FILE):
        save_config(None, None)
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_config(token, channel_id):
    """Config ko file mein save karta hai."""
    config = load_config()
    if token is not None:
        config['testbook_auth_token'] = token
    if channel_id is not None:
        config['forward_channel_id'] = channel_id
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_config(key):
    """Config file se ek specific key ki value laata hai."""
    return load_config().get(key)

# --- Decorators for Auth ---

def is_owner(user_id):
    """Check karta hai ki user owner hai ya nahi."""
    return user_id == BOT_OWNER_ID

def is_admin(user_id):
    """Check karta hai ki user admin hai ya nahi."""
    return user_id in load_admins()

def admin_required(func):
    """Decorator jo check karta hai ki user owner ya admin hai."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not (is_owner(user_id) or is_admin(user_id)):
            await update.message.reply_text("❌ Shama karein, aap is command ka istemal karne ke liye authorized nahi hain.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def owner_required(func):
    """Decorator jo check karta hai ki user owner hai."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not is_owner(user_id):
            await update.message.reply_text("❌ Shama karein, sirf bot owner hi is command ka istemal kar sakta hai.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Bot Commands Setup ---
async def set_bot_commands(application: Application):
    """Bot ke menu mein dikhne waale commands set karta hai."""
    owner_commands = [
        BotCommand("start", "Bot ko start karein"),
        BotCommand("menu", "Mukhya menu (search) dikhayein"),
        BotCommand("stop", "Current bulk download rokein"),
        BotCommand("settoken", "Testbook token set/update karein (Owner)"),
        BotCommand("setchannel", "Default forward channel set karein (Admin)"),
        BotCommand("removechannel", "Forward channel hatayein (Admin)"),
        BotCommand("viewchannel", "Current channel ID dekhein (Admin)"),
        BotCommand("addadmin", "Naya admin add karein (Owner)"),
        BotCommand("removeadmin", "Admin ko remove karein (Owner)"),
        BotCommand("adminlist", "Sabhi admins ki list dekhein (Owner)"),
    ]
    await application.bot.set_my_commands(owner_commands)

# --- Utility Functions ---
async def clear_previous_message(context: ContextTypes.DEFAULT_TYPE):
    """Bot ke pichhle message ko delete karta hai (chat saaf rakhne ke liye)."""
    if 'last_bot_message_id' in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=context.user_data['chat_id'],
                message_id=context.user_data['last_bot_message_id']
            )
        except (BadRequest, Forbidden) as e:
            logger.warning(f"Purana message delete nahi kar saka: {e}")
        finally:
            del context.user_data['last_bot_message_id']

# --- Owner Commands ---

@owner_required
async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner) Testbook Auth Token ko update karta hai."""
    if not context.args:
        await update.message.reply_text("Istemal: /settoken <Naya Token Yahaan>")
        return
    
    new_token = context.args[0]
    save_config(token=new_token, channel_id=None)
    
    # Global extractor ko update karne ki koshish (agar zaroori ho)
    try:
        context.bot_data['extractor'] = TestbookExtractor(new_token)
        logger.info("Global extractor token updated.")
    except Exception as e:
        logger.error(f"Extractor update karte waqt error: {e}")

    await update.message.reply_text("✅ Testbook token safaltapoorvak update ho gaya hai!")

@admin_required
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Default forward channel ID set karta hai."""
    if not context.args:
        await update.message.reply_text("Istemal: /setchannel <Channel/Group ID> (jaise -100...)\n\n"
                                        "Note: Bot us channel/group mein admin hona chahiye.")
        return
    
    try:
        new_channel_id = int(context.args[0])
        save_config(token=None, channel_id=new_channel_id)
        await update.message.reply_text(f"✅ Default forward channel ID safaltapoorvak set ho gaya hai: `{new_channel_id}`")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. ID hamesha ek number hota hai (group/channel ke liye -100 se shuru hota hai).")

@admin_required
async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Forward channel ID ko hata deta hai."""
    save_config(token=None, channel_id=None) # None set karke remove karein
    await update.message.reply_text("✅ Default forward channel safaltapoorvak hata diya gaya hai.")

@admin_required
async def view_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin) Current forward channel ID dikhata hai."""
    channel_id = get_config('forward_channel_id')
    if channel_id:
        await update.message.reply_text(f"ℹ️ Current default forward channel ID hai: `{channel_id}`")
    else:
        await update.message.reply_text("ℹ️ Abhi koi default forward channel set nahi hai.")

@owner_required
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner) Naya admin add karta hai."""
    if not context.args:
        await update.message.reply_text("Istemal: /addadmin <User ID>")
        return
    
    try:
        new_admin_id = int(context.args[0])
        admins = load_admins()
        if new_admin_id not in admins:
            admins.append(new_admin_id)
            save_admins(admins)
            await update.message.reply_text(f"✅ Admin `{new_admin_id}` safaltapoorvak add ho gaya hai.")
        else:
            await update.message.reply_text(f"ℹ️ User `{new_admin_id}` pehle se hi admin hai.")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID. ID hamesha ek number hota hai.")

@owner_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner) Admin ko remove karta hai."""
    if not context.args:
        await update.message.reply_text("Istemal: /removeadmin <User ID>")
        return

    try:
        admin_to_remove = int(context.args[0])
        admins = load_admins()
        if admin_to_remove in admins:
            admins.remove(admin_to_remove)
            save_admins(admins)
            await update.message.reply_text(f"✅ Admin `{admin_to_remove}` safaltapoorvak remove ho gaya hai.")
        else:
            await update.message.reply_text(f"ℹ️ User `{admin_to_remove}` admin list mein nahi hai.")
    except ValueError:
        await update.message.reply_text("❌ Invalid User ID. ID hamesha ek number hota hai.")

@owner_required
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner) Sabhi admins ki list dikhata hai."""
    admins = load_admins()
    if not admins:
        await update.message.reply_text("ℹ️ Abhi koi admin add nahi hua hai.")
        return
    
    admin_list_str = "\n".join([f"- `{admin_id}`" for admin_id in admins])
    await update.message.reply_text(f"👑 **Current Admin List:**\n{admin_list_str}")

# --- Main Bot Logic ---

@admin_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command handle karta hai."""
    user = update.effective_user
    await update.message.reply_text(
        f"👋 **Welcome, {user.first_name}!**\n\n"
        f"Main Testbook se tests extract karne mein aapki madad kar sakta hoon.\n\n"
        f"Apna search shuru karne ke liye /menu type karein.",
        parse_mode=ParseMode.MARKDOWN
    )
    # Purana conversation state clear karein (agar koi ho)
    context.user_data.clear()

@admin_required
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/menu command handle karta hai aur search prompt dikhata hai."""
    await clear_previous_message(context)
    message = await update.message.reply_text("🔍 **Aap kya search karna chahte hain?**\n\n"
                                              "Test series ka naam type karein (jaise 'SSC CGL', 'Banking', 'Railways').")
    context.user_data['last_bot_message_id'] = message.message_id
    context.user_data['chat_id'] = update.message.chat_id

@admin_required
async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search results (Test Series) dikhata hai."""
    await clear_previous_message(context)
    query = context.user_data.get('last_search_query', 'Unknown Query')
    results = context.user_data.get('search_results', [])
    
    if not results:
        message = await update.callback_query.message.reply_text(f"❌ '{query}' ke liye koi results nahi mile.")
        context.user_data['last_bot_message_id'] = message.message_id
        return

    buttons = []
    for i, series in enumerate(results):
        buttons.append([InlineKeyboardButton(series.get('name', 'N/A'), callback_data=f"series_{i}")])
    
    buttons.append([InlineKeyboardButton("🔙 Naya Search", callback_data="main_menu")])
    
    message = await update.callback_query.message.reply_text(
        f"📚 **'{query}' ke liye results:**\n\nEk test series chunein:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_bot_message_id'] = message.message_id
    await update.callback_query.answer()

@admin_required
async def series_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ek series ke sections dikhata hai."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        # /menu command ko simulate karein
        await show_menu(query, context)
        return

    series_index = int(query.data.split('_')[1])
    context.user_data['current_series_index'] = series_index
    
    results = context.user_data.get('search_results', [])
    selected_series = results[series_index]
    
    token = get_config('testbook_auth_token')
    if not token:
        await query.message.reply_text("❌ Token set nahi hai. Kripya owner se /settoken ka istemal karne ko kahein.")
        return

    extractor = TestbookExtractor(token)
    
    await clear_previous_message(context)
    loading_msg = await query.message.reply_text(f"⏳ '{selected_series.get('name')}' ke sections load kiye ja rahe hain...")
    
    details = extractor.get_series_details(selected_series.get('slug'))
    if not details:
        await loading_msg.edit_text("❌ Is series ke details fetch nahi kar paya.")
        return

    context.user_data['series_details'] = details
    sections = details.get('sections', [])
    
    buttons = []
    for i, section in enumerate(sections):
        buttons.append([InlineKeyboardButton(section.get('name', 'N/A'), callback_data=f"section_{i}")])
    
    buttons.append([InlineKeyboardButton("🔙 Peeche (Series List)", callback_data="search_results")])
    
    await loading_msg.edit_text(
        f"🗂️ **{details.get('name')}**\n\nEk section chunein:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_bot_message_id'] = loading_msg.message_id

@admin_required
async def section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ek section ke subsections dikhata hai."""
    query = update.callback_query
    await query.answer()

    if query.data == "search_results":
        await search_callback(query, context)
        return
    
    # Check karein ki yeh bulk download ka start hai ya nahi
    if query.data.startswith("bulk_section_"):
        # Yeh ConversationHandler dwaara handle kiya jayega
        # Yahaan alag se handle karne ki zaroorat nahi hai
        logger.info("Bulk section download conversation entry point.")
        return

    section_index = int(query.data.split('_')[1])
    context.user_data['current_section_index'] = section_index
    
    series_details = context.user_data.get('series_details', {})
    selected_section = series_details.get('sections', [])[section_index]
    context.user_data['selected_section'] = selected_section
    
    subsections = selected_section.get('subsections', [])
    
    buttons = []
    for i, sub in enumerate(subsections):
        buttons.append([InlineKeyboardButton(sub.get('name', 'N/A'), callback_data=f"subsection_{i}")])
    
    # Bulk Download Button (Entry point for conversation)
    bulk_callback_data = f"bulk_section_{context.user_data['current_series_index']}_{section_index}"
    buttons.append([InlineKeyboardButton("📥 Download All Tests", callback_data=bulk_callback_data)])
    
    buttons.append([InlineKeyboardButton(f"🔙 Peeche ({series_details.get('name', 'Series')})", callback_data=f"series_{context.user_data['current_series_index']}")])
    
    await clear_previous_message(context)
    message = await query.message.reply_text(
        f"📂 **{selected_section.get('name')}**\n\nEk subsection chunein:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_bot_message_id'] = message.message_id

@admin_required
async def subsection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ek subsection ke tests ki list (.txt file) bhejta hai."""
    query = update.callback_query
    await query.answer()

    series_details = context.user_data.get('series_details', {})
    section_index = context.user_data.get('current_section_index', 0)
    
    if query.data == f"section_{section_index}":
        # Peeche jaane ke liye series_callback ko call na karein, section_callback ko karein
        # (Lekin series_callback ka data use karna hoga)
        # Simple: series_callback ko call karein taaki woh sections dikha de
        
        # Series index ko context se lein
        series_index = context.user_data.get('current_series_index', 0)
        query.data = f"series_{series_index}" # Query data ko modify karein
        await series_callback(update, context) # Ab series_callback handle karega
        return

    # Check karein ki yeh bulk download ka start hai ya nahi
    if query.data.startswith("bulk_subsection_"):
        # Yeh ConversationHandler dwaara handle kiya jayega
        logger.info("Bulk subsection download conversation entry point.")
        return

    subsection_index = int(query.data.split('_')[1])
    context.user_data['current_subsection_index'] = subsection_index
    
    selected_section = context.user_data.get('selected_section', {})
    selected_subsection = selected_section.get('subsections', [])[subsection_index]
    context.user_data['selected_subsection'] = selected_subsection

    token = get_config('testbook_auth_token')
    if not token:
        await query.message.reply_text("❌ Token set nahi hai. Kripya owner se /settoken ka istemal karne ko kahein.")
        return

    extractor = TestbookExtractor(token)
    
    await clear_previous_message(context)
    loading_msg = await query.message.reply_text(f"⏳ '{selected_subsection.get('name')}' ke tests fetch kiye ja rahe hain...")
    
    tests = extractor.get_tests_in_subsection(
        series_details.get('id'),
        selected_section.get('id'),
        selected_subsection.get('id')
    )
    
    if not tests:
        await loading_msg.edit_text("❌ Is subsection mein koi test nahi mila.")
        # Peeche jaane ka button provide karein
        buttons = [[InlineKeyboardButton(f"🔙 Peeche ({selected_section.get('name', 'Section')})", callback_data=f"section_{section_index}")]]
        await loading_msg.reply_text("Wapas jaane ke liye click karein:", reply_markup=InlineKeyboardMarkup(buttons))
        context.user_data['last_bot_message_id'] = loading_msg.message_id + 1 # Next message ID
        return

    context.user_data['last_tests_list'] = tests
    
    # .txt file banayein
    test_list_str = f"--- {selected_subsection.get('name')} ---\n\n"
    for i, test in enumerate(tests):
        test_list_str += f"{i+1}. {test.get('title', 'N/A')}\n"
    
    txt_file = io.BytesIO(test_list_str.encode('utf-8'))
    txt_file.name = f"{selected_subsection.get('name', 'tests')}.txt"
    
    await loading_msg.delete() # Loading message hata dein
    
    # File bhejें
    await query.message.reply_document(
        document=txt_file,
        caption=(
            f"📄 **{selected_subsection.get('name')}** ke liye **{len(tests)}** tests mile.\n\n"
            "Download karne ke liye file se test ka **number** type karke reply karein (jaise '1', '5', '23')."
        )
    )
    
    # Bulk Download Button
    bulk_callback_data = f"bulk_subsection_{subsection_index}"
    buttons = [
        [InlineKeyboardButton("📥 Download All Tests", callback_data=bulk_callback_data)],
        [InlineKeyboardButton(f"🔙 Peeche ({selected_section.get('name', 'Section')})", callback_data=f"section_{section_index}")]
    ]
    
    message = await query.message.reply_text(
        "Aap sabhi tests ek saath download kar sakte hain, ya peeche ja sakte hain:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_bot_message_id'] = message.message_id

@admin_required
async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text input ko handle karta hai (Search query ya Test number)."""
    text = update.message.text
    
    # Check karein ki kya yeh test number hai
    if text.isdigit() and 'last_tests_list' in context.user_data:
        await clear_previous_message(context) # Test number wala message clear karein
        
        test_index = int(text) - 1
        tests = context.user_data.get('last_tests_list', [])
        
        if 0 <= test_index < len(tests):
            selected_test = tests[test_index]
            
            # Context se baaki details lein
            series_details = context.user_data.get('series_details', {})
            selected_section = context.user_data.get('selected_section', {})
            selected_subsection = context.user_data.get('selected_subsection', {})
            
            token = get_config('testbook_auth_token')
            if not token:
                await update.message.reply_text("❌ Token set nahi hai. Kripya owner se /settoken ka istemal karne ko kahein.")
                return

            extractor = TestbookExtractor(token)
            
            loading_msg = await update.message.reply_text(f"⏳ Test #{test_index+1} ('{selected_test.get('title')}') extract kiya ja raha hai...")
            
            test_id = selected_test.get('id')
            questions_data = extractor.extract_questions(test_id)
            
            if questions_data.get('error'):
                await loading_msg.edit_text(f"❌ Test extract karne mein error: {questions_data.get('error')}")
                return

            # NAYA: Extractor name = None (single download ke liye)
            caption = extractor.get_caption(selected_test, series_details, selected_section, selected_subsection, extractor_name=None)
            
            html_content = generate_html(questions_data, extractor.last_details)
            html_file = io.BytesIO(html_content.encode('utf-8'))
            file_name = f"{selected_test.get('title', 'test').replace('/', '_')}.html"
            
            await loading_msg.delete()
            
            # File ko user ko DM karein
            await update.message.reply_document(
                document=InputFile(html_file, filename=file_name),
                caption=caption,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # File ko default channel mein forward karein (agar set hai)
            channel_id = get_config('forward_channel_id')
            if channel_id:
                try:
                    await context.bot.send_document(
                        chat_id=channel_id,
                        document=InputFile(html_file, filename=file_name),
                        caption=caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Channel {channel_id} par forward karne mein error: {e}")
                    await update.message.reply_text(f"⚠️ Warning: File channel {channel_id} par forward nahi ho saki. (Error: {e})")

        else:
            await update.message.reply_text("❌ Invalid test number. Kripya .txt file se sahi number chunein.")
        
    # Agar yeh search query hai
    else:
        context.user_data['last_search_query'] = text
        token = get_config('testbook_auth_token')
        if not token:
            await update.message.reply_text("❌ Token set nahi hai. Kripya owner se /settoken ka istemal karne ko kahein.")
            return

        extractor = TestbookExtractor(token)
        
        await clear_previous_message(context)
        loading_msg = await update.message.reply_text(f"⏳ '{text}' ke liye search kiya ja raha hai...")
        
        results = extractor.search(text)
        context.user_data['search_results'] = results
        
        # search_callback ko manually call karein
        # (CallbackQuery simulate karna thoda mushkil hai, isliye function ko seedha call karein
        # lekin 'update' object ko modify karna hoga)
        
        # Aasaan tareeka: Sirf message edit karein aur user ko batayein
        if not results:
            await loading_msg.edit_text(f"❌ '{text}' ke liye koi results nahi mile. Dobara try karein.")
            context.user_data['last_bot_message_id'] = loading_msg.message_id
            return

        buttons = []
        for i, series in enumerate(results):
            buttons.append([InlineKeyboardButton(series.get('name', 'N/A'), callback_data=f"series_{i}")])
        
        buttons.append([InlineKeyboardButton("🔙 Naya Search", callback_data="main_menu")])
        
        await loading_msg.edit_text(
            f"📚 **'{text}' ke liye results:**\n\nEk test series chunein:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        context.user_data['last_bot_message_id'] = loading_msg.message_id


# --- BULK DOWNLOAD CONVERSATION ---

@admin_required
async def bulk_download_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bulk download conversation shuru karta hai. Pehle 'Extracted By' naam poochta hai.
    """
    query = update.callback_query
    await query.answer()
    query_data = query.data
    
    # Callback data ko user_data mein store karein taaki baad mein use kar sakein
    context.user_data['bulk_query_data'] = query_data
    
    # Purana message clear karein
    await clear_previous_message(context)
    
    message = await query.message.reply_text(
        "📝 **Extractor Ka Naam Darj Karein:**\n\n"
        "Aap jo naam yahaan denge (jaise 'H4R'), woh har file ke caption mein 'Extracted By: H4R' bankar jud jayega.\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    context.user_data['last_bot_message_id'] = message.message_id
    
    return ASK_EXTRACTOR_NAME

@admin_required
async def receive_extractor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Extractor ka naam save karta hai aur destination poochta hai.
    """
    extractor_name = update.message.text
    context.user_data['extractor_name'] = extractor_name
    
    # User ka message delete karein (naam wala)
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"User message delete nahi kar saka: {e}")

    # Purana message clear karein (bot ka prompt wala)
    await clear_previous_message(context)
    
    default_channel_id = get_config('forward_channel_id') or "N/A"
    destination_text = (
        f"✅ Extractor ka naam set: **{extractor_name}**\n\n"
        "📍 **Destination Chunein:**\n"
        "Aapko yeh sabhi files kahaan bhejni hain?\n\n"
        f"1️⃣ Type `/d` - Default Channel mein bhejne ke liye (ID: `{default_channel_id}`)\n"
        "2️⃣ Type `1` - Mujhe isi chat mein bhejne ke liye (Private).\n"
        "3️⃣ Type `-100...` - Kisi naye specific Channel/Group ID mein bhejne ke liye.\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    
    message = await update.message.reply_text(destination_text, parse_mode=ParseMode.MARKDOWN)
    context.user_data['last_bot_message_id'] = message.message_id

    return ASK_DESTINATION

@admin_required
async def receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Destination save karta hai aur bulk download shuru karta hai.
    """
    destination_choice = update.message.text
    context.user_data['destination_choice'] = destination_choice
    
    # User ka message delete karein (destination wala)
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"User message delete nahi kar saka: {e}")
        
    # Purana message clear karein (bot ka prompt wala)
    await clear_previous_message(context)
    
    # Asli bulk download function ko call karein (ab yeh naya function hai)
    await perform_bulk_download(update, context)
    
    # Conversation khatm karein
    return ConversationHandler.END

async def cancel_bulk_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bulk download conversation ko /cancel se rokta hai.
    """
    await clear_previous_message(context)
    await update.message.reply_text("Bulk download setup cancel kar diya gaya hai.")
    
    # context.user_data se temporary keys clear karein
    context.user_data.pop('bulk_query_data', None)
    context.user_data.pop('extractor_name', None)
    context.user_data.pop('destination_choice', None)
    
    return ConversationHandler.END

# --- Bulk Download Logic (Updated) ---
async def perform_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asli bulk download logic, ab extractor_name aur destination ke saath.
    """
    # Conversation se data retrieve karein
    query_data = context.user_data.pop('bulk_query_data', None)
    extractor_name = context.user_data.pop('extractor_name', None)
    destination_choice = context.user_data.pop('destination_choice', None)
    user_chat_id = update.effective_chat.id

    if not all([query_data, extractor_name, destination_choice]):
        await update.message.reply_text("❌ **Error:** Conversation data missing. Kripya /start se dobara shuru karein.")
        return

    # Destination ID tay karein
    final_chat_id = None
    if destination_choice == '1':
        final_chat_id = user_chat_id
    elif destination_choice == '/d':
        final_chat_id = get_config('forward_channel_id')
        if not final_chat_id:
            await update.message.reply_text("❌ **Error:** Aapne default channel chuna, lekin koi default channel set nahi hai. Kripya pehle `/setchannel` ka istemal karein.")
            return
    else:
        try:
            final_chat_id = int(destination_choice)
        except ValueError:
            await update.message.reply_text("❌ **Error:** Invalid destination. Kripya `1`, `/d`, ya ek valid channel ID (jaise -100...) type karein.")
            return

    # User ko batayein ki process shuru ho gaya hai (sirf private chat mein)
    progress_message = await context.bot.send_message(chat_id=user_chat_id, text=f"⚙️ Bulk download shuru ho raha hai...\nDestination: `{final_chat_id}`")
    
    token = get_config('testbook_auth_token')
    if not token:
        await progress_message.edit_text("❌ Token not set. Use /settoken.")
        return
        
    extractor = TestbookExtractor(token)
    series_details = context.user_data.get('series_details')
    
    if not series_details:
        await progress_message.edit_text("❌ Session expire ho gaya hai, /start se shuru karein.")
        return

    # Stop flag reset karein
    context.bot_data[user_chat_id] = {'stop_flag': False}
    
    total_tests = 0
    completed_tests = 0
    
    try:
        tests_to_process = []
        
        if query_data.startswith("bulk_section_"):
            _, series_idx, section_idx = query_data.split('_')
            selected_section = series_details.get('sections', [])[int(series_idx)]
            subsections = selected_section.get('subsections', [])
            
            await progress_message.edit_text(f"⏳ **{selected_section.get('name')}** ke liye tests ki jaankari ikatthi ki ja rahi hai...")
            
            # Pehle sabhi tests ki list jama karein
            for sub in subsections:
                tests = extractor.get_tests_in_subsection(series_details['id'], selected_section['id'], sub['id'])
                if tests:
                    tests_to_process.extend([(test, selected_section, sub) for test in tests])
            total_tests = len(tests_to_process)
            
            if total_tests == 0:
                await progress_message.edit_text("❌ Is section mein koi test nahi mila.")
                return

            await progress_message.edit_text(f"📥 **{selected_section.get('name')}** ke liye {total_tests} tests download ho rahe hain...")

        elif query_data.startswith("bulk_subsection_"):
            _, subsection_idx = query_data.split('_')
            selected_section = context.user_data.get('selected_section')
            selected_subsection = selected_section.get('subsections', [])[int(subsection_idx)]
            
            await progress_message.edit_text(f"⏳ **{selected_subsection.get('name')}** ke liye tests ki jaankari ikatthi ki ja rahi hai...")
            
            tests = extractor.get_tests_in_subsection(series_details['id'], selected_section['id'], selected_subsection['id'])
            total_tests = len(tests) if tests else 0

            if total_tests == 0:
                await progress_message.edit_text("❌ Is subsection mein koi test nahi mila.")
                return

            tests_to_process = [(test, selected_section, selected_subsection) for test in tests]
            await progress_message.edit_text(f"📥 **{selected_subsection.get('name')}** ke liye {total_tests} tests download ho rahe hain...")

        # --- Asli Download Loop ---
        start_time = asyncio.get_event_loop().time()

        for test, sec, sub in tests_to_process:
            # Stop flag check
            if context.bot_data[user_chat_id].get('stop_flag'):
                await progress_message.edit_text("🛑 Bulk download roka gaya.")
                break
            
            test_id = test.get('id')
            try:
                questions_data = extractor.extract_questions(test_id)
                if questions_data.get('error'):
                    logger.warning(f"Skipping test {test_id}: {questions_data.get('error')}")
                    continue

                caption = extractor.get_caption(test, series_details, sec, sub, extractor_name)
                
                html_content = generate_html(questions_data, extractor.last_details)
                html_file = io.BytesIO(html_content.encode('utf-8'))
                file_name = f"{test.get('title', 'test').replace('/', '_')}.html"

                await context.bot.send_document(
                    chat_id=final_chat_id,
                    document=InputFile(html_file, filename=file_name),
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                completed_tests += 1
                
                # Progress bar update (har 5 test par ya har 2 second mein)
                current_time = asyncio.get_event_loop().time()
                if completed_tests % 5 == 0 or current_time - start_time > 2:
                    start_time = current_time # Timer reset
                    progress = completed_tests / total_tests
                    bar = "🟩" * int(progress * 10) + "⬜️" * (10 - int(progress * 10))
                    await progress_message.edit_text(
                        f"📥 Download ho raha hai...\n\n"
                        f"Progess: {bar} {completed_tests}/{total_tests} ({int(progress * 100)}%)\n\n"
                        f"File: `{file_name}`\n"
                        f"Destination: `{final_chat_id}`\n\n"
                        "Rokne ke liye /stop type karein."
                    )
                
                await asyncio.sleep(1) # Telegram API rate limit se bachne ke liye

            except Exception as e:
                logger.error(f"File {test_id} bhejte waqt error (Chat ID: {final_chat_id}): {e}")
                await context.bot.send_message(chat_id=user_chat_id, text=f"⚠️ **Error:** File `{test.get('title')}` ko Chat ID `{final_chat_id}` par nahi bhej saka. (Error: {e})\n\nAgle test par ja raha hoon...")
                if isinstance(e, Forbidden):
                    await context.bot.send_message(chat_id=user_chat_id, text="Bot us group/channel mein admin nahi hai ya block ho gaya hai. Process roka ja raha hai.")
                    break # Agar permission error hai toh ruk jaayein
                
                await asyncio.sleep(5) # Thoda zyada rukein agar error aaye

        # --- Download Samapt ---
        if not context.bot_data[user_chat_id].get('stop_flag'):
            await progress_message.edit_text(f"✅ **Bulk Download Complete!**\n\nTotal {completed_tests}/{total_tests} files ko `{final_chat_id}` par bhej diya gaya hai.")

    except Exception as e:
        logger.error(f"Bulk download mein bada error: {e}")
        await progress_message.edit_text(f"❌ **Error:** Bulk download fail ho gaya. Details: {e}")
    finally:
        # Stop flag clean up
        context.bot_data.pop(user_chat_id, None)


@admin_required
async def stop_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stop command se bulk download ko rokta hai.
    """
    user_chat_id = update.effective_chat.id
    if user_chat_id in context.bot_data and 'stop_flag' in context.bot_data[user_chat_id]:
        context.bot_data[user_chat_id]['stop_flag'] = True
        await update.message.reply_text("🛑 Roka ja raha hai... Agle test ke baad process ruk jayega.")
        
    else:
        await update.message.reply_text("ℹ️ Abhi koi bulk download process nahi chal raha hai.")
    
    # Check karein ki kya hum bulk download conversation (setup) mein hain
    if 'bulk_query_data' in context.user_data:
        # Yeh /stop ko conversation ka fallback banata hai
        await update.message.reply_text("Bulk download setup bhi cancel kar diya gaya hai.")
        context.user_data.pop('bulk_query_data', None)
        context.user_data.pop('extractor_name', None)
        context.user_data.pop('destination_choice', None)
        return ConversationHandler.END # Conversation ko force-stop karein
    
    return ConversationHandler.END


# --- Main Function ---
def main():
    # Initial file setup
    if not os.path.exists(ADMIN_FILE): save_admins([])
    if not os.path.exists(CONFIG_FILE): save_config(None, None)

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Bot commands set karein
    application.job_queue.run_once(set_bot_commands, 0)

    # --- NAYA: Bulk Download Conversation Handler ---
    bulk_download_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_section_"),
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_subsection_")
        ],
        states={
            ASK_EXTRACTOR_NAME: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, receive_extractor_name)],
            ASK_DESTINATION: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, receive_destination)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_bulk_conversation),
            CommandHandler("stop", stop_bulk_download) # Stop ko bhi fallback banayein
        ],
        conversation_timeout=600 # 10 minute timeout
    )
    
    application.add_handler(bulk_download_conv)
    # --- END NAYA HANDLER ---

    # --- Baaki handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_menu))
    application.add_handler(CommandHandler("stop", stop_bulk_download)) # General stop handler
    
    # Owner commands
    application.add_handler(CommandHandler("settoken", set_token))
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("removechannel", remove_channel))
    application.add_handler(CommandHandler("viewchannel", view_channel))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("adminlist", admin_list))

    # Callback handlers (Bulk waale chhodkar)
    application.add_handler(CallbackQueryHandler(search_callback, pattern="^search_"))
    application.add_handler(CallbackQueryHandler(series_callback, pattern="^series_"))
    application.add_handler(CallbackQueryHandler(section_callback, pattern="^section_"))
    application.add_handler(CallbackQueryHandler(subsection_callback, pattern="^subsection_"))
    application.add_handler(CallbackQueryHandler(series_callback, pattern="^main_menu$")) # Main menu button


    # Text handler (sabse aakhir mein)
    application.add_handler(MessageHandler(Filters.TEXT & ~Filters.COMMAND, text_input_handler))

    logger.info("Bot shuru ho raha hai...")
    application.run_polling()

if __name__ == "__main__":
    main()

