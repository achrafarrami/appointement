import asyncio
import hashlib
import os
from playwright.async_api import async_playwright
import httpx

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
URL = (
    "https://rdv.anct.gouv.fr/prendre_rdv"
    "?departement=&motif_name_with_location_type=renouvellement_de_recepisses_arrives_a_echeance_-public_office"
    "&public_link_organisation_id=2458"
)
STATE_FILE = "state.txt"


async def send_telegram(message: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        r.raise_for_status()


async def fetch_page_text() -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        await page.goto(URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(4000)
        text = await page.inner_text("body")
        await browser.close()
    return text


def read_state() -> str:
    try:
        return open(STATE_FILE).read().strip()
    except FileNotFoundError:
        return ""


def write_state(h: str) -> None:
    with open(STATE_FILE, "w") as f:
        f.write(h)


# Exact phrase shown by the page when no slots are available
NO_SLOT_PHRASE = "aucun créneau correspondant à votre recherche n'a été trouvé"


def has_no_slots(text: str) -> bool:
    return NO_SLOT_PHRASE in text.lower()


async def main() -> None:
    print("Fetching page...")
    try:
        text = await fetch_page_text()
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        return

    no_slots = has_no_slots(text)
    print(f"Slots available: {not no_slots}")

    # We only care about slot availability — ignore other page changes
    # State stores "NO_SLOTS" or "SLOTS_AVAILABLE"
    current_state = "NO_SLOTS" if no_slots else "SLOTS_AVAILABLE"
    previous_state = read_state()

    print(f"prev={previous_state or 'none'} curr={current_state}")

    if current_state == previous_state:
        print("No change in slot availability.")
        return

    write_state(current_state)

    if current_state == "SLOTS_AVAILABLE":
        await send_telegram(
            "🟢 <b>Créneaux disponibles !</b>\n\n"
            "Des créneaux sont disponibles pour le <b>renouvellement de récépissé</b>.\n\n"
            "⚡ Réservez vite, ça part rapidement !\n\n"
            f"👉 <a href='{URL}'>Prendre rendez-vous</a>"
        )
        print("Slots appeared — notification sent!")
    else:
        # Slots disappeared (were available, now gone) — silent, no notification needed
        print("Slots are gone again. Monitoring continues.")


if __name__ == "__main__":
    asyncio.run(main())
