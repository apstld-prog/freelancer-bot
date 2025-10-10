# platform_peopleperhour.py
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}

BASE = "https://www.peopleperhour.com"
SEARCH = BASE + "/freelance-jobs"

def fetch(query: str | None = None, max_items: int = 50):
    """
    Αν δεν στείλεις query -> επιστρέφει τα πιο πρόσφατα jobs από την κεντρική αναζήτηση.
    Επιστρέφει list[dict] με πεδία: title, url, description, source, platform, budget_min, budget_max (όπου βρεθεί).
    """
    out = []
    params = {}
    if query:
        params["q"] = query
    url = SEARCH + ("?" + urlencode(params) if params else "")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Κάρτες εργασιών — οι selectors αλλάζουν, οπότε έχουμε fallback αλυσίδα
    cards = soup.select("[data-at='job-card'], .job, article, li")
    seen = set()
    for c in cards:
        a = c.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = BASE + href
        title = a.get_text(strip=True)
        if (title, href) in seen:
            continue
        seen.add((title, href))

        # Περιγραφή / budget (best effort)
        desc_el = c.find("p") or c.find("div", class_=lambda x: x and "desc" in x.lower()) or c
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        budget_min = budget_max = None
        budgel = c.find(string=lambda s: s and ("$" in s or "€" in s or "£" in s))
        if budgel:
            # απλή εξαγωγή ποσών
            import re
            nums = [n.replace(",", "") for n in re.findall(r"(\d+[.,]?\d*)", budgel)]
            if len(nums) == 1:
                budget_min = float(nums[0])
            elif len(nums) >= 2:
                try:
                    budget_min = float(nums[0]); budget_max = float(nums[1])
                except:
                    pass

        out.append({
            "title": title,
            "url": href,
            "description": desc,
            "source": "PeoplePerHour",
            "platform": "peopleperhour",
            "budget_min": budget_min,
            "budget_max": budget_max,
        })
        if len(out) >= max_items:
            break

    return out
