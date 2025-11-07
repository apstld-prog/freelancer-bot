# platform_kariera.py
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}

def fetch(listing_url: str):
    """
    Αν το KARIERA_RSS που δίνεις είναι στην πραγματικότητα listing σελίδα HTML,
    π.χ. https://www.kariera.gr/jobs , κάνουμε basic HTML scrape από τα job-cards.
    Αν έχεις πραγματικό RSS, μπορείς να αλλάξεις αυτόν τον parser με XML parse.
    """
    out = []
    if not listing_url:
        return out
    resp = requests.get(listing_url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Συνήθη CSS selectors (ενδέχεται να θες προσαρμογή αν αλλάξει markup)
    cards = soup.select("[data-test='job-result'], .job-card, article")
    for c in cards[:50]:  # safeguard
        a = c.find("a", href=True)
        if not a:
            continue
        url = a["href"]
        if url.startswith("/"):
            # απόλυτο URL
            url = "https://www.kariera.gr" + url
        title = (a.get_text(strip=True) or "").strip()
        if not title:
            # δοκίμασε header
            h = c.find(["h2", "h3"])
            if h:
                title = h.get_text(strip=True)
        desc_tag = c.find(["p", "div"], class_=lambda x: x and "description" in x.lower()) or c.find("p")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        if not title or not url:
            continue
        out.append({
            "title": title,
            "url": url,
            "description": desc,
            "source": "Kariera",
            "platform": "kariera",
        })
    return out
