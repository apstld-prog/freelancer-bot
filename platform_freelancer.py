import httpx, time, math, datetime, traceback, logging

log = logging.getLogger("platform_freelancer")

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
    """Normalize a single Freelancer project entry with safe currency handling."""
    b = p.get("budget") or {}
    cur_info = b.get("currency") if isinstance(b.get("currency"), dict) else {}
    cur = (cur_info.get("code") if isinstance(cur_info, dict) else None) or "USD"

    return {
        "source": "Freelancer",
        "title": p.get("title", "") or "(untitled)",
        "description": p.get("preview_description", "") or "",
        "budget_min": _safe_num(b.get("minimum")) if isinstance(b, dict) else None,
        "budget_max": _safe_num(b.get("maximum")) if isinstance(b, dict) else None,
        "budget_currency": cur,
        "original_url": _make_url(p),
        "time_submitted": int(p.get("time_submitted", time.time())),
        "matched_keyword": kw,
    }

def fetch_freelancer_jobs(keywords):
    """Fetch Freelancer jobs one keyword at a time with detailed logging."""
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

        log.info(f"[Freelancer] Fetching jobs for keyword: {kw}")
        try:
            with httpx.Client(timeout=15.0, headers=HEADERS) as cli:
                r = cli.get(FREELANCER_SEARCH_URL, params=params)
                log.info(f"[Freelancer] Status {r.status_code} for '{kw}'")
                if r.status_code != 200:
                    log.warning(f"[Freelancer] Non-200 response for '{kw}': {r.status_code}")
                    continue
                try:
                    data = r.json()
                except Exception as je:
                    log.error(f"[Freelancer] JSON decode error for '{kw}': {je}")
                    log.debug(r.text[:300])
                    continue

                projects = (data.get("result") or {}).get("projects", [])
                log.info(f"[Freelancer] Retrieved {len(projects)} projects for '{kw}'")

                for p in projects:
                    try:
                        job = _normalize(p, kw)
                        all_jobs.append(job)
                    except Exception as inner:
                        log.warning(f"[Freelancer] normalize error: {inner}")
                        log.debug(traceback.format_exc())

        except Exception as e:
            log.error(f"[Freelancer] fetch error for '{kw}': {e}")
            log.debug(traceback.format_exc())

        time.sleep(1)

    log.info(f"[Freelancer] total merged: {len(all_jobs)}")
    return all_jobs
