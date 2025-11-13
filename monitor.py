import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright
from PIL import Image
import io
import sys

def exception_hook(exctype, value, traceback):
    print(f"❌ Uncaught exception: {value}")
    import traceback as tb
    tb.print_exception(exctype, value, traceback)
    sys.exit(1)

sys.excepthook = exception_hook

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID')
TELEGRAM_LOG_CHANNEL_ID = os.environ.get('TELEGRAM_LOG_CHANNEL_ID')
URL = 'https://www.ztoe.com.ua/unhooking-search.php'

# Часовий пояс України
UKRAINE_TZ = pytz.timezone('Europe/Kyiv')

# Змінна для збору логів
log_messages = []

def get_ukraine_time():
    """Повертає поточний час в українському часовому поясі"""
    return datetime.now(pytz.utc).astimezone(UKRAINE_TZ)

def log(message):
    """Додає повідомлення до логу та виводить у консоль"""
    print(message)
    ukraine_time = get_ukraine_time()
    log_messages.append(f"{ukraine_time.strftime('%H:%M:%S')} - {message}")

def send_log_to_channel():
    """Відправляє зібрані логи у лог-канал"""
    if not TELEGRAM_LOG_CHANNEL_ID or not log_messages:
        return
    
    try:
        ukraine_time = get_ukraine_time()
        log_text = "📊 <b>ЛОГ ВИКОНАННЯ СКРИПТА</b>\n\n"
        log_text += "<pre>"
        log_text += "\n".join(log_messages)
        log_text += "</pre>"
        log_text += f"\n\n⏰ Завершено: {get_ukraine_time().strftime('%d.%m.%Y %H:%M:%S')} (Київський час)"
        
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
    """Отримує контент розкладу з використанням Playwright"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)
            
            page_content = page.content()
            browser.close()
            
        soup = BeautifulSoup(page_content, 'html.parser')
        
        # Замінюємо <br> на перенос рядка
        for br in soup.find_all("br"):
            br.replace_with("\n")
        
        # Шукаємо повідомлення
        message_div = soup.find('div', class_='message')
        if not message_div:
            log("⚠️ Не знайдено div з класом 'message'")
            return None, None
        
        # Отримуємо текст повідомлення
        message_text = message_div.get_text(separator='\n', strip=True)
        
        # Знаходимо дату оновлення
        date_text = soup.find(string=lambda text: text and 'Дата оновлення інформації' in text)
        date_content = date_text.strip() if date_text else "Дата не знайдена"
        
        log(f"✅ Отримано контент ({len(message_text)} символів)")
        return message_text, date_content
        
    except Exception as e:
        log(f"❌ Помилка отримання контенту: {e}")
        return None, None

def take_table_screenshot():
    """Робить скріншот обох графіків (сьогодні + завтра)"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)
            
            # Знаходимо всі таблиці
            tables = page.locator('table')
            table_count = tables.count()
            log(f"📊 Знайдено таблиць: {table_count}")
            
            if table_count == 0:
                browser.close()
                return None
            
            # Визначаємо скільки таблиць з графіками
            # Остання таблиця - це роз'яснення (вона маленька)
            graph_count = table_count - 1  # всі таблиці крім останньої
            
            # Перевіряємо розмір останньої таблиці для підтвердження
            if table_count >= 2:
                last_table = tables.nth(table_count - 1)
                last_box = last_table.bounding_box()
                
                # Якщо остання таблиця низька (менше 200px) - це точно роз'яснення
                if last_box and last_box['height'] < 200:
                    log(f"📋 Таблиця роз'яснень виявлена")
                else:
                    # Якщо остання таблиця велика - це теж графік
                    graph_count = table_count
                    log(f"📊 Всі таблиці - графіки")
            
            log(f"📊 Графіків для захоплення: {graph_count}")
            
            # Робимо скріншот графіків
            screenshots = []
            for i in range(graph_count):
                screenshot_bytes = tables.nth(i).screenshot()
                screenshots.append(Image.open(io.BytesIO(screenshot_bytes)))
                log(f"✅ Захоплено графік {i+1}")
            
            browser.close()
            
            # Якщо один графік - повертаємо як є
            if len(screenshots) == 1:
                img_bytes = io.BytesIO()
                screenshots[0].save(img_bytes, format='PNG')
                return img_bytes.getvalue()
            
            # Якщо два графіки (сьогодні + завтра) - об'єднуємо вертикально
            total_width = max(img.width for img in screenshots)
            total_height = sum(img.height for img in screenshots) + (20 * (len(screenshots) - 1))
            
            combined = Image.new('RGB', (total_width, total_height), 'white')
            
            y_offset = 0
            for img in screenshots:
                combined.paste(img, (0, y_offset))
                y_offset += img.height + 20  # 20px відступ між графіками
            
            img_bytes = io.BytesIO()
            combined.save(img_bytes, format='PNG')
            return img_bytes.getvalue()
            
    except Exception as e:
        log(f"❌ Помилка скріншота таблиць: {e}")
        return None

