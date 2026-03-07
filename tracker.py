import os
import asyncio
import logging
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.sync_api import sync_playwright

# 1. Настройка Flask для Render (чтобы не было Timed Out)
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    # Render использует порт 10000 по умолчанию
    app.run(host='0.0.0.0', port=10000)

# 2. Настройки бота
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

def check_updates():
    results = []
    data = {}
    if os.path.exists(FILE_NAME):
        with open(FILE_NAME, "r") as f:
            for line in f:
                if "==" in line:
                    u, v = line.strip().split("==")
                    data[u] = v

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for url in urls:
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    element = page.wait_for_selector(".episodes .active", timeout=15000)
                    current_val = element.inner_text().strip()
                    name = url.split('/')[-1].replace('-', ' ').title()

                    if data.get(url) != current_val:
                        results.append(f"🔔 Обновление: {name}\nСерия: {current_val}\n{url}")
                        data[url] = current_val
                except Exception as e:
                    logging.error(f"Ошибка на {url}: {e}")
            browser.close()
        except Exception as e:
            logging.error(f"Ошибка запуска браузера: {e}")

    with open(FILE_NAME, "w") as f:
        for u, v in data.items():
            f.write(f"{u}=={v}\n")
    return results

# 3. Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот активен на Render!\n\nКоманды:\n/add [ссылка] — добавить сериал\n/list — что отслеживаем\n/check — проверить сейчас")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" in url:
        if url not in urls:
            urls.append(url)
            with open(FILE_NAME, "a") as f:
                f.write(f"{url}==0\n")
            await message.answer("👍 Добавил в список!")
        else:
            await message.answer("Уже есть в списке.")
    else:
        await message.answer("Нужна ссылка на kinovod.pro")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    load_urls()
    if not urls:
        await message.answer("Список пуст.")
    else:
        text = "\n".join([f"• {u.split('/')[-1]}" for u in urls])
        await message.answer(f"Отслеживаю:\n{text}")

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Проверяю серии, это займет около минуты...")
    updates = check_updates()
    if updates:
        for up in updates:
            await message.answer(up)
    else:
        await message.answer("Новых серий не найдено.")

async def scheduler():
    while True:
        await asyncio.sleep(21600) # Проверка каждые 6 часов
        updates = check_updates()
        if updates:
            for up in updates:
                try:
                    await bot.send_message(CHAT_ID, up)
                except Exception as e:
                    logging.error(f"Ошибка отправки: {e}")

async def main():
    load_urls()
    # Запускаем фоновую проверку
    asyncio.create_task(scheduler())
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Сначала запускаем Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    # Затем запускаем асинхронную часть
    asyncio.run(main())
