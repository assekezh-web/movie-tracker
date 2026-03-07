import os
import asyncio
import logging
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.async_api import async_playwright

# 1. Настройка Flask для Render (чтобы статус стал Live)
app = Flask('')

@app.route('/')
def home():
    return "Movie Tracker Bot is Running!"

def run_flask():
    # Render ожидает ответ на порту 10000
    app.run(host='0.0.0.0', port=10000)

# 2. Настройки бота и логирования
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FILE_NAME = "last_episodes.txt"

bot = Bot(token=TOKEN)
dp = Dispatcher()
urls = []

def load_urls():
    global urls
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, "r") as f:
            urls = [line.split('==')[0] for line in f if '==' in line]

async def check_updates():
    results = []
    data = {}
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, "r") as f:
            for line in f:
                if "==" in line:
                    u, v = line.strip().split("==")
                    data[u] = v

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page()
            for url in urls:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    element = await page.wait_for_selector(".episodes .active", timeout=15000)
                    current_val = await element.inner_text()
                    current_val = current_val.strip()
                    name = url.split('/')[-1].replace('-', ' ').title()

                    if data.get(url) != current_val:
                        results.append(f"🔔 Обновление: {name}\nСерия: {current_val}\n{url}")
                        data[url] = current_val
                except Exception as e:
                    logging.error(f"Ошибка на {url}: {e}")
            await browser.close()
        except Exception as e:
            logging.error(f"Критическая ошибка браузера: {e}")

    with open(FILE_NAME, "w") as f:
        for u, v in data.items():
            f.write(f"{u}=={v}\n")
    return results

# 3. Команды бота
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот запущен на Render!\n\n/add [ссылка] — добавить сериал\n/list — список отслеживания\n/check — проверить сейчас")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" in url:
        if url not in urls:
            urls.append(url)
            with open(FILE_NAME, "a") as f:
                f.write(f"{url}==0\n")
            await message.answer("👍 Сериал добавлен в список!")
        else:
            await message.answer("Этот сериал уже отслеживается.")
    else:
        await message.answer("Пожалуйста, отправьте корректную ссылку на kinovod.pro")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    load_urls()
    if not urls:
        await message.answer("Ваш список пуст.")
    else:
        text = "\n".join([f"• {u.split('/')[-1]}" for u in urls])
        await message.answer(f"Сейчас отслеживаю:\n{text}")

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Проверяю новые серии... Это займет около минуты.")
    updates = await check_updates()
    if updates:
        for up in updates:
            await message.answer(up)
    else:
        await message.answer("Пока новых серий нет.")

async def scheduler():
    while True:
        await asyncio.sleep(21600) # Проверка каждые 6 часов
        updates = await check_updates()
        if updates:
            for up in updates:
                try:
                    await bot.send_message(CHAT_ID, up)
                except Exception as e:
                    logging.error(f"Ошибка уведомления: {e}")

async def main():
    load_urls()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск Flask для Render в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    # Запуск основного цикла бота
    asyncio.run(main())
