import httpx
from bs4 import BeautifulSoup
import re

# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def _clean(s: str) -> str:
    return (s or "").strip()


def _extract_budget(text):
    """
    Παίρνει κάτι όπως:
      "$40"
      "£50 - £200"
      "€120"
      "$37/hr"
    και επιστρέφει:
      (min, max, currency)
    """
    if not text:
        return None, None, None

    txt = text.replace(",", "").strip()

    # currency detection
    if "£" in txt:
        cur = "GBP"
    elif "€" in txt:
        cur = "EUR"
    elif "$" in txt:
        cur = "USD"
    else:
        cur = None

    # βγάζουμε σύμβολα και /hr κτλ.
    cleaned = (
        txt.replace("£", "")
        .replace("€", "")
        .replace("$", "")
        .replace("/hr", "")
        .replace("/HR", "")
    )

    numbers = re.findall(r"\d+(?:\.\d+)?", cleaned)
    if not numbers:
        return None, None, cur

    nums = list(map(float, numbers))

    if len(nums) == 1:
        return nums[0], nums[0], cur
    else:
        return nums[0], nums[-1], cur


# ---------------------------------------------------------
# HTML parsing για μία σελίδα
# ---------------------------------------------------------


def _parse_cards(html: str, kw: str):
    """
    Διαβάζει το HTML της:
      https://www.peopleperhour.com/freelance-jobs?q=KEYWORD

    και γυρνάει λίστα από items με:
      title, description, original_url, budget_min, budget_max,
      original_currency, matched_keyword, source="peopleperhour"
    """
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Τα <li> έχουν class σαν "list__item⤍List⤚2ytmm"
    cards = []
    for li in soup.find_all("li"):
        classes = " ".join(li.get("class") or [])
        if "list__item" in classes:
            cards.append(li)

    for card in cards:
        # ------------------------- URL & Title -------------------------
        job_link = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            # πραγματικά job links
            if "/freelance-jobs/" in href:
                job_link = a
                break

        if not job_link:
            continue

        title = _clean(job_link.get_text())
        href = job_link["href"]
        if href.startswith("/"):
            href = "https://www.peopleperhour.com" + href

        # ------------------------- Description -------------------------
        # Συνήθως το τελευταίο <p> μέσα στην κάρτα είναι η περιγραφή
        p_tags = card.find_all("p")
        description = ""
        if p_tags:
            description = _clean(p_tags[-1].get_text())

        # Strict keyword filter όπως στο Freelancer:
        # κρατάμε μόνο αν το kw υπάρχει σε title+description
        hay = f"{title} {description}".lower()
        if kw and kw.lower() not in hay:
            continue

        # ------------------------- Budget / Price -------------------------
        price_text = ""
        for div in card.find_all("div"):
            classes = " ".join(div.get("class") or [])
            if "card__price" in classes:
                price_text = _clean(div.get_text())
                break

        bmin, bmax, cur = _extract_budget(price_text)

        item = {
            "source": "peopleperhour",
            "matched_keyword": kw,
            "title": title,
            "description": description,
            "original_url": href,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": cur,
        }
        items.append(item)

    return items


# ---------------------------------------------------------
# Public API (όπως το καλεί ο worker)
# ---------------------------------------------------------


def get_items(keywords):
    """
    Scrapes PeoplePerHour search results:
      https://www.peopleperhour.com/freelance-jobs?q=KEYWORD

    και επιστρέφει items όπως ο freelancer scraper.
    """

    if not keywords:
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    all_items = []

    for kw in keywords:
        if not kw:
            continue

        url = f"https://www.peopleperhour.com/freelance-jobs?q={kw}"

        try:
            resp = httpx.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            # Σε αποτυχία, απλά συνεχίζουμε με επόμενο keyword
            print(f"[PPH] Error for kw={kw}: {e}")
            continue

        batch = _parse_cards(resp.text, kw)
        all_items.extend(batch)

    return all_items
