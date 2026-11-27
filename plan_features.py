"""What a user can use right now, from their plan settings in the database.

One place for every plan check (server-side enforcement and what the page shows):
- master admins and the subscription kill switch get everything (unlimited mode);
- an active one-day Pro trial gets the Pro plan's features (the daily limit stays the user's own);
- everyone else gets their plan's settings, falling back to the Free plan.
"""
from datetime import datetime

from sqlalchemy.orm import Session

import config
from db import SubscriptionTier, User

EMAIL_STYLES = ("standard", "tailored", "tailored_fit")
EMAIL_STYLE_LABELS = {
    "standard": "Standard application",
    "tailored": "Company-tailored application",
    "tailored_fit": "Tailored application + fit summary",
}
# Everything on: master admins and kill-switch "temp user" mode.
ALL_FEATURES = {"email_style": "tailored_fit", "best_matches": True, "linkedin": True, "resume_slots": 3, "bulk": True}


def tier_features(tier: SubscriptionTier | None) -> dict:
    if not tier:
        return {"email_style": "standard", "best_matches": False, "linkedin": False, "resume_slots": 1, "bulk": False}
    style = tier.email_style if tier.email_style in EMAIL_STYLES else "tailored"
    return {
        "email_style": style,
        "best_matches": bool(tier.has_best_matches),
        "linkedin": bool(tier.has_linkedin),
        "resume_slots": max(1, int(tier.resume_slots or 1)),
        "bulk": bool(tier.has_bulk),
    }


def trial_active(user: User | None) -> bool:
    ends = getattr(user, "trial_ends_at", None) if user else None
    return bool(ends and ends > datetime.utcnow())


def plan_features(db: Session, user: User | None, kill_switch: bool = False) -> dict:
    """Features for this user now, plus where they come from ("admin", "trial", "plan")."""
    if user and (getattr(user, "is_admin", False) or config.is_master_admin(user.email)):
        return dict(ALL_FEATURES, source="admin")
    if user and kill_switch:
        return dict(ALL_FEATURES, source="admin")
    if trial_active(user):
        pro = db.query(SubscriptionTier).filter(SubscriptionTier.code == "pro").first()
        return dict(tier_features(pro), source="trial")
    code = (getattr(user, "subscription_tier", None) or "free") if user else "free"
    tier = db.query(SubscriptionTier).filter(SubscriptionTier.code == code).first()
    if not tier:
        tier = db.query(SubscriptionTier).filter(SubscriptionTier.code == "free").first()
    return dict(tier_features(tier), source="plan")


if __name__ == "__main__":
    # Self-check of the resolution order without touching the database.
    class _T:  # minimal plan row
        def __init__(self, **kw):
            self.__dict__.update(kw)
    free = _T(email_style="standard", has_best_matches=False, has_linkedin=False, resume_slots=1, has_bulk=False)
    assert tier_features(free)["bulk"] is False and tier_features(None)["email_style"] == "standard"
    assert tier_features(_T(email_style="bogus", has_best_matches=1, has_linkedin=0, resume_slots=0, has_bulk=1)) == \
        {"email_style": "tailored", "best_matches": True, "linkedin": False, "resume_slots": 1, "bulk": True}
    print("plan_features self-check passed")
