# test_pph_scraper.py
# Quick probe for PeoplePerHour HTML layout to debug parser.
# Prints counts for multiple patterns + shows 2 sample matches from each.

import httpx, re, sys

KW = sys.argv[1] if len(sys.argv) > 1 else "logo"
URL = f"https://www.peopleperhour.com/freelance-jobs?q={KW}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobBot/Probe",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.peopleperhour.com/",
}

def fetch(url: str) -> str:
    r = httpx.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
    print(f"[HTTP] {r.status_code} {url} (len={len(r.text)})")
    r.raise_for_status()
    return r.text

def show_samples(name: str, items, max_show=2):
    print(f"\n=== {name}: {len(items)} matches ===")
    for i, it in enumerate(items[:max_show]):
        print(f"\n--- {name} sample #{i+1} ---")
        print(it[:1200])

def main():
    html = fetch(URL)

    # 1) Direct job links: /job/<id>-...
    re_job_a = re.compile(r'(<a[^>]+href="/job/\d+[^"]*"[^>]*>.*?</a>)', re.I|re.S)
    m_job_a = re_job_a.findall(html)
    show_samples("A_TAG_JOB", m_job_a)

    # 2) Any href containing /job/<id> (wider)
    re_job_href = re.compile(r'href="(/job/\d+[^"]*)"', re.I)
    m_job_href = re_job_href.findall(html)
    print(f"\n=== HREF_JOB (href only): {len(m_job_href)} matches ===")
    for i, h in enumerate(m_job_href[:5]):
        print(f"href[{i+1}] = {h}")

    # 3) Card/article blocks that likely contain jobs
    # Try common wrappers PPH uses: <article ... job ...>, <li ... job ...>, <div ... card ...>
    re_article_job = re.compile(r'(<article[^>]+class="[^"]*(?:job|project)[^"]*"[^>]*>.*?</article>)', re.I|re.S)
    m_article_job = re_article_job.findall(html)
    show_samples("ARTICLE_JOB", m_article_job)

    re_li_job = re.compile(r'(<li[^>]+class="[^"]*(?:job|project)[^"]*"[^>]*>.*?</li>)', re.I|re.S)
    m_li_job = re_li_job.findall(html)
    show_samples("LI_JOB", m_li_job)

    re_div_card = re.compile(r'(<div[^>]+class="[^"]*(?:job|project|card)[^"]*"[^>]*>.*?</div>)', re.I|re.S)
    m_div_card = re_div_card.findall(html)
    show_samples("DIV_CARD", m_div_card)

    # 4) data-* ids e.g. data-job-id="123456" / data-project-id="123456"
    re_data_id = re.compile(r'(data-(?:job|project)-id="(\d+)")', re.I)
    m_data_id = re_data_id.findall(html)
    print(f"\n=== DATA_IDS: {len(m_data_id)} matches ===")
    for i, (_full, jid) in enumerate(m_data_id[:10]):
        print(f"data-id[{i+1}] = {jid}  -> https://www.peopleperhour.com/job/{jid}")

    # 5) Titles
    re_title = re.compile(r'(<h[12-4][^>]*>.*?</h[12-4]>)', re.I|re.S)
    m_titles = re_title.findall(html)
    show_samples("HEADINGS", m_titles)

    # 6) Save snapshot to file for deeper offline inspection
    with open("pph_probe.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("\n[OK] Saved HTML snapshot to pph_probe.html")

if __name__ == "__main__":
    main()
