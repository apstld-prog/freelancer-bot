import hashlib

def make_key(job):
    data = f"{job.get('title','')}-{job.get('platform','')}"
    return hashlib.sha1(data.encode()).hexdigest()

def match_keywords(job, keywords):
    text_content = f"{job.get('title','')} {job.get('description','')}".lower()
    return any(k.lower() in text_content for k in keywords)
