import requests
from bs4 import BeautifulSoup
import os
import hashlib
import json
from datetime import datetime
import pytz
from playwright.sync_api import sync_playwright
import sys
from io import BytesIO
from PIL import Image

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
    return datetime.now(pytz.utc).astimezone(UKRAINE_TZ)

def log(message):
    print(message)
    ukraine_time = get_ukraine_time()
    log_messages.append(f"{ukraine_time.strftime('%H:%M:%S')} - {message}")

def take_screenshot_between_elements():
    try:
        log("📸 Створюю скріншот проміжку між елементами...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            page.goto(URL, wait_until='networkidle', timeout=30000)

            # Блок 'Дата оновлення інформації'
            date_element = page.locator("text=/Дата оновлення інформації/").first
            # ОСТАННЄ слово 'робіт'
            end_element = page.locator("text=/робіт/").last

            if date_element.count() == 0:
                log("❌ Не знайдено елемент 'Дата оновлення інформації'")
                browser.close()
                return None, None

            if end_element.count() == 0:
                log("⚠️ Не знайдено слово 'робіт', буде використано висоту всієї сторінки!")

            # Завантажуємо bounding_box для точок обрізки
            date_box = date_element.bounding_box()
            end_box = end_element.bounding_box() if end_element.count() > 0 else None

            if not date_box:
                log("❌ Не вдалося отримати координати 'Дата оновлення інформації'")
                browser.close()
                return None, None

            x = 0
            width = 1920
            start_y = date_box['y'] + date_box['height']

            full_screenshot = page.screenshot()
            browser.close()
            image = Image.open(BytesIO(full_screenshot))
            # Якщо слово 'робіт' знайдено
            if end_box:
                end_y = end_box['y'] + end_box['height'] + 5
                log(f"📐 Обрізка до слова 'робіт': y={start_y}-{end_y}")
            else:
                # Якщо не знайдено, захватити до кінця сторінки
                end_y = image.height
                log("📐 Обрізка на всю висоту сторінки (робіт не знайдено)")
            height = end_y - start_y
            if height <= 0:
                log("❌ Некоректна висота області для скріншота")
                return None, None
            cropped_image = image.crop((x, start_y, x + width, end_y))
            cropped_image.save('screenshot.png')
            screenshot_hash = hashlib.md5(cropped_image.tobytes()).hexdigest()
            log(f"✅ Скріншот створено. Хеш: {screenshot_hash}")
            return 'screenshot.png', screenshot_hash
    except Exception as e:
        log(f"❌ Помилка створення скріншоту: {e}")
        return None, None

# ... залишся весь інший код без змін
