import logging
import json
import os
from collections import defaultdict, Counter
from datetime import datetime, timedelta, time
import io
import matplotlib.pyplot as plt
import numpy as np
import random
import asyncio

from telegram import Update, ReplyKeyboardMarkup, InputFile, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, PollAnswerHandler
)

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = -1003072750672
ADMIN_ID = 284884293
DATA_FILE = "bot_data.json"
BACKUP_FILE = "bot_data_backup.json"
POLL_DURATION = 600  # 10 минут
COOLDOWN = timedelta(minutes=15)

# Константы для системы контента дня
CONTENT_FIRST_REQUEST_TIME = time(hour=8, minute=30)  # 08:30
CONTENT_RETRY_REQUEST_TIME = time(hour=9, minute=30)  # 09:30 
CONTENT_SEND_TIME = time(hour=10, minute=0)           # 10:00

# ... остальной код без изменений до хранилища ...

# --- Хранилище ---
active_poll_id = None
active_poll_options = []
poll_votes = {}  # Текущие голоса в активном опросе (только последние)
stats_yes = defaultdict(int)
stats_no = defaultdict(int)
stats_stickers = defaultdict(int)
stats_photos = defaultdict(int)
usernames = {}
sessions = []  # Все сессии голосований (только окончательные голоса)
last_poll_time = None
consecutive_yes = defaultdict(int)
consecutive_no = defaultdict(int)
consecutive_button_press = defaultdict(int)
last_button_press_time = defaultdict(lambda: datetime.min)
achievements_unlocked = defaultdict(set)
successful_polls = []  # Успешные перекуры (опросы с хотя бы одним голосом)
user_levels = defaultdict(dict)  # {user_id: {"smoker_level": int, "worker_level": int}}

# Система контента дня
pending_daily_content = None

# --- Вспомогательные функции для системы контента ---

def is_workday():
    """Проверка рабочих дней"""
    today = datetime.now().weekday()
    return today < 5  # Пн-Пт (0-4)

def select_random_user(used_users=None):
    """Выбор случайного активного участника (за последние 7 дней)"""
    if used_users is None:
        used_users = set()
    
    # Берем пользователей, которые голосовали за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    active_users = list(set(
        uid for t, uid, _ in sessions 
        if t >= week_ago and uid != ADMIN_ID  # Исключаем админа
    ))
    
    # Исключаем уже использованных
    available_users = [uid for uid in active_users if uid not in used_users]
    
    if not available_users:
        return None
    
    return random.choice(available_users)

