import asyncio
import base64
import html
import random
import time
import urllib.parse
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from typing import Any

import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from db import ColdPitch, DoNotContact, OutreachLog, SendAttachment, SessionLocal, User

# --- Opt-out (do-not-contact) ---
# Every email carries a signed link; opening it adds the recipient to
# do_not_contact, and no OutreachPilot user can email that address again.
_optout_signer = URLSafeSerializer(config.SECRET_KEY, salt="recipient-optout")
PUBLIC_BASE_URL = (os.getenv("APP_BASE_URL") or "https://outreachpilot.in").rstrip("/")


def optout_url(recipient: str) -> str:
    return f"{PUBLIC_BASE_URL}/unsubscribe?t={_optout_signer.dumps(recipient.strip().lower())}"


def read_optout_token(token: str) -> str | None:
    try:
        email = _optout_signer.loads(token)
        return email if isinstance(email, str) and "@" in email else None
    except BadSignature:
        return None


def is_do_not_contact(db: Session, email: str) -> bool:
    return db.query(DoNotContact).filter(DoNotContact.email == email.strip().lower()).first() is not None


def add_do_not_contact(db: Session, email: str, source: str = "unsubscribe_link") -> None:
    email = email.strip().lower()
    if not is_do_not_contact(db, email):
        db.add(DoNotContact(email=email, source=source))
        db.commit()


def with_optout_footer(body: str, recipient: str) -> str:
    return f"{body.rstrip()}\n\n--\nNot interested? Unsubscribe: {optout_url(recipient)}"


def html_with_optout_footer(body: str, recipient: str) -> str:
    """HTML version of the email: paragraphs use the reader's full width (Gmail wraps plain text narrow)."""
    paras = [p for p in body.replace("\r\n", "\n").strip().split("\n\n") if p.strip()]
    html_body = "".join(f"<p>{html.escape(p.strip()).replace(chr(10), '<br>')}</p>" for p in paras)
    link = html.escape(optout_url(recipient), quote=True)
    return (f"<div>{html_body}<p style=\"margin-top:24px;color:#888;font-size:12px\">"
            f"Not interested? <a href=\"{link}\" style=\"color:#888\">Unsubscribe</a></p></div>")


