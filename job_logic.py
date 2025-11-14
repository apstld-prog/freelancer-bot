def make_key(job):
    return f"{job['platform']}::{job['title'][:60]}::{job.get('url', '')}"

def match_keywords(job, keywords):
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(k.lower() in text for k in keywords)
