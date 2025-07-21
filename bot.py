# bot.py (Updated Version)

import os
import logging

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# yt-dlp ကို video info နဲ့ download အတွက် သုံးပါမယ်။
import yt_dlp

# --- လုံခြုံရေးအတွက် API Key များကို Environment Variables မှတစ်ဆင့် ရယူခြင်း ---
# ဒီ key တွေကို Render.com မှာ သတ်မှတ်ပေးရပါမယ်။
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Gemini API Key မလိုအပ်တော့ပါဘူး။

# Logging ကို enable လုပ်ထားပါမယ်။ Error ရှာရလွယ်အောင်ပါ။
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Helper function: ဖိုင်ဆိုဒ်ကို လူဖတ်လို့လွယ်တဲ့ format ပြောင်းပေးရန်
def format_bytes(size):
    if size is None:
        return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}
    while size > power and n < len(power_labels) -1 :
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}"

# /start command အတွက် handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User က /start လို့ရိုက်ထည့်ရင် ကြိုဆို message ပို့ပါမယ်။"""
    user = update.effective_user
    await update.message.reply_html(
        rf"မင်္ဂလာပါ {user.mention_html()}! 👋",
        reply_markup=None,
    )
    await update.message.reply_text(
        "ကြိုက်တဲ့ video link တစ်ခုခု (YouTube, Facebook, TikTok, etc.) ကို ပို့ပေးပါ။ "
        "ကျွန်တော် download options တွေ ပြပေးပါမယ်။"
    )

# Video link တွေကို လက်ခံမယ့် handler
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User ပို့လိုက်တဲ့ link ကိုစစ်ဆေးပြီး download options တွေပြပါမယ်။"""
    video_url = update.message.text
    processing_message = await update.message.reply_text("🔎 Link ကို စစ်ဆေးနေပါတယ်... ခဏစောင့်ပေးပါ...")

    try:
        # yt-dlp options
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            video_title = info_dict.get('title', 'No Title')
            thumbnail_url = info_dict.get('thumbnail', None)
            formats = info_dict.get('formats', [])
            video_id = info_dict.get('id', None)

            # context မှာ video info ကို ခဏသိမ်းထားမယ်။
            context.user_data[video_id] = {
                'title': video_title,
                'video_url': video_url
            }

            keyboard = []
            
            # --- Download Options တွေကို ရှာဖွေခြင်း ---
            # MP3 (Audio only)
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
            if audio_formats:
                best_audio = max(audio_formats, key=lambda f: f.get('abr', 0))
                file_size = format_bytes(best_audio.get('filesize') or best_audio.get('filesize_approx'))
                keyboard.append([InlineKeyboardButton(
                    f"🎵 MP3 Audio ({file_size})",
                    callback_data=f"download_audio_{video_id}"
                )])

            # Video Formats (360p, 480p, 720p, 1080p)
            video_resolutions = [360, 480, 720, 1080]
            found_resolutions = set()

            for f in formats:
                height = f.get('height')
                if height in video_resolutions and height not in found_resolutions:
                    # mp4 format ကိုပဲရွေးမယ်။ audio ပါပြီးသားဖြစ်ရမယ်။
                    if f.get('ext') == 'mp4' and f.get('acodec') != 'none':
                        file_size = format_bytes(f.get('filesize') or f.get('filesize_approx'))
                        keyboard.append([InlineKeyboardButton(
                            f"🎬 {height}p Video ({file_size})",
                            callback_data=f"download_video_{height}_{video_id}"
                        )])
                        found_resolutions.add(height)

            if not keyboard:
                await processing_message.edit_text("❌ দুঃখিত, ဒီ link အတွက် download လုပ်နိုင်တဲ့ format တွေ ရှာမတွေ့ပါဘူး။")
                return

            reply_markup = InlineKeyboardMarkup(keyboard)
            
            caption = f"**{video_title}**\n\nဘယ် format နဲ့ download လုပ်ချင်လဲ ရွေးချယ်ပါ:"
            
            await processing_message.delete() # "Processing" message ကိုဖျက်မယ်။
            if thumbnail_url:
                await update.message.reply_photo(photo=thumbnail_url, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Error processing link: {e}")
        await processing_message.edit_text("❌ দুঃখিত, ဒီ link ကို download လုပ်လို့မရပါဘူး။ link မှန်မမှန် စစ်ဆေးပြီး ထပ်ကြိုးစားကြည့်ပါ။")


# Button တွေကို နှိပ်ရင် အလုပ်လုပ်မယ့် handler
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Callback query ကို လက်ခံကြောင်းပြရန်

    data = query.data
    parts = data.split('_')
    action = parts[0]
    
    if action == "download":
        media_type = parts[1]
        video_id = parts[-1]
        
        video_info = context.user_data.get(video_id, {})
        video_url = video_info.get('video_url')
        video_title = video_info.get('title', 'video')

        if not video_url:
            await query.edit_message_text(text="Error: Video information not found. Please send the link again.")
            return

        await query.edit_message_text(text=f"⏳ Downloading... ခဏစောင့်ပေးပါ။ ဒါဟာ ဖိုင်ဆိုဒ်ပေါ်မူတည်ပြီး အချိန်အနည်းငယ်ကြာနိုင်ပါတယ်။")

        try:
            output_path = f'{video_id}.%(ext)s'
            if media_type == "audio":
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': output_path.replace('.%(ext)s', ''),
                }
                file_ext = 'mp3'
            else: # video
                resolution = parts[2]
                ydl_opts = {
                    'format': f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/best[height<={resolution}][ext=mp4]',
                    'outtmpl': output_path,
                }
                file_ext = 'mp4'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            downloaded_file = f'{video_id}.{file_ext}'
            
            await query.edit_message_text(text="✅ Download ပြီးပါပြီ။ သင့်ဆီကို ပို့ပေးနေပါတယ်။")
            
            # ဖိုင်ကို user ဆီပို့မယ်
            if media_type == "audio":
                await context.bot.send_audio(chat_id=query.message.chat_id, audio=open(downloaded_file, 'rb'), title=video_title, filename=f"{video_title}.mp3")
            else:
                await context.bot.send_video(chat_id=query.message.chat_id, video=open(downloaded_file, 'rb'), supports_streaming=True, filename=f"{video_title}.mp4")

            # server ပေါ်က file ကို ဖျက်မယ်
            os.remove(downloaded_file)

        except Exception as e:
            logging.error(f"Download failed: {e}")
            await query.edit_message_text(text=f"❌ Download လုပ်ရာတွင် အမှားတစ်ခုဖြစ်ပွားပါတယ်။: {e}")
    
    # AI Cover Art feature ကို ဖြုတ်လိုက်ပါပြီ။

def main() -> None:
    """Bot ကို စတင်လည်ပတ်စေရန်။"""
    if not TELEGRAM_TOKEN:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: TELEGRAM_TOKEN not found                  !!!")
        print("!!! Please set it in your environment variables.     !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))

    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Bot ကို စတင် run မယ်
    print("Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