async def send_content_request(context: ContextTypes.DEFAULT_TYPE, user_id: int, attempt_type: str, used_users=None):
    """Отправка запроса контента пользователю"""
    global pending_daily_content
    
    if used_users is None:
        used_users = set()
    
    username = usernames.get(user_id, "Участник")
    
    keyboard = [
        ["Анекдот дня 😄", "Мем дня 🎭"],
        ["Пропустить этот раз 🔄"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    try:
        if attempt_type == "первый":
            message_text = (f"🎉 Доброе утро, {username}! Ты выбран для утреннего контента!\n\n"
                          f"Выбери тип контента (будет анонимно отправлен в 10:00):")
        else:  # повторный или мгновенный переход
            message_text = (f"🎉 {username}, твоя очередь!\n\n"
                          f"Выбери тип контента (будет анонимно отправлен в 10:00):")
        
        await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=reply_markup
        )
        
        pending_daily_content = {
            "request_time": datetime.now().isoformat(),
            "type": None,
            "content": None,
            "selected_user_id": user_id,
            "attempt_type": attempt_type,
            "used_users": list(used_users)  # Сохраняем использованных пользователей
        }
        
        logger.info(f"Запрос контента отправлен пользователю {user_id} (used: {len(used_users)})")
        save_data()
        
    except Exception as e:
        logger.warning(f"Не удалось отправить запрос пользователю {user_id}: {e}")
        # При ошибке сразу переходим к следующему
        used_users.add(user_id)
        await instant_retry(context, used_users, f"ошибка отправки пользователю {user_id}")

async def instant_retry(context: ContextTypes.DEFAULT_TYPE, used_users=None, reason=""):
    """Мгновенный повторный запрос другому пользователю"""
    if used_users is None:
        used_users = set()
    
    next_user_id = select_random_user(used_users)
    if not next_user_id:
        logger.info("Нет доступных пользователей для мгновенного повторного запроса")
        return
    
    await send_content_request(context, next_user_id, "мгновенный", used_users)

# Функции для системы контента дня
async def request_daily_content_first(context: ContextTypes.DEFAULT_TYPE):
    """Первый запрос контента в 08:30"""
    global pending_daily_content
    
    if not is_workday():
        logger.info("Сегодня выходной - пропускаем запрос контента")
        return
    
    selected_user_id = select_random_user()
    if not selected_user_id:
        logger.info("Нет активных пользователей для запроса контента")
        return
    
    await send_content_request(context, selected_user_id, "первый")

async def request_daily_content_retry(context: ContextTypes.DEFAULT_TYPE):
    """Повторный запрос контента в 09:30"""
    global pending_daily_content
    
    if not is_workday():
        return
    
    # Если контент уже получен, пропускаем
    if pending_daily_content and pending_daily_content.get("content"):
        logger.info("Контент уже получен - пропускаем повторный запрос")
        return
    
    # Если есть pending_daily_content но нет контента - значит пользователь не ответил
    if pending_daily_content and not pending_daily_content.get("content"):
        current_used_users = set(pending_daily_content.get("used_users", []))
        current_user_id = pending_daily_content["selected_user_id"]
        current_used_users.add(current_user_id)
        
        logger.info(f"Пользователь {current_user_id} не ответил - повторный запрос в 09:30")
        await instant_retry(context, current_used_users, f"пользователь {current_user_id} не ответил к 09:30")

async def send_daily_content(context: ContextTypes.DEFAULT_TYPE):
    """Отправка контента в группу в 10:00"""
    global pending_daily_content
    
    if not pending_daily_content or not pending_daily_content.get("content"):
        logger.info("Контент не получен - пропускаем отправку")
        return
    
    try:
        content_type = pending_daily_content["type"]
        content = pending_daily_content["content"]
        
        if content_type == "joke":
            message = f"😄 Анекдот дня (от анонимного героя):\n\n{content}"
        else:  # meme
            message = f"🎭 Мем дня (от анонимного героя):\n\n{content}"
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message
        )
        
        logger.info("Контент дня отправлен в группу от анонимного пользователя")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке контента в группу: {e}")
    
    # Очищаем после отправки
    pending_daily_content = None
    save_data()

# Обработчики для системы контента
async def handle_user_content_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа контента"""
    global pending_daily_content
    
    user_id = update.effective_user.id
    
    if not pending_daily_content or pending_daily_content["selected_user_id"] != user_id:
        return
    
    text = update.message.text
    
    if text == "Анекдот дня 😄":
        pending_daily_content["type"] = "joke"
        await update.message.reply_text(
            "📝 Напиши свой анекдот (будет анонимно отправлен в группу в 10:00):",
            reply_markup=ReplyKeyboardRemove()
        )
        save_data()
        
    elif text == "Мем дня 🎭":
        pending_daily_content["type"] = "meme" 
        await update.message.reply_text(
            "📝 Напиши текст мема (будет анонимно отправлен в группу в 10:00):",
            reply_markup=ReplyKeyboardRemove()
        )
        save_data()
        
    elif text == "Пропустить этот раз 🔄":
        # МГНОВЕННЫЙ ПЕРЕХОД К СЛЕДУЮЩЕМУ
        current_used_users = set(pending_daily_content.get("used_users", []))
        current_used_users.add(user_id)  # Добавляем текущего в использованных
        
        await update.message.reply_text(
            "✅ Хорошо, ищем следующего героя...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        logger.info(f"Пользователь {user_id} пропустил - мгновенный переход")
        
        # Немного задержки для UX
        await asyncio.sleep(1)
        
        # Запускаем мгновенный повторный запрос
        await instant_retry(context, current_used_users, f"пользователь {user_id} пропустил")

async def handle_user_content_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста контента от пользователя"""
    global pending_daily_content
    
    user_id = update.effective_user.id
    
    if (not pending_daily_content or 
        pending_daily_content["selected_user_id"] != user_id or
        not pending_daily_content["type"]):
        return
    
    content_text = update.message.text
    
    if len(content_text.strip()) < 5:
        await update.message.reply_text("❌ Слишком короткий текст. Минимум 5 символов.")
        return
    
    pending_daily_content["content"] = content_text
    
    # Добавляем пользователя в использованных (он выполнил свою миссию)
    current_used_users = set(pending_daily_content.get("used_users", []))
    current_used_users.add(user_id)
    pending_daily_content["used_users"] = list(current_used_users)
    
    # Подтверждаем получение
    content_type_ru = "анекдот" if pending_daily_content["type"] == "joke" else "мем"
    await update.message.reply_text(
        f"✅ {content_type_ru.capitalize()} сохранен! Он будет анонимно отправлен в группу в 10:00\n\n"
        f"📋 Твой контент:\n{content_text}"
    )
    
    logger.info(f"Контент дня получен от пользователя {user_id}")
    save_data()

