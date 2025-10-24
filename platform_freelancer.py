import os
import logging
from typing import List, Dict, Any

import httpx
from datetime import datetime, timezone

log = logging.getLogger("platform_freelancer")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

FREELANCER_API = "https://www.freelancer.com/api/projects/0.1/projects/active/"

def _ts_to_iso(ts: Any) -> str | None:
    try:
        # API δίνει seconds (unix). Αν είναι string, κάνε cast
        iv = int(float(ts))
        return datetime.fromtimestamp(iv, tz=timezone.utc).isoformat()
    except Exception:
        return None

def _build_original_url(project: Dict[str, Any]) -> str:
    # ασφαλές fallback: /projects/<id> ή από seo_url
    pid = project.get("id")
    seo = project.get("seo_url") or project.get("seo_url_slug") or ""
    if seo:
        return f"https://www.freelancer.com/projects/{seo}"
    if pid:
        return f"https://www.freelancer.com/projects/{pid}"
    return "https://www.freelancer.com/jobs"

def _extract_budget(project: Dict[str, Any]) -> Dict[str, Any]:
    """
    Γεμίζει:
      - budget_currency
      - budget_min/budget_max ή budget_amount
      - usd_min/usd_max ή usd_amount (αν υπάρχει exchange_rate στο API)
    """
    out: Dict[str, Any] = {}
    # Πολλά responses έχουν: currency:{code,exchange_rate}, budget:{minimum:{amount}, maximum:{amount}} ή budget:{amount}
    currency = (project.get("currency") or {})
    cur_code = (currency.get("code") or "").upper()
    rate = currency.get("exchange_rate")  # συνήθως USD rate
    budget = project.get("budget") or {}

    minimum = None
    maximum = None
    amount  = None

    if isinstance(budget, dict):
        if isinstance(budget.get("minimum"), dict):
            minimum = budget["minimum"].get("amount")
        if isinstance(budget.get("maximum"), dict):
            maximum = budget["maximum"].get("amount")
        if budget.get("amount") is not None:
            amount = budget.get("amount")

    # Σε κάποια responses υπάρχουν κατευθείαν min,max
    minimum = minimum if minimum is not None else project.get("min")
    maximum = maximum if maximum is not None else project.get("max")
    amount  = amount  if amount  is not None else project.get("amount")

    out["budget_currency"] = cur_code or project.get("currency_code") or ""
    if minimum is not None or maximum is not None:
        out["budget_min"] = minimum
        out["budget_max"] = maximum
        if rate:
            try:
                if minimum is not None:
                    out["usd_min"] = float(minimum) * float(rate)
                if maximum is not None:
                    out["usd_max"] = float(maximum) * float(rate)
            except Exception:
                pass
    elif amount is not None:
        out["budget_amount"] = amount
        if rate:
            try:
                out["usd_amount"] = float(amount) * float(rate)
            except Exception:
                pass

    return out

def _normalize(project: Dict[str, Any], match_kw: str) -> Dict[str, Any]:
    title = project.get("title") or project.get("name") or "Untitled"
    desc = (project.get("preview_description") or project.get("description") or "").strip()
    posted_iso = _ts_to_iso(project.get("time_submitted") or project.get("submitdate"))

    normalized = {
        "title": title,
        "description": desc,
        "original_url": _build_original_url(project),
        "source": "Freelancer",
        "posted_at": posted_iso,
        "match": match_kw,
    }
    normalized.update(_extract_budget(project))
    return normalized

async def fetch_freelancer_jobs(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Κάνει ΕΝΑ call ανά keyword (όπως ήδη φαίνεται στα logs σου),
    και ενώνει αποτελέσματα. Γυρνάει normalized entries.
    """
    results: Dict[str, Dict[str, Any]] = {}
    params_base = {
        "full_description": "false",
        "job_details": "false",
        "limit": "30",
        "sort_field": "time_submitted",
        "sort_direction": "desc",
    }

    async with httpx.AsyncClient(timeout=25) as client:
        for kw in keywords:
            qparams = dict(params_base)
            qparams["query"] = kw
            r = await client.get(FREELANCER_API, params=qparams)
            if r.status_code != 200:
                log.info(f"[Freelancer] Status {r.status_code} for '{kw}'")
                continue
            data = r.json()
            projects = (data.get("result") or {}).get("projects") or data.get("projects") or []
            # debug
            log.info(f"[Freelancer] Retrieved {len(projects)} projects for '{kw}'")

            for p in projects:
                pid = str(p.get("id") or "")
                if not pid:
                    continue
                # κράτα την πιο πρόσφατη αν διπλό
                norm = _normalize(p, kw)
                # απλό dedupe: by pid
                results[pid] = norm

    merged = list(results.values())
    log.info(f"[Freelancer] total merged: {len(merged)}")
    return merged
