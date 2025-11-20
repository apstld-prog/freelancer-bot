# worker.py
import platform_peopleperhour as p
import platform_free as f if False else None  # placeholder

def fetch_all(keywords_query):
    keywords = [keywords_query] if isinstance(keywords_query,str) else keywords_query
    items=[]
    try:
        items.extend(p.get_items(keywords))
    except Exception as e:
        print("[Worker] PPH error:", e)
    return items

def run_pipeline(keywords):
    return fetch_all(keywords)
