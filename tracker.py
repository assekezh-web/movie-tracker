import os
import asyncio
import logging
import threading
from flask import Flask
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.async_api import async_playwright

# 1. Настройка Flask для Render (Health Check)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!", 200

def run_flask():
    # Render использует порт 10000 по умолчанию
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. Настройки бота
logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FILE_NAME = "last_episodes.txt"

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_last_episode(url):
    async with async_playwright() as p:
        try:
            # Важно: аргументы для работы внутри Docker/Render
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Ждем селектор номера серии
            element = await page.wait_for_selector("li.active span.video-series-number", timeout=15000)
            if element:
                text = await element.inner_text()
                result = "".join(filter(str.isdigit, text))
                await browser.close()
                return int(result) if result else 0
            
            await browser.close()
            return 0
        except Exception as e:
            logging.error(f"Ошибка парсинга {url}: {e}")
            return 0

async def check_updates_logic():
    if not os.path.exists(FILE_NAME):
        return
    
    with open(FILE_NAME, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if "==" not in line: continue
        url, last_ep = line.strip().split("==")
        current_ep = await get_last_episode(url)
        
        if current_ep > int(last_ep):
            name = url.split('/')[-1].replace('-', ' ').title()
            await bot.send_message(CHAT_ID, f"🔔 Новая серия: {name}\nСерия: {current_ep}\n{url}")
            new_lines.append(f"{url}=={current_ep}\n")
        else:
            new_lines.append(line)
            
    with open(FILE_NAME, "w") as f:
        f.writelines(new_lines)

# 3. Команды бота
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот активen!\n/add [ссылка] — добавить\n/list — список\n/check — проверить")

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" not in url:
        return await message.answer("Нужна ссылка на kinovod.pro")
    
    with open(FILE_NAME, "a") as f:
        f.write(f"{url}==0\n")
    await message.answer("👍 Добавил в список!")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not os.path.exists(FILE_NAME) or os.stat(FILE_NAME).st_size == 0:
        return await message.answer("Список пуст.")
    with open(FILE_NAME, "r") as f:
        lines = f.readlines()
    text = "\n".join([f"• {line.split('==')[0].split('/')[-1]}" for line in lines])
    await message.answer(f"Отслеживаю:\n{text}")

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Проверяю, это займет минуту...")
    await check_updates_logic()
    await message.answer("✅ Проверка завершена.")

async def scheduler():
    while True:
        await asyncio.sleep(21600) # 6 часов
        await check_updates_logic()

async def main():
    # Запуск планировщика
    asyncio.create_task(scheduler())
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск Flask для Health Check
    threading.Thread(target=run_flask, daemon=True).start()
    # Запуск бота
    asyncio.run(main())
