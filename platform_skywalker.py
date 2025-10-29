def fetch_skywalker_jobs(keywords=None):
    logger.info("[Skywalker] Fetching latest jobs...")
    url = "https://www.skywalker.gr/el/thesis"
    jobs = []
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"[Skywalker] HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select("div.job")
        for item in items:
            title_tag = item.select_one("a.job-title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link = "https://www.skywalker.gr" + title_tag["href"]

            desc = item.select_one("div.job-desc")
            description = desc.get_text(strip=True) if desc else "N/A"

            budget_amount, budget_currency = None, "EUR"
            budget_usd = convert_to_usd(budget_amount, budget_currency)

            posted_time = datetime.utcnow()

            if posted_time < datetime.utcnow() - timedelta(hours=48):
                continue

            jobs.append({
                "platform": "Skywalker",
                "title": title,
                "description": description,
                "budget_amount": budget_amount,
                "budget_currency": budget_currency,
                "budget_usd": budget_usd,
                "url": link,
                "created_at": posted_time.isoformat()
            })
        logger.info(f"[Skywalker] ✅ {len(jobs)} jobs fetched")
        return jobs
    except Exception as e:
        logger.error(f"[Skywalker] Error: {e}")
        return []
