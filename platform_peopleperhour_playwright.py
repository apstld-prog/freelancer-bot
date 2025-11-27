import httpx
import asyncio
import re
from typing import Dict, List, Optional

# Proxy backend για να μη χτυπάς απευθείας το PPH με τον worker.
PROXYBASE = "https://pph-proxy-chris.fly.dev?url="
BASE = "https://www.peopleperhour.com"

# ------------------ helpers για HTTP & parsing ------------------ #

async def fetch(url: str, timeout: float = 20.0) -> Optional[str]:
    """
    Fetch μέσω Fly proxy (Playwright backend).
    Επιστρέφει full HTML αν όλα πάνε καλά, αλλιώς None.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as c:
            r = await c.get(PROXYBASE + url)
            if r.status_code == 200 and r.text:
                return r.text
    except Exception:
        return None
    return None


def clean(text: str) -> str:
    return (text or "").replace("\r", " ").replace("\n", " ").strip()


def extract_budget(html: str):
    """
    Εξάγει min/max price και currency από HTML.
    Πιάνει patterns όπως: "£100 - £200", "$150", "€50 - €80" κλπ.
    """
    if not html:
        return None, None, None

    pat = re.compile(r"([$\£\€])\s*([\d,]+(?:\.\d+)?)")
    matches = pat.findall(html)
    if not matches:
        return None, None, None

    vals = []
    currency = None
    for sym, num in matches:
        try:
            vals.append(float(num.replace(",", "")))
        except Exception:
            continue
        if not currency:
            if sym == "$":
                currency = "USD"
            elif sym == "£":
                currency = "GBP"
            elif sym == "€":
                currency = "EUR"

    if not vals:
        return None, None, currency

    return min(vals), max(vals), currency


def extract_description_html(html: str) -> str:
    """
    Παίρνει το κείμενο από το job description block.
    """
    if not html:
        return ""
    m = re.search(r'<div[^>]+class="job-description"[^>]*>(.+?)</div>', html, re.S)
    if m:
        return clean(m.group(1))
    return ""


def extract_title(html: str) -> str:
    """
    Εξάγει τον τίτλο της αγγελίας.
    """
    if not html:
        return ""
    m = re.search(r"<h1[^>]*>(.+?)</h1>", html, re.S)
    return clean(m.group(1)) if m else ""


def extract_date(html: str) -> Optional[int]:
    """
    Προσπαθεί να βρει epoch timestamp από data-published="1698765432" κλπ.
    """
    if not html:
        return None
    m = re.search(r'data-published="(\d+)"', html)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


async def scrape_job(url: str) -> Dict:
    """
    Κατεβάζει μια job page και επιστρέφει normalized dict.
    """
    html = await fetch(url)
    if not html:
        bmin = bmax = None
        cur = None
        desc = ""
        title = ""
        ts = None
    else:
        title = extract_title(html)
        desc = extract_description_html(html)
        bmin, bmax, cur = extract_budget(html)
        ts = extract_date(html)

    return {
        "title": title or "",
        "description": desc or "",
        "description_html": desc or "",
        "budget_min": bmin,
        "budget_max": bmax,
        "original_currency": cur,
        "timestamp": ts,
        "time_submitted": ts,
        "original_url": url,
        "proposal_url": url,
        "source": "peopleperhour",
        "matched_keyword": None,
    }


def extract_job_links(html: str) -> List[str]:
    """
    Βγάζει τα URLs αγγελιών από τη σελίδα freelance-jobs HTML.
    Ψάχνει links τύπου /freelance-jobs/... ή /job/...
    """
    if not html:
        return []

    links: List[str] = []

    # 1) /freelance-jobs/... links
    for m in re.findall(r'href="(/freelance-jobs/[^"#?]+)"', html):
        links.append(BASE + m)

    # 2) /job/... links (αν υπάρχουν)
    for m in re.findall(r'href="(/job/[^"#?]+)"', html):
        links.append(BASE + m)

    # αφαίρεση διπλών, διατήρηση σειράς
    seen = set()
    out: List[str] = []
    for url in links:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)

    # μικρό όριο για να μη γινόμαστε επιθετικοί
    return out[:10]


async def search_urls_html(keyword: str) -> List[str]:
    """
    HTML search page per keyword (μέσω proxy).
    Παίρνει URLs αγγελιών για ένα keyword από τη σελίδα αποτελεσμάτων.
    """
    kw = (keyword or "").strip()
    if not kw:
        return []

    search_url = f"{BASE}/freelance-jobs?q={kw}"
    html = await fetch(search_url)
    if not html:
        return []

    return extract_job_links(html)


async def get_items_async(keywords: List[str]) -> List[Dict]:
    """
    Κεντρική async ρουτίνα:
    - για κάθε keyword διαβάζει HTML search results,
    - scrape των πρώτων N job URLs,
    - φτιάχνει unified dict ανά job.
    """
    out: List[Dict] = []
    seen_urls: set = set()

    for kw in keywords or []:
        kw = kw.strip()
        if not kw:
            continue

        links = await search_urls_html(kw)
        for url in links:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            data = await scrape_job(url)
            data["matched_keyword"] = kw.lower()
            out.append(data)

    return out


def get_items(keywords: List[str]) -> List[Dict]:
    """
    Sync wrapper για τον unified worker (όπως στα άλλα platform_*).
    """
    return asyncio.run(get_items_async(keywords or []))
