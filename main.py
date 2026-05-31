import random
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime

# НАСТРОЙКА: Вставь сюда свои данные
TOKEN = "8626005892:AAGGhDL-IgQvo-Jw2Q2jrU6YIRqRpx8KrGQ"
ADMIN_ID =  977553639 # СЮДА_ВСТАВЬ_СВОЙ_ID (например: 543216789)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Подключаем базу данных SQLite (она создастся автоматически)
conn = sqlite3.connect("daily_cm.db")
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER,
        user_id INTEGER,
        username TEXT,
        score INTEGER DEFAULT 0,
        last_use TEXT,
        PRIMARY KEY (chat_id, user_id)
    )
''')
conn.commit()

@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    today = datetime.now().strftime("%Y-%m-%d")

    # Проверяем, играл ли юзер сегодня в этом чате
    cursor.execute("SELECT score, last_use FROM users WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    user = cursor.fetchone()

    if user and user[1] == today:
        await message.reply("❌ Ты уже крутил сегодня! Приходи завтра.")
        return

    # НАКРУТКА: Если пишет админ — всегда даем жесткий плюс, остальным — рандом
    if user_id == ADMIN_ID:
        cm = random.randint(15, 20)  # Тебе всегда выпадет от 15 до 20 см
    else:
        cm = random.randint(-5, 20)  # Обычным юзерам от -5 до 20 см

    new_score = (user[0] if user else 0) + cm

    # Обновляем или добавляем юзера в базу
    cursor.execute('''
        INSERT INTO users (chat_id, user_id, username, score, last_use)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id) 
        DO UPDATE SET score = ?, last_use = ?, username = ?
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
    
    # Берем топ-10 игроков конкретно этого чата
    cursor.execute("SELECT username, score FROM users WHERE chat_id = ? ORDER BY score DESC LIMIT 10", (chat_id,))
    leaders = cursor.fetchall()

    if not leaders:
        await message.reply("Таблица лидеров пуста. Напишите /daily!")
        return

    text = "🏆 **ТОП СМ В ЭТОМ ЧАТЕ:**\n\n"
    for i, leader in enumerate(leaders, 1):
        text += f"{i}. {leader[0]} — {leader[1]} см\n"
    
    await message.reply(text, parse_mode="Markdown")

if __name__ == "__main__":
    dp.run_polling(bot)
