# -*- coding: utf-8 -*-
import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, BotCommand, InlineQueryResultArticle, InputTextMessageContent, BotCommandScopeChat
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    ConversationHandler, MessageHandler, filters, InlineQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import io
import asyncio  # Live progress bar ke liye
import time
from functools import wraps # Decorator ke liye zaroori

from extractor import TestbookExtractor
from html_generator import generate_html
from config import TELEGRAM_BOT_TOKEN, BOT_OWNER_ID

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration & Admin Files ---
ADMIN_FILE = 'admins.json'
CONFIG_FILE = 'config.json'

# --- State Definitions for Bulk Download ---
ASK_EXTRACTOR_NAME, ASK_DESTINATION = range(2)

# --- Bot Data Stop Flag ---
STOP_BULK_DOWNLOAD_FLAG = 'stop_bulk_download'

# extractor instance ko global rakhein taaki token update ho sake
extractor = None

# =============================================================================
# === DECORATORS & HELPER FUNCTIONS (MOVED TO TOP) ===
# =============================================================================

def load_json(filename, default_data=None):
    """JSON file load karta hai, agar nahi hai toh banata hai."""
    if default_data is None:
        default_data = {}
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(filename, 'w') as f:
            json.dump(default_data, f, indent=4)
        return default_data

def save_json(filename, data):
    """JSON file save karta hai."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def is_admin(user_id):
    """Check karta hai ki user owner hai ya admin file mein hai."""
    if user_id == BOT_OWNER_ID:
        return True
    admins = load_json(ADMIN_FILE, {'admin_ids': []})
    return user_id in admins['admin_ids']

def admin_required(func):
    """
    Decorator jo check karta hai ki user admin/owner hai ya nahi.
    Owner, Admin commands (jaise /setchannel) bhi use kar sakta hai.
    """
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not is_admin(user.id):
            if update.message:
                await update.message.reply_text("⛔ Sorry, yeh command sirf admins ke liye hai.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Sorry, yeh command sirf admins ke liye hai.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def owner_required(func):
    """Decorator jo check karta hai ki user BOT_OWNER hai ya nahi."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id != BOT_OWNER_ID:
            if update.message:
                await update.message.reply_text("⛔ Sorry, yeh command sirf bot owner ke liye hai.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Sorry, yeh command sirf bot owner ke liye hai.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def clear_previous_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Agar pichhla message ID stored hai, toh use delete karta hai."""
    if 'last_bot_message_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
        except (BadRequest, Forbidden) as e:
            logger.warning(f"Purana message delete nahi kar paya: {e}")
        finally:
            # Delete hone par ya fail hone par, key ko hata dein
            context.user_data.pop('last_bot_message_id', None)
            
async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Naya main menu (search bar ke saath) bhejta hai."""
    chat_id = update.effective_chat.id
    await clear_previous_message(context, chat_id)
    
    keyboard = [[InlineKeyboardButton("🔍 Search New Test", switch_inline_query_current_chat="")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = await context.bot.send_message(
        chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    context.user_data['last_bot_message_id'] = message.message_id

def get_config():
    """Config file (token/channel) load karta hai."""
    return load_json(CONFIG_FILE, {"testbook_token": None, "forward_channel_id": None})

def save_config(config_data):
    """Config file (token/channel) save karta hai."""
    save_json(CONFIG_FILE, config_data)

def init_extractor():
    """Extractor ko initialize ya re-initialize karta hai."""
    global extractor
    config = get_config()
    token = config.get('testbook_token')
    if token:
        try:
            extractor = TestbookExtractor(token)
            logger.info("Extractor successfully initialized with token.")
            return True
        except Exception as e:
            logger.error(f"Extractor initialize karne mein error: {e}")
            extractor = None
            return False
    else:
        logger.warning("Extractor initialize nahi hua: config.json mein Testbook token nahi hai.")
        extractor = None
        return False

# =============================================================================
# === OWNER COMMANDS ===
# =============================================================================

@owner_required
async def set_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Naya Testbook token set karta hai."""
    try:
        new_token = context.args[0]
        config = get_config()
        config['testbook_token'] = new_token
        save_config(config)
        
        if init_extractor():
            await update.message.reply_text("✅ Testbook token successfully update ho gaya hai.")
        else:
            await update.message.reply_text("⚠️ Token save ho gaya hai, lekin extractor initialize nahi ho paya. Token galat ho sakta hai.")
            
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /settoken <Naya Token Yahaan>")

@owner_required
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Naya admin add karta hai."""
    try:
        user_id_to_add = int(context.args[0])
        admins = load_json(ADMIN_FILE, {'admin_ids': []})
        
        if user_id_to_add in admins['admin_ids']:
            await update.message.reply_text(f"⚠️ User {user_id_to_add} pehle se admin hai.")
            return
            
        admins['admin_ids'].append(user_id_to_add)
        save_json(ADMIN_FILE, admins)
        await update.message.reply_text(f"✅ User {user_id_to_add} ko admin bana diya gaya hai.")
        
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addadmin <User ID>")

@owner_required
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Admin ko remove karta hai."""
    try:
        user_id_to_remove = int(context.args[0])
        admins = load_json(ADMIN_FILE, {'admin_ids': []})
        
        if user_id_to_remove not in admins['admin_ids']:
            await update.message.reply_text(f"⚠️ User {user_id_to_remove} admin list mein nahi hai.")
            return
            
        admins['admin_ids'].remove(user_id_to_remove)
        save_json(ADMIN_FILE, admins)
        await update.message.reply_text(f"✅ User {user_id_to_remove} ko admin list se hata diya gaya hai.")
        
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /removeadmin <User ID>")

@owner_required
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Owner Only) Sabhi admins ki list dikhata hai."""
    admins = load_json(ADMIN_FILE, {'admin_ids': []})
    admin_ids = admins.get('admin_ids', [])
    
    if not admin_ids:
        await update.message.reply_text("👤 Admin list khaali hai.")
        return

    text = "👤 **Current Admins:**\n"
    for admin_id in admin_ids:
        text += f"- `{admin_id}`\n"
        
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# =============================================================================
# === ADMIN & OWNER COMMANDS ===
# =============================================================================

@admin_required
async def set_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin/Owner) Forwarding ke liye channel ID set karta hai."""
    try:
        new_channel_id = context.args[0]
        # Check karein ki ID valid hai (yaani @username ya -100... se shuru hota hai)
        if not (new_channel_id.startswith('@') or new_channel_id.startswith('-100')):
            await update.message.reply_text("⚠️ Invalid Channel ID. ID `@channel_username` ya `-100...` se shuru hona chahiye.")
            return

        config = get_config()
        config['forward_channel_id'] = new_channel_id
        save_config(config)
        await update.message.reply_text(f"✅ Forward channel set kar diya gaya hai: `{new_channel_id}`", parse_mode=ParseMode.MARKDOWN)
        
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /setchannel <Channel ID ya @username>")

