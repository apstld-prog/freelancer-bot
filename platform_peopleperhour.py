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

            # Πιο ακριβής επιλογή για job links
            job_links = soup.find_all("a", href=re.compile(r"^/freelance-jobs/"))
            print(f"[PPH] Εντοπίστηκαν {len(job_links)} αγγελίες αρχικά")

            for a in job_links:
                title = a.get_text(strip=True)
                link = a["href"]
                if not link.startswith("http"):
                    link = f"https://www.peopleperhour.com{link}"

                # Αναζήτηση περιγραφής ή budget κοντά στο link
                parent = a.find_parent(["div", "section", "li"])
                desc_el = parent.find("p") if parent else None
                desc = desc_el.get_text(" ", strip=True) if desc_el else ""

                budget_el = parent.find(text=re.compile(r"[$€£]\s*\d")) if parent else None
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
