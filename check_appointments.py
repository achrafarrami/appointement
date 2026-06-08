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


NO_SLOT_PHRASES = [
    "aucun créneau",
    "aucun rendez-vous",
    "pas de créneau",
    "aucune disponibilité",
    "no slot available",
]


def slots_likely(text: str) -> bool:
    lower = text.lower()
    return not any(phrase in lower for phrase in NO_SLOT_PHRASES)


async def main() -> None:
    print("Fetching page...")
    try:
        text = await fetch_page_text()
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        return

    current = hashlib.sha256(text.encode()).hexdigest()
    previous = read_state()
    first_run = previous == ""

    print(f"prev={previous[:8] or 'none'} curr={current[:8]} changed={current != previous}")

    if not first_run and current == previous:
        print("No change detected.")
        return

    write_state(current)

    if first_run:
        if slots_likely(text):
            await send_telegram(
                "🟢 <b>Créneaux disponibles !</b>\n\n"
                "Des créneaux semblent disponibles dès maintenant.\n"
                f"👉 <a href='{URL}'>Réserver maintenant</a>"
            )
            print("Slots found on first run — notification sent.")
        else:
            print("First run complete, no slots yet. Monitoring started.")
        return

    if slots_likely(text):
        msg = (
            "🟢 <b>Nouveaux créneaux disponibles !</b>\n\n"
            "La page a changé et des créneaux semblent disponibles.\n"
            f"👉 <a href='{URL}'>Réserver maintenant</a>"
        )
    else:
        msg = (
            "🔄 <b>Page modifiée</b>\n\n"
            "La page a changé (mais aucun créneau évident détecté).\n"
            f"👉 <a href='{URL}'>Vérifier quand même</a>"
        )

    await send_telegram(msg)
    print("Notification sent.")


if __name__ == "__main__":
    asyncio.run(main())
