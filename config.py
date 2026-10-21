import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

PROJECT_NAME = os.getenv("PROJECT_NAME", "OutreachPilot")
TAGLINE = os.getenv("TAGLINE", "Find Leads. Personalize. Reach Out.")
APP_DESCRIPTOR = os.getenv("APP_DESCRIPTOR", "AI Outreach Automation")

DEV_MODE = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")
DEV_OVERRIDE_EMAIL = os.getenv("DEV_OVERRIDE_EMAIL", "rahulvora234@gmail.com")

GROQ_API_KEYS_RAW = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in GROQ_API_KEYS_RAW.split(",") if k.strip()]
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/outreachpilot")

# Master Admin Email configuration (supports multiple comma-separated emails)
MASTER_ADMIN_EMAILS_RAW = os.getenv("MASTER_ADMIN_EMAILS", "vorarahul111@gmail.com")
MASTER_ADMIN_EMAILS = [
    email.strip().lower() for email in MASTER_ADMIN_EMAILS_RAW.split(",") if email.strip()
]

# Security Secrets & Cryptography
SECRET_KEY = os.getenv("SECRET_KEY", "outreachpilot_super_secret_production_key_9837498172")

import base64
import hashlib
import json
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from cryptography.fernet import Fernet

_signer = URLSafeTimedSerializer(SECRET_KEY, salt="pilot-auth-cookie")
_fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
_cipher = Fernet(_fernet_key)


def sign_user_email(email: str) -> str:
    """Signs an email address into a tamper-proof session token."""
    return _signer.dumps(email.strip().lower())


def verify_user_email(token: str, max_age: int = 86400 * 30) -> str | None:
    """Verifies a signed session token. Returns email if valid, else None."""
    if not token:
        return None
    try:
        return _signer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, Exception):
        return None


def encrypt_tokens(token_dict: dict) -> str:
    """Encrypts OAuth credentials into ciphertext for database storage."""
    raw = json.dumps(token_dict).encode("utf-8")
    return _cipher.encrypt(raw).decode("utf-8")


def decrypt_tokens(encrypted_str: str) -> dict | None:
    """Decrypts OAuth credentials from ciphertext."""
    if not encrypted_str:
        return None
    try:
        decrypted = _cipher.decrypt(encrypted_str.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        # Fallback in case tokens were stored as raw JSON dict earlier
        if isinstance(encrypted_str, dict):
            return encrypted_str
        try:
            return json.loads(encrypted_str)
        except Exception:
            return None


def is_master_admin(email: str | None) -> bool:
    if not email:
        return False
    clean_email = email.strip().strip("\"'").lower()
    return clean_email in MASTER_ADMIN_EMAILS


import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_public_url(url: str) -> bool:
    """
    Prevents Server-Side Request Forgery (SSRF) attacks by verifying that a URL:
    1. Uses http or https scheme.
    2. Has a valid non-empty hostname.
    3. Does not resolve to localhost, loopback (127.0.0.0/8), private subnets,
       link-local addresses (169.254.0.0/16), or cloud metadata services.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        hostname = hostname.strip().lower()
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if hostname in ("169.254.169.254", "metadata.google.internal", "instance-data"):
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        except ValueError:
            try:
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False
            except Exception:
                return False
        return True
    except Exception:
        return False