def crop_date_area(screenshot_bytes):
    """Обрізає область з датою оновлення зі скріншота"""
    try:
        img = Image.open(io.BytesIO(screenshot_bytes))
        width, height = img.size
        
        # Обрізаємо нижні 100 пікселів де знаходиться дата оновлення
        cropped = img.crop((0, 0, width, height - 100))
        
        img_bytes = io.BytesIO()
        cropped.save(img_bytes, format='PNG')
        return img_bytes.getvalue()
    except Exception as e:
        log(f"❌ Помилка обрізання: {e}")
        return screenshot_bytes

def get_table_hash(screenshot_bytes):
    """Обчислює хеш зображення таблиці"""
    if not screenshot_bytes:
        return None
    return hashlib.md5(screenshot_bytes).hexdigest()

def take_screenshot():
    """Робить повний скріншот сторінки для відправки"""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)
            
            screenshot_path = 'screenshot.png'
            page.screenshot(path=screenshot_path, full_page=True)
            
            browser.close()
            log(f"✅ Скріншот збережено: {screenshot_path}")
            return screenshot_path
            
    except Exception as e:
        log(f"❌ Помилка створення скріншота: {e}")
        return None

def send_to_channel(message_content, date_content, screenshot_path):
    """Відправляє повідомлення та скріншот у Telegram канал"""
    try:
        ukraine_time = get_ukraine_time()
        formatted_message = (
            f"🔔 <b>ОНОВЛЕННЯ ГРАФІКУ ВІДКЛЮЧЕНЬ</b>\n\n"
            f"{message_content}\n\n"
            f"📅 {date_content}\n"
            f"⏰ Виявлено: {ukraine_time.strftime('%d.%m.%Y %H:%M:%S')} (Київський час)"
        )
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        
        with open(screenshot_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': TELEGRAM_CHANNEL_ID,
                'caption': formatted_message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, data=data, files=files, timeout=30)
            
            if response.status_code == 200:
                log("✅ Повідомлення успішно відправлено у канал")
                return True
            else:
                log(f"❌ Помилка відправки: {response.text}")
                return False
                
    except Exception as e:
        log(f"❌ Помилка відправки у Telegram: {e}")
        return False

def get_last_hashes():
    """Завантажує збережені хеші"""
    try:
        with open('last_hash.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {
                'hash_message': data.get('hash_message'),
                'hash_table': data.get('hash_table')
            }
    except:
        return {'hash_message': None, 'hash_table': None}

def save_hashes(message_content, date_content, table_hash):
    """Зберігає обидва хеші"""
    hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest()
    
    with open('last_hash.json', 'w', encoding='utf-8') as f:
        json.dump({
            'hash_message': hash_message,
            'hash_table': table_hash,
            'content_message': message_content,
            'content_date': date_content,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

def main():
    log("=" * 50)
    log("🔍 ЗАПУСК МОНІТОРИНГУ РОЗКЛАДУ")
    log("=" * 50)
    
    try:
        # Отримуємо текст
        message_content, date_content = get_schedule_content()
        if not message_content:
            log("⚠️ Не вдалося отримати контент")
            return
        
        # Отримуємо скріншот таблиці
        table_screenshot = take_table_screenshot()
        if not table_screenshot:
            log("⚠️ Не вдалося отримати скріншот таблиці")
            return
        
        # Обрізаємо дату зі скріншота
        table_screenshot_no_date = crop_date_area(table_screenshot)
        
        # Обчислюємо хеші
        current_hash_message = hashlib.md5(message_content.encode('utf-8')).hexdigest()
        current_hash_table = get_table_hash(table_screenshot_no_date)
        
        # Завантажуємо попередні хеші
        last_hashes = get_last_hashes()
        
        log(f"📊 Хеш повідомлення: {current_hash_message}")
        log(f"📊 Хеш таблиці: {current_hash_table}")
        
        # Перевіряємо обидві зміни
        message_changed = last_hashes['hash_message'] != current_hash_message
        table_changed = last_hashes['hash_table'] != current_hash_table
        
        if not message_changed and not table_changed:
            log("✅ Зміни відсутні. Скріншот не потрібен.")
            return
        
        if message_changed:
            log("🔔 Виявлено зміни у тексті повідомлення!")
        if table_changed:
            log("🔔 Виявлено зміни у таблиці/графіку!")
        
        # Робимо повний скріншот для відправки
        screenshot_path = take_screenshot()
        
        if screenshot_path and send_to_channel(message_content, date_content, screenshot_path):
            # Зберігаємо нові хеші
            save_hashes(message_content, date_content, current_hash_table)
            log("✅ Зміни успішно відправлені!")
        else:
            log("❌ Помилка відправки")
            
    except Exception as e:
        log(f"❌ Помилка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        send_log_to_channel()

if __name__ == "__main__":
    main()
