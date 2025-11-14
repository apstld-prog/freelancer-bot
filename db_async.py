# db_async.py
# -----------------------------------------------------------------------------
# Async adapter για το υπαρχον SessionLocal από το db.py
# Επιτρέπει:  "async with get_session() as db:"
# Χωρίς να αλλάξουμε το db.py ή τα μοντέλα σου.
# -----------------------------------------------------------------------------

from contextlib import asynccontextmanager

# Εισάγουμε το SessionLocal από το υπάρχον db.py σου.
# Το db.py ΠΡΕΠΕΙ ήδη να ορίζει: SessionLocal = sessionmaker(bind=engine, ...)
from db import SessionLocal  # <- ΜΗΝ το αλλάξεις

@asynccontextmanager
async def get_session():
    """
    Επιστρέφει SQLAlchemy session ως async context manager ώστε
    να δουλεύει η σύνταξη:  async with get_session() as db:
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


# Προαιρετικά: helper για sync χρήση όπου χρειάζεται
def get_session_sync():
    """Πάρε απλώς ένα session (χωρίς context manager)."""
    return SessionLocal()
