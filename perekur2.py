import logging
import json
import os
from collections import defaultdict, Counter
from datetime import datetime, timedelta, time
import io
import random
import matplotlib.pyplot as plt
import numpy as np

from telegram import Update, ReplyKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, PollAnswerHandler
)

# --- Настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = -1003072750672
ADMIN_ID = 284884293
DATA_FILE = "bot_data.json"
BACKUP_FILE = "bot_data_backup.json"
POLL_DURATION = 600  # 10 минут
COOLDOWN = timedelta(minutes=15)

# Константы для уровней (до 1000 ответов)
SMOKER_LEVELS = {
    0: "Курильщик 0 lvl",
    10: "Курильщик 1 lvl", 
    20: "Курильщик 2 lvl",
    30: "Курильщик 3 lvl",
    40: "Курильщик 4 lvl",
    50: "Курильщик 5 lvl",
    60: "Курильщик 6 lvl",
    70: "Курильщик 7 lvl",
    80: "Курильщик 8 lvl",
    90: "Курильщик 9 lvl",
    100: "Курильщик 10 lvl",
    150: "Курильщик 15 lvl",
    200: "Курильщик 20 lvl",
    250: "Курильщик 25 lvl",
    300: "Курильщик 30 lvl",
    350: "Курильщик 35 lvl",
    400: "Курильщик 40 lvl",
    450: "Курильщик 45 lvl",
    500: "Курильщик 50 lvl",
    550: "Курильщик 55 lvl",
    600: "Курильщик 60 lvl",
    650: "Курильщик 65 lvl",
    700: "Курильщик 70 lvl",
    750: "Курильщик 75 lvl",
    800: "Курильщик 80 lvl",
    850: "Курильщик 85 lvl",
    900: "Курильщик 90 lvl",
    950: "Курильщик 95 lvl",
    1000: "Курильщик MAX lvl"
}

WORKER_LEVELS = {
    0: "Работяга 0 lvl",
    10: "Работяга 1 lvl",
    20: "Работяга 2 lvl", 
    30: "Работяга 3 lvl",
    40: "Работяга 4 lvl",
    50: "Работяга 5 lvl",
    60: "Работяга 6 lvl",
    70: "Работяга 7 lvl",
    80: "Работяга 8 lvl",
    90: "Работяга 9 lvl",
    100: "Работяга 10 lvl",
    150: "Работяга 15 lvl",
    200: "Работяга 20 lvl",
    250: "Работяга 25 lvl",
    300: "Работяга 30 lvl",
    350: "Работяга 35 lvl",
    400: "Работяга 40 lvl",
    450: "Работяга 45 lvl",
    500: "Работяга 50 lvl",
    550: "Работяга 55 lvl",
    600: "Работяга 60 lvl",
    650: "Работяга 65 lvl",
    700: "Работяга 70 lvl",
    750: "Работяга 75 lvl",
    800: "Работяга 80 lvl",
    850: "Работяга 85 lvl",
    900: "Работяга 90 lvl",
    950: "Работяга 95 lvl",
    1000: "Работяга MAX lvl"
}

# Константы для других ачивок
ACHIEVEMENT_STICKERS_20 = 20
ACHIEVEMENT_PHOTOS_20 = 20
CONSECUTIVE_THRESHOLD = 5

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Кнопки ---
main_keyboard = [["Курить 🚬"]]
reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

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
successful_polls = []  # Успешные перекуры (опросы с хотя бы одним голосом "Да")
user_levels = defaultdict(dict)  # {user_id: {"smoker_level": int, "worker_level": int}}

# --- СИСТЕМА КОНТЕНТА ДНЯ ---
content_submissions = {}  # {user_id: {"message": message, "date": datetime}}
asked_today = set()  # Пользователи, которых уже спрашивали сегодня
current_content_author = None  # Текущий автор контента

# --- Вспомогательные функции для графиков ---
def setup_plot_style():
    """Настройка стиля графиков"""
    plt.style.use('seaborn-v0_8')
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['axes.facecolor'] = '#f8f9fa'
    plt.rcParams['figure.facecolor'] = '#ffffff'

