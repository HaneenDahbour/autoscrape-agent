"""
risk_engine.py — Field-level safety gate.

Purpose:
  Before touching the network, inspect the fields the user wants to extract.
  If any field name matches a sensitive category, block the entire job.
  This prevents accidental or intentional collection of private personal data.

Decision logged: risk_level ("low" / "high"), allowed (True / False).
"""

from src.models import JobContext

# Fields that must never be collected.
# These names cover common database column naming conventions.
SENSITIVE_FIELDS = {
    "password", "passwd", "pwd",
    "token", "access_token", "refresh_token", "auth_token", "api_key",
    "cookie", "session", "session_id",
    "credit_card", "card_number", "cvv", "ccv",
    "national_id", "ssn", "social_security",
    "private_email",          # generic public "email" is allowed
    "phone_number", "phone", "mobile",
}

# Fields explicitly considered safe public data.
SAFE_FIELDS = {
    "title", "price", "url", "href", "link",
    "availability", "description", "category",
    "date", "author", "rating", "name",
    "image", "thumbnail", "currency",
}


def run_risk_engine(ctx: JobContext) -> JobContext:
    """
    Check each requested field against the sensitive fields blocklist.

    Sets:
      ctx.risk_level      — "high" if any sensitive field found, else "low"
      ctx.allowed         — False if risk_level is "high"
      ctx.authorization_status — updated to "blocked" or left for later layers
    Appends a decision to ctx.decisions.
    """
    requested = [f.lower().strip() for f in ctx.fields]
    blocked_fields = [f for f in requested if f in SENSITIVE_FIELDS]

    if blocked_fields:
        ctx.risk_level = "high"
        ctx.allowed = False
        ctx.authorization_status = "blocked"
        reason = (
            f"Requested fields contain sensitive data categories: "
            f"{blocked_fields}. Collection of these fields is not permitted."
        )
        ctx.decisions.append({
            "layer": "risk_engine",
            "decision": "blocked",
            "reason": reason,
        })
        ctx.errors.append(reason)
    else:
        ctx.risk_level = "low"
        # allowed stays True — subsequent layers may still flip it
        reason = (
            f"All requested fields ({requested}) passed sensitive-field check. "
            f"Risk level: low."
        )
        ctx.decisions.append({
            "layer": "risk_engine",
            "decision": "permitted",
            "reason": reason,
        })

    return ctx
