import os
import json
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TIMEZONE = pytz.timezone('Europe/Kyiv')

def load_subscribers():
    try:
        with open('subscribers.json', 'r') as f:
            return json.load(f)
    except:
        return []

def save_subscribers(subs):
    with open('subscribers.json', 'w') as f:
        json.dump(subs, f)

def load_schedule():
    try:
        with open('last_hash.json', 'r') as f:
            data = json.load(f)
            return data.get('content', ''), data.get('timestamp')
    except:
        return '', None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    subs = load_subscribers()
    if cid not in subs:
        subs.append(cid)
        save_subscribers(subs)
    await update.message.reply_text("✅ Підписано!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = str(update.effective_chat.id)
    subs = load_subscribers()
    if cid in subs:
        subs.remove(cid)
        save_subscribers(subs)
    await update.message.reply_text("❌ Відписано!")

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content, ts = load_schedule()
    if not content:
        await update.message.reply_text("❌ Графік не завантажено")
        return
    msg = f"📋 ГРАФІК\n\n{content[:3900]}"
    await update.message.reply_text(msg, parse_mode='HTML')

if __name__ == '__main__':
    if TELEGRAM_BOT_TOKEN:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stop", stop))
        app.add_handler(CommandHandler("schedule", schedule))
        app.run_polling()
