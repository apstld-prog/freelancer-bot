import re
import hashlib

def match_keywords(item: dict, keywords: list[str]) -> bool:
    """
    Returns True if any keyword is found in the title or description of the job.
    """
    text_parts = []
    for key in ("title", "description", "summary", "text"):
        v = item.get(key)
        if isinstance(v, str):
            text_parts.append(v.lower())
    if not text_parts:
        return False

    full_text = " ".join(text_parts)
    for kw in keywords:
        if not kw:
            continue
        pattern = re.escape(kw.strip().lower())
        if re.search(pattern, full_text):
            return True
    return False


def make_key(item: dict) -> str:
    """
    Creates a unique hash key for a job item (used for deduplication).
    """
    base = ""
    for key in ("id", "url", "link", "title"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            base = v.strip()
            break
    if not base:
        base = str(item)
    return hashlib.md5(base.encode("utf-8")).hexdigest()
