import random
import sqlite3
import asyncio
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

# Временное хранилище для текста рассылки админа (чтобы бот помнил, что отправлять после нажатия кнопки)
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

@dp.message(Command("set"))
async def cmd_set_cm(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        return
    if message.chat.type != "private":
        await message.reply("❌ Эту команду нужно писать мне в личку!")
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
            await message.reply(f"❌ Юзера @{target_username} нет в базе данных.")
            return
        cursor.execute('UPDATE users SET next_custom_cm = ? WHERE user_id = ?', (chosen_cm, target[0]))
        conn.commit()
        await message.reply(f"🤫 Подкрутил для @{target_username}: {chosen_cm} см.")

# ====================================================
# НОВАЯ КОМАНДА /mes ДЛЯ ОТПРАВКИ СООБЩЕНИЙ В ГРУППЫ
# ====================================================
@dp.message(Command("mes"))
async def cmd_send_message_menu(message: types.Message):
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        return
    if message.chat.type != "private":
        await message.reply("❌ Пиши эту команду только мне в личку!")
        return

    # Получаем текст сообщения, который идет после команды /mes
    text_to_send = message.text[5:].strip() # Пропускаем "/mes "
    if not text_to_send:
        await message.reply("Использование: `/mes <твой текст>`\nНапример: `/mes Всем привет от админа!`")
        return

    # Запоминаем текст, который админ хочет отправить
    admin_messages[user_id] = text_to_send

    # Ищем уникальные chat_id (группы) из нашей базы данных
    cursor.execute("SELECT DISTINCT chat_id FROM users WHERE chat_id < 0")
    chats = cursor.fetchall()

    if not chats:
        await message.reply("❌ В базе данных пока нет ни одной группы. Бот должен быть добавлен в группу, и там кто-то должен написать команду!")
        return

    # Создаем интерактивное меню с кнопками
    keyboard = InlineKeyboardBuilder()
    
    for count, chat in enumerate(chats, 1):
        chat_id = chat[0]
        # Так как Телеграм без специальных запросов не выдает красивое имя группы в личке,
        # мы просто делаем кнопку "Группа №..." с её ID, чтобы бот точно знал куда слать.
        keyboard.button(
            text=f"Группа {count} (ID: {chat_id})", 
            callback_data=f"send_to_{chat_id}"
        )
    
    keyboard.adjust(1) # Кнопки будут идти в один столбик
    await message.reply("👇 Выбери группу, куда бот должен отправить это сообщение:", reply_markup=keyboard.as_markup())

# Обработка нажатия на кнопку выбора группы
@dp.callback_query(lambda c: c.data.startswith('send_to_'))
async def process_send_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback_query.answer("У тебя нет прав!", show_alert=True)
        return

    # Извлекаем chat_id из даты кнопки
    target_chat_id = int(callback_query.data.replace("send_to_", ""))
    
    # Берем сохраненный текст админа
    text_to_send = admin_messages.get(user_id)

    if not text_to_send:
        await callback_query.message.edit_text("❌ Ошибка: текст сообщения затерялся. Напиши команду `/mes <текст>` заново.")
        return

    try:
        # Отправляем сообщение в выбранную группу от лица бота
        await bot.send_message(chat_id=target_chat_id, text=text_to_send)
        # Обновляем меню в личке админа, подтверждая успех
        await callback_query.message.edit_text(f"✅ Сообщение успешно отправлено в чат `{target_chat_id}`!\n\nТекст: {text_to_send}")
        # Очищаем память
        admin_messages.pop(user_id, None)
    except Exception as e:
         await callback_query.message.edit_text(f"❌ Не удалось отправить сообщение. Возможно, бота кикнули из этой группы.\nОшибка: {e}")

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
