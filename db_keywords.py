from db import get_session


def ensure_keyword_unique():
    """Δημιουργεί τον πίνακα user_keywords και αφαιρεί διπλότυπα."""
    with get_session() as s:
        s.execute("""
        CREATE TABLE IF NOT EXISTS user_keywords (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            keyword TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'UTC')
        );
        """)
        s.execute("""
        DELETE FROM user_keywords a
        USING user_keywords b
        WHERE a.id < b.id AND a.user_id = b.user_id AND a.keyword = b.keyword;
        """)
        s.commit()


def get_user_keywords(user_id: int):
    """Επιστρέφει όλα τα keywords ενός χρήστη ως λίστα."""
    with get_session() as s:
        s.execute("SELECT keyword FROM user_keywords WHERE user_id=%s;", (user_id,))
        rows = s.fetchall()
        return [r["keyword"] for r in rows]


def add_user_keyword(user_id: int, keyword: str):
    """Προσθέτει νέο keyword για χρήστη, αν δεν υπάρχει ήδη."""
    if not keyword:
        return
    with get_session() as s:
        s.execute("SELECT 1 FROM user_keywords WHERE user_id=%s AND keyword=%s;", (user_id, keyword))
        if not s.fetchone():
            s.execute("INSERT INTO user_keywords (user_id, keyword) VALUES (%s, %s);", (user_id, keyword))
            s.commit()


def delete_user_keyword(user_id: int, keyword: str):
    """Διαγράφει keyword χρήστη."""
    with get_session() as s:
        s.execute("DELETE FROM user_keywords WHERE user_id=%s AND keyword=%s;", (user_id, keyword))
        s.commit()


def list_keywords(user_id: int = None):
    """Λίστα όλων των keywords ή ανά χρήστη (αν δοθεί user_id)."""
    with get_session() as s:
        if user_id:
            s.execute("SELECT keyword FROM user_keywords WHERE user_id=%s;", (user_id,))
        else:
            s.execute("SELECT DISTINCT keyword FROM user_keywords;")
        rows = s.fetchall()
        return [r["keyword"] for r in rows]


def ensure_keywords():
    """Προσθέτει default keywords για admin (id=1) αν δεν υπάρχουν."""
    default_keywords = ["logo", "lighting", "design", "sales"]
    with get_session() as s:
        for kw in default_keywords:
            s.execute("SELECT 1 FROM user_keywords WHERE user_id=1 AND keyword=%s;", (kw,))
            if not s.fetchone():
                s.execute("INSERT INTO user_keywords (user_id, keyword) VALUES (1, %s);", (kw,))
        s.commit()


if __name__ == "__main__":
    print("======================================================")
    print("🔑 INIT KEYWORDS TOOL — psycopg2 version (FINAL)")
    print("======================================================")
    ensure_keyword_unique()
    ensure_keywords()
    print("✅ Default keywords ensured successfully.")
    print("======================================================")
