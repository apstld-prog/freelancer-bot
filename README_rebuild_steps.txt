======================================================
🚀 FREELANCER BOT CLEAN SCHEMA REBUILD — INSTRUCTIONS
======================================================

1️⃣ DROP OLD STRUCTURE
   psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

2️⃣ REBUILD CLEAN SCHEMA
   psql "$DATABASE_URL" -f rebuild_schema.sql

3️⃣ DEPLOY
   - push to Render
   - service will boot cleanly (no undefined columns)
   - workers will auto-create missing indexes if needed

======================================================
💡 TIP: You can test locally before Render:
   python db.py && python db_events.py && python db_keywords.py
======================================================
