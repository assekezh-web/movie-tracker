import os
import asyncio
import logging
import threading
import psycopg2
import requests
from bs4 import BeautifulSoup
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# Flask для поддержания активности на Render
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is alive", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Настройки из Environment Variables
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_conn():
    return psycopg2.connect(DB_URL, sslmode='require')

async def get_last_episode(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Логика для kinovod.pro
            items = soup.find_all("div", class_="item")
            for item in items:
                text = item.get_text().lower()
                if "серия" in text:
                    num_text = "".join(filter(str.isdigit, text))
                    return int(num_text) if num_text else 0
        return 0
    except Exception as e:
        logging.error(f"Ошибка парсинга {url}: {e}")
        return 0

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        "👋 Привет! Я бот для отслеживания серий на Kinovod.\n\n"
        "Доступные команды:\n"
        "/add [ссылка] — добавить сериал\n"
        "/list — ваши подписки\n"
        "/check — проверить новые серии вручную\n"
        "/remove [ссылка] — удалить сериал"
    )
    await message.answer(text)

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" not in url:
        return await message.answer("⚠️ Пожалуйста, введите ссылку на сайт kinovod.pro")
    
    msg = await message.answer("⌛ Проверяю сериал на сайте...")
    ep = await get_last_episode(url)
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO subs (url, last_ep) VALUES (%s, %s) "
        "ON CONFLICT (url) DO UPDATE SET last_ep = EXCLUDED.last_ep", 
        (url, ep)
    )
    conn.commit()
    cur.close()
    conn.close()
    await msg.edit_text(f"✅ Добавлено! Текущая серия: {ep}")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT url, last_ep FROM subs")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows:
        return await message.answer("Ваш список подписок пуст.")
    
    res = []
    for r in rows:
        name = r[0].split('/')[-1]
        res.append(f"🎬 {name}: {r[1]} сер.\n🔗 {r[0]}")
    
    await message.answer("📋 Ваши подписки:\n\n" + "\n\n".join(res))

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔍 Запускаю проверку обновлений...")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT url, last_ep FROM subs")
    rows = cur.fetchall()
    
    updates_found = False
    for url, last_ep in rows:
        current_ep = await get_last_episode(url)
        if current_ep > last_ep:
            updates_found = True
            name = url.split('/')[-1]
            await message.answer(f"🔔 Новая серия!\n🎬 {name}\nСтало: {current_ep} (было: {last_ep})\n🔗 {url}")
            cur.execute("UPDATE subs SET last_ep = %s WHERE url = %s", (current_ep, url))
    
    conn.commit()
    cur.close()
    conn.close()
    
    if not updates_found:
        await message.answer("Новых серий пока нет.")

@dp.message(Command("remove"))
async def cmd_remove(message: types.Message):
    url = message.text.replace("/remove ", "").strip()
    if not url:
        return await message.answer("Введите ссылку, которую хотите удалить (из списка /list).")
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM subs WHERE url = %s", (url,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    if deleted > 0:
        await message.answer("✅ Сериал успешно удален.")
    else:
        await message.answer("❌ Этот сериал не найден в вашем списке.")

async def main():
    # Запуск Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    logging.info("Бот запущен и готов к работе")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
