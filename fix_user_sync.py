#!/usr/bin/env python3
import logging
from sqlalchemy import text
from db import get_session

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("fix_user_sync")

def main():
    log.info("======================================================")
    log.info("🔧 FIX USER SYNC TOOL — ensure admin and keyword linkage")
    log.info("======================================================")

    with get_session() as s:
        try:
            log.info("1️⃣  Updating admin telegram_id in both user tables...")
            s.execute(text('UPDATE "user" SET telegram_id=5254014824 WHERE username=\'admin\';'))
            s.execute(text('UPDATE users SET telegram_id=5254014824 WHERE id=1;'))

            log.info("2️⃣  Fixing keyword-user linkage (user_id → 1)...")
            s.execute(text("UPDATE keyword SET user_id=1 WHERE user_id IS NULL;"))

            log.info("3️⃣  Removing orphan saved_job entries (no valid user)...")
            s.execute(text('DELETE FROM saved_job WHERE user_id NOT IN (SELECT id FROM "user");'))

            s.commit()
            log.info("✅ Fix complete — admin + keywords + saved_job now consistent.")
            log.info("======================================================")
            log.info("Now you can run:  ./diagnostic.sh  → should show clean DB state.")
            log.info("======================================================")
        except Exception as e:
            s.rollback()
            log.error("❌ Error during fix: %s", e)

if __name__ == "__main__":
    main()
