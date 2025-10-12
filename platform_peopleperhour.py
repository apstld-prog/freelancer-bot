import requests

def fetch_peopleperhour_jobs(keywords):
    jobs = []
    for kw in keywords:
        jobs.append({
            "platform": "peopleperhour",
            "title": f"PPH job: {kw}",
            "description": f"PeoplePerHour result for {kw}",
            "url": f"https://www.peopleperhour.com/freelance-jobs?q={kw}"
        })
    return jobs
