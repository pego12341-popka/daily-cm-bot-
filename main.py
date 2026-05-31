import random
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime
from aiohttp import web

# ====================================================
# НАСТРОЙКА: Твои данные уже внутри
# ====================================================
TOKEN = "8626005892:AAGGhDL-IgQvo-Jw2Q2jrU6YIRqRpx8KrGQ"
ADMIN_IDS = [977553639]  # Твой ID. Можно добавлять друзей через запятую

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Подключаем базу данных
conn = sqlite3.connect("daily_cm.db")
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

# Проверяем колонку для кастомных см
try:
    cursor.execute("ALTER TABLE users ADD COLUMN next_custom_cm INTEGER DEFAULT NULL")
    conn.commit()
except sqlite3.OperationalError:
    pass

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

    # Логика выдачи см
    if user and user[2] is not None:
        # Если админ заказал число (себе или кому-то)
        cm = user[2]
    elif user_id in ADMIN_IDS:
        # Обычная админская накрутка в плюс
        cm = random.randint(15, 20)
    else:
        # Обычный рандом для участников группы
        cm = random.randint(-5, 20)

    new_score = (user[0] if user else 0) + cm

    # Записываем данные и сбрасываем кастомное число обратно в NULL, чтобы сработало один раз
    cursor.execute('''
        INSERT INTO users (chat_id, user_id, username, score, last_use, next_custom_cm)
        VALUES (?, ?, ?, ?, ?, NULL)
        ON CONFLICT(chat_id, user_id) 
        DO UPDATE SET score = ?, last_use = ?, username = ?, next_custom_cm = NULL
    ''', (chat_id, user_id, username, new_score, today, new_score, today, username))
    conn.commit()

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
    await message.reply(f"🛒 Успешная покупка! Списано 5 см (Осталось: {new_score} см).\n🔥 Твой таймер сброшен, пиши `/daily`!")

# СЕКРЕТНАЯ УЛУЧШЕННАЯ КОМАНДА В ЛИЧКЕ БОТА
@dp.message(Command("set"))
async def cmd_set_cm(message: types.Message):
    user_id = message.from_user.id

    # 1. Проверяем, админ ли это
    if user_id not in ADMIN_IDS:
        return

    # 2. Проверяем, что админ пишет это в ЛИЧКЕ бота, а не в группе
    if message.chat.type != "private":
        await message.reply("❌ Эту команду нужно писать мне в личку, чтобы никто в группе не спалил!")
        return

    args = message.text.split()
    
    # Вариант 1: Накрутка СЕБЕ (/set 50)
    if len(args) == 2:
        try:
            chosen_cm = int(args[1])
        except ValueError:
            await message.reply("❌ Введи правильное число!")
            return

        cursor.execute('UPDATE users SET next_custom_cm = ? WHERE user_id = ?', (chosen_cm, user_id))
        conn.commit()
        await message.reply(f"🤫 Себе настроил! При следующем прокруте `/daily` тебе выпадет: {chosen_cm} см.")
        return

    # Вариант 2: Накрутка ДРУГОМУ УЧАСТНИКУ (/set @username 100)
    elif len(args) == 3:
        target_username = args[1].replace("@", "").strip()
        try:
            chosen_cm = int(args[2])
        except ValueError:
            await message.reply("❌ Введи правильное число!")
            return

        # Ищем челика в базе данных по его юзернейму
        cursor.execute('SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)', (target_username,))
        target = cursor.fetchone()

        if not target:
            await message.reply(f"❌ Юзера @{target_username} пока нет в моей базе данных. Он должен хотя бы один раз написать любую команду боту в группе (например /top или /daily), чтобы я его запомнил!")
            return

        target_id = target[0]
        # Обновляем ему кастомное число
        cursor.execute('UPDATE users SET next_custom_cm = ? WHERE user_id = ?', (chosen_cm, target_id))
        conn.commit()
        await message.reply(f"🤫 Сделано! Подкрутил для @{target_username}. Ему при следующем `/daily` выпадет ровно: {chosen_cm} см.")
        return

    else:
        await message.reply("Неправильный формат!\n\nПиши:\n`/set <число>` — себе\n`/set @username <число>` — другому")


# ОБМАНКА ДЛЯ RENDER
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 10000)
    asyncio.create_task(site.start())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