def create_user_stats_plot(user_id):
    """Создание персональной статистики пользователя"""
    setup_plot_style()
    
    user_sessions = [(t, ans) for t, uid, ans in sessions if uid == user_id]
    if not user_sessions:
        return None
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    username = usernames.get(user_id, f"User{user_id}")
    fig.suptitle(f'📊 Статистика пользователя: {username}', fontsize=14, fontweight='bold')
    
    # 1. Распределение ответов пользователя
    user_answers = Counter(ans for _, ans in user_sessions)
    colors = ['#28a745', '#dc3545']  # Только Да и Нет
    axes[0, 0].pie(user_answers.values(), labels=user_answers.keys(), autopct='%1.1f%%',
                   colors=colors[:len(user_answers)], startangle=90)
    axes[0, 0].set_title('Мои ответы')
    
    # 2. Активность по дням недели
    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    day_count = [0] * 7
    for t, _ in user_sessions:
        day_count[t.weekday()] += 1
    
    axes[0, 1].bar(days, day_count, color='#007bff', alpha=0.7)
    axes[0, 1].set_title('Мои активные дни')
    axes[0, 1].set_ylabel('Голосов')
    axes[0, 1].grid(True, alpha=0.3)
    
    # 3. Активность по рабочим часам (7:00-17:00)
    work_periods = ['7-8', '8-9', '9-10', '10-11', '11-12', '12-13', '13-14', '14-15', '15-16', '16-17']
    period_count = [0] * 10
    
    for t, _ in user_sessions:
        hour = t.hour
        # Только рабочие часы с 7:00 до 17:00
        if 7 <= hour < 17:
            period_index = hour - 7
            period_count[period_index] += 1
    
    # Фильтруем только периоды с активностью
    active_periods = []
    active_counts = []
    for i, count in enumerate(period_count):
        if count > 0:
            active_periods.append(work_periods[i])
            active_counts.append(count)
    
    if active_counts:
        axes[1, 0].bar(active_periods, active_counts, color='#20c997', alpha=0.7)
        axes[1, 0].set_title('Активность по рабочим часам')
        axes[1, 0].set_ylabel('Голосов')
        axes[1, 0].grid(True, alpha=0.3)
        plt.setp(axes[1, 0].xaxis.get_majorticklabels(), rotation=45)
    else:
        axes[1, 0].text(0.5, 0.5, 'Нет активности\nв рабочие часы', 
                       ha='center', va='center', transform=axes[1, 0].transAxes)
        axes[1, 0].set_title('Активность по рабочим часам')
    
    # 4. История активности (последние 7 дней)
    today = datetime.now().date()
    last_week = [today - timedelta(days=i) for i in range(6, -1, -1)]
    week_dates = [d.strftime('%d.%m') for d in last_week]
    week_count = [0] * 7
    
    for t, _ in user_sessions:
        session_date = t.date()
        for i, date_obj in enumerate(last_week):
            if session_date == date_obj:
                week_count[i] += 1
                break
    
    axes[1, 1].plot(week_dates, week_count, marker='o', linewidth=2, color='#dc3545')
    axes[1, 1].fill_between(week_dates, week_count, alpha=0.3, color='#dc3545')
    axes[1, 1].set_title('Моя активность за неделю')
    axes[1, 1].set_ylabel('Голосов в день')
    axes[1, 1].grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

def create_statistics_plot():
    """Создание общей статистики"""
    setup_plot_style()
    
    if not sessions:
        return None
    
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('📊 Статистика перекуров', fontsize=16, fontweight='bold')
    
    # 1. Распределение ответов
    answers_count = {
        'Да, конечно': sum(1 for _, _, ans in sessions if ans == "Да, конечно"),
        'Нет': sum(1 for _, _, ans in sessions if ans == "Нет")
    }
    
    colors = ['#28a745', '#dc3545']  # Только Да и Нет
    axes[0, 0].pie(answers_count.values(), labels=answers_count.keys(), autopct='%1.1f%%', 
                   colors=colors, startangle=90)
    axes[0, 0].set_title('📈 Распределение ответов')
    
    # 2. Активность по дням недели
    days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    day_count = [0] * 7
    for t, _, _ in sessions:
        day_count[t.weekday()] += 1
    
    axes[0, 1].bar(days, day_count, color='#007bff', alpha=0.7)
    axes[0, 1].set_title('📅 Активность по дням недели')
    axes[0, 1].set_ylabel('Количество голосов')
    axes[0, 1].grid(True, alpha=0.3)
    
    # 3. Активность по рабочим часам (7:00-17:00)
    work_periods = ['7-8', '8-9', '9-10', '10-11', '11-12', '12-13', '13-14', '14-15', '15-16', '16-17']
    period_count = [0] * 10
    
    for t, _, _ in sessions:
        hour = t.hour
        # Только рабочие часы с 7:00 до 17:00
        if 7 <= hour < 17:
            period_index = hour - 7
            period_count[period_index] += 1
    
    # Фильтруем только периоды с активностью
    active_periods = []
    active_counts = []
    for i, count in enumerate(period_count):
        if count > 0:
            active_periods.append(work_periods[i])
            active_counts.append(count)
    
    if active_counts:
        axes[1, 0].bar(active_periods, active_counts, color='#20c997', alpha=0.7)
        axes[1, 0].set_title('🕐 Активность по рабочим часам')
        axes[1, 0].set_xlabel('Часовые промежутки')
        axes[1, 0].set_ylabel('Количество голосов')
        axes[1, 0].grid(True, alpha=0.3)
        plt.setp(axes[1, 0].xaxis.get_majorticklabels(), rotation=45)
    else:
        axes[1, 0].text(0.5, 0.5, 'Нет активности\nв рабочие часы', 
                       ha='center', va='center', transform=axes[1, 0].transAxes)
        axes[1, 0].set_title('🕐 Активность по рабочим часам')
    
    # 4. Топ пользователей
    user_yes = defaultdict(int)
    for _, uid, ans in sessions:
        if ans == "Да, конечно":
            user_yes[uid] += 1
    
    if user_yes:
        top_users = sorted(user_yes.items(), key=lambda x: x[1], reverse=True)[:8]
        user_names = [usernames.get(uid, f"User{uid}")[:15] for uid, _ in top_users]
        user_counts = [count for _, count in top_users]
        
        y_pos = np.arange(len(user_names))
        axes[1, 1].barh(y_pos, user_counts, color='#fd7e14', alpha=0.7)
        axes[1, 1].set_yticks(y_pos)
        axes[1, 1].set_yticklabels(user_names)
        axes[1, 1].set_title('🏆 Топ курильщиков')
        axes[1, 1].set_xlabel('Количество "Да"')
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf

# --- Сохранение/загрузка ---
def create_backup():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as source:
                data = source.read()
            with open(BACKUP_FILE, 'w', encoding='utf-8') as target:
                target.write(data)
            logger.info("Резервная копия данных создана")
        except Exception as e:
            logger.error(f"Ошибка при создании бэкапа: {e}")

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
        # СИСТЕМА КОНТЕНТА: сохраняем только asked_today
        "asked_today": list(asked_today),
    }
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Данные успешно сохранены")
    except Exception as e:
        logger.error(f"Ошибка при сохранении данных: {e}")

def load_data():
    global stats_yes, stats_no, stats_stickers, stats_photos
    global usernames, sessions, consecutive_yes, consecutive_no, consecutive_button_press
    global last_button_press_time, achievements_unlocked, successful_polls, user_levels
    global asked_today
    
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
        
        # СИСТЕМА КОНТЕНТА: загружаем asked_today
        asked_today.update(data.get("asked_today", []))
        
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

# --- Выдача ачивок ---
async def give_achievement(user_id: int, context: ContextTypes.DEFAULT_TYPE, achievement_name: str):
    if achievement_name not in achievements_unlocked[user_id]:
        achievements_unlocked[user_id].add(achievement_name)
        save_data()
        
        try:
            await context.bot.send_message(chat_id=user_id, text=f"🏅 Ачивка: {achievement_name}")
        except Exception as e:
            logger.warning(f"Не удалось отправить ачивку пользователю {user_id}: {e}")
        
        username = usernames.get(user_id, "Неизвестный")
        try:
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=f"🎉 {username} получил(а) ачивку: {achievement_name}!")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление в группу: {e}")

# --- Система уровней ---
def get_smoker_level(yes_count: int) -> tuple:
    """Получить уровень курильщика и следующий порог"""
    level_thresholds = sorted(SMOKER_LEVELS.keys(), reverse=True)
    for threshold in level_thresholds:
        if yes_count >= threshold:
            return SMOKER_LEVELS[threshold], threshold
    return SMOKER_LEVELS[0], 0

def get_worker_level(no_count: int) -> tuple:
    """Получить уровень работяги и следующий порог"""
    level_thresholds = sorted(WORKER_LEVELS.keys(), reverse=True)
    for threshold in level_thresholds:
        if no_count >= threshold:
            return WORKER_LEVELS[threshold], threshold
    return WORKER_LEVELS[0], 0