def _text_and_html(text_body: str, html_body: str):
    from email.mime.multipart import MIMEMultipart
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    return alt


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
    resume_attachment_path: str | None = None,
    resume_attachment_bytes: bytes | None = None,
    resume_attachment_name: str | None = None
) -> dict[str, Any]:
    """
    Sends an email directly through user's authorized Google OAuth 2.0 credentials.
    Redirects to DEV_OVERRIDE_EMAIL if DEV_MODE is active.
    Supports optional resume PDF attachment via file path or direct in-memory bytes.
    """
    if not user.oauth_tokens:
        return {"success": False, "error": "Google OAuth account not connected."}

    if not to_email or not str(to_email).strip():
        return {"success": False, "error": "Company email not found! Cannot send email."}

    # Opted-out recipients are never emailed, by any user.
    if is_do_not_contact(db, to_email):
        return {"success": False, "blocked": True,
                "error": "This address opted out of emails from OutreachPilot users. Not sent."}
    sent_body = with_optout_footer(body, to_email)
    sent_html = html_with_optout_footer(body, to_email)
    unsubscribe_link = optout_url(to_email)

    effective_to = get_effective_recipient(to_email)
    effective_subject = f"[TEST -> {to_email}] {subject}" if config.DEV_MODE else subject

    try:
        import os
        token_data = config.decrypt_tokens(user.oauth_tokens) if isinstance(user.oauth_tokens, str) else user.oauth_tokens
        if not token_data or not isinstance(token_data, dict):
            return {"success": False, "error": "Invalid or unparseable OAuth tokens. Please reconnect Google."}

        client_id = token_data.get("client_id") or config.GOOGLE_CLIENT_ID
        client_secret = token_data.get("client_secret") or config.GOOGLE_CLIENT_SECRET
        refresh_token = token_data.get("refresh_token")
        token_uri = token_data.get("token_uri") or "https://oauth2.googleapis.com/token"

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/gmail.send"]
        )

        # Proactively refresh token if expired
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            auth_request = GoogleAuthRequest()
            if creds.expired or not creds.valid:
                if creds.refresh_token:
                    creds.refresh(auth_request)
                    token_data["token"] = creds.token
                    user.oauth_tokens = config.encrypt_tokens(token_data)
                    db.commit()
                else:
                    return {
                        "success": False,
                        "error": "Google session expired. Please sign in with Google again to grant email sending permissions."
                    }
        except Exception as refresh_err:
            err_str = str(refresh_err)
            print(f"[OAuth Refresh Warning]: {err_str}")
            if "invalid_grant" in err_str.lower() or "refresh the access token" in err_str.lower():
                return {
                    "success": False,
                    "error": "Google session expired. Please sign in with Google again to refresh email sending permissions."
                }

        service = build("gmail", "v1", credentials=creds)

        has_attachment = False
        att_bytes = None
        att_filename = "Resume.pdf"

        if resume_attachment_bytes:
            has_attachment = True
            att_bytes = resume_attachment_bytes
            att_filename = resume_attachment_name or "Resume.pdf"
        elif resume_attachment_path and os.path.exists(resume_attachment_path):
            try:
                with open(resume_attachment_path, "rb") as f:
                    att_bytes = f.read()
                has_attachment = True
                att_filename = os.path.basename(resume_attachment_path)
            except Exception as read_err:
                print(f"[Attachment Warning] Could not read file {resume_attachment_path}: {read_err}")

        if has_attachment and att_bytes:
            from email import encoders
            from email.mime.base import MIMEBase
            from email.mime.multipart import MIMEMultipart

            message = MIMEMultipart()
            message["to"] = effective_to
            message["from"] = user.email
            message["subject"] = effective_subject
            message.attach(_text_and_html(sent_body, sent_html))
            try:
                subtype = "pdf" if att_filename.lower().endswith(".pdf") else "octet-stream"
                part = MIMEBase("application", subtype)
                part.set_payload(att_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{att_filename}"')
                message.attach(part)
            except Exception as att_err:
                print(f"[Attachment Warning] Could not attach resume bytes: {att_err}")
        else:
            message = _text_and_html(sent_body, sent_html)
            message["to"] = effective_to
            message["from"] = user.email
            message["subject"] = effective_subject

        # RFC 8058 one-click unsubscribe (Gmail shows an "Unsubscribe" button).
        message["List-Unsubscribe"] = f"<{unsubscribe_link}>"
        message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

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


# --- Send queue ---
# Bulk sends are queued (ColdPitch.status = QUEUED) and sent here in the background, so a batch
# survives a closed tab or a server restart. Rows are claimed with FOR UPDATE SKIP LOCKED, so no
# two workers ever send the same email. One user's emails go out 2 to 3.5 s apart (human pace).
QUEUE_MAX_ATTEMPTS = 3
QUEUE_CONCURRENCY = 3          # different users sent in parallel
QUEUE_POLL_SECONDS = 2.0
QUEUE_USER_GAP = (2.0, 3.5)    # seconds between two emails of the same user

# Errors that will fail again on retry: stop and refund the quota.
_PERMANENT_ERRORS = (
    "not connected", "session expired", "invalid or unparseable", "email not found",
    "opted out", "invalid to header", "invalid recipient", "invalid_grant", "not available for sending",
)


def refund_daily_pitches(db: Session, user_id: int, count: int) -> None:
    """Give back reserved sends that did not go out (failed or skipped)."""
    if count <= 0:
        return
    db.execute(text(
        "UPDATE users SET pitches_sent_today = GREATEST(0, COALESCE(pitches_sent_today, 0) - :n) WHERE id = :uid"
    ), {"uid": user_id, "n": int(count)})
    db.commit()


def recover_interrupted_sends() -> int:
    """Run at startup. A row left in SENDING was cut off mid-send, so it may or may not have gone
    out; mark it FAILED (never resend: a duplicate email to a company is worse than a missed one)."""
    with SessionLocal() as db:
        n = db.query(ColdPitch).filter(ColdPitch.status == "SENDING").update(
            {ColdPitch.status: "FAILED",
             ColdPitch.last_error: "Interrupted while sending. Check your Gmail Sent folder before sending again."},
            synchronize_session=False)
        db.commit()
        return n or 0


def _claim_next(busy_user_ids: list[int]) -> tuple[int, int] | None:
    """Atomically move the oldest due QUEUED pitch (of a user not currently pacing) to SENDING.
    Returns (pitch_id, user_id)."""
    with SessionLocal() as db:
        row = db.execute(text("""
            UPDATE cold_pitches SET status = 'SENDING', send_attempts = COALESCE(send_attempts, 0) + 1
            WHERE id = (
                SELECT id FROM cold_pitches
                WHERE status = 'QUEUED'
                  AND (next_attempt_at IS NULL OR next_attempt_at <= :now)
                  AND NOT (user_id = ANY(:busy))
                ORDER BY queued_at NULLS FIRST, id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, user_id
        """), {"now": datetime.utcnow(), "busy": busy_user_ids or [0]}).fetchone()
        db.commit()
        return (int(row[0]), int(row[1] or 0)) if row else None


def _send_queued_pitch(pitch_id: int) -> str:
    """Send one claimed pitch (runs in a worker thread). Returns SENT, RETRY, FAILED or GONE."""
    with SessionLocal() as db:
        pitch = db.query(ColdPitch).filter(ColdPitch.id == pitch_id).first()
        if not pitch:
            return "GONE"
        user = db.query(User).filter(User.id == pitch.user_id).first()

        if not user or getattr(user, "is_banned", False):
            res = {"success": False, "error": "Account not available for sending (not connected or suspended)."}
        else:
            att = db.query(SendAttachment).filter(SendAttachment.user_id == user.id).first()
            stored = os.path.join("uploads", "resumes", f"user_{user.id}_resume.pdf")
            try:
                res = asyncio.run(send_via_google_oauth(
                    user=user, to_email=pitch.target_email, subject=pitch.subject_line, body=pitch.email_body,
                    db=db, company_id=pitch.company_id,
                    resume_attachment_bytes=att.data if att else None,
                    resume_attachment_name=att.filename if att else None,
                    resume_attachment_path=None if att else (stored if os.path.exists(stored) else None),
                ))
            except Exception as e:
                res = {"success": False, "error": str(e)}

        if res.get("success"):
            pitch.status, pitch.sent_at, pitch.delivery_method = "SENT", datetime.utcnow(), "OAUTH_DIRECT"
            pitch.last_error, pitch.next_attempt_at, pitch.quota_reserved = None, None, False
            db.commit()
            return "SENT"

        err = str(res.get("error") or "Unknown send error")[:1000]
        permanent = bool(res.get("blocked")) or any(k in err.lower() for k in _PERMANENT_ERRORS)
        attempts = pitch.send_attempts or 1
        pitch.last_error = err
        if not permanent and attempts < QUEUE_MAX_ATTEMPTS:
            # Temporary (Gmail rate limit, network): retry after 1, then 2 minutes.
            pitch.status = "QUEUED"
            pitch.next_attempt_at = datetime.utcnow() + timedelta(minutes=2 ** (attempts - 1))
            db.commit()
            return "RETRY"
        pitch.status, pitch.next_attempt_at = "FAILED", None
        refund = bool(pitch.quota_reserved)
        pitch.quota_reserved = False
        db.commit()
        # shortcut: a refund after midnight IST credits the new day, not the day it was queued; rare, fine at this scale
        if refund and pitch.user_id:
            refund_daily_pitches(db, pitch.user_id, 1)
        return "FAILED"


async def run_send_queue() -> None:
    """Background worker started from the app lifespan; runs until the app stops."""
    try:
        n = await asyncio.to_thread(recover_interrupted_sends)
        if n:
            print(f"[SendQueue] Marked {n} interrupted send(s) as FAILED.")
    except Exception as e:
        print(f"[SendQueue] Recovery failed: {e}")

    next_allowed: dict[int, float] = {}   # user_id -> monotonic time their next email may go
    in_flight: dict[asyncio.Task, int] = {}  # task -> user_id

    while True:
        try:
            for task in [t for t in in_flight if t.done()]:
                uid = in_flight.pop(task)
                if task.exception():
                    print(f"[SendQueue] Send crashed: {task.exception()}")
                next_allowed[uid] = time.monotonic() + random.uniform(*QUEUE_USER_GAP)

            while len(in_flight) < QUEUE_CONCURRENCY:
                now = time.monotonic()
                busy = [u for u, ts in next_allowed.items() if ts > now]
                claimed = await asyncio.to_thread(_claim_next, busy)
                if claimed is None:
                    break
                pid, uid = claimed
                next_allowed[uid] = float("inf")  # no second email for this user until this one finishes
                in_flight[asyncio.create_task(asyncio.to_thread(_send_queued_pitch, pid))] = uid
        except Exception as e:
            print(f"[SendQueue] Loop error: {e}")
        await asyncio.sleep(QUEUE_POLL_SECONDS)
