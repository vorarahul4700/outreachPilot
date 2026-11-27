import socket
import urllib.parse
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.types import JSON

from config import DATABASE_URL

Base = declarative_base()

# Choose JSON type (JSONB if postgresql dialect, else fallback JSON)
JsonType = JSONB if "postgres" in DATABASE_URL.lower() else JSON


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String(255), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    picture = Column(Text, nullable=True)
    oauth_tokens = Column(JsonType, nullable=True)
    target_role = Column(String(255), nullable=True)
    resume_summary = Column(JsonType, nullable=True)
    resume_link = Column(String(500), nullable=True)
    daily_send_limit = Column(Integer, default=50)

    # --- Role & Admin Controls ---
    is_admin = Column(Boolean, default=False, index=True)
    is_banned = Column(Boolean, default=False, index=True)
    ban_reason = Column(String(255), nullable=True)

    # --- Subscription & Tier Controls ---
    subscription_tier = Column(String(50), default="free", index=True)  # 'free', 'pro', 'premium_plus'
    subscription_status = Column(String(50), default="active")          # 'active', 'past_due', 'canceled'
    subscription_end_date = Column(DateTime, nullable=True)
    # One-day Pro trial: set once when started; never cleared, so it can't be repeated.
    trial_started_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)

    # --- Pitch Quotas (Free: 10, Pro: 25, Premium+: 50, Admin: 999999) ---
    daily_pitch_limit = Column(Integer, default=10)
    pitches_sent_today = Column(Integer, default=0)
    last_pitch_reset_date = Column(DateTime, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cold_pitches = relationship("ColdPitch", back_populates="user", cascade="all, delete-orphan")
    outreach_logs = relationship("OutreachLog", back_populates="user", cascade="all, delete-orphan")


# --- Taxonomy: filters match on these IDs, never on text (see taxonomy.py) ---
class Industry(Base):
    __tablename__ = "industries"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), unique=True, nullable=False)   # it, sales, marketing, ...
    name = Column(String(120), nullable=False)
    slug = Column(String(120), unique=True, nullable=False)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    slug = Column(String(160), unique=True, nullable=False)
    name = Column(String(160), nullable=False)
    industry_id = Column(Integer, ForeignKey("industries.id"), nullable=False, index=True)
    is_hidden = Column(Boolean, default=False, nullable=False)  # admin > Categories


class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True)
    slug = Column(String(120), unique=True, nullable=False)
    name = Column(String(120), nullable=False)


class Tech(Base):
    __tablename__ = "techs"

    id = Column(Integer, primary_key=True)
    slug = Column(String(120), unique=True, nullable=False)
    name = Column(String(120), nullable=False)


class CompanyTech(Base):
    __tablename__ = "company_techs"

    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    tech_id = Column(Integer, ForeignKey("techs.id", ondelete="CASCADE"), primary_key=True, index=True)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    website_url = Column(Text, nullable=True)
    phone = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    location_url = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, default=0)
    source_query = Column(String(255), nullable=True)
    search_keyword = Column(String(255), nullable=True, index=True)
    city = Column(String(100), nullable=True, index=True)
    normalized_keyword = Column(String(255), nullable=True, index=True)
    # Filled from city / keyword by taxonomy.py on every save; filters use these.
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    is_enriched = Column(Boolean, default=False)
    enrichment_status = Column(String(50), default="PENDING", nullable=False, index=True)
    enrichment_attempts = Column(Integer, default=0, nullable=False)
    last_enriched_at = Column(DateTime, nullable=True)
    is_invalid = Column(Boolean, default=False, nullable=False, index=True)
    invalid_reason = Column(String(255), nullable=True)
    invalid_at = Column(DateTime, nullable=True)
    has_email = Column(Boolean, default=False, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    emails = relationship("CompanyEmail", back_populates="company", cascade="all, delete-orphan")
    profile = relationship("CompanyProfile", uselist=False, back_populates="company", cascade="all, delete-orphan")
    pitches = relationship("ColdPitch", back_populates="company", cascade="all, delete-orphan")
    outreach_logs = relationship("OutreachLog", back_populates="company", cascade="all, delete-orphan")


class CompanyEmail(Base):
    __tablename__ = "company_emails"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    email_address = Column(String(255), nullable=False, index=True)
    email_type = Column(String(50), default="generic")
    discovered_on_page = Column(String(255), nullable=True)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="emails")


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False)
    summary_short = Column(Text, nullable=True)
    detailed_analysis = Column(Text, nullable=True)
    industry = Column(Text, nullable=True)
    tech_stack = Column(JsonType, nullable=True)
    services = Column(JsonType, nullable=True)
    hiring_signals = Column(Text, nullable=True)
    tone = Column(Text, default="Professional")
    analyzed_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="profile")


