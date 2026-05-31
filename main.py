import random
import sqlite3
import asyncio
import os
import requests
import base64
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiohttp import web

# ====================================================
# НАСТРОЙКА: Твои данные
# ====================================================
TOKEN = "8626005892:AAGGhDL-IgQvo-Jw2Q2jrU6YIRqRpx8KrGQ"
ADMIN_IDS = [977553639]  # Твой ID

# НАСТРОЙКА СОХРАНЕНИЯ В GITHUB:
GITHUB_TOKEN = "Ghp_v0gEkBBiXb0XutFznYl1lwzIixxwux2G27Bq"  # Твой токен уже тут
GITHUB_REPO = "pego12341-popka/daily-cm-bot-" # Твой репозиторий

DB_PATH = "daily_cm.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Функция для скачивания базы с GitHub при запуске
def download_db_from_github():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        data = res.json()
        db_content = base64.b64decode(data["content"])
        with open(DB_PATH, "wb") as f:
            f.write(db_content)
        print("📥 База данных успешно загружена из GitHub!")
    else:
        print("🆕 База данных не найдена на GitHub, создаем новую.")

# Функция для сохранения базы на GitHub
def save_db_to_github():
    if not os.path.exists(DB_PATH):
        return
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DB_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    with open(DB_PATH, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")
        
    res = requests.get(url, headers=headers)
    sha = None
    if res.status_code == 200:
        sha = res.json()["sha"]
        
    data = {
        "message": "🔥 Авто-обновление базы данных сантиметров",
        "content": content
    }
    if sha:
        data["sha"] = sha
        
    requests.put(url, headers=headers, json=data)
    print("📤 База данных сохранена на GitHub!")

# Скачиваем старую базу перед стартом
download_db_from_github()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER,
        user_id INTEGER,
        username TEXT,
        score INTEGER DEFAULT 0,
        last_use TEXT,
        next_custom_cm INTEGER DEFAULT NULL,
        PRIMARY KEY (chat_id, user_id)
    )