# Команда для тестирования системы контента
async def test_content_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Тестовая команда для запуска системы контента"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ У тебя нет прав для этой команды.")
        return
    
    logger.info("🔧 Ручной запуск системы контента через команду /test_content")
    await update.message.reply_text("🔧 Запускаю систему контента вручную...")
    await request_daily_content_first(context)
    await update.message.reply_text("✅ Запрос контента отправлен случайному пользователю")

# Планировщик для системы контента
def schedule_content_system(application):
    """Запланировать систему контента дня"""
    job_queue = application.job_queue
    
    if job_queue is None:
        logger.error("❌ Job queue недоступна для системы контента!")
        return
    
    # Первый запрос в 08:30 (Пн-Пт)
    job_queue.run_daily(
        request_daily_content_first,
        time=CONTENT_FIRST_REQUEST_TIME,
        days=(0, 1, 2, 3, 4),
        name="content_first_request"
    )
    
    # Повторный запрос в 09:30 (Пн-Пт)
    job_queue.run_daily(
        request_daily_content_retry,
        time=CONTENT_RETRY_REQUEST_TIME, 
        days=(0, 1, 2, 3, 4),
        name="content_retry_request"
    )
    
    # Отправка в группу в 10:00 (Пн-Пт)
    job_queue.run_daily(
        send_daily_content,
        time=CONTENT_SEND_TIME,
        days=(0, 1, 2, 3, 4),
        name="content_send"
    )
    
    logger.info("✅ Система контента дня настроена: 08:30 → 09:30 → 10:00 (Пн-Пт)")

