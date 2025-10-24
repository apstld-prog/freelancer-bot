import httpx, time, traceback, logging

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

def _detect_currency(p):
    """Improved currency detection for Freelancer jobs."""
    b = p.get("budget") or {}
    cur_info = b.get("currency") if isinstance(b.get("currency"), dict) else None

    # Priority 1: explicit code
    if cur_info and "code" in cur_info and cur_info["code"]:
        return cur_info["code"].upper()

    # Priority 2: sign or name detection
    if cur_info:
        sign = str(cur_info.get("sign") or "").strip()
        name = str(cur_info.get("name") or "").lower()

        if sign in ["£", "₤"] or "pound" in name:
            return "GBP"
        if sign in ["€"] or "euro" in name:
            return "EUR"
        if sign in ["₹"] or "rupee" in name or "inr" in name:
            return "INR"
        if "a$" in name or "aud" in name or "australian" in name:
            return "AUD"
        if "cad" in name or "canadian" in name or sign == "C$":
            return "CAD"
        if "php" in name or "peso" in name:
            return "PHP"

    # Priority 3: currency_id lookup
    cur_id = None
    if isinstance(cur_info, dict) and cur_info.get("id"):
        cur_id = cur_info["id"]
    elif "currency_id" in b:
        cur_id = b["currency_id"]

    id_map = {
        1: "USD",
        3: "GBP",
        4: "EUR",
        5: "AUD",
        6: "CAD",
        9: "INR",
        12: "PHP",
    }
    if cur_id and cur_id in id_map:
        return id_map[cur_id]

    # Priority 4: try parsing text fields
    for key in ("currency", "currency_code"):
        val = b.get(key)
        if isinstance(val, str) and len(val) == 3:
            return val.upper()

    # Priority 5: sign detection from description or title
    text = (p.get("title", "") + " " + p.get("preview_description", "")).lower()
    if "£" in text or "pound" in text:
        return "GBP"
    if "€" in text or "euro" in text:
        return "EUR"
    if "₹" in text or "inr" in text:
        return "INR"
    if "$" in text:
        return "USD"

    # Default fallback
    return "USD"

def _normalize(p, kw):
    """Normalize a single Freelancer project entry with safe currency handling."""
    b = p.get("budget") or {}
    cur = _detect_currency(p)

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
