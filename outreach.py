import asyncio
import base64
import random
import urllib.parse
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

import config
from db import ColdPitch, OutreachLog, User


def get_effective_recipient(actual_email: str) -> str:
    """Returns safe override email if in DEV_MODE, else actual company email."""
    if config.DEV_MODE and config.DEV_OVERRIDE_EMAIL:
        return config.DEV_OVERRIDE_EMAIL
    return actual_email


def generate_gmail_web_link(to_email: str, subject: str, body: str) -> str:
    """
    Builds a 1-Click Gmail Web URL that opens compose modal in browser prefilled.
    Redirects to DEV_OVERRIDE_EMAIL if DEV_MODE is active.
    """
    effective_to = get_effective_recipient(to_email)
    effective_subject = f"[TEST -> {to_email}] {subject}" if config.DEV_MODE else subject

    params = {
        "view": "cm",
        "fs": "1",
        "to": effective_to,
        "su": effective_subject,
        "body": body
    }
    return f"https://mail.google.com/mail/?{urllib.parse.urlencode(params)}"


def generate_mailto_link(to_email: str, subject: str, body: str) -> str:
    """
    Builds a standard mailto: URI for mobile browsers or native desktop email clients.
    Redirects to DEV_OVERRIDE_EMAIL if DEV_MODE is active.
    """
    effective_to = get_effective_recipient(to_email)
    effective_subject = f"[TEST -> {to_email}] {subject}" if config.DEV_MODE else subject

    params = {
        "subject": effective_subject,
        "body": body
    }
    return f"mailto:{effective_to}?{urllib.parse.urlencode(params)}"


async def send_via_google_oauth(
    user: User,
    to_email: str,
    subject: str,
    body: str,
    db: Session,
    company_id: int | None = None,
    resume_attachment_path: str | None = None
) -> dict[str, Any]:
    """
    Sends an email directly through user's authorized Google OAuth 2.0 credentials.
    Redirects to DEV_OVERRIDE_EMAIL if DEV_MODE is active.
    Supports optional resume PDF attachment.
    """
    if not user.oauth_tokens:
        return {"success": False, "error": "Google OAuth account not connected."}

    effective_to = get_effective_recipient(to_email)
    effective_subject = f"[TEST -> {to_email}] {subject}" if config.DEV_MODE else subject

    try:
        import os
        token_data = config.decrypt_tokens(user.oauth_tokens) if isinstance(user.oauth_tokens, str) else user.oauth_tokens
        if not token_data or not isinstance(token_data, dict):
            return {"success": False, "error": "Invalid or unparseable OAuth tokens."}

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=["https://www.googleapis.com/auth/gmail.send"]
        )

        service = build("gmail", "v1", credentials=creds)

        if resume_attachment_path and os.path.exists(resume_attachment_path):
            from email import encoders
            from email.mime.base import MIMEBase
            from email.mime.multipart import MIMEMultipart

            message = MIMEMultipart()
            message["to"] = effective_to
            message["from"] = user.email
            message["subject"] = effective_subject
            message.attach(MIMEText(body, "plain"))
            try:
                with open(resume_attachment_path, "rb") as f:
                    part = MIMEBase("application", "pdf" if resume_attachment_path.lower().endswith(".pdf") else "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                filename = os.path.basename(resume_attachment_path)
                part.add_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
                message.attach(part)
            except Exception as att_err:
                print(f"[Attachment Warning] Could not attach resume: {att_err}")
        else:
            message = MIMEText(body)
            message["to"] = effective_to
            message["from"] = user.email
            message["subject"] = effective_subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        send_result = service.users().messages().send(
            userId="me",
            body={"raw": raw_message}
        ).execute()

        # Log into OutreachLog
        if company_id:
            log_entry = OutreachLog(
                company_id=company_id,
                user_id=user.id,
                recipient_email=effective_to,
                subject=effective_subject,
                email_body=body,
                delivery_method="OAUTH_DIRECT",
                status="SENT",
                sent_at=datetime.utcnow()
            )
            db.add(log_entry)
            db.commit()

        return {"success": True, "message_id": send_result.get("id")}
    except Exception as e:
        print(f"[OAuth Send Error] {e}")
        return {"success": False, "error": str(e)}


async def dispatch_batch_outreach(
    pitch_ids: list[int],
    user: User,
    db: Session,
    delay_min: float = 2.0,
    delay_max: float = 4.0
) -> dict[str, Any]:
    """
    Strict 1-to-1 sequential outreach batch dispatcher.
    Applies human-like random jitter delays (2-4s) between individual sends.
    """
    results = []
    sent_count = 0
    failed_count = 0

    for idx, pitch_id in enumerate(pitch_ids):
        pitch = db.query(ColdPitch).filter(ColdPitch.id == pitch_id).first()
        if not pitch or not pitch.target_email:
            continue

        # IDOR Protection: verify user ownership unless Master Admin
        if not config.is_master_admin(user.email) and pitch.user_id != user.id:
            failed_count += 1
            results.append({
                "pitch_id": pitch_id,
                "email": pitch.target_email,
                "status": "FAILED",
                "error": "Forbidden: You do not own this pitch record"
            })
            continue

        import os
        user_resume_path = os.path.join("uploads", "resumes", f"user_{user.id}_resume.pdf")
        resume_att = user_resume_path if os.path.exists(user_resume_path) else None

        res = await send_via_google_oauth(
            user=user,
            to_email=pitch.target_email,
            subject=pitch.subject_line,
            body=pitch.email_body,
            db=db,
            company_id=pitch.company_id,
            resume_attachment_path=resume_att
        )

        if res.get("success"):
            pitch.status = "SENT"
            pitch.sent_at = datetime.utcnow()
            pitch.delivery_method = "OAUTH_DIRECT"
            sent_count += 1
            results.append({"pitch_id": pitch.id, "email": pitch.target_email, "status": "SENT"})
        else:
            pitch.status = "FAILED"
            failed_count += 1
            results.append({"pitch_id": pitch.id, "email": pitch.target_email, "status": "FAILED", "error": res.get("error")})

        db.commit()

        # Apply random human jitter delay before next send (skip on last item)
        if idx < len(pitch_ids) - 1:
            jitter = random.uniform(delay_min, delay_max)
            await asyncio.sleep(jitter)

    return {
        "total": len(pitch_ids),
        "sent": sent_count,
        "failed": failed_count,
        "details": results
    }
