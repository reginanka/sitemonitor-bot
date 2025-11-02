import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')  # -1001234567890
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

def get_schedule_content():
    """Витягує важливе повідомлення з сайту"""
    try:
        response = requests.get(URL, timeout=10)
        response.encoding = 'windows-1251'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Замінюємо на \n ПЕРЕД витягуванням тексту
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

def send_to_channel(message, screenshot_path=None):
    """Відправляє скріншот + текст в одному повідомленні"""
    
    try:
        if screenshot_path and os.path.exists(screenshot_path):
            # Відправляємо фото з текстом як caption
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            
            full_message = f"{message}\n\n➡️ <a href='{URL}'>Переглянути графік на сайті</a>"
            
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
    
    # Створюємо скріншот
    screenshot_path = take_screenshot()
    
    # Формуємо повідомлення
    message = f"🔔 ОНОВЛЕННЯ ГРАФІКА ВІДКЛЮЧЕНЬ\n\n{content}"
    
    # Відправляємо в канал
    if send_to_channel(message, screenshot_path):
        save_hash(content)
        print("✅ Успішно!")
    else:
        print("❌ Не вдалося відправити")

if __name__ == '__main__':
    main()
