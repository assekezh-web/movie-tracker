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

app = Flask(__name__)
@app.route('/')
def home(): return "Bot is alive", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DB_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_conn():
    return psycopg2.connect(DB_URL, sslmode='require')

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS subs (url TEXT PRIMARY KEY, last_ep INTEGER)')
    conn.commit()
    cur.close()
    conn.close()

async def get_last_episode(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            # Логика для kinovod.pro: ищем текст "серия" в информации о релизе
            items = soup.find_all("div", class_="item")
            for item in items:
                text = item.get_text().lower()
                if "серия" in text:
                    # Извлекаем только цифры
                    num_text = "".join(filter(str.isdigit, text))
                    return int(num_text) if num_text else 0
        return 0
    except Exception as e:
        logging.error(f"Ошибка парсинга {url}: {e}")
        return 0

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
    res = "\n".join([f"🎬 {r[0].split('/')[-1]}: {r[1]} сер." for r in rows])
    await message.answer(f"Ваши подписки:\n{res}")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" not in url:
        return await message.answer("Пожалуйста, введите ссылку на kinovod.pro")
    
    msg = await message.answer("⌛ Проверяю Kinovod...")
    ep = await get_last_episode(url)
    
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO subs (url, last_ep) VALUES (%s, %s) ON CONFLICT (url) DO UPDATE SET last_ep = EXCLUDED.last_ep", (url, ep))
    conn.commit()
    cur.close()
    conn.close()
    await msg.edit_text(f"✅ Добавлено! Последняя серия на Kinovod: {ep}")

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())
