"""Resumes kept in the database (user_resumes), not on Render's wiped-on-deploy disk.

Each user has one main resume (is_main) and, on plans that allow it, extra labelled ones.
The old disk copy (uploads/resumes/user_<id>_resume.pdf) is still read as a fallback.
"""
import os

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
