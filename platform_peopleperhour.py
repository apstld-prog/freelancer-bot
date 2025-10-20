import requests
from bs4 import BeautifulSoup
import re
import html
from urllib.parse import quote

PROXY_URL = "https://pph-proxy-service.onrender.com"
API_KEY = "1211"

CURRENCY_MAP = {
    "£": 1.22,  # GBP -> USD
    "€": 1.08,  # EUR -> USD
    "$": 1.0,   # USD
}

def convert_to_usd(amount_str: str):
    """Μετατροπή ποσού σε USD αν εντοπιστεί νόμισμα."""
    for symbol, rate in CURRENCY_MAP.items():
        if symbol in amount_str:
            try:
                num = float(re.findall(r"[\d.]+", amount_str.replace(",", ""))[0])
                usd = round(num * rate, 2)
                return f"{amount_str} (≈ {usd} USD)"
            except Exception:
                return amount_str
    return amount_str

def get_items(keywords):
    """Ανάγνωση αγγελιών από το proxy PPH"""
    all_items = []

    for kw in keywords:
        try:
            print(f"[PPH] Αναζήτηση για '{kw}' μέσω proxy...")
            url = f"{PROXY_URL}?keyword={quote(kw)}&key={API_KEY}"
            res = requests.get(url, timeout=30)
            res.raise_for_status()

            data = res.json()
            html_content = data.get("html") or ""
            soup = BeautifulSoup(html_content, "html.parser")

            jobs = soup.select("section, div.job, li.job") or soup.find_all("a", href=re.compile("/freelance-jobs/"))
            print(f"[PPH] Εντοπίστηκαν {len(jobs)} αγγελίες αρχικά")

            for job in jobs:
                title_el = job.find("h2") or job.find("h3") or job.find("a")
                title = title_el.get_text(strip=True) if title_el else "Untitled"

                link = title_el["href"] if title_el and title_el.has_attr("href") else ""
                if link and not link.startswith("http"):
                    link = f"https://www.peopleperhour.com{link}"

                desc_el = job.find("p") or job.find("div", class_=re.compile("description|summary"))
                desc = desc_el.get_text(" ", strip=True) if desc_el else ""

                budget_el = job.find(text=re.compile(r"[$€£]\s*\d"))
                budget = budget_el.strip() if budget_el else "N/A"
                budget = convert_to_usd(budget)

                # Match λέξης-κλειδί σε τίτλο + περιγραφή
                if kw.lower() not in (title + " " + desc).lower():
                    continue

                all_items.append({
                    "title": html.unescape(title),
                    "desc": html.unescape(desc),
                    "link": link,
                    "budget": budget,
                    "source": "PeoplePerHour",
                })

        except Exception as e:
            print(f"[PPH] Σφάλμα για '{kw}': {e}")

    print(f"[PPH] Συνολικά {len(all_items)} αγγελίες μετά το φίλτρο")
    return all_items