''')
conn.commit()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN next_custom_cm INTEGER DEFAULT NULL")
    conn.commit()
except sqlite3.OperationalError:
    pass

admin_messages = {}

@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT score, last_use, next_custom_cm FROM users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    user = cursor.fetchone()

    if user and user[1] == today:
        await message.reply("❌ Ты уже крутил сегодня! Купи еще одну попытку за 5 см через /shop")
        return

    if user and user[2] is not None:
        cm = user[2]
    elif user_id in ADMIN_IDS:
        cm = random.randint(15, 20)
    else:
        cm = random.randint(-5, 20)

    new_score = (user[0] if user else 0) + cm

    cursor.execute('''
        INSERT INTO users (chat_id, user_id, username, score, last_use, next_custom_cm)
        VALUES (?, ?, ?, ?, ?, NULL)
        ON CONFLICT(chat_id, user_id) 
        DO UPDATE SET score = ?, last_use = ?, username = ?, next_custom_cm = NULL
    ''', (chat_id, user_id, username, new_score, today, new_score, today, username))
    conn.commit()
    save_db_to_github()

    if cm > 0:
        await message.reply(f"📈 Твой результат сегодня: +{cm} см! Всего: {new_score} см.")
    elif cm == 0:
        await message.reply(f"😐 Ничего не изменилось: 0 см. Всего: {new_score} см.")
    else:
        await message.reply(f"📉 Оу... у тебя убавилось: {cm} см. Всего: {new_score} см.")

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    chat_id = message.chat.id
    cursor.execute("SELECT username, score FROM users WHERE chat_id = ? ORDER BY score DESC LIMIT 10", (chat_id,))
    leaders = cursor.fetchall()

    if not leaders:
        await message.reply("Таблица лидеров пуста. Напишите /daily!")
        return

    text = "🏆 **ТОП СМ В ЭТОМ ЧАТЕ:**\n\n"
    for i, leader in enumerate(leaders, 1):
        text += f"{i}. {leader[0]} — {leader[1]} см\n"
    await message.reply(text, parse_mode="Markdown")

@dp.message(Command("shop"))
async def cmd_shop(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT score, last_use FROM users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    user = cursor.fetchone()

    if not user or user[0] < 5:
        await message.reply("❌ У тебя не хватает см! Нужно минимум 5 см на балансе.")
        return

    if user[1] != today:
        await message.reply("❓ Ты сегодня еще не крутил бесплатный `/daily`!")
        return

    new_score = user[0] - 5
    cursor.execute('UPDATE users SET score = ?, last_use = "" WHERE chat_id = ? AND user_id = ?', (new_score, chat_id, user_id))
    conn.commit()
    save_db_to_github()
    await message.reply(f"🛒 Успешная покупка! Списано 5 см (Осталось: {new_score} см).\n🔥 Твой таймер сброшен, пиши `/daily`!")

@dp.message(Command("set"))
async def cmd_set_cm(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    args = message.text.split()
    if len(args) == 2:
        try:
            chosen_cm = int(args[1])
        except ValueError:
            await message.reply("❌ Введи правильное число!")
            return
        cursor.execute('UPDATE users SET next_custom_cm = ? WHERE user_id = ?', (chosen_cm, user_id))
        conn.commit()
        save_db_to_github()
        await message.reply(f"🤫 Себе настроил! Выпадет: {chosen_cm} см.")
    elif len(args) == 3:
        target_username = args[1].replace("@", "").strip()
        try:
            chosen_cm = int(args[2])
        except ValueError:
            await message.reply("❌ Введи правильное число!")
            return
        
        cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)', (target_username,))
        target = cursor.fetchone()
        
        if not target:
            fake_user_id = random.randint(100000, 999999)
            cursor.execute('INSERT INTO users (chat_id, user_id, username, score, next_custom_cm) VALUES (0, ?, ?, 0, ?)', (fake_user_id, target_username, chosen_cm))
        else:
            cursor.execute('UPDATE users SET next_custom_cm = ? WHERE user_id = ?', (chosen_cm, target[0]))
            
        conn.commit()
        save_db_to_github()
        await message.reply(f"🤫 Подкрутил для @{target_username}: {chosen_cm} см.")

@dp.message(Command("give"))
async def cmd_give_cm(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("Формат: `/give @username <сколько>`")
        return

    target_username = args[1].replace("@", "").strip()
    try:
        amount = int(args[2])
    except ValueError:
        await message.reply("❌ Введи число!")
        return

    cursor.execute('SELECT user_id, score FROM users WHERE LOWER(username) = LOWER(?)', (target_username,))
    target = cursor.fetchone()
    
    if not target:
        new_user_id = random.randint(1000000, 9999999)
        cursor.execute('INSERT INTO users (chat_id, user_id, username, score) VALUES (0, ?, ?, ?)', (new_user_id, target_username, amount))
        new_score = amount
    else:
        new_score = target[1] + amount
        cursor.execute('UPDATE users SET score = ? WHERE user_id = ?', (new_score, target[0]))
        
    conn.commit()
    save_db_to_github()
    await message.reply(f"✅ Готово! У @{target_username} теперь: {new_score} см. (Добавлен автоматически).")

@dp.message(Command("take"))
async def cmd_take_cm(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("Формат: `/take @username <сколько>`")
        return

    target_username = args[1].replace("@", "").strip()
    try:
        amount = int(args[2])
    except ValueError:
        await message.reply("❌ Введи число!")
        return

    cursor.execute('SELECT user_id, score FROM users WHERE LOWER(username) = LOWER(?)', (target_username,))
    target = cursor.fetchone()
    if not target:
        await message.reply(f"❌ Юзера @{target_username} нет в базе данных.")
        return

    new_score = target[1] - amount
    cursor.execute('UPDATE users SET score = ? WHERE user_id = ?', (new_score, target[0]))
    conn.commit()
    save_db_to_github()
    await message.reply(f"✅ Списано! У @{target_username} осталось: {new_score} см.")

@dp.message(Command("reset"))
async def cmd_reset_user(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Формат: `/reset @username`")
        return

    target_username = args[1].replace("@", "").strip()

    cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)', (target_username,))
    target = cursor.fetchone()
    if not target:
        await message.reply(f"❌ Юзера @{target_username} нет в базе данных.")
        return

    cursor.execute('UPDATE users SET score = 0 WHERE user_id = ?', (target[0],))
    conn.commit()
    save_db_to_github()
    await message.reply(f"🔥 У @{target_username} теперь 0 см.") 

# 4. КОМАНДА /giveall (Раздать всем см в текущем чате)
@dp.message(Command("giveall"))
async def cmd_give_all(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("Формат: `/giveall <сколько_всем>`")
        return

    try:
        amount = int(args[1])
    except ValueError:
        await message.reply("❌ Введи число!")
        return

    # Получаем список всех уникальных юзеров из базы
    cursor.execute('UPDATE users SET score = score + ?', (amount,))
    conn.commit()
    save_db_to_github()
    
    await message.reply(f"✅ Успешно! Всем игрокам в базе начислено +{amount} см.")

@dp.message(Command("mes"))
async def cmd_send_message_menu(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS or message.chat.type != "private":
        return

    text_to_send = message.text[5:].strip()
    if not text_to_send:
        await message.reply("Использование: `/mes <текст>`")
        return

    admin_messages[user_id] = text_to_send
    cursor.execute("SELECT DISTINCT chat_id FROM users WHERE chat_id < 0")
    chats = cursor.fetchall()

    if not chats:
        await message.reply("❌ В базе данных пока нет ни одной группы.")
        return

    keyboard = InlineKeyboardBuilder()
    for count, chat in enumerate(chats, 1):
        chat_id = chat[0]
        keyboard.button(text=f"Группа {count} (ID: {chat_id})", callback_data=f"send_to_{chat_id}")
    
    keyboard.adjust(1)
    await message.reply("👇 Выбери группу для отправки сообщения:", reply_markup=keyboard.as_markup())

@dp.callback_query(lambda c: c.data.startswith('send_to_'))
async def process_send_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in ADMIN_IDS:
        return

    target_chat_id = int(callback_query.data.replace("send_to_", ""))
    text_to_send = admin_messages.get(user_id)

    if not text_to_send:
        await callback_query.message.edit_text("❌ Ошибка: напиши команду заново.")
        return

    try:
        await bot.send_message(chat_id=target_chat_id, text=text_to_send)
        await callback_query.message.edit_text(f"✅ Сообщение отправлено!")
        admin_messages.pop(user_id, None)
    except Exception as e:
         await callback_query.message.edit_text(f"❌ Ошибка отправки: {e}")

# Веб-сервер для обхода ошибки портов на Render Web Service
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    asyncio.create_task(site.start())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
 
