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


# "See example" samples on the plan cards: one fictional company and candidate, always labelled
# "Example" on the page, and editable by the admin (stored in system_settings "plan_examples").
EXAMPLE_KEYS = ("standard", "tailored", "tailored_fit", "best_matches", "linkedin", "resumes", "bulk")
DEFAULT_PLAN_EXAMPLES = {
    "standard": (
        "Subject: Application for a Full Stack Developer role\n\n"
        "Hi Brightleaf Studio team,\n\n"
        "I'm Aarav, a Full Stack Developer working with React, Node.js and PostgreSQL. "
        "I'd like to apply for an open developer role on your team. My resume is attached.\n\n"
        "Thank you for your time,\nAarav"
    ),
    "tailored": (
        "Subject: Full Stack Developer for Brightleaf Studio's booking platform\n\n"
        "Hi Brightleaf Studio team,\n\n"
        "I saw that you build online booking tools for salons and clinics with React and Node.js. "
        "That's the stack I work in every day. In my last role I built a scheduling dashboard used by 40 clinics.\n\n"
        "I'd love to help grow your platform. My resume is attached.\n\n"
        "Regards,\nAarav"
    ),
    "tailored_fit": (
        "Subject: Full Stack Developer for Brightleaf Studio's booking platform\n\n"
        "Hi Brightleaf Studio team,\n\n"
        "I saw that you build online booking tools for salons and clinics with React and Node.js...\n\n"
        "Why I fit Brightleaf Studio:\n"
        "- Your React booking widgets: I work with React\n"
        "- Your appointment reminders: Built SMS reminders that cut no-shows by 30%\n\n"
        "Regards,\nAarav"
    ),
    "best_matches": (
        "Brightleaf Studio\n"
        "Matches React, Node.js (2 of your skills)\n\n"
        "Companies that use the skills on your resume are shown first."
    ),
    "linkedin": (
        "LinkedIn message:\n"
        "Hi [Name], I'm Aarav, a Full Stack Developer. I just applied to Brightleaf Studio and like what "
        "your team is building. Happy to connect.\n\n"
        "Referral request:\n"
        "Hi [Name], I've applied for a developer role at Brightleaf Studio. If you think I'm a good fit, "
        "would you be open to referring me? Thank you."
    ),
    "resumes": (
        "Aarav's resumes: Full Stack (main), QA, Backend\n\n"
        "Brightleaf Studio uses Cypress and Jest, so its email is written from the QA resume "
        "and that resume is attached."
    ),
    "bulk": (
        "Select 20 companies and click Send Emails.\n"
        "Each company gets its own email from Aarav's Gmail, sent in the background."
    ),
}


def plan_card_lines(tiers: list[dict], trial_hours: int | None = None) -> list[dict]:
    """Copies of the public plan dicts with "lines": [{"text", "example"}], built from the plan
    settings. A line every plan shares is left out (it doesn't help anyone choose).
    trial_hours: show the Free plan's one-time trial line (None when the trial is off)."""
    def own(t: dict) -> list[dict]:
        slots = int(t.get("resume_slots") or 1)
        lines = [{"text": EMAIL_STYLE_LABELS.get(t.get("email_style"), EMAIL_STYLE_LABELS["tailored"]),
                  "example": t.get("email_style") if t.get("email_style") in EMAIL_STYLES else "tailored"}]
        if t.get("has_best_matches"):
            lines.append({"text": "Best matches for your resume", "example": "best_matches"})
        if t.get("has_linkedin"):
            lines.append({"text": "LinkedIn message + referral request", "example": "linkedin"})
        lines.append({"text": f"Up to {slots} resumes, picked for each company", "example": "resumes"} if slots > 1
                     else {"text": "1 resume", "example": None})
        if t.get("has_bulk"):
            lines.append({"text": "Apply in bulk", "example": "bulk"})
        if trial_hours and int(t.get("price_inr") or 0) == 0:
            length = "One-day" if trial_hours == 24 else f"{trial_hours}-hour"
            lines.append({"text": f"{length} Pro trial, once per account", "example": None})
        lines += [{"text": f, "example": None} for f in (t.get("features") or [])]
        return lines

    built = [dict(t, lines=own(t)) for t in tiers]
    if len(built) > 1:
        shared = set.intersection(*({ln["text"] for ln in t["lines"]} for t in built))
        for t in built:
            t["lines"] = [ln for ln in t["lines"] if ln["text"] not in shared]
    return built


if __name__ == "__main__":
    # Self-check of the resolution order without touching the database.
    class _T:  # minimal plan row
        def __init__(self, **kw):
            self.__dict__.update(kw)
    free = _T(email_style="standard", has_best_matches=False, has_linkedin=False, resume_slots=1, has_bulk=False)
    assert tier_features(free)["bulk"] is False and tier_features(None)["email_style"] == "standard"
    assert tier_features(_T(email_style="bogus", has_best_matches=1, has_linkedin=0, resume_slots=0, has_bulk=1)) == \
        {"email_style": "tailored", "best_matches": True, "linkedin": False, "resume_slots": 1, "bulk": True}
    cards = plan_card_lines([
        {"code": "free", "price_inr": 0, "email_style": "standard", "resume_slots": 1, "features": ["Sends from your own Gmail"]},
        {"code": "pro", "price_inr": 199, "email_style": "tailored_fit", "has_bulk": True, "resume_slots": 3,
         "features": ["Sends from your own Gmail"]},
    ], trial_hours=24)
    free_lines = [ln["text"] for ln in cards[0]["lines"]]
    assert "Sends from your own Gmail" not in free_lines  # shared by every plan: dropped
    assert free_lines == ["Standard application", "1 resume", "One-day Pro trial, once per account"], free_lines
    assert [ln["example"] for ln in cards[1]["lines"]] == ["tailored_fit", "resumes", "bulk"]
    print("plan_features self-check passed")
