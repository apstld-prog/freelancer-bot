import httpx
import re
import time
import traceback
from bs4 import BeautifulSoup

PPH_BASE = "https://www.peopleperhour.com/freelance-jobs?rss=1&page={}"

def fetch_page(page: int):
    url = PPH_BASE.format(page)
    try:
        print("="*70)
        print(f"🔎 FETCHING PAGE {page}: {url}")

        resp = httpx.get(url, timeout=15)
        print(f"HTTP STATUS: {resp.status_code}")

        if resp.status_code != 200:
            print("❌ FAILED TO FETCH PAGE")
            return None

        text = resp.text
        print(f"XML SIZE: {len(text)} bytes")
        print("PREVIEW (first 500 chars):")
        print(text[:500])
        return text

    except Exception as e:
        print("❌ Exception in fetch:")
        print(e)
        traceback.print_exc()
        return None


def parse_items(xml_text: str):
    try:
        soup = BeautifulSoup(xml_text, "xml")

        items = soup.find_all("item")
        print(f"📦 TOTAL ITEMS FOUND: {len(items)}")

        titles = []
        for it in items:
            t = it.find("title")
            if t:
                titles.append(t.text.strip())

        print("📝 TITLES:")
        for t in titles[:20]:
            print(" -", t)

        if len(titles) == 0:
            print("⚠️ WARNING: NO TITLES FOUND (RSS may be blocked).")

    except Exception as e:
        print("❌ PARSE ERROR:")
        print(e)
        traceback.print_exc()


def main():
    print("\n=============================================")
    print("🚀 LIVE DIAGNOSTIC — PPH RSS (10 pages)")
    print("=============================================\n")

    total_ok = 0
    total_fail = 0

    for page in range(1, 11):
        xml = fetch_page(page)
        if not xml:
            total_fail += 1
            continue

        total_ok += 1
        print("\n🔧 PARSING PAGE", page)
        parse_items(xml)

        print("\nSleeping 0.5s...\n")
        time.sleep(0.5)

    print("\n=============================================")
    print("🏁 FINAL SUMMARY")
    print("=============================================")
    print(f"✔️ SUCCESSFUL PAGES: {total_ok}")
    print(f"❌ FAILED PAGES: {total_fail}")
    print("Done.\n")


if __name__ == "__main__":
    main()
