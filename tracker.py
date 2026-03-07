import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from playwright.sync_api import sync_playwright

# Настройки логирования
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FILE_NAME = "last_episodes.txt"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Глобальный список ссылок (загружается из файла)
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

    with open(FILE_NAME, "w") as f:
        for u, v in data.items():
            f.write(f"{u}=={v}\n")
    return results

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Бот-трекер запущен! \n/add [ссылка] - добавить сериал\n/list - список\n/check - проверить сейчас")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" in url:
        if url not in urls:
            urls.append(url)
            with open(FILE_NAME, "a") as f:
                f.write(f"{url}==0\n")
            await message.answer(f"✅ Добавлено в список отслеживания!")
        else:
            await message.answer("Этот сериал уже есть в списке.")
    else:
        await message.answer("Пришлите корректную ссылку с kinovod.pro")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not urls:
        await message.answer("Список пуст.")
    else:
        text = "\n".join([f"• {u.split('/')[-1]}" for u in urls])
        await message.answer(f"Отслеживаю:\n{text}")

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Запускаю проверку, подождите...")
    updates = check_updates()
    if updates:
        for up in updates:
            await message.answer(up)
    else:
        await message.answer("Новых серий пока нет.")

async def scheduler():
    while True:
        # Проверка каждые 6 часов автоматически
        await asyncio.sleep(21600)
        updates = check_updates()
        if updates:
            for up in updates:
                await bot.send_message(CHAT_ID, up)

async def main():
    load_urls()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
