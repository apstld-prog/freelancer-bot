def fetch_pph_jobs(keywords=None):
    logger.info("[PPH] Fetching latest jobs...")
    url = "https://www.peopleperhour.com/freelance-jobs/"
    jobs = []
    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(url)
        if r.status_code != 200:
            logger.warning(f"[PPH] HTTP {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("section.job-card, div.job-card")
        for card in cards:
            title_tag = card.select_one("a.job-title")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            link = "https://www.peopleperhour.com" + title_tag["href"]

            desc = card.select_one("p.job-description")
            description = desc.get_text(strip=True) if desc else "N/A"

            budget_tag = card.select_one("span.price, span.amount")
            budget_raw = budget_tag.get_text(strip=True) if budget_tag else "N/A"

            budget_amount, budget_currency = parse_budget(budget_raw)
            budget_usd = convert_to_usd(budget_amount, budget_currency)

            posted_time = datetime.utcnow()

            if posted_time < datetime.utcnow() - timedelta(hours=48):
                continue

            jobs.append({
                "platform": "PeoplePerHour",
                "title": title,
                "description": description,
                "budget_amount": budget_amount,
                "budget_currency": budget_currency,
                "budget_usd": budget_usd,
                "url": link,
                "created_at": posted_time.isoformat()
            })
        logger.info(f"[PPH] ✅ {len(jobs)} jobs fetched")
        return jobs
    except Exception as e:
        logger.error(f"[PPH] Error: {e}")
        return []
