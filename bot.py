# bot.py

import os
import logging
import requests
from io import BytesIO

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

import google.generativeai as genai

# yt-dlp ကို video info နဲ့ download အတွက် သုံးပါမယ်။
import yt_dlp

# --- လုံခြုံရေးအတွက် API Key များကို Environment Variables မှတစ်ဆင့် ရယူခြင်း ---
# ဒီ key တွေကို Render.com မှာ သတ်မှတ်ပေးရပါမယ်။
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Gemini AI ကို ပြင်ဆင်ခြင်း
genai.configure(api_key=GEMINI_API_KEY)
# Gemini Pro Vision model ကိုသုံးပြီး ပုံတွေကို နားလည်စေပါမယ်။
vision_model = genai.GenerativeModel('gemini-pro-vision')

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
                'thumbnail_url': thumbnail_url,
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

            # Video Formats (360p, 480p)
            video_resolutions = [360, 480]
            for res in video_resolutions:
                # mp4 format ကိုပဲရွေးမယ်။ audio ပါပြီးသားဖြစ်ရမယ်။
                video_format = [
                    f for f in formats 
                    if f.get('height') == res and f.get('ext') == 'mp4' and f.get('acodec') != 'none'
                ]
                if video_format:
                    # အကောင်းဆုံး format ကိုရွေးမယ်
                    best_video = max(video_format, key=lambda f: f.get('tbr', 0))
                    file_size = format_bytes(best_video.get('filesize') or best_video.get('filesize_approx'))
                    keyboard.append([InlineKeyboardButton(
                        f"🎬 {res}p Video ({file_size})",
                        callback_data=f"download_video_{res}_{video_id}"
                    )])
            
            # AI Cover Art Button
            if thumbnail_url:
                keyboard.append([InlineKeyboardButton(
                    "🎨 AI Music Cover Art ဖန်တီးမယ်",
                    callback_data=f"generate_art_{video_id}"
                )])

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

    elif action == "generate":
        video_id = parts[-1]
        video_info = context.user_data.get(video_id, {})
        thumbnail_url = video_info.get('thumbnail_url')
        video_title = video_info.get('title', 'a song')

        if not thumbnail_url:
            await query.edit_message_text(text="Error: Thumbnail not found.")
            return
        
        await query.edit_message_text(text="🎨 AI ကို Cover Art ဖန်တီးခိုင်းနေပါတယ်။ ခဏစောင့်ပေးပါ...")

        try:
            # Thumbnail ပုံကို download ဆွဲမယ်
            response = requests.get(thumbnail_url)
            img = BytesIO(response.content)
            img.seek(0) # Reset buffer position
            
            # Gemini Pro Vision ကိုသုံးပြီး ပုံကိုဖော်ပြခိုင်းမယ်၊ ပြီးတော့ cover art idea တောင်းမယ်။
            # မှတ်ချက်: Gemini Pro Vision ဟာ ပုံအသစ်ဖန်တီးပေးတာမဟုတ်ဘဲ၊ ရှိပြီးသားပုံကို နားလည်ပြီး စာသားဖန်တီးပေးတာပါ။
            # ဒီကနေရတဲ့ idea ကို တခြား Text-to-Image AI (ဥပမာ Midjourney) မှာသုံးနိုင်ပါတယ်။
            # ဒီမှာတော့ Gemini ကိုပဲသုံးပြီး creative description ဖန်တီးခိုင်းပါမယ်။
            
            prompt = (
                f"This is a thumbnail for a video titled '{video_title}'. "
                "Analyze the image and the title. Based on them, write a creative and evocative description for a music album cover. "
                "Describe the mood, the colors, the style, and the overall concept. "
                "Make it sound like a professional art director's brief. "
                "Start with 'Album Cover Concept:'"
            )

            # Gemini API call
            response = vision_model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img.read()}])
            
            ai_description = response.text

            await query.edit_message_text(text=ai_description)

        except Exception as e:
            logging.error(f"AI generation failed: {e}")
            await query.edit_message_text(text=f"❌ AI Cover Art ဖန်တီးရာတွင် အမှားတစ်ခုဖြစ်ပွားပါတယ်။: {e}")


def main() -> None:
    """Bot ကို စတင်လည်ပတ်စေရန်။"""
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: TELEGRAM_TOKEN or GEMINI_API_KEY not found !!!")
        print("!!! Please set them in your environment variables.     !!!")
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
