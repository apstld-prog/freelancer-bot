import httpx
import logging
import re
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

log = logging.getLogger("platform_peopleperhour")

BASE_URL = "https://www.peopleperhour.com/freelance-jobs"

# --- Βοηθητικό για μετατροπή σε USD (προσεγγιστικά rates)
CURRENCY_TO_USD = {
    "GBP": 1.28,
    "EUR": 1.09,
    "USD": 1.0
}

def convert_to_usd(amount, currency):
    try:
        rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
        return round(amount * rate, 2)
    except Exception:
        return amount

async def fetch_peopleperhour_jobs(keywords):
    """Πραγματικό scraping από το peopleperhour.com σαν αναζήτηση χρήστη."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for kw in keywords:
                url = f"{BASE_URL}?q={kw}"
                log.info(f"[PPH HTML] Fetching {url}")
                r = await client.get(url)
                if r.status_code != 200:
                    log.warning(f"[PPH HTML] Status {r.status_code} for {kw}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")

                # Κάθε job σε PeoplePerHour (2025 layout)
                job_cards = soup.select("li.project-list-item, section.job, article.job-tile, div.search-result")
                log.info(f"[PPH HTML] Found {len(job_cards)} listings for '{kw}'")

                for card in job_cards:
                    try:
                        # Τίτλος & link
                        a_tag = card.find("a", href=re.compile(r"^/job/"))
                        title = a_tag.text.strip() if a_tag else ""
                        link = a_tag["href"] if a_tag and a_tag.get("href") else ""
                        if link and not link.startswith("http"):
                            link = f"https://www.peopleperhour.com{link}"

                        # Περιγραφή
                        desc = card.get_text(separator=" ", strip=True)
                        desc = desc[:400]  # truncate για ασφάλεια

                        # Budget & νόμισμα
                        budget_text = ""
                        for elem in card.find_all(text=re.compile(r"[$€£]")):
                            budget_text = elem.strip()
                            break
                        amount = 0.0
                        currency = "USD"
                        if budget_text:
                            if "£" in budget_text:
                                currency = "GBP"
                            elif "€" in budget_text:
                                currency = "EUR"
                            elif "$" in budget_text:
                                currency = "USD"
                            m = re.findall(r"[\d\.]+", budget_text)
                            if m:
                                amount = float(m[0])

                        amount_usd = convert_to_usd(amount, currency)

                        # Χρονική σήμανση τώρα (δεν δίνει ημερομηνία η σελίδα)
                        ts = datetime.now(tz=timezone.utc).timestamp()

                        # Δημιουργία αντικειμένου
                        job = {
                            "title": title,
                            "description": desc,
                            "original_url": link,
                            "affiliate_url": link,
                            "budget_amount": amount,
                            "budget_currency": f"{currency} (~${amount_usd} USD)",
                            "source": "PeoplePerHour",
                            "timestamp": ts,
                        }

                        # Match keywords
                        text_to_match = (title + " " + desc).lower()
                        if any(k.lower() in text_to_match for k in keywords):
                            results.append(job)

                    except Exception as e:
                        log.warning(f"[PPH HTML parse error] {e}")

            # ✅ Μόνο αγγελίες έως 48 ωρών (timestamp τώρα)
            cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
            results = [j for j in results if datetime.fromtimestamp(j["timestamp"], tz=timezone.utc) >= cutoff]

    except Exception as e:
        log.warning(f"[PPH HTML error] {e}")

    log.info(f"[PPH total merged: {len(results)}]")
    return results
