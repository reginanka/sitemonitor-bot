import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

def get_schedule_content():
    """Витягує два блоки: важливе повідомлення та дату оновлення"""
    try:
        response = requests.get(URL, timeout=10)
        response.encoding = 'windows-1251'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Замінюємо <br> на \n
        for br in soup.find_all('br'):
            br.replace_with('\n')
        
        important_message = None
        update_date = None
        
        # Шукаємо блок з "УВАГА! ВАЖЛИВА ІНФОРМАЦІЯ!"
        for elem in soup.find_all(['div', 'span', 'p', 'h2', 'h3']):
            text = elem.get_text(strip=False)
            
            # Перший блок: важливе повідомлення
            if 'УВАГА' in text and 'ВАЖЛИВА' in text and important_message is None:
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                important_message = '\n'.join(lines)
                print(f"✅ Знайдено важливе повідомлення: {important_message[:100]}...")
            
            # Другий блок: дата оновлення
            if 'Дата оновлення інформації' in text and update_date is None:
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                update_date = '\n'.join(lines)
                print(f"✅ Знайдено дату оновлення: {update_date}")
        
        if not important_message:
            print("⚠️ Важливе повідомлення не знайдено")
        if not update_date:
            print("⚠️ Дата оновлення не знайдена")
            
        return important_message, update_date
        
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return None, None

def take_screenshot():
    """Створює скріншот сайту"""
    try:
        print("📸 Створюю скріншот...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)
            page.screenshot(path='screenshot.png', full_page=True)
            browser.close()
        print("✅ Скріншот створено")
        return 'screenshot.png'
    except Exception as e:
        print(f"❌ Помилка створення скріншоту: {e}")
        return None

def get_last_hashes():
    """Отримує останні хеші обох блоків"""
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('hash_message'), data.get('hash_date')
    except:
        print("⚠️ last_hash.json не знайдено (перший запуск)")
        return None, None

def save_hashes(message_content, date_content):
    """Зберігає хеші обох блоків"""
    hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest() if message_content else None
    hash_date = hashlib.md5(date_content.encode('utf-8')).hexdigest() if date_content else None
    
    with open('last_hash.json', 'w', encoding='utf-8') as f:
        json.dump({
            'hash_message': hash_message,
            'hash_date': hash_date,
            'content_message': message_content,
            'content_date': date_content,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Хеш повідомлення збережено: {hash_message}")
    print(f"💾 Хеш дати збережено: {hash_date}")
    return hash_message, hash_date

def send_to_channel(message_content, date_content, screenshot_path=None):
    """Відправляє скріншот + обидва тексти в одному повідомленні"""
    try:
        if screenshot_path and os.path.exists(screenshot_path):
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            
            # Формуємо повідомлення з обох блоків (дата в кінці)
            full_message = f"🔔 ОНОВЛЕННЯ ГРАФІКА ВІДКЛЮЧЕНЬ\n\n{message_content}\n\n➡️ Переглянути графік на сайті"
            
            if date_content:
                full_message += f"\n\n{date_content}"
            
            with open(screenshot_path, 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': TELEGRAM_CHANNEL_ID,
                    'caption': full_message,
                    'parse_mode': 'HTML'
                }
                
                response = requests.post(photo_url, files=files, data=data, timeout=30)
                
                if response.status_code == 200:
                    print("✅ Фото + текст відправлено одним повідомленням")
                    return True
                else:
                    print(f"❌ Помилка: {response.text}")
                    return False
        else:
            print("❌ Скріншот не знайдено")
            return False
            
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return False

def main():
    print("=" * 50)
    print("🔍 МОНІТОРИНГ ГРАФІКА ВІДКЛЮЧЕНЬ")
    print("=" * 50)
    
    # Отримуємо обидва блоки з сайту
    message_content, date_content = get_schedule_content()
    
    if not message_content and not date_content:
        print("❌ Не вдалося отримати контент")
        return
    
    # Обчислюємо хеші
    current_hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest() if message_content else None
    current_hash_date = hashlib.md5(date_content.encode('utf-8')).hexdigest() if date_content else None
    
    last_hash_message, last_hash_date = get_last_hashes()
    
    print(f"🔑 Поточний хеш повідомлення: {current_hash_message}")
    print(f"🔑 Попередній хеш повідомлення: {last_hash_message}")
    print(f"🔑 Поточний хеш дати: {current_hash_date}")
    print(f"🔑 Попередній хеш дати: {last_hash_date}")
    
    # Порівнюємо - якщо хоча б один змінився
    message_changed = last_hash_message != current_hash_message
    date_changed = last_hash_date != current_hash_date
    
    if not message_changed and not date_changed:
        print("✅ Змін немає. Завершення.")
        return
    
    print("🔔 ВИЯВЛЕНІ ЗМІНИ!")
    if message_changed:
        print("   📝 Змінилося важливе повідомлення")
    if date_changed:
        print("   📅 Змінилася дата оновлення")
    
    # Створюємо скріншот
    screenshot_path = take_screenshot()
    
    # Відправляємо в канал (обидва блоки разом)
    if send_to_channel(message_content, date_content, screenshot_path):
        save_hashes(message_content, date_content)
        print("✅ Успішно!")
    else:
        print("❌ Не вдалося відправити")

if __name__ == '__main__':
    main()
