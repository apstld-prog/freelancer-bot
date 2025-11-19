# ---------- fetch ----------
def fetch_all(keywords_query: Optional[str] = None) -> List[Dict]:
    out: List[Dict] = []

    # --- FREELANCER ---
    if PLATFORMS.get("freelancer"):
        try:
            out += fr.fetch(keywords_query or None)
        except Exception:
            pass

    # --- PEOPLEPERHOUR ---
    try:
        import platform_peopleperhour as pph
        if PLATFORMS.get("peopleperhour"):
            kws = _normalize_kw_list(keywords_query.split(",") if keywords_query else [])
            for i in pph.get_items(kws):
                i["affiliate"] = False
                i["source"] = "peopleperhour"   # 🔥 ΑΥΤΟ ΕΛΕΙΠΕ
                out.append(i)
    except Exception:
        pass

    # --- SKYWALKER ---
    if PLATFORMS.get("skywalker"):
        try:
            for i in sky.fetch(SKYWALKER_RSS):
                i["affiliate"] = False
                i["source"] = "skywalker"
                out.append(i)
        except Exception:
            pass

    # --- PLACEHOLDERS (malt, workana, etc) ---
    try:
        if PLATFORMS.get("malt"): out += ph.fetch_malt()
        if PLATFORMS.get("workana"): out += ph.fetch_workana()
        if PLATFORMS.get("wripple"): out += ph.fetch_wripple()
        if PLATFORMS.get("toptal"): out += ph.fetch_toptal()
        if PLATFORMS.get("twago"): out += ph.fetch_twago()
        if PLATFORMS.get("freelancermap"): out += ph.fetch_freelancermap()
        if PLATFORMS.get("younojuno") or PLATFORMS.get("yunoJuno") or PLATFORMS.get("yuno_juno"):
            out += ph.fetch_yunojuno()
        if PLATFORMS.get("worksome"): out += ph.fetch_worksome()
        if PLATFORMS.get("codeable"): out += ph.fetch_codeable()
        if PLATFORMS.get("guru"): out += ph.fetch_guru()
        if PLATFORMS.get("99designs"): out += ph.fetch_99designs()
        if PLATFORMS.get("jobfind"): out += ph.fetch_jobfind()
        if PLATFORMS.get("kariera"): out += ph.fetch_kariera()
        if PLATFORMS.get("careerjet"): out += ph.fetch_careerjet()
    except Exception:
        pass

    return out
