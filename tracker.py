import os
import requests
from playwright.sync_api import sync_playwright

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://kinovod.pro/serial/245917-monarh-nasledie-monstrov"
FILE_NAME = "last_episode.txt"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text={text}"
    requests.get(url)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(URL, wait_until="networkidle", timeout=60000)
            element = page.wait_for_selector(".episodes .active", timeout=15000)
            current_val = element.inner_text().strip()

            last_val = ""
            if os.path.exists(FILE_NAME):
                with open(FILE_NAME, "r") as f:
                    last_val = f.read().strip()

            if current_val != last_val:
                send_telegram(f"🔔 Новая серия!\nТекущая: {current_val}\n{URL}")
                with open(FILE_NAME, "w") as f:
                    f.write(current_val)
        except Exception as e:
            print(f"Ошибка: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
