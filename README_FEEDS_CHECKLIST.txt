Freelancer Bot — Template Pack (v1)
=====================================

What this pack includes
-----------------------
1) ui_texts.py
   • Welcome text and Help/Admin sections matching your screenshots.
   • Admin footer is HTML-safe (uses &lt; &gt; inside <code> blocks).
2) git_auto_push.bat
   • Simple Windows script to auto add/commit/push with a timestamp.

How to use
----------
1. Replace your project's ui_texts.py with the one in this zip.
2. Deploy.
3. /start will show the classic welcome; /help will show Features & Platforms; Admins will also see admin commands.

Why no jobs are arriving?
-------------------------
Check these quickly:
• WORKER is running (log: "[Worker] ✅ Running ...").
• Keywords exist: /addkeyword python, telegram (or check in DB).
• KEYWORD_FILTER_MODE: keep "off" for quick testing.
• Platform feeds/API keys:
  - FREELANCER_API_KEY or the affiliate wrapper/envs you used before.
  - SKYWORKER_FEED=https://www.skywalker.gr/jobs/feed
• Country filters: /setcountry ALL for testing.
• Self test: use /selftest (should send a sample card, no banner).

If feedstatus shows nothing:
• Ensure the worker actually pushes events to the bot (check worker logs).
• Temporarily relax dedup rules to see flow.
• Verify timezone on the server (UTC) vs your query window.
Generated at 2025-10-11 08:37:11.
