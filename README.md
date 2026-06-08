# Appointment Checker — Prefecture RDV Monitor

Automatically monitors the French prefecture appointment page and sends a **Telegram notification** the moment new slots become available. Runs every 5 minutes in the cloud via GitHub Actions — no PC required.

---

## How it works

1. GitHub Actions triggers the script every 5 minutes
2. A headless Chromium browser loads the appointment page (JavaScript fully rendered)
3. The page text is hashed and compared to the previous run's hash stored in `state.txt`
4. If the page changed:
   - Slots detected → sends a **green alert** with a direct booking link
   - Page changed but no obvious slots → sends a **neutral alert** to go check manually
5. The new hash is committed back to the repo automatically

---

## Stack

| Tool | Role |
|---|---|
| Python 3.11 | Main script |
| Playwright | Headless browser (renders JS) |
| httpx | Telegram API calls |
| GitHub Actions | Cloud scheduler (free, no server needed) |
| Telegram Bot | Push notifications |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/achrafarrami/appointement.git
cd appointement
```

### 2. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret name | Value |
|---|---|
| `TELEGRAM_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram user ID from @userinfobot |

### 3. Enable GitHub Actions

Go to the **Actions** tab in your repo and enable workflows if prompted.

### 4. Trigger a first run manually

Actions → **Check Appointments** → **Run workflow**

The first run saves the initial state without notifying (unless slots are already available).

---

## Files

```
appointement/
├── check_appointments.py       # Main monitoring script
├── requirements.txt            # Python dependencies
├── state.txt                   # Stores hash of last seen page (auto-updated)
└── .github/
    └── workflows/
        └── check.yml           # GitHub Actions workflow (runs every 5 min)
```

---

## Monitored page

```
https://rdv.anct.gouv.fr/prendre_rdv
  ?motif_name_with_location_type=renouvellement_de_recepisses_arrives_a_echeance_-public_office
  &public_link_organisation_id=2458
```

**Appointment type:** Renouvellement de récépissés arrivés à échéance

---

## Notifications

| Message | Meaning |
|---|---|
| 🟢 Nouveaux créneaux disponibles ! | Page changed + slots detected → book now |
| 🔄 Page modifiée | Page changed but no clear slot detected → check manually |

---

## Local run (optional)

```bash
pip install -r requirements.txt
playwright install --with-deps chromium

export TELEGRAM_TOKEN=your_token
export TELEGRAM_CHAT_ID=your_chat_id

python check_appointments.py
```

---

## Notes

- GitHub Actions scheduled workflows run on UTC time
- Minimum interval is 5 minutes (GitHub limitation)
- GitHub may delay scheduled runs by a few minutes during high load
- Scheduled workflows are auto-disabled after 60 days of repo inactivity — the automatic `state.txt` commits prevent this
