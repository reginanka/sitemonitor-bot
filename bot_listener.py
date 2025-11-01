import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

def load_subscribers():
    try:
        with open('subscribers.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_subscribers(subscribers):
    with open('subscribers.json', 'w', encoding='utf-8') as f:
        json.dump(subscribers, f, indent=2)

def load_last_schedule():
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('content'), data.get('timestamp')
    except FileNotFoundError:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    subscribers = load_subscribers()
    
    if chat_id not in subscribers:
        subscribers.append(chat_id)
        save_subscribers(subscribers)
        message = "✅ Підписка активна!\n\n📅 /schedule - графік\n🛑 /stop - відписатись"
    else:
        message = "Ви вже підписані!\n\n📅 /schedule - графік\n🛑 /stop - відписатись"
    
    await update.message.reply_text(message)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    subscribers = load_subscribers()
    
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers(subscribers)
        message = "✅ Відписка успішна"
    else:
        message = "Ви не підписані"
    
    await update.message.reply_text(message)

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content, timestamp = load_last_schedule()
    
    if not content:
        await update.message.reply_text("📅 Інформація відсутня")
        return
    
    try:
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime('%d.%m.%Y %H:%M')
    except:
        time_str = timestamp
    
    formatted = content.replace('<br>', '\n').replace('<br/>', '\n')
    message = f"📅 <b>Графік відключень</b>\n\n<i>{time_str}</i>\n\n{formatted[:3900]}"
    
    await update.message.reply_text(message, parse_mode='HTML')

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("schedule", schedule))
    
    print("🤖 Бот запущено")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
