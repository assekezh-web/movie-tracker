import os
import asyncio
import logging
import threading
import psycopg2
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.async_api import async_playwright

# 1. Flask для Render (Health Check)
app = Flask(__name__)
@app.route('/')
def home(): return "Bot with DB is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. Настройки и логирование
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DB_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# 3. Работа с базой данных
def init_db():
    """Создает таблицу и переносит данные из файла при первом запуске."""
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    # Создаем таблицу
    cur.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                   (url TEXT PRIMARY KEY, last_ep INTEGER)''')
    
    # Пытаемся мигрировать данные из старого файла
    if os.path.exists("last_episode.txt"):
        logging.info("Обнаружен текстовый файл, переношу данные в БД...")
        try:
            with open("last_episode.txt", "r") as f:
                for line in f:
                    if "==" in line:
                        url, ep = line.strip().split("==")
                        cur.execute("INSERT INTO subscriptions (url, last_ep) VALUES (%s, %s) ON CONFLICT DO NOTHING", (url, int(ep)))
            conn.commit()
            logging.info("Миграция завершена успешно.")
        except Exception as e:
            logging.error(f"Ошибка миграции: {e}")
            
    cur.close()
    conn.close()

async def get_last_episode(url):
    """Парсинг номера серии через Playwright."""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            element = await page.wait_for_selector("li.active span.video-series-number", timeout=15000)
            text = await element.inner_text()
            res = int("".join(filter(str.isdigit, text))) if text else 0
            await browser.close()
            return res
        except Exception as e:
            logging.error(f"Ошибка парсинга {url}: {e}")
            return 0

# 4. Обработка команд Telegram
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🎬 **Бот-трекер на PostgreSQL активен!**\n\n"
        "📌 **Команды:**\n"
        "/add [ссылка] — добавить сериал\n"
        "/list — список подписок\n"
        "/remove [номер] — удалить из списка\n"
        "/check — ручная проверка обновлений"
    )

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" not in url:
        return await message.answer("❌ Ошибка: Нужна прямая ссылка на kinovod.pro")
    
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO subscriptions (url, last_ep) VALUES (%s, %s)", (url, 0))
        conn.commit()
        await message.answer(f"✅ Добавлено в базу! Запускаю проверку...")
        # Сразу проверяем текущую серию
        current_ep = await get_last_episode(url)
        cur.execute("UPDATE subscriptions SET last_ep = %s WHERE url = %s", (current_ep, url))
        conn.commit()
        await message.answer(f"📊 Текущая серия: {current_ep}")
    except Exception:
        await message.answer("⚠ Этот сериал уже отслеживается.")
    finally:
        cur.close()
        conn.close()

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT url, last_ep FROM subscriptions ORDER BY url")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return await message.answer("📭 Ваш список подписок пуст.")
    
    text = "📋 **Ваши подписки:**\n\n"
    for i, (url, ep) in enumerate(rows, 1):
        name = url.split('/')[-1].replace('-', ' ').title()
        text += f"{i}. {name} (Серия: {ep})\n"
    text += "\n💡 Чтобы удалить, введите `/remove номер`"
    await message.answer(text)

@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    try:
        parts = message.text.split()
        if len(parts) < 2: return await message.answer("Использование: `/remove 1`")
        
        idx = int(parts[1]) - 1
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT url FROM subscriptions ORDER BY url")
        rows = cur.fetchall()
        
        if 0 <= idx < len(rows):
            target = rows[idx][0]
            cur.execute("DELETE FROM subscriptions WHERE url = %s", (target,))
            conn.commit()
            await message.answer(f"🗑 Удалено: {target.split('/')[-1]}")
        else:
            await message.answer("❌ Неверный номер в списке.")
        cur.close()
        conn.close()
    except Exception:
        await message.answer("❌ Ошибка. Введите `/remove [номер из списка]`")

async def check_updates_logic():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT url, last_ep FROM subscriptions")
    for url, last_ep in cur.fetchall():
        current_ep = await get_last_episode(url)
        if current_ep > last_ep:
            name = url.split('/')[-1].replace('-', ' ').title()
            await bot.send_message(CHAT_ID, f"🔔 **НОВАЯ СЕРИЯ!**\n🎬 {name}\n🔢 Серия: {current_ep}\n🔗 {url}")
            cur.execute("UPDATE subscriptions SET last_ep = %s WHERE url = %s", (current_ep, url))
            conn.commit()
    cur.close()
    conn.close()

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Проверяю обновления для всех подписок...")
    await check_updates_logic()
    await message.answer("✅ Проверка завершена.")

async def scheduler():
    while True:
        await asyncio.sleep(21600) # Проверка каждые 6 часов
        await check_updates_logic()

async def main():
    init_db()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
