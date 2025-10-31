async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_session() as s:
        u = get_or_create_user_by_tid(s, update.effective_user.id)
        s.execute(
            'UPDATE "user" SET trial_start = COALESCE(trial_start, NOW() AT TIME ZONE \'UTC\') WHERE id = %(id)s;',
            {"id": u.id},
        )
        # ✅ use make_interval(days => X) for postgres safety
        s.execute(
            'UPDATE "user" '
            'SET trial_end = COALESCE(trial_end, (NOW() AT TIME ZONE \'UTC\') + make_interval(days => %(days)s)) '
            'WHERE id = %(id)s;',
            {"id": u.id, "days": TRIAL_DAYS},
        )
        s.execute(
            'SELECT COALESCE(license_until, trial_end) AS expiry FROM "user" WHERE id = %(id)s;',
            {"id": u.id},
        )
        row = s.fetchone()
        expiry = row["expiry"] if row else None
        s.commit()

    await update.effective_chat.send_message(
        welcome_text(expiry if isinstance(expiry, datetime) else None),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(is_admin=is_admin_user(update.effective_user.id)),
    )
    await update.effective_chat.send_message(
        HELP_EN + help_footer(STATS_WINDOW_HOURS),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
