def make_key(job):
    # Υποστήριξη και για παλιά και για νέα πεδία
    platform = job.get("platform") or job.get("source") or "unknown"
    url = job.get("url") or job.get("original_url") or job.get("proposal_url") or ""
    title = job.get("title", "")
    return f"{platform}::{title[:60]}::{url}"


def match_keywords(job, keywords):
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(k.lower() in text for k in keywords)
