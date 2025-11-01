import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

def get_subscribers():
    """Завантажує список підписників"""
    try:
        with open('subscribers.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def get_schedule_content():
    """Витягує важливе повідомлення з сайту"""
    try:
        response = requests.get(URL, timeout=10)
        response.encoding = 'windows-1251'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Шукаємо блок з УВАГА! ВАЖЛИВА ІНФОРМАЦІЯ!
        for elem in soup.find_all(['div', 'span', 'p', 'h2', 'h3']):
            text = elem.get_text(strip=True)
            if 'УВАГА' in text and 'ВАЖЛИВА' in text:
                logger.info(f"✅ Знайдено повідомлення")
                return text
        
        logger.warning("⚠️ Повідомлення не знайдено")
        return None
        
    except Exception as e:
        logger.error(f"❌ Помилка: {e}")
        return None

def get_last_hash():
    """Отримує останній хеш"""
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('hash')
    except:
        return None

def save_hash(content):
    """Зберігає хеш"""
    content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    with open('last_hash.json', 'w', encoding='utf-8') as f:
        json.dump({
            'hash': content_hash,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
    return content_hash

def send_to_telegram(chat_id, message):
    """Відправляє повідомлення"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    try:
        response = requests.post(url, json={
            'chat_id': chat_id,
            'text': message.replace('<br>', '\n').replace('<br/>', '\n'),
            'parse_mode': 'HTML'
        }, timeout=10)
        
        return response.status_code == 200
    except:
        return False

def main():
    logger.info("🔍 Перевірка оновлень...")
    
    content = get_schedule_content()
    if not content:
        return
    
    current_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    last_hash = get_last_hash()
    
    if last_hash == current_hash:
        logger.info("✅ Змін немає")
        return
    
    logger.info("🔔 ЗМІНИ ВИЯВЛЕНІ! Відправка...")
    
    subscribers = get_subscribers()
    if not subscribers:
        logger.warning("⚠️ Немає підписників")
        return
    
    message = f"🔔 <b>ОНОВЛЕННЯ ГРАФІКА</b>\n\n{content}"
    
    for chat_id in subscribers:
        send_to_telegram(chat_id, message)
    
    save_hash(content)
    logger.info("✅ Готово!")

if __name__ == '__main__':
    main()
