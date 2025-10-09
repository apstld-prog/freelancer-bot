
import hashlib
import re
from typing import Dict

def normalize_title(t: str) -> str:
    t = (t or '').strip().lower()
    t = re.sub(r'\s+', ' ', t)
    return t

def make_key(item: Dict) -> str:
    base = f"{normalize_title(item.get('title'))}|{item.get('source','')}|{item.get('url','')}"
    return hashlib.sha1(base.encode('utf-8')).hexdigest()

def prefer_affiliate(a: Dict, b: Dict) -> Dict:
    a_aff = a.get('affiliate', False)
    b_aff = b.get('affiliate', False)
    if a_aff and not b_aff:
        return a
    if b_aff and not a_aff:
        return b
    return a