@admin_required
async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin/Owner) Forward channel ko remove karta hai."""
    config = get_config()
    if 'forward_channel_id' in config and config['forward_channel_id'] is not None:
        config['forward_channel_id'] = None
        save_config(config)
        await update.message.reply_text("✅ Forward channel hata diya gaya hai. Files ab auto-forward nahi hongi.")
    else:
        await update.message.reply_text("ℹ️ Koi forward channel pehle se set nahi hai.")

@admin_required
async def view_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(Admin/Owner) Current forward channel dikhata hai."""
    config = get_config()
    channel_id = config.get('forward_channel_id')
    if channel_id:
        await update.message.reply_text(f"ℹ️ Current forward channel hai: `{channel_id}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("ℹ️ Koi forward channel set nahi hai.")

# =============================================================================
# === PUBLIC COMMANDS & BOT LOGIC ===
# =============================================================================

@admin_required
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command handle karta hai."""
    user = update.effective_user
    welcome_text = (
        f"👋 **Welcome, {user.first_name}!**\n\n"
        "Main Testbook Extractor Bot hoon. Main aapke liye tests extract kar sakta hoon.\n\n"
        "Naya test search karne ke liye neeche diye gaye '🔍 Search New Test' button par click karein."
    )
    await send_main_menu(update, context, welcome_text)

@admin_required
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/menu command handle karta hai."""
    await send_main_menu(update, context, "🏠 Main Menu")

@admin_required
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline search requests handle karta hai."""
    if not extractor:
        await update.inline_query.answer([], switch_pm_text="Bot initialized nahi hai (Token set karein)", switch_pm_parameter="start")
        return
        
    query = update.inline_query.query
    if not query:
        await update.inline_query.answer([], switch_pm_text="Search karne ke liye type karein...", switch_pm_parameter="start")
        return

    try:
        search_results = extractor.search(query)
        results = []
        
        if search_results:
            for i, series in enumerate(search_results[:20]): # Limit 20 results
                series_id = series.get('slug')
                series_name = series.get('name', 'Unknown Series')
                tests_count = series.get('testsCount', 0)
                
                results.append(
                    InlineQueryResultArticle(
                        id=f"series_{series_id}_{i}",
                        title=series_name,
                        description=f"{tests_count} tests available",
                        input_message_content=InputTextMessageContent(
                            f"/select_series {series_id}", # Hum slug ka istemal karenge
                            parse_mode=ParseMode.MARKDOWN
                        )
                    )
                )
        
        await update.inline_query.answer(results, cache_time=5)

    except Exception as e:
        logger.error(f"Inline query mein error: {e}")

@admin_required
async def series_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline query se select ki gayi series ko handle karta hai."""
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    try:
        series_slug = context.args[0]
        context.user_data['current_series_slug'] = series_slug
        
        details = extractor.get_series_details(series_slug)
        if not details:
            await update.message.reply_text("Error: Is series ki details nahi mil saki.")
            return

        context.user_data['series_details'] = details
        sections = details.get('sections', [])
        
        keyboard = []
        for i, section in enumerate(sections):
            section_name = section.get('name', 'N/A')
            callback_data = f"section_{i}"
            keyboard.append([InlineKeyboardButton(section_name, callback_data=callback_data)])
        
        # Bulk Download Button (Section Level)
        keyboard.append([InlineKeyboardButton("📥 Download All Tests in this Series", callback_data=f"bulk_section_all")])
        keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data="main_menu")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await clear_previous_message(context, update.effective_chat.id)
        message = await update.message.reply_text(
            f"📚 **{details.get('name')}**\n\nEk section chunein:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['last_bot_message_id'] = message.message_id
        
    except (IndexError, ValueError):
        await update.message.reply_text("Invalid command.")
    except Exception as e:
        logger.error(f"Series selection mein error: {e}")
        await update.message.reply_text("Series select karne mein error aaya.")


@admin_required
async def section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Section button press handle karta hai."""
    query = update.callback_query
    await query.answer()
    
    try:
        section_index = int(query.data.split('_')[1])
        context.user_data['current_section_index'] = section_index
        
        details = context.user_data.get('series_details')
        if not details:
            await query.edit_message_text("Session expire ho gaya hai. /start se dobara search karein.")
            return

        selected_section = details['sections'][section_index]
        context.user_data['selected_section'] = selected_section
        subsections = selected_section.get('subsections', [])
        
        keyboard = []
        for i, sub in enumerate(subsections):
            sub_name = sub.get('name', 'N/A')
            callback_data = f"subsection_{i}"
            keyboard.append([InlineKeyboardButton(sub_name, callback_data=callback_data)])
        
        # Bulk Download Button (Subsection Level)
        keyboard.append([InlineKeyboardButton(f"📥 Download All in '{selected_section.get('name')}'", callback_data=f"bulk_subsection_all")])
        keyboard.append([InlineKeyboardButton("« Back to Sections", callback_data="back_to_series")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🗂️ **{selected_section.get('name')}**\n\nEk subsection chunein:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except (IndexError, ValueError, KeyError):
        await query.edit_message_text("Error: Section data nahi mila. /start se dobara search karein.")
        
@admin_required
async def subsection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subsection button press handle karta hai."""
    query = update.callback_query
    await query.answer()
    
    try:
        subsection_index = int(query.data.split('_')[1])
        context.user_data['current_subsection_index'] = subsection_index
        
        series_details = context.user_data.get('series_details')
        selected_section = context.user_data.get('selected_section')
        if not series_details or not selected_section:
            await query.edit_message_text("Session expire ho gaya hai. /start se dobara search karein.")
            return

        selected_subsection = selected_section['subsections'][subsection_index]
        context.user_data['selected_subsection'] = selected_subsection
        
        tests = extractor.get_tests_in_subsection(
            series_details['id'], 
            selected_section['id'], 
            selected_subsection['id']
        )
        
        if not tests:
            await query.edit_message_text(
                "Is subsection mein koi tests nahi mile.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Subsections", callback_data=f"back_to_section")]])
            )
            return
            
        context.user_data['last_tests'] = tests
        
        # Tests ko .txt file mein convert karein
        test_list_str = ""
        for i, test in enumerate(tests):
            test_list_str += f"{i+1}. {test.get('title', 'N/A')}\n"
            
        test_list_io = io.BytesIO(test_list_str.encode('utf-8'))
        test_list_io.name = f"{selected_subsection.get('name', 'tests')}.txt"
        
        keyboard = [
            [InlineKeyboardButton(f"📥 Download All in '{selected_subsection.get('name')}'", callback_data=f"bulk_subsection_single")],
            [InlineKeyboardButton("« Back to Subsections", callback_data="back_to_section")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Purana message delete karein (kyonki hum file bhej rahe hain)
        await query.delete_message()
        context.user_data.pop('last_bot_message_id', None) # Stored ID ko bhi clear karein
        
        message = await context.bot.send_document(
            chat_id=query.effective_chat.id,
            document=test_list_io,
            caption=(
                f"📂 **{selected_subsection.get('name')}**\n\n"
                f"Is subsection mein {len(tests)} tests mile hain.\n\n"
                "Test download karne ke liye, list se **test ka number** (jaise `5`) copy karke mujhe reply karein."
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['last_bot_message_id'] = message.message_id
        
    except (IndexError, ValueError, KeyError):
        await query.edit_message_text("Error: Subsection data nahi mila. /start se dobara search karein.")

@admin_required
async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test number (text input) handle karta hai."""
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    try:
        test_index = int(update.message.text.strip()) - 1 # 1-based index ko 0-based karein
        
        tests = context.user_data.get('last_tests')
        series_details = context.user_data.get('series_details')
        selected_section = context.user_data.get('selected_section')
        selected_subsection = context.user_data.get('selected_subsection')
        
        if not all([tests, series_details, selected_section, selected_subsection]):
            await update.message.reply_text("Session expire ho gaya hai ya test list nahi mili. /start se dobara search karein.")
            return

        if 0 <= test_index < len(tests):
            selected_test = tests[test_index]
            await process_single_test_download(update, context, selected_test)
        else:
            await update.message.reply_text(f"Invalid number. Kripya 1 aur {len(tests)} ke beech ka number reply karein.")
            
    except (ValueError, TypeError):
        # Agar text number nahi hai, toh use search query maanein
        await handle_search_as_text(update, context)
    except Exception as e:
        logger.error(f"Text input handle karne mein error: {e}")
        await update.message.reply_text("Test process karne mein error aaya.")

async def handle_search_as_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agar text number nahi hai, toh use search query maanta hai."""
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    query = update.message.text
    search_results = extractor.search(query)
    
    if not search_results:
        await update.message.reply_text(f"'{query}' ke liye koi results nahi mile.")
        return

    results_text = f"🔍 **Results for '{query}'**\n\n"
    keyboard = []
    
    for i, series in enumerate(search_results[:10]): # Limit 10 results for text
        series_slug = series.get('slug')
        series_name = series.get('name', 'Unknown Series')
        tests_count = series.get('testsCount', 0)
        
        results_text += f"**{i+1}. {series_name}** ({tests_count} tests)\n"
        keyboard.append([InlineKeyboardButton(f"{i+1}. {series_name[:30]}...", callback_data=f"search_slug_{series_slug}")])
    
    keyboard.append([InlineKeyboardButton("« Back to Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await clear_previous_message(context, update.effective_chat.id)
    message = await update.message.reply_text(
        results_text + "\nSelect a series:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['last_bot_message_id'] = message.message_id

@admin_required
async def search_slug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text search se aaye series slug callback ko handle karta hai."""
    query = update.callback_query
    await query.answer()
    
    series_slug = query.data.split('_', 2)[2] # "search_slug_" ke baad sab kuch
    
    # Fake update object banayein taaki hum series_selection_handler ko call kar sakein
    class FakeMessage:
        async def reply_text(*args, **kwargs):
            # Text search ke baad, hum naya message bhejenge, edit nahi karenge
            return await query.message.reply_text(*args, **kwargs)
        
    class FakeUpdate:
        effective_chat = update.effective_chat
        message = FakeMessage()

    context.args = [series_slug]
    await series_selection_handler(FakeUpdate(), context)
    await query.delete_message() # Purane search result message ko delete karein


async def process_single_test_download(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_test: dict):
    """Ek single test ko download aur send karta hai."""
    processing_message = await update.message.reply_text(f"⏳ **Processing...**\n`{selected_test.get('title')}`\n\nTest extract karne mein 1-2 minute lag sakte hain...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        test_id = selected_test.get('id')
        series_details = context.user_data.get('series_details')
        selected_section = context.user_data.get('selected_section')
        selected_subsection = context.user_data.get('selected_subsection')

        questions_data = extractor.extract_questions(test_id)
        
        if questions_data.get('error'):
            await processing_message.edit_text(f"Error: {questions_data.get('error')}")
            return
            
        # Caption generate karein
        caption = extractor.get_caption(
            test_summary=selected_test,
            series_details=series_details,
            selected_section=selected_section,
            subsection_context=selected_subsection
        )
        
        # HTML generate karein (extractor.last_details ka istemal karega)
        html_content = generate_html(questions_data, extractor.last_details)
        
        html_file = io.BytesIO(html_content.encode('utf-8'))
        file_name = f"{selected_test.get('title', 'test')[:50]}.html".replace('/', '_')
        html_file.name = file_name
        
        # File ko user ko send karein
        sent_message = await update.message.reply_document(
            document=html_file,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Processing message delete karein
        await processing_message.delete()
        
        # Auto-forward karein (agar set hai)
        config = get_config()
        channel_id = config.get('forward_channel_id')
        if channel_id:
            try:
                await context.bot.forward_message(
                    chat_id=channel_id,
                    from_chat_id=update.effective_chat.id,
                    message_id=sent_message.message_id
                )
            except Exception as e:
                logger.error(f"Channel {channel_id} mein forward karne mein error: {e}")
                await update.message.reply_text(f"⚠️ Test send ho gaya hai, lekin channel `{channel_id}` mein forward nahi kar paya. (Error: {e})", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Test download/send karne mein error: {e}")
        await processing_message.edit_text(f"Test process karne mein ek error aaya: {e}")


# =============================================================================
# === NAVIGATION CALLBACKS ===
# =============================================================================

@admin_required
async def series_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'Back to Sections' (Series detail) button handle karta hai."""
    query = update.callback_query
    await query.answer()
    
    # Fake update object
    class FakeMessage:
        async def reply_text(*args, **kwargs):
            return await query.message.edit_text(*args, **kwargs)
    class FakeUpdate:
        effective_chat = update.effective_chat
        message = FakeMessage()

    series_slug = context.user_data.get('current_series_slug')
    if not series_slug:
        await query.edit_message_text("Session expire ho gaya hai. /start se dobara search karein.")
        return
        
    context.args = [series_slug]
    # series_selection_handler ke liye message text ki zaroorat nahi hai,
    # lekin context.args[0] (slug) ki zaroorat hai.
    # Hum seedha handler call karenge.
    await series_selection_handler(FakeUpdate(), context)

@admin_required
async def section_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'Back to Subsections' (Section detail) button handle karta hai."""
    query = update.callback_query
    await query.answer()
    # Puraane logic ko call karne ke bajaye, hum series_callback ko call karenge
    # jo section list ko dobara render karega.
    # Iske liye humein context se section_index hatana hoga taaki
    # section_callback sahi se kaam kare.
    context.user_data.pop('current_section_index', None)
    context.user_data.pop('selected_section', None)
    await series_callback(update, context) # Yeh sections ki list dikhayega

@admin_required
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'Back to Main Menu' button handle karta hai."""
    query = update.callback_query
    await query.answer()
    
    # Fake update object
    class FakeUpdate:
        effective_user = update.effective_user
        effective_chat = update.effective_chat
    
    await send_main_menu(FakeUpdate(), context, "🏠 Main Menu")
    await query.delete_message()


# =============================================================================
# === BULK DOWNLOAD CONVERSATION ===
# =============================================================================

@admin_required
async def bulk_download_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk download shuru karta hai, extractor ka naam poochta hai."""
    query = update.callback_query
    await query.answer()
    
    # Store karein ki kya download karna hai
    context.user_data['bulk_query_data'] = query.data
    
    text = (
        "📝 **Extractor ka Naam:**\n\n"
        "Aap jo test extract kar rahe hain, unke caption mein 'Extracted By:' ke baad kya naam aana chahiye?\n\n"
        "(Jaise: `H4R`, `Testbook Team`, etc.)\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    return ASK_EXTRACTOR_NAME

@admin_required
async def receive_extractor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Extractor ka naam save karta hai aur destination poochta hai.
    """
    extractor_name = update.message.text.strip()
    context.user_data['bulk_extractor_name'] = extractor_name
    
    # Pichhla message delete karein (jo "Extractor ka Naam" pooch raha tha)
    chat_id = update.effective_chat.id
    if 'last_bot_message_id' in context.user_data:
         try:
            # ConversationHandler mein, last message ID message ka hi ID hota hai
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
         except Exception: pass # Fail hone par ignore karein
            
    # User ka message (naam) delete karein
    try:
        await update.message.delete()
    except Exception: pass

    config = get_config()
    default_channel = config.get('forward_channel_id', 'N/A')

    text = (
        f"➡️ **Destination Chunein:**\n\n"
        "Aap yeh sabhi test files kahaan bhejna chahte hain?\n\n"
        "1. **`1`** type karein - Files ko isi chat (aapki personal chat) mein bhejne ke liye.\n"
        "2. **`/d`** type karein - Default channel (`{default_channel}`) mein bhejne ke liye.\n"
        "3. Koi naya **Channel ID** (jaise `-100...` ya `@username`) type karein - Kisi doosre channel mein bhejne ke liye.\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    
    message = await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    context.user_data['last_bot_message_id'] = message.message_id # Naya message ID store karein

    return ASK_DESTINATION

@admin_required
async def receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Destination save karta hai aur bulk download shuru karta hai.
    """
    destination_input = update.message.text.strip()
    context.user_data['bulk_destination'] = destination_input
    
    # Pichhla message delete karein (jo "Destination Chunein" pooch raha tha)
    chat_id = update.effective_chat.id
    if 'last_bot_message_id' in context.user_data:
         try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
         except Exception: pass
            
    # User ka message (destination) delete karein
    try:
        await update.message.delete()
    except Exception: pass
        
    # Async task shuru karein (taaki bot block na ho)
    asyncio.create_task(perform_bulk_download(update, context))
    
    # Conversation khatm karein
    return ConversationHandler.END

async def cancel_bulk_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bulk download conversation ko cancel karta hai."""
    await clear_previous_message(context, update.effective_chat.id)
    
    await update.message.reply_text("Bulk download cancel kar diya gaya hai.")
    
    # Cleanup
    context.user_data.pop('bulk_query_data', None)
    context.user_data.pop('bulk_extractor_name', None)
    context.user_data.pop('bulk_destination', None)
    
    await send_main_menu(update, context, "🏠 Main Menu")
    return ConversationHandler.END

# --- Bulk Download Logic (Updated) ---
async def perform_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asynchronously sabhi tests ko download aur forward karta hai.
    """
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    user_chat_id = update.effective_chat.id
    
    # User data se context lein
    query_data = context.user_data.get('bulk_query_data')
    extractor_name = context.user_data.get('bulk_extractor_name')
    destination = context.user_data.get('bulk_destination')
    
    # Stop flag set karein
    context.bot_data[user_chat_id] = {STOP_BULK_DOWNLOAD_FLAG: False}

    try:
        # 1. Destination ID set karein
        final_chat_id = None
        config = get_config()
        
        if destination == '1':
            final_chat_id = user_chat_id
        elif destination == '/d':
            final_chat_id = config.get('forward_channel_id')
            if not final_chat_id:
                await context.bot.send_message(user_chat_id, "Error: Aapne default channel chuna, lekin koi default channel set nahi hai. /setchannel ka istemal karein.")
                return
        elif destination.startswith('@') or destination.startswith('-100'):
            final_chat_id = destination
        else:
            await context.bot.send_message(user_chat_id, "Error: Invalid destination input. Process cancel kar diya gaya hai.")
            return

        # 2. Tests ki list fetch karein
        series_details = context.user_data.get('series_details')
        if not series_details:
            await context.bot.send_message(user_chat_id, "Error: Session expire ho gaya hai. /start se dobara search karein.")
            return

        tests_to_process = []
        parts = query_data.split('_') # e.g., "bulk_section_all" ya "bulk_subsection_single"
        
        if parts[1] == "section":
            # Poori series ke sabhi sections ke sabhi subsections ke tests
            for sec in series_details.get('sections', []):
                for sub in sec.get('subsections', []):
                    tests = extractor.get_tests_in_subsection(series_details['id'], sec['id'], sub['id'])
                    if tests:
                        tests_to_process.extend([(test, sec, sub) for test in tests])
                        
        elif parts[1] == "subsection":
            selected_section = context.user_data.get('selected_section')
            if not selected_section:
                await context.bot.send_message(user_chat_id, "Error: Section data nahi mila. /start se dobara search karein.")
                return
                
            if parts[2] == "all":
                # Current section ke sabhi subsections ke tests
                for sub in selected_section.get('subsections', []):
                    tests = extractor.get_tests_in_subsection(series_details['id'], selected_section['id'], sub['id'])
                    if tests:
                        tests_to_process.extend([(test, selected_section, sub) for test in tests])
            
            elif parts[2] == "single":
                # Sirf current subsection ke tests
                selected_subsection = context.user_data.get('selected_subsection')
                if not selected_subsection:
                    await context.bot.send_message(user_chat_id, "Error: Subsection data nahi mila. /start se dobara search karein.")
                    return
                tests = context.user_data.get('last_tests', []) # Jo pehle hi fetch ho chuke hain
                tests_to_process.extend([(test, selected_section, selected_subsection) for test in tests])

        if not tests_to_process:
            await context.bot.send_message(user_chat_id, "Error: Download karne ke liye koi tests nahi mile.")
            return

        total_tests = len(tests_to_process)
        progress_message = await context.bot.send_message(
            user_chat_id, 
            f"✅ Setup complete. {total_tests} tests ko download kiya ja raha hai...\n"
            f"Destination: `{final_chat_id}`\n\n"
            "Rokne ke liye /stop type karein.",
            parse_mode=ParseMode.MARKDOWN
        )

        # --- Asli Download Loop ---
        last_update_time = asyncio.get_event_loop().time()
        completed_tests = 0

        for test, sec, sub in tests_to_process:
            # Check karein ki /stop call hua ya nahi
            if context.bot_data.get(user_chat_id, {}).get(STOP_BULK_DOWNLOAD_FLAG, False):
                await progress_message.edit_text(f"🛑 Bulk download ko {completed_tests}/{total_tests} tests ke baad rok diya gaya hai.")
                break
                
            completed_tests += 1
            file_name = f"{test.get('title', 'test')[:50]}.html".replace('/', '_')

            try:
                # 1. Questions extract karein
                questions_data = extractor.extract_questions(test.get('id'))
                if questions_data.get('error'):
                    logger.warning(f"Test {file_name} skip kiya (Error: {questions_data.get('error')})")
                    continue
                
                # 2. Caption generate karein
                caption = extractor.get_caption(
                    test_summary=test,
                    series_details=series_details,
                    selected_section=sec,
                    subsection_context=sub,
                    extractor_name=extractor_name
                )
                
                # 3. HTML generate karein
                html_content = generate_html(questions_data, extractor.last_details)
                html_file = io.BytesIO(html_content.encode('utf-8'))
                html_file.name = file_name
                
                # 4. File ko destination par send karein
                await context.bot.send_document(
                    chat_id=final_chat_id,
                    document=html_file,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # 5. Progress update karein
                current_time = asyncio.get_event_loop().time()
                # Har 5 file ya 3 second mein message update karein (Telegram limit se bachne ke liye)
                if completed_tests % 5 == 0 or current_time - last_update_time > 3:
                    last_update_time = current_time # Timer reset
                    progress = completed_tests / total_tests
                    bar = "🟩" * int(progress * 10) + "⬜️" * (10 - int(progress * 10))
                    
                    try:
                        await progress_message.edit_text(
                            f"📥 Download ho raha hai...\n\n"
                            f"Progess: {bar} {completed_tests}/{total_tests} ({int(progress * 100)}%)\n\n"
                            f"File: `{file_name}`\n"
                            f"Destination: `{final_chat_id}`\n\n"
                            "Rokne ke liye /stop type karein.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except BadRequest as e:
                        if "message is not modified" in str(e):
                            pass # Agar message same hai toh error ignore karein
                        else:
                            raise # Doosra error hai toh raise karein
                
                await asyncio.sleep(1) # Telegram API rate limit se bachne ke liye
                
            except Exception as e:
                logger.error(f"Test {file_name} process karne mein error: {e}")
                await context.bot.send_message(user_chat_id, f"⚠️ Test `{file_name}` ko process karne mein error aaya: {e}", parse_mode=ParseMode.MARKDOWN)
                await asyncio.sleep(2) # Error ke baad thoda rukein

        if not context.bot_data.get(user_chat_id, {}).get(STOP_BULK_DOWNLOAD_FLAG, False):
            await progress_message.edit_text(f"✅ **Bulk Download Complete!**\n\n{completed_tests}/{total_tests} tests ko `{final_chat_id}` mein bhej diya gaya hai.", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Bulk download mein bada error: {e}")
        await context.bot.send_message(user_chat_id, f"❌ Bulk download fail ho gaya: {e}")
        
    finally:
        # Stop flag clean up
        context.bot_data.pop(user_chat_id, None)
        # Context data clean up
        context.user_data.pop('bulk_query_data', None)
        context.user_data.pop('bulk_extractor_name', None)
        context.user_data.pop('bulk_destination', None)


@admin_required
async def stop_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stop command handle karta hai."""
    user_chat_id = update.effective_chat.id
    if user_chat_id in context.bot_data and not context.bot_data[user_chat_id].get(STOP_BULK_DOWNLOAD_FLAG, False):
        context.bot_data[user_chat_id][STOP_BULK_DOWNLOAD_FLAG] = True
        await update.message.reply_text("🛑 Stopping... Agla test complete hone ke baad bulk download ruk jayega.")
    else:
        await update.message.reply_text("Abhi koi bulk download process active nahi hai.")
    
    # Conversation se bahar nikalne ke liye (agar /stop bulk conv ke dauraan kiya gaya)
    return ConversationHandler.END


# =============================================================================
# === MAIN FUNCTION ===
# =============================================================================

async def set_bot_commands(application: Application):
    """Bot ke menu commands set karta hai."""
    owner_commands = [
        BotCommand("start", "Bot ko start karein"),
        BotCommand("menu", "Main menu dikhayein"),
        BotCommand("settoken", "<token> - Testbook token set karein (Owner)"),
        BotCommand("addadmin", "<user_id> - Naya admin add karein (Owner)"),
        BotCommand("removeadmin", "<user_id> - Admin remove karein (Owner)"),
        BotCommand("adminlist", "Sabhi admins ki list dekhein (Owner)"),
        BotCommand("setchannel", "<chat_id> - Auto-forward channel set karein (Admin)"),
        BotCommand("removechannel", "Auto-forward channel hatayein (Admin)"),
        BotCommand("viewchannel", "Current forward channel dekhein (Admin)"),
        BotCommand("stop", "Current bulk download ko rokein")
    ]
    
    admin_commands = [
        BotCommand("start", "Bot ko start karein"),
        BotCommand("menu", "Main menu dikhayein"),
        BotCommand("setchannel", "<chat_id> - Auto-forward channel set karein (Admin)"),
        BotCommand("removechannel", "Auto-forward channel hatayein (Admin)"),
        BotCommand("viewchannel", "Current forward channel dekhein (Admin)"),
        BotCommand("stop", "Current bulk download ko rokein")
    ]

    try:
        # Owner ke liye sabhi commands
        await application.bot.set_my_commands(owner_commands, scope=BotCommandScopeChat(chat_id=BOT_OWNER_ID))
        
        # Admins ke liye limited commands
        admins = load_json(ADMIN_FILE, {'admin_ids': []})
        for admin_id in admins.get('admin_ids', []):
            if admin_id != BOT_OWNER_ID:
                try:
                    await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
                except Exception as e:
                    logger.warning(f"Admin {admin_id} ke liye commands set nahi kar paya (shayad bot block hai): {e}")
                
    except Exception as e:
        logger.warning(f"Bot commands set karne mein error: {e}")

def main():
    """Bot ko run karta hai."""
    
    # Pehli baar config files load/create karein
    load_json(ADMIN_FILE, {'admin_ids': []})
    load_json(CONFIG_FILE, {"testbook_token": None, "forward_channel_id": None})
    
    # Extractor ko initialize karein
    if not init_extractor():
        logger.warning("Bot shuru ho raha hai, lekin Testbook Token set nahi hai. /settoken ka istemal karein.")

    # --- YEH HAI FIX ---
    # Application builder mein post_init pass karein
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(set_bot_commands).build()
    # --- END FIX ---

    # --- NAYA HANDLER: Bulk Download Conversation ---
    bulk_download_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_section_"),
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_subsection_")
        ],
        states={
            ASK_EXTRACTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_extractor_name)],
            ASK_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_bulk_conversation),
            CommandHandler("stop", stop_bulk_download)
        ],
        conversation_timeout=300, # 5 minute timeout
        per_message=False # Performance ke liye behtar
    )
    
    application.add_handler(bulk_download_conv)
    # --- END NAYA HANDLER ---

    # --- Baaki Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    
    # Owner Commands
    application.add_handler(CommandHandler("settoken", set_token))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("adminlist", admin_list))
    
    # Admin Commands
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("removechannel", remove_channel))
    application.add_handler(CommandHandler("viewchannel", view_channel))
    application.add_handler(CommandHandler("stop", stop_bulk_download)) # Conversation ke bahar bhi kaam karega

    # Inline Query
    application.add_handler(InlineQueryHandler(inline_query))
    
    # Message Handlers (Inline query se selection ke liye)
    application.add_handler(MessageHandler(filters.Regex(r'^/select_series'), series_selection_handler))
    
    # Callback Handlers (Buttons ke liye)
    application.add_handler(CallbackQueryHandler(section_callback, pattern="^section_"))
    application.add_handler(CallbackQueryHandler(subsection_callback, pattern="^subsection_"))
    application.add_handler(CallbackQueryHandler(series_callback, pattern="^back_to_series$"))
    application.add_handler(CallbackQueryHandler(section_nav_callback, pattern="^back_to_section$"))
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(search_slug_callback, pattern="^search_slug_"))


    # Text handler (sabse aakhir mein)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))

    logger.info("Bot shuru ho raha hai...")
    
    # Bot ko run karein
    application.run_polling()

if __name__ == '__main__':
    main()