async def check_level_up(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Проверить повышение уровня и уведомить пользователя"""
    yes_count = stats_yes[user_id]
    no_count = stats_no[user_id]
    
    # Получаем текущие и новые уровни
    current_smoker_level = user_levels[user_id].get("smoker_level", 0)
    current_worker_level = user_levels[user_id].get("worker_level", 0)
    
    new_smoker_level, smoker_threshold = get_smoker_level(yes_count)
    new_worker_level, worker_threshold = get_worker_level(no_count)
    
    # Проверяем повышение уровня курильщика
    if smoker_threshold > current_smoker_level:
        user_levels[user_id]["smoker_level"] = smoker_threshold
        username = usernames.get(user_id, "Неизвестный")
        
        # Уведомление в личку
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=f"🎉 Поздравляем! Ты достиг нового уровня: {new_smoker_level}!"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о уровне пользователю {user_id}: {e}")
        
        # Уведомление в группу
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🚬 {username} повысил(а) уровень до {new_smoker_level}! 🎉"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление в группу: {e}")
        
        logger.info(f"Пользователь {user_id} повысил уровень курильщика до {new_smoker_level}")
    
    # Проверяем повышение уровня работяги
    if worker_threshold > current_worker_level:
        user_levels[user_id]["worker_level"] = worker_threshold
        username = usernames.get(user_id, "Неизвестный")
        
        # Уведомление в личку
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=f"🎉 Поздравляем! Ты достиг нового уровня: {new_worker_level}!"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о уровне пользователю {user_id}: {e}")
        
        # Уведомление в группу
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"💪 {username} повысил(а) уровень до {new_worker_level}! 🎉"
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление в группу: {e}")
        
        logger.info(f"Пользователь {user_id} повысил уровень работяги до {new_worker_level}")
    
    save_data()

# --- Проверка ачивок ---
async def check_achievements(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    # Используем екатеринбургское время для проверки ачивок
    now_utc = datetime.utcnow()
    now_ekt = now_utc + timedelta(hours=5)  # YEKT = UTC + 5
    
    week_ago = now_ekt - timedelta(days=7)
    
    # Фильтруем сессии по екатеринбургскому времени
    yes_week = sum(1 for t, uid, ans in sessions 
                  if uid == user_id and ans == "Да, конечно" 
                  and (t + timedelta(hours=5)) >= week_ago)  # Конвертируем время сессии в ЕКБ
    no_week = sum(1 for t, uid, ans in sessions 
                 if uid == user_id and ans == "Нет" 
                 and (t + timedelta(hours=5)) >= week_ago)

    if consecutive_yes[user_id] >= CONSECUTIVE_THRESHOLD:
        await give_achievement(user_id, context, "Серийный курильщик")
    if consecutive_no[user_id] >= CONSECUTIVE_THRESHOLD:
        await give_achievement(user_id, context, "Серийный ЗОЖник")

    h = now_ekt.hour  # Используем екатеринбургское время для проверки времени суток
    if consecutive_yes[user_id] >= 1:
        if 0 <= h <= 7:
            await give_achievement(user_id, context, "Ранний перекур")
        elif 17 <= h <= 23:
            await give_achievement(user_id, context, "Ночная смена")

    if stats_stickers[user_id] >= ACHIEVEMENT_STICKERS_20:
        await give_achievement(user_id, context, "Стикеро(WO)MAN")
    if stats_photos[user_id] >= ACHIEVEMENT_PHOTOS_20:
        await give_achievement(user_id, context, "Мемолог")

    # Проверяем повышение уровней
    await check_level_up(user_id, context)

# --- Функции для группировки топов ---
def get_grouped_top(stats_dict, level_func):
    """Получить сгруппированный топ с учетом одинаковых значений (первые 3 места)"""
    if not stats_dict:
        return []
    
    # Сортируем по убыванию
    sorted_stats = sorted(stats_dict.items(), key=lambda x: x[1], reverse=True)
    
    # Группируем по значениям
    groups = []
    current_group = []
    current_value = None
    
    for user_id, count in sorted_stats:
        if count != current_value:
            if current_group:
                groups.append(current_group)
            current_value = count
            current_group = [(user_id, count)]
        else:
            current_group.append((user_id, count))
    
    if current_group:
        groups.append(current_group)
    
    # Присваиваем места (1, 2, 3) каждой группе
    result = []
    
    for place, group in enumerate(groups, 1):
        if place > 3:  # Ограничиваем тремя местами
            break
            
        # Все участники в группе получают одинаковое место
        for user_id, count in group:
            username = usernames.get(user_id, "Неизвестный")
            level_name, _ = level_func(count)
            result.append((place, username, count, level_name))
    
    return result

# --- СИСТЕМА КОНТЕНТА ДНЯ ---
def get_active_users():
    """Получить список активных пользователей за последние 7 дней"""
    # Используем екатеринбургское время
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    week_ago = now_ekt - timedelta(days=7)
    active_users = set()
    
    for t, uid, _ in sessions:
        # Конвертируем время сессии в ЕКБ для сравнения
        session_time_ekt = t + timedelta(hours=5)
        if session_time_ekt >= week_ago:
            active_users.add(uid)
    
    return list(active_users)

def reset_daily_content():
    """Сброс состояния ежедневного контента"""
    global asked_today, content_submissions, current_content_author
    asked_today.clear()
    content_submissions.clear()
    current_content_author = None
    logger.info("🔄 Состояние ежедневного контента сброшено")

async def ask_for_content(context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """Запросить контент у пользователя"""
    global current_content_author
    
    # Проверяем рабочий день (Пн-Пт) по екатеринбургскому времени
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    if now_ekt.weekday() >= 5:  # 5=Сб, 6=Вс
        logger.info("📅 Сегодня выходной, пропускаем запрос контента")
        return
    
    # Если пользователь не указан, выбираем случайного
    if user_id is None:
        active_users = get_active_users()
        if not active_users:
            logger.info("👥 Нет активных пользователей для запроса контента")
            return
        
        # Исключаем уже опрошенных сегодня
        available_users = [uid for uid in active_users if uid not in asked_today]
        if not available_users:
            logger.info("📝 Все активные пользователи уже были опрошены сегодня")
            return
        
        user_id = random.choice(available_users)
    
    # Сохраняем текущего автора
    current_content_author = user_id
    asked_today.add(user_id)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🎭 *Привет! Ты сегодняшний счастливчик!*\n\n"
                 "Отправь мне любой контент для *анонимной* публикации в общем чате:\n"
                 "• 📸 Картинка/мем\n"
                 "• 🎬 Видео/GIF\n" 
                 "• 🎵 Музыка/аудио\n"
                 "• 📝 Текст (анекдот, шутка, факт)\n"
                 "• 📎 Файл\n\n"
                 "Я просто перешлю твой контент в группу *без указания автора*.\n\n"
                 "Контент будет опубликован в 10:00 ⏰",
            parse_mode='Markdown'
        )
        
        logger.info(f"📨 Запрос контента отправлен пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке запроса пользователю {user_id}: {e}")
        # Переходим к следующему пользователю
        await ask_for_content(context)

async def handle_content_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка любого отправленного контента"""
    user_id = update.effective_user.id
    message = update.message
    
    # Проверяем, был ли пользователь выбран сегодня для отправки контента
    if user_id not in asked_today:
        return
    
    today_ekt = (datetime.utcnow() + timedelta(hours=5)).date()
    
    try:
        # Сохраняем сообщение для последующей публикации
        content_submissions[user_id] = {
            "message": message,
            "date": datetime.utcnow()  # Сохраняем в UTC
        }
        
        # Определяем тип контента для логов
        content_type = "текст"
        if message.photo:
            content_type = "картинка"
        elif message.video:
            content_type = "видео" 
        elif message.audio:
            content_type = "аудио"
        elif message.document:
            content_type = "файл"
        elif message.animation:
            content_type = "GIF"
        elif message.sticker:
            content_type = "стикер"
        elif message.voice:
            content_type = "голосовое сообщение"
        
        await message.reply_text(
            f"✅ Отлично! Твой {content_type} сохранён.\n\n"
            f"Он будет *анонимно* опубликован в общем чате сегодня в 10:00 🕙\n\n"
            f"_Никто не узнает, что это был ты_ 😉",
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Контент типа '{content_type}' от пользователя {user_id} сохранен")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении контента от пользователя {user_id}: {e}")
        await message.reply_text("❌ Произошла ошибка при сохранении контента.")

async def publish_daily_content(context: ContextTypes.DEFAULT_TYPE):
    """Публикация ежедневного контента в 10:00"""
    # Используем екатеринбургское время
    today_ekt = (datetime.utcnow() + timedelta(hours=5)).date()
    
    # Проверяем рабочий день
    if (datetime.utcnow() + timedelta(hours=5)).weekday() >= 5:
        logger.info("📅 Сегодня выходной, пропускаем публикацию контента")
        return
    
    if not content_submissions:
        logger.info("📭 Нет контента для публикации сегодня")
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text="📰 *Контент дня*\n\n"
                     "Сегодня никто не прислал контент для публикации 😔\n\n"
                     "Завтра у кого-то другого будет шанс! 🎲",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке уведомления об отсутствии контента: {e}")
        return
    
    try:
        # Отправляем заголовок
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="📰 *Контент дня!*\n\n"
                 "Сегодняшний анонимный контент от одного из участников:",
            parse_mode='Markdown'
        )
        
        # Пересылаем все сохраненные сообщения (анонимно)
        for user_id, submission in content_submissions.items():
            message = submission["message"]
            
            # Пересылаем сообщение в группу (без указания автора)
            if message.text:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=message.text
                )
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=GROUP_CHAT_ID,
                    photo=message.photo[-1].file_id,
                    caption=message.caption
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=GROUP_CHAT_ID,
                    video=message.video.file_id,
                    caption=message.caption
                )
            elif message.audio:
                await context.bot.send_audio(
                    chat_id=GROUP_CHAT_ID,
                    audio=message.audio.file_id,
                    caption=message.caption
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=GROUP_CHAT_ID,
                    document=message.document.file_id,
                    caption=message.caption
                )
            elif message.animation:
                await context.bot.send_animation(
                    chat_id=GROUP_CHAT_ID,
                    animation=message.animation.file_id,
                    caption=message.caption
                )
            elif message.sticker:
                await context.bot.send_sticker(
                    chat_id=GROUP_CHAT_ID,
                    sticker=message.sticker.file_id
                )
            elif message.voice:
                await context.bot.send_voice(
                    chat_id=GROUP_CHAT_ID,
                    voice=message.voice.file_id
                )
        
        # Отправляем завершающее сообщение
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="🎭 *Контент опубликован анонимно*\n\n"
                 "Завтра у другого участника будет шанс поделиться чем-то интересным!",
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ Опубликован контент дня от {len(content_submissions)} пользователя(ей)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при публикации контента дня: {e}")
    
    # Сбрасываем состояние
    reset_daily_content()

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для организации перекуров 🚬\n\n"
        "Используй кнопку 'Курить 🚬', чтобы начать опрос в группе!",
        reply_markup=reply_markup
    )

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    usernames[user_id] = username
    
    now = datetime.now()
    last_press = last_button_press_time[user_id]
    
    if now - last_press < COOLDOWN:
        remaining = COOLDOWN - (now - last_press)
        await update.message.reply_text(
            f"⏳ Подожди еще {int(remaining.total_seconds() // 60)} минут(ы) перед следующим запросом.",
            reply_markup=reply_markup
        )
        return
    
    last_button_press_time[user_id] = now
    consecutive_button_press[user_id] += 1
    
    if consecutive_button_press[user_id] >= 3:
        await give_achievement(user_id, context, "Настойчивый")
    
    global active_poll_id, active_poll_options, poll_votes, last_poll_time
    if active_poll_id is not None:
        await update.message.reply_text("Уже есть активный опрос! Голосуй там.", reply_markup=reply_markup)
        return
    
    last_poll_time = now
    poll_options = ["Да, конечно", "Нет"]
    active_poll_options = poll_options
    
    try:
        message = await context.bot.send_poll(
            chat_id=GROUP_CHAT_ID,
            question=f"Курить? (от @{username})",
            options=poll_options,
            is_anonymous=False,
            allows_multiple_answers=False,
            open_period=POLL_DURATION
        )
        active_poll_id = message.poll.id
        poll_votes = {}
        logger.info(f"Создан новый опрос {active_poll_id} пользователем {user_id}")
        
        await update.message.reply_text("✅ Опрос создан!", reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при создании опроса: {e}")
        await update.message.reply_text("❌ Ошибка при создании опроса.", reply_markup=reply_markup)

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_poll_id, poll_votes
    if active_poll_id is None or update.poll_answer.poll_id != active_poll_id:
        return
    
    user_id = update.poll_answer.user.id
    username = update.poll_answer.user.username or update.poll_answer.user.first_name
    usernames[user_id] = username
    
    selected_options = update.poll_answer.option_ids
    if not selected_options:
        return
    
    selected_option = active_poll_options[selected_options[0]]
    poll_votes[user_id] = selected_option
    
    logger.info(f"Пользователь {user_id} проголосовал: {selected_option}")

async def handle_poll_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global active_poll_id, poll_votes
    if active_poll_id is None or update.poll.id != active_poll_id:
        return
    
    if update.poll.is_closed:
        logger.info(f"Опрос {active_poll_id} завершен")
        
        # Сохраняем только окончательные голоса
        for user_id, answer in poll_votes.items():
            if answer == "Да, конечно":
                stats_yes[user_id] += 1
                consecutive_yes[user_id] += 1
                consecutive_no[user_id] = 0
            elif answer == "Нет":
                stats_no[user_id] += 1
                consecutive_no[user_id] += 1
                consecutive_yes[user_id] = 0
            
            sessions.append((last_poll_time, user_id, answer))
            await check_achievements(user_id, context)
        
        # Проверяем успешность опроса
        yes_votes = sum(1 for vote in poll_votes.values() if vote == "Да, конечно")
        if yes_votes > 0:
            successful_polls.append(last_poll_time)
            logger.info(f"Успешный перекур! {yes_votes} голосов 'Да'")
        
        save_data()
        
        # Сбрасываем состояние
        active_poll_id = None
        active_poll_options = []
        poll_votes = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    usernames[user_id] = username
    
    message = update.message
    
    # Обработка контента дня (если пользователь был выбран)
    if user_id in asked_today:
        await handle_content_submission(update, context)
        return
    
    # Обычная обработка статистики
    if message.sticker:
        stats_stickers[user_id] += 1
        await check_achievements(user_id, context)
        save_data()
    elif message.photo:
        stats_photos[user_id] += 1
        await check_achievements(user_id, context)
        save_data()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = usernames.get(user_id, "Неизвестный")
    
    yes_count = stats_yes[user_id]
    no_count = stats_no[user_id]
    total = yes_count + no_count
    yes_percentage = (yes_count / total * 100) if total > 0 else 0
    
    smoker_level, _ = get_smoker_level(yes_count)
    worker_level, _ = get_worker_level(no_count)
    
    # Используем екатеринбургское время для недельной статистики
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    week_ago = now_ekt - timedelta(days=7)
    
    # Фильтруем сессии по екатеринбургскому времени
    yes_week = sum(1 for t, uid, ans in sessions 
                  if uid == user_id and ans == "Да, конечно" 
                  and (t + timedelta(hours=5)) >= week_ago)
    no_week = sum(1 for t, uid, ans in sessions 
                 if uid == user_id and ans == "Нет" 
                 and (t + timedelta(hours=5)) >= week_ago)
    
    total_week = yes_week + no_week
    yes_week_percentage = (yes_week / total_week * 100) if total_week > 0 else 0
    
    response = (
        f"📊 *Статистика для {username}:*\n\n"
        f"*Общая статистика:*\n"
        f"🚬 Да: {yes_count}\n"
        f"💪 Нет: {no_count}\n"
        f"📈 Процент согласий: {yes_percentage:.1f}%\n\n"
        f"*Статистика за неделю:*\n"
        f"🚬 Да: {yes_week}\n"
        f"💪 Нет: {no_week}\n"
        f"📈 Процент согласий: {yes_week_percentage:.1f}%\n\n"
        f"*Уровни:*\n"
        f"🚬 {smoker_level}\n"
        f"💪 {worker_level}\n\n"
        f"*Дополнительно:*\n"
        f"🎭 Стикеров отправлено: {stats_stickers[user_id]}\n"
        f"📸 Фото отправлено: {stats_photos[user_id]}\n"
        f"🏅 Ачивок получено: {len(achievements_unlocked[user_id])}"
    )
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объединенный топ курильщиков и работяг"""
    if not sessions:
        await update.message.reply_text("📊 Пока нет статистики.")
        return
    
    # Используем екатеринбургское время для недельной статистики
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    week_ago = now_ekt - timedelta(days=7)
    
    # Общая статистика (все время)
    response = "🏆 *ТОП УЧАСТНИКОВ*\n\n"
    
    # Топ курильщиков (все время)
    if stats_yes:
        response += "🚬 *ТОП КУРИЛЬЩИКОВ (все время):*\n"
        smoker_top = get_grouped_top(stats_yes, get_smoker_level)
        for place, username, count, level in smoker_top:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
            response += f"{medal} {username}: {count} раз - {level}\n"
    else:
        response += "🚬 *ТОП КУРИЛЬЩИКОВ:*\nПока нет данных\n"
    
    response += "\n"
    
    # Топ работяг (все время)
    if stats_no:
        response += "💪 *ТОП РАБОТЯГ (все время):*\n"
        worker_top = get_grouped_top(stats_no, get_worker_level)
        for place, username, count, level in worker_top:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
            response += f"{medal} {username}: {count} раз - {level}\n"
    else:
        response += "💪 *ТОП РАБОТЯГ:*\nПока нет данных\n"
    
    response += "\n"
    
    # Недельная статистика
    weekly_yes = defaultdict(int)
    weekly_no = defaultdict(int)
    
    for t, uid, ans in sessions:
        # Конвертируем время сессии в ЕКБ для сравнения
        session_time_ekt = t + timedelta(hours=5)
        if session_time_ekt >= week_ago:
            if ans == "Да, конечно":
                weekly_yes[uid] += 1
            elif ans == "Нет":
                weekly_no[uid] += 1
    
    # Недельный топ курильщиков
    if weekly_yes:
        response += "📅 *НЕДЕЛЬНЫЙ ТОП КУРИЛЬЩИКОВ:*\n"
        weekly_smoker_top = get_grouped_top(weekly_yes, get_smoker_level)
        for place, username, count, level in weekly_smoker_top:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
            response += f"{medal} {username}: {count} раз - {level}\n"
    else:
        response += "📅 *НЕДЕЛЬНЫЙ ТОП КУРИЛЬЩИКОВ:*\nПока нет данных\n"
    
    response += "\n"
    
    # Недельный топ работяг
    if weekly_no:
        response += "📅 *НЕДЕЛЬНЫЙ ТОП РАБОТЯГ:*\n"
        weekly_worker_top = get_grouped_top(weekly_no, get_worker_level)
        for place, username, count, level in weekly_worker_top:
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
            response += f"{medal} {username}: {count} раз - {level}\n"
    else:
        response += "📅 *НЕДЕЛЬНЫЙ ТОП РАБОТЯГ:*\nПока нет данных\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка графика статистики"""
    buf = create_statistics_plot()
    if buf is None:
        await update.message.reply_text("📊 Пока недостаточно данных для построения графиков.")
        return
    
    await update.message.reply_photo(
        photo=InputFile(buf, filename="statistics.png"),
        caption="📊 *Общая статистика перекуров*",
        parse_mode='Markdown'
    )

async def my_graph(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка персонального графика статистики"""
    user_id = update.effective_user.id
    buf = create_user_stats_plot(user_id)
    if buf is None:
        await update.message.reply_text("📊 У тебя пока нет статистики для построения графиков.")
        return
    
    username = usernames.get(user_id, "Пользователь")
    await update.message.reply_photo(
        photo=InputFile(buf, filename="my_statistics.png"),
        caption=f"📊 *Персональная статистика: {username}*",
        parse_mode='Markdown'
    )

async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать полученные ачивки"""
    user_id = update.effective_user.id
    user_achievements = achievements_unlocked[user_id]
    username = usernames.get(user_id, "Неизвестный")
    
    if not user_achievements:
        await update.message.reply_text("🏅 У тебя пока нет ачивок. Продолжай участвовать в опросах!")
        return
    
    response = f"🏅 *Ачивки пользователя {username}:*\n\n"
    for i, achievement in enumerate(sorted(user_achievements), 1):
        response += f"{i}. {achievement}\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для администратора"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    
    total_users = len(set(list(stats_yes.keys()) + list(stats_no.keys())))
    total_sessions = len(sessions)
    total_successful = len(successful_polls)
    
    # Используем екатеринбургское время
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    week_ago = now_ekt - timedelta(days=7)
    
    # Фильтруем по екатеринбургскому времени
    sessions_week = sum(1 for t, _, _ in sessions if (t + timedelta(hours=5)) >= week_ago)
    successful_week = sum(1 for t in successful_polls if (t + timedelta(hours=5)) >= week_ago)
    
    response = (
        f"👑 *Админ статистика:*\n\n"
        f"• Всего пользователей: {total_users}\n"
        f"• Всего сессий: {total_sessions}\n"
        f"• Успешных перекуров: {total_successful}\n"
        f"• Сессий за неделю: {sessions_week}\n"
        f"• Успешных за неделю: {successful_week}\n"
        f"• Активный опрос: {'Да' if active_poll_id else 'Нет'}\n"
        f"• Размер файла данных: {os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 0} байт"
    )
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def reset_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной сброс недельной статистики (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для этой команды.")
        return
    
    # В новой системе недельная статистика рассчитывается на лету из sessions
    # поэтому не требует сброса. Но можно добавить уведомление о новом недельном топе
    
    # Используем екатеринбургское время
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    
    await update.message.reply_text(
        f"✅ Недельная статистика рассчитывается автоматически.\n"
        f"Текущая неделя: {now_ekt.strftime('%d.%m.%Y')}\n"
        f"Недельный топ обновляется автоматически.",
        parse_mode='Markdown'
    )

async def friday_rewards(context: ContextTypes.DEFAULT_TYPE):
    """Пятничное награждение по недельному топу"""
    # Используем екатеринбургское время
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    
    # Проверяем, что сегодня пятница (4) и время около 17:00
    if now_ekt.weekday() != 4 or now_ekt.hour < 16:
        return
    
    logger.info("🎉 Запуск пятничного награждения по недельному топу")
    
    # Рассчитываем недельную статистику
    week_ago = now_ekt - timedelta(days=7)
    weekly_yes = defaultdict(int)
    weekly_no = defaultdict(int)
    
    for t, uid, ans in sessions:
        session_time_ekt = t + timedelta(hours=5)
        if session_time_ekt >= week_ago:
            if ans == "Да, конечно":
                weekly_yes[uid] += 1
            elif ans == "Нет":
                weekly_no[uid] += 1
    
    # Находим победителей недели
    weekly_smoker_top = get_grouped_top(weekly_yes, get_smoker_level)
    weekly_worker_top = get_grouped_top(weekly_no, get_worker_level)
    
    try:
        message = "🎉 *ПЯТНИЧНОЕ НАГРАЖДЕНИЕ!*\n\n"
        message += "По итогам рабочей недели определяем лучших:\n\n"
        
        if weekly_smoker_top:
            message += "🚬 *Лучшие курильщики недели:*\n"
            for place, username, count, level in weekly_smoker_top[:3]:  # Только первые 3 места
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
                message += f"{medal} {username} - {count} раз\n"
        else:
            message += "🚬 *Лучшие курильщики недели:*\nПока нет данных\n"
        
        message += "\n"
        
        if weekly_worker_top:
            message += "💪 *Лучшие работяги недели:*\n"
            for place, username, count, level in weekly_worker_top[:3]:  # Только первые 3 места
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, "🏅")
                message += f"{medal} {username} - {count} раз\n"
        else:
            message += "💪 *Лучшие работяги недели:*\nПока нет данных\n"
        
        message += "\nПоздравляем победителей! 🎊\nХороших выходных! 😊"
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        
        logger.info("✅ Пятничное награждение отправлено")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке пятничного награждения: {e}")

async def daily_content_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Напоминание о контенте дня в 9:30"""
    # Используем екатеринбургское время
    now_ekt = datetime.utcnow() + timedelta(hours=5)
    
    # Проверяем рабочий день и время
    if now_ekt.weekday() >= 5 or now_ekt.hour != 9 or now_ekt.minute != 30:
        return
    
    logger.info("📝 Напоминание о контенте дня")
    
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text="🎭 *Напоминание!*\n\n"
                 "Сегодня в 10:00 будет опубликован *анонимный контент дня*!\n\n"
                 "Если ты был выбран сегодняшним автором - не забудь отправить свой контент!",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке напоминания: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

# --- Основная функция ---
def main():
    load_data()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("top", top))
    application.add_handler(CommandHandler("graph", graph))
    application.add_handler(CommandHandler("my_graph", my_graph))
    application.add_handler(CommandHandler("achievements", achievements))
    application.add_handler(CommandHandler("admin_stats", admin_stats))
    application.add_handler(CommandHandler("reset_week", reset_week))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.Regex("^Курить 🚬$"), handle_button))
    
    # ОБНОВЛЕННЫЙ ФИЛЬТР для обработки всех типов сообщений
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO | 
        filters.Document.ALL | filters.ANIMATION | filters.VOICE | filters.Sticker.ALL, 
        handle_message
    ))
    
    # Обработчики опросов
    application.add_handler(PollAnswerHandler(handle_poll_answer))
    application.add_handler(MessageHandler(filters.POLL, handle_poll_update))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Планировщик задач
    job_queue = application.job_queue
    
    # Ежедневный сброс состояния контента в 00:01 ЕКБ (19:01 UTC)
    job_queue.run_daily(
        lambda context: reset_daily_content(),
        time=time(hour=19, minute=1, second=0),  # 00:01 ЕКБ
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    
    # Запрос контента в 9:00 ЕКБ (4:00 UTC)
    job_queue.run_daily(
        lambda context: application.create_task(ask_for_content(context)),
        time=time(hour=4, minute=0, second=0),  # 9:00 ЕКБ
        days=(0, 1, 2, 3, 4)  # Пн-Пт
    )
    
    # Напоминание о контенте в 9:30 ЕКБ (4:30 UTC)
    job_queue.run_daily(
        lambda context: application.create_task(daily_content_reminder(context)),
        time=time(hour=4, minute=30, second=0),  # 9:30 ЕКБ
        days=(0, 1, 2, 3, 4)  # Пн-Пт
    )
    
    # Публикация контента в 10:00 ЕКБ (5:00 UTC)
    job_queue.run_daily(
        lambda context: application.create_task(publish_daily_content(context)),
        time=time(hour=5, minute=0, second=0),  # 10:00 ЕКБ
        days=(0, 1, 2, 3, 4)  # Пн-Пт
    )
    
    # Пятничное награждение в 17:00 ЕКБ (12:00 UTC)
    job_queue.run_daily(
        lambda context: application.create_task(friday_rewards(context)),
        time=time(hour=12, minute=0, second=0),  # 17:00 ЕКБ
        days=(4,)  # Только пятница
    )
    
    # Сохранение данных каждые 5 минут
    job_queue.run_repeating(
        lambda context: save_data(),
        interval=300,
        first=10
    )
    
    logger.info("Бот запущен")
    application.run_polling()

if __name__ == "__main__":
    main()
