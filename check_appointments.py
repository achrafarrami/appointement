import asyncio
import os
import time
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
HEARTBEAT_FILE = "last_heartbeat.txt"
ERROR_FILE = "last_error.txt"

# How often to send the "still alive, no slots" heartbeat
HEARTBEAT_HOURS = 6

# How often to re-send an error alert if the issue continues
ERROR_NOTIFY_HOURS = 1

# Phrase shown by the page when no slots are available
NO_SLOT_PHRASE = "aucun créneau correspondant à votre recherche n'a été trouvé"

# Phrase that should ALWAYS appear on the page if it loaded correctly.
# If missing → the page didn't load correctly (blocked, captcha, layout change, etc.)
PAGE_ANCHOR_PHRASE = "renouvellement de récépissés"


# ---------- Telegram ----------

async def send_telegram(message: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        r.raise_for_status()


# ---------- Page fetch ----------

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


# ---------- State helpers ----------

def _read(path: str) -> str:
    try:
        return open(path).read().strip()
    except FileNotFoundError:
        return ""


def _write(path: str, value: str) -> None:
    with open(path, "w") as f:
        f.write(value)


def read_state() -> str:
    return _read(STATE_FILE)


def write_state(v: str) -> None:
    _write(STATE_FILE, v)


def read_last_ts(path: str) -> float:
    try:
        return float(_read(path))
    except ValueError:
        return 0.0


def write_ts(path: str) -> None:
    _write(path, str(time.time()))


def hours_since(path: str) -> float:
    return (time.time() - read_last_ts(path)) / 3600


def format_hours(h: float) -> str:
    if h >= 1:
        return f"{int(round(h))}h"
    return f"{int(round(h * 60))}min"


# ---------- Page analysis ----------

def has_no_slots(text: str) -> bool:
    return NO_SLOT_PHRASE in text.lower()


def page_loaded_correctly(text: str) -> bool:
    return PAGE_ANCHOR_PHRASE in text.lower()


# ---------- Error notification (rate-limited) ----------

async def notify_error(reason: str) -> None:
    if hours_since(ERROR_FILE) < ERROR_NOTIFY_HOURS:
        print(f"Error suppressed (rate-limited): {reason}")
        return
    await send_telegram(
        "⚠️ <b>Problème détecté</b>\n\n"
        f"Le bot n'arrive pas à surveiller la page correctement.\n\n"
        f"<b>Raison :</b> {reason}\n\n"
        f"Vérifie manuellement et le serveur si besoin.\n"
        f"👉 <a href='{URL}'>Ouvrir la page</a>"
    )
    write_ts(ERROR_FILE)
    print(f"Error notification sent: {reason}")


# ---------- Main ----------

async def main() -> None:
    print("Fetching page...")
    try:
        text = await fetch_page_text()
    except Exception as e:
        print(f"Failed to fetch page: {e}")
        await notify_error(f"Impossible de charger la page : {type(e).__name__}")
        return

    # Sanity check — did the page load correctly?
    if not page_loaded_correctly(text):
        snippet = text[:200].replace("\n", " ")
        print(f"Unexpected page content. First 200 chars: {snippet}")
        await notify_error(
            "La page ne contient pas le contenu attendu. "
            "Peut-être un blocage, captcha, ou changement du site."
        )
        return

    # Page loaded fine → clear any previous error timer so next error notifies immediately
    if read_last_ts(ERROR_FILE) > 0:
        _write(ERROR_FILE, "0")

    no_slots = has_no_slots(text)
    print(f"Slots available: {not no_slots}")

    current_state = "NO_SLOTS" if no_slots else "SLOTS_AVAILABLE"
    previous_state = read_state()
    print(f"prev={previous_state or 'none'} curr={current_state}")

    # --- Case 1: nothing changed ---
    if current_state == previous_state:
        print("No change in slot availability.")
        if current_state == "NO_SLOTS" and hours_since(HEARTBEAT_FILE) >= HEARTBEAT_HOURS:
            await send_telegram(
                "🔴 <b>Toujours aucun créneau disponible</b>\n\n"
                "Le bot fonctionne bien et surveille la page.\n"
                f"📅 Prochain rapport dans {format_hours(HEARTBEAT_HOURS)}\n\n"
                f"👉 <a href='{URL}'>Vérifier manuellement</a>"
            )
            write_ts(HEARTBEAT_FILE)
            print("Heartbeat sent.")
        return

    # --- Case 2: state changed ---
    write_state(current_state)
    write_ts(HEARTBEAT_FILE)

    if current_state == "SLOTS_AVAILABLE":
        await send_telegram(
            "🟢 <b>Créneaux disponibles !</b>\n\n"
            "Des créneaux sont disponibles pour le <b>renouvellement de récépissé</b>.\n\n"
            "⚡ Réservez vite, ça part rapidement !\n\n"
            f"👉 <a href='{URL}'>Prendre rendez-vous</a>"
        )
        print("Slots appeared — notification sent!")
    else:
        await send_telegram(
            "🔴 <b>Les créneaux sont repartis</b>\n\n"
            "Il n'y a plus de créneaux disponibles. Le bot continue de surveiller.\n\n"
            f"👉 <a href='{URL}'>Vérifier quand même</a>"
        )
        print("Slots gone — notification sent.")


if __name__ == "__main__":
    asyncio.run(main())
