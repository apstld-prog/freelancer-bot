RESET PACK v0 — minimal & safe
---------------------------------
• Δεν αλλάζει το στήσιμο/εμφάνιση.
• Διορθώνει /start (γράφει/δείχνει trial dates), /help (HTML-safe), και κουμπιά (CallbackQueryHandler).
• Περιλαμβάνει ασφαλή ensure_schema() για την trial_reminder_sent & saved_job.

Τι να κάνεις:
1) Αντικατάστησε τα αρχεία bot.py, ui_texts.py, db.py με αυτά του zip.
2) Βεβαιώσου στο .env:
   - BOT_TOKEN=...
   - DATABASE_URL=...
   - ADMIN_IDS=5254014824,7916253053   (παράδειγμα)
   - TRIAL_DAYS=10
   - CONTACT_HANDLE=@your_username
3) Deploy.

Γιατί δεν έρχονται αγγελίες;
• Έλεγξε ότι ο worker τρέχει και έχει σωστές πηγές (Freelancer API/feeds).
• Δώσε keywords (/addkeyword python, logo). Για test, KEYWORD_FILTER_MODE=off.
• Αν έχεις affiliate wrapping, βεβαιώσου ότι τα envs είναι σωστά.

Generated: 2025-10-11 09:07:11 UTC
