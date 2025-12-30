import os
from datetime import datetime
from typing import List
import pytz
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_LOG_CHANNEL_ID = os.getenv("TELEGRAM_LOG_CHANNEL_ID")
UKRAINE_TZ = pytz.timezone("Europe/Kyiv")

log_messages: List[str] = []

def get_ukraine_time() -> datetime:
    return datetime.now().astimezone(UKRAINE_TZ)

def log_to_buffer(message: str) -> None:
    ts = get_ukraine_time().strftime("%H:%M:%S")
    log_messages.append(f"{ts} - {message}")

def save_logs_to_file():
    """Зберігає логи у файл для GitHub Artifacts"""
    try:
        with open('monitor.log', 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_messages) + '\n')
        print("💾 Логи збережено в monitor.log")
    except Exception:
        pass

def send_log_to_channel():
    """Спроба відправити в Telegram + fallback на файл"""
    if not TELEGRAM_LOG_CHANNEL_ID or not TELEGRAM_BOT_TOKEN:
        save_logs_to_file()
        return
    
    text = format_log_message()
    
    # Retry з проксі для України
    session = requests.Session()
    retry_strategy = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_LOG_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    
    try:
        response = session.post(url, data=data, timeout=20)
        response.raise_for_status()
        print("📤 Лог відправлено в Telegram")
    except Exception as e:
        print(f"❌ Telegram недоступний: {e}")
        save_logs_to_file()  # Fallback

def format_log_message() -> str:
    current_time = get_ukraine_time()
    header = f"""📊 ЛОГ ВИКОНАННЯ СКРИПТА

{("="*60)}
🚀 СТАРТ [{current_time.strftime("%Y-%m-%d %H:%M:%S")}]"""
    
    logs_html = "<pre>" + "\n".join(log_messages) + "</pre>"
    
    footer = f"""
{("="*60)}
⏰ Завершено: {current_time.strftime("%d.%m.%Y %H:%M:%S")} (Київський час)"""
    
    return f"{header}\n\n{logs_html}\n\n{footer}"
