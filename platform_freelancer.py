import httpx, time

FREELANCER_SEARCH_URL = "https://www.freelancer.com/api/projects/0.1/projects/active/"
HEADERS = {"User-Agent": "Mozilla/5.0 (FreelancerFeedBot)"}

def _safe_num(x):
    try:
        return round(float(x), 1)
    except Exception:
        return None

def _make_url(p):
    seo = p.get("seo_url")
    if seo:
        return f"https://www.freelancer.com/projects/{seo}"
    return f"https://www.freelancer.com/projects/{p.get('id')}"

def _normalize(p, kw):
    b = p.get("budget") or {}
    cur = (b.get("currency") or {}).get("code", "USD")
    return {
        "source": "Freelancer",
        "title": p.get("title", ""),
        "description": p.get("preview_description", ""),
        "budget_min": _safe_num(b.get("minimum")),
        "budget_max": _safe_num(b.get("maximum")),
        "budget_currency": cur,
        "original_url": _make_url(p),
        "time_submitted": int(p.get("time_submitted", time.time())),
        "matched_keyword": kw,
    }

def fetch_freelancer_jobs(keywords):
    """Fetch Freelancer jobs one keyword at a time (sync)."""
    all_jobs = []
    for kw in [k.strip() for k in keywords if k.strip()]:
        params = {
            "full_description": False,
            "job_details": False,
            "limit": 30,
            "offset": 0,
            "sort_field": "time_submitted",
            "sort_direction": "desc",
            "query": kw,
        }
        try:
            with httpx.Client(timeout=12.0, headers=HEADERS) as cli:
                r = cli.get(FREELANCER_SEARCH_URL, params=params)
                if r.status_code != 200:
                    continue
                data = r.json()
                for p in (data.get("result") or {}).get("projects", []):
                    job = _normalize(p, kw)
                    all_jobs.append(job)
        except Exception as e:
            print("[Freelancer fetch error]", e)
        time.sleep(1)
    print(f"[Freelancer] total merged: {len(all_jobs)}")
    return all_jobs