class ColdPitch(Base):
    __tablename__ = "cold_pitches"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    target_email = Column(String(255), nullable=True)
    subject_line = Column(String(255), nullable=False)
    email_body = Column(Text, nullable=False)
    cover_letter = Column(Text, nullable=True)
    matched_skills = Column(JsonType, nullable=True)
    status = Column(String(50), default="DRAFT")  # DRAFT, QUEUED, SENDING, SENT, FAILED
    delivery_method = Column(String(50), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Send queue (outreach.run_send_queue): bulk sends are queued and sent by a background worker
    queued_at = Column(DateTime, nullable=True)
    send_attempts = Column(Integer, default=0)
    next_attempt_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    quota_reserved = Column(Boolean, default=False)  # one daily send was reserved; refund it if this never goes out

    company = relationship("Company", back_populates="pitches")
    user = relationship("User", back_populates="cold_pitches")


class SendAttachment(Base):
    """The resume a user attached to their latest queued batch, kept in the DB so a restart
    (Render's disk is not persistent) cannot drop the attachment from emails still queued."""
    __tablename__ = "send_attachments"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    filename = Column(String(255), nullable=False)
    data = Column(LargeBinary, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Payment(Base):
    """A Razorpay order for a plan. status: created -> paid (activated once)."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    tier_code = Column(String(50), nullable=False)
    amount_paise = Column(Integer, nullable=False)
    order_id = Column(String(64), unique=True, index=True, nullable=False)
    payment_id = Column(String(64), nullable=True)
    status = Column(String(20), default="created", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)


class DoNotContact(Base):
    """Addresses that opted out. No user can send to them again (outreach.send_via_google_oauth)."""
    __tablename__ = "do_not_contact"

    email = Column(String(255), primary_key=True)  # stored lowercase
    source = Column(String(50), default="unsubscribe_link")
    created_at = Column(DateTime, default=datetime.utcnow)


class OutreachLog(Base):
    __tablename__ = "outreach_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    recipient_email = Column(String(255), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    email_body = Column(Text, nullable=True)
    delivery_method = Column(String(50), nullable=False)
    status = Column(String(50), default="SENT")
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, index=True)

    company = relationship("Company", back_populates="outreach_logs")
    user = relationship("User", back_populates="outreach_logs")


class ScoutJob(Base):
    __tablename__ = "scout_jobs"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(255), nullable=False)
    city = Column(String(100), nullable=True)
    max_pages = Column(Integer, default=2)
    status = Column(String(50), default="QUEUED", index=True)  # QUEUED, RUNNING, COMPLETED, FAILED
    progress = Column(Integer, default=0)
    status_message = Column(Text, default="Job Queued in Cloud")
    total_found = Column(Integer, default=0)
    total_enriched = Column(Integer, default=0)
    logs = Column(JsonType, default=list)
    results = Column(JsonType, default=list)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionTier(Base):
    __tablename__ = "subscription_tiers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)  # 'free', 'pro', 'premium_plus'
    name = Column(String(100), nullable=False)
    subtitle = Column(String(100), nullable=True)
    price_inr = Column(Integer, default=0)
    daily_pitch_limit = Column(Integer, default=10)
    period_days = Column(Integer, default=30)  # plan length: 7 = weekly pass, 30 = monthly
    # Plan features (see plan_features.py)
    email_style = Column(String(20), default="tailored")  # standard | tailored | tailored_fit
    has_best_matches = Column(Boolean, default=False)
    has_linkedin = Column(Boolean, default=False)  # LinkedIn message + referral request
    resume_slots = Column(Integer, default=1)
    has_bulk = Column(Boolean, default=False)  # bulk prepare and bulk send
    features = Column(JsonType, default=list)
    badge = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database engine & Session factory
clean_db_url = (DATABASE_URL or "").strip().strip("\"'").strip()
clean_db_url = clean_db_url.replace("&channel_binding=require", "").replace("?channel_binding=require&", "?").replace("?channel_binding=require", "")
if clean_db_url.startswith("postgres://"):
    clean_db_url = clean_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif clean_db_url.startswith("postgresql://") and not clean_db_url.startswith("postgresql+"):
    clean_db_url = clean_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {
    "connect_timeout": 20,
    "keepalives": 1,
    "keepalives_idle": 15,
    "keepalives_interval": 5,
    "keepalives_count": 3
}
if "postgresql" in clean_db_url:
    try:
        parsed_url = urllib.parse.urlparse(clean_db_url)
        if parsed_url.hostname and not parsed_url.hostname.replace(".", "").isdigit():
            # Try AF_INET getaddrinfo first for reliable IPv4 resolution
            try:
                addr_info = socket.getaddrinfo(parsed_url.hostname, 5432, socket.AF_INET, socket.SOCK_STREAM)
                if addr_info:
                    connect_args["hostaddr"] = addr_info[0][4][0]
            except Exception:
                # If local DNS is unreachable or drops A records, fallback to known AWS ap-southeast-1 pooler IPv4
                if "neon.tech" in parsed_url.hostname:
                    connect_args["hostaddr"] = "52.76.246.190"
    except Exception as dns_err:
        print(f"[DB Warning] Could not pre-resolve IPv4 hostaddr: {dns_err}")

try:
    engine = create_engine(
        clean_db_url,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_size=20,
        max_overflow=30,
        pool_timeout=35,
        connect_args=connect_args
    )
    print(f"[DB] Initialized database engine: {engine.name} ({engine.url.render_as_string(hide_password=True)})")
except Exception as e:
    print(f"[DB Error] Could not initialize engine with DATABASE_URL ({e}). Falling back to SQLite.")
    engine = create_engine("sqlite:///./reachpilot_fallback.db")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create tables automatically on startup and ensure columns & indexes exist"""
    try:
        Base.metadata.create_all(bind=engine)
        print(f"[DB] Schema initialized successfully on engine: {engine.name}")

        # Safe schema alteration & indexing for high-concurrency performance (PostgreSQL only)
        if engine.name == "postgresql":
            # Each statement commits on its own (AUTOCOMMIT) and gives up quickly if it
            # cannot get a lock. Previously the whole list ran in one transaction, so a
            # server killed mid-startup (e.g. a reload) left an exclusive lock on
            # `companies` and every company query hung behind it. ALTERs are skipped
            # entirely when the column already exists, so normal starts take no
            # exclusive lock at all.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("SET lock_timeout = '5s'"))
                conn.execute(text("SET statement_timeout = '60s'"))
                existing = {
                    (r[0], r[1]) for r in conn.execute(text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name IN ('companies','outreach_logs','users','scout_jobs','cold_pitches')"
                    ))
                }
                column_adds = [
                    ("companies", "is_invalid", "BOOLEAN DEFAULT FALSE"),
                    ("companies", "invalid_reason", "VARCHAR(255)"),
                    ("companies", "invalid_at", "TIMESTAMP"),
                    ("companies", "location_url", "TEXT"),
                    ("companies", "enrichment_status", "VARCHAR(50) DEFAULT 'PENDING'"),
                    ("companies", "enrichment_attempts", "INTEGER DEFAULT 0"),
                    ("companies", "last_enriched_at", "TIMESTAMP"),
                    ("companies", "city_id", "INTEGER REFERENCES cities(id)"),
                    ("companies", "category_id", "INTEGER REFERENCES categories(id)"),
                    ("outreach_logs", "email_body", "TEXT"),
                    ("users", "resume_link", "VARCHAR(500)"),
                    ("cold_pitches", "queued_at", "TIMESTAMP"),
                    ("cold_pitches", "send_attempts", "INTEGER DEFAULT 0"),
                    ("cold_pitches", "next_attempt_at", "TIMESTAMP"),
                    ("cold_pitches", "last_error", "TEXT"),
                    ("cold_pitches", "quota_reserved", "BOOLEAN DEFAULT FALSE"),
                    ("subscription_tiers", "period_days", "INTEGER DEFAULT 30"),
                    ("subscription_tiers", "email_style", "VARCHAR(20) DEFAULT 'tailored'"),
                    ("subscription_tiers", "has_best_matches", "BOOLEAN DEFAULT FALSE"),
                    ("subscription_tiers", "has_linkedin", "BOOLEAN DEFAULT FALSE"),
                    ("subscription_tiers", "resume_slots", "INTEGER DEFAULT 1"),
                    ("subscription_tiers", "has_bulk", "BOOLEAN DEFAULT FALSE"),
                    ("users", "trial_started_at", "TIMESTAMP"),
                    ("users", "trial_ends_at", "TIMESTAMP"),
                ]
                statements = [
                    f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col} {ddl};"
                    for tbl, col, ddl in column_adds if (tbl, col) not in existing
                ]
                if ("companies", "enrichment_status") not in existing:
                    statements += [
                        "UPDATE companies SET enrichment_status = 'COMPLETED' WHERE is_enriched = TRUE AND (enrichment_status IS NULL OR enrichment_status = 'PENDING');",
                        "UPDATE companies SET enrichment_status = 'PENDING' WHERE is_enriched = FALSE AND (enrichment_status IS NULL);",
                    ]
                st_type = conn.execute(text(
                    "SELECT data_type FROM information_schema.columns WHERE table_schema = current_schema() "
                    "AND table_name = 'scout_jobs' AND column_name = 'status_message'"
                )).scalar()
                if st_type and st_type != "text":
                    statements.append("ALTER TABLE scout_jobs ALTER COLUMN status_message TYPE TEXT;")
                statements += [
                    # Performance indexes (no-ops when present)
                    "CREATE INDEX IF NOT EXISTS ix_companies_is_enriched ON companies(is_enriched);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_created_at ON companies(created_at DESC);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_rating ON companies(rating DESC NULLS LAST);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_reviews_count ON companies(reviews_count DESC);",
                    "CREATE INDEX IF NOT EXISTS ix_company_emails_company_id ON company_emails(company_id);",
                    "CREATE INDEX IF NOT EXISTS ix_company_profiles_company_id ON company_profiles(company_id);",
                    "CREATE INDEX IF NOT EXISTS ix_outreach_logs_user_company ON outreach_logs(user_id, company_id);",
                    # Send queue worker scans only queued/sending rows
                    "CREATE INDEX IF NOT EXISTS ix_cold_pitches_queue ON cold_pitches(status, next_attempt_at) WHERE status IN ('QUEUED','SENDING');",
                    "CREATE INDEX IF NOT EXISTS ix_companies_city_id ON companies(city_id);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_category_id ON companies(category_id);",
                    # Search box is free text: trigram indexes make ILIKE '%x%' use an index.
                    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
                    "CREATE INDEX IF NOT EXISTS ix_companies_name_trgm ON companies USING gin (name gin_trgm_ops);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_domain_trgm ON companies USING gin (domain gin_trgm_ops);",
                    "CREATE INDEX IF NOT EXISTS ix_companies_address_trgm ON companies USING gin (address gin_trgm_ops);",
                ]
                for stmt in statements:
                    try:
                        conn.execute(text(stmt))
                    except Exception as e:
                        print(f"[DB] Skipped migration step ({str(e).splitlines()[0][:120]}): {stmt[:70]}")

            # Fill city_id / category_id / company_techs for rows saved before they existed.
            try:
                import taxonomy
                taxonomy.backfill()
            except Exception as tax_err:
                print(f"[DB Warning] Taxonomy backfill failed: {tax_err}")

        # Seed default subscription tiers if none exist
        try:
            with SessionLocal() as db_session:
                if db_session.query(SubscriptionTier.id).first() is None:
                    default_tiers = [
                        SubscriptionTier(
                            code="free",
                            name="Free Job Seeker",
                            subtitle="Starter Tier",
                            price_inr=0,
                            daily_pitch_limit=10,
                            features=[
                                "10 job applications / day",
                                "Full company directory access",
                                "Careers and contact email discovery",
                                "Sends from your own Gmail"
                            ],
                            badge=None,
                            is_active=True
                        ),
                        SubscriptionTier(
                            code="pro",
                            name="Job Seeker Pro",
                            subtitle="Growth Tier",
                            price_inr=199,
                            daily_pitch_limit=25,
                            features=[
                                "25 job applications / day",
                                "AI research of each company website",
                                "Resume PDF attached automatically",
                                "Each application written for that company"
                            ],
                            badge="Most Popular",
                            is_active=True
                        ),
                        SubscriptionTier(
                            code="premium_plus",
                            name="Premium+",
                            subtitle="Maximum Velocity",
                            price_inr=399,
                            daily_pitch_limit=50,
                            features=[
                                "50 job applications / day",
                                "Highest priority email queue",
                                "Matches your skills to each company's tech stack",
                                "Unlimited AI rewrites of each application"
                            ],
                            badge="Maximum Velocity",
                            is_active=True
                        ),
                        SubscriptionTier(
                            code="master_admin",
                            name="Master Admin Persona",
                            subtitle="Superuser",
                            price_inr=0,
                            daily_pitch_limit=999999,
                            features=[
                                "Infinite pitches / day (Bypass)",
                                "Zero subscription payment needed",
                                "Full user and lead administration",
                                "Act as regular job seeker on /app"
                            ],
                            badge="Dual Persona",
                            is_active=True
                        ),
                    ]
                    db_session.add_all(default_tiers)
                    db_session.commit()
                    print("[DB] Initialized default subscription tiers.")
        except Exception as seed_err:
            print(f"[DB Warning] Could not seed subscription tiers: {seed_err}")
    except Exception as ex:
        print(f"[DB Warning] Could not auto-create/migrate tables: {ex}")


def get_db():
    """Dependency helper for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Keep city_id / category_id / company_techs in step with every save (any writer).
# Imported lazily: taxonomy imports this module.
@event.listens_for(SessionLocal, "before_flush")
def _taxonomy_before_flush(session, flush_context, instances):
    import taxonomy
    taxonomy._before_flush(session, flush_context, instances)


@event.listens_for(SessionLocal, "after_flush")
def _taxonomy_after_flush(session, flush_context):
    import taxonomy
    taxonomy._after_flush(session, flush_context)
