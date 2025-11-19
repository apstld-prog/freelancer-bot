import httpx
from bs4 import BeautifulSoup
import re

def _clean(s: str) -> str:
    return (s or "").strip()

def _extract_budget(text):
    if not text:
        return None, None, None
    txt = text.replace(",", "").strip()
    if "£" in txt:
        cur = "GBP"
    elif "€" in txt:
        cur = "EUR"
    elif "$" in txt:
        cur = "USD"
    else:
        cur = None
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

def _parse_cards(html: str, kw: str):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    cards = []
    for li in soup.find_all("li"):
        classes = " ".join(li.get("class") or [])
        if "list__item" in classes:
            cards.append(li)

    for card in cards:
        job_link = None
        for a in card.find_all("a", href=True):
            href = a["href"]
            if "/freelance-jobs/" in href:
                job_link = a
                break

        if not job_link:
            continue

        title = _clean(job_link.get_text())
        href = job_link["href"]
        if href.startswith("/"):
            href = "https://www.peopleperhour.com" + href

        p_tags = card.find_all("p")
        description = ""
        if p_tags:
            description = _clean(p_tags[-1].get_text())

        hay = f"{title} {description}".lower()
        if kw and kw.lower() not in hay:
            continue

        price_text = ""
        for div in card.find_all("div"):
            classes = " ".join(div.get("class") or [])
            if "card__price" in classes:
                price_text = _clean(div.get_text())
                break

        bmin, bmax, cur = _extract_budget(price_text)

        items.append({
            "source": "peopleperhour",
            "matched_keyword": kw,
            "title": title,
            "description": description,
            "external_id": href,
            "url": href,
            "proposal_url": href,
            "original_url": href,
            "budget_min": bmin,
            "budget_max": bmax,
            "original_currency": cur,
            "currency": cur,
            "time_submitted": None,
            "affiliate": False,
        })

    return items

def get_items(keywords):
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
        except Exception:
            continue

        batch = _parse_cards(resp.text, kw)
        all_items.extend(batch)

    return all_items
