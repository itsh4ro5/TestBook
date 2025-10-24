# -*- coding: utf-8 -*-
import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes, 
    ConversationHandler, MessageHandler, filters  # 'Filters' ko 'filters' se badal diya gaya hai
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import io
import asyncio  # Live progress bar ke liye
import time

from extractor import TestbookExtractor
from html_generator import generate_html
from config import TELEGRAM_BOT_TOKEN, BOT_OWNER_ID

# ... baaki code ...

# --- State Definitions for Bulk Download ---
ASK_EXTRACTOR_NAME, ASK_DESTINATION = range(2)

# ... baaki code ...

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
            # Yahaan 'Filters' ko 'filters' se badla gaya hai
            ASK_EXTRACTOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_extractor_name)],
            ASK_DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_destination)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_bulk_conversation),
            CommandHandler("stop", stop_bulk_download) # Stop ko bhi fallback banayein
        ],
        conversation_timeout=600 # 10 minute timeout
    )
    
    application.add_handler(bulk_download_conv)
    # --- END NAYA HANDLER ---

    # ... baaki handlers ...
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
    # Yahaan 'Filters' ko 'filters' se badla gaya hai
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))

    logger.info("Bot shuru ho raha hai...")
    application.run_polling()

if __name__ == "__main__":
    main()


