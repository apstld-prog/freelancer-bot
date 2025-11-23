
# platform_skywalker.py — full file with fetch() + parse_atom() + get_items()
import html
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict

# ------------- ORIGINAL FUNCTIONS (selftest compatibility) -------------

def parse_atom(xml_text: str) -> List[Dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    ns = {"a": "http://www.w3.org/2005/Atom"}

    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.get("href") if link_el is not None else ""

        work_type = entry.findtext("workType", default="", namespaces={})
        publish = entry.findtext("publishDate", default="", namespaces={})

        emps = []
        emp_root = entry.find("employmentTypes")
        if emp_root is not None:
            for e in emp_root.findall("employmentType"):
                if e.text:
                    emps.append(e.text.strip())

        desc_parts = []
        if work_type:
            desc_parts.append(work_type)
        desc_parts.extend(emps)
        description = "\n".join(desc_parts)

        item = {
            "external_id": link or title,
            "title": title,
            "description": description,
            "url": link,
            "proposal_url": link,
            "original_url": link,
            "budget_min": None,
            "budget_max": None,
            "currency": "EUR",
            "original_currency": "EUR",
            "source": "Skywalker",
            "time_submitted": None,
            "affiliate": False,
        }

        if publish:
            import datetime
            try:
                dt = datetime.datetime.fromisoformat(publish.replace("Z","+00:00"))
                item["time_submitted"] = int(dt.timestamp())
            except:
                pass

        items.append(item)

    return items

def fetch(feed_url: str, timeout: int = 10) -> List[Dict]:
    try:
        resp = requests.get(feed_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_atom(resp.text)
    except Exception:
        return []


# ------------- NEW FUNCTION FOR WORKER (uses fetch internally) -------------

RSS_URL = "https://www.skywalker.gr/jobs/feed"

def get_items(keywords: List[str]) -> List[Dict]:
    raw_items = fetch(RSS_URL)
    out = []

    for it in raw_items:
        title = it.get("title","")
        desc = it.get("description","")

        for kw in keywords:
            if kw.lower() in title.lower() or kw.lower() in desc.lower():
                new = dict(it)
                new["matched_keyword"] = kw
                out.append(new)
                break

    return out
