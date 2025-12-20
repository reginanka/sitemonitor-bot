import os
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from log_utils import log_to_buffer, send_log_to_channel
from site_content import get_schedule_content, take_screenshot_between_elements
from telegram_handler import send_notification

API_BASE_URL = os.getenv("API_BASE_URL")
URL = os.environ.get('URL')
SUBSCRIBE = os.environ.get('SUBSCRIBE')

QUEUES = [(i, j) for i in range(1, 7) for j in range(1, 2 + 1)]

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CURRENT_FILE = DATA_DIR / "current.json"
PREVIOUS_FILE = DATA_DIR / "previous.json"
HASH_FILE = DATA_DIR / "last_hash.json"


def fetch_schedule(cherga_id: int, pidcherga_id: int) -> Tuple[List[Dict], bool]:
    """
    Тягне графік для однієї черги.
    Повертає (дані, is_error).
    """
    resp: Optional[requests.Response] = None
    try:
        params = {"cherga_id": cherga_id, "pidcherga_id": pidcherga_id}
        resp = requests.get(API_BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        text = resp.text.strip()
        if text.startswith("[") and text.endswith("]"):
            data = json.loads(text)
        else:
            if text.startswith("{"):
                text = f"[{text}]"
            data = json.loads(text)

        if isinstance(data, list):
            return data, False

        log_to_buffer(f"⚠️ Відповідь не список для {cherga_id}.{pidcherga_id}")
        return [], False

    except Exception as e:
        body = resp.text[:200] if resp is not None else ""
        log_to_buffer(
            f"❌ Помилка {cherga_id}.{pidcherga_id}: {e}. "
            f"Фрагмент відповіді: {body}"
        )
        return [], True


def fetch_all_schedules() -> Tuple[Dict[str, List[Dict]], Dict[str, bool]]:
    """Повертає (дані, словник помилок)."""
    all_schedules: Dict[str, List[Dict]] = {}
    has_error: Dict[str, bool] = {}

    log_to_buffer("📡 Завантажую графіки по всіх чергах...")
    for cherga_id, pidcherga_id in QUEUES:
        queue_key = f"{cherga_id}.{pidcherga_id}"
        schedule, is_error = fetch_schedule(cherga_id, pidcherga_id)
        all_schedules[queue_key] = schedule
        has_error[queue_key] = is_error

        error_note = " [помилка API]" if is_error else ""
        log_to_buffer(f" ✓ {queue_key}: {len(schedule)} записів{error_note}")

    return all_schedules, has_error


def save_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def calculate_hash(obj) -> str:
    json_str = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(json_str.encode("utf-8")).hexdigest()


def normalize_record(rec: Dict, cherga_id: int, pidcherga_id: int) -> Dict:
    """Нормалізація одного запису."""
    date = rec.get("date", "")
    span = rec.get("span", "")
    color = rec.get("color", "").strip().lower()

    return {
        "cherga": cherga_id,
        "pidcherga": pidcherga_id,
        "queue_key": f"{cherga_id}.{pidcherga_id}",
        "date": date,
        "span": span,
        "color": color,
    }


def build_state(
    raw_schedules: Dict[str, List[Dict]],
    has_error: Dict[str, bool],
) -> Tuple[
    Dict[str, List[Dict]], # norm_by_queue
    Dict[str, str], # main_hashes
    Dict[str, Dict[str, Dict[str, str]]] # span_hashes[queue][date][span]
]:
    """
    Будує нормалізований стан з хешами по інтервалах.
    ⭐ Порожні графіки отримують пустий хеш ""
    """
    norm_by_queue: Dict[str, List[Dict]] = {}
    main_hashes: Dict[str, str] = {}
    span_hashes: Dict[str, Dict[str, Dict[str, str]]] = {}

    for queue_key, schedule in raw_schedules.items():
        cherga_id, pidcherga_id = map(int, queue_key.split("."))
        
        # ⭐ ПОРОЖНІЙ ГРАФІК → пустий хеш
        if has_error.get(queue_key, False) or not schedule:
            norm_by_queue[queue_key] = []
            main_hashes[queue_key] = ""  # ⭐ ПУСТИЙ ХЕШ
            span_hashes[queue_key] = {}
            log_to_buffer(f"ℹ️ {queue_key}: порожній/помилка → хеш=''")
            continue

        norm_list: List[Dict] = []
        for rec in schedule:
            nrec = normalize_record(rec, cherga_id, pidcherga_id)
            norm_list.append(nrec)

        norm_list.sort(key=lambda r: (r["date"], r["span"]))
        norm_by_queue[queue_key] = norm_list

        # Головний хеш черги
        main_hash_data = [{"date": r["date"], "span": r["span"], "color": r["color"]} for r in norm_list]
        main_hashes[queue_key] = calculate_hash(main_hash_data)

        # Хеші по кожному інтервалу
        sh: Dict[str, Dict[str, str]] = {}
        for rec in norm_list:
            d = rec["date"]
            span = rec["span"]
            if d not in sh:
                sh[d] = {}
            sh[d][span] = calculate_hash({"color": rec["color"]})
        
        span_hashes[queue_key] = sh

    return norm_by_queue, main_hashes, span_hashes


def load_last_state():
    """Завантажує хеші з last_hash.json + дані з previous.json"""
    hash_data = load_json(HASH_FILE)
    prev_norm = load_json(PREVIOUS_FILE)
    
    return {
        "timestamp": hash_data.get("timestamp"),
        "main_hashes": hash_data.get("main_hashes", {}),
        "span_hashes": hash_data.get("span_hashes", {}),
        "norm_by_queue": prev_norm,
    }


def save_state(
    main_hashes: Dict[str, str],
    span_hashes: Dict[str, Dict[str, Dict[str, str]]],
    timestamp: str
) -> None:
    """Зберігає тільки хеші в last_hash.json"""
    data = {
        "timestamp": timestamp,
        "main_hashes": main_hashes,
        "span_hashes": span_hashes,
    }
    save_json(data, HASH_FILE)


def parse_span(span: str) -> Tuple[str, str]:
    """0000-0030 або 00:00-00:30 -> (00:00, 00:30)"""
    if not span or "-" not in span:
        return ("", "")
    start, end = span.split("-")
    if ":" in start:
        return start, end
    return f"{start[:2]}:{start[2:]}", f"{end[:2]}:{end[2:]}"


def group_spans(spans_changes: List[Dict]) -> List[Dict]:
    """Групує сусідні інтервали з однаковим типом зміни."""
    result: List[Dict] = []
    current: Optional[Dict] = None

    for item in sorted(spans_changes, key=lambda x: x["span"]):
        start_time, end_time = parse_span(item["span"])

        if not current:
            current = {
                "start": start_time,
                "end": end_time,
                "change": item["change"],
            }
        else:
            if current["change"] == item["change"] and current["end"] == start_time:
                current["end"] = end_time
            else:
                result.append(current)
                current = {
                    "start": start_time,
                    "end": end_time,
                    "change": item["change"],
                }

    if current:
        result.append(current)

    return result


def build_diff(
    norm_by_queue: Dict[str, List[Dict]],
    main_hashes: Dict[str, str],
    span_hashes: Dict[str, Dict[str, Dict[str, str]]],
    last_state: Dict,
) -> Dict:
    """
    ⭐ Логіка:
    1. None → ігнор (ініціалізація)
    2. "" → "" → ігнор (порожній)
    3. "" → дані → НОВИЙ ГРАФІК!
    4. дані → дані+зміни → ОНОВЛЕННЯ!
    """
    last_main = last_state.get("main_hashes", {})
    last_span = last_state.get("span_hashes", {})
    last_norm = last_state.get("norm_by_queue", {})

    diff = {
        "queues": [],
        "per_queue": {},
        "new_dates": [],
        "from_empty_queues": [],  # ⭐ З порожнього → повний
    }

    for queue_key, cur_main_hash in main_hashes.items():
        cur_records = norm_by_queue.get(queue_key, [])
        old_main_hash = last_main.get(queue_key)
        
        # ⭐ КЕЙС 1: Ініціалізація (немає історії)
        if old_main_hash is None:
            log_to_buffer(f"ℹ️ Ініціалізація {queue_key} ({len(cur_records)} записів)")
            continue
        
        # ⭐ КЕЙС 2: Зараз порожній
        if not cur_records:
            log_to_buffer(f"ℹ️ Порожній {queue_key}")
            continue
        
        # ⭐ КЕЙС 3: БУВ ПОРОЖНІЙ → ЗАРАЗ Є → НОВИЙ ГРАФІК!
        if old_main_hash == "" and cur_main_hash != "":
            log_to_buffer(f"🎉 {queue_key}: З'ЯВИВСЯ ГРАФІК з нуля!")
            diff["from_empty_queues"].append(queue_key)
            diff["queues"].append(queue_key)
            new_dates = list(span_hashes.get(queue_key, {}).keys())
            diff["new_dates"].extend(new_dates)
            diff["per_queue"][queue_key] = {
                "new_dates": new_dates,
                "changed_dates": {},
            }
            continue
        
        # ⭐ КЕЙС 4: Зміна хешу → детальний аналіз
        if old_main_hash != cur_main_hash:
            log_to_buffer(f"🔍 Зміни в {queue_key}")
            
            cur_sh = span_hashes.get(queue_key, {})
            old_sh = last_span.get(queue_key, {})
            
            new_dates = sorted(d for d in cur_sh.keys() if d not in old_sh)
            changed_dates = {}
            cur_items = norm_by_queue.get(queue_key, [])
            old_items_list = last_norm.get(queue_key, [])

            for d in cur_sh.keys():
                if d in new_dates:
                    continue
                
                cur_spans = cur_sh.get(d, {})
                old_spans = old_sh.get(d, {})
                changes_for_date = []
                
                for span, cur_span_hash in cur_spans.items():
                    old_span_hash = old_spans.get(span)
                    if old_span_hash == cur_span_hash:
                        continue
                    
                    new_rec = next((r for r in cur_items if r["date"] == d and r["span"] == span), None)
                    old_rec = next((r for r in old_items_list if r["date"] == d and r["span"] == span), None)
                    
                    if new_rec and old_rec and new_rec["color"] != old_rec["color"]:
                        change = "added" if new_rec["color"] == "red" else "removed"
                        changes_for_date.append({"span": span, "change": change})

                if changes_for_date:
                    changed_dates[d] = group_spans(changes_for_date)

            if new_dates or changed_dates:
                diff["queues"].append(queue_key)
                diff["per_queue"][queue_key] = {
                    "new_dates": new_dates,
                    "changed_dates": changed_dates,
                }
                diff["new_dates"].extend(new_dates)

    return diff


def build_changes_notification(
    diff: Dict,
    url: str,
    subscribe: str,
    update_str: str
) -> str:
    """Повідомлення про зміни в ІСНУЮЧИХ датах"""
    queues_with_changes = []
    for q in sorted(diff["queues"]):
        info = diff["per_queue"].get(q, {})
        if info.get("changed_dates"):
            queues_with_changes.append(q)
    
    if not queues_with_changes:
        return ""
    
    parts = []
    parts.append(f"Для черг {', '.join(queues_with_changes)} 🔔 ОНОВЛЕННЯ ГРАФІКА ВІДКЛЮЧЕНЬ!")
    parts.append("⬇️⬇️⬇️
")
    
    # Дата оновлення
    update_date_str = ""
    if update_str:
        import re
        match = re.search(r'(d{2}:d{2})s+(d{2}.d{2}).d{4}', update_str)
        if match:
            update_date_str = f"🕐 {match.group(1)} {match.group(2)}"
    
    dates_with_changes = set()
    for q in queues_with_changes:
        info = diff["per_queue"].get(q, {})
        for d in info.get("changed_dates", {}).keys():
            dates_with_changes.add(d)
    
    for date in sorted(dates_with_changes):
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = dt.strftime("%d.%m.%Y")
        except ValueError:
            formatted_date = date
        
        parts.append(f"🗓 {formatted_date}
")
        
        for queue_key in sorted(queues_with_changes, key=lambda x: tuple(map(int, x.split(".")))):
            queue_info = diff["per_queue"].get(queue_key, {})
            
            if date not in queue_info.get("changed_dates", {}):
                continue
            
            parts.append(f"▶️ Черга {queue_key}:")
            
            ranges = queue_info["changed_dates"][date]
            for r in ranges:
                start = r['start'].lstrip('0') or '0:00'
                end = r['end'].lstrip('0') or '0:00'
                if start.startswith(':'):
                    start = '0' + start
                if end.startswith(':'):
                    end = '0' + end
                if r["change"] == "added":
                    action = "🪫 додали відключення"
                    parts.append(f"{start}-{end} {action}")
                else:
                    action = "🔋 скасували відключення"
                    parts.append(f"<s>{start}-{end}</s> {action}")
            
            parts.append("")
        
        parts.append("======
")
    
    parts.append(
        f'<a href="{url}">🔗 Переглянути графік</a> | '
        f'<a href="{subscribe}">⚡️ ПІДПИСАТИСЯ</a>'
    )
    if update_date_str:
        parts.append(update_date_str)
    
    return "
".join(parts)


def build_new_schedule_notification(
    diff: Dict,
    norm_by_queue: Dict[str, List[Dict]],
    url: str,
    subscribe: str,
    update_str: str
) -> str:
    """Компактне повідомлення про НОВИЙ графік"""
    queues_with_new_dates = []
    for q in sorted(diff["queues"]):
        info = diff["per_queue"].get(q, {})
        if info.get("new_dates"):
            queues_with_new_dates.append(q)

    if not queues_with_new_dates:
        return ""

    parts = []
    parts.append("🔔 Додано новий графік на завтра!")
    parts.append("⬇️⬇️⬇️
")

    update_date_str = ""
    if update_str:
        import re
        match = re.search(r'(d{2}:d{2})s+(d{2}.d{2}).d{4}', update_str)
        if match:
            update_date_str = f"🕐 {match.group(1)} {match.group(2)}"

    for date in sorted(set(diff.get("new_dates", []))):
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = dt.strftime("%d.%m.%Y")
        except ValueError:
            formatted_date = date

        parts.append(f"🗓 {formatted_date}
")

        for queue_key in sorted(
            queues_with_new_dates, key=lambda x: tuple(map(int, x.split(".")))
        ):
            records = norm_by_queue.get(queue_key, [])
            outages = [
                r for r in records
                if r["date"] == date and r["color"] == "red"
            ]

            if outages:
                grouped = group_spans(
                    [{"span": o["span"], "change": "added"} for o in outages]
                )

                time_ranges = []
                for g in grouped:
                    start = g["start"].lstrip("0") or "0:00"
                    end = g["end"].lstrip("0") or "0:00"
                    if start.startswith(":"):
                        start = "0" + start
                    if end.startswith(":"):
                        end = "0" + end
                    time_ranges.append(f"{start}-{end}")

                times_str = ", ".join(time_ranges)
                parts.append(f"Черга {queue_key}: 
🪫{times_str}")
                parts.append("")

        parts.append("")

    parts.append(
        f'<a href="{url}">🔗 Переглянути графік</a> | '
        f'<a href="{subscribe}">⚡️ ПІДПИСАТИСЯ</a>'
    )
    if update_date_str:
        parts.append(update_date_str)

    return "
".join(parts)


def send_notification_safe(message: str, img_path=None) -> bool:
    """Надсилає повідомлення з перевіркою лімітів Telegram"""
    CAPTION_LIMIT = 1024
    TEXT_LIMIT = 4096
    
    msg_len = len(message)
    log_to_buffer(f"📝 Довжина повідомлення: {msg_len} символів")
    
    if img_path and msg_len > CAPTION_LIMIT:
        log_to_buffer(f"⚠️ Текст {msg_len} > {CAPTION_LIMIT}, надсилаю фото+текст окремо")
        send_notification("📸", img_path)
        if msg_len > TEXT_LIMIT:
            message = message[:TEXT_LIMIT-100] + "

... (текст скорочено)"
        return send_notification(message, None)
    
    if not img_path and msg_len > TEXT_LIMIT:
        log_to_buffer(f"⚠️ Текст {msg_len} > {TEXT_LIMIT}, обрізаю")
        message = message[:TEXT_LIMIT-100] + "

... (текст скорочено)"
    
    return send_notification(message, img_path)


def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_to_buffer("=" * 60)
    log_to_buffer(f"🚀 СТАРТ [{timestamp}]")
    log_to_buffer("=" * 60)

    try:
        # ⭐ Ініціалізація порожніх файлів
        if not HASH_FILE.exists():
            save_state({}, {}, timestamp)
            log_to_buffer("🆕 Створено порожній last_hash.json")
        if not PREVIOUS_FILE.exists():
            save_json({}, PREVIOUS_FILE)
            log_to_buffer("🆕 Створено порожній previous.json")

        # 1. Завантажити графіки
        current_schedules, has_error = fetch_all_schedules()
        if not any(not has_error[q] and current_schedules[q] for q in current_schedules):
            log_to_buffer("❌ Не вдалось завантажити жоден графік")
            return

        # 2. Побудувати поточний стан
        norm_by_queue, current_main_hashes, current_span_hashes = build_state(
            current_schedules, has_error
        )
        log_to_buffer(f"🔐 Хеші для {len(current_main_hashes)} черг")

        # 3. Зберегти поточні дані
        if CURRENT_FILE.exists():
            shutil.copy(CURRENT_FILE, PREVIOUS_FILE)
        save_json(norm_by_queue, CURRENT_FILE)
        log_to_buffer("💾 Дані збережено")

        # 4. Завантажити попередній стан
        last_state = load_last_state()

        # 5. Побудувати diff
        diff = build_diff(norm_by_queue, current_main_hashes, current_span_hashes, last_state)

        # ⭐ 6. Чітка перевірка реальних змін
        real_changes = (diff["queues"] or 
                       diff.get("from_empty_queues", []))
        
        if not real_changes:
            log_to_buffer("✅ Все стабільно")
            save_state(current_main_hashes, current_span_hashes, timestamp)
            return

        log_to_buffer(f"🔔 Зміни: {len(diff['queues'])} черг, "
                     f"з нуля: {len(diff.get('from_empty_queues', []))}")

        # 7. Отримати контент сайту
        _, date_content = get_schedule_content()
        screenshot_path, _ = take_screenshot_between_elements()
        img_path = Path(screenshot_path) if screenshot_path else None

        # ⭐ 8. Пріоритет повідомлень
        msg = ""
        if diff.get("from_empty_queues"):
            log_to_buffer("🚀 'Новий графік!' (з порожнього)")
            msg = build_new_schedule_notification(
                diff, norm_by_queue, URL, SUBSCRIBE, date_content or ""
            )
        elif diff.get("new_dates"):
            log_to_buffer("🆕 'Новий графік на завтра!'")
            msg = build_new_schedule_notification(
                diff, norm_by_queue, URL, SUBSCRIBE, date_content or ""
            )
        else:
            log_to_buffer("🔄 'Оновлення графіку!'")
            msg = build_changes_notification(
                diff, URL, SUBSCRIBE, date_content or ""
            )

        if msg:
            log_to_buffer("📤 Надсилаю повідомлення + фото")
            send_notification_safe(msg, img_path)
        else:
            log_to_buffer("⚠️ Повідомлення порожнє")

        # 9. Зберегти стан
        save_state(current_main_hashes, current_span_hashes, timestamp)
        log_to_buffer("✅ Кінець")

    except Exception as e:
        log_to_buffer(f"💥 Критична помилка: {e}")
        import traceback
        log_to_buffer(t
