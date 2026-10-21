from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cold_pitches = relationship("ColdPitch", back_populates="user", cascade="all, delete-orphan")
    outreach_logs = relationship("OutreachLog", back_populates="user", cascade="all, delete-orphan")


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
    is_enriched = Column(Boolean, default=False)
    is_invalid = Column(Boolean, default=False, nullable=False, index=True)
    invalid_reason = Column(String(255), nullable=True)
    invalid_at = Column(DateTime, nullable=True)
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
    industry = Column(String(150), nullable=True)
    tech_stack = Column(JsonType, nullable=True)
    services = Column(JsonType, nullable=True)
    hiring_signals = Column(Text, nullable=True)
    tone = Column(String(100), default="Professional")
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
    status = Column(String(50), default="DRAFT")
    delivery_method = Column(String(50), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="pitches")
    user = relationship("User", back_populates="cold_pitches")


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
    status_message = Column(String(255), default="Job Queued in Cloud")
    total_found = Column(Integer, default=0)
    total_enriched = Column(Integer, default=0)
    logs = Column(JsonType, default=list)
    results = Column(JsonType, default=list)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Database engine & Session factory
clean_db_url = (DATABASE_URL or "").strip().strip("\"'").strip()
if clean_db_url.startswith("postgres://"):
    clean_db_url = clean_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif clean_db_url.startswith("postgresql://") and not clean_db_url.startswith("postgresql+"):
    clean_db_url = clean_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

try:
    engine = create_engine(
        clean_db_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    print(f"[DB] Initialized database engine: {engine.name} ({engine.url.render_as_string(hide_password=True)})")
except Exception as e:
    print(f"[DB Error] Could not initialize engine with DATABASE_URL ({e}). Falling back to SQLite.")
    engine = create_engine("sqlite:///./reachpilot_fallback.db")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create tables automatically on startup and ensure columns exist"""
    try:
        Base.metadata.create_all(bind=engine)
        print(f"[DB] Schema initialized successfully on engine: {engine.name}")

        # Safe schema alteration for new columns (PostgreSQL only)
        if engine.name == "postgresql":
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS is_invalid BOOLEAN DEFAULT FALSE;"))
                conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS invalid_reason VARCHAR(255);"))
                conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS invalid_at TIMESTAMP;"))
                conn.execute(text("ALTER TABLE companies ADD COLUMN IF NOT EXISTS location_url TEXT;"))
                conn.execute(text("ALTER TABLE outreach_logs ADD COLUMN IF NOT EXISTS email_body TEXT;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_link VARCHAR(500);"))
                conn.commit()
    except Exception as ex:
        print(f"[DB Warning] Could not auto-create/migrate tables: {ex}")


def get_db():
    """Dependency helper for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
