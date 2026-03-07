import os
import requests
from playwright.sync_api import sync_playwright

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Создаем список ссылок
URLS = [
    "https://kinovod.pro/serial/245917-monarh-nasledie-monstrov",
    "https://kinovod.pro/serial/260779-yelloustoun-marshaly",
    "https://kinovod.pro/serial/257228-pervobytnyy"
]
FILE_NAME = "last_episodes.txt"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}"
    requests.get(url)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Читаем все сохраненные данные в словарь
        data = {}
        if os.path.exists(FILE_NAME):
            with open(FILE_NAME, "r") as f:
                for line in f:
                    if "==" in line:
                        url, val = line.strip().split("==")
                        data[url] = val

        for url in URLS:
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                element = page.wait_for_selector(".episodes .active", timeout=15000)
                current_val = element.inner_text().strip()
                
                # Получаем название сериала из URL для красивого уведомления
                name = url.split('/')[-1].replace('-', ' ').title()

                if data.get(url) != current_val:
                    send_telegram(f"🔔 Обновление: {name}\nСерия: {current_val}\n{url}")
                    data[url] = current_val
            except Exception as e:
                print(f"Ошибка на {url}: {e}")

        # Сохраняем обновленные данные обратно в файл
        with open(FILE_NAME, "w") as f:
            for url, val in data.items():
                f.write(f"{url}=={val}\n")
        
        browser.close()

if __name__ == "__main__":
    run()
