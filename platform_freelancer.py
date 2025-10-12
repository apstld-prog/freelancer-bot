import requests

def fetch_freelancer_jobs(keywords):
    jobs = []
    for kw in keywords:
        jobs.append({
            "platform": "freelancer",
            "title": f"Freelancer job: {kw}",
            "description": f"Example fetched job for keyword {kw}",
            "url": f"https://www.freelancer.com/search?q={kw}"
        })
    return jobs
