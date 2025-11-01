import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
import pytz

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

# Додаємо часовий пояс
TIMEZONE = pytz.timezone('Europe/Kyiv')

def get_schedule_content():
    """Отримує HTML-контент з сайту та витягує розклад відключень"""
    response = requests.get(URL)
    response.encoding = 'windows-1251'
    soup = BeautifulSoup(response.text, 'html.parser')
    
    important_header = soup.find('h2')
    
    if not important_header:
        return None
    
    content_parts = [important_header.get_text(strip=True)]
    current = important_header.next_sibling
    
    while current:
        if hasattr(current, 'name'):
            if current.name in ['table', 'form', 'h2', 'h3']:
                break
            elif current.name == 'br':
                current = current.next_sibling
                continue
        else:
            text = str(current).strip()
            if text and 'Пошук' not in text and 'Оберіть' not in text:
                content_parts.append(text)
            elif 'Пошук' in text or 'Оберіть' in text:
                break
        
        current = current.next_sibling
    
    result = '\n'.join(content_parts)
    return result if len(result) > 50 else None

def get_content_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def load_previous_hash():
    try:
        with open('last_hash.json', 'r') as f:
            data = json.load(f)
            return data.get('hash'), data.get('content')
    except FileNotFoundError:
        return None, None

def save_hash(content_hash, content):
    with open('last_hash.json', 'w') as f:
        json.dump({
            'hash': content_hash,
            'content': content,
            'timestamp': datetime.now(TIMEZONE).isoformat()
        }, f, ensure_ascii=False, indent=2)

def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    response = requests.post(url, json=payload)
    return response.json()

def main():
    print(f"Перевірка сайту: {URL}")
    print(f"Час перевірки: {datetime.now(TIMEZONE).isoformat()}")
    
    current_content = get_schedule_content()
    
    if not current_content:
        print("Не вдалося отримати контент з сайту")
        return
    
    current_hash = get_content_hash(current_content)
    previous_hash, previous_content = load_previous_hash()
    
    print(f"Поточний хеш: {current_hash}")
    print(f"Попередній хеш: {previous_hash}")
    
    if current_hash != previous_hash:
        print("Виявлено зміни в розкладі!")
        
        message = f"🔔 <b>УВАГА! ОНОВЛЕННЯ РОЗКЛАДУ ВІДКЛЮЧЕНЬ</b>\n\n"
        message += f"⏰ Час оновлення: {datetime.now(TIMEZONE).strftime('%d.%m.%Y %H:%M')}\n\n"
        message += f"📋 <b>Новий розклад:</b>\n\n"
        message += current_content[:4000]
        
        result = send_telegram_message(message)
        print(f"Результат надсилання: {result}")
        
        save_hash(current_hash, current_content)
    else:
        print("Змін не виявлено")

if __name__ == '__main__':
    main()
