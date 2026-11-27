"""Resumes kept in the database (user_resumes), not on Render's wiped-on-deploy disk.

Each user has one main resume (is_main) and, on plans that allow it, extra labelled ones.
The old disk copy (uploads/resumes/user_<id>_resume.pdf) is still read as a fallback.
"""
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from db import UserResume


def legacy_resume_path(user_id: int) -> str:
    return os.path.join("uploads", "resumes", f"user_{user_id}_resume.pdf")


def main_resume(db: Session, user_id: int) -> UserResume | None:
    return (db.query(UserResume)
            .filter(UserResume.user_id == user_id)
            .order_by(UserResume.is_main.desc(), UserResume.id.asc())
            .first())


def resume_pdf(db: Session, user_id: int, resume_id: int | None = None) -> tuple[bytes | None, str | None]:
    """PDF bytes and file name for a resume (the main one unless resume_id is given)."""
    row = None
    if resume_id:
        row = db.query(UserResume).filter(UserResume.id == resume_id, UserResume.user_id == user_id).first()
    row = row or main_resume(db, user_id)
    if row and row.pdf:
        return row.pdf, row.filename or "Resume.pdf"
    path = legacy_resume_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read(), "Resume.pdf"
        except OSError:
            pass
    return None, None


def save_main_resume(db: Session, user_id: int, filename: str, pdf: bytes | None, summary: dict) -> UserResume:
    """Create or replace the user's main resume (caller commits)."""
    row = db.query(UserResume).filter(UserResume.user_id == user_id, UserResume.is_main.is_(True)).first()
    if not row:
        row = UserResume(user_id=user_id, label="Main", is_main=True)
        db.add(row)
    row.filename = filename or "Resume.pdf"
    if pdf is not None:
        row.pdf = pdf
    row.summary = summary
    return row


def all_resumes(db: Session, user_id: int) -> list[UserResume]:
    """Main first, then extras in the order they were added."""
    return (db.query(UserResume).filter(UserResume.user_id == user_id)
            .order_by(UserResume.is_main.desc(), UserResume.id.asc()).all())


def usable_resumes(db: Session, user_id: int, slots: int) -> list[UserResume]:
    """The resumes the plan allows. After a downgrade the extras past the limit stay saved but locked."""
    return all_resumes(db, user_id)[:max(1, int(slots or 1))]


def _norm(t: Any) -> str:
    return re.sub(r"[^a-z0-9+#]+", "", str(t).lower())


def resume_fit_score(summary: dict | None, company_profile: dict) -> int:
    """How many of the resume's skills the company lists in its tech stack or services."""
    company = {_norm(t) for t in (company_profile.get("tech_stack") or []) + (company_profile.get("services") or []) if _norm(t)}
    return sum(1 for k in {_norm(s) for s in ((summary or {}).get("top_skills") or [])} if k and k in company)


def pick_resume(rows: list[UserResume], company_profile: dict) -> UserResume | None:
    """The resume whose skills overlap the company most; ties (and no overlap) go to the main one."""
    if not rows:
        return None
    return max(rows, key=lambda r: (resume_fit_score(r.summary, company_profile), bool(r.is_main), -r.id))
