import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, TIMESTAMP,
    ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)

    # flags
    is_admin = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    is_blocked = Column(Boolean, nullable=False, server_default=text("false"))

    # access dates
    trial_start = Column(TIMESTAMP(timezone=True))
    trial_end = Column(TIMESTAMP(timezone=True))
    license_until = Column(TIMESTAMP(timezone=True))

    # settings
    countries = Column(String)                 # CSV ή 'ALL'
    proposal_template = Column(String)

    # audit
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    keywords = relationship("Keyword", back_populates="user", cascade="all, delete-orphan")


class Keyword(Base):
    __tablename__ = "keyword"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    # ΠΡΟΣΟΧΗ: η canonical στήλη είναι 'value'
    value = Column(String, nullable=False)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    user = relationship("User", back_populates="keywords")

    __table_args__ = (UniqueConstraint("user_id", "value", name="uq_keyword_user_value"),)


def ensure_schema():
    # Δημιουργία πινάκων αν δεν υπάρχουν (idempotent)
    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        # === USER columns: χρήση IF NOT EXISTS για πλήρη ανθεκτικότητα ===
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT false;""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_admin   BOOLEAN NOT NULL DEFAULT false;""")

        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_start    TIMESTAMPTZ NULL;""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_end      TIMESTAMPTZ NULL;""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS license_until  TIMESTAMPTZ NULL;""")

        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS countries          TEXT NULL;""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS proposal_template  TEXT NULL;""")

        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();""")
        conn.exec_driver_sql("""ALTER TABLE "user" ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();""")

        # === KEYWORD: εξασφαλίζουμε ότι υπάρχει 'value' & είναι NOT NULL ===
        conn.exec_driver_sql("""ALTER TABLE keyword ADD COLUMN IF NOT EXISTS value TEXT NULL;""")

        # Backfill από πιθανές παλιές ονομασίες στηλών (στο CURRENT_SCHEMA only)
        conn.exec_driver_sql("""
        DO $$
        DECLARE
            has_keyword boolean := EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name='keyword' AND column_name='keyword'
            );
            has_name boolean := EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name='keyword' AND column_name='name'
            );
            has_term boolean := EXISTS(
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name='keyword' AND column_name='term'
            );
        BEGIN
            IF has_keyword THEN
                EXECUTE 'UPDATE keyword SET value = COALESCE(value, keyword) WHERE value IS NULL OR value = ''''''';
            END IF;
            IF has_name THEN
                EXECUTE 'UPDATE keyword SET value = COALESCE(value, name) WHERE value IS NULL OR value = ''''''';
            END IF;
            IF has_term THEN
                EXECUTE 'UPDATE keyword SET value = COALESCE(value, term) WHERE value IS NULL OR value = ''''''';
            END IF;
            -- fallback σε κενό string (ώστε να μπορέσει να γίνει NOT NULL)
            EXECUTE 'UPDATE keyword SET value = '''''' WHERE value IS NULL';
        END $$;
        """)

        # Κάνε τη NOT NULL (αν έχει ήδη NOT NULL δεν θα σκάσει)
        conn.exec_driver_sql("""ALTER TABLE keyword ALTER COLUMN value SET NOT NULL;""")

        # Unique constraint (idempotent)
        conn.exec_driver_sql("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_keyword_user_value'
            ) THEN
                ALTER TABLE keyword
                ADD CONSTRAINT uq_keyword_user_value UNIQUE (user_id, value);
            END IF;
        END $$;
        """)

        # Audit columns για keyword (idempotent)
        conn.exec_driver_sql("""ALTER TABLE keyword ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();""")
        conn.exec_driver_sql("""ALTER TABLE keyword ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();""")


def init_db():
    ensure_schema()