# Обновляем функцию сохранения данных
def save_data():
    create_backup()
    data = {
        "stats_yes": dict(stats_yes),
        "stats_no": dict(stats_no),
        "stats_stickers": dict(stats_stickers),
        "stats_photos": dict(stats_photos),
        "usernames": usernames,
        "sessions": [(t.isoformat(), uid, ans) for t, uid, ans in sessions],
        "consecutive_yes": dict(consecutive_yes),
        "consecutive_no": dict(consecutive_no),
        "consecutive_button_press": dict(consecutive_button_press),
        "last_button_press_time": {str(k): v.isoformat() for k, v in last_button_press_time.items()},
        "achievements_unlocked": {str(uid): list(achs) for uid, achs in achievements_unlocked.items()},
        "successful_polls": [t.isoformat() for t in successful_polls],
        "user_levels": {str(uid): levels for uid, levels in user_levels.items()},
        "pending_daily_content": pending_daily_content,  # Добавляем сохранение состояния контента
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Данные успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

# Обновляем функцию загрузки данных
def load_data():
    global stats_yes, stats_no, stats_stickers, stats_photos
    global usernames, sessions, consecutive_yes, consecutive_no, consecutive_button_press
    global last_button_press_time, achievements_unlocked, successful_polls, user_levels
    global pending_daily_content
    
    if not os.path.exists(DATA_FILE):
        logger.info("Файл данных не найден, начинаем с чистого листа")
        return
    
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        stats_yes.update(data.get("stats_yes", {}))
        stats_no.update(data.get("stats_no", {}))
        stats_stickers.update(data.get("stats_stickers", {}))
        stats_photos.update(data.get("stats_photos", {}))
        usernames.update(data.get("usernames", {}))
        sessions.extend([(datetime.fromisoformat(t), uid, ans) for t, uid, ans in data.get("sessions", [])])
        consecutive_yes.update(data.get("consecutive_yes", {}))
        consecutive_no.update(data.get("consecutive_no", {}))
        consecutive_button_press.update(data.get("consecutive_button_press", {}))
        successful_polls.extend([datetime.fromisoformat(t) for t in data.get("successful_polls", [])])
        user_levels.update({int(uid): levels for uid, levels in data.get("user_levels", {}).items()})
        
        # Загружаем состояние системы контента
        pending_daily_content_data = data.get("pending_daily_content")
        if pending_daily_content_data:
            # Проверяем, не устарели ли данные (больше 24 часов)
            request_time = datetime.fromisoformat(pending_daily_content_data["request_time"])
            if datetime.now() - request_time < timedelta(hours=24):
                pending_daily_content = pending_daily_content_data
                logger.info("Состояние системы контента загружено")
        
        last_button_press_time_data = data.get("last_button_press_time", {})
        for k, v in last_button_press_time_data.items():
            try:
                last_button_press_time[int(k)] = datetime.fromisoformat(v)
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка при загрузке времени для пользователя {k}: {e}")
        
        for uid, achs in data.get("achievements_unlocked", {}).items():
            try:
                achievements_unlocked[int(uid)].update(achs)
            except (ValueError, TypeError) as e:
                logger.warning(f"Ошибка при загрузке ачивок для пользователя {uid}: {e}")
        
        logger.info("Данные успешно загружены")
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка формата JSON: {e}")
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")

# Обновляем команду помощи
async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = [
        ("/start", "Начать работу с ботом"),
        ("/stats", "Общая статистика перекуров"),
        ("/stats_detailed", "Детальная статистика с графиками"),
        ("/me", "Твоя персональная статистика с графиками"),
        ("/top", "Топ курильщиков"),
        ("/workers_top", "Топ работяг"),
        ("/help", "Показать все команды"),
        ("/reset", "Сброс статистики (только админ)"),
        ("/test_weekly", "Тест еженедельных итогов (админ)"),
        ("/test_content", "Тест системы контента дня (админ)"),
        ("/jobs", "Показать запланированные задачи (админ)"),
    ]
    text = "📖 Доступные команды:\n\n" + "\n".join([f"{cmd} — {desc}" for cmd, desc in commands])
    await update.message.reply_text(text)

# Обновляем команду статистики
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_smoke_sessions = len(successful_polls)
    total_votes = len(sessions)
    
    text = f"""📊 Общая статистика:

🚬 Всего перекуров: {total_smoke_sessions}
🗳️ Всего голосов: {total_votes}

Используй:
/stats_detailed - подробная статистика с графиками
/me - твоя персональная статистика с графиками
/top - топ курильщиков
/workers_top - топ работяг
/test_weekly - тест еженедельных итогов (админ)
/test_content - тест системы контента дня (админ)
/jobs - показать запланированные задачи (админ)"""
    
    await update.message.reply_text(text)

# В функции main() добавляем обработчики и планировщик:
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("❌ Установите BOT_TOKEN через переменную окружения!")
        return
    
    load_data()
    
    try:
        app = Application.builder().token(BOT_TOKEN).build()

        # Команды
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stats", show_stats))
        app.add_handler(CommandHandler("stats_detailed", show_detailed_stats))
        app.add_handler(CommandHandler("me", show_me))
        app.add_handler(CommandHandler("top", show_top))
        app.add_handler(CommandHandler("workers_top", show_workers_top))
        app.add_handler(CommandHandler("help", show_help))
        app.add_handler(CommandHandler("reset", reset_stats))
        app.add_handler(CommandHandler("test_weekly", test_weekly_summary))
        app.add_handler(CommandHandler("test_content", test_content_system))
        app.add_handler(CommandHandler("jobs", show_scheduled_jobs))

        # Сообщения
        app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Sticker.ALL, handle_message))
        
        # Обработчики для системы контента
        app.add_handler(MessageHandler(
            filters.Text(["Анекдот дня 😄", "Мем дня 🎭", "Пропустить этот раз 🔄"]),
            handle_user_content_choice
        ))
        
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_user_content_text
        ))

        # Опросы
        app.add_handler(PollAnswerHandler(handle_poll_answer))

        logger.info("🤖 Бот запускается...")
        
        # Планировщики
        schedule_weekly_summary(app)
        schedule_content_system(app)
        
        app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()

