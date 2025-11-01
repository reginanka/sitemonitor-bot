import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')  # -1001234567890
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

def get_schedule_content():
    """Витягує важливе повідомлення з сайту"""
    try:
        response = requests.get(URL, timeout=10)
        response.encoding = 'windows-1251'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Замінюємо <br> на \n ПЕРЕД витягуванням тексту
        for br in soup.find_all('br'):
            br.replace_with('\n')
        
        # Шукаємо блок з "УВАГА! ВАЖЛИВА ІНФОРМАЦІЯ!"
        for elem in soup.find_all(['div', 'span', 'p', 'h2', 'h3']):
            text = elem.get_text(strip=False)
            if 'УВАГА' in text and 'ВАЖЛИВА' in text:
                # Очищаємо зайві порожні рядки
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                result = '\n'.join(lines)
                print(f"✅ Знайдено повідомлення: {result[:100]}...")
                return result
        
        print("⚠️ Повідомлення не знайдено")
        return None
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return None

def get_last_hash():
    """Отримує останній хеш"""
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            return json.load(f).get('hash')
    except:
        print("⚠️ last_hash.json не знайдено (перший запуск)")
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
    print(f"💾 Хеш збережено: {content_hash}")
    return content_hash

def send_to_channel(message):
    """Відправляє повідомлення в Telegram канал"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Додаємо посилання на сайт внизу повідомлення
    full_message = (
        f"{message}\n\n"
        f"➡️ <a href=\"https://www.ztoe.com.ua/unhooking-search.php\">Переглянути графік на сайті</a>"
    )
    
    try:
        response = requests.post(url, json={
            'chat_id': TELEGRAM_CHANNEL_ID,
            'text': full_message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': False  # Показувати превʼю сайту
        }, timeout=10)
        
        if response.status_code == 200:
            print("✅ Повідомлення відправлено в канал")
            return True
        else:
            print(f"❌ Помилка Telegram API: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")
        return False

def main():
    print("=" * 50)
    print("🔍 МОНІТОРИНГ ГРАФІКА ВІДКЛЮЧЕНЬ")
    print("=" * 50)
    
    # Отримуємо контент з сайту
    content = get_schedule_content()
    if not content:
        print("❌ Не вдалося отримати контент")
        return
    
    # Обчислюємо хеш
    current_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
    last_hash = get_last_hash()
    
    print(f"🔑 Поточний хеш: {current_hash}")
    print(f"🔑 Попередній хеш: {last_hash}")
    
    # Порівнюємо
    if last_hash == current_hash:
        print("✅ Змін немає. Завершення.")
        return
    
    print("🔔 ВИЯВЛЕНІ ЗМІНИ!")
    
    # Формуємо повідомлення
    message = f"🔔 <b>ОНОВЛЕННЯ ГРАФІКА ВІДКЛЮЧЕНЬ</b>\n\n{content}"
    
    # Відправляємо в канал
    if send_to_channel(message):
        save_hash(content)
        print("✅ Успішно!")
    else:
        print("❌ Не вдалося відправити")

if __name__ == '__main__':
    main()
