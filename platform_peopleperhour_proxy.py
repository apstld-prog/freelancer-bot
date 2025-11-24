# platform_peopleperhour_proxy.py — FINAL CLEAN VERSION (PPH via proxy /jobs)
import httpx
from bs4 import BeautifulSoup

PROXY_URL = "https://pph-proxy.onrender.com/jobs"


def fetch_raw_html():
    """
    Fetch raw HTML directly from PPH proxy.
    The proxy returns HTML from PeoplePerHour.
    """
    try:
        r = httpx.get(PROXY_URL, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""


def parse_html(html: str):
    """
    Extract PPH job tiles from HTML snapshot.
    This matches the structure in the file you sent.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Each job container (from your HTML file)
    for div in soup.select("div.jobs--item"):

        title_el = div.select_one("h3.jobs--item__title")
        desc_el = div.select_one("p.jobs--item__description")
        link_el = div.select_one("a.jobs--item__link")
        budget_el = div.select_one(".jobs--item__budget")
        time_el = div.select_one(".jobs--item__posted")

        title = title_el.get_text(strip=True) if title_el else ""
        desc = desc_el.get_text(strip=True) if desc_el else ""
        link = link_el["href"] if link_el and link_el.has_attr("href") else ""

        # Normalize link (PeoplePerHour uses /something)
        if link and link.startswith("/"):
            link = "https://www.peopleperhour.com" + link

        # Budget extraction
        budget_min = None
        budget_max = None
        currency = None

        if budget_el:
            txt = budget_el.get_text(" ", strip=True)
            # Examples: "€50", "€100 - €200"
            parts = txt.replace("–", "-").split("-")
            if len(parts) == 2:
                p1 = parts[0].strip()
                p2 = parts[1].strip()
                currency = p1[0] if p1 else None
                try:
                    budget_min = float(p1[1:].strip())
                    budget_max = float(p2[1:].strip())
                except:
                    pass
            else:
                # Single price
                p = txt.strip()
                if p:
                    currency = p[0]
                    try:
                        budget_min = float(p[1:])
                        budget_max = float(p[1:])
                    except:
                        pass

        # Timestamp (if available)
        posted = time_el.get_text(strip=True) if time_el else ""

        jobs.append({
            "source": "PPH",
            "title": title,
            "description": desc,
            "original_url": link,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "original_currency": currency,
            "posted": posted,
        })

    return jobs


def get_items(keywords):
    """
    Unified worker access point.
    """
    html = fetch_raw_html()
    if not html:
        return []

    data = parse_html(html)
    out = []

    for it in data:
        title = it.get("title", "") or ""
        desc = it.get("description", "") or ""

        hay = (title + " " + desc).lower()

        for kw in keywords:
            k = kw.lower()
            if k in hay:
                x = it.copy()
                x["matched_keyword"] = kw
                out.append(x)
                break

    return out
