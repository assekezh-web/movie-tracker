import asyncio
import os
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from playwright.async_api import async_playwright

# Настройки Flask для Render
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Данные бота
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
FILE_NAME = "last_episode.txt"

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def get_last_episode(url):
    async with async_playwright() as p:
        try:
            # Запуск с флагами для стабильности в Docker/Render
            browser = await p.chromium.launch(
                headless=True, 
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(15)  # Ждем прогрузку динамического контента
            
            # Поиск номера серии
            element = await page.query_selector("li.active span.video-series-number")
            if element:
                text = await element.inner_text()
                result = "".join(filter(str.isdigit, text))
                await browser.close()
                return int(result) if result else 0
            await browser.close()
            return 0
        except Exception as e:
            print(f"Ошибка при парсинге {url}: {e}")
            return 0

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✅ Бот активен на Render!\n\n/add [ссылка] — добавить сериал\n/list — что отслеживаем\n/check — проверить сейчас")

@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    if not os.path.exists(FILE_NAME) or os.stat(FILE_NAME).st_size == 0:
        return await message.answer("Список пуст.")
    with open(FILE_NAME, "r") as f:
        lines = f.readlines()
    response = "Отслеживаю:\n" + "\n".join([line.split("==")[0].split("/")[-1] for line in lines])
    await message.answer(response)

@dp.message(Command("add"))
async def cmd_add(message: types.Message):
    url = message.text.replace("/add ", "").strip()
    if "kinovod.pro" not in url:
        return await message.answer("Нужна ссылка на kinovod.pro")
    with open(FILE_NAME, "a") as f:
        f.write(f"{url}==0\n")
    await message.answer("👍 Добавил в список!")

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await message.answer("🔄 Проверяю серии, это займет пару минут...")
    await check_updates_logic()

async def check_updates_logic():
    if not os.path.exists(FILE_NAME): return
    with open(FILE_NAME, "r") as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        url, last_ep = line.strip().split("==")
        current_ep = await get_last_episode(url)
        
        if current_ep > int(last_ep):
            await bot.send_message(CHAT_ID, f"🔔 Новая серия! ({current_ep})\n{url}")
            new_lines.append(f"{url}=={current_ep}\n")
        else:
            new_lines.append(line)
            
    with open(FILE_NAME, "w") as f:
        f.writelines(new_lines)

async def scheduler():
    while True:
        await check_updates_logic()
        await asyncio.sleep(21600)  # Проверка каждые 6 часов

async def main():
    Thread(target=run_flask).start()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
