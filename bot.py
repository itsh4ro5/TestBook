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
from txt_generator import generate_txt # TXT generator import karein
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

# --- State Definitions for User Input ---
# Flags to track what the bot expects next
STATE_WAITING_SEARCH_NUM = 'awaiting_search_num'
STATE_WAITING_SECTION_NUM = 'awaiting_section_num'
STATE_WAITING_TEST_NUM = 'awaiting_test_num' # After txt file
STATE_WAITING_FORMAT_SINGLE = 'awaiting_format_single' # Naya state single test format ke liye

# --- State Definitions for Bulk Download ---
# --- MODIFIED: Naya state add kiya ---
ASK_EXTRACTOR_NAME, ASK_START_NUMBER, ASK_DESTINATION, ASK_FORMAT_BULK = range(4) # Naya state ASK_FORMAT_BULK

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
    # Clear state when returning to main menu
    context.user_data.pop(STATE_WAITING_SEARCH_NUM, None)
    context.user_data.pop(STATE_WAITING_SECTION_NUM, None)
    context.user_data.pop(STATE_WAITING_TEST_NUM, None)
    context.user_data.pop(STATE_WAITING_FORMAT_SINGLE, None) # Naya state clear karein
    context.user_data.pop('search_results', None)
    context.user_data.pop('series_details', None)
    context.user_data.pop('last_tests', None) # Combined tests list
    context.user_data.pop('selected_test_info', None) # Selected test info clear karein

    # keyboard = [[InlineKeyboardButton("🔍 Search New Test", switch_inline_query_current_chat="")]] # Removed inline search
    # reply_markup = InlineKeyboardMarkup(keyboard)
    
    # --- FIXED: text mein `/search <query>` ko <code> aur &lt; &gt; se replace kiya ---
    message = await context.bot.send_message(
        chat_id,
        text=text + "\n\nTest search karne ke liye <code>/search &lt;query&gt;</code> type karein.", # Instruct user on how to search
        # reply_markup=reply_markup, # Removed inline search button
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
    # --- FIXED: Markdown (**) ko HTML (<b>) se replace kiya ---
    welcome_text = (
        f"👋 <b>Welcome, {user.first_name}!</b>\n\n"
        "Main Testbook Extractor Bot hoon. Main aapke liye tests extract kar sakta hoon."
    )
    await send_main_menu(update, context, welcome_text)

@admin_required
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/menu command handle karta hai."""
    await send_main_menu(update, context, "🏠 Main Menu")

@admin_required
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /search command."""
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: `/search <search query>`", parse_mode=ParseMode.MARKDOWN)
        return

    try:
        search_results = extractor.search(query)
        if not search_results:
            await update.message.reply_text(f"'{query}' ke liye koi results nahi mile.")
            return

        context.user_data['search_results'] = search_results # Store full results
        results_text = f"🔍 **Results for '{query}'**\n\n"
        
        for i, series in enumerate(search_results[:20]): # Show top 20
            series_name = series.get('name', 'Unknown Series')
            tests_count = series.get('testsCount', 0)
            results_text += f"**{i+1}.** {series_name} ({tests_count} tests)\n"
        
        results_text += "\nSeries select karne ke liye **number** reply karein."
        
        await clear_previous_message(context, update.effective_chat.id)
        message = await update.message.reply_text(results_text, parse_mode=ParseMode.MARKDOWN)
        context.user_data['last_bot_message_id'] = message.message_id
        context.user_data[STATE_WAITING_SEARCH_NUM] = True # Set state

    except Exception as e:
        logger.error(f"Search command mein error: {e}")
        await update.message.reply_text("Search karne mein error aaya.")

@admin_required
async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input based on the current state."""
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # --- Naya: State 4: Format selection (Single Test) ---
    if context.user_data.get(STATE_WAITING_FORMAT_SINGLE):
        selected_test_info = context.user_data.get('selected_test_info')
        if not selected_test_info:
            await update.message.reply_text("Session expire ho gaya hai. Dobara `/search` karein.", parse_mode=ParseMode.MARKDOWN)
            context.user_data.pop(STATE_WAITING_FORMAT_SINGLE, None)
            context.user_data.pop(STATE_WAITING_TEST_NUM, None) # Also clear test num state
            return

        format_choice = text.lower()
        if format_choice not in ['html', 'txt', 'both']:
            await update.message.reply_text("Invalid format. Kripya `html`, `txt`, ya `both` type karein.")
            return # State ko active rakhein

        # Format valid hai, process download
        await process_single_test_download(
            update, 
            context, 
            selected_test_info['test_data'],
            selected_test_info['section_context'],
            selected_test_info['subsection_context'],
            format_choice # Pass the format
        )
        
        # State clear karein, lekin test num state active rakhein
        context.user_data.pop(STATE_WAITING_FORMAT_SINGLE, None)
        context.user_data.pop('selected_test_info', None) # Selected test info clear karein
        # STATE_WAITING_TEST_NUM active hai, taaki user agla number daal sake
        await update.message.reply_text("Aap agla test download karne ke liye number reply kar sakte hain.")
        return

    # --- States 1, 2, 3 (Number input) ---
    try:
        number = int(text) - 1 # Convert to 0-based index

        # --- State 1: Waiting for Search Result Number ---
        if context.user_data.get(STATE_WAITING_SEARCH_NUM):
            search_results = context.user_data.get('search_results')
            if not search_results:
                await update.message.reply_text("Session expire ho gaya hai. Dobara `/search` karein.", parse_mode=ParseMode.MARKDOWN)
                return ConversationHandler.END # End conv if applicable

            if 0 <= number < len(search_results):
                selected_series = search_results[number]
                series_slug = selected_series.get('slug')
                
                details = extractor.get_series_details(series_slug)
                if not details:
                    await update.message.reply_text("Error: Is series ki details nahi mil saki.")
                    context.user_data.pop(STATE_WAITING_SEARCH_NUM, None) # Reset state
                    return

                context.user_data['series_details'] = details
                context.user_data['current_series_slug'] = series_slug # Store slug for bulk download context
                sections = details.get('sections', [])
                
                if not sections:
                    await update.message.reply_text("Is series mein koi sections nahi hain.")
                    context.user_data.pop(STATE_WAITING_SEARCH_NUM, None) # Reset state
                    return

                sections_text = f"📚 **{details.get('name')}**\n\nSections:\n"
                for i, section in enumerate(sections):
                    sections_text += f"**{i+1}.** {section.get('name', 'N/A')}\n"
                
                sections_text += "\nSection select karne ke liye **number** reply karein."
                
                # Add bulk download button for the series
                keyboard = [[InlineKeyboardButton("📥 Download All Tests in this Series", callback_data=f"bulk_section_all")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await clear_previous_message(context, chat_id)
                message = await update.message.reply_text(sections_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
                context.user_data['last_bot_message_id'] = message.message_id
                
                # Update state
                context.user_data.pop(STATE_WAITING_SEARCH_NUM, None)
                context.user_data[STATE_WAITING_SECTION_NUM] = True
            else:
                await update.message.reply_text(f"Invalid number. Kripya 1 aur {len(search_results)} ke beech ka number reply karein.")
            return # Don't fall through

        # --- State 2: Waiting for Section Number ---
        elif context.user_data.get(STATE_WAITING_SECTION_NUM):
            details = context.user_data.get('series_details')
            if not details:
                await update.message.reply_text("Session expire ho gaya hai. Dobara `/search` karein.", parse_mode=ParseMode.MARKDOWN)
                return

            sections = details.get('sections', [])
            if 0 <= number < len(sections):
                selected_section = sections[number]
                context.user_data['selected_section'] = selected_section # Store for bulk download context
                subsections = selected_section.get('subsections', [])
                
                if not subsections:
                    await update.message.reply_text("Is section mein koi subsections nahi hain.")
                    context.user_data.pop(STATE_WAITING_SECTION_NUM, None) # Reset state
                    return

                await update.message.reply_text(f"⏳ Fetching tests for section '{selected_section.get('name')}'...")

                all_tests_in_section = []
                combined_test_list_str = ""
                test_counter = 1

                for i, sub in enumerate(subsections):
                    combined_test_list_str += f"\n--- {sub.get('name', f'Subsection {i+1}')} ---\n"
                    tests = extractor.get_tests_in_subsection(
                        details['id'], 
                        selected_section['id'], 
                        sub['id']
                    )
                    
                    if tests:
                        for test in tests:
                            # Store test with its context
                            all_tests_in_section.append({
                                'test_data': test,
                                'section_context': selected_section,
                                'subsection_context': sub
                            })
                            combined_test_list_str += f"{test_counter}. {test.get('title', 'N/A')}\n"
                            test_counter += 1
                    else:
                         combined_test_list_str += "(No tests found)\n"


                if not all_tests_in_section:
                    await update.message.reply_text("Is section ke kisi bhi subsection mein tests nahi mile.")
                    context.user_data.pop(STATE_WAITING_SECTION_NUM, None) # Reset state
                    return

                context.user_data['last_tests'] = all_tests_in_section # Store combined list with context
                
                test_list_io = io.BytesIO(combined_test_list_str.encode('utf-8'))
                test_list_io.name = f"{selected_section.get('name', 'section_tests')}.txt"
                
                # Add bulk download button for the section
                keyboard = [[InlineKeyboardButton(f"📥 Download All in '{selected_section.get('name')}'", callback_data=f"bulk_subsection_all")]] # Uses section context
                reply_markup = InlineKeyboardMarkup(keyboard)

                await clear_previous_message(context, chat_id) # Clear the "Fetching..." message
                message = await context.bot.send_document(
                    chat_id=chat_id,
                    document=test_list_io,
                    caption=(
                        f"📂 **{selected_section.get('name')}**\n\n"
                        f"Is section mein {len(all_tests_in_section)} tests mile hain (sabhi subsections mila kar).\n\n"
                        "Test download karne ke liye, list se **test ka number** (jaise `5`) copy karke mujhe reply karein."
                    ),
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                context.user_data['last_bot_message_id'] = message.message_id
                
                # Update state
                context.user_data.pop(STATE_WAITING_SECTION_NUM, None)
                context.user_data[STATE_WAITING_TEST_NUM] = True
                
            else:
                 await update.message.reply_text(f"Invalid number. Kripya 1 aur {len(sections)} ke beech ka number reply karein.")
            return # Don't fall through

        # --- State 3: Waiting for Test Number (after txt file) ---
        elif context.user_data.get(STATE_WAITING_TEST_NUM):
            combined_tests = context.user_data.get('last_tests')
            series_details = context.user_data.get('series_details') # Keep series details

            if not combined_tests or not series_details:
                await update.message.reply_text("Session expire ho gaya hai ya test list nahi mili. Dobara `/search` karein.", parse_mode=ParseMode.MARKDOWN)
                context.user_data.pop(STATE_WAITING_TEST_NUM, None) # Reset state
                return

            if 0 <= number < len(combined_tests):
                selected_test_info = combined_tests[number]
                context.user_data['selected_test_info'] = selected_test_info # Store for format selection
                
                # Format poochne ke liye naya state set karein
                context.user_data[STATE_WAITING_FORMAT_SINGLE] = True
                # STATE_WAITING_TEST_NUM ko active rakhein
                
                await update.message.reply_text(
                    f"Aapne test select kiya: `{selected_test_info['test_data'].get('title')}`\n\n"
                    "Aapko kaunsa format chahiye?\n"
                    "Kripya reply karein: `html`, `txt`, ya `both`",
                    parse_mode=ParseMode.MARKDOWN
                )
                
            else:
                await update.message.reply_text(f"Invalid number. Kripya 1 aur {len(combined_tests)} ke beech ka number reply karein.")
            return # Don't fall through
            
        # --- No Specific State ---
        else:
            # If no state is set, treat as a normal text message (could be a search query)
             await update.message.reply_text("Command samajh nahi aaya. Test search karne ke liye <code>/search &lt;query&gt;</code> type karein.", parse_mode=ParseMode.HTML)

    except (ValueError, TypeError):
        # If text is not a number and no state is active, treat as search
        if not context.user_data.get(STATE_WAITING_SEARCH_NUM) and \
           not context.user_data.get(STATE_WAITING_SECTION_NUM) and \
           not context.user_data.get(STATE_WAITING_TEST_NUM) and \
           not context.user_data.get(STATE_WAITING_FORMAT_SINGLE): # Naya state check karein
             await update.message.reply_text("Command samajh nahi aaya. Test search karne ke liye <code>/search &lt;query&gt;</code> type karein.", parse_mode=ParseMode.HTML)
        elif context.user_data.get(STATE_WAITING_FORMAT_SINGLE):
            # Agar format selection state mein hai, toh text input (html, txt, both) valid hai
            # Yeh block already upar handle ho gaya hai, lekin safe side ke liye
            pass
        else:
            # If expecting a number but got text
             await update.message.reply_text("Invalid input. Kripya ek number type karein.")
             
    except Exception as e:
        logger.error(f"Text input handle karne mein error: {e}")
        await update.message.reply_text("Kuch error aaya. Dobara try karein.")
        # Reset states on error
        context.user_data.pop(STATE_WAITING_SEARCH_NUM, None)
        context.user_data.pop(STATE_WAITING_SECTION_NUM, None)
        context.user_data.pop(STATE_WAITING_TEST_NUM, None)
        context.user_data.pop(STATE_WAITING_FORMAT_SINGLE, None)


# --- Modified process_single_test_download to accept format ---
async def process_single_test_download(update: Update, context: ContextTypes.DEFAULT_TYPE, selected_test: dict, section_context: dict, subsection_context: dict, file_format: str):
    """Ek single test ko download aur send karta hai, specified format mein."""
    processing_message = await update.message.reply_text(f"⏳ **Processing...**\n`{selected_test.get('title')}`\n\nTest extract karne mein 1-2 minute lag sakte hain...", parse_mode=ParseMode.MARKDOWN)
    
    try:
        test_id = selected_test.get('id')
        series_details = context.user_data.get('series_details') # Get series details from context

        if not series_details:
             await processing_message.edit_text("Error: Series details nahi mile. Session expire ho gaya hoga.")
             return

        questions_data = extractor.extract_questions(test_id)
        
        if questions_data.get('error'):
            await processing_message.edit_text(f"Error extracting test: {questions_data.get('error')}")
            return
            
        # Caption generate karein using passed context
        caption = extractor.get_caption(
            test_summary=selected_test,
            series_details=series_details,
            selected_section=section_context,
            subsection_context=subsection_context
            # Extractor name is not needed for single download
        )
        
        # File name (bina extension)
        base_file_name = f"{selected_test.get('title', 'test')[:50]}".replace('/', '_')
        
        files_to_send = []
        
        # Generate HTML if needed
        if file_format in ['html', 'both']:
            html_content = generate_html(questions_data, extractor.last_details)
            html_file = io.BytesIO(html_content.encode('utf-8'))
            html_file.name = f"{base_file_name}.html"
            files_to_send.append(html_file)
        
        # Generate TXT if needed
        if file_format in ['txt', 'both']:
            # --- FIXED: extractor.last_details ko pass kiya ---
            txt_content = generate_txt(questions_data, extractor.last_details) # Use new generator
            txt_file = io.BytesIO(txt_content.encode('utf-8'))
            txt_file.name = f"{base_file_name}.txt"
            files_to_send.append(txt_file)

        # Processing message delete karein
        await processing_message.delete()
        
        sent_messages = []
        # Files ko user ko send karein (ek-ek karke)
        for i, file_to_send in enumerate(files_to_send):
            sent_msg = await update.message.reply_document(
                document=file_to_send,
                caption=caption if i == 0 else None, # Sirf pehli file par caption lagayein
                parse_mode=ParseMode.MARKDOWN
            )
            sent_messages.append(sent_msg)
        
        # Auto-forward karein (agar set hai)
        config = get_config()
        channel_id = config.get('forward_channel_id')
        if channel_id:
            try:
                for sent_message in sent_messages:
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
        try:
            await processing_message.edit_text(f"Test process karne mein ek error aaya: {e}")
        except Exception:
            await update.message.reply_text(f"Test process karne mein ek error aaya: {e}")


# =============================================================================
# === NAVIGATION CALLBACKS (REMOVED/SIMPLIFIED) ===
# =============================================================================
# Back buttons are removed as navigation is now text/number based via /search
# User can use /menu or /search again to navigate.

@admin_required
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Back to Main Menu' button potentially left on old messages."""
    query = update.callback_query
    await query.answer()
    
    # Fake update object
    class FakeUpdate:
        effective_user = update.effective_user
        effective_chat = update.effective_chat
    
    await send_main_menu(FakeUpdate(), context, "🏠 Main Menu")
    try:
        await query.delete_message()
    except Exception:
        pass


# =============================================================================
# === BULK DOWNLOAD CONVERSATION ===
# =============================================================================
# This part is MODIFIED to include ASK_FORMAT_BULK.

@admin_required
async def bulk_download_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bulk download shuru karta hai, STARTING NUMBER poochta hai.
    """
    query = update.callback_query
    await query.answer()
    
    # Store karein ki kya download karna hai
    context.user_data['bulk_query_data'] = query.data
    
    text = (
        f"🔢 **Kahaan se Shuru Karein?**\n\n"
        "Kripya test ka starting number type karein (jaise list mein 5 number se shuru karne ke liye `5` type karein).\n\n"
        "Shuru se (number 1 se) start karne ke liye `1` type karein."
        "\n\nCancel karne ke liye /cancel type karein."
    )
    
    # Edit the message containing the button
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        context.user_data['last_bot_message_id'] = query.message.message_id # Store ID for deletion later
    except BadRequest as e:
        if "message is not modified" in str(e): pass
        else: logger.error(f"Bulk start edit error: {e}")
    except Exception as e:
         logger.error(f"Bulk start edit error: {e}")

    return ASK_START_NUMBER 

@admin_required
async def receive_start_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Start number save karta hai aur extractor ka naam poochta hai.
    """
    chat_id = update.effective_chat.id
    try:
        # User-facing number 1-based hai
        start_number = int(update.message.text.strip())
        if start_number < 1:
            start_number = 1 # Force start from 1 if user enters 0 or negative
    except ValueError:
        await update.message.reply_text("Invalid number. '1' se start kar raha hoon.")
        start_number = 1
    
    # 1-based start number store karein
    context.user_data['bulk_start_number'] = start_number 

    # "Start Number" prompt ko delete karein
    if 'last_bot_message_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
        except Exception: pass
            
    # User ka message (number) delete karein
    try:
        await update.message.delete()
    except Exception: pass

    # --- Ab extractor name poochhein ---
    text = (
        "📝 **Extractor ka Naam:**\n\n"
        "Aap jo test extract kar rahe hain, unke caption mein 'Extracted By:' ke baad kya naam aana chahiye?\n\n"
        "(Jaise: `H4R`, `Testbook Team`, etc.)\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    
    # Send the new prompt
    message = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
    context.user_data['last_bot_message_id'] = message.message_id # Store ID for the next step

    return ASK_EXTRACTOR_NAME


@admin_required
async def receive_extractor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Extractor ka naam save karta hai aur destination poochta hai.
    """
    extractor_name = update.message.text.strip()
    context.user_data['bulk_extractor_name'] = extractor_name
    
    chat_id = update.effective_chat.id
    
    # Try deleting the "Extractor ka Naam" prompt
    if 'last_bot_message_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
            # Don't pop yet, need it for the next message
        except Exception: pass
            
    # Delete the user's message (the name)
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
    
    # Send the new prompt
    message = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
    context.user_data['last_bot_message_id'] = message.message_id # Store ID for the next step

    return ASK_DESTINATION

@admin_required
async def receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Destination save karta hai aur file format poochta hai. (MODIFIED)
    """
    destination_input = update.message.text.strip()
    context.user_data['bulk_destination'] = destination_input
    
    chat_id = update.effective_chat.id

    # Try deleting the "Destination Chunein" prompt
    if 'last_bot_message_id' in context.user_data:
         try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
         except Exception: pass
         context.user_data.pop('last_bot_message_id', None) # Clean up the ID
            
    # Delete the user's message (the destination)
    try:
        await update.message.delete()
    except Exception: pass
        
    # --- Naya: Format poochhein ---
    text = (
        "💾 **File Format Chunein:**\n\n"
        "Aapko files kaunse format mein chahiye?\n\n"
        "Kripya reply karein:\n"
        "- `html` (Sirf HTML files)\n"
        "- `txt` (Sirf Text files)\n"
        "- `both` (HTML aur TXT dono)\n\n"
        "Cancel karne ke liye /cancel type karein."
    )
    
    message = await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)
    context.user_data['last_bot_message_id'] = message.message_id # Store ID for the next step

    return ASK_FORMAT_BULK # Naya state return karein

@admin_required
async def receive_format_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    (NAYA FUNCTION) File format save karta hai aur bulk download shuru karta hai.
    """
    file_format = update.message.text.strip().lower()
    
    if file_format not in ['html', 'txt', 'both']:
        await update.message.reply_text("Invalid format. Kripya `html`, `txt`, ya `both` type karein.")
        return ASK_FORMAT_BULK # State ko active rakhein

    context.user_data['bulk_format'] = file_format
    
    chat_id = update.effective_chat.id

    # Try deleting the "File Format Chunein" prompt
    if 'last_bot_message_id' in context.user_data:
         try:
            await context.bot.delete_message(chat_id, context.user_data['last_bot_message_id'])
         except Exception: pass
         context.user_data.pop('last_bot_message_id', None) # Clean up the ID
            
    # Delete the user's message (the format)
    try:
        await update.message.delete()
    except Exception: pass
        
    # Start the background task
    asyncio.create_task(perform_bulk_download(update, context))
    
    # End the conversation
    return ConversationHandler.END


async def cancel_bulk_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Bulk download conversation ko cancel karta hai.
    (MODIFIED: Naya state clean karein)
    """
    await clear_previous_message(context, update.effective_chat.id)
    
    # Send cancellation message if triggered by command
    if update.message:
        await update.message.reply_text("Bulk download cancel kar diya gaya hai.")
    
    # Cleanup user data specific to bulk download
    context.user_data.pop('bulk_query_data', None)
    context.user_data.pop('bulk_extractor_name', None)
    context.user_data.pop('bulk_start_number', None) 
    context.user_data.pop('bulk_destination', None)
    context.user_data.pop('bulk_format', None) # --- ADDED ---
    
    # Send main menu again
    await send_main_menu(update, context, "🏠 Main Menu")
    return ConversationHandler.END

# --- Bulk Download Logic (MODIFIED) ---
async def perform_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asynchronously sabhi tests ko download aur forward karta hai.
    (MODIFIED: Start number aur format ka istemal karega)
    """
    if not extractor:
        await update.message.reply_text("Bot abhi initialized nahi hai. Owner se /settoken karne ko kahein.")
        return
        
    user_chat_id = update.effective_chat.id
    
    # --- MODIFIED: Start number aur format lein ---
    query_data = context.user_data.get('bulk_query_data')
    extractor_name = context.user_data.get('bulk_extractor_name')
    destination = context.user_data.get('bulk_destination')
    file_format = context.user_data.get('bulk_format', 'html') # Default 'html'
    
    # 1-based start number lein, default 1
    start_from_number = context.user_data.get('bulk_start_number', 1) 
    # Slicing ke liye 0-based index banayein
    start_index = max(0, start_from_number - 1)
    
    # Stop flag set karein in bot_data using user_chat_id as key
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
                return ConversationHandler.END # End here if default channel not set
        elif destination.startswith('@') or destination.startswith('-100'):
            final_chat_id = destination
        else:
            await context.bot.send_message(user_chat_id, "Error: Invalid destination input. Process cancel kar diya gaya hai.")
            return ConversationHandler.END # End here for invalid input

        # 2. Tests ki list fetch karein
        series_details = context.user_data.get('series_details')
        if not series_details:
            await context.bot.send_message(user_chat_id, "Error: Session expire ho gaya hai. /start se dobara search karein.")
            return ConversationHandler.END

        tests_to_process = []
        parts = query_data.split('_') # e.g., "bulk_section_all" or "bulk_subsection_single"
        bulk_level_name = series_details.get('name', 'Series') # Default name

        if parts[1] == "section": # Download all tests in the entire series
            bulk_level_name = series_details.get('name', 'Series')
            for sec_idx, sec in enumerate(series_details.get('sections', [])):
                for sub_idx, sub in enumerate(sec.get('subsections', [])):
                    tests = extractor.get_tests_in_subsection(series_details['id'], sec['id'], sub['id'])
                    if tests:
                        tests_to_process.extend([(test, sec, sub) for test in tests])
                        
        elif parts[1] == "subsection": # Download related to a specific section
            selected_section = context.user_data.get('selected_section')
            if not selected_section:
                await context.bot.send_message(user_chat_id, "Error: Section data nahi mila. /start se dobara search karein.")
                return ConversationHandler.END
            bulk_level_name = selected_section.get('name', 'Section')

            if parts[2] == "all": # Download all tests in the selected section
                for sub_idx, sub in enumerate(selected_section.get('subsections', [])):
                    tests = extractor.get_tests_in_subsection(series_details['id'], selected_section['id'], sub['id'])
                    if tests:
                        tests_to_process.extend([(test, selected_section, sub) for test in tests])
            
            # (Note: "bulk_subsection_single" case yahaan se hata diya gaya hai kyonki UI use ab trigger nahi karta, 
            #  lekin logic rakha ja sakta hai agar zaroorat ho. Abhi ke liye yeh 'all' par hi chalega.)


        if not tests_to_process:
            await context.bot.send_message(user_chat_id, f"Error: '{bulk_level_name}' mein download karne ke liye koi tests nahi mile.")
            return ConversationHandler.END # End if no tests found

        # --- MODIFIED: List ko slice karein aur message update karein ---
        original_total = len(tests_to_process)
        if start_index > 0:
            if start_index >= original_total:
                await context.bot.send_message(user_chat_id, f"Error: Aapne {start_from_number} se start karne ko kaha, lekin total {original_total} tests hi hain. Process cancel kar diya gaya hai.")
                return ConversationHandler.END
            
            # List ko slice karein
            tests_to_process = tests_to_process[start_index:]
            
        total_tests_in_batch = len(tests_to_process) # Yeh naya total hai jo process hoga
        # --- End Naya Code ---

        progress_message = await context.bot.send_message(
            user_chat_id, 
            f"✅ Starting bulk download for **{bulk_level_name}** ({total_tests_in_batch} tests).\n"
            f"(Starting from number {start_from_number} of {original_total} total)\n" # User ko batayein
            f"Destination: `{final_chat_id}`\n"
            f"Format: `{file_format}`\n\n"
            "Rokne ke liye /stop type karein.",
            parse_mode=ParseMode.MARKDOWN
        )

        # --- Asli Download Loop (MODIFIED) ---
        last_update_time = asyncio.get_event_loop().time()
        completed_in_this_batch = 0 # Variable ka naam badal diya

        for test, sec, sub in tests_to_process:
            # Check for stop flag using user_chat_id as key in bot_data
            if context.bot_data.get(user_chat_id, {}).get(STOP_BULK_DOWNLOAD_FLAG, False):
                await progress_message.edit_text(f"🛑 Bulk download for **{bulk_level_name}** stopped after {completed_in_this_batch}/{total_tests_in_batch} tests.", parse_mode=ParseMode.MARKDOWN)
                break # Exit the loop
                
            completed_in_this_batch += 1
            # Asli test number (original list ke hisab se)
            actual_test_number = start_index + completed_in_this_batch 
            
            # File name mein asli number add karein
            base_file_name = f"{actual_test_number}. {test.get('title', 'test')[:50]}".replace('/', '_')


            try:
                # 1. Questions extract karein
                questions_data = extractor.extract_questions(test.get('id'))
                if questions_data.get('error'):
                    logger.warning(f"Test {base_file_name} skip kiya (Error: {questions_data.get('error')})")
                    continue
                
                # 2. Caption generate karein
                caption = extractor.get_caption(
                    test_summary=test,
                    series_details=series_details,
                    selected_section=sec,
                    subsection_context=sub,
                    extractor_name=extractor_name # Add extractor name here
                )
                
                # 3. Files generate karein
                files_to_send = []
                
                # Generate HTML if needed
                if file_format in ['html', 'both']:
                    html_content = generate_html(questions_data, extractor.last_details)
                    html_file = io.BytesIO(html_content.encode('utf-8'))
                    html_file.name = f"{base_file_name}.html"
                    files_to_send.append(html_file)
                
                # Generate TXT if needed
                if file_format in ['txt', 'both']:
                    # --- FIXED: extractor.last_details ko pass kiya ---
                    txt_content = generate_txt(questions_data, extractor.last_details) # Use new generator
                    txt_file = io.BytesIO(txt_content.encode('utf-8'))
                    txt_file.name = f"{base_file_name}.txt"
                    files_to_send.append(txt_file)

                
                # 4. Files ko destination par send karein
                for i, file_to_send in enumerate(files_to_send):
                    await context.bot.send_document(
                        chat_id=final_chat_id,
                        document=file_to_send,
                        caption=caption if i == 0 else None, # Sirf pehli file par caption
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # 5. Progress update karein (MODIFIED)
                current_time = asyncio.get_event_loop().time()
                # Har 5 file ya 3 second mein message update karein
                if completed_in_this_batch % 5 == 0 or current_time - last_update_time > 3:
                    last_update_time = current_time 
                    progress = completed_in_this_batch / total_tests_in_batch
                    bar = "🟩" * int(progress * 10) + "⬜️" * (10 - int(progress * 10))
                    
                    try:
                        await progress_message.edit_text(
                            f"📥 Downloading **{bulk_level_name}**...\n\n"
                            f"Progess: {bar} {completed_in_this_batch}/{total_tests_in_batch} ({int(progress * 100)}%)\n"
                            f"(Overall Test {actual_test_number}/{original_total})\n\n"
                            f"File: `{base_file_name}` (Format: {file_format})\n"
                            f"Destination: `{final_chat_id}`\n\n"
                            "Rokne ke liye /stop type karein.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    except BadRequest as e:
                        if "message is not modified" in str(e): pass
                        else: raise 
                
                await asyncio.sleep(1) # Rate limit avoidance
                
            except Exception as e:
                logger.error(f"Test {base_file_name} process karne mein error: {e}")
                await context.bot.send_message(user_chat_id, f"⚠️ Test `{base_file_name}` ko process karne mein error aaya: {e}", parse_mode=ParseMode.MARKDOWN)
                await asyncio.sleep(2) 

        # Check if download completed without being stopped (MODIFIED)
        if not context.bot_data.get(user_chat_id, {}).get(STOP_BULK_DOWNLOAD_FLAG, False):
            actual_test_number = start_index + completed_in_this_batch
            await progress_message.edit_text(f"✅ **Bulk Download Complete!**\n\n{completed_in_this_batch}/{total_tests_in_batch} tests (from {start_from_number} to {actual_test_number}) from **{bulk_level_name}** sent to `{final_chat_id}`.", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Bulk download mein bada error: {e}")
        await context.bot.send_message(user_chat_id, f"❌ Bulk download fail ho gaya: {e}")
        
    finally:
        # Clean up stop flag from bot_data
        context.bot_data.pop(user_chat_id, None)
        # Clean up user_data specific to this bulk download (MODIFIED)
        context.user_data.pop('bulk_query_data', None)
        context.user_data.pop('bulk_extractor_name', None)
        context.user_data.pop('bulk_start_number', None) 
        context.user_data.pop('bulk_destination', None)
        context.user_data.pop('bulk_format', None) # --- ADDED ---
        # Reset general state flags as well
        context.user_data.pop(STATE_WAITING_SEARCH_NUM, None)
        context.user_data.pop(STATE_WAITING_SECTION_NUM, None)
        context.user_data.pop(STATE_WAITING_TEST_NUM, None)



@admin_required
async def stop_bulk_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stop command handle karta hai."""
    user_chat_id = update.effective_chat.id
    # Check bot_data for the specific user's flag
    if user_chat_id in context.bot_data and not context.bot_data[user_chat_id].get(STOP_BULK_DOWNLOAD_FLAG, False):
        context.bot_data[user_chat_id][STOP_BULK_DOWNLOAD_FLAG] = True
        await update.message.reply_text("🛑 Stopping... Agla test complete hone ke baad bulk download ruk jayega.")
        # Return END to potentially exit ConversationHandler if called within it
        return ConversationHandler.END
    else:
        await update.message.reply_text("Abhi koi bulk download process active nahi hai.")
        # Return None or appropriate state if not ending a conversation
        return None


# =============================================================================
# === MAIN FUNCTION ===
# =============================================================================

async def set_bot_commands(application: Application):
    """Bot ke menu commands set karta hai."""
    # This function is now optional as post_init was removed due to errors
    # If kept, it needs error handling for application.bot access
    pass # Keeping it empty for now

def main():
    """Bot ko run karta hai."""
    
    # Pehli baar config files load/create karein
    load_json(ADMIN_FILE, {'admin_ids': []})
    load_json(CONFIG_FILE, {"testbook_token": None, "forward_channel_id": None})
    
    # Extractor ko initialize karein
    if not init_extractor():
        logger.warning("Bot shuru ho raha hai, lekin Testbook Token set nahi hai. /settoken ka istemal karein.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Bulk Download Conversation Handler (MODIFIED) ---
    bulk_download_conv = ConversationHandler(
        entry_points=[
            # These buttons are now shown in messages after text selection
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_section_all$"),
            CallbackQueryHandler(bulk_download_start, pattern="^bulk_subsection_all$"),
            # CallbackQueryHandler(bulk_download_start, pattern="^bulk_subsection_single$"), # Yeh wala ab use nahi ho raha
        ],
        states={
            # --- MODIFIED: Naye states add kiye ---
            ASK_START_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_start_number)],
            ASK_EXTRACTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_extractor_name)],
            ASK_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
            ASK_FORMAT_BULK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_format_bulk)], # Naya state
        },
        fallbacks=[
            CommandHandler("cancel", cancel_bulk_conversation),
            CommandHandler("stop", stop_bulk_download) # Stop can also exit the conversation
        ],
        conversation_timeout=600, # --- Timeout 600 seconds (10 min) kar diya ---
        per_message=False 
    )
    
    application.add_handler(bulk_download_conv)

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("search", search_command)) # Added /search
    
    # Owner Commands
    application.add_handler(CommandHandler("settoken", set_token))
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    application.add_handler(CommandHandler("adminlist", admin_list))
    
    # Admin Commands
    application.add_handler(CommandHandler("setchannel", set_channel))
    application.add_handler(CommandHandler("removechannel", remove_channel))
    application.add_handler(CommandHandler("viewchannel", view_channel))
    application.add_handler(CommandHandler("stop", stop_bulk_download)) 

    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$")) # Keep main menu callback


    # Text handler (handles number inputs based on state)
    # Yeh handler naye STATE_WAITING_FORMAT_SINGLE ko bhi handle karega
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))

    logger.info("Bot shuru ho raha hai...")
    
    # Bot ko run karein
    application.run_polling()

if __name__ == '__main__':
    main()

