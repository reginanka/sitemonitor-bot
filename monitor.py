import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
TELEGRAM_LOG_CHANNEL_ID = os.environ.get('TELEGRAM_LOG_CHANNEL_ID')
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

# Часовий пояс України
UKRAINE_TZ = pytz.timezone('Europe/Kyiv')
# Змінна для збору логів
log_messages = []

def log(message):
    """Додає повідомлення до логу та виводить у консоль"""
    print(message)
    log_messages.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")

def send_log_to_channel():
    """Відправляє зібрані логи у лог-канал"""
    if not TELEGRAM_LOG_CHANNEL_ID or not log_messages:
        return
    
    try:
        log_text = "📊 <b>ЛОГ ВИКОНАННЯ СКРИПТА</b>\n\n"
        log_text += "\n".join(log_messages)
        log_text += f"\n\n⏰ Завершено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_LOG_CHANNEL_ID,
            'text': log_text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print("✅ Лог відправлено у лог-канал")
        else:
            print(f"❌ Помилка відправки логу: {response.text}")
    except Exception as e:
        print(f"❌ Помилка відправки логу: {e}")

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
                log(f"✅ Знайдено важливе повідомлення: {important_message[:100]}...")
            
            # Другий блок: дата оновлення
            if 'Дата оновлення інформації' in text and update_date is None:
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                update_date = '\n'.join(lines)
                log(f"✅ Знайдено дату оновлення: {update_date}")
        
        if not important_message:
            log("⚠️ Важливе повідомлення не знайдено")
        if not update_date:
            log("⚠️ Дата оновлення не знайдена")
        
        return important_message, update_date
    
    except Exception as e:
        log(f"❌ Помилка отримання контенту: {e}")
        return None, None

def take_screenshot():
    """Створює скріншот сайту"""
    try:
        log("📸 Створюю скріншот...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)
            page.screenshot(path='screenshot.png', full_page=True)
            browser.close()
        log("✅ Скріншот створено")
        return 'screenshot.png'
    except Exception as e:
        log(f"❌ Помилка створення скріншоту: {e}")
        return None

def get_last_hash():
    """Отримує останній хеш важливого повідомлення"""
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('hash_message')
    except:
        log("⚠️ last_hash.json не знайдено (перший запуск)")
        return None

def save_hash(message_content, date_content):
    """Зберігає хеш лише важливого повідомлення"""
    hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest() if message_content else None
    with open('last_hash.json', 'w', encoding='utf-8') as f:
        json.dump({
            'hash_message': hash_message,
            'content_message': message_content,
            'content_date': date_content,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)
    log(f"💾 Хеш повідомлення збережено: {hash_message}")
    return hash_message

def send_to_channel(message_content, date_content, screenshot_path=None):
    """Відправляє повідомлення у форматі, який ви вказали"""
    try:
        if screenshot_path and os.path.exists(screenshot_path):
            photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            
            # Формуємо повідомлення у вашому форматі
            full_message = f"🔔 ОНОВЛЕННЯ ГРАФІКА ВІДКЛЮЧЕНЬ\n\n{message_content}\n\n➡️ <a href='{URL}'>Переглянути графік на сайті</a>"
            
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
                    log("✅ Фото + текст відправлено у головний канал")
                    return True
                else:
                    log(f"❌ Помилка відправки у канал: {response.text}")
                    return False
        else:
            log("❌ Скріншот не знайдено")
            return False
    
    except Exception as e:
        log(f"❌ Помилка відправки у канал: {e}")
        return False

def main():
    log("=" * 50)
    log("🔍 МОНІТОРИНГ ГРАФІКА ВІДКЛЮЧЕНЬ")
    log("=" * 50)
    
    try:
        # Отримуємо обидва блоки з сайту
        message_content, date_content = get_schedule_content()
        
        if not message_content:
            log("❌ Не вдалося отримати важливе повідомлення")
            send_log_to_channel()
            return
        
        # Обчислюємо хеш ЛИШЕ важливого повідомлення
        current_hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest()
        last_hash_message = get_last_hash()
        
        log(f"🔑 Поточний хеш повідомлення: {current_hash_message}")
        log(f"🔑 Попередній хеш повідомлення: {last_hash_message}")
        
        # Порівнюємо лише важливе повідомлення
        if last_hash_message == current_hash_message:
            log("✅ Змін у важливому повідомленні немає. Завершення.")
            send_log_to_channel()
            return
        
        log("🔔 ВИЯВЛЕНІ ЗМІНИ У ВАЖЛИВОМУ ПОВІДОМЛЕННІ!")
        
        # Створюємо скріншот
        screenshot_path = take_screenshot()
        
        # Відправляємо в канал
        if send_to_channel(message_content, date_content, screenshot_path):
            save_hash(message_content, date_content)
            log("✅ Успішно! Оновлення відправлено")
        else:
            log("❌ Не вдалося відправити оновлення")
    
    except Exception as e:
        log(f"❌ Критична помилка: {e}")
    
    finally:
        # Завжди відправляємо лог наприкінці
        send_log_to_channel()

if __name__ == '__main__':
    main()
